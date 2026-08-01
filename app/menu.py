"""
app/menu.py — CLI sučelje s kursorskom navigacijom
Ref: doc/README_TechDoc.md §6
"""

from __future__ import annotations

import sys
import logging
import os
import json
import yaml
from typing import Any, Callable, Optional
from pathlib import Path
from datetime import datetime

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
from app.document_processor import DocumentProcessor
from app.text_cleaner import TextCleaner
from app.translator import Translator
from app.tts_engine import TTSEngine
from app.file_manager import FileManager


# ===========================================================================
# Box-drawing utilities
# ===========================================================================

def _okvir(sirina: int = 64) -> tuple[str, str, str, str, str, str]:
    """Vraća znakove za okvir (top, bottom, left, right, top-left, top-right)."""
    return ("═", "═", "║", "║", "╔", "╗")


def nacrtaj_okvir(naslov: str, sirina: int = 64, kontekst: str = "") -> None:
    """Crta okviran naslov s kontekstualnom putanjom.

    Args:
        naslov: Naslov sekcije.
        sirina: Širina okvira u znakovima.
        kontekst: Putanja konteksta (npr. "GLAVNI IZBORNIK > KONVERZIJA").
    """
    print("╔" + "═" * sirina + "╗")
    # Naslov
    naslov_str = f"  {naslov}"
    print("║" + naslov_str.ljust(sirina) + "║")
    # Kontekst
    if kontekst:
        ctx_str = f"  {kontekst}"
        print("║" + ctx_str.ljust(sirina) + "║")
    print("╚" + "═" * sirina + "╝")


def nacrtaj_okvir_opcije(naslov: str, sirina: int = 52, kontekst: str = "") -> None:
    """Crta okviran naslov za podizbornike s kontekstualnom putanjom."""
    print("╔" + "═" * sirina + "╗")
    naslov_str = f"  {naslov}"
    print("║" + naslov_str.ljust(sirina) + "║")
    if kontekst:
        ctx_str = f"  {kontekst}"
        print("║" + ctx_str.ljust(sirina) + "║")
    print("╚" + "═" * sirina + "╝")


def prikazi_okvir(stavke: list[str], naslov: str = "", sirina: int = 64,
                  kontekst: str = "", allow_y: bool = False,
                  allow_r: bool = False, trenutni: int = 0) -> None:
    """Crta okviran izbornik s kursorskom navigacijom.

    Args:
        stavke: Lista opcija za prikaz.
        naslov: Naslov izbornika.
        sirina: Širina okvira.
        kontekst: Putanja konteksta.
        allow_y: Dozvoli Y kao odgovor.
        allow_r: Dozvoli R kao odgovor.
        trenutni: Indeks trenutno označene stavke (0-based).
    """
    print("╔" + "═" * sirina + "╗")
    if naslov:
        naslov_str = f"  {naslov}"
        print("║" + naslov_str.ljust(sirina) + "║")
    if kontekst:
        ctx_str = f"  {kontekst}"
        print("║" + ctx_str.ljust(sirina) + "║")
    print("╠" + "═" * sirina + "╣")
    for i, stavka in enumerate(stavke, 1):
        if i - 1 == trenutni:
            stavka_str = f"  > [{i}] {stavka} <"
        else:
            stavka_str = f"  [{i}] {stavka}"
        print("║" + stavka_str.ljust(sirina) + "║")
    print("╠" + "═" * sirina + "╣")
    if allow_y:
        y_str = "  [Y] — BRZI TEST"
        print("║" + y_str.ljust(sirina) + "║")
    if allow_r:
        r_str = "  [R] — Nastavi od checkpointa"
        print("║" + r_str.ljust(sirina) + "║")
    x_str = "  [X] — Izlaz / Povratak"
    print("║" + x_str.ljust(sirina) + "║")
    print("╚" + "═" * sirina + "╝")


# ===========================================================================
# CursorMenu — kursorska navigacija
# ===========================================================================

class CursorMenu:
    """Kursorska navigacija za izbornike."""

    @staticmethod
    def odabir_iz_liste(opcije: list[str], naslov: str = "", allow_y: bool = False,
                        allow_r: bool = False, kontekst: str = "") -> str:
        """Kursorski odabir iz liste (↑↓ + Enter/Space).

        Args:
            opcije: Lista opcija za prikaz.
            naslov: Naslov za prikaz.
            allow_y: Dozvoli Y kao odgovor.
            allow_r: Dozvoli R kao odgovor.
            kontekst: Putanja konteksta (npr. "GLAVNI IZBORNIK > KONVERZIJA").

        Returns:
            Odabir korisnika.
        """
        if sys.platform == "win32" and _MSVCRT_AVAILABLE:
            return CursorMenu._odabir_windows(opcije, naslov, allow_y, allow_r, kontekst)
        elif _CURSES_AVAILABLE:
            return CursorMenu._odabir_linux(opcije, naslov, allow_y, allow_r, kontekst)
        else:
            # Fallback na input()
            return CursorMenu._odabir_fallback(opcije, naslov, allow_y, allow_r, kontekst)

    @staticmethod
    def _odabir_windows(opcije: list[str], naslov: str, allow_y: bool, allow_r: bool,
                        kontekst: str = "") -> str:
        """Windows kursorski odabir koristeći msvcrt."""
        if not opcije:
            return "x"

        trenutni = 0

        while True:
            ocisti_ekran()
            prikazi_okvir(opcije, naslov, kontekst=kontekst, allow_y=allow_y, allow_r=allow_r, trenutni=trenutni)

            # Čekaj tipku
            while True:
                if msvcrt.kbhit():
                    key = msvcrt.getch()
                    if key == b'\xe0' or key == b'\x00':  # Extended key prefix
                        key = msvcrt.getch()
                        if key == b'H' or key == b'\x48':  # Up
                            trenutni = (trenutni - 1) % len(opcije)
                            break
                        elif key == b'P' or key == b'\x50':  # Down
                            trenutni = (trenutni + 1) % len(opcije)
                            break
                    elif key in (b'\r', b' ', b'\n'):  # Enter or Space
                        return str(trenutni + 1)
                    elif key == b'x' or key == b'X':
                        return "x"
                    elif (key == b'y' or key == b'Y') and allow_y:
                        return "y"
                    elif (key == b'r' or key == b'R') and allow_r:
                        return "r"
                    elif key.isdigit() and 1 <= int(key) <= len(opcije):
                        return key.decode()

    @staticmethod
    def _odabir_linux(opcije: list[str], naslov: str, allow_y: bool, allow_r: bool,
                      kontekst: str = "") -> str:
        """Linux kursorski odabir koristeći curses."""
        if not opcije:
            return "x"

        def wrapper(stdscr):
            curses.curs_set(0)
            stdscr.keypad(True)
            trenutni = 0

            while True:
                stdscr.clear()
                # Crtaj okvir
                sirina = 64
                stdscr.addstr("╔" + "═" * sirina + "╗\n")
                if naslov:
                    naslov_str = f"  {naslov}"
                    stdscr.addstr("║" + naslov_str.ljust(sirina) + "║\n")
                if kontekst:
                    ctx_str = f"  {kontekst}"
                    stdscr.addstr("║" + ctx_str.ljust(sirina) + "║\n")
                stdscr.addstr("╠" + "═" * sirina + "╣\n")

                for i, opc in enumerate(opcije):
                    if i == trenutni:
                        stdscr.addstr(f"║  > [{i + 1}] {opc}" + " " * (sirina - len(f"  > [{i + 1}] {opc}")) + "║\n")
                    else:
                        stdscr.addstr(f"║    [{i + 1}] {opc}" + " " * (sirina - len(f"    [{i + 1}] {opc}")) + "║\n")

                stdscr.addstr("╠" + "═" * sirina + "╣\n")
                if allow_y:
                    stdscr.addstr("║  [Y] — BRZI TEST" + " " * (sirina - 17) + "║\n")
                if allow_r:
                    stdscr.addstr("║  [R] — Nastavi od checkpointa" + " " * (sirina - 31) + "║\n")
                stdscr.addstr("║  [X] — Izlaz / Povratak" + " " * (sirina - 23) + "║\n")
                stdscr.addstr("╚" + "═" * sirina + "╝\n")

                stdscr.refresh()

                key = stdscr.getch()
                if key == curses.KEY_UP:
                    trenutni = (trenutni - 1) % len(opcije)
                elif key == curses.KEY_DOWN:
                    trenutni = (trenutni + 1) % len(opcije)
                elif key in (curses.KEY_ENTER, 10, 32):
                    return str(trenutni + 1)
                elif key == ord('x'):
                    return "x"
                elif key == ord('y') and allow_y:
                    return "y"
                elif key == ord('r') and allow_r:
                    return "r"

        return curses.wrapper(wrapper)

    @staticmethod
    def _odabir_fallback(opcije: list[str], naslov: str, allow_y: bool, allow_r: bool,
                         kontekst: str = "") -> str:
        """Fallback na input() ako kursorska navigacija nije dostupna."""
        if not opcije:
            return "x"

        prikazi_okvir(opcije, naslov, kontekst=kontekst, allow_y=allow_y, allow_r=allow_r, trenutni=trenutni)

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


