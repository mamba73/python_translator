"""
app/logger.py — Logging setup za osnovne, verbatim i LLM response logove
Ref: doc/README_TechDoc.md §14
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any


def setup_logging(config: dict[str, Any]) -> None:
    """Postavlja logging konfiguraciju na temelju settings.yaml.

    Kreira tri loggera:
    - Osnovni logger (uvijek aktivan) → work/logs/app.log
    - Verbatim logger (opcionalan) → work/logs/verbatim.log
    - LLM response logger (opcionalan) → work/logs/llm_responses.log

    Args:
        config: Globalna konfiguracija iz settings.yaml.
    """
    log_dir = Path(config["directories"]["logs"])
    log_dir.mkdir(parents=True, exist_ok=True)

    # Osnovni logger
    basic_log = log_dir / "app.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(basic_log, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Verbatim logger (opcionalan)
    if config.get("logging", {}).get("verbatim", False):
        verbatim_log = log_dir / "verbatim.log"
        _setup_verbatim_logger(verbatim_log)

    # LLM response logger (opcionalan)
    if config.get("logging", {}).get("llm_responses", False):
        llm_log = log_dir / "llm_responses.log"
        _setup_llm_logger(llm_log)

    logging.info("Logging inicijaliziran.")


def log_basic(message: str, level: str = "info") -> None:
    """Bilježi osnovnu poruku u app.log.

    Args:
        message: Poruka za bilježenje.
        level: Log level ('debug', 'info', 'warning', 'error').
    """
    log_fn = getattr(logging, level.lower(), logging.info)
    log_fn(message)


def log_verbatim(content: str, context: str = "") -> None:
    """Bilježi sirovi sadržaj u verbatim.log (ako je omogućen).

    Koristi se za bilježenje originalnog teksta prije čišćenja,
    segmentacije, itd.

    Args:
        content: Sirovi sadržaj za bilježenje.
        context: Kontekstualni opis (npr. "Chapter 1 - original").
    """
    logger = logging.getLogger("verbatim")
    if not logger.handlers:
        return  # Verbatim logging nije omogućen
    logger.info(f"=== {context} ===\n{content}\n")


def log_llm_response(prompt: str, response: str, metadata: dict[str, Any] | None = None) -> None:
    """Bilježi LLM prompt i response u llm_responses.log (ako je omogućen).

    Koristi se za debugging i analizu kvalitete prijevoda.

    Args:
        prompt: Prompt poslan modelu.
        response: Odgovor od modela.
        metadata: Dodatni podaci (npr. segment info, model name).
    """
    logger = logging.getLogger("llm_responses")
    if not logger.handlers:
        return  # LLM response logging nije omogućen

    meta_str = ""
    if metadata:
        meta_str = "\n".join(f"  {k}: {v}" for k, v in metadata.items())

    logger.info(f"=== LLM CALL ===\n{meta_str}\n=== PROMPT ===\n{prompt}\n=== RESPONSE ===\n{response}\n")


# ---------------------------------------------------------------------------
# Interne pomoćne funkcije
# ---------------------------------------------------------------------------

def _setup_verbatim_logger(log_path: Path) -> None:
    """Postavlja verbatim logger sa vlastitim handlerom."""
    logger = logging.getLogger("verbatim")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # Ne šalji u root logger
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    logger.addHandler(handler)


def _setup_llm_logger(log_path: Path) -> None:
    """Postavlja LLM response logger sa vlastitim handlerom."""
    logger = logging.getLogger("llm_responses")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # Ne šalji u root logger
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    logger.addHandler(handler)
