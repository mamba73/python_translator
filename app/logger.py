"""
app/logger.py — Logging setup za osnovne, verbatim i LLM response logove
Ref: doc/README_TechDoc.md §14
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


# Putanja do aktivne sesije — postavlja setup_logging(), čita get_session_log_dir()
_SESSION_LOG_DIR: Path | None = None


# ---------------------------------------------------------------------------
# FlushFileHandler — identičan kao u web_server.py, za CLI use-case
# ---------------------------------------------------------------------------
class FlushFileHandler(logging.FileHandler):
    """FileHandler koji poziva flush() nakon svakog emit() — log na disku uvijek aktualan."""

    def __init__(self, filename: str | Path, **kwargs: Any) -> None:
        super().__init__(str(filename), encoding="utf-8", delay=False, **kwargs)

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


def setup_logging(config: dict[str, Any]) -> None:
    """Postavlja logging konfiguraciju na temelju settings.yaml.

    Kreira sesijski poddirektorij s vremenskim žigom i unutar njega tri loggera:
    - Osnovni logger (uvijek aktivan) → work/logs/session_YYYYMMDD_HHMMSS/app.log
    - Verbatim logger (opcionalan) → work/logs/session_YYYYMMDD_HHMMSS/verbatim.log
    - LLM response logger (opcionalan) → work/logs/session_YYYYMMDD_HHMMSS/llm_responses.log

    Args:
        config: Globalna konfiguracija iz settings.yaml.
    """
    global _SESSION_LOG_DIR

    base_log_dir = Path(config["directories"]["logs"])
    base_log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = base_log_dir / f"session_{timestamp}"
    session_dir.mkdir(parents=True, exist_ok=True)
    _SESSION_LOG_DIR = session_dir

    root = logging.getLogger()

    # Ukloni stare FileHandler-e (idempotentno)
    for h in list(root.handlers):
        if isinstance(h, logging.FileHandler):
            try:
                h.close()
            except Exception:
                pass
            root.removeHandler(h)

    root.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"
    )

    # Handler 1: datoteka s trenutnim flushom
    basic_log = session_dir / "app.log"
    fh = FlushFileHandler(basic_log)
    fh.setFormatter(fmt)
    fh.setLevel(logging.INFO)
    root.addHandler(fh)

    # Handler 2: konzola (stdout)
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
               for h in root.handlers):
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fmt)
        ch.setLevel(logging.INFO)
        root.addHandler(ch)

    # Verbatim logger (opcionalan)
    if config.get("logging", {}).get("verbatim", False):
        verbatim_log = session_dir / "verbatim.log"
        _setup_verbatim_logger(verbatim_log)

    # LLM response logger (opcionalan)
    if config.get("logging", {}).get("llm_responses", False):
        llm_log = session_dir / "llm_responses.log"
        _setup_llm_logger(llm_log)

    logging.info("Logging inicijaliziran.")


def get_session_log_dir() -> Path | None:
    """Vraća putanju do direktorija aktivne sesije ili None ako nije inicijaliziran."""
    return _SESSION_LOG_DIR


def log_basic(message: str, level: str = "info") -> None:
    """Bilježi osnovnu poruku u app.log.

    Args:
        message: Poruka za bilježenje.
        level: Log level ('debug', 'info', 'warning', 'error').
    """
    log_fn = getattr(logging, level.lower(), logging.info)
    log_fn(message)


def log_verbatim(content: str, context: str = "") -> None:
    """Bilježi sirovi sadržaj u verbatim.log (logger ili direktni fallback).

    Args:
        content: Sirovi sadržaj za bilježenje.
        context: Kontekstualni opis (npr. "Chapter 1 - original").
    """
    logger = logging.getLogger("verbatim")
    linija = f"=== {context} ===\n{content}\n"
    if logger.handlers:
        logger.info(linija)
    elif _SESSION_LOG_DIR:
        path = _SESSION_LOG_DIR / "verbatim.log"
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%H:%M:%S')} - {linija}\n")
            f.flush()


def log_llm_response(prompt: str, response: str, metadata: dict[str, Any] | None = None) -> None:
    """Bilježi LLM prompt i response u llm_responses.log (logger ili direktni fallback).

    Args:
        prompt: Prompt poslan modelu.
        response: Odgovor od modela.
        metadata: Dodatni podaci (npr. segment info, model name).
    """
    logger = logging.getLogger("llm_responses")
    meta_str = ""
    if metadata:
        meta_str = "\n".join(f"  {k}: {v}" for k, v in metadata.items())
    linija = f"=== LLM CALL ===\n{meta_str}\n=== PROMPT ===\n{prompt}\n=== RESPONSE ===\n{response}\n"
    if logger.handlers:
        logger.info(linija)
    elif _SESSION_LOG_DIR:
        path = _SESSION_LOG_DIR / "llm_responses.log"
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%H:%M:%S')} - {linija}\n")
            f.flush()


# ---------------------------------------------------------------------------
# Interne pomoćne funkcije
# ---------------------------------------------------------------------------

def _setup_verbatim_logger(log_path: Path) -> None:
    """Postavlja verbatim logger sa FlushFileHandler-om."""
    logger = logging.getLogger("verbatim")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = FlushFileHandler(log_path)
        handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
        logger.addHandler(handler)


def _setup_llm_logger(log_path: Path) -> None:
    """Postavlja LLM response logger sa FlushFileHandler-om."""
    logger = logging.getLogger("llm_responses")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = FlushFileHandler(log_path)
        handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
        logger.addHandler(handler)