# ===========================================================================
# Menu — CLI sučelje s kursorskom navigacijom
# ===========================================================================

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

        # Inicijaliziraj module
        self._fm = FileManager(config)
        self._doc_proc = DocumentProcessor(config)
        self._text_cleaner = TextCleaner(self._fm, config)
        self._translator = Translator(config, checkpoint_manager)
        self._tts_engine = TTSEngine(config, self._fm)

    # -----------------------------------------------------------------------
    # Glavni entry point
    # -----------------------------------------------------------------------

    def run(self) -> None:
        """Pokreće glavni izbornik."""
        while True:
            odabir = self.show_main()
            if odabir == "exit" or odabir == "x":
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
            elif odabir == "5":
                self._pokreni_web_gui()
            elif odabir and odabir.startswith("resume:"):
                # P2: Checkpoint resume - nastavi prijevod od zadnje točke
                self._nastavi_prijevod(odabir)

    # -----------------------------------------------------------------------
    # Glavni izbornik
    # -----------------------------------------------------------------------

    def show_main(self) -> str:
        """Glavni izbornik s checkpoint blokom i BRZI TEST linijom.

        Returns:
            Odabir korisnika ("1", "2", "3", "4", "test", "exit").
        """
        ocisti_ekran()

        # Header
        version = self._cfg.get("project", {}).get("version", "0.4.0")
        nacrtaj_okvir(f"Dynamic Book Translator v{version}", sirina=64,
                      kontekst="GLAVNI IZBORNIK")
        print()

        # Checkpoint blok
        checkpointi = self._cp.ucitaj_checkpointe()
        if checkpointi:
            print("╔" + "═" * 64 + "╗")
            print("║  🔄 AKTIVNI CHECKPOINTOVI:" + " " * 41 + "║")
            for cp in checkpointi:
                title = cp.get("book_title", "Nepoznato")
                progress = f"{cp.get('current_segment', 0)}/{cp.get('total_segments', 0)}"
                line = f"  • {title} — {progress} segmenata"
                print("║" + line.ljust(64) + "║")
            print("║  [R] — Nastavi od zadnje točke" + " " * 41 + "║")
            print("╚" + "═" * 64 + "╝")
            print()

        # BRZI TEST linija
        last_test = self._cp.ucitaj_last_test()
        if last_test:
            print("╔" + "═" * 64 + "╗")
            gran = last_test.get('granularnost', 'paragraph')
            count = last_test.get('count', 1)
            hdr = "DA" if last_test.get('header', True) else "NE"
            y_str = f"  [Y] — BRZI TEST ({gran}, {count} segmenata | Header: {hdr})"
            print("║" + y_str.ljust(64) + "║")
            print("╚" + "═" * 64 + "╝")
            print()

        # Opcije
        opcije = [
            "Konverzija dokumenata (PDF/DOCX/EPUB/MOBI → TXT/MD)",
            "Obrada i čišćenje tekstualnih datoteka ([fixed] priprema)",
            "Prevođenje obrađenog teksta preko lokalnog LLM-a",
            "Pretvaranje prevedenih datoteka u MP3 audio knjigu",
            "Pokreni web GUI poslužitelj (FastAPI)"
        ]

        odabir = CursorMenu.odabir_iz_liste(opcije, "MambaBookVoice v4.5",
                                            allow_y=last_test is not None,
                                            allow_r=len(checkpointi) > 0,
                                            kontekst="GLAVNI IZBORNIK")

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
        nacrtaj_okvir("FAZA 1 — KONVERZIJA DOKUMENATA", sirina=64,
                      kontekst="GLAVNI IZBORNIK > KONVERZIJA")
        print()

        input_dir = Path(self._cfg["directories"]["input"])
        if not input_dir.exists():
            print("Direktorij work/input/ ne postoji. Dodajte datoteke za konverziju.")
            ack = self._safe_input("Pritisnite Enter za povratak...")
            if ack is None:
                return
            return

        # Pronađi datoteke rekurzivno s metadatama
        datoteke_info = self._pronadi_datoteke_s_metadatama(input_dir)

        if not datoteke_info:
            print("Nema datoteka u work/input/ (uključujući poddirektorije).")
            ack = self._safe_input("Pritisnite Enter za povratak...")
            if ack is None:
                return
            return

        datoteke_info = self._sortiraj_stavke(datoteke_info)

        # Batch odabir s mtime oznakama
        odabrane = self._batch_odabir(
            [
                f"[{info['mtime_str']}] [{info['type']}] "
                f"{info['path'].relative_to(input_dir)} ({info['size']})"
                for info in datoteke_info
            ],
            "Odaberite datoteke za konverziju (ili X za povratak)"
        )

        if odabrane == "x":
            return

        if not odabrane:
            print("Nije odabrana nijedna datoteka.")
            ack = self._safe_input("Pritisnite Enter za povratak...")
            if ack is None:
                return
            return

        print(f"\nOdabrano: {len(odabrane)} datoteka")
        print("Konverzija u tijeku...")

        # Konvertiraj odabrane datoteke
        for idx in odabrane:
            if idx < 0 or idx >= len(datoteke_info):
                print(f"  -> Preskakanje: nevažeći indeks {idx}")
                continue
            datoteka_info = datoteke_info[idx]
            putanja = datoteka_info["path"]

            # Provjeri postoji li datoteka
            if not putanja.exists():
                print(f"  -> Preskakanje: datoteka ne postoji {putanja}")
                continue
            rel_path = putanja.relative_to(input_dir)

            print(f"\nKonverzija: {rel_path}")

            try:
                # Učitaj tekst iz dokumenta
                tekst = self._doc_proc.ucitaj_izvorni_tekst(str(putanja))

                # Kreiraj per-book direktorij kroz FileManager
                book_title = putanja.stem
                book_dir = self._fm.work_output_book_dir(book_title)

                # Zaštita od prepisivanja: book.txt → book_001.txt → book_002.txt
                izlazna_putanja = self._fm.ensure_file_path(
                    book_dir / f"{putanja.stem}.txt",
                    suffix_if_exists=True,
                )

                with open(izlazna_putanja, 'w', encoding='utf-8') as f:
                    f.write(tekst)

                print(f"  -> Spremljeno: {izlazna_putanja}")

                # Kreiraj per-book config.yaml ako ne postoji
                config_putanja = book_dir / "config.yaml"
                if not config_putanja.exists():
                    from app.config_loader import create_book_config
                    create_book_config(
                        book_dir=book_dir,
                        book_title=book_title,
                        author="Autor",
                        original_file=putanja.name,
                        profile_name="sf_literature"
                    )
                    print(f"  -> Config: {config_putanja.name}")

            except Exception as e:
                print(f"  -> Greška: {e}")

        print("\nKonverzija završena.")
        ack = self._safe_input("Pritisnite Enter za povratak...")

    # -----------------------------------------------------------------------
    # Faza 2 - Čišćenje
    # -----------------------------------------------------------------------

    def show_phase2(self) -> None:
        """Čišćenje tehničkog šuma s batch odabirom."""
        ocisti_ekran()
        nacrtaj_okvir("FAZA 2 — ČIŠĆENJE TEHNIČKOG ŠUMA + KREIRANJE MEMORIJE",
                      sirina=64, kontekst="GLAVNI IZBORNIK > ČIŠĆENJE")
        print()

        output_dir = Path(self._cfg["directories"]["output"])
        if not output_dir.exists():
            print("Direktorij work/output/ ne postoji.")
            ack = self._safe_input("Pritisnite Enter za povratak...")
            if ack is None:
                return
            return

        # Pronađi .txt datoteke ili direktorije knjiga
        txt_datoteke = sorted(output_dir.glob("*.txt"), key=lambda p: p.name.lower())
        knjige_dir = [d for d in output_dir.iterdir() if d.is_dir()]

        if txt_datoteke:
            # Ako postoje .txt datoteke u rootu, premjesti ih u per-book direktorije
            stavke = self._sortiraj_putanje(txt_datoteke)
            odabrane = self._batch_odabir(
                [f"[{self._mtime_str(p)}] {p.name}" for p in stavke],
                "Odaberite datoteke za čišćenje (ili X za povratak)"
            )
            txt_datoteke = stavke

            if odabrane == "x":
                return

            if not odabrane:
                print("Nije odabrana nijedna datoteka.")
                ack = self._safe_input("Pritisnite Enter za povratak...")
                if ack is None:
                    return
                return

            print(f"\nOdabrano: {len(odabrane)} datoteka")
            print("Čišćenje u tijeku...")

            for idx in odabrane:
                if idx < 0 or idx >= len(txt_datoteke):
                    print(f"  -> Preskakanje: nevažeći indeks {idx}")
                    continue
                txt_datoteka = txt_datoteke[idx]

                # Provjeri postoji li datoteka
                if not txt_datoteka.exists():
                    print(f"  -> Preskakanje: datoteka ne postoji {txt_datoteka.name}")
                    continue

                print(f"\nČišćenje: {txt_datoteka.name}")

                try:
                    # Učitaj tekst
                    with open(txt_datoteka, 'r', encoding='utf-8') as f:
                        tekst = f.read()

                    # Kreiraj per-book direktorij kroz FileManager
                    book_title = txt_datoteka.stem
                    book_dir = self._fm.work_output_book_dir(book_title)

                    # Očisti dokument
                    ocisceni_tekst = self._text_cleaner.ocisti_dokument(tekst, book_title)

                    # Spremi očišćeni tekst kao [fixed] datoteku u per-book direktorij s inkrementalnim sufiksom
                    from app.text_cleaner import generiraj_inkrementalnu_putanju
                    izlazna_putanja = Path(generiraj_inkrementalnu_putanju(str(book_dir), book_title, ".txt"))
                    with open(izlazna_putanja, 'w', encoding='utf-8') as f:
                        f.write(ocisceni_tekst)

                    print(f"  -> Očišćeno: {izlazna_putanja.name}")

                    # Kreiraj memoriju
                    memorija = self._text_cleaner.kreiraj_memoriju(ocisceni_tekst)
                    memorija_putanja = book_dir / f"{book_title}_memorija.json"
                    with open(memorija_putanja, 'w', encoding='utf-8') as f:
                        json.dump(memorija, f, indent=2, ensure_ascii=False)
                    print(f"  -> Memorija: {memorija_putanja.name}")

                    # Kreiraj book config ako ne postoji
                    config_putanja = book_dir / "config.yaml"
                    if not config_putanja.exists():
                        from app.config_loader import create_book_config
                        create_book_config(
                            book_dir=book_dir,
                            book_title=book_title,
                            author="Autor",
                            original_file=txt_datoteka.name,
                            profile_name="sf_literature"
                        )
                        print(f"  -> Config: {config_putanja.name}")

                except Exception as e:
                    print(f"  -> Greška: {e}")

        elif knjige_dir:
            # Ako postoje direktoriji knjiga, koristi per-book logiku
            knjige_dir = self._sortiraj_putanje(knjige_dir)
            odabrane = self._batch_odabir(
                [f"[{self._mtime_str(d)}] {d.name}" for d in knjige_dir],
                "Odaberite knjige za čišćenje (ili X za povratak)"
            )

            if odabrane == "x":
                return

            if not odabrane:
                print("Nije odabrana nijedna knjiga.")
                ack = self._safe_input("Pritisnite Enter za povratak...")
                if ack is None:
                    return
                return

            print(f"\nOdabrano: {len(odabrane)} knjiga")
            print("Čišćenje u tijeku...")

            for idx in odabrane:
                if idx < 0 or idx >= len(knjige_dir):
                    print(f"  -> Preskakanje: nevažeći indeks {idx}")
                    continue
                knjiga_dir = knjige_dir[idx]

                # Provjeri postoji li direktorij
                if not knjiga_dir.exists() or not knjiga_dir.is_dir():
                    print(f"  -> Preskatanje: direktorij ne postoji {knjiga_dir.name}")
                    continue

                # Samo sirovi (ne-[fixed]) .txt — izbjegava re-čišćenje i gomilanje
                txt_datoteke = [
                    t for t in knjiga_dir.glob("*.txt")
                    if "[fixed]" not in t.stem.lower()
                ]

                if not txt_datoteke:
                    print(f"\n{knjiga_dir.name}: Nema sirovih .txt datoteka za čišćenje "
                          f"(samo [fixed] ili prazno).")
                    continue

                for txt_datoteka in txt_datoteke:
                    print(f"\nČišćenje: {knjiga_dir.name}/{txt_datoteka.name}")

                    try:
                        # Učitaj tekst
                        with open(txt_datoteka, 'r', encoding='utf-8') as f:
                            tekst = f.read()

                        # Očisti dokument i spremi kao [fixed] datoteku s inkrementalnim sufiksom
                        from app.text_cleaner import generiraj_inkrementalnu_putanju
                        ocisceni_tekst = self._text_cleaner.ocisti_dokument(tekst, knjiga_dir.name)
                        izlazna_putanja = Path(generiraj_inkrementalnu_putanju(str(knjiga_dir), txt_datoteka.name, ".txt"))
                        with open(izlazna_putanja, 'w', encoding='utf-8') as f:
                            f.write(ocisceni_tekst)

                        print(f"  -> Očišćeno: {izlazna_putanja.name}")

                        # Kreiraj memoriju
                        memorija = self._text_cleaner.kreiraj_memoriju(ocisceni_tekst)
                        memorija_putanja = knjiga_dir / f"{knjiga_dir.name}_memorija.json"
                        with open(memorija_putanja, 'w', encoding='utf-8') as f:
                            json.dump(memorija, f, indent=2, ensure_ascii=False)
                        print(f"  -> Memorija: {memorija_putanja.name}")

                        # Kreiraj book config ako ne postoji
                        config_putanja = knjiga_dir / "config.yaml"
                        if not config_putanja.exists():
                            from app.config_loader import create_book_config
                            create_book_config(
                                book_dir=knjiga_dir,
                                book_title=knjiga_dir.name,
                                author="Autor",
                                original_file=txt_datoteka.name,
                                profile_name="sf_literature"
                            )
                            print(f"  -> Config: {config_putanja.name}")

                    except Exception as e:
                        print(f"  -> Greška: {e}")
        else:
            print("Nema .txt datoteka ili knjiga u work/output/")
            ack = self._safe_input("Pritisnite Enter za povratak...")
            if ack is None:
                return
            return

        print("\nČišćenje završeno.")
        ack = self._safe_input("Pritisnite Enter za povratak...")

    # -----------------------------------------------------------------------
    # Faza 3 - Prevođenje
    # -----------------------------------------------------------------------

    def show_phase3(self) -> None:
        """Prevođenje: TEST / Produkcijski / Opcije."""
        while True:
            ocisti_ekran()
            nacrtaj_okvir("FAZA 3 — PREVOĐENJE", sirina=64,
                          kontekst="GLAVNI IZBORNIK > PREVOĐENJE")
            print()

            # Notifikacijska linija
            gran = self._opcije["granularnost"]
            kol = self._opcije["kolicina"]
            hdr = "DA" if self._opcije["header"] else "NE"
            print(f"  ── Granularnost: {gran.capitalize()} | Količina: {kol} | Header: {hdr} ──")
            print()

            opcije = [
                "TEST prijevod",
                "Produkcijski prijevod",
                "Opcije",
                "Povratak"
            ]

            odabir = CursorMenu.odabir_iz_liste(opcije, "FAZA 3 — PREVOĐENJE",
                                                kontekst="GLAVNI IZBORNIK > PREVOĐENJE")

            if odabir == "x" or odabir == "4":
                break
            elif odabir == "3":
                self.show_opcije()
            elif odabir == "1":
                self._test_prijevod()
            elif odabir == "2":
                self._produkcijski_prijevod()

    def show_opcije(self) -> None:
        """Opcije: Header, Granularnost, Količina."""
        while True:
            ocisti_ekran()
            nacrtaj_okvir("OPCIJE PREVOĐENJA", sirina=52,
                          kontekst="GLAVNI IZBORNIK > PREVOĐENJE > OPCIJE")
            print()

            # Dropdown prikaz
            print("╔" + "═" * 52 + "╗")
            print("║  [1] Header u testnoj datoteci:" + " " * 23 + "║")
            if self._opcije["header"]:
                print("║      ● DA" + " " * 43 + "║")
                print("║      ○ NE" + " " * 43 + "║")
            else:
                print("║      ○ DA" + " " * 43 + "║")
                print("║      ● NE" + " " * 43 + "║")
            print("║" + " " * 52 + "║")
            print("║  [2] Granularnost segmenata:" + " " * 25 + "║")
            granularnosti = ["odlomak", "paragraf", "rečenica"]
            trenutni_g = self._opcije["granularnost"]
            for g in granularnosti:
                if g == trenutni_g:
                    print(f"║      ● {g.capitalize()}" + " " * (52 - 8 - len(g.capitalize())) + "║")
                else:
                    print(f"║      ○ {g.capitalize()}" + " " * (52 - 8 - len(g.capitalize())) + "║")
            print("║" + " " * 52 + "║")
            print(f"║  [3] Količina (default): {self._opcije['kolicina']}" + " " * (52 - 30 - len(str(self._opcije['kolicina']))) + "║")
            print("║" + " " * 52 + "║")
            print("║  [X] Povratak" + " " * 40 + "║")
            print("╚" + "═" * 52 + "╝")
            print()

            opcije = [
                f"1. Header u testu: {'DA' if self._opcije['header'] else 'NE'}",
                f"2. Granularnost: {self._opcije['granularnost'].capitalize()}",
                f"3. Količina (TEST): {self._opcije['kolicina']}",
                "X. Povratak"
            ]

            odabir = CursorMenu.odabir_iz_liste(opcije, "OPCIJE PREVOĐENJA",
                                                kontekst="GLAVNI IZBORNIK > PREVOĐENJE > OPCIJE")

            if odabir == "x" or odabir == "4":
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
        nacrtaj_okvir("FAZA 4 — TTS SINTEZA", sirina=64,
                      kontekst="GLAVNI IZBORNIK > TTS")
        print()

        opcije = [
            "Zasebne MP3 datoteke po segmentima",
            "Jedna MP3 datoteka (cijela knjiga)",
            "Povratak"
        ]

        odabir = CursorMenu.odabir_iz_liste(opcije, "FAZA 4 — TTS SINTEZA",
                                            kontekst="GLAVNI IZBORNIK > TTS")

        if odabir == "x" or odabir == "3":
            return

        # Odabir knjige za TTS
        translated_dir = Path(self._cfg["directories"]["translated"])
        if not translated_dir.exists():
            print("Direktorij work/translated/ ne postoji.")
            ack = self._safe_input("Pritisnite Enter za povratak...")
            if ack is None:
                return
            return

        try:
            knjige = [d for d in translated_dir.iterdir() if d.is_dir()]
        except PermissionError as e:
            print(f"Greška: Nedozvoljen pristup direktoriju work/translated/: {e}")
            ack = self._safe_input("Pritisnite Enter za povratak...")
            if ack is None:
                return
            return
        except OSError as e:
            print(f"Greška pri čitanju direktorija work/translated/: {e}")
            ack = self._safe_input("Pritisnite Enter za povratak...")
            if ack is None:
                return
            return

        if not knjige:
            print("Nema knjiga u work/translated/")
            ack = self._safe_input("Pritisnite Enter za povratak...")
            return

        knjige = self._sortiraj_putanje(knjige)
        odabrane = self._batch_odabir(
            [f"[{self._mtime_str(d)}] {d.name}" for d in knjige],
            "Odaberite knjigu za TTS sintezu (ili X za povratak)"
        )

        if odabrane == "x":
            return

        if not odabrane or len(odabrane) != 1:
            print("Odaberite točno jednu knjigu za TTS sintezu.")
            ack = self._safe_input("Pritisnite Enter za povratak...")
            return

        idx = odabrane[0]
        if idx < 0 or idx >= len(knjige):
            print("Greška: nevažeći odabir knjige.")
            ack = self._safe_input("Pritisnite Enter za povratak...")
            return

        knjiga_dir = knjige[idx]

        # Provjeri postoji li direktorij
        if not knjiga_dir.exists() or not knjiga_dir.is_dir():
            print(f"Direktorij {knjiga_dir.name} ne postoji.")
            ack = self._safe_input("Pritisnite Enter za povratak...")
            return

        txt_datoteke = list(knjiga_dir.glob("*.txt"))

        if not txt_datoteke:
            print(f"Nema .txt datoteka u {knjiga_dir.name}")
            ack = self._safe_input("Pritisnite Enter za povratak...")
            return

        # Preferiraj produkcijski prijevod (bez _test_); inače prvi po sort_mode
        produkcijski = [t for t in txt_datoteke if "_test_" not in t.name]
        kandidati = self._sortiraj_putanje(produkcijski or txt_datoteke)
        txt_datoteka = kandidati[0]
        print(f"\nTTS sinteza: {knjiga_dir.name}/{txt_datoteka.name}")
        print(f"Način: {'Zasebne datoteke' if odabir == '1' else 'Jedna datoteka'}")
        print()

        try:
            # Učitaj tekst
            with open(txt_datoteka, 'r', encoding='utf-8') as f:
                tekst = f.read()

            # Učitaj book config ako postoji
            config_putanja = knjiga_dir / "config.yaml"
            book_config = None
            if config_putanja.exists():
                with open(config_putanja, 'r', encoding='utf-8') as f:
                    book_config = yaml.safe_load(f)

            # Zaštita mape: ako postoji, kreira ..._001, ..._002 (ne dira staru)
            audiobook_dir = self._fm.ensure_dir(
                self._fm.audiobook_dir(
                    knjiga_dir.name,
                    book_config.get("author", "Unknown") if book_config else "Unknown"
                ),
                suffix_if_exists=True,
            )

            # Pozovi TTSEngine
            self._tts_engine.generiraj_audiobook(
                tekst=tekst,
                book_title=knjiga_dir.name,
                book_config=book_config or {},
                output_dir=audiobook_dir,
                merge_single=(odabir == "2")
            )

            print(f"\nTTS sinteza završena: {audiobook_dir}")

        except Exception as e:
            print(f"Greška pri TTS sintezi: {e}")

        ack = self._safe_input("\nPritisnite Enter za povratak...")

    # -----------------------------------------------------------------------
    # Pomoćne metode
    # -----------------------------------------------------------------------

    def _mtime_str(self, path: Path) -> str:
        """Vraća datum/vrijeme zadnje izmjene u formatu YYYY-MM-DD HH:MM:SS."""
        try:
            return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        except OSError:
            return "0000-00-00 00:00:00"

    def _sortiraj_putanje(self, putanje: list[Path]) -> list[Path]:
        """Sortira putanje prema sort_mode iz konfiguracije."""
        sort_mode = self._cfg.get("sort_mode", "date_desc")
        if sort_mode == "name_asc":
            return sorted(putanje, key=lambda p: p.name.lower())
        if sort_mode == "name_desc":
            return sorted(putanje, key=lambda p: p.name.lower(), reverse=True)
        if sort_mode == "date_asc":
            return sorted(putanje, key=lambda p: self._safe_mtime(p))
        return sorted(putanje, key=lambda p: self._safe_mtime(p), reverse=True)

    def _sortiraj_stavke(self, stavke: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Sortira listu dict stavki s 'path'/'name'/'mtime' prema sort_mode."""
        sort_mode = self._cfg.get("sort_mode", "date_desc")
        if sort_mode == "name_asc":
            return sorted(stavke, key=lambda x: x.get("name", str(x.get("path", ""))).lower())
        if sort_mode == "name_desc":
            return sorted(stavke, key=lambda x: x.get("name", str(x.get("path", ""))).lower(), reverse=True)
        if sort_mode == "date_asc":
            return sorted(stavke, key=lambda x: x.get("mtime", 0.0))
        return sorted(stavke, key=lambda x: x.get("mtime", 0.0), reverse=True)

    @staticmethod
    def _safe_mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    def _pronadi_datoteke_s_metadatama(self, dir_path: Path) -> list[dict[str, Any]]:
        """Pronalazi datoteke rekurzivno s metadatama o tipu.

        Args:
            dir_path: Početni direktorij za pretragu.

        Returns:
            Lista rječnika s path, type, size, mtime, mtime_str, name.
        """
        datoteke_info = []
        supported_exts = {
            '.pdf': 'PDF',
            '.docx': 'DOCX',
            '.doc': 'DOC',
            '.epub': 'EPUB',
            '.mobi': 'MOBI',
            '.txt': 'TXT'
        }

        for path in dir_path.rglob("*"):
            if path.is_file() and not path.name.startswith("."):
                ext = path.suffix.lower()
                file_type = supported_exts.get(ext, ext.upper().replace(".", ""))

                try:
                    st = path.stat()
                    size_bytes = st.st_size
                    mtime = st.st_mtime
                except OSError:
                    size_bytes = 0
                    mtime = 0.0

                if size_bytes < 1024:
                    size_str = f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    size_str = f"{size_bytes / 1024:.1f} KB"
                else:
                    size_str = f"{size_bytes / (1024 * 1024):.1f} MB"

                datoteke_info.append({
                    "path": path,
                    "name": path.name,
                    "type": file_type,
                    "size": size_str,
                    "mtime": mtime,
                    "mtime_str": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                    if mtime else "0000-00-00 00:00:00",
                })

        return datoteke_info

    def _odaberi_fixed_datoteku(self, naslov: str, search_dir: Optional[Path] = None) -> Optional[Path]:
        """Prikazuje i omogućava odabir [fixed] datoteke uz dinamički prikaz datuma izmjene i 4 načina sortiranja."""
        from app.config_loader import save_settings

        if search_dir is None:
            search_dir = Path(self._cfg["directories"]["output"])

        if not search_dir.exists():
            print(f"Direktorij {search_dir} ne postoji.")
            self._safe_input("Pritisnite Enter za povratak...")
            return None

        while True:
            # Pronađi sve [fixed] datoteke (uključujući [fixed]_001) ili općenite txt
            fixed_files = list(search_dir.rglob("*[fixed]*.txt"))
            if not fixed_files:
                fixed_files = [
                    f for f in search_dir.rglob("*.txt")
                    if "_memorija" not in f.name and "_test_" not in f.name
                ]

            if not fixed_files:
                print(f"Nema raspoloživih .txt / [fixed] datoteka u {search_dir.name}.")
                self._safe_input("Pritisnite Enter za povratak...")
                return None

            items = []
            for pf in fixed_files:
                mtime = self._safe_mtime(pf)
                rel_display = pf.name
                if pf.parent != search_dir:
                    rel_display = f"{pf.parent.name}/{pf.name}"
                items.append({
                    "path": pf,
                    "name": rel_display,
                    "mtime": mtime,
                    "mtime_str": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                    if mtime else "0000-00-00 00:00:00",
                })

            sort_mode = self._cfg.get("sort_mode", "date_desc")
            items = self._sortiraj_stavke(items)

            if sort_mode == "name_asc":
                sort_label = "IMENU – Uzlazno (ASC)"
            elif sort_mode == "name_desc":
                sort_label = "IMENU – Silazno (DESC)"
            elif sort_mode == "date_asc":
                sort_label = "DATUMU IZMJENE – Uzlazno (ASC)"
            else:
                sort_label = "DATUMU IZMJENE – Silazno (DESC)"

            ocisti_ekran()
            nacrtaj_okvir(naslov, sirina=64, kontekst="GLAVNI IZBORNIK > ODABIR DATOTEKE")
            print()
            print(f"  ── Način sortiranja: {sort_label} ──")
            print()

            for i, item in enumerate(items, 1):
                print(f"  {i}. [{item['mtime_str']}] {item['name']}")
            print()
            print("  [S] Promijeni način sortiranja")
            print("  [X] Povratak")
            print()

            unos_raw = self._safe_input("Odaberite broj datoteke (ili S / X): ")
            if unos_raw is None:
                return None

            unos = unos_raw.strip().lower()

            if unos == "x" or unos == "":
                return None
            elif unos == "s":
                # Podizbornik za sortiranje
                ocisti_ekran()
                nacrtaj_okvir("POSTAVKE SORTIRANJA", sirina=52)
                print()
                print("  1. Sortiraj po IMENU – Uzlazno (ASC)")
                print("  2. Sortiraj po IMENU – Silazno (DESC)")
                print("  3. Sortiraj po DATUMU IZMJENE – Uzlazno (ASC)")
                print("  4. Sortiraj po DATUMU IZMJENE – Silazno (DESC)")
                print()
                opt_raw = self._safe_input("Odaberite način sortiranja (1-4 ili Enter za natrag): ")
                if opt_raw is not None:
                    opt = opt_raw.strip()
                    if opt == "1":
                        self._cfg["sort_mode"] = "name_asc"
                    elif opt == "2":
                        self._cfg["sort_mode"] = "name_desc"
                    elif opt == "3":
                        self._cfg["sort_mode"] = "date_asc"
                    elif opt == "4":
                        self._cfg["sort_mode"] = "date_desc"

                    if opt in ["1", "2", "3", "4"]:
                        try:
                            save_settings(self._cfg)
                        except Exception as e:
                            logging.error(f"Greška pri spremanju sort_mode: {e}")
                continue
            elif unos.isdigit():
                idx = int(unos) - 1
                if 0 <= idx < len(items):
                    return items[idx]["path"]
                else:
                    print(f"Nevažeći broj. Unesite broj između 1 i {len(items)}.")
                    self._safe_input("Pritisnite Enter za nastavak...")
            else:
                print("Nevažeći unos.")
                self._safe_input("Pritisnite Enter za nastavak...")

    def _safe_input(self, prompt: str = "") -> Optional[str]:
        """Sigurno čitanje unosa s rukovanjem EOF/KeyboardInterrupt.

        Args:
            prompt: Poruka za prikaz prije unosa.

        Returns:
            Unos korisnika ili None kod EOF/KeyboardInterrupt.
        """
        try:
            return input(prompt)
        except (EOFError, KeyboardInterrupt):
            print()
            return None

    def _batch_odabir(self, stavke: list[str], naslov: str) -> list[int] | str:
        """Batch odabir: 1, 1,3,5, 1-5, *, X.

        Args:
            stavke: Lista stavki za odabir.
            naslov: Naslov za prikaz.

        Returns:
            Lista indeksa odabranih stavki ili "x" za povratak.
        """
        if not stavke:
            print("Nema dostupnih stavki za odabir.")
            return []

        print(f"{naslov}:")
        print()

        for i, stavka in enumerate(stavke, 1):
            print(f"  {i}. {stavka}")
        print()

        print("Unesite brojeve (npr. 1,3,5 ili 1-5 ili * za sve, ili X za povratak):")
        unos = self._safe_input("> ")
        if unos is None:
            return "x"  # EOF/KeyboardInterrupt -> povratak

        unos = unos.strip().lower()

        # Prazan Enter ne ruši skriptu — tretira se kao odustajanje bez odabira
        if unos == "":
            return []
        if unos == "x":
            return "x"
        if unos == "*":
            return list(range(len(stavke)))

        odabrani = set()
        for dio in unos.split(","):
            dio = dio.strip()
            if not dio:
                continue
            if "-" in dio:
                try:
                    parts = dio.split("-")
                    if len(parts) != 2:
                        print(f"  -> Nevažeći raspon: {dio}")
                        continue
                    start, end = map(int, parts)
                    # Ispravljanje: range(start-1, end+1) za ispravan raspon (inclusive end)
                    if start > end:
                        print(f"  -> Nevažeći raspon: {dio} (start > end)")
                        continue
                    for i in range(start - 1, end):
                        if 0 <= i < len(stavke):
                            odabrani.add(i)
                except ValueError:
                    print(f"  -> Nevažeći raspon: {dio}")
                    continue
            elif dio.isdigit():
                idx = int(dio) - 1
                if 0 <= idx < len(stavke):
                    odabrani.add(idx)
            else:
                print(f"  -> Nevažeći unos: {dio}")

        return sorted(odabrani)

    def _pokreni_web_gui(self) -> None:
        """Opcija [5] — Pokreće FastAPI web server i otvara preglednik."""
        ocisti_ekran()
        print("╔" + "═" * 64 + "╗")
        print("║  [5] POKRENI WEB GUI POSLUŽITELJ (FastAPI)" + " " * 23 + "║")
        print("╠" + "═" * 64 + "╣")
        print("║  Adresa: http://localhost:8000" + " " * 35 + "║")
        print("║  Pritisnite Ctrl+C za zaustavljanje servera." + " " * 20 + "║")
        print("╚" + "═" * 64 + "╝")
        print()

        try:
            import subprocess
            import webbrowser
            import time
            import signal

            # Eksplicitna putanja do Python interpretera u virtualnom okruženju
            # — osigurava da su uvicorn[standard], websockets i ostale knjižnice dostupne
            root = Path(__file__).resolve().parent.parent
            env_python = root / "knjige_env" / "Scripts" / "python.exe"

            if not env_python.exists():
                print(f"  Greška: Python interpreter nije pronađen: {env_python}")
                print("  Pokrenite server ručno: uvicorn web_server:app --host 127.0.0.1 --port 8000")
                self._safe_input("Pritisnite Enter za povratak...")
                return

            cmd = [
                str(env_python),
                "-m", "uvicorn",
                "web_server:app",
                "--host", "127.0.0.1",
                "--port", "8000",
                "--log-level", "info",
            ]

            print(f"  Interpreter: {env_python}")
            print(f"  Pokretanje: uvicorn web_server:app --host 127.0.0.1 --port 8000\n")

            # Pokreni kao subprocess — blokira dok korisnik ne pritisne Ctrl+C
            process = subprocess.Popen(cmd, cwd=str(root))

            # Otvori browser nakon 2 sekunde
            time.sleep(2.0)
            webbrowser.open("http://127.0.0.1:8000")

            print("  Server pokrenut. Pritisnite Ctrl+C za zaustavljanje...\n")

            try:
                process.wait()  # Čekaj dok korisnik ne zaustavi server
            except KeyboardInterrupt:
                print("\n  Zaustavljam server...")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                print("  Web server zaustavljen.")

        except Exception as e:
            print(f"  Greška pri pokretanju web servera: {e}")
            logging.error(f"Web server greška: {e}")

        self._safe_input("\nPritisnite Enter za povratak u izbornik...")

    def _potvrda_izlaza(self) -> bool:
        """Potvrda izlaza s Y/N.

        Returns:
            True ako korisnik potvrđuje izlaz.
        """
        print()
        odgovor = self._safe_input("Sigurno želite izaći? (Y/N): ")
        if odgovor is None:
            return True
        return odgovor.strip().upper() == "Y"

    def _brzi_test(self) -> None:
        """Pokreće BRZI TEST iz last_test.json."""
        ocisti_ekran()
        nacrtaj_okvir("BRZI TEST", sirina=64,
                      kontekst="GLAVNI IZBORNIK > BRZI TEST")
        print()

        last_test = self._cp.ucitaj_last_test()
        if not last_test:
            print("Nema podataka za BRZI TEST (pokrenite prvo TEST prijevod).")
            ack = self._safe_input("Pritisnite Enter za povratak...")
            return

        print(f"Granularnost: {last_test.get('granularnost', 'paragraph')}")
        print(f"Količina: {last_test.get('count', 1)}")
        print(f"Header: {last_test.get('header', True)}")
        print()
        print("BRZI TEST ponavlja zadnji TEST prijevod s istim postavkama.")
        print()

        book_title = last_test.get("book_title")
        if not book_title:
            print("Greška: nema naslova knjige u last_test.json.")
            ack = self._safe_input("Pritisnite Enter za povratak...")
            return

        output_dir = Path(self._cfg["directories"]["output"])
        knjiga_dir = output_dir / book_title

        if not knjiga_dir.exists() or not knjiga_dir.is_dir():
            print(f"Direktorij {knjiga_dir} ne postoji.")
            ack = self._safe_input("Pritisnite Enter za povratak...")
            return

        txt_datoteke = list(knjiga_dir.glob("*.txt"))
        if not txt_datoteke:
            print(f"Nema .txt datoteka u {knjiga_dir.name}")
            ack = self._safe_input("Pritisnite Enter za povratak...")
            return

        # Filtriraj test datoteke da uzme originalnu
        original_txt = [t for t in txt_datoteke if "_test_" not in t.name and "[fixed]" not in t.stem]
        if not original_txt:
            original_txt = txt_datoteke

        txt_datoteka = original_txt[0]
        print(f"BRZI TEST: {knjiga_dir.name}/{txt_datoteka.name}")
        print()

        try:
            with open(txt_datoteka, 'r', encoding='utf-8') as f:
                tekst = f.read()

            # Učitaj book config ako postoji
            config_putanja = knjiga_dir / "config.yaml"
            book_config = None
            if config_putanja.exists():
                with open(config_putanja, 'r', encoding='utf-8') as f:
                    book_config = yaml.safe_load(f)

            # Postavi knjigu i učitaj memoriju ([ime_knjige]_memorija.json)
            self._translator.postavi_knjigu(str(knjiga_dir), book_config)

            prijevod = self._translator.prevedi_test(
                tekst,
                granularnost=last_test.get("granularnost", "paragraph"),
                kolicina=last_test.get("count", 1),
                header=last_test.get("header", True)
            )

            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            naziv = f"{txt_datoteka.stem}_test_{timestamp}.txt"

            # Spremi u work/translated/<Knjiga>/ (ista mapa; zaštita na razini datoteke)
            translated_book_dir = self._fm.ensure_dir(
                self._fm.book_output_dir(
                    knjiga_dir.name,
                    book_config.get("author", "Unknown") if book_config else "Unknown"
                ),
                suffix_if_exists=False,
            )

            # Zaštita datoteke: nikad ne pregazi postojeći .txt
            izlazna_putanja = self._fm.ensure_file_path(
                translated_book_dir / naziv,
                suffix_if_exists=True,
            )

            with open(izlazna_putanja, 'w', encoding='utf-8') as f:
                f.write(prijevod)

            print(f"BRZI TEST prijevod spremljen: {izlazna_putanja.name}")

        except Exception as e:
            print(f"Greška pri BRZOM TESTU: {e}")

        ack = self._safe_input("\nPritisnite Enter za povratak...")

    def _nastavi_prijevod(self, odabir: str) -> None:
        """P2: Nastavlja prijevod od checkpointa.

        Args:
            odabir: String u formatu "resume:<index>" gdje je index
                indeks checkpointa u listi.
        """
        try:
            idx_str = odabir.split(":")[1]
            idx = int(idx_str)
        except (IndexError, ValueError):
            print(f"Greška: nevažeći resume odabir: {odabir}")
            ack = self._safe_input("Pritisnite Enter za povratak...")
            return

        checkpointi = self._cp.ucitaj_checkpointe()
        if idx < 0 or idx >= len(checkpointi):
            print(f"Greška: nevažeći indeks checkpointa: {idx}")
            ack = self._safe_input("Pritisnite Enter za povratak...")
            return

        cp = checkpointi[idx]
        book_id = cp.get("book_id", "")
        book_title = cp.get("book_title", "Nepoznato")
        current_segment = cp.get("current_segment", 0)
        total_segments = cp.get("total_segments", 0)
        output_path = cp.get("output_path", "")

        print(f"\nNastavak prijevoda: {book_title}")
        print(f"Checkpoint: {current_segment}/{total_segments} segmenata")
        print()

        # Pronađi direktorij knjige i [fixed] datoteku
        output_dir = Path(self._cfg["directories"]["output"])
        knjiga_dir = output_dir / book_title

        if not knjiga_dir.exists() or not knjiga_dir.is_dir():
            print(f"Direktorij {knjiga_dir} ne postoji.")
            ack = self._safe_input("Pritisnite Enter za povratak...")
            return

        # Traži [fixed] datoteku
        fixed_datoteke = list(knjiga_dir.glob("*[fixed]*.txt"))
        if not fixed_datoteke:
            txt_datoteke = list(knjiga_dir.glob("*.txt"))
            if not txt_datoteke:
                print(f"Nema .txt datoteka u {knjiga_dir.name}")
                ack = self._safe_input("Pritisnite Enter za povratak...")
                return
            txt_datoteka = txt_datoteke[0]
        else:
            txt_datoteka = fixed_datoteke[0]

        try:
            # Učitaj tekst
            with open(txt_datoteka, 'r', encoding='utf-8') as f:
                tekst = f.read()

            # Učitaj book config ako postoji
            config_putanja = knjiga_dir / "config.yaml"
            book_config = None
            if config_putanja.exists():
                with open(config_putanja, 'r', encoding='utf-8') as f:
                    book_config = yaml.safe_load(f)

            # Postavi knjigu i učitaj memoriju
            self._translator.postavi_knjigu(str(knjiga_dir), book_config)

            # Nastavi prijevod od current_segment
            prijevod, je_prekinuto = self._translator.prevedi_knjigu(
                tekst,
                output_path=output_path,
                book_id=book_id,
                granularnost=self._opcije["granularnost"],
                resume_from=current_segment
            )

            if je_prekinuto:
                print(f"Prijevod prekinut - napredak spremljen u checkpoint.")
            else:
                print(f"Prijevod završen: {output_path}")

        except Exception as e:
            print(f"Greška pri nastavku prijevoda: {e}")

        ack = self._safe_input("\nPritisnite Enter za povratak...")

    def _odabir_checkpointa(self, checkpointi: list[dict]) -> str:
        """Odabir checkpointa za nastavak.

        Args:
            checkpointi: Lista checkpointova.

        Returns:
            "resume:<index>" s indeksom odabranog checkpointa, ili "x" za povratak.
        """
        if not checkpointi:
            print("Nema dostupnih checkpointova.")
            return "x"

        print("\nOdaberite checkpoint za nastavak:")
        for i, cp in enumerate(checkpointi, 1):
            title = cp.get("book_title", "Nepoznato")
            progress = f"{cp.get('current_segment', 0)}/{cp.get('total_segments', 0)}"
            print(f"  {i}. {title} — {progress}")

        odgovor_raw = self._safe_input("\nOdabir (ili X za povratak): ")
        if odgovor_raw is None:
            return "x"
        odgovor = odgovor_raw.strip().lower()
        if odgovor == "x":
            return "x"
        if odgovor.isdigit():
            idx = int(odgovor) - 1
            if 0 <= idx < len(checkpointi):
                return f"resume:{idx}"
        print("Nevažeći odabir.")
        return "x"

    def _test_prijevod(self) -> None:
        """TEST prijevod."""
        txt_datoteka = self._odaberi_fixed_datoteku("FAZA 3 — TEST PRIJEVOD (ODABIR DATOTEKE)")
        if not txt_datoteka:
            return

        knjiga_dir = txt_datoteka.parent

        print(f"\nTEST prijevod: {knjiga_dir.name}/{txt_datoteka.name}")
        print(f"Granularnost: {self._opcije['granularnost']}, Količina: {self._opcije['kolicina']}, Header: {self._opcije['header']}")
        print()

        try:
            # Učitaj tekst
            with open(txt_datoteka, 'r', encoding='utf-8') as f:
                tekst = f.read()

            # Učitaj book config ako postoji
            config_putanja = knjiga_dir / "config.yaml"
            book_config = None
            if config_putanja.exists():
                with open(config_putanja, 'r', encoding='utf-8') as f:
                    book_config = yaml.safe_load(f)

            # Postavi knjigu i učitaj memoriju ([ime_knjige]_memorija.json)
            self._translator.postavi_knjigu(str(knjiga_dir), book_config)

            # Pozovi translator za TEST prijevod
            prijevod = self._translator.prevedi_test(
                tekst,
                granularnost=self._opcije["granularnost"],
                kolicina=self._opcije["kolicina"],
                header=self._opcije["header"]
            )

            # Spremi TEST prijevod u work/translated/<Knjiga>/
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            naziv = f"{txt_datoteka.stem}_test_{timestamp}.txt"

            translated_book_dir = self._fm.ensure_dir(
                self._fm.book_output_dir(
                    knjiga_dir.name,
                    book_config.get("author", "Unknown") if book_config else "Unknown"
                ),
                suffix_if_exists=False,
            )

            izlazna_putanja = self._fm.ensure_file_path(
                translated_book_dir / naziv,
                suffix_if_exists=True,
            )

            with open(izlazna_putanja, 'w', encoding='utf-8') as f:
                f.write(prijevod)

            print(f"TEST prijevod spremljen: {izlazna_putanja.name}")

            # Spremi last_test za BRZI TEST
            self._cp.spremi_last_test({
                "book_title": knjiga_dir.name,
                "granularnost": self._opcije["granularnost"],
                "count": self._opcije["kolicina"],
                "header": self._opcije["header"],
                "timestamp": timestamp
            })

        except Exception as e:
            print(f"Greška pri TEST prijevodu: {e}")

        ack = self._safe_input("\nPritisnite Enter za povratak...")

    def _produkcijski_prijevod(self) -> None:
        """Produkcijski prijevod."""
        txt_datoteka = self._odaberi_fixed_datoteku("FAZA 3 — PRODUKCIJSKI PRIJEVOD (ODABIR DATOTEKE)")
        if not txt_datoteka:
            return

        knjiga_dir = txt_datoteka.parent

        print(f"\nProdukcijski prijevod: {knjiga_dir.name}/{txt_datoteka.name}")
        print(f"Granularnost: {self._opcije['granularnost']}")
        print()

        try:
            # Učitaj tekst
            with open(txt_datoteka, 'r', encoding='utf-8') as f:
                tekst = f.read()

            # Učitaj book config ako postoji
            config_putanja = knjiga_dir / "config.yaml"
            book_config = None
            if config_putanja.exists():
                with open(config_putanja, 'r', encoding='utf-8') as f:
                    book_config = yaml.safe_load(f)

            # Postavi knjigu i učitaj memoriju ([ime_knjige]_memorija.json)
            self._translator.postavi_knjigu(str(knjiga_dir), book_config)

            # Spremi produkcijski prijevod u work/translated/<Knjiga>/
            # Ista mapa knjige; datoteka dobiva _001/_002 ako već postoji
            translated_book_dir = self._fm.ensure_dir(
                self._fm.book_output_dir(
                    knjiga_dir.name,
                    book_config.get("author", "Unknown") if book_config else "Unknown"
                ),
                suffix_if_exists=False,
            )

            izlazna_putanja = self._fm.ensure_file_path(
                translated_book_dir / f"{knjiga_dir.name}.txt",
                suffix_if_exists=True,
            )

            # Pozovi translator za produkcijski prijevod
            prijevod, je_prekinuto = self._translator.prevedi_knjigu(
                tekst,
                output_path=str(izlazna_putanja),
                book_id=f"{knjiga_dir.name}_fixed",
                granularnost=self._opcije["granularnost"]
            )

            if je_prekinuto:
                print(f"Produkcijski prijevod prekinut - prevedeni dio spremljen: {izlazna_putanja}")
            else:
                print(f"Produkcijski prijevod spremljen: {izlazna_putanja}")

        except Exception as e:
            print(f"Greška pri produkcijskom prijevodu: {e}")

        ack = self._safe_input("\nPritisnite Enter za povratak...")
