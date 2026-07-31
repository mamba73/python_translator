"""
app/checkpoint.py — Multi-checkpoint sustav perzistencije
Ref: doc/README_TechDoc.md §12
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from app.file_manager import FileManager


class CheckpointManager:
    """Upravlja checkpointovima za više paralelnih knjiga."""

    CHECKPOINT_FILE = "translation_checkpoints.json"
    LAST_TEST_FILE = "last_test.json"

    def __init__(self, config: dict[str, Any], file_manager: FileManager) -> None:
        self._cfg = config
        self._fm = file_manager
        self._state_dir = Path(config["directories"]["state"])

    def atomic_write(self, path: str | Path, content: str) -> None:
        """Sigurno pisanje tekstualne datoteke: temp → fsync → rename.

        Zaštita od korupcije pri nestanku struje.
        """
        FileManager.atomic_write(path, content)

    def atomic_write_json(self, path: str | Path, data: dict | list) -> None:
        """Sigurno pisanje JSON datoteke koristeći atomic_write."""
        FileManager.atomic_write_json(path, data)

    def spremi_checkpoint(self, book_data: dict[str, Any]) -> None:
        """Sprema checkpoint za knjigu u multi-book strukturu.

        Args:
            book_data: Rječnik s podacima o knjizi i napretku.
                Minimalni format: {
                    "book_id": "unique_id",
                    "book_title": "Naslov",
                    "author": "Autor",
                    "current_chapter": 5,
                    "total_chapters": 20,
                    "current_segment": 10,
                    "total_segments": 150,
                    "output_path": "/path/to/output",
                    "timestamp": "2026-07-31T12:00:00"
                }
        """
        self._state_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = self._state_dir / self.CHECKPOINT_FILE

        # Učitaj postojeće checkpointe
        if checkpoint_path.exists():
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                checkpoints = json.load(f)
        else:
            checkpoints = {}

        # Ažuriraj ili dodaj
        book_id = book_data["book_id"]
        book_data["timestamp"] = datetime.now().isoformat(timespec="seconds")
        checkpoints[book_id] = book_data

        # Spremi atomski
        self.atomic_write_json(checkpoint_path, checkpoints)
        logging.debug(f"Checkpoint spremljen za knjigu: {book_id}")

    def ucitaj_checkpointe(self) -> list[dict[str, Any]]:
        """Vraća listu svih aktivnih checkpointova.

        Returns:
            Lista rječnika s podacima o svim knjigama s checkpointovima.
        """
        checkpoint_path = self._state_dir / self.CHECKPOINT_FILE

        if not checkpoint_path.exists():
            return []

        with open(checkpoint_path, 'r', encoding='utf-8') as f:
            checkpoints = json.load(f)

        return list(checkpoints.values())

    def obrisi_checkpoint(self, book_id: str) -> None:
        """Briše checkpoint za specificiranu knjigu.

        Args:
            book_id: Jedinstveni ID knjige.
        """
        checkpoint_path = self._state_dir / self.CHECKPOINT_FILE

        if not checkpoint_path.exists():
            return

        with open(checkpoint_path, 'r', encoding='utf-8') as f:
            checkpoints = json.load(f)

        if book_id in checkpoints:
            del checkpoints[book_id]
            self.atomic_write_json(checkpoint_path, checkpoints)
            logging.info(f"Checkpoint obrisan za knjigu: {book_id}")

    def spremi_last_test(self, params: dict[str, Any]) -> None:
        """Sprema parametre zadnjeg TEST prijevoda.

        Args:
            params: Rječnik s parametrima testa.
                Format: {
                    "book_path": "/path/to/book.txt",
                    "granularity": "paragraph",
                    "count": 1,
                    "include_header": true,
                    "timestamp": "2026-07-31T12:00:00"
                }
        """
        self._state_dir.mkdir(parents=True, exist_ok=True)
        last_test_path = self._state_dir / self.LAST_TEST_FILE

        params["timestamp"] = datetime.now().isoformat(timespec="seconds")
        self.atomic_write_json(last_test_path, params)
        logging.debug("Last test parametri spremljeni.")

    def ucitaj_last_test(self) -> dict[str, Any] | None:
        """Učitava parametre zadnjeg TEST prijevoda.

        Returns:
            Rječnik s parametrima ili None ako ne postoji.
        """
        last_test_path = self._state_dir / self.LAST_TEST_FILE

        if not last_test_path.exists():
            return None

        with open(last_test_path, 'r', encoding='utf-8') as f:
            return json.load(f)
