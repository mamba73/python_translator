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
        if suffix_if_exists and path.exists():
            path = self._suffix_dir(path)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ensure_file_path(self, file_path: str | Path,
                         suffix_if_exists: bool = False) -> Path:
        """Generira sigurnu putanju za datoteku. Kreira roditeljski direktorij.

        Ako datoteka postoji i suffix_if_exists=True, dodaje (001), (002)...
        Roditeljski direktorij se uvijek kreira.

        Args:
            file_path:        Putanja datoteke.
            suffix_if_exists: Ako True i datoteka postoji, dodaje suffix.

        Returns:
            Finalna putanja (nova ili s suffixom).
        """
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if suffix_if_exists and path.exists():
            path = self._suffix_file(path)
        return path

    def ensure_directories(self) -> None:
        """Kreira sve work/ direktorije iz konfiguracije pri startu aplikacije."""
        for key, dir_path in self._dirs.items():
            Path(dir_path).mkdir(parents=True, exist_ok=True)
            logging.debug(f"Direktorij osiguran: {dir_path}")

    # -----------------------------------------------------------------------
    # Book-specific direktoriji
    # -----------------------------------------------------------------------

    def book_output_dir(self, book_title: str, author: str) -> Path:
        """Vraća putanju work/translated/<naziv---autor>/.

        Ako direktorij postoji, dodaje suffix _001, _002...

        Args:
            book_title: Naslov knjige.
            author:     Autor knjige.

        Returns:
            Putanja do direktorija za prevedenu knjigu (ne kreira ga).
        """
        base = Path(self._dirs["translated"])
        name = self._book_dirname(book_title, author)
        return self._suffix_dir(base / name) if (base / name).exists() else base / name

    def audiobook_dir(self, book_title: str, author: str) -> Path:
        """Vraća putanju work/audiobooks/<naziv---autor>/.

        Ista logika kao book_output_dir, za audiobooks.
        """
        base = Path(self._dirs["audiobooks"])
        name = self._book_dirname(book_title, author)
        return self._suffix_dir(base / name) if (base / name).exists() else base / name

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
        if not path.exists():
            return path
        counter = 1
        while True:
            candidate = Path(f"{path}_{counter:03d}")
            if not candidate.exists():
                return candidate
            counter += 1

    @staticmethod
    def _suffix_file(path: Path) -> Path:
        """Dodaje (001), (002)... sufiks ako datoteka postoji."""
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        counter = 0
        while True:
            candidate = parent / f"{stem}({counter:03d}){suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    def _book_dirname(self, book_title: str, author: str) -> str:
        """Formatira naziv direktorija kao <naziv>---<autor>."""
        sanitize = self.sanitize_name
        return f"{sanitize(book_title)}---{sanitize(author)}"
