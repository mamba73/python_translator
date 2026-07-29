# Putanja i ime: ./mamba_voice.py
# Verzija: 1.0.6

import os
import sys
import re
import json
import logging
import asyncio
import argparse
import urllib.request
import subprocess
from typing import Any, Optional
from datetime import datetime
from collections import Counter

# Eksterni paketi
from pypdf import PdfReader
from docx import Document
import edge_tts

# Pokušaj uvoza za EPUB / MOBI - neobavezni paketi
try:
    import ebooklib
    from ebooklib import epub
    _EPUB_AVAILABLE = True
except ImportError:
    _EPUB_AVAILABLE = False

try:
    import mobi
    _MOBI_AVAILABLE = True
except ImportError:
    _MOBI_AVAILABLE = False


# ==============================================================================
# 3. MINIMALNA KONFIGURACIJA - samo DIR putanje i konstante
# ==============================================================================
# NAPOMENA: Sva ostala konfiguracija ide u config/settings.py
# Ova CONFIG će biti spojena sa vrijednostima iz settings.py pri pokretanju.
# ==============================================================================
CONFIG: dict[str, Any] = {
    "VERSION": "1.0.7",
    "PROJECT_NAME": "MambaBookVoice",

    # ===== SAMO DIR PUTANJE (dinamičke, trebaju biti ovdje) =====
    "DIR": {
        "BASE": os.path.dirname(os.path.abspath(__file__)),
        "LOGS": os.path.join(os.path.dirname(os.path.abspath(__file__)), "doc", "logs"),
        "MODELS": os.path.join(os.path.dirname(os.path.abspath(__file__)), "models"),
        "CACHE": os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache"),
        "CONFIG_DIR": os.path.join(os.path.dirname(os.path.abspath(__file__)), "config"),
        "INPUT": os.path.join(os.path.dirname(os.path.abspath(__file__)), "input"),
        "INPUT_PROCESSED": os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "input", "processed_text"
        ),
        "OUTPUT_TEXT": os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "text"),
        "OUTPUT_MP3": os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "mp3")
    },

    # ===== SANITIZATION - samo CHAR_MAP koji se ne može konfigurirati =====
    "SANITIZATION": {
        "CHAR_MAP": str.maketrans("čćšđžŽŠĐČĆ", "ccsdzZSDCC"),
    }

    # OSTALIH VRIJEDNOSTI NEMA OVDJE - sve su u config/settings.py
}


# ==============================================================================
# Funkcija za učitavanje konfiguracije iz Python datoteke
# ==============================================================================

def uc_konfiguraciju_iz_python_datoteke(config_dict: dict[str, Any]) -> dict[str, Any]:
    """Učitava konfiguraciju iz config/settings.py i spaja je s hardkodiiranim vrijednostima.
    
    Ova funkcija omogućava da se sve vrijednosti konfiguriraju kroz Python datoteku bez
    potrebe za escape znakovima. Multi-line stringovi se mogu pisati kao običan Python kod.
    
    Args:
        config_dict: Hardkodiirana zadana konfiguracija (CONFIG)
    
    Returns:
        Spojena konfiguracija sa vrijednostima iz settings.py (ako postoji)
    """
    config_dir = config_dict["DIR"]["CONFIG_DIR"]
    config_datoteka = os.path.join(config_dir, "settings.py")
    
    if not os.path.exists(config_datoteka):
        logging.info(f"Konfigurijska Python datoteka nije pronađena: {config_datoteka}")
        return config_dict
    
    try:
        # Dinamički učitaj Python modul iz putanje
        import importlib.util
        spec = importlib.util.spec_from_file_location("config_settings", config_datoteka)
        config_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config_module)
        
        if hasattr(config_module, 'SETTINGS'):
            ucitana_config = config_module.SETTINGS
            
            # Duboka spajanja konfiguracije (recursive merge)
            def spoji_dictionaryje(bazna: dict, nova: dict) -> dict:
                """Rekurzivno spaja novi dictionary u bazni."""
                rezultat = bazna.copy()
                for kljuc, vrijednost in nova.items():
                    if kljuc in rezultat and isinstance(rezultat[kljuc], dict) and isinstance(vrijednost, dict):
                        rezultat[kljuc] = spoji_dictionaryje(rezultat[kljuc], vrijednost)
                    else:
                        rezultat[kljuc] = vrijednost
                return rezultat
            
            config_dict = spoji_dictionaryje(config_dict, ucitana_config)
            logging.info(f"Konfiguracija uspješno učitana iz: {config_datoteka}")
        else:
            logging.warning(f"Datoteka {config_datoteka} nema SETTINGS dictionary")
        
    except Exception as e:
        logging.error(f"Greška pri učitavanju konfiguracije iz Python datoteke: {e}")
    
    return config_dict


# Učitaj konfiguraciju iz settings.py i spoji je s hardkodiiranim vrijednostima
CONFIG = uc_konfiguraciju_iz_python_datoteke(CONFIG)

# Osiguraj da CHAR_MAP postoji (jer se ne može pohraniti u Python datoteci kao lako editabilno)
if "CHAR_MAP" not in CONFIG.get("SANITIZATION", {}):
    CONFIG["SANITIZATION"]["CHAR_MAP"] = str.maketrans("čćšđžŽŠĐČĆ", "ccsdzZSDCC")


# ==============================================================================
# Funkcija za automatsku detekciju aktivnog modela iz LM Studio
# ==============================================================================

def detektiraj_aktivni_model() -> Optional[str]:
    """Pronalazi prvi dostupan model iz LM Studio API-ja.
    
    Ako je AUTO_DETECT_MODEL uključen, ova funkcija se poziva da pronađe
    koji je model trenutno aktivan u LM Studio, umjesto da korisnik ručno
    upisuje API_MODEL u settings.py
    
    Returns:
        Naziv modela ako je pronađen, None ako nije dostupan API
    """
    try:
        api_url = CONFIG["TRANSLATION"]["API_URL"]
        # Zamijeni /v1/chat/completions sa /v1/models
        models_url = api_url.replace("/v1/chat/completions", "/v1/models")
        
        with urllib.request.urlopen(models_url, timeout=5) as odgovor:
            data = json.loads(odgovor.read().decode('utf-8'))
            if data.get("data") and len(data["data"]) > 0:
                aktivni_model = data["data"][0]["id"]
                logging.info(f"✅ Auto-detektovan aktivni model: {aktivni_model}")
                return aktivni_model
    except Exception as e:
        logging.warning(f"Nije moguća auto-detekcija modela: {e}")
    
    return None


# Auto-detektiraj model ako je postavka uključena
if CONFIG["TRANSLATION"].get("AUTO_DETECT_MODEL", False) and not CONFIG["TRANSLATION"].get("API_MODEL"):
    detektirani_model = detektiraj_aktivni_model()
    if detektirani_model:
        CONFIG["TRANSLATION"]["API_MODEL"] = detektirani_model
    else:
        logging.error("Nije moguće detektovati model. Postavite API_MODEL u config/settings.py")


# ==============================================================================
# Globalne varijable za metadata o prijevodu
# ==============================================================================
TRANSLATION_METADATA = {
    "model": CONFIG["TRANSLATION"].get("API_MODEL", "Nepoznat"),
    "timestamp": None  # Će se postaviti pri svakom prijevodu
}


def generiraj_metadata_header() -> str:
    """Generiraj metadata header sa modelom i vremenom prijevoda.
    
    Returns:
        String sa header-om: # Model: qwen/qwen3.5-9b | Vrijeme: 2026-07-27 20:15:43
    """
    if not CONFIG["TRANSLATION"].get("ADD_METADATA_HEADER", False):
        return ""
    
    model = TRANSLATION_METADATA.get("model", "Nepoznat")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    return f"# Model: {model} | Vrijeme: {timestamp}\n"

# Osiguraj kreiranje svih potrebnih direktorija iz konfiguracije
for mapa in CONFIG["DIR"].values():
    os.makedirs(mapa, exist_ok=True)

