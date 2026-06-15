"""
ai_client.py — wrapper minimale verso l'API di Claude (Anthropic SDK).

Usato dalle SOLE routine che richiedono giudizio: ricerca di mercato (01) e
supervisore (06). Le routine di rischio/esecuzione restano deterministiche.

La chiave si legge da ANTHROPIC_API_KEY (GitHub Secret nel cloud). Se manca o la
chiamata fallisce, si solleva AIUnavailable: il chiamante DEVE avere un fallback
deterministico, così il bot non si ferma mai.
"""
from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("ai")

# Modello di default: il più capace (vedi skill claude-api). Override via config.
DEFAULT_MODEL = "claude-opus-4-8"


class AIUnavailable(RuntimeError):
    """L'AI non è utilizzabile (chiave mancante, SDK assente, errore API)."""


def ai_enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def ask_json(system: str, user: str, schema: dict, model: str | None = None,
             max_tokens: int = 3000) -> dict:
    """Chiede a Claude una risposta JSON conforme a `schema` (structured output).
    Ritorna il dict già parsato. Solleva AIUnavailable in caso di problemi."""
    if not ai_enabled():
        raise AIUnavailable("ANTHROPIC_API_KEY non impostata")
    try:
        import anthropic
    except ImportError as e:
        raise AIUnavailable(f"SDK anthropic non installato: {e}") from e

    client = anthropic.Anthropic()  # legge ANTHROPIC_API_KEY dall'ambiente
    try:
        resp = client.messages.create(
            model=model or DEFAULT_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
    except Exception as e:  # noqa: BLE001 — qualsiasi errore API -> fallback
        raise AIUnavailable(f"chiamata API fallita: {type(e).__name__}: {e}") from e

    # Con output strutturato il blocco di testo contiene JSON valido.
    text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), None)
    if not text:
        raise AIUnavailable("risposta senza blocco di testo")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise AIUnavailable(f"JSON non valido dall'AI: {e}") from e
