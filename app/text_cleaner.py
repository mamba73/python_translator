"""
app/text_cleaner.py — Čišćenje tehničkog šuma iz ulaznih tekstualnih datoteka.

Ovaj modul prima sirove .txt datoteke i uklanja:
  - HTML entitete (&nbsp;, \xa0, <br>, <br/>, itd.)
  - Sve HTML/XML tagove
  - Ponavljajuće headere i footere (sistemske putanje, brojeve stranica, vremenske žigove)
  - Višestruke prazne redove (sažima na točno jedan prazan red između odlomaka)
  - Prekidane rečenice unutar odlomka (spaja u kontinuirani redak)
"""

import os
import re
from pathlib import Path
from typing import Optional, List


def ukloni_sistemski_i_paginacijski_sum(tekst: str) -> str:
    """
    Kirurški uklanja specifične file:// linkove, vremenske oznake, 
    te detektira i čisti ponavljajuće headere/footere s brojevima stranica.
    """
    if not tekst:
        return ""

    # 1. Čišćenje specifičnih lokalnih HTML/TXT dump URL-ova s timestampom i brojem stranica
    # Primjer: file:///F|/rah/Herbert,%20Frank/Dune%201%20-%20Dune.txt (221 of 274) [1/14/03 7:28:46 PM]
    tekst = re.sub(r'file:///.*?\.txt\s*\(\d+\s+of\s+\d+\)\s*\[.*?\]', '', tekst, flags=re.IGNORECASE)
    
    # 2. Uklanjanje čistih file URL-ova bez zagrada koji se ponavljaju u idućem retku
    tekst = re.sub(r'file:///.*?\.txt', '', tekst, flags=re.IGNORECASE)

    # 3. Uklanjanje agresivnih separator linija koje razdvajaju stranice u starim dumpovima
    # Primjer: ===========================
    tekst = re.sub(r'={5,}', '', tekst)
    tekst = re.sub(r'-{5,}', '', tekst)

    # 4. Dinamički algoritam za detekciju i uklanjanje ponavljajućih headera/footera i brojeva stranica
    # Razbijamo tekst na retke kako bismo analizirali uzorke na granicama stranica
    retci = tekst.split('\n')
    očišćeni_retci = []

    # Regex uzorci za uobičajene formate brojeva stranica (Page 1, - 1 -, [1], izolirani brojevi na dnu/vrhu)
    regex_stranica = [
        r'^\s*page\s+\d+\s*$',
        r'^\s*stranica\s+\d+\s*$',
        r'^\s*-\s*\d+\s*-\s*$',
        r'^\s*\[\s*\d+\s*\]\s*$',
        r'^\s*\d+\s+of\s+\d+\s*$',
        r'^\s*\d+\s*$'  # Samostalni izolirani broj u retku
    ]
    
    kompilirani_uzorci = [re.compile(patern, re.IGNORECASE) for patern in regex_stranica]

    for linija in retci:
        linija_strip = linija.strip()
        
        # Ako je redak prazan, preskoči brze provjere
        if not linija_strip:
            očišćeni_retci.append(linija)
            continue

        # Provjera poklapa li se redak s nekim od standardnih formata brojeva stranica
        je_broj_stranice = any(uzorak.match(linija_strip) for uzorak in kompilirani_uzorci)
        if je_broj_stranice:
            continue  # Preskačemo i eliminiramo taj redak

        očišćeni_retci.append(linija)

    return "\n".join(očišćeni_retci)


