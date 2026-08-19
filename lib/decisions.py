"""
decisions.py — registro delle decisioni con lezione a esito noto.

Il problema che risolve: il supervisore analizza aggregati settimanali, ma non
sa mai COSA aveva pensato quando ha aperto una posizione, ne' se quel
ragionamento si e' rivelato giusto. Ogni settimana riparte da zero.

Come funziona, in tre tempi:

  1. all'apertura si registra la decisione e il perche', in sospeso;
  2. quando la posizione si chiude si aggiunge l'esito reale (risultato,
     fattore di rischio, alpha rispetto all'indice);
  3. un modello scrive 2-4 frasi di lezione, che vengono rilette dalle
     analisi future.

Il vincolo delle 2-4 frasi non e' estetico: le lezioni finiscono dentro i
prompt successivi, e un registro prolisso mangerebbe il contesto senza
aggiungere informazione. Ogni parola deve guadagnarsi il posto.

Non prevede nulla e non decide nulla: e' memoria. Serve a non ripetere lo
stesso errore per la terza volta senza accorgersene.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .alpaca_rest import atomic_write_json, read_json, now_cet

log = logging.getLogger("decisions")

MAX_ENTRIES = 400          # oltre, si dimenticano le piu' vecchie
LESSON_MAX_CHARS = 700     # difesa contro riflessioni chilometriche


class DecisionLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    # ---------------------------------------------------------------
    def _load(self) -> list[dict]:
        try:
            d = read_json(self.path)
            return d.get("entries", []) if isinstance(d, dict) else []
        except Exception:  # noqa: BLE001 — primo avvio o file assente
            return []

    def _save(self, entries: list[dict]) -> None:
        atomic_write_json(self.path, {
            "updated_at": now_cet().isoformat(timespec="seconds"),
            "entries": entries[-MAX_ENTRIES:],
        })

    # ---------------------------------------------------------------
    def record(self, ticker: str, decision: str, **meta) -> None:
        """Registra una decisione appena presa, in attesa di esito."""
        entries = self._load()
        oggi = now_cet().date().isoformat()
        # Idempotenza: una routine che gira ogni minuto non deve duplicare.
        for e in entries:
            if e["ticker"] == ticker and e["date"] == oggi and e["status"] == "in_sospeso":
                return
        entries.append({
            "ticker": ticker,
            "date": oggi,
            "opened_at": now_cet().isoformat(timespec="seconds"),
            "decision": (decision or "").strip()[:1500],
            "meta": meta,
            "status": "in_sospeso",
        })
        self._save(entries)
        log.info("Registrata decisione su %s.", ticker)

    def pending(self) -> list[dict]:
        return [e for e in self._load() if e["status"] == "in_sospeso"]

    def resolve(self, ticker: str, date: str, outcome: dict, lesson: str) -> bool:
        """Chiude una decisione con il suo esito e la lezione imparata."""
        entries = self._load()
        for e in entries:
            if e["ticker"] == ticker and e["date"] == date and e["status"] == "in_sospeso":
                e["status"] = "chiusa"
                e["outcome"] = outcome
                e["lesson"] = (lesson or "").strip()[:LESSON_MAX_CHARS]
                e["closed_at"] = now_cet().isoformat(timespec="seconds")
                self._save(entries)
                return True
        return False

    # ---------------------------------------------------------------
    def recent_lessons(self, ticker: str | None = None,
                       n_same: int = 3, n_other: int = 5) -> str:
        """Testo da inserire nei prompt: lezioni sullo stesso titolo e altrove.

        Le lezioni sullo stesso titolo contano di piu' (stesso comportamento,
        stesso settore), ma quelle sugli altri catturano gli errori di metodo,
        che sono i piu' ripetitivi.
        """
        chiuse = [e for e in self._load() if e["status"] == "chiusa" and e.get("lesson")]
        if not chiuse:
            return ""
        same, other = [], []
        for e in reversed(chiuse):
            if ticker and e["ticker"] == ticker and len(same) < n_same:
                same.append(e)
            elif len(other) < n_other:
                other.append(e)
            if len(same) >= n_same and len(other) >= n_other:
                break

        def riga(e):
            o = e.get("outcome") or {}
            pezzi = []
            if o.get("pl_pct") is not None:
                pezzi.append(f"{o['pl_pct']:+.2f}%")
            if o.get("r_multiple") is not None:
                pezzi.append(f"{o['r_multiple']:+.2f}R")
            if o.get("alpha_pct") is not None:
                pezzi.append(f"alpha {o['alpha_pct']:+.2f}%")
            return f"- {e['ticker']} ({e['date']}, {', '.join(pezzi) or 'esito ignoto'}): {e['lesson']}"

        parti = []
        if same:
            parti.append(f"Cosa e' successo le ultime volte su {ticker}:")
            parti += [riga(e) for e in same]
        if other:
            parti.append("Lezioni recenti su altri titoli:")
            parti += [riga(e) for e in other]
        return "\n".join(parti)

    def stats(self) -> dict:
        e = self._load()
        chiuse = [x for x in e if x["status"] == "chiusa"]
        return {"totali": len(e), "chiuse": len(chiuse),
                "in_sospeso": len(e) - len(chiuse)}


# =====================================================================
#  Riflessione
# =====================================================================
_SYSTEM = """Sei un analista che rilegge una PROPRIA decisione passata ora che
l'esito e' noto. Scrivi ESATTAMENTE 2-4 frasi di prosa semplice, senza elenchi
puntati e senza titoli.

Copri nell'ordine:
1. la direzione era giusta? cita l'alpha, non il rendimento grezzo
2. quale parte del ragionamento ha tenuto e quale ha ceduto
3. UNA lezione concreta da applicare alla prossima analisi simile

Sii specifico e asciutto. Il testo verra' riletto da analisi future e ogni
parola deve guadagnarsi il posto. Non consolarti e non incolpare il mercato:
se la decisione era ragionevole ma l'esito e' stato sfortunato, dillo.
Rispondi in italiano."""

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"lezione": {"type": "string"}},
    "required": ["lezione"],
}


def reflect(decision: str, outcome: dict, model: str | None = None) -> str | None:
    """Chiede al modello la lezione. Ritorna None se l'AI non e' disponibile."""
    from . import ai_client
    if not ai_client.ai_enabled():
        return None
    parti = []
    if outcome.get("pl_pct") is not None:
        parti.append(f"Risultato: {outcome['pl_pct']:+.2f}%")
    if outcome.get("benchmark_pct") is not None:
        parti.append(f"Indice nello stesso periodo: {outcome['benchmark_pct']:+.2f}%")
    if outcome.get("alpha_pct") is not None:
        parti.append(f"Alpha: {outcome['alpha_pct']:+.2f}%")
    if outcome.get("r_multiple") is not None:
        parti.append(f"Fattore di rischio: {outcome['r_multiple']:+.2f}R")
    if outcome.get("closed_by"):
        parti.append(f"Uscita per: {outcome['closed_by']}")
    user = ("\n".join(parti) + "\n\nDecisione presa allora:\n" + (decision or "(non registrata)"))
    try:
        return (ai_client.ask_json(_SYSTEM, user, _SCHEMA,
                                   model=model, max_tokens=400) or {}).get("lezione")
    except Exception as e:  # noqa: BLE001 — mai bloccare una routine per questo
        log.warning("Riflessione non generata: %s", e)
        return None
