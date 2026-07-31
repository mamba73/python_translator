"""
app/text_cleaner.py — Čišćenje tehničkog šuma i kreiranje memorije
Ref: doc/README_TechDoc.md §8
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.file_manager import FileManager


class TextCleaner:
    """Klasa za čišćenje dokumenta i kreiranje memorije."""

    def __init__(self, config: dict[str, Any], file_manager: FileManager) -> None:
        self._cfg = config
        self._fm = file_manager

    def ocisti_dokument(self, input_path: Path, book_title: str) -> Path:
        """Čisti dokument i sprema ga kao [fixed] datoteku.

        Args:
            input_path: Putanja do izvorne datoteke (work/output/<Knjiga>/<naziv>.txt).
            book_title: Naslov knjige za imenovanje.

        Returns:
            Putanja do [fixed] datoteke.
        """
        with open(input_path, 'r', encoding='utf-8') as f:
            tekst = f.read()

        # Čišćenje: normalizacija whitespace-a
        tekst = self._normaliziraj_whitespace(tekst)
        tekst = self._spoji_prelomljene_rečenice(tekst)

        # Kreiranje [fixed] putanje
        output_dir = input_path.parent
        fixed_name = f"{input_path.stem} [fixed]{input_path.suffix}"
        fixed_path = output_dir / fixed_name

        # Spremanje
        self._fm.atomic_write(fixed_path, tekst)
        logging.info(f"Dokument očišćen i spremljen: {fixed_path}")

        return fixed_path

    def kreiraj_memoriju(self, book_dir: Path, book_title: str) -> Path:
        """Kreira memoriju JSON s CHARACTERS, GLOSSARY, GRAMMAR_FIXES placeholderima.

        Args:
            book_dir: Direktorij knjige (work/output/<Knjiga>/).
            book_title: Naslov knjige.

        Returns:
            Putanja do memorije JSON datoteke.
        """
        from app.config_loader import _sanitize_filename

        memorija_name = f"{_sanitize_filename(book_title)}_memorija.json"
        memorija_path = book_dir / memorija_name

        memorija_data = {
            "CHARACTERS": {},
            "GLOSSARY": {},
            "GRAMMAR_FIXES": {}
        }

        self._fm.atomic_write_json(memorija_path, memorija_data)
        logging.info(f"Memorija kreirana: {memorija_path}")

        return memorija_path

    def kreiraj_book_config(self, book_dir: Path, book_title: str, author: str,
                           original_file: str, profile_name: str = "sf_literature",
                           api_provider: str | None = None) -> dict[str, Any]:
        """Generira i sprema work/output/<Knjiga>/config.yaml iz profil predloška.

        Delegira na config_loader.create_book_config.

        Args:
            book_dir: Putanja do direktorija knjige.
            book_title: Naslov knjige.
            author: Autor knjige.
            original_file: Naziv izvorne datoteke.
            profile_name: Profil predložak (default: sf_literature).
            api_provider: Override API providera.

        Returns:
            Generirani book config rječnik.
        """
        from app.config_loader import create_book_config

        return create_book_config(
            book_dir=book_dir,
            book_title=book_title,
            author=author,
            original_file=original_file,
            profile_name=profile_name,
            api_provider=api_provider
        )

    # -----------------------------------------------------------------------
    # Interne pomoćne metode
    # -----------------------------------------------------------------------

    def _normaliziraj_whitespace(self, tekst: str) -> str:
        """Normalizira whitespace: višestruki razmaci → jedan, tabovi → razmaci."""
        tekst = re.sub(r'[ \t]+', ' ', tekst)  # Tabovi i višestruki razmaci
        tekst = re.sub(r'\n\s*\n\s*\n+', '\n\n', tekst)  # Višestruki prazni redovi
        return tekst.strip()

    def _spoji_prelomljene_rečenice(self, tekst: str) -> str:
        """Spaja rečenice prelomljene na kraju redova (nema točku-zarez)."""
        # Jednostavna heuristika: ako red ne završava s točkom, upitnikom, uskličnikom
        # ili navodnikom, spoji sa sljedećim redom
        redovi = tekst.split('\n')
        spojeni = []
        for i, red in enumerate(redovi):
            if red and not red[-1] in '.?!)"\'':
                if i + 1 < len(redovi):
                    spojeni.append(red + ' ')
                    continue
            spojeni.append(red)
        return '\n'.join(spojeni)
