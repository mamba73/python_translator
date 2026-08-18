"""
app/utils.py — Pomoćne funkcije za čišćenje, sanitizaciju i UI
Ref: doc/README_TechDoc.md §22
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from typing import Any

_CHAR_MAP = str.maketrans("čćšđžŽŠĐČĆ", "ccsdzZSDCC")


def sanitiziraj_naziv(naziv: str, separator: str = "-") -> str:
    """Uklanja dijakritike, pretvara razmake u separator i priprema naziv za datoteke.

    Args:
        naziv: Originalni naziv koji može sadržavati specijalne znakove.
        separator: Zamjena za razmake (default: '-').

    Returns:
        Sanitizirani naziv spreman za korištenje u datotečnom sustavu.
    """
    naziv = naziv.translate(_CHAR_MAP)
    naziv = re.sub(r'[^\w\s-]', '', naziv).strip().lower()
    naziv = re.sub(r'\s+', separator, naziv)
    return naziv


# Module-level state for ETA calculation — prati vrijeme početka i ukupno
# segmenata kako bi se izračunala prosječna brzina i preostalo vrijeme.
_progress_start_time: float | None = None
_progress_total: int | None = None


def _format_eta(eta_seconds: float) -> str:
    """Formatira sekunde u čitljiv ETA string (npr. '5m 30s', '1h 15m', '< 1min').

    Uključuje strogu zaštitu protiv negativnih vrijednosti — ako je ETA
    manji od nule, vraća 'U završnoj fazi'.

    Args:
        eta_seconds: Preostalo vrijeme u sekundama.

    Returns:
        Formatirani ETA string.
    """
    # STROGA zaštita: ETA ne smije biti negativan
    if eta_seconds < 0:
        eta_seconds = 0

    if eta_seconds < 60:
        if eta_seconds < 1:
            return "U završnoj fazi"
        return f"< 1min"
    elif eta_seconds < 3600:
        minute = int(eta_seconds // 60)
        sekunde = int(eta_seconds % 60)
        return f"{minute}m {sekunde}s"
    else:
        sati = int(eta_seconds // 3600)
        minute = int((eta_seconds % 3600) // 60)
        return f"{sati}h {minute}m"


def prikazi_progres(
    trenutno: int,
    ukupno: int,
    tekst_statusa: str = "",
    dodatno: str = ""
) -> None:
    """Iscrtava dinamički progress bar u istom retku terminala.

    Prikazuje postotak, traku napretka, detaljan status (npr. broj riječi/paragraf),
    te ETA (procijenjeno preostalo vrijeme) izračunato na temelju prosječne brzine
    obrade segmenata i proteklog vremena.

    ETA zaštita: ako izračunati ETA ode ispod nule, prikazuje se 'U završnoj fazi'
    umjesto negativne vrijednosti.

    Nakon svakog poziva poziva sys.stdout.flush() kako bi se osiguralo ažuriranje
    u stvarnom vremenu.

    Args:
        trenutno: Trenutni broj obrađenih jedinica.
        ukupno: Ukupan broj jedinica za obradu.
        tekst_statusa: Opisni tekst statusa (npr. "Odlomak: 5/20").
        dodatno: Dodatne informacije (npr. "riječi: 12345/50000 (24%)").
    """
    global _progress_start_time, _progress_total

    if ukupno <= 0:
        return

    # Resetiraj ETA tracking kada se ukupno promijeni (novi zadatak)
    if _progress_total != ukupno or _progress_start_time is None:
        _progress_start_time = time.time()
        _progress_total = ukupno

    sirina_bara = 30
    procent = float(trenutno) / ukupno
    ispunjeno = int(sirina_bara * procent)
    bar = "█" * ispunjeno + "░" * (sirina_bara - ispunjeno)

    dio_procenta = f"{int(procent * 100)}%"

    # ETA izračun: na temelju proteklog vremena i broja obrađenih segmenata
    eta_str = ""
    if _progress_start_time is not None and trenutno > 0:
        elapsed = time.time() - _progress_start_time
        if trenutno > 1 and elapsed > 0:
            # Prosječna brzina: segmenti po sekundi
            rate = trenutno / elapsed
            if rate > 0:
                remaining_segments = ukupno - trenutno
                eta_seconds = remaining_segments / rate
                # STROGA zaštita: ETA ne smije biti negativan
                if eta_seconds < 0:
                    eta_seconds = 0
                eta_str = f" | ETA: {_format_eta(eta_seconds)}"

    if dodatno:
        linija = f"[Progres] : [{bar}] {dio_procenta} | {tekst_statusa} | {dodatno}{eta_str}"
    else:
        linija = f"[Progres] : [{bar}] {dio_procenta} | {tekst_statusa}{eta_str}"

    # Progress bar se ispisuje u ISTOM retku terminala koristeći carriage
    # return (\r) — vraća kursor na početak retka i prepisuje prethodni
    # ispis umjesto da otvara nove redove. Tako terminal ostaje čist.
    #
    # Za WebSocket streaming (web GUI): pišemo liniju u app.log datoteku
    # (FlushFileHandler flusha odmah) u standardnom formatu — WebSocket
    # čita liniju i šalje je frontend-u koji je parsira.
    import logging
    import sys
    from datetime import datetime
    from app.logger import get_session_log_dir

    # 1) Terminal ispis — carriage return za refresh iste linije
    sys.stdout.write(f"\r{linija}    ")
    sys.stdout.flush()

    # 2) app.log zapis — za WebSocket streaming (novi red, standardni format)
    #    Pišemo direktno u datoteku kako bismo izbjegli logging.info() koji
    #    bi duplicirao ispis na stdout (preko StreamHandler) i stvorio šum.
    session_dir = get_session_log_dir()
    if session_dir:
        log_file = session_dir / "app.log"
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                ts = datetime.now().strftime("%H:%M:%S")
                f.write(f"{ts} INFO {linija}\n")
                f.flush()
        except Exception:
            pass
    else:
        # Fallback: ako sesija nije inicijalizirana, koristi logging.info()
        logging.info(linija)


def ocisti_ekran() -> None:
    """Čisti terminal na Windows i Unix sustavima koristeći siguran subprocess poziv."""
    subprocess.run(
        "cls" if os.name == "nt" else "clear",
        shell=True,
        capture_output=True
    )


def detektiraj_x_tipku() -> bool:
    """Non-blocking detekcija X tipke za prekid prevođenja.

    Returns:
        True ako je pritisnuta X tipka, inače False.
    """
    try:
        if sys.platform == "win32":
            import msvcrt
            if msvcrt.kbhit():
                tipka = msvcrt.getch().decode('ascii', errors='ignore').upper()
                return tipka == 'X'
        else:
            import select
            if select.select([sys.stdin], [], [], 0)[0]:
                tipka = sys.stdin.read(1).upper()
                return tipka == 'X'
    except Exception:
        pass
    return False


def unificiraj_navodnike(tekst: str) -> str:
    """Pretvara sve varijante tipografskih navodnika u standardne ravne dvostruke navodnike.

    Konvertira: „ ”, " ", « », ‹ ›, ‚ ', "" (mixed) u " ".
    Ovo je ključno za ispravno prepoznavanje dijaloga u TTS modulu.

    Args:
        tekst: Ulazni tekst s bilo kojom vrstom navodnika.

    Returns:
        Tekst sa standardiziranim navodnicima (").
    """
    # Mapa svih mogućih otvarajućih/zatvarajućih navodnika
    # Lijevi/desni tipografski (engleski)
    tekst = tekst.replace('\u201c', '"')  # "
    tekst = tekst.replace('\u201d', '"')  # "
    # Donji/desni (njemački/hrvatski stil)
    tekst = tekst.replace('\u201e', '"')  # „
    tekst = tekst.replace('\u201f', '"')  # ‟
    # Jednostruki tipografski
    tekst = tekst.replace('\u2018', "'")  # '
    tekst = tekst.replace('\u2019', "'")  # '
    tekst = tekst.replace('\u201a', "'")  # ‚
    tekst = tekst.replace('\u201b', "'")  # ‛
    # Francuski/španjolski (guillemets)
    tekst = tekst.replace('\u00ab', '"')  # «
    tekst = tekst.replace('\u00bb', '"')  # »
    tekst = tekst.replace('\u2039', '"')  # ‹
    tekst = tekst.replace('\u203a', '"')  # ›
    # Ostali rijetki
    tekst = tekst.replace('\u2e42', '"')  # ⹂
    tekst = tekst.replace('\u2012', '-')  # ‒ (en-dash)
    tekst = tekst.replace('\u2013', '-')  # –
    tekst = tekst.replace('\u2014', '--')  # —
    tekst = tekst.replace('\u2015', '--')  # ―

    return tekst


def ocisti_leaked_prijevod(tekst: str) -> str:
    """Uklanja sve procurjele fraze iz prijevoda koje model može dodati.

    Briše uvodne fraze poput 'Translation:', 'Here is the translation:',
    'Croatian translation:', 'Translated text:' itd.

    Args:
        tekst: Sirovi izlaz iz LM Studio API-ja.

    Returns:
        Očišćeni tekst bez procurjelih fraza.
    """
    # Uzorci za uklanjanje - case insensitive
    uzorci = [
        r'^(Translation|Translated text|Croatian translation|Here is the translation|'
        r'Here is the Croatian translation|Output|Result|Response)'
        r'[\s]*:[\s]*',
        r'^["\']?(Translation|Translated text|Croatian translation)["\']?\s*:?\s*',
        r'^Here\s+is\s+the\s+(Croatian\s+)?translation\s*:?\s*',
        r'^The\s+(Croatian\s+)?translation\s+(of\s+the\s+(given\s+)?paragraph\s+)?is\s*:?\s*',
        r'^["\'](.*?)["\']\s+translates?\s+to\s+["\']',
        r'^In\s+Croatian\s*:?\s*',
        r'^Croatian\s*:?\s*',
        r'^Translation\s+of\s+the\s+(given\s+)?(English\s+)?paragraph\s*:?\s*',
    ]

    for uzorak in uzorci:
        tekst = re.sub(uzorak, '', tekst, flags=re.IGNORECASE)

    # Ne uklanjaj navodnike na početku/završetku — oni često pripadaju
    # stvarnom dijalogu (npr. "U čemu je, jebote, problem?" upitao je.).
    tekst = re.sub(r'^\s+', '', tekst)
    tekst = re.sub(r'\s+$', '', tekst)

    return tekst.strip()
