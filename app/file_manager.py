"""
app/file_manager.py — Unificirana klasa za upravljanje direktorijima i datotekama
Ref: doc/README_TechDoc.md §22
"""

from __future__ import annotations

import os
import re
import logging
from pathlib import Path
from typing import Any

_CHAR_MAP = str.maketrans("čćšđžŽŠĐČĆ", "ccsdzZSDCC")


class FileManager:
    """Centralna točka za kreiranje direktorija, datoteka i suffix-increment logiku.

    Sve ostale klase u app/ dobivaju instancu FileManager i pozivaju njene
    metode — nema direktnih os.makedirs ili open() poziva za upravljanje
    putanjama izvan ove klase.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._cfg = config
        self._dirs = config.get("directories", {})

    # -----------------------------------------------------------------------
    # Osiguranje direktorija
    # -----------------------------------------------------------------------

    def ensure_dir(self, dir_path: str | Path,
                   suffix_if_exists: bool = False) -> Path:
        """Kreira direktorij. Ako postoji i suffix_if_exists=True, dodaje _001, _002...

        Args:
            dir_path:         Putanja direktorija koji treba kreirati.
            suffix_if_exists: Ako True i direktorij postoji, kreira novi s suffixom.

        Returns:
            Finalna putanja (nova ili s suffixom).
        """
        path = Path(dir_path)
        if suffix_if_exists:
            path = Path(self.unique_dir_path(path))
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ensure_file_path(self, file_path: str | Path,
                         suffix_if_exists: bool = False) -> Path:
        """Generira sigurnu putanju za datoteku. Kreira roditeljski direktorij.

        Ako datoteka postoji i suffix_if_exists=True, dodaje _001, _002...
        neposredno ispred ekstenzije (nikad ne prepisuje postojeću datoteku).

        Args:
            file_path:        Putanja datoteke.
            suffix_if_exists: Ako True i datoteka postoji, dodaje suffix.

        Returns:
            Finalna putanja (nova ili s suffixom).
        """
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if suffix_if_exists:
            path = Path(self.unique_file_path(path))
        return path

    def ensure_directories(self) -> None:
        """Kreira sve work/ direktorije iz konfiguracije pri startu aplikacije."""
        for key, dir_path in self._dirs.items():
            Path(dir_path).mkdir(parents=True, exist_ok=True)
            logging.debug(f"Direktorij osiguran: {dir_path}")

    # -----------------------------------------------------------------------
    # Jedinstvene putanje (zaštita od prepisivanja)
    # -----------------------------------------------------------------------

    @staticmethod
    def unique_file_path(file_path: str | Path) -> str:
        """Vraća putanju koja ne prepisuje postojeću datoteku.

        Ako ciljana datoteka ne postoji, vraća original.
        Ako postoji, dodaje _001, _002... neposredno ispred ekstenzije.

        Primjer:
            book.txt       (slobodno) → book.txt
            book.txt       (postoji)  → book_001.txt
            book_001.txt   (postoji)  → book_002.txt  (bazirano na stemu 'book')
        """
        path_str = os.path.normpath(str(file_path))
        if not os.path.exists(path_str):
            return path_str

        directory = os.path.dirname(path_str)
        filename = os.path.basename(path_str)
        stem, ext = os.path.splitext(filename)

        # Ukloni postojeći inkrementalni sufiks (_001, _002...) da ne gomilamo
        # npr. book_001.txt → baza "book", pa sljedeći slobodni broj
        baza = re.sub(r'_\d{3}$', '', stem)

        brojac = 1
        while True:
            kandidat = os.path.join(directory, f"{baza}_{brojac:03d}{ext}")
            if not os.path.exists(kandidat):
                return kandidat
            brojac += 1

    @staticmethod
    def unique_dir_path(dir_path: str | Path) -> str:
        """Vraća putanju direktorija koja ne dira postojeći direktorij.

        Ako ciljani dir ne postoji, vraća original.
        Ako postoji, dodaje _001, _002... na kraj naziva mape.
        """
        path_str = os.path.normpath(str(dir_path))
        if not os.path.exists(path_str):
            return path_str

        # Ukloni postojeći inkrementalni sufiks da brojimo od baze
        baza = re.sub(r'_\d{3}$', '', path_str)

        brojac = 1
        while True:
            kandidat = f"{baza}_{brojac:03d}"
            if not os.path.exists(kandidat):
                return kandidat
            brojac += 1

    # -----------------------------------------------------------------------
    # Book-specific direktoriji
    # -----------------------------------------------------------------------

    def book_output_dir(self, book_title: str, author: str) -> Path:
        """Vraća baznu putanju work/translated/<naziv---autor>/.

        Ne kreira direktorij i ne dodaje sufiks — pozivatelj treba
        ensure_dir(..., suffix_if_exists=True) za zaštitu od prepisivanja.
        """
        base = Path(self._dirs["translated"])
        return base / self._book_dirname(book_title, author)

    def audiobook_dir(self, book_title: str, author: str) -> Path:
        """Vraća baznu putanju work/audiobooks/<naziv---autor>/.

        Ne kreira direktorij i ne dodaje sufiks — pozivatelj treba
        ensure_dir(..., suffix_if_exists=True) za zaštitu od prepisivanja.
        """
        base = Path(self._dirs["audiobooks"])
        return base / self._book_dirname(book_title, author)

    def work_output_book_dir(self, book_title: str) -> Path:
        """Vraća putanju work/output/<naziv>/ za [fixed] i config.yaml.

        Ne dodaje suffix — direktorij se kreira samo jednom.
        """
        base = Path(self._dirs["output"])
        name = self.sanitize_name(book_title, lowercase=False)
        path = base / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    # -----------------------------------------------------------------------
    # Sanitizacija
    # -----------------------------------------------------------------------

    @staticmethod
    def sanitize_name(name: str, separator: str = "-", lowercase: bool = True) -> str:
        """Uklanja dijakritike, pretvara razmake u separator.

        Args:
            name:       Originalni naziv.
            separator:  Zamjena za razmake (default: '-').
            lowercase:  Ako True, pretvara u mala slova (default: True).
                        Postavi na False za work/output/ direktorije gdje se
                        čuva originalni case (npr. "Dune" ne "dune").

        Returns:
            Sanitizirani naziv spreman za datotečni sustav.
        """
        name = name.translate(_CHAR_MAP)
        name = re.sub(r'[^\w\s-]', '', name).strip()
        if lowercase:
            name = name.lower()
        name = re.sub(r'\s+', separator, name)
        return name

    # -----------------------------------------------------------------------
    # Atomski zapis
    # -----------------------------------------------------------------------

    @staticmethod
    def atomic_write(path: str | Path, content: str) -> None:
        """Sigurno pisanje tekstualne datoteke: temp → fsync → rename.

        Zaštita od korupcije pri nestanku struje.
        NAPOMENA: ovo zamjenjuje datoteku na danoj putanji. Za zaštitu od
        prepisivanja pozovi unique_file_path() / ensure_file_path() prije.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(str(path) + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except Exception:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise

    @staticmethod
    def atomic_write_json(path: str | Path, data: dict | list) -> None:
        """Sigurno pisanje JSON datoteke koristeći atomic_write."""
        import json
        content = json.dumps(data, ensure_ascii=False, indent=2)
        FileManager.atomic_write(path, content)

    # -----------------------------------------------------------------------
    # Interne pomoćne metode
    # -----------------------------------------------------------------------

    @staticmethod
    def _suffix_dir(path: Path) -> Path:
        """Dodaje _001, _002... sufiks ako direktorij postoji."""
        return Path(FileManager.unique_dir_path(path))

    @staticmethod
    def _suffix_file(path: Path) -> Path:
        """Dodaje _001, _002... sufiks ako datoteka postoji."""
        return Path(FileManager.unique_file_path(path))

    def _book_dirname(self, book_title: str, author: str) -> str:
        """Formatira naziv direktorija kao <naziv>---<autor>."""
        sanitize = self.sanitize_name
        return f"{sanitize(book_title)}---{sanitize(author)}"