def ocisti_html_i_paragrafe(sirovi_tekst: str) -> str:
    """
    Čisti HTML entitete, tagove, tehnički šum stranica i normalizira višestruke prazne redove.
    Također pametno spaja rečenice prelomljene u stupce, ali čuva naslove poglavlja.
    """
    if not sirovi_tekst:
        return ""
    
    # 1. Prvo pokrećemo napredno čišćenje sistemskog šuma, file linkova i brojeva stranica
    tekst = ukloni_sistemski_i_paginacijski_sum(sirovi_tekst)
    
    # 2. Čišćenje HTML tagova kroz više redova (Multiline regex)
    tekst = re.sub(r'<[^>]+>', '', tekst, flags=re.DOTALL)
    
    # 3. Čišćenje specifičnih HTML entiteta i skrivenih razmaka
    tekst = tekst.replace('\xa0', ' ')
    tekst = tekst.replace(' ', ' ')
    tekst = re.sub(r'<br\s*/?>', '\n', tekst, flags=re.IGNORECASE)
    
    # 4. Normalizacija prijeloma redaka na Unix standard
    tekst = tekst.replace('\r\n', '\n').replace('\r', '\n')
    
    # 5. Razbijanje teksta na retke i micanje praznina s rubova
    retci = [linija.strip() for linija in tekst.split('\n')]
    
    očišćeni_odlomci = []
    trenutni_odlomak = []
    
    for linija in retci:
        if linija == "":
            # Ako imamo prazan red, ali rečenica u memoriji NE završava točkom,
            # to znači da je u pitanju umjetni PDF/HTML lom. Nastavi spajati.
            if trenutni_odlomak and not trenutni_odlomak[-1].endswith(('.', '?', '!', '"', '”', '-')):
                continue
            
            # Ako je rečenica stvarno gotova, zatvori odlomak
            if trenutni_odlomak:
                pun_odlomak = " ".join(trenutni_odlomak)
                pun_odlomak = re.sub(r'\s+', ' ', pun_odlomak).strip()
                pun_odlomak = re.sub(r'\s+([,.:;?!])', r'\1', pun_odlomak)
                očišćeni_odlomci.append(pun_odlomak)
                trenutni_odlomak = []
        else:
            # --- ZAŠTITA NASLOVA I SADRŽAJA KNJIGE ---
            # Ako redak prepoznamo kao naslov poglavlja ili je napisan isključivo VELIKIM SLOVIMA,
            # prisilno zatvaramo stari odlomak i otvaramo novi, kako ih ne bismo spojili u jednu liniju.
            je_naslov = linija.startswith(('Part', 'Chapter', 'Contents', 'Introduction', 'THE STORY')) or linija.isupper()
            
            if je_naslov:
                if trenutni_odlomak:
                    pun_odlomak = " ".join(trenutni_odlomak)
                    pun_odlomak = re.sub(r'\s+', ' ', pun_odlomak).strip()
                    pun_odlomak = re.sub(r'\s+([,.:;?!])', r'\1', pun_odlomak)
                    očišćeni_odlomci.append(pun_odlomak)
                trenutni_odlomak = [linija]
                continue

            # --- DETEKCIJA I SPAJANJE SLOMLJENIH REČENICA ---
            # Ako linija počinje malim slovom ili interpunkcijom, to je sigurno nastavak rečenice
            if trenutni_odlomak and (linija.islower() or linija.startswith((',', '.', ':', ';', '?', '!'))):
                if linija.startswith((',', '.', ':', ';', '?', '!')):
                    trenutni_odlomak[-1] = trenutni_odlomak[-1] + linija
                else:
                    trenutni_odlomak.append(linija)
            else:
                # Ako stari odlomak nije završio točkom, spoji bez obzira na veliko slovo (za imena poput Columbia)
                if trenutni_odlomak and not trenutni_odlomak[-1].endswith(('.', '?', '!', '"', '”', '-')):
                    trenutni_odlomak.append(linija)
                else:
                    # Počinje stvarni, novi odlomak teksta
                    if trenutni_odlomak:
                        pun_odlomak = " ".join(trenutni_odlomak)
                        pun_odlomak = re.sub(r'\s+', ' ', pun_odlomak).strip()
                        pun_odlomak = re.sub(r'\s+([,.:;?!])', r'\1', pun_odlomak)
                        očišćeni_odlomci.append(pun_odlomak)
                    trenutni_odlomak = [linija]
            
    # Zatvaranje zadnjeg odlomka nakon izlaska iz petlje
    if trenutni_odlomak:
        pun_odlomak = " ".join(trenutni_odlomak)
        pun_odlomak = re.sub(r'\s+', ' ', pun_odlomak).strip()
        pun_odlomak = re.sub(r'\s+([,.:;?!])', r'\1', pun_odlomak)
        očišćeni_odlomci.append(pun_odlomak)
        
    # Spajanje svih odlomaka s točno jednim praznim redom razmaka između njih
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
            "config_type": "Profil A: Knjizevna SF literatura",
            "chunking": {
                "max_tokens_per_chunk": 1500,
                "overlap_tokens": 100
            },
            "enable_reasoning": not trans_cfg.get("disable_reasoning", True),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