# Postavljanje logiranja
log_datoteka = os.path.join(
    CONFIG["DIR"]["LOGS"],
    f"mamba_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_datoteka, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)


# ==============================================================================
# Cache / History funkcije
# ==============================================================================

HISTORY_DATOTEKA = os.path.join(CONFIG["DIR"]["CACHE"], "history.json")


def spremi_povijest(mode_number: str, odabrane_knjige: list[dict[str, str]], nacin_rada: str, tts_book: str = "") -> None:
    """Sprema zadnji odabir u history cache.
    
    Args:
        mode_number: Broj načina rada (1-5) za prikaz opisa.
        odabrane_knjige: Lista odabranih knjiga (rječnici s putanja, naziv, itd.).
        nacin_rada: Interni naziv načina rada (translate, full, tts_only, extract, convert_text).
        tts_book: Ime knjige za TTS (samo za način 3).
    """
    try:
        base_dir = CONFIG["DIR"]["BASE"]
        portabilne_knjige = []
        for knj in odabrane_knjige:
            knj_kopija = knj.copy()
            if "putanja" in knj_kopija and knj_kopija["putanja"].startswith(base_dir):
                knj_kopija["putanja"] = knj_kopija["putanja"][len(base_dir):]
            portabilne_knjige.append(knj_kopija)

        history_data = {
            "mode_number": mode_number,
            "nacin_rada": nacin_rada,
            "odabrane_knjige": portabilne_knjige,
            "tts_book": tts_book,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        with open(HISTORY_DATOTEKA, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.warning(f"Nije moguće spremiti history: {e}")


def ucitaj_povijest() -> Optional[dict]:
    """Učitava zadnji spremljeni history iz cache/history.json.
    
    Returns:
        Dictionar sa history podacima ili None ako ne postoji.
    """
    if not os.path.exists(HISTORY_DATOTEKA):
        return None
    try:
        with open(HISTORY_DATOTEKA, "r", encoding="utf-8") as f:
            data = json.load(f)
        base_dir = CONFIG["DIR"]["BASE"]
        for knj in data.get("odabrane_knjige", []):
            if "putanja" in knj:
                # Ako putanja ne počinje s base_dir, dodaj base_dir ispred
                # Ovo rješava problem na Windowsu gdje \putanja\vodi\do isabs=True
                if not knj["putanja"].startswith(base_dir):
                    # Ukloni vodeći \ ili / ako postoji (relativna putanja)
                    rel_putanja = knj["putanja"].lstrip("\\/")
                    knj["putanja"] = os.path.join(base_dir, rel_putanja)
        return data
    except Exception as e:
        logging.warning(f"Nije moguće učitati history: {e}")
        return None


def opisi_nacin_rada(mode_number: str) -> str:
    """Vraća ljudski čitljiv opis načina rada prema broju."""
    opisi = {
        "1": "Translate Only",
        "2": "Translate + Convert to MP3",
        "3": "TTS Only from Existing Translations",
        "4": "Extract and Clean Raw Text Only",
        "5": "Convert Document to Clean Text"
    }
    return opisi.get(mode_number, f"Način {mode_number}")


# ==============================================================================
# Pomoćne funkcije za čišćenje i sanitizaciju
# ==============================================================================

def sanitiziraj_naziv(naziv: str) -> str:
    """Uklanja dijakritike, pretvara razmake u crtice i priprema naziv za datoteke.

    Args:
        naziv: Originalni naziv koji može sadržavati specijalne znakove.

    Returns:
        Sanitizirani naziv spreman za korištenje u datotečnom sustavu.
    """
    naziv = naziv.translate(CONFIG["SANITIZATION"]["CHAR_MAP"])
    naziv = re.sub(r'[^\w\s-]', '', naziv).strip().lower()
    naziv = re.sub(r'\s+', CONFIG["SANITIZATION"]["REPLACE_SPACES_WITH"], naziv)
    return naziv


def generiraj_sigurnu_putanju(putanja: str) -> str:
    """Generira sigurnu putanju dodavanjem (000), (001), ... sufksa ako datoteka postoji.

    Args:
        putanja: Originalna putanja do datoteke.

    Returns:
        Putana koja ne postoji na disku (s dodatnim sufiksom ako je potrebno).
    """
    if not os.path.exists(putanja):
        return putanja

    korijen, ekst = os.path.splitext(putanja)
    brojac = 0
    while True:
        nova_putanja = f"{korijen}({brojac:03d}){ekst}"
        if not os.path.exists(nova_putanja):
            return nova_putanja
        brojac += 1


def generiraj_sigurnu_mapu(putanja_mape: str) -> str:
    """Generira sigurnu mapu dodavanjem (001), (002), ... sufksa ako mapa postoji.

    Ako mapa 'foundation---isaac-asimov' već postoji, stvara
    'foundation---isaac-asimov(001)', 'foundation---isaac-asimov(002)', itd.

    Args:
        putanja_mape: Originalna putanja do mape.

    Returns:
        Putanja do mape koja ne postoji (s brojčanim sufiksom ako je potrebno).
    """
    if not os.path.exists(putanja_mape):
        return putanja_mape

    brojac = 1
    while True:
        nova_putanja = f"{putanja_mape}({brojac:03d})"
        if not os.path.exists(nova_putanja):
            return nova_putanja
        brojac += 1


def unificiraj_navodnike(tekst: str) -> str:
    """Pretvara sve varijante tipografskih navodnika u standardne ravne dvostruke navodnike.

    Konvertira: „ ”, “ ”, « », ‹ ›, ‚ ', "" (mixed) u " ".
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
        sys.stdout.write(
            f"\r[Progres] : [{bar}] {dio_procenta} | {tekst_statusa} | {dodatno}"
        )
    else:
        sys.stdout.write(
            f"\r[Progres] : [{bar}] {dio_procenta} | {tekst_statusa}"
        )
    sys.stdout.flush()
    if trenutno == ukupno:
        sys.stdout.write("\n")


def ocisti_ekran() -> None:
    """Čisti terminal na Windows i Unix sustavima koristeći siguran subprocess poziv."""
    subprocess.run(
        "cls" if os.name == "nt" else "clear",
        shell=True,
        capture_output=True
    )


def ucitaj_izvorni_tekst(putanja_knjige: str) -> str:
    """Učitava sirovi tekst iz datoteke bez frekvencijske analize (za već očišćene knjige).

    Args:
        putanja_knjige: Apsolutna putanja do datoteke.

    Returns:
        Sirovi tekst iz datoteke.
    """
    ekstenzija = os.path.splitext(putanja_knjige)[1].lower()
    logging.info(f"Učitavam izvorni tekst: {os.path.basename(putanja_knjige)}")

    if ekstenzija == '.txt':
        with open(putanja_knjige, 'r', encoding='utf-8') as f:
            return f.read()
    elif ekstenzija == '.docx':
        doc = Document(putanja_knjige)
        return "\n".join([p.text for p in doc.paragraphs])
    elif ekstenzija == '.pdf':
        reader = PdfReader(putanja_knjige)
        dijelovi: list[str] = []
        for stranica in reader.pages:
            t = stranica.extract_text()
            if t:
                dijelovi.append(t)
        return "\n".join(dijelovi)
    elif ekstenzija == '.epub':
        if not _EPUB_AVAILABLE:
            logging.warning(
                "Biblioteka 'ebooklib' nije instalirana. "
                "Instalirajte je s: pip install ebooklib"
            )
            raise ImportError(
                "Biblioteka 'ebooklib' nije instalirana. "
                "Instalirajte je s: pip install ebooklib"
            )
        knjiga = epub.read_epub(putanja_knjige)
        dijelovi = []
        for item in knjiga.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                content = item.get_content()
                if content:
                    dekodirani = content.decode('utf-8', errors='replace')
                    cisti = re.sub(r'<[^>]+>', '', dekodirani)
                    dijelovi.append(cisti)
        return "\n".join(dijelovi)
    elif ekstenzija == '.mobi':
        if not _MOBI_AVAILABLE:
            logging.warning(
                "Biblioteka 'mobi' nije instalirana. "
                "Instalirajte je s: pip install mobi"
            )
            raise ImportError(
                "Biblioteka 'mobi' nije instalirana. "
                "Instalirajte je s: pip install mobi"
            )
        temp_dir, file_path = mobi.extract(putanja_knjige)
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    else:
        raise ValueError(f"Nepodržani format datoteke: {ekstenzija}")


# ==============================================================================
# Modul za analizu, čišćenje i ekstrakciju teksta
# ==============================================================================
def analiziraj_i_izvuci_tekst(putanja_knjige: str) -> tuple[str, dict[str, list[str]], list]:
    """Provodi frekvencijsku analizu otiska te čisti Header/Footer bez hardkodiranja.

    Args:
        putanja_knjige: Apsolutna putanja do datoteke za obradu.

    Returns:
        tuple: (očišćeni_tekst, detektirani_elementi, pages)
    """
    ekstenzija = os.path.splitext(putanja_knjige)[1].lower()

    logging.info(f"Započinje analiza dokumenta: {os.path.basename(putanja_knjige)}")

    if ekstenzija == '.txt':
        with open(putanja_knjige, 'r', encoding='utf-8') as f:
            return f.read(), {}, []
    elif ekstenzija == '.docx':
        doc = Document(putanja_knjige)
        pun_tekst = "\n".join([p.text for p in doc.paragraphs])
        return pun_tekst, {}, []

    if ekstenzija in ('.epub', '.mobi'):
        try:
            pun_tekst = ucitaj_izvorni_tekst(putanja_knjige)
            return pun_tekst, {}, []
        except ImportError as e:
            logging.error(str(e))
            raise

    if ekstenzija != '.pdf':
        raise ValueError(f"Nepodržani format datoteke: {ekstenzija}")

    reader = PdfReader(putanja_knjige)
    ukupno_stranica = len(reader.pages)
    limit_skeniranja = min(ukupno_stranica, CONFIG["TRANSLATION"]["SCAN_PAGES_LIMIT"])

    vrhovi_stranica: list[str] = []
    dna_stranica: list[str] = []

    for i in range(limit_skeniranja):
        tekst_stranice = reader.pages[i].extract_text()
        if not tekst_stranice:
            continue
        redovi = [r.strip() for r in tekst_stranice.split('\n') if r.strip()]
        if redovi:
            vrhovi_stranica.append(redovi[0])
            if len(redovi) > 1:
                dna_stranica.append(redovi[-1])

    brojac_vrh = Counter(vrhovi_stranica)
    brojac_dno = Counter(dna_stranica)

    za_uklanjanje: list[str] = []
    detektirani_elementi: dict[str, list[str]] = {"headers": [], "footers": []}

    for tekst, count in brojac_vrh.items():
        if count / limit_skeniranja > CONFIG["TRANSLATION"]["HEADER_FOOTER_THRESHOLD"] and len(tekst) > 3:
            if not re.match(r'^\d+$', tekst):
                za_uklanjanje.append(tekst)
                detektirani_elementi["headers"].append(tekst)

    for tekst, count in brojac_dno.items():
        if count / limit_skeniranja > CONFIG["TRANSLATION"]["HEADER_FOOTER_THRESHOLD"] and len(tekst) > 3:
            if not re.match(r'^\d+$', tekst):
                za_uklanjanje.append(tekst)
                detektirani_elementi["footers"].append(tekst)

    ocisceni_tekst_lista: list[str] = []
    regex_brojevi = r'^\d+$|^\b(Page|page)\b\s*\d+'

    for i in range(ukupno_stranica):
        tekst_stranice = reader.pages[i].extract_text()
        if not tekst_stranice:
            continue

        redovi = tekst_stranice.split('\n')
        novi_redovi: list[str] = []
        for r in redovi:
            r_clean = r.strip()
            if r_clean in za_uklanjanje:
                continue
            if re.match(regex_brojevi, r_clean):
                continue
            novi_redovi.append(r)

        ocisceni_tekst_lista.append("\n".join(novi_redovi))

    kompletan_tekst = "\n".join(ocisceni_tekst_lista)
    return kompletan_tekst, detektirani_elementi, reader.pages


# ==============================================================================
# Modul za segmentaciju poglavlja
# ==============================================================================
def segmentiraj_poglavlja(tekst: str) -> list[dict[str, str]]:
    """Razbija očišćeni tekst na poglavlja koristeći konfiguracijske uzorke.

    Čuva strukturu odlomaka unutar svakog poglavlja (\\n prijelomi se zadržavaju).

    Args:
        tekst: Očišćeni tekst knjige.

    Returns:
        Lista poglavlja, svako s "naslov" i "sadrzaj" (s očuvanim odlomcima).
    """
    redovi = tekst.split('\n')
    poglavlja: list[dict[str, str]] = []
    trenutno_poglavlje_naziv = "Prologue/Pre-Chapter Text"
    trenutni_tekst: list[str] = []

    uzorci = [re.compile(pat) for pat in CONFIG["CHAPTER_PATTERNS"]]

    for red in redovi:
        red_clean = red.strip()
        je_naslov = False

        for uzorak in uzorci:
            if uzorak.match(red_clean):
                je_naslov = True
                break

        if je_naslov:
            if trenutni_tekst:
                poglavlja.append({
                    "naslov": trenutno_poglavlje_naziv,
                    "sadrzaj": "\n".join(trenutni_tekst).strip()
                })
            trenutno_poglavlje_naziv = red_clean
            trenutni_tekst = []
        else:
            trenutni_tekst.append(red)

    if trenutni_tekst:
        poglavlja.append({
            "naslov": trenutno_poglavlje_naziv,
            "sadrzaj": "\n".join(trenutni_tekst).strip()
        })

    if len(poglavlja) == 1 and poglavlja[0]["naslov"] == "Prologue/Pre-Chapter Text":
        logging.warning("Nije detektirana struktura poglavlja preko Regexa. Pokrećem automatsko rezanje.")
        poglavlja = []
        velicina_bloka = 15000
        pun_tekst = "\n".join(trenutni_tekst) if trenutni_tekst else tekst
        za_rezanje = [pun_tekst[i:i + velicina_bloka] for i in range(0, len(pun_tekst), velicina_bloka)]
        for idx, blok in enumerate(za_rezanje):
            poglavlja.append({
                "naslov": f"Dio {idx + 1}",
                "sadrzaj": blok.strip()
            })

    return poglavlja


def segmentiraj_poglavlja_po_odlomcima(tekst: str) -> list[dict[str, str]]:
    """Alternativna segmentacija koja čuva strukturu paragrafa.

    Args:
        tekst: Sirovi tekst knjige.

    Returns:
        Lista poglavlja s očuvanim odlomcima.
    """
    poglavlja = segmentiraj_poglavlja(tekst)
    return poglavlja


# ==============================================================================
# Modul za strojno prevođenje putem LM Studio API-ja (paragrafski)
# ==============================================================================

def je_strukturni_ili_kratak(odlomak: str) -> bool:
    """Provjerava treba li odlomak preskočiti LLM prijevod.

    Vraća True ako odlomak:
    - Ima manje od MIN_WORDS_FOR_LLM riječi
    - Sadrži samo strukturne znakove (<, >, *, #, ---, ===, itd.)
    - Sadrži samo brojeve ili pojedinačne znakove

    Args:
        odlomak: Tekst odlomka za provjeru.

    Returns:
        True ako treba preskočiti LLM, False inače.
    """
    rijeci = odlomak.strip().split()
    min_rijeci = CONFIG["TRANSLATION"]["MIN_WORDS_FOR_LLM"]

    if len(rijeci) < min_rijeci:
        return True

    # Provjeri sadrži li samo strukturne/simboličke znakove
    samo_strukturno = all(
        re.match(r'^[\s<>\*#\-\=\|\/\\\(\)\[\]\{\}\.\,\!\?\"\'\;\:]+$', r)
        for r in rijeci
    )
    if samo_strukturno:
        return True

    return False


def prevedi_odlomak_lm_studio(odlomak: str) -> str:
    """Prevodi jedan odlomak engleskog teksta na hrvatski koristeći LM Studio API.

    Ako je odlomak prekratak ili sadrži samo strukturne znakove, preskače LLM
    i vraća original. Inače šalje zahtjev na lokalni LM Studio server.
    Nakon prijevoda primjenjuje:
    - Unifikaciju navodnika (sve -> ")
    - Čišćenje procurjelih fraza

    Args:
        odlomak: Engleski tekst jednog odlomka.

    Returns:
        Prevedeni hrvatski odlomak (ili original ako je preskočen).
    """
    if len(odlomak.strip()) <= 2:
        return odlomak

    if je_strukturni_ili_kratak(odlomak):
        logging.debug(f"Preskačem LLM za kratki/strukturni odlomak: '{odlomak[:50]}...'")
        return odlomak

    api_url = CONFIG["TRANSLATION"]["API_URL"]
    temperatura = CONFIG["TRANSLATION"]["TEMPERATURE"]
    max_tokena = CONFIG["TRANSLATION"]["MAX_TOKENS"]
    system_prompt = CONFIG["TRANSLATION"]["SYSTEM_PROMPT"]

    top_p = CONFIG["TRANSLATION"].get("TOP_P", 0.85)
    min_p = CONFIG["TRANSLATION"].get("MIN_P", 0.05)
    top_k = CONFIG["TRANSLATION"].get("TOP_K", 20)
    repeat_penalty = CONFIG["TRANSLATION"].get("REPEAT_PENALTY", 1.15)

    payload: dict[str, Any] = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": odlomak}
        ],
        "temperature": temperatura,
        "max_tokens": max_tokena,
        "top_p": top_p,
        "min_p": min_p,
        "top_k": top_k,
        "repeat_penalty": repeat_penalty,
        "stream": False
    }

    if CONFIG["TRANSLATION"].get("API_MODEL"):
        payload["model"] = CONFIG["TRANSLATION"]["API_MODEL"]

    # Isključi reasoning/thinking ako je DISABLE_REASONING uključeno
    if CONFIG["TRANSLATION"].get("DISABLE_REASONING", True):
        payload["reasoning"] = False
        payload["thinking"] = False

    podaci_json = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    zahtjev = urllib.request.Request(
        api_url,
        data=podaci_json,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(zahtjev, timeout=120) as odgovor:
            odgovor_json = json.loads(odgovor.read().decode('utf-8'))
            prijevod = odgovor_json["choices"][0]["message"]["content"].strip()

            # Post-processing: unifikacija navodnika
            prijevod = unificiraj_navodnike(prijevod)
            # Post-processing: čišćenje procurjelih fraza
            prijevod = ocisti_leaked_prijevod(prijevod)

            logging.debug(f"API odgovor primljen ({len(prijevod)} znakova)")
            return prijevod
    except urllib.error.HTTPError as e:
        logging.error(f"HTTP greška pri API pozivu: {e.code} - {e.reason}")
        return odlomak
    except urllib.error.URLError as e:
        logging.error(
            f"LM Studio API nije dostupan na {api_url}. "
            f"Provjerite je li LM Studio pokrenut i server aktivan. Greška: {e.reason}"
        )
        return odlomak
    except json.JSONDecodeError as e:
        logging.error(f"Neispravan JSON odgovor iz API-ja: {e}")
        return odlomak
    except Exception as e:
        logging.error(f"Neočekivana greška pri API pozivu: {e}")
        return odlomak


def prevedi_tekst_paragrafski(tekst_eng: str) -> str:
    """Prevodi engleski tekst na hrvatski čuvajući strukturu odlomaka.

    Dijeli tekst na prave odlomke pomoću .split('\\n\\n'), šalje svaki
    odlomak zasebno na LM Studio API, zatim ih spaja natrag s \\n\\n.
    Primjenjuje unifikaciju navodnika na cijeli tekst na kraju.

    Progress bar se ažurira nakon svakog odlomka u stvarnom vremenu.

    Args:
        tekst_eng: Engleski tekst koji može sadržavati više odlomaka.

    Returns:
        Prevedeni hrvatski tekst s očuvanom strukturom odlomaka.
    """
    odlomci_raw = tekst_eng.split('\n\n')
    odlomci: list[str] = []
    for o in odlomci_raw:
        o_strip = o.strip()
        if o_strip:
            odlomci.append(o_strip)

    if not odlomci:
        return ""

    ukupno_rijeci = sum(len(o.split()) for o in odlomci)
    akumulirane_rijeci = 0

    prevedeni_odlomci: list[str] = []
    ukupno = len(odlomci)

    for idx, odlomak in enumerate(odlomci):
        rijeci_u_odlomku = len(odlomak.split())
        akumulirane_rijeci += rijeci_u_odlomku

        try:
            prevedeni = prevedi_odlomak_lm_studio(odlomak)
            prevedeni_odlomci.append(prevedeni)
        except Exception as e:
            logging.error(f"Greška pri prevođenju odlomka {idx + 1}/{ukupno}: {e}")
            prevedeni_odlomci.append(odlomak)

        prikazi_progres(
            idx + 1,
            ukupno,
            f"Odlomak: {idx + 1}/{ukupno}",
            f"riječi: {akumulirane_rijeci}/{ukupno_rijeci} ({int(akumulirane_rijeci / ukupno_rijeci * 100)}%)"
        )

    # Spajanje s \n\n - savršeno očuvanje originalne strukture
    konacni_tekst = "\n\n".join(prevedeni_odlomci)

    # Završna unifikacija navodnika na cijelom tekstu
    konacni_tekst = unificiraj_navodnike(konacni_tekst)

    return konacni_tekst


# ==============================================================================
# Modul za strojno prevođenje putem LM Studio API-ja (rečenica-po-rečenicu)
# ==============================================================================

def prevedi_recenicu_lm_studio(recenica: str) -> str:
    """Prevodi jednu rečenicu engleskog teksta na hrvatski koristeći LM Studio API.

    Svaka rečenica se omota u <source_text> i </source_text> tagove prije slanja
    API-ju. Nakon prijevoda primjenjuje:
    - Unifikaciju navodnika (sve -> ")
    - Čišćenje procurjelih fraza

    Args:
        recenica: Engleski tekst jedne rečenice.

    Returns:
        Prevedena hrvatska rečenica (ili original ako je preskočena).
    """
    if len(recenica.strip()) <= 2:
        return recenica

    if je_strukturni_ili_kratak(recenica):
        logging.debug(f"Preskačem LLM za kratku/strukturnu rečenicu: '{recenica[:50]}...'")
        return recenica

    api_url = CONFIG["TRANSLATION"]["API_URL"]
    temperatura = CONFIG["TRANSLATION"]["TEMPERATURE"]
    max_tokena = CONFIG["TRANSLATION"]["MAX_TOKENS"]
    system_prompt = CONFIG["TRANSLATION"]["SYSTEM_PROMPT"]

    top_p = CONFIG["TRANSLATION"].get("TOP_P", 0.85)
    min_p = CONFIG["TRANSLATION"].get("MIN_P", 0.05)
    top_k = CONFIG["TRANSLATION"].get("TOP_K", 20)
    repeat_penalty = CONFIG["TRANSLATION"].get("REPEAT_PENALTY", 1.15)

    # Omotaj rečenicu u <source_text> tagove
    tagged_content = f"<source_text>{recenica}</source_text>"

    payload: dict[str, Any] = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": tagged_content}
        ],
        "temperature": temperatura,
        "max_tokens": max_tokena,
        "top_p": top_p,
        "min_p": min_p,
        "top_k": top_k,
        "repeat_penalty": repeat_penalty,
        "stream": False
    }

    if CONFIG["TRANSLATION"].get("API_MODEL"):
        payload["model"] = CONFIG["TRANSLATION"]["API_MODEL"]

    # Isključi reasoning/thinking ako je DISABLE_REASONING uključeno
    if CONFIG["TRANSLATION"].get("DISABLE_REASONING", True):
        payload["reasoning"] = False
        payload["thinking"] = False

    podaci_json = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    zahtjev = urllib.request.Request(
        api_url,
        data=podaci_json,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(zahtjev, timeout=120) as odgovor:
            odgovor_json = json.loads(odgovor.read().decode('utf-8'))
            prijevod = odgovor_json["choices"][0]["message"]["content"].strip()

            # Post-processing: unifikacija navodnika
            prijevod = unificiraj_navodnike(prijevod)
            # Post-processing: čišćenje procurjelih fraza
            prijevod = ocisti_leaked_prijevod(prijevod)

            logging.debug(f"API odgovor primljen za rečenicu ({len(prijevod)} znakova)")
            return prijevod
    except urllib.error.HTTPError as e:
        logging.error(f"HTTP greška pri API pozivu: {e.code} - {e.reason}")
        return recenica
    except urllib.error.URLError as e:
        logging.error(
            f"LM Studio API nije dostupan na {api_url}. "
            f"Provjerite je li LM Studio pokrenut i server aktivan. Greška: {e.reason}"
        )
        return recenica
    except json.JSONDecodeError as e:
        logging.error(f"Neispravan JSON odgovor iz API-ja: {e}")
        return recenica
    except Exception as e:
        logging.error(f"Neočekivana greška pri API pozivu: {e}")
        return recenica


def prevedi_tekst_recenica_po_recenicu(tekst_eng: str) -> str:
    """Prevodi engleski tekst na hrvatski rečenicu po rečenicu.

    Dijeli tekst na rečenice pomoću regex split-a na granicama rečenica
    ('.', '!', '?'), šalje svaku rečenicu zasebno omotanu u <source_text> tagove
    na LM Studio API, zatim ih spaja natrag u kohezivni paragraf.
    Ovo sprječava attention drift i gramatičku degradaciju u dugim izlazima.

    Progress bar se ažurira nakon svake rečenice u stvarnom vremenu.

    Args:
        tekst_eng: Engleski tekst koji može sadržavati više rečenica.

    Returns:
        Prevedeni hrvatski tekst s očuvanom strukturom rečenica.
    """
    # Prvo podijeli na odlomke da očuva strukturu paragrafa
    odlomci_raw = tekst_eng.split('\n\n')
    odlomci: list[str] = []
    for o in odlomci_raw:
        o_strip = o.strip()
        if o_strip:
            odlomci.append(o_strip)

    if not odlomci:
        return ""

    prevedeni_odlomci: list[str] = []
    ukupno_odlomaka = len(odlomci)
    ukupno_rijeci = sum(len(o.split()) for o in odlomci)
    akumulirane_rijeci = 0

    for od_idx, odlomak in enumerate(odlomci):
        # Podijeli odlomak na rečenice koristeći regex
        recenice = re.split(r'(?<=[.!?])\s+', odlomak)
        recenice = [r.strip() for r in recenice if r.strip()]

        if not recenice:
            prevedeni_odlomci.append("")
            continue

        prevedene_recenice: list[str] = []
        for rec_idx, recenica in enumerate(recenice):
            rijeci_u_recenici = len(recenica.split())
            akumulirane_rijeci += rijeci_u_recenici

            try:
                prevedena = prevedi_recenicu_lm_studio(recenica)
                prevedene_recenice.append(prevedena)
            except Exception as e:
                logging.error(f"Greška pri prevođenju rečenice {rec_idx + 1}/{len(recenice)}: {e}")
                prevedene_recenice.append(recenica)

            prikazi_progres(
                od_idx + 1,
                ukupno_odlomaka,
                f"Odlomak: {od_idx + 1}/{ukupno_odlomaka} | Rečenica: {rec_idx + 1}/{len(recenice)}",
                f"riječi: {akumulirane_rijeci}/{ukupno_rijeci} ({int(akumulirane_rijeci / ukupno_rijeci * 100)}%)"
            )

        # Spoji prevedene rečenice natrag u odlomak
        prevedeni_odlomci.append(" ".join(prevedene_recenice))

    # Spajanje odlomaka s \n\n - očuvanje originalne strukture
    konacni_tekst = "\n\n".join(prevedeni_odlomci)

    # Završna unifikacija navodnika na cijelom tekstu
    konacni_tekst = unificiraj_navodnike(konacni_tekst)

    return konacni_tekst


# ==============================================================================
# Modul za sintezu govora (Edge-TTS) s podrškom za Naraciju, Dijalog i Dramu
# ==============================================================================
async def generiraj_audio_poglavlje(tekst_hr: str, putanja_izlaza: str) -> None:
    """Generira MP3 audio uz analizu dijaloga i dramatskog moda (brzina/visina glasa).

    Args:
        tekst_hr: Hrvatski tekst za pretvorbu u govor.
        putanja_izlaza: Putanja za spremanje MP3 datoteke.
    """
    trenutna_brzina = CONFIG["TTS"]["NARATOR"]["RATE"]

    if CONFIG["TTS"]["DRAMATIC_MODE"]["ENABLED"]:
        rijeci = tekst_hr.lower().split()
        if any(kw in rijeci for kw in CONFIG["TTS"]["DRAMATIC_MODE"]["KEYWORDS_ANXIOUS"]):
            trenutna_brzina = CONFIG["TTS"]["DRAMATIC_MODE"]["RATE_MODIFIER_ANXIOUS"]

    dijelovi_teksta = re.split(r'("[^"]+"|—\s*.*?\n|"[^"]+")', tekst_hr)
    tts_objekti: list[Any] = []

    for komad in dijelovi_teksta:
        komad_clean = komad.strip()
        if not komad_clean:
            continue

        je_dijalog = komad_clean.startswith(('"', '—', '"'))

        if je_dijalog and CONFIG["TTS"]["DIJALOG"]["USE_DIFFERENT_VOICE"]:
            glas = CONFIG["TTS"]["DIJALOG"]["VOICE"]
            brzina = CONFIG["TTS"]["DIJALOG"]["RATE"]
            visina = CONFIG["TTS"]["DIJALOG"]["PITCH"]
        else:
            glas = CONFIG["TTS"]["NARATOR"]["VOICE"]
            brzina = trenutna_brzina
            visina = CONFIG["TTS"]["NARATOR"]["PITCH"]

        communicate = edge_tts.Communicate(komad_clean, glas, rate=brzina, pitch=visina)
        tts_objekti.append(communicate)

    with open(putanja_izlaza, "wb") as f:
        for tts_obj in tts_objekti:
            async for chunk in tts_obj.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])


# ==============================================================================
# Funkcije za skeniranje direktorija i odabir knjiga
# ==============================================================================
def skeniraj_input_datoteke() -> list[dict[str, str]]:
    """Skenira i input/ i input/processed_text/ direktorije za podržane datoteke.

    Returns:
        Lista rječnika dostupnih knjiga za obradu.
    """
    podrzane_ekstenzije = ('.pdf', '.docx', '.txt', '.epub', '.mobi')
    knjige: list[dict[str, str]] = []

    ulazna_mapa = CONFIG["DIR"]["INPUT"]
    if os.path.isdir(ulazna_mapa):
        for dat in os.listdir(ulazna_mapa):
            if dat.lower().endswith(podrzane_ekstenzije):
                knjige.append({
                    "putanja": os.path.join(ulazna_mapa, dat),
                    "naziv": dat,
                    "je_preciscen": "false"
                })

    preciscena_mapa = CONFIG["DIR"]["INPUT_PROCESSED"]
    if os.path.isdir(preciscena_mapa):
        for ime_mape in sorted(os.listdir(preciscena_mapa)):
            puna_putanja_mape = os.path.join(preciscena_mapa, ime_mape)
            if os.path.isdir(puna_putanja_mape):
                txt_datoteke = [
                    d for d in os.listdir(puna_putanja_mape)
                    if d.lower().endswith('.txt')
                ]
                if txt_datoteke:
                    knjige.append({
                        "putanja": puna_putanja_mape,
                        "naziv": f"[OČIŠĆENO] {ime_mape}",
                        "je_preciscen": "true",
                        "ime_mape": ime_mape
                    })

    return knjige


def skeniraj_output_tekst_mape() -> list[str]:
    """Skenira output/text/ za postojeće prevedene knjige (mape s .txt poglavljima).

    Returns:
        Lista naziva mapa koje sadrže prevedene .txt datoteke.
    """
    tekst_mapa = CONFIG["DIR"]["OUTPUT_TEXT"]
    if not os.path.isdir(tekst_mapa):
        return []

    knjige: list[str] = []
    for ime in sorted(os.listdir(tekst_mapa)):
        puna = os.path.join(tekst_mapa, ime)
        if os.path.isdir(puna):
            txt_datoteke = [
                d for d in os.listdir(puna)
                if d.lower().endswith('.txt')
            ]
            if txt_datoteke:
                knjige.append(ime)
    return knjige


# ==============================================================================
# Obrada za način rada 4: Ekstrakcija i čišćenje sirovog teksta
# ==============================================================================
def obradi_ekstrakciju_i_ciscenje(putanja_knjige: str, naziv_knjige: str) -> None:
    """Obrađuje sirovu datoteku frekvencijskom analizom i izvozi očišćeni tekst.

    Očuvava strukturu odlomaka (\\n\\n) u izlaznim .txt datotekama.

    Args:
        putanja_knjige: Apsolutna putanja do sirove datoteke.
        naziv_knjige: Originalni naziv datoteke za prikaz.
    """
    print(f"\n[EKSTRAKCIJA] Obrada: {naziv_knjige}")

    if os.path.isdir(putanja_knjige):
        print(f"  [SKIP] '{naziv_knjige}' je već pročišćena knjiga.")
        return

    try:
        ocisceni_tekst, detektirani_elementi, _ = analiziraj_i_izvuci_tekst(putanja_knjige)
    except ImportError as e:
        logging.error(str(e))
        print(f"\n[GRESKA] {e}")
        return
    except Exception as e:
        logging.error(f"Greška pri analizi {naziv_knjige}: {e}")
        print(f"\n[GRESKA] Ne mogu obraditi datoteku: {e}")
        return

    print(f"\n  Detektirani headeri: {detektirani_elementi.get('headers', [])}")
    print(f"  Detektirani footeri: {detektirani_elementi.get('footers', [])}")

    poglavlja = segmentiraj_poglavlja(ocisceni_tekst)
    print(f"  Ukupno poglavlja: {len(poglavlja)}")

    cisti_naziv = sanitiziraj_naziv(os.path.splitext(naziv_knjige)[0])
    izlazna_mapa = os.path.join(CONFIG["DIR"]["INPUT_PROCESSED"], cisti_naziv)
    izlazna_mapa = generiraj_sigurnu_mapu(izlazna_mapa)
    os.makedirs(izlazna_mapa, exist_ok=True)

    padding = CONFIG["SANITIZATION"]["PREFIX_PADDING"]
    for idx, poglavlje in enumerate(poglavlja):
        redni_broj = str(idx + 1).zfill(padding)
        cisti_naslov = sanitiziraj_naziv(poglavlje["naslov"])
        if not cisti_naslov:
            cisti_naslov = f"poglavlje-{redni_broj}"

        naziv_datoteke = f"{redni_broj}_{cisti_naslov}.txt"
        putanja_datoteke = os.path.join(izlazna_mapa, naziv_datoteke)
        putanja_datoteke = generiraj_sigurnu_putanju(putanja_datoteke)

        with open(putanja_datoteke, "w", encoding="utf-8") as f:
            f.write(poglavlje["sadrzaj"])

        prikazi_progres(idx + 1, len(poglavlja), f"Spremam: {os.path.basename(putanja_datoteke)}")

    kompletna_datoteka = os.path.join(izlazna_mapa, f"{cisti_naziv}-complete.txt")
    kompletna_datoteka = generiraj_sigurnu_putanju(kompletna_datoteka)
    with open(kompletna_datoteka, "w", encoding="utf-8") as f:
        f.write(ocisceni_tekst)

    print(f"\n  [OK] Očišćeni tekst spremljen u: {izlazna_mapa}")
    print(f"  [OK] Kompletni tekst: {kompletna_datoteka}")


# ==============================================================================
# Obrada za način rada 3: TTS Only iz postojećih prijevoda
# ==============================================================================
async def obradi_tts_iz_postojecih(ime_knjige: str) -> None:
    """Generira MP3 datoteke iz postojećih prevedenih .txt datoteka.

    Čita strukturirane .txt datoteke (s očuvanim \\n\\n odlomcima) i
    pretvara ih u MP3 pomoću edge-tts modula.

    Args:
        ime_knjige: Ime mape unutar output/text/ koja sadrži .txt datoteke.
    """
    ulazna_mapa = os.path.join(CONFIG["DIR"]["OUTPUT_TEXT"], ime_knjige)
    izlazna_mapa = os.path.join(CONFIG["DIR"]["OUTPUT_MP3"], ime_knjige)
    izlazna_mapa = generiraj_sigurnu_mapu(izlazna_mapa)
    os.makedirs(izlazna_mapa, exist_ok=True)

    txt_datoteke = sorted([
        d for d in os.listdir(ulazna_mapa)
        if d.lower().endswith('.txt') and not d.endswith('-complete.txt')
    ])

    if not txt_datoteke:
        print(f"\n[GRESKA] Nema .txt datoteka u mapi: {ulazna_mapa}")
        return

    ukupno_rijeci = 0
    for txt_dat in txt_datoteke:
        putanja_txt = os.path.join(ulazna_mapa, txt_dat)
        with open(putanja_txt, "r", encoding="utf-8") as f:
            ukupno_rijeci += len(f.read().split())

    print(f"\n[TTS ONLY] Generiram MP3 za: {ime_knjige}")
    print(f"  Pronađeno poglavlja: {len(txt_datoteke)}, ukupno riječi: {ukupno_rijeci}")

    akumulirane_rijeci = 0
    for idx, txt_dat in enumerate(txt_datoteke):
        putanja_txt = os.path.join(ulazna_mapa, txt_dat)
        with open(putanja_txt, "r", encoding="utf-8") as f:
            tekst = f.read()

        rijeci_u_datoteci = len(tekst.split())
        akumulirane_rijeci += rijeci_u_datoteci

        mp3_naziv = txt_dat.replace('.txt', '.mp3')
        putanja_mp3 = os.path.join(izlazna_mapa, mp3_naziv)
        putanja_mp3 = generiraj_sigurnu_putanju(putanja_mp3)

        print(f"\n  [TTS] {txt_dat} -> {os.path.basename(putanja_mp3)}")
        await generiraj_audio_poglavlje(tekst, putanja_mp3)

        prikazi_progres(
            idx + 1,
            len(txt_datoteke),
            f"Poglavlje: {idx + 1}/{len(txt_datoteke)}",
            f"riječi: {akumulirane_rijeci}/{ukupno_rijeci} ({int(akumulirane_rijeci / ukupno_rijeci * 100)}%)"
        )

    print(f"\n  [OK] MP3 datoteke spremljene u: {izlazna_mapa}")


# ==============================================================================
# Glavni CLI i upravljački tok sučelja
# ==============================================================================
def obradi_konverziju_u_tekst(putanja_knjige: str, naziv_knjige: str) -> None:
    """Konvertira dokument (PDF, DOCX, EPUB, MOBI, TXT) u čisti tekst s unifikacijom navodnika.

    Ekstrahira tekst, primjenjuje unificiraj_navodnike() za standardizaciju
    svih tipografskih navodnika, i sprema u input/processed_text/ direktorij
    kao jedinstvenu .txt datoteku. Ova datoteka se zatim automatski detektira
    u skeniraj_input_datoteke() za daljnju obradu (prijevod, TTS).

    Args:
        putanja_knjige: Apsolutna putanja do izvorne datoteke.
        naziv_knjige: Originalni naziv datoteke za prikaz.
    """
    print(f"\n[KONVERZIJA U TEKST] Obrada: {naziv_knjige}")

    if os.path.isdir(putanja_knjige):
        print(f"  [SKIP] '{naziv_knjige}' je mapa, ne datoteka.")
        return

    try:
        sirovi_tekst = ucitaj_izvorni_tekst(putanja_knjige)
    except ImportError as e:
        logging.error(str(e))
        print(f"\n[GRESKA] {e}")
        return
    except Exception as e:
        logging.error(f"Greška pri učitavanju {naziv_knjige}: {e}")
        print(f"\n[GRESKA] Ne mogu učitati datoteku: {e}")
        return

    # Primijeni unifikaciju navodnika na cijeli tekst
    ocisceni_tekst = unificiraj_navodnike(sirovi_tekst)

    # Sanitiziraj naziv i kreiraj izlaznu mapu
    cisti_naziv = sanitiziraj_naziv(os.path.splitext(naziv_knjige)[0])
    izlazna_mapa = os.path.join(CONFIG["DIR"]["INPUT_PROCESSED"], cisti_naziv)
    izlazna_mapa = generiraj_sigurnu_mapu(izlazna_mapa)
    os.makedirs(izlazna_mapa, exist_ok=True)

    # Spremi kao jedinstvenu .txt datoteku
    naziv_datoteke = f"{cisti_naziv}.txt"
    putanja_datoteke = os.path.join(izlazna_mapa, naziv_datoteke)
    putanja_datoteke = generiraj_sigurnu_putanju(putanja_datoteke)

    with open(putanja_datoteke, "w", encoding="utf-8") as f:
        f.write(ocisceni_tekst)

    print(f"\n  [OK] Konvertirani tekst spremljen u: {putanja_datoteke}")
    print(f"  [OK] Ova datoteka je sada dostupna za odabir u načinima 1, 2 i 4 kao [OČIŠĆENO].")


def interaktivni_izbornik() -> tuple[list[dict[str, str]], str, str]:
    """Simulira tekstualno checkbox sučelje za odabir knjiga i načina rada.

    Nudi 5 načina rada:
      1. Translate Only
      2. Translate + Convert to MP3
      3. TTS Only from Existing Translations
      4. Extract and Clean Raw Text Only
      5. Convert Document to Clean Text (PDF/DOCX/EPUB/MOBI -> TXT u input/processed_text/)

    Returns:
        tuple: (odabrane_knjige, nacin_rada, odabrana_knjiga_za_tts)
    """
    while True:
        ocisti_ekran()
        print("=== MambaBookVoice v1.0.7 — Odabir načina rada ===\n")
        print("Odaberite način rada:\n")
        print("  1. Translate Only (Prijevod u tekstualni format)")
        print("  2. Translate + Convert to MP3 (Potpuni proces)")
        print("  3. TTS Only from Existing Translations (MP3 iz gotovih prijevoda)")
        print("  4. Extract and Clean Raw Text Only (Čišćenje sirovog teksta)")
        print("  5. Convert Document to Clean Text (PDF/DOCX/EPUB/MOBI -> TXT)\n")

        # Provjeri postoji li history i ponudi Y opciju
        history_data = ucitaj_povijest()
        if history_data and history_data.get("mode_number") and history_data.get("nacin_rada"):
            print(f"  Y - Ponovi zadnju radnju: [{history_data['mode_number']}] {opisi_nacin_rada(history_data['mode_number'])}")
        print("  X - Izlaz iz aplikacije\n")

        izbor = input("Unesite broj načina rada (1-5) / Y / X: ").strip().upper()

        if izbor == 'X':
            print("\nPotvrda izlaska iz aplikacije? (D/N): ", end="")
            potvrda = input().strip().upper()
            if potvrda == 'D':
                print("\n[Dovidenja!]")
                sys.exit(0)
            continue

        if izbor == 'Y':
            history_data = ucitaj_povijest()
            if history_data and history_data.get("mode_number") and history_data.get("nacin_rada"):
                mode_number = history_data["mode_number"]
                nacin_rada = history_data["nacin_rada"]
                odabrane_knjige = history_data.get("odabrane_knjige", [])
                tts_book = history_data.get("tts_book", "")
                print(f"\n[History] Ponavljam radnju: [{mode_number}] {opisi_nacin_rada(mode_number)}")
                if nacin_rada == "tts_only":
                    return [], nacin_rada, tts_book
                else:
                    return odabrane_knjige, nacin_rada, ""
            print("[History] Nema spremljene povijesti. Pritisnite Enter.")
            input()
            continue

        if izbor == "1":
            knjige = skeniraj_input_datoteke()
            if not knjige:
                print("\n[GRESKA] Nema podržanih datoteka u input/ ili input/processed_text/.")
                input("Pritisnite Enter za povratak...")
                continue

            odabrane = prikazi_checkbox_izbor(knjige, "Odaberite knjige za prijevod:")
            if not odabrane:
                print("Niste odabrali nijednu knjigu. Pritisnite Enter za povratak...")
                input()
                continue
            spremi_povijest("1", odabrane, "translate")
            return odabrane, "translate", ""

        elif izbor == "2":
            knjige = skeniraj_input_datoteke()
            if not knjige:
                print("\n[GRESKA] Nema podržanih datoteka u input/ ili input/processed_text/.")
                input("Pritisnite Enter za povratak...")
                continue

            odabrane = prikazi_checkbox_izbor(knjige, "Odaberite knjige za potpuni proces:")
            if not odabrane:
                print("Niste odabrali nijednu knjigu. Pritisnite Enter za povratak...")
                input()
                continue
            spremi_povijest("2", odabrane, "full")
            return odabrane, "full", ""

        elif izbor == "3":
            knjige_mape = skeniraj_output_tekst_mape()
            if not knjige_mape:
                print("\n[GRESKA] Nema prevedenih knjiga u output/text/. Prvo prevedite knjige.")
                input("Pritisnite Enter za povratak...")
                continue

            odabrana = prikazi_jednostruki_izbor(knjige_mape, "Odaberite knjigu za TTS generiranje:")
            if odabrana is None:
                continue
            spremi_povijest("3", [], "tts_only", odabrana)
            return [], "tts_only", odabrana

        elif izbor == "4":
            knjige = skeniraj_input_datoteke()
            if not knjige:
                print("\n[GRESKA] Nema podržanih datoteka u input/ ili input/processed_text/.")
                input("Pritisnite Enter za povratak...")
                continue

            odabrane = prikazi_checkbox_izbor(knjige, "Odaberite knjige za ekstrakciju i čišćenje:")
            if not odabrane:
                print("Niste odabrali nijednu knjigu. Pritisnite Enter za povratak...")
                input()
                continue
            spremi_povijest("4", odabrane, "extract")
            return odabrane, "extract", ""

        elif izbor == "5":
            # Convert Document to Clean Text
            knjige = skeniraj_input_datoteke()
            if not knjige:
                print("\n[GRESKA] Nema podržanih datoteka u input/ ili input/processed_text/.")
                input("Pritisnite Enter za povratak...")
                continue

            odabrane = prikazi_checkbox_izbor(knjige, "Odaberite dokumente za konverziju u čisti tekst:")
            if not odabrane:
                print("Niste odabrali nijednu datoteku. Pritisnite Enter za povratak...")
                input()
                continue
            spremi_povijest("5", odabrane, "convert_text")
            return odabrane, "convert_text", ""

        else:
            print("Neispravan unos. Molimo unesite broj 1-5.")
            input("Pritisnite Enter za nastavak...")


def prikazi_checkbox_izbor(
    knjige: list[dict[str, str]], naslov: str = ""
) -> list[dict[str, str]]:
    """Prikazuje interaktivni checkbox izbornik za višestruki odabir.

    Args:
        knjige: Lista rječnika s ključevima "putanja", "naziv", "je_preciscen".
        naslov: Naslov izbornika.

    Returns:
        Lista odabranih knjiga (rječnici).
    """
    izabrane_oznake = [False] * len(knjige)

    while True:
        ocisti_ekran()
        print(f"=== {naslov} ===")
        print("Odaberite knjige upisivanjem broja (ponovni unos uklanja kvačicu).")
        print("Upišite 'ALL' za sve, ili 'S' za potvrdu i nastavak.\n")

        for idx, knj in enumerate(knjige):
            checkbox = "[X]" if izabrane_oznake[idx] else "[ ]"
            oznaka = ""
            if knj.get("je_preciscen") == "true":
                oznaka = " [očišćeno]"
            print(f"{checkbox} {idx + 1}. {knj['naziv']}{oznaka}")

        unos = input("\nVaš unos (broj / ALL / S / X): ").strip().upper()

        if unos == 'X':
            return []

        if unos == 'S':
            if any(izabrane_oznake):
                break
            else:
                print("Morate odabrati barem jednu knjigu prije nastavka! Pritisnite Enter.")
                input()
        elif unos == 'ALL':
            izabrane_oznake = [True] * len(knjige)
            break
        elif unos.isdigit():
            broj = int(unos) - 1
            if 0 <= broj < len(knjige):
                izabrane_oznake[broj] = not izabrane_oznake[broj]
            else:
                print("Nepostojeći broj. Pritisnite Enter.")
                input()
        else:
            print("Neispravan unos. Pritisnite Enter.")
            input()

    odabrane_knjige = [knjige[i] for i, izabrano in enumerate(izabrane_oznake) if izabrano]
    return odabrane_knjige


def prikazi_jednostruki_izbor(opcije: list[str], naslov: str = "") -> Optional[str]:
    """Prikazuje jednostruki izbornik za odabir jedne opcije.

    Args:
        opcije: Lista naziva opcija za odabir.
        naslov: Naslov izbornika.

    Returns:
        Odabrana opcija ili None ako je odustao.
    """
    while True:
        ocisti_ekran()
        print(f"=== {naslov} ===\n")

        for idx, opc in enumerate(opcije):
            print(f"  {idx + 1}. {opc}")

        print("\n  'Q' za odustajanje, 'X' za povratak u glavni izbornik\n")
        unos = input("Unesite broj opcije: ").strip().upper()

        if unos == 'Q' or unos == 'X':
            return None
        elif unos.isdigit():
            broj = int(unos) - 1
            if 0 <= broj < len(opcije):
                return opcije[broj]
            else:
                print("Nepostojeći broj. Pritisnite Enter.")
                input()
        else:
            print("Neispravan unos. Pritisnite Enter.")
            input()


# ==============================================================================
# Glavna obrađivačka petlja
# ==============================================================================
async def main() -> None:
    """Glavna async funkcija koja pokreće cijeli proces obrade knjiga."""
    parser = argparse.ArgumentParser(description="MambaBookVoice CLI v1.0.6")
    parser.add_argument("--batch", action="store_true", help="Preskače izbornik i automatski obrađuje sve datoteke")
    parser.add_argument("--only-translate", action="store_true", help="Pokreće samo mod prevođenja")
    args = parser.parse_args()

    if args.batch:
        knjige = skeniraj_input_datoteke()
        knjige_za_obradu = knjige
        nacin_rada = "translate" if args.only_translate else "full"
        odabrana_knjiga_tts = ""
    else:
        knjige_za_obradu, nacin_rada, odabrana_knjiga_tts = interaktivni_izbornik()

    # ===== NAČIN 3: TTS Only =====
    if nacin_rada == "tts_only" and odabrana_knjiga_tts:
        await obradi_tts_iz_postojecih(odabrana_knjiga_tts)
        print("\n\n[ZAVRSENO] TTS generiranje uspješno završeno!")
        return

    # ===== NAČIN 4: Extract and Clean Only =====
    if nacin_rada == "extract":
        ukupno_knjiga = len(knjige_za_obradu)
        for bk, knjiga in enumerate(knjige_za_obradu):
            print(f"\n--- Knjiga {bk + 1}/{ukupno_knjiga}: {knjiga['naziv']} ---")
            obradi_ekstrakciju_i_ciscenje(knjiga["putanja"], knjiga["naziv"])
        print("\n\n[ZAVRSENO] Ekstrakcija i čišćenje uspješno završeno!")
        return

    # ===== NAČIN 5: Convert Document to Clean Text =====
    if nacin_rada == "convert_text":
        ukupno_knjiga = len(knjige_za_obradu)
        for bk, knjiga in enumerate(knjige_za_obradu):
            print(f"\n--- Dokument {bk + 1}/{ukupno_knjiga}: {knjiga['naziv']} ---")
            obradi_konverziju_u_tekst(knjiga["putanja"], knjiga["naziv"])
        print("\n\n[ZAVRSENO] Konverzija u čisti tekst uspješno završena!")
        return

    # ===== NAČIN 1 (translate) i NAČIN 2 (full) =====
    ukupno_knjiga = len(knjige_za_obradu)
    for bk, knjiga in enumerate(knjige_za_obradu):
        putanja_knjige = knjiga["putanja"]
        naziv_knjige = knjiga["naziv"]
        je_preciscena = knjiga.get("je_preciscen") == "true"

        print(f"\n{'=' * 60}")
        print(f"KNJIGA {bk + 1}/{ukupno_knjiga}: {naziv_knjige}")
        print(f"{'=' * 60}")

        if je_preciscena:
            ime_mape = knjiga.get("ime_mape", os.path.basename(putanja_knjige))
            cisti_naziv_knjige = sanitiziraj_naziv(ime_mape)

            print(f"\n[PRECISCENA KNJIGA] Učitavam iz: {putanja_knjige}")

            svi_tekstovi: list[str] = []
            mape_poglavlja: list[dict[str, str]] = []
            txt_datoteke = sorted([
                d for d in os.listdir(putanja_knjige)
                if d.lower().endswith('.txt') and not d.endswith('-complete.txt')
            ])

            for txt_dat in txt_datoteke:
                putanja_txt = os.path.join(putanja_knjige, txt_dat)
                with open(putanja_txt, "r", encoding="utf-8") as f:
                    sadrzaj = f.read()
                svi_tekstovi.append(sadrzaj)
                naslov_poglavlja = os.path.splitext(txt_dat)[0]
                naslov_poglavlja = re.sub(r'^\d{3}_', '', naslov_poglavlja)
                naslov_poglavlja = naslov_poglavlja.replace('-', ' ').title()
                mape_poglavlja.append({
                    "naslov": naslov_poglavlja,
                    "sadrzaj": sadrzaj
                })

            tekst_knjige = "\n\n".join(svi_tekstovi)
            detektirani_anomalije: dict[str, list[str]] = {}
            poglavlja = mape_poglavlja

        else:
            pun_naziv, _ = os.path.splitext(os.path.basename(putanja_knjige))
            cisti_naziv_knjige = sanitiziraj_naziv(pun_naziv)

            try:
                tekst_knjige, detektirani_anomalije, _ = analiziraj_i_izvuci_tekst(putanja_knjige)
            except ImportError as e:
                logging.error(str(e))
                print(f"\n[GRESKA] {e}")
                continue
            except Exception as e:
                logging.error(f"Greška pri obradi {naziv_knjige}: {e}")
                print(f"\n[GRESKA] Ne mogu obraditi datoteku: {e}")
                continue

            poglavlja = segmentiraj_poglavlja(tekst_knjige)

        samo_prijevod = (nacin_rada == "translate")
        print(f"\n{'=' * 50}")
        print(f"IZVJEŠTAJ O STRUKTURI KNJIGE: {naziv_knjige}")
        if not je_preciscena:
            print(f"  - Detektirani Headeri za uklanjanje: {detektirani_anomalije.get('headers', [])}")
            print(f"  - Detektirani Footeri za uklanjanje: {detektirani_anomalije.get('footers', [])}")
        else:
            print(f"  - [OČIŠĆENO] Frekvencijska analiza preskočena.")
        print(f"  - Ukupno uspješno mapiranih poglavlja: {len(poglavlja)}")
        print(f"  - Planirani izlaz audio datoteka: {0 if samo_prijevod else len(poglavlja)}")
        ukupno_rijeci_knjige = sum(len(p["sadrzaj"].split()) for p in poglavlja)
        print(f"  - Ukupno riječi u knjizi: {ukupno_rijeci_knjige}")
        print(f"{'=' * 50}\n")

        # Kreiranje izlaznih podmapa s inkrementalnim prefiksom
        tekst_izlazna_mapa = os.path.join(CONFIG["DIR"]["OUTPUT_TEXT"], cisti_naziv_knjige)
        tekst_izlazna_mapa = generiraj_sigurnu_mapu(tekst_izlazna_mapa)
        mp3_izlazna_mapa = os.path.join(CONFIG["DIR"]["OUTPUT_MP3"], cisti_naziv_knjige)
        mp3_izlazna_mapa = generiraj_sigurnu_mapu(mp3_izlazna_mapa)
        os.makedirs(tekst_izlazna_mapa, exist_ok=True)
        if not samo_prijevod:
            os.makedirs(mp3_izlazna_mapa, exist_ok=True)

        padding = CONFIG["SANITIZATION"]["PREFIX_PADDING"]
        for idx, poglavlje in enumerate(poglavlja):
            redni_broj = str(idx + 1).zfill(padding)
            cisti_naslov_poglavlja = sanitiziraj_naziv(poglavlje["naslov"])
            if not cisti_naslov_poglavlja:
                cisti_naslov_poglavlja = f"poglavlje-{redni_broj}"

            rijeci_u_poglavlju = len(poglavlje["sadrzaj"].split())
            print(
                f"\n[Poglavlje {idx + 1}/{len(poglavlja)}]: "
                f"{poglavlje['naslov']} ({rijeci_u_poglavlju} riječi)"
            )

            if CONFIG["TRANSLATION"].get("SENTENCE_BY_SENTENCE", True):
                prevedeni_tekst = prevedi_tekst_recenica_po_recenicu(poglavlje["sadrzaj"])
            else:
                prevedeni_tekst = prevedi_tekst_paragrafski(poglavlje["sadrzaj"])

            # Dodaj metadata header ako je uključeno u settings.py
            metadata_header = generiraj_metadata_header()
            tekst_za_pisanje = metadata_header + prevedeni_tekst if metadata_header else prevedeni_tekst

            tekst_file_name = f"{redni_broj}_{cisti_naslov_poglavlja}.txt"
            putanja_tekst = os.path.join(tekst_izlazna_mapa, tekst_file_name)
            putanja_tekst = generiraj_sigurnu_putanju(putanja_tekst)

            with open(putanja_tekst, "w", encoding="utf-8") as tf:
                tf.write(tekst_za_pisanje)

            print(f"  [SPREMLJENO] {os.path.basename(putanja_tekst)}")

            if not samo_prijevod:
                audio_file_name = f"{redni_broj}_{cisti_naslov_poglavlja}.mp3"
                putanja_mp3 = os.path.join(mp3_izlazna_mapa, audio_file_name)
                putanja_mp3 = generiraj_sigurnu_putanju(putanja_mp3)
                print(f"  [TTS] Generiram MP3: {os.path.basename(putanja_mp3)}")
                await generiraj_audio_poglavlje(prevedeni_tekst, putanja_mp3)
                print(f"  [TTS OK] {os.path.basename(putanja_mp3)}")

    print("\n\n[ZAVRSENO] Sve izabrane knjige su uspješno obrađene!")


if __name__ == "__main__":
    asyncio.run(main())