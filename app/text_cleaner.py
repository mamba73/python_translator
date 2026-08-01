"""
app/text_cleaner.py — Čišćenje tehničkog šuma iz ulaznih tekstualnih datoteka.

Ovaj modul prima sirove .txt datoteke i uklanja:
  - HTML entitete (&nbsp;, \xa0, <br>, <br/>, itd.)
  - Sve HTML/XML tagove
  - Višestruke prazne redove (sažima na točno jedan prazan red između odlomaka)
  - Prekidane rečenice unutar odlomka (spaja u kontinuirani redak)
"""

import os
import re
from pathlib import Path
from typing import Optional


def ocisti_html_i_paragrafe(sirovi_tekst: str) -> str:
    """Čisti HTML entitete, tagove i normalizira višestruke prazne redove."""
    if not sirovi_tekst:
        return ""
    
    # 1. Čišćenje specifičnih HTML entiteta i skrivenih razmaka
    tekst = sirovi_tekst.replace('\xa0', ' ')
    tekst = tekst.replace(' ', ' ')
    tekst = re.sub(r'<br\s*/?>', '\n', tekst)
    
    # 2. Uklanjanje općenitih HTML tagova
    tekst = re.sub(r'<[^>]+>', '', tekst)
    
    # 3. Normalizacija prijeloma redaka na Unix standard
    tekst = tekst.replace('\r\n', '\n').replace('\r', '\n')
    
    # 4. Razbijanje na retke, micanje praznina s rubova i čišćenje uvodnog šuma
    retci = [linija.strip() for linija in tekst.split('\n')]
    
    # 5. Agresivno sažimanje i spajanje odlomaka
    očišćeni_odlomci = []
    trenutni_odlomak = []
    
    for linija in retci:
        if linija == "":
            if trenutni_odlomak:
                očišćeni_odlomci.append(" ".join(trenutni_odlomak))
                trenutni_odlomak = []
        else:
            trenutni_odlomak.append(linija)
            
    if trenutni_odlomak:
        očišćeni_odlomci.append(" ".join(trenutni_odlomak))
        
    # Spajanje odlomaka s točno jednim praznim redom razmaka između njih
    finalni_tekst = "\n\n".join([odlomak for odlomak in očišćeni_odlomci if odlomak.strip()])
    return finalni_tekst


def generiraj_inkrementalnu_putanju(izlazni_dir: str, originalni_naziv: str, ekstenzija: str = ".txt") -> str:
    """Generira jedinstvenu [fixed] putanju s inkrementalnim sufiksom (_001, _002...).

    Nikad ne prepisuje postojeću datoteku i nikad ne gomila višestruke [fixed]
    oznake (npr. "knjiga [fixed] [fixed].txt").

    Primjeri:
        Foundation.txt              → Foundation [fixed].txt
        (ako postoji)               → Foundation [fixed]_001.txt
        Foundation [fixed].txt      → Foundation [fixed]_001.txt  (strip + inkrement)
    """
    from app.file_manager import FileManager

    # Ukloni zaostale [fixed] oznake i numeričke sufikse da ne gomilamo
    baza_naziva = re.sub(r'\s*\[fixed\](?:_\d+)?', '', originalni_naziv, flags=re.IGNORECASE).strip()
    baza_naziva = os.path.splitext(baza_naziva)[0]
    # Ukloni i čisti _NNN sufiks s baze (npr. Foundation_001 → Foundation)
    baza_naziva = re.sub(r'_\d{3}$', '', baza_naziva)

    osnovni_fixed = os.path.join(izlazni_dir, f"{baza_naziva} [fixed]{ekstenzija}")
    return FileManager.unique_file_path(osnovni_fixed)


class TextCleaner:
    """Glavna klasa za čišćenje tekstualnih datoteka."""

    def __init__(self, file_manager=None, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.file_manager = file_manager

    def clean_file(self, input_path: str) -> str:
        """
        Učita datoteku, očisti je i sprema kao novu datoteku s [fixed] oznakom (ili inkrementalnim sufiksom).
        Vraća putanju do očišćene datoteke.
        """
        with open(input_path, "r", encoding="utf-8") as f:
            tekst = f.read()

        ocisceno = ocisti_html_i_paragrafe(tekst)

        directory = os.path.dirname(input_path)
        filename = os.path.basename(input_path)
        ext = os.path.splitext(filename)[1] or ".txt"

        output_path = generiraj_inkrementalnu_putanju(directory, filename, ext)
        
        if self.file_manager:
            self.file_manager.ensure_dir(Path(output_path).parent, suffix_if_exists=False)
        else:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(ocisceno)

        return output_path

    def clean_text(self, tekst: str) -> str:
        """Čisti tekst iz stringa i vraća očišćenu verziju."""
        return ocisti_html_i_paragrafe(tekst)

    def ocisti_dokument(self, tekst: str, book_title: str = "") -> str:
        """Alias za clean_text — čisti tekst i vraća očišćenu verziju."""
        return ocisti_html_i_paragrafe(tekst)

    def kreiraj_memoriju(self, tekst: str = "") -> dict:
        """Kreira praznu memoriju (CHARACTERS, GLOSSARY, GRAMMAR_FIXES)."""
        return {
            "CHARACTERS": {},
            "GLOSSARY": {},
            "GRAMMAR_FIXES": {}
        }

    def kreiraj_book_config(self, book_title: str, author: str = "Autor") -> dict:
        """Kreira per-book konfiguraciju iz predloška i globalnih postavki."""
        trans_cfg = self.settings.get("translation", {})
        api_cfg = self.settings.get("api", {})

        from datetime import datetime

        return {
            "book_title": book_title,
            "author": author,
            "api_provider": api_cfg.get("provider", "gemini"),
            "model": "",
            "api_key_override": "",
            "system_prompt": trans_cfg.get(
                "default_system_prompt",
                "Ti si stručni prevoditelj s engleskog na hrvatski. Prevedi sljedeći tekst zadržavajući stil i ton originala."
            ),
            "parameters": {
                "temperature": trans_cfg.get("temperature", 0.25),
                "top_p": trans_cfg.get("top_p", 0.80),
                "top_k": trans_cfg.get("top_k", 15),
                "min_p": trans_cfg.get("min_p", 0.05),
                "max_tokens": trans_cfg.get("max_tokens", 4000),
                "repeat_penalty": trans_cfg.get("repeat_penalty", 1.20)
            },
            "chunking": {
                "max_tokens_per_chunk": 1500,
                "overlap_tokens": 100
            },
            "enable_reasoning": not trans_cfg.get("disable_reasoning", True),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }