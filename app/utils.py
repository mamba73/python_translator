"""
app/utils.py — Pomoćne funkcije za čišćenje, sanitizaciju i UI
Ref: doc/README_TechDoc.md §22
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
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


def prikazi_progres(
    trenutno: int,
    ukupno: int,
    tekst_statusa: str = "",
    dodatno: str = ""
) -> None:
    """Iscrtava dinamički progress bar u istom retku terminala.

    Prikazuje postotak, traku napretka, i detaljan status (npr. broj riječi/paragraf).
    Nakon svakog poziva poziva sys.stdout.flush() kako bi se osiguralo ažuriranje
    u stvarnom vremenu.

    Args:
        trenutno: Trenutni broj obrađenih jedinica.
        ukupno: Ukupan broj jedinica za obradu.
        tekst_statusa: Opisni tekst statusa (npr. "Odlomak: 5/20").
        dodatno: Dodatne informacije (npr. "riječi: 12345/50000 (24%)").
    """
    if ukupno <= 0:
        return
    sirina_bara = 30
    procent = float(trenutno) / ukupno
    ispunjeno = int(sirina_bara * procent)
    bar = "█" * ispunjeno + "░" * (sirina_bara - ispunjeno)

    dio_procenta = f"{int(procent * 100)}%"
    if dodatno:
        linija = f"[Progres] : [{bar}] {dio_procenta} | {tekst_statusa} | {dodatno}"
    else:
        linija = f"[Progres] : [{bar}] {dio_procenta} | {tekst_statusa}"

    # UVIJEK logiraj progress liniju u app.log (FlushFileHandler flusha odmah)
    # kako bi WebSocket u web_server.py mogao streamati ažuriranja u stvarnom
    # vremenu na frontend. U CLI modu logging StreamHandler ispisuje istu
    # liniju na stdout — progress bar tako radi u oba okruženja.
    #
    # NAPOMENA: Ne koristimo sys.stdout.write() s \r jer u FastAPI async
    # kontekstu (uvicorn) stdout output nije pouzdano flushan — pojavljuje
    # se tek nakon što se cijeli prijevod završi.
    import logging
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

    # Također ukloni bilo kakve ostatke poput "..." na početku
    tekst = re.sub(r'^[\s"\']+', '', tekst)
    tekst = re.sub(r'[\s"\']+$', '', tekst)

    return tekst.strip()
