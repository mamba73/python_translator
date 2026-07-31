"""
app/menu.py — CLI sučelje s kursorskom navigacijom
Ref: doc/README_TechDoc.md §6
"""

from __future__ import annotations

import sys
import logging
import os
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
from app.document_processor import DocumentProcessor
from app.text_cleaner import TextCleaner
from app.translator import Translator
from app.tts_engine import TTSEngine
from app.file_manager import FileManager


class CursorMenu:
    """Kursorska navigacija za izbornike."""

    @staticmethod
    def odabir_iz_liste(opcije: list[str], naslov: str = "", allow_y: bool = False,
                        allow_r: bool = False) -> str:
        """Kursorski odabir iz liste (↑↓ + Enter/Space).

        Args:
            opcije: Lista opcija za prikaz.
            naslov: Naslov za prikaz.
            allow_y: Dozvoli Y kao odgovor.
            allow_r: Dozvoli R kao odgovor.

        Returns:
            Odabir korisnika.
        """
        if sys.platform == "win32" and _MSVCRT_AVAILABLE:
            return CursorMenu._odabir_windows(opcije, naslov, allow_y, allow_r)
        elif _CURSES_AVAILABLE:
            return CursorMenu._odabir_linux(opcije, naslov, allow_y, allow_r)
        else:
            # Fallback na input()
            return CursorMenu._odabir_fallback(opcije, naslov, allow_y, allow_r)

    @staticmethod
    def _odabir_windows(opcije: list[str], naslov: str, allow_y: bool, allow_r: bool) -> str:
        """Windows kursorski odabir koristeći msvcrt."""
        trenutni = 0

        while True:
            ocisti_ekran()
            if naslov:
                print(naslov)
                print()

            for i, opc in enumerate(opcije):
                if i == trenutni:
                    print(f"> {opc} <")
                else:
                    print(f"  {opc}")

            print()
            if allow_y:
                print("[Y] - BRZI TEST")
            if allow_r:
                print("[R] - Nastavi od checkpointa")
            print("[X] - Izlaz")
            print("\nKoristite strelice za navigaciju, Enter za odabir")

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
    def _odabir_linux(opcije: list[str], naslov: str, allow_y: bool, allow_r: bool) -> str:
        """Linux kursorski odabir koristeći curses."""
        def wrapper(stdscr):
            curses.curs_set(0)
            stdscr.keypad(True)
            trenutni = 0

            while True:
                stdscr.clear()
                if naslov:
                    stdscr.addstr(naslov + "\n\n")

                for i, opc in enumerate(opcije):
                    if i == trenutni:
                        stdscr.addstr(f"> {opc} <\n")
                    else:
                        stdscr.addstr(f"  {opc}\n")

                stdscr.addstr("\n")
                if allow_y:
                    stdscr.addstr("[Y] - BRZI TEST\n")
                if allow_r:
                    stdscr.addstr("[R] - Nastavi od checkpointa\n")
                stdscr.addstr("[X] - Izlaz\n")

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
    def _odabir_fallback(opcije: list[str], naslov: str, allow_y: bool, allow_r: bool) -> str:
        """Fallback na input() ako kursorska navigacija nije dostupna."""
        if naslov:
            print(naslov)
            print()

        for i, opc in enumerate(opcije, 1):
            print(f"  {i}. {opc}")
        print()

        if allow_y:
            print("[Y] - BRZI TEST")
        if allow_r:
            print("[R] - Nastavi od checkpointa")
        print("[X] - Izlaz")

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
        self._text_cleaner = TextCleaner(config, self._fm)
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

        odabir = CursorMenu.odabir_iz_liste(opcije, "Dynamic Book Translator v0.4.0",
                                            allow_y=last_test is not None,
                                            allow_r=len(checkpointi) > 0)

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

        # Pronađi datoteke rekurzivno s metadatima
        datoteke_info = self._pronadi_datoteke_s_metadatima(input_dir)

        if not datoteke_info:
            print("Nema datoteka u work/input/ (uključujući poddirektorije).")
            input("Pritisnite Enter za povratak...")
            return

        # Prikaz s metadatima
        print(f"Pronađeno: {len(datoteke_info)} datoteka\n")
        for i, info in enumerate(datoteke_info, 1):
            rel_path = info["path"].relative_to(input_dir)
            print(f"  {i}. [{info['type']}] {rel_path} ({info['size']})")

        # Batch odabir
        odabrane = self._batch_odabir([str(info["path"].relative_to(input_dir)) for info in datoteke_info], "Odaberite datoteke za konverziju (ili X za povratak)")

        if odabrane == "x":
            return

        if not odabrane:
            print("Nije odabrana nijedna datoteka.")
            input("Pritisnite Enter za povratak...")
            return

        print(f"\nOdabrano: {len(odabrane)} datoteka")
        print("Konverzija u tijeku...")

        # Konvertiraj odabrane datoteke
        for idx in odabrane:
            datoteka_info = datoteke_info[idx]
            putanja = datoteka_info["path"]
            rel_path = putanja.relative_to(input_dir)

            print(f"\nKonverzija: {rel_path}")

            try:
                # Učitaj tekst iz dokumenta
                tekst = self._doc_proc.ucitaj_izvorni_tekst(str(putanja))

                # Spremi u output direktorij
                output_dir = Path(self._cfg["directories"]["output"])
                output_dir.mkdir(parents=True, exist_ok=True)

                # Kreiraj naziv izlazne datoteke
                naziv = putanja.stem + ".txt"
                izlazna_putanja = output_dir / naziv

                # Spremi tekst
                with open(izlazna_putanja, 'w', encoding='utf-8') as f:
                    f.write(tekst)

                print(f"  -> Spremljeno: {izlazna_putanja}")

            except Exception as e:
                print(f"  -> Greška: {e}")

        print("\nKonverzija završena.")
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

        # Pronađi .txt datoteke ili direktorije knjiga
        txt_datoteke = list(output_dir.glob("*.txt"))
        knjige_dir = [d for d in output_dir.iterdir() if d.is_dir()]

        if txt_datoteke:
            # Ako postoje .txt datoteke, prikaži ih
            print("Pronađene .txt datoteke:")
            for i, txt in enumerate(txt_datoteke, 1):
                print(f"  {i}. {txt.name}")

            odabrane = self._batch_odabir([t.name for t in txt_datoteke], "Odaberite datoteke za čišćenje (ili X za povratak)")

            if odabrane == "x":
                return

            if not odabrane:
                print("Nije odabrana nijedna datoteka.")
                input("Pritisnite Enter za povratak...")
                return

            print(f"\nOdabrano: {len(odabrane)} datoteka")
            print("Čišćenje u tijeku...")

            for idx in odabrane:
                txt_datoteka = txt_datoteke[idx]
                print(f"\nČišćenje: {txt_datoteka.name}")

                try:
                    # Učitaj tekst
                    with open(txt_datoteka, 'r', encoding='utf-8') as f:
                        tekst = f.read()

                    # Očisti dokument
                    ocisceni_tekst = self._text_cleaner.ocisti_dokument(tekst, txt_datoteka.stem)

                    # Spremi očišćeni tekst kao novu datoteku s [fixed] sufiksom
                    naziv = txt_datoteka.stem + "[fixed]" + txt_datoteka.suffix
                    izlazna_putanja = output_dir / naziv
                    with open(izlazna_putanja, 'w', encoding='utf-8') as f:
                        f.write(ocisceni_tekst)

                    print(f"  -> Očišćeno: {izlazna_putanja.name}")

                    # Kreiraj memoriju
                    memorija = self._text_cleaner.kreiraj_memoriju(ocisceni_tekst)
                    memorija_putanja = output_dir / f"{txt_datoteka.stem}_memory.json"
                    import json
                    with open(memorija_putanja, 'w', encoding='utf-8') as f:
                        json.dump(memorija, f, indent=2, ensure_ascii=False)
                    print(f"  -> Memorija: {memorija_putanja.name}")

                    # Kreiraj book config
                    book_config = self._text_cleaner.kreiraj_book_config(txt_datoteka.stem, "Autor")
                    config_putanja = output_dir / f"{txt_datoteka.stem}_config.yaml"
                    import yaml
                    with open(config_putanja, 'w', encoding='utf-8') as f:
                        yaml.dump(book_config, f, default_flow_style=False, allow_unicode=True)
                    print(f"  -> Config: {config_putanja.name}")

                except Exception as e:
                    print(f"  -> Greška: {e}")

        elif knjige_dir:
            # Ako postoje direktoriji, koristi originalnu logiku
            odabrane = self._batch_odabir([d.name for d in knjige_dir], "Odaberite knjige za čišćenje (ili X za povratak)")

            if odabrane == "x":
                return

            if not odabrane:
                print("Nije odabrana nijedna knjiga.")
                input("Pritisnite Enter za povratak...")
                return

            print(f"\nOdabrano: {len(odabrane)} knjiga")
            print("Čišćenje u tijeku...")

            for idx in odabrane:
                knjiga_dir = knjige_dir[idx]
                txt_datoteke = list(knjiga_dir.glob("*.txt"))

                if not txt_datoteke:
                    print(f"\n{knjiga_dir.name}: Nema .txt datoteka za čišćenje.")
                    continue

                for txt_datoteka in txt_datoteke:
                    print(f"\nČišćenje: {knjiga_dir.name}/{txt_datoteka.name}")

                    try:
                        # Učitaj tekst
                        with open(txt_datoteka, 'r', encoding='utf-8') as f:
                            tekst = f.read()

                        # Očisti dokument
                        ocisceni_tekst = self._text_cleaner.ocisti_dokument(tekst, knjiga_dir.name)

                        # Spremi očišćeni tekst kao novu datoteku s [fixed] sufiksom
                        naziv = txt_datoteka.stem + "[fixed]" + txt_datoteka.suffix
                        izlazna_putanja = knjiga_dir / naziv
                        with open(izlazna_putanja, 'w', encoding='utf-8') as f:
                            f.write(ocisceni_tekst)

                        print(f"  -> Očišćeno: {izlazna_putanja.name}")

                        # Kreiraj memoriju
                        memorija = self._text_cleaner.kreiraj_memoriju(ocisceni_tekst)
                        memorija_putanja = knjiga_dir / "memory.json"
                        import json
                        with open(memorija_putanja, 'w', encoding='utf-8') as f:
                            json.dump(memorija, f, indent=2, ensure_ascii=False)
                        print(f"  -> Memorija: {memorija_putanja.name}")

                        # Kreiraj book config
                        book_config = self._text_cleaner.kreiraj_book_config(knjiga_dir.name, "Autor")
                        config_putanja = knjiga_dir / "config.yaml"
                        import yaml
                        with open(config_putanja, 'w', encoding='utf-8') as f:
                            yaml.dump(book_config, f, default_flow_style=False, allow_unicode=True)
                        print(f"  -> Config: {config_putanja.name}")

                    except Exception as e:
                        print(f"  -> Greška: {e}")
        else:
            print("Nema .txt datoteka ili knjiga u work/output/")
            input("Pritisnite Enter za povratak...")
            return

        print("\nČišćenje završeno.")
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

            odabir = CursorMenu.odabir_iz_liste(opcije, "FAZA 3 — PREVOĐENJE")

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

            odabir = CursorMenu.odabir_iz_liste(opcije, "OPCIJE PREVOĐENJA")

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

        odabir = CursorMenu.odabir_iz_liste(opcije, "FAZA 4 — TTS SINTEZA")

        if odabir == "x":
            return

        # Odabir knjige za TTS
        translated_dir = Path(self._cfg["directories"]["translated"])
        if not translated_dir.exists():
            print("Direktorij work/translated/ ne postoji.")
            input("Pritisnite Enter za povratak...")
            return

        knjige = [d for d in translated_dir.iterdir() if d.is_dir()]

        if not knjige:
            print("Nema knjiga u work/translated/")
            input("Pritisnite Enter za povratak...")
            return

        odabrane = self._batch_odabir([d.name for d in knjige], "Odaberite knjigu za TTS sintezu (ili X za povratak)")

        if odabrane == "x":
            return

        if not odabrane or len(odabrane) != 1:
            print("Odaberite točno jednu knjigu za TTS sintezu.")
            input("Pritisnite Enter za povratak...")
            return

        knjiga_dir = knjige[odabrane[0]]
        txt_datoteke = list(knjiga_dir.glob("*.txt"))

        if not txt_datoteke:
            print(f"Nema .txt datoteka u {knjiga_dir.name}")
            input("Pritisnite Enter za povratak...")
            return

        txt_datoteka = txt_datoteke[0]
        print(f"\nTTS sinteza: {knjiga_dir.name}/{txt_datoteka.name}")
        print(f"Način: {'Zasebne datoteke' if odabir == '1' else 'Jedna datoteka'}")
        print()

        try:
            # Učitaj tekst
            with open(txt_datoteka, 'r', encoding='utf-8') as f:
                tekst = f.read()

            # Učitaj book config ako postoji
            import yaml
            config_putanja = knjiga_dir / "config.yaml"
            book_config = None
            if config_putanja.exists():
                with open(config_putanja, 'r', encoding='utf-8') as f:
                    book_config = yaml.safe_load(f)

            # Kreiraj audiobook direktorij
            audiobook_dir = self._fm.audiobook_dir(knjiga_dir.name, book_config.get("author", "Unknown") if book_config else "Unknown")
            audiobook_dir.mkdir(parents=True, exist_ok=True)

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

        input("\nPritisnite Enter za povratak...")

    # -----------------------------------------------------------------------
    # Pomoćne metode
    # -----------------------------------------------------------------------

    def _pronadi_datoteke_s_metadatima(self, dir_path: Path) -> list[dict[str, Any]]:
        """Pronalazi datoteke rekurzivno s metadatima o tipu.

        Args:
            dir_path: Početni direktorij za pretragu.

        Returns:
            Lista rječnika s path, type, size.
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

                # Format veličine
                size_bytes = path.stat().st_size
                if size_bytes < 1024:
                    size_str = f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    size_str = f"{size_bytes / 1024:.1f} KB"
                else:
                    size_str = f"{size_bytes / (1024 * 1024):.1f} MB"

                datoteke_info.append({
                    "path": path,
                    "type": file_type,
                    "size": size_str
                })

        return datoteke_info

    def _batch_odabir(self, stavke: list[str], naslov: str) -> list[int] | str:
        """Batch odabir: 1, 1,3,5, 1-5, *, X.

        Args:
            stavke: Lista stavki za odabir.
            naslov: Naslov za prikaz.

        Returns:
            Lista indeksa odabranih stavki ili "x" za povratak.
        """
        print(f"{naslov}:")
        print()

        for i, stavka in enumerate(stavke, 1):
            print(f"  {i}. {stavka}")
        print()

        print("Unesite brojeve (npr. 1,3,5 ili 1-5 ili * za sve, ili X za povratak):")
        unos = input("> ").strip().lower()

        if unos == "x":
            return "x"
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
        ocisti_ekran()
        print("=" * 70)
        print("TEST PRIJEVOD")
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

        # Odabir knjige
        odabrane = self._batch_odabir([d.name for d in knjige], "Odaberite knjigu za TEST prijevod (ili X za povratak)")

        if odabrane == "x":
            return

        if not odabrane or len(odabrane) != 1:
            print("Odaberite točno jednu knjigu za TEST prijevod.")
            input("Pritisnite Enter za povratak...")
            return

        knjiga_dir = knjige[odabrane[0]]
        txt_datoteke = list(knjiga_dir.glob("*.txt"))

        if not txt_datoteke:
            print(f"Nema .txt datoteka u {knjiga_dir.name}")
            input("Pritisnite Enter za povratak...")
            return

        txt_datoteka = txt_datoteke[0]
        print(f"\nTEST prijevod: {knjiga_dir.name}/{txt_datoteka.name}")
        print(f"Granularnost: {self._opcije['granularnost']}, Količina: {self._opcije['kolicina']}, Header: {self._opcije['header']}")
        print()

        try:
            # Učitaj tekst
            with open(txt_datoteka, 'r', encoding='utf-8') as f:
                tekst = f.read()

            # Pozovi translator za TEST prijevod
            prijevod = self._translator.prevedi_test(
                tekst,
                granularnost=self._opcije["granularnost"],
                kolicina=self._opcije["kolicina"],
                header=self._opcije["header"]
            )

            # Spremi TEST prijevod
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            naziv = f"{txt_datoteka.stem}_test_{timestamp}.txt"
            izlazna_putanja = knjiga_dir / naziv

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

        input("\nPritisnite Enter za povratak...")

    def _produkcijski_prijevod(self) -> None:
        """Produkcijski prijevod."""
        ocisti_ekran()
        print("=" * 70)
        print("PRODUKCIJSKI PRIJEVOD")
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

        # Odabir knjige
        odabrane = self._batch_odabir([d.name for d in knjige], "Odaberite knjigu za produkcijski prijevod (ili X za povratak)")

        if odabrane == "x":
            return

        if not odabrane or len(odabrane) != 1:
            print("Odaberite točno jednu knjigu za produkcijski prijevod.")
            input("Pritisnite Enter za povratak...")
            return

        knjiga_dir = knjige[odabrane[0]]
        txt_datoteke = list(knjiga_dir.glob("*.txt"))

        if not txt_datoteke:
            print(f"Nema .txt datoteka u {knjiga_dir.name}")
            input("Pritisnite Enter za povratak...")
            return

        txt_datoteka = txt_datoteke[0]
        print(f"\nProdukcijski prijevod: {knjiga_dir.name}/{txt_datoteka.name}")
        print(f"Granularnost: {self._opcije['granularnost']}")
        print()

        try:
            # Učitaj tekst
            with open(txt_datoteka, 'r', encoding='utf-8') as f:
                tekst = f.read()

            # Učitaj book config ako postoji
            import yaml
            config_putanja = knjiga_dir / "config.yaml"
            book_config = None
            if config_putanja.exists():
                with open(config_putanja, 'r', encoding='utf-8') as f:
                    book_config = yaml.safe_load(f)

            # Pozovi translator za produkcijski prijevod
            prijevod = self._translator.prevedi_knjigu(
                tekst,
                book_title=knjiga_dir.name,
                book_config=book_config,
                granularnost=self._opcije["granularnost"]
            )

            # Spremi produkcijski prijevod
            naziv = f"{txt_datoteka.stem}.txt"
            izlazna_putanja = knjiga_dir / naziv

            with open(izlazna_putanja, 'w', encoding='utf-8') as f:
                f.write(prijevod)

            print(f"Produkcijski prijevod spremljen: {izlazna_putanja.name}")

        except Exception as e:
            print(f"Greška pri produkcijskom prijevodu: {e}")

        input("\nPritisnite Enter za povratak...")
