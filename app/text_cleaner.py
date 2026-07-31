"""
app/text_cleaner.py — Čišćenje tehničkog šuma iz ulaznih tekstualnih datoteka.

Ovaj modul prima sirove .txt datoteke (često izvučene iz PDF knjiga) i uklanja:
  - HTML entitete (&#13;, &#x2002;, itd.)
  - Višestruke prazne redove
  - Početni izdavački šum (Copyright, Contents, Cover, Publisher info)
  - Formatira tekst u čiste paragrafe spremne za TTS sintezu.

Arhitektura:
  - Učitavanje iz work/output/<Naziv_Knjige>/<originalna_datoteka>.txt
  - Spremanje u work/output/<Naziv_knjige>/<originalni_naziv> [fixed].txt
"""

import os
import re
import json
from typing import Optional

from app.file_manager import FileManager


class TextCleaner:
    """Glavna klasa za čišćenje tekstualnih datoteka."""

    def __init__(self, file_manager: FileManager, settings: dict):
        self.settings = settings
        self.file_manager = file_manager

    # -----------------------------------------------------------------------
    # PUBLIC API
    # -----------------------------------------------------------------------

    def clean_file(self, input_path: str) -> str:
        """
        Učita datoteku, očisti je i sprema kao novu datoteku s [fixed] oznakom.
        Vraća putanju do očišćene datoteke.

        Koristi FileManager za upravljanje direktorijima.
        """
        with open(input_path, "r", encoding="utf-8") as f:
            tekst = f.read()

        tekst = self._clean_text(tekst)

        output_path = self._generate_output_path(input_path)
        # Koristi FileManager za osiguranje roditeljskog direktorija
        self.file_manager.ensure_dir(Path(output_path).parent, suffix_if_exists=False)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(tekst)

        return output_path

    def clean_text(self, tekst: str) -> str:
        """Čisti tekst iz stringa i vraća očišćenu verziju."""

        return self._clean_text(tekst)

    def ocisti_dokument(self, tekst: str, book_title: str = "") -> str:
        """Alias za clean_text — čisti tekst i vraća očišćenu verziju.

        Args:
            tekst: Sirovi tekst za čišćenje.
            book_title: Naslov knjige (nije obavezan, za buduću upotrebu).

        Returns:
            Očišćeni tekst.
        """
        return self._clean_text(tekst)

    def kreiraj_memoriju(self, tekst: str = "") -> dict:
        """Kreira praznu memoriju (CHARACTERS, GLOSSARY, GRAMMAR_FIXES).

        Args:
            tekst: Tekst knjige (za buduću automatsku detekciju likova).

        Returns:
            Rječnik s praznim sekcijama za memoriju.
        """
        return {
            "CHARACTERS": {},
            "GLOSSARY": {},
            "GRAMMAR_FIXES": {}
        }

    def kreiraj_book_config(self, book_title: str, author: str = "Autor") -> dict:
        """Kreira per-book konfiguraciju iz predloška.

        Args:
            book_title: Naslov knjige.
            author: Autor knjige.

        Returns:
            Rječnik s osnovnim postavkama za knjigu.
        """
        from datetime import datetime

        return {
            "book_title": book_title,
            "author": author,
            "api_provider": "lm_studio",
            "model": "",
            "api_key_override": "",
            "system_prompt": (
                "Ti si stručni prevoditelj s engleskog na hrvatski. "
                "Prevedi sljedeći tekst zadržavajući stil i ton originala."
            ),
            "parameters": {
                "temperature": 0.25,
                "top_p": 0.80,
                "top_k": 15,
                "min_p": 0.05,
                "max_tokens": 4096,
                "repeat_penalty": 1.1
            },
            "chunking": {
                "max_tokens_per_chunk": 1500,
                "overlap_tokens": 100
            },
            "enable_reasoning": False,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }

    # -----------------------------------------------------------------------
    # PATH GENERATION
    # -----------------------------------------------------------------------

    def _generate_output_path(self, input_path: str) -> str:
        """
        Generira izlaznu putanju s [fixed] oznakom.
        Primjer: work/output/Foundation - Isaac Asimov/Foundation - Isaac Asimov.txt
                -> work/output/Foundation - Isaac Asimov/Foundation - Isaac Asimov [fixed].txt
        """
        directory = os.path.dirname(input_path)
        filename = os.path.basename(input_path)
        name, ext = os.path.splitext(filename)
        fixed_filename = f"{name} [fixed]{ext}"
        return os.path.join(directory, fixed_filename)

    # -----------------------------------------------------------------------
    # INTERNAL CLEANING PIPELINE
    # -----------------------------------------------------------------------

    def _clean_text(self, tekst: str) -> str:
        """Glavna cijev čišćenja — poziva sve korake redom."""
        tekst = self._cleanup_html_entities(tekst)
        tekst = self._cleanup_carriage_returns(tekst)
        tekst = self._remove_noise_lines(tekst)
        tekst = self._strip_publisher_frontmatter(tekst)
        tekst = self._normalize_blank_lines(tekst)
        return tekst

    # -----------------------------------------------------------------------
    # KORAK 1 — HTML ENTITETI
    # -----------------------------------------------------------------------

    def _cleanup_html_entities(self, tekst: str) -> str:
        """Uklanja HTML escape sekvence koje ne mijenjaju vizualni sadržaj."""
        tekst = re.sub(r'&#13;', '', tekst)
        tekst = re.sub(r'&#[xX][0-9a-fA-F]+;', ' ', tekst)
        tekst = re.sub(r'&#\d+;', ' ', tekst)
        tekst = tekst.replace('&', '&')
        tekst = tekst.replace('<', '<')
        tekst = tekst.replace('>', '>')
        return tekst

    # -----------------------------------------------------------------------
    # KORAK 2 — CARRIAGE RETURNS
    # -----------------------------------------------------------------------

    def _cleanup_carriage_returns(self, tekst: str) -> str:
        """Svaki \r ili \r\n normalizira u \n."""
        tekst = tekst.replace('\r\n', '\n')
        tekst = tekst.replace('\r', '\n')
        return tekst

    # -----------------------------------------------------------------------
    # KORAK 3 — ŠUM LINIJE (page numbers, widows/orphans)
    # -----------------------------------------------------------------------

    def _remove_noise_lines(self, tekst: str) -> str:
        """Uklanja tipične šum linije poput brojeva stranica."""
        lines = tekst.split('\n')
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if re.match(r'^\d{1,5}\s*$', stripped):
                continue
            cleaned.append(line)
        return '\n'.join(cleaned)

    # -----------------------------------------------------------------------
    # KORAK 4 — PUBLISHER FRONTMATTER REMOVAL
    # -----------------------------------------------------------------------

    def _strip_publisher_frontmatter(self, tekst: str) -> str:
        """
        Uklanja početni izdavački šum (Copyright, Contents, Cover, itd.)
        sve do prave početne točke knjige.
        """
        content_start_markers = [
            r'(?i)begin\s+(reading|of\s+book)',
            r'(?i)chapter\s+\d+',
            r'(?i)chapter\s+[a-z]',
            r'(?i)part\s+i+',
            r'(?i)prologue',
            r'(?i)preface',
            r'(?i)introduction',
        ]

        for marker in content_start_markers:
            match = re.search(marker, tekst)
            if match:
                tekst = tekst[match.start():]
                break

        return tekst

    # -----------------------------------------------------------------------
    # KORAK 5 — NORMALIZACIJA BLANK LINIJA
    # -----------------------------------------------------------------------

    def _normalize_blank_lines(self, tekst: str) -> str:
        """Normalizira višestruke prazne redove u jedan."""
        tekst = re.sub(r'\n{3,}', '\n\n', tekst)
        tekst = tekst.strip()
        return tekst + '\n'