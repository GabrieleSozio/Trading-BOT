"""
gitsync.py — commit & push automatico dopo ogni routine.

Best-effort: non solleva MAI eccezioni che possano far cadere una routine di trading;
in caso di problema logga e ritorna False. Include un guard di sicurezza che ABORTA
il push se in staging compaiono file che sembrano segreti (difesa in profondita',
oltre al .gitignore).

Nota: le routine girano sulla stessa macchina e si scambiano i file via `state/`
locale. Il push su GitHub serve come backup/audit, non come trasporto della staffetta.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("gitsync")

# Se un path in staging contiene uno di questi, NON si pusha (safety).
SECRET_HINTS = ("secret", ".env", "recovery", ".key", "alpaca_keys")


def _git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True, text=True, timeout=120,
    )


def sync(message: str) -> bool:
    """Stage tutto (rispettando .gitignore), commit e push. Ritorna True se OK/no-op."""
    try:
        _git(["add", "-A"])
        staged = [f for f in _git(["diff", "--cached", "--name-only"]).stdout.split() if f]

        bad = [f for f in staged if any(h in f.lower() for h in SECRET_HINTS)]
        if bad:
            log.error("ABORT push: possibili file sensibili in staging: %s", bad)
            _git(["reset"])
            return False

        if not staged:
            log.info("gitsync: nessuna modifica da pushare.")
            return True

        c = _git(["commit", "-m", message])
        if c.returncode != 0:
            log.warning("gitsync: commit fallito: %s", (c.stderr or c.stdout).strip()[:300])
            return False

        p = _git(["push", "origin", "HEAD"])
        if p.returncode != 0:
            # Il remote potrebbe essere avanti (un'altra routine ha pushato in
            # contemporanea, tipico nel cloud): rebase e riprova una volta.
            branch = _git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip() or "main"
            log.warning("gitsync: push rifiutato, provo pull --rebase + retry...")
            _git(["pull", "--rebase", "origin", branch])
            p = _git(["push", "origin", "HEAD"])
            if p.returncode != 0:
                log.error("gitsync: PUSH FALLITO (anche dopo rebase): %s", (p.stderr or p.stdout).strip()[:300])
                return False

        log.info("gitsync: push OK (%d file) -> %s", len(staged), message)
        return True
    except Exception as e:  # noqa: BLE001 — best effort, mai far cadere la routine
        log.error("gitsync: errore inatteso, push saltato: %s", e)
        return False
