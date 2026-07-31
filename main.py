#!/usr/bin/env python3
"""
main.py — Dynamic Book Translator v0.4
Čisti orkestrator koji poziva module iz app/
Ref: doc/README_TechDoc.md §21
"""

from __future__ import annotations

import sys
import logging
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.config_loader import load_global_config
from app.file_manager import FileManager
from app.logger import setup_logging
from app.checkpoint import CheckpointManager
from app.menu import Menu


def main() -> int:
    """Glavni entry point aplikacije.

    Returns:
        Exit code (0 za uspjeh, 1 za grešku).
    """
    try:
        # 1. Učitaj globalnu konfiguraciju
        config = load_global_config()

        # 2. Setup logging
        setup_logging(config)

        # 3. Inicijaliziraj FileManager i osiguraj direktorije
        file_manager = FileManager(config)
        file_manager.ensure_directories()

        # 4. Inicijaliziraj CheckpointManager
        checkpoint_manager = CheckpointManager(config, file_manager)

        # 5. Inicijaliziraj i pokreni Menu
        menu = Menu(config, checkpoint_manager)
        menu.run()

        return 0

    except FileNotFoundError as e:
        print(f"Greška: Konfiguracijska datoteka nije pronađena: {e}")
        return 1
    except Exception as e:
        logging.exception(f"Neočekivana greška: {e}")
        print(f"Greška: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
