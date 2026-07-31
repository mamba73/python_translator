"""
app/menu.py — CLI sučelje s kursorskom navigacijom
Ref: doc/README_TechDoc.md §6
"""

from __future__ import annotations

import sys
import logging
from typing import Any, Callable, Optional
from pathlib import Path

# Platform-specific imports
if sys.platform == "win32":
    try:
        import msvcrt
        _MSVCRT_AVAILABLE = True
    except ImportError:
        _MSVCRT_AVAILABLE = False
else:
    try:
        import curses
        _CURSES_AVAILABLE = True
    except ImportError:
        _CURSES_AVAILABLE = False

from app.utils import ocisti_ekran
from app.checkpoint import CheckpointManager


class Menu:
    """CLI sučelje s kursorskom navigacijom."""

    def __init__(self, config: dict[str, Any], checkpoint_manager: CheckpointManager) -> None:
        self._cfg = config
        self._cp = checkpoint_manager
        self._opcije = {
            "granularnost": "paragraph",  # paragraph | sentence
            "kolicina": 1,
            "header": True  # DA/NE
        }

    # -----------------------------------------------------------------------
    # Glavni entry point
    # -----------------------------------------------------------------------

    def run(self) -> None:
        """Pokreće glavni izbornik."""
        while True:
            odabir = self.show_main()
            if odabir == "exit":
                if self._potvrda_izlaza():
                    break
            elif odabir == "test":
                self._brzi_test()
            elif odabir == "1":
                self.show_phase1()
            elif odabir == "2":
                self.show_phase2()
            elif odabir == "3":
                self.show_phase3()
            elif odabir == "4":
                self.show_phase4()

    # -----------------------------------------------------------------------
    # Glavni izbornik
    # -----------------------------------------------------------------------

    def show_main(self) -> str:
        """Glavni izbornik s checkpoint blokom i BRZI TEST linijom.

        Returns:
            Odabir korisnika ("1", "2", "3", "4", "test", "exit").
        """
        ocisti_ekran()

        # Checkpoint blok
        checkpointi = self._cp.ucitaj_checkpointe()
        if checkpointi:
            print("=" * 70)
            print("🔄 AKTIVNI CHECKPOINTOVI:")
            for cp in checkpointi:
                title = cp.get("book_title", "Nepoznato")
                progress = f"{cp.get('current_segment', 0)}/{cp.get('total_segments', 0)}"
                print(f"  • {title} — {progress} segmenata")
            print("  [R] — Nastavi od zadnje točke")
            print("=" * 70)
            print()

        # Header
        version = self._cfg.get("project", {}).get("version", "0.4.0")
        print("=" * 70)
        print(f"         Dynamic Book Translator v{version}")
        print("=" * 70)
        print()

        # BRZI TEST linija
        last_test = self._cp.ucitaj_last_test()
        if last_test:
            print(f"  [Y] — BRZI TEST ({last_test.get('granularnost', 'paragraph')}, "
                  f"{last_test.get('count', 1)} segmenata)")
            print()

        # Opcije
        opcije = [
            "1. Konverzija dokumenata (PDF/DOCX/EPUB/MOBI → TXT)",
            "2. Čišćenje tehničkog šuma + kreiranje memorije",
            "3. Prevođenje (TEST / Produkcijski)",
            "4. TTS sinteza (TXT → MP3)",
            "X. Izlaz"
        ]

        odabir = self._odabir_iz_liste(opcije, allow_y=last_test is not None, allow_r=len(checkpointi) > 0)

        if odabir == "r" and len(checkpointi) > 0:
            # Odabir checkpointa za nastavak
            return self._odabir_checkpointa(checkpointi)
        elif odabir == "y" and last_test:
            return "test"

        return odabir

    # -----------------------------------------------------------------------
    # Faza 1 - Konverzija
    # -----------------------------------------------------------------------

    def show_phase1(self) -> None:
        """Konverzija dokumenata s batch odabirom."""
        ocisti_ekran()
        print("=" * 70)
        print("FAZA 1 — KONVERZIJA DOKUMENATA")
        print("=" * 70)
        print()

        input_dir = Path(self._cfg["directories"]["input"])
        if not input_dir.exists():
            print("Direktorij work/input/ ne postoji. Dodajte datoteke za konverziju.")
            input("Pritisnite Enter za povratak...")
            return

        # Pronađi datoteke
        datoteke = list(input_dir.glob("*.*"))
        datoteke = [d for d in datoteke if d.is_file() and not d.name.startswith(".")]

        if not datoteke:
            print("Nema datoteka u work/input/")
            input("Pritisnite Enter za povratak...")
            return

        # Batch odabir
        odabrane = self._batch_odabir([d.name for d in datoteke], "Odaberite datoteke za konverziju")

        if not odabrane:
            print("Nije odabrana nijedna datoteka.")
            input("Pritisnite Enter za povratak...")
            return

        print(f"\nOdabrano: {len(odabrane)} datoteka")
        print("Konverzija još nije implementirana u ovoj fazi refactoringa.")
        input("Pritisnite Enter za povratak...")

    # -----------------------------------------------------------------------
    # Faza 2 - Čišćenje
    # -----------------------------------------------------------------------

    def show_phase2(self) -> None:
        """Čišćenje tehničkog šuma s batch odabirom."""
        ocisti_ekran()
        print("=" * 70)
        print("FAZA 2 — ČIŠĆENJE TEHNIČKOG ŠUMA + KREIRANJE MEMORIJE")
        print("=" * 70)
        print()

        output_dir = Path(self._cfg["directories"]["output"])
        if not output_dir.exists():
            print("Direktorij work/output/ ne postoji.")
            input("Pritisnite Enter za povratak...")
            return

        # Pronađi direktorije knjiga
        knjige = [d for d in output_dir.iterdir() if d.is_dir()]

        if not knjige:
            print("Nema knjiga u work/output/")
            input("Pritisnite Enter za povratak...")
            return

        # Batch odabir
        odabrane = self._batch_odabir([d.name for d in knjige], "Odaberite knjige za čišćenje")

        if not odabrane:
            print("Nije odabrana nijedna knjiga.")
            input("Pritisnite Enter za povratak...")
            return

        print(f"\nOdabrano: {len(odabrane)} knjiga")
        print("Čišćenje još nije implementirano u ovoj fazi refactoringa.")
        input("Pritisnite Enter za povratak...")

    # -----------------------------------------------------------------------
    # Faza 3 - Prevođenje
    # -----------------------------------------------------------------------

    def show_phase3(self) -> None:
        """Prevođenje: TEST / Produkcijski / Opcije."""
        while True:
            ocisti_ekran()
            print("=" * 70)
            print("FAZA 3 — PREVOĐENJE")
            print("=" * 70)
            print()

            # Notifikacijska linija
            gran = self._opcije["granularnost"]
            kol = self._opcije["kolicina"]
            hdr = "DA" if self._opcije["header"] else "NE"
            print(f"  ── Granularnost: {gran.capitalize()} | Količina: {kol} | Header: {hdr} ──")
            print()

            opcije = [
                "1. TEST prijevod",
                "2. Produkcijski prijevod",
                "0. Opcije",
                "X. Povratak"
            ]

            odabir = self._odabir_iz_liste(opcije)

            if odabir == "x":
                break
            elif odabir == "0":
                self.show_opcije()
            elif odabir == "1":
                self._test_prijevod()
            elif odabir == "2":
                self._produkcijski_prijevod()

    def show_opcije(self) -> None:
        """Opcije: Header, Granularnost, Količina."""
        while True:
            ocisti_ekran()
            print("=" * 70)
            print("OPCIJE PREVOĐENJA")
            print("=" * 70)
            print()

            opcije = [
                f"1. Header u testu: {'DA' if self._opcije['header'] else 'NE'}",
                f"2. Granularnost: {self._opcije['granularnost'].capitalize()}",
                f"3. Količina (TEST): {self._opcije['kolicina']}",
                "X. Povratak"
            ]

            odabir = self._odabir_iz_liste(opcije)

            if odabir == "x":
                break
            elif odabir == "1":
                self._opcije["header"] = not self._opcije["header"]
            elif odabir == "2":
                granularnosti = ["paragraph", "sentence"]
                trenutni = granularnosti.index(self._opcije["granularnost"])
                sljedeci = (trenutni + 1) % len(granularnosti)
                self._opcije["granularnost"] = granularnosti[sljedeci]
            elif odabir == "3":
                kolicine = [1, 2, 3, 5, 10]
                trenutni = kolicine.index(self._opcije["kolicina"]) if self._opcije["kolicina"] in kolicine else 0
                sljedeci = (trenutni + 1) % len(kolicine)
                self._opcije["kolicina"] = kolicine[sljedeci]

    # -----------------------------------------------------------------------
    # Faza 4 - TTS
    # -----------------------------------------------------------------------

    def show_phase4(self) -> None:
        """TTS sinteza: zasebni segmenti / jedna datoteka."""
        ocisti_ekran()
        print("=" * 70)
        print("FAZA 4 — TTS SINTEZA")
        print("=" * 70)
        print()

        opcije = [
            "1. Zasebne MP3 datoteke po segmentima",
            "2. Jedna MP3 datoteka (cijela knjiga)",
            "X. Povratak"
        ]

        odabir = self._odabir_iz_liste(opcije)

        if odabir == "x":
            return

        print(f"\nOdabran način: {'Zasebne datoteke' if odabir == '1' else 'Jedna datoteka'}")
        print("TTS sinteza još nije implementirana u ovoj fazi refactoringa.")
        input("Pritisnite Enter za povratak...")

    # -----------------------------------------------------------------------
    # Pomoćne metode
    # -----------------------------------------------------------------------

    def _odabir_iz_liste(self, opcije: list[str], allow_y: bool = False,
                        allow_r: bool = False) -> str:
        """Jednostavan odabir iz liste (brojevi + Y/R/X).

        Args:
            opcije: Lista opcija za prikaz.
            allow_y: Dozvoli Y kao odgovor.
            allow_r: Dozvoli R kao odgovor.

        Returns:
            Odabir korisnika.
        """
        for opc in opcije:
            print(f"  {opc}")
        print()

        while True:
            odgovor = input("Odabir: ").strip().lower()
            if odgovor == "x":
                return "x"
            if odgovor == "y" and allow_y:
                return "y"
            if odgovor == "r" and allow_r:
                return "r"
            if odgovor.isdigit():
                idx = int(odgovor) - 1
                if 0 <= idx < len(opcije):
                    return str(idx + 1)

    def _batch_odabir(self, stavke: list[str], naslov: str) -> list[int]:
        """Batch odabir: 1, 1,3,5, 1-5, *.

        Args:
            stavke: Lista stavki za odabir.
            naslov: Naslov za prikaz.

        Returns:
            Lista indeksa odabranih stavki.
        """
        print(f"{naslov}:")
        print()

        for i, stavka in enumerate(stavke, 1):
            print(f"  {i}. {stavka}")
        print()

        print("Unesite brojeve (npr. 1,3,5 ili 1-5 ili * za sve):")
        unos = input("> ").strip()

        if unos == "*":
            return list(range(len(stavke)))

        odabrani = set()
        for dio in unos.split(","):
            dio = dio.strip()
            if "-" in dio:
                start, end = map(int, dio.split("-"))
                for i in range(start - 1, end):
                    if 0 <= i < len(stavke):
                        odabrani.add(i)
            elif dio.isdigit():
                idx = int(dio) - 1
                if 0 <= idx < len(stavke):
                    odabrani.add(idx)

        return sorted(odabrani)

    def _potvrda_izlaza(self) -> bool:
        """Potvrda izlaza s Y/N.

        Returns:
            True ako korisnik potvrđuje izlaz.
        """
        print()
        odgovor = input("Sigurno želite izaći? (Y/N): ").strip().upper()
        return odgovor == "Y"

    def _brzi_test(self) -> None:
        """Pokreće BRZI TEST iz last_test.json."""
        print("\nPokretanje BRZOG TESTA...")
        last_test = self._cp.ucitaj_last_test()
        if last_test:
            print(f"Granularnost: {last_test.get('granularnost')}")
            print(f"Količina: {last_test.get('count')}")
            print("TEST prijevod još nije implementiran u ovoj fazi refactoringa.")
        input("Pritisnite Enter za povratak...")

    def _odabir_checkpointa(self, checkpointi: list[dict]) -> str:
        """Odabir checkpointa za nastavak.

        Args:
            checkpointi: Lista checkpointova.

        Returns:
            "resume" ili odgovor za nastavak.
        """
        print("\nOdaberite checkpoint za nastavak:")
        for i, cp in enumerate(checkpointi, 1):
            title = cp.get("book_title", "Nepoznato")
            progress = f"{cp.get('current_segment', 0)}/{cp.get('total_segments', 0)}"
            print(f"  {i}. {title} — {progress}")

        odgovor = input("\nOdabir (ili X za povratak): ").strip().lower()
        if odgovor == "x":
            return "x"

        # Vrati "resume" - konkretna logika nastavka će se implementirati kasnije
        return "resume"

    def _test_prijevod(self) -> None:
        """TEST prijevod."""
        print("\nTEST prijevod još nije implementiran u ovoj fazi refactoringa.")
        input("Pritisnite Enter za povratak...")

    def _produkcijski_prijevod(self) -> None:
        """Produkcijski prijevod."""
        print("\nProdukcijski prijevod još nije implementiran u ovoj fazi refactoringa.")
        input("Pritisnite Enter za povratak...")
