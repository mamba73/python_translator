# TEHNIČKA DOKUMENTACIJA SUSTAVA — KOMPLETNA SPECIFIKACIJA

## DYNAMIC BOOK TRANSLATOR & PARSER — V0.3
**Datum:** 30. srpnja 2026.  
**Autor:** mamba  
**Platforma:** Windows + Git Bash (MSYS2/MinGW)  
**Jezik:** Python 3.10+  
**Status:** Produkcijska specifikacija

---

## SADRŽAJ

1. [Sažetak sustava](#1-sažetak-sustava)
2. [Tehnički zahtjevi i dependencies](#2-tehnički-zahtjevi-i-dependencies)
3. [Struktura direktorija i datoteka](#3-struktura-direktorija-i-datoteka)
4. [Bootstrap mehanizam — `./start` datoteka](#4-bootstrap-mehanizam--start-datoteka)
5. [Konfiguracijski sustav — YAML format i per-book direktoriji](#5-konfiguracijski-sustav)
6. [Arhitektura glavnog izbornika (CLI)](#6-arhitektura-glavnog-izbornika-cli)
7. [Faza 1 — Konverzija dokumenata u TXT/MD](#7-faza-1--konverzija-dokumenata-u-txtmd)
8. [Faza 2 — Čišćenje tehničkog šuma (`[fixed]`) + kreiranje memorije](#8-faza-2--čišćenje-tehničkog-šuma-fixed--kreiranje-memorije)
9. [Faza 3 — Prevođenje preko lokalnog LLM-a](#9-faza-3--prevođenje-preko-lokalnog-llm-a)
10. [Faza 4 — TTS sinteza u MP3 po paragrafima](#10-faza-4--tts-sinteza-u-mp3-po-paragrafima)
11. [Batch processing mehanizam](#11-batch-processing-mehanizam)
12. [Multi-checkpoint sustav perzistencije](#12-multi-checkpoint-sustav-perzistencije)
13. [1-Click test sustav](#13-1-click-test-sustav)
14. [Trorazinsko logiranje](#14-troazinsko-logiranje)
15. [Vanjski API integracija](#15-vanjski-api-integracija)
16. [Automatska detekcija likova — analiza izvedivosti](#16-automatska-detekcija-likova)
17. [.gitignore specifikacija](#17-gitignore-specifikacija)
18. [Sigurnosno rukovanje greškama](#18-sigurnosno-rukovanje-greškama)
19. [Protokol sigurnog izlaza](#19-protokol-sigurnog-izlaza)
20. [Header metapodaci u prevedenom tekstu](#20-header-metapodaci-u-prevedenom-tekstu)

---

## 1. SAŽETAK SUSTAVA

Sustav je četverofazni CLI alat namijenjen automatiziranoj pripremi, prijevodu i audio-sintezi knjiga različitih žanrova (književna SF literatura, stručna IT literatura, općenito). Ključne karakteristike:

- **Bootstrap provjera okruženja** pri svakom pokretanju putem `./start` datoteke.
- **Unificirana `X` navigacija** kroz sve razine izbornika.
- **Per-book direktoriji** — svaka knjiga ima vlastiti direktorij s izoliranom konfiguracijom i memorijom.
- **YAML konfiguracija** — multi-line system prompt s jednostavnim copy/paste i komentarima.
- **Čista struktura** — svi radni direktoriji unutar `work/`, root sadrži samo kod.
- **Memorija vezana za obrađeni tekst** — JSON s likovima/glosarom kreira se uz [fixed] datoteku.
- **Batch processing** — višestruki odabir datoteka u svakoj fazi.
- **MP3 po paragrafima** — audio knjiga se razdvaja po paragrafima u direktoriju knjige.
- **Multi-checkpoint perzistencija** — do 6+ paralelnih naslova s neovisnim postotkom napretka.
- **1-Click test sustav** — pamti zadnje testne parametre za brzo ponavljanje.
- **Trorazinsko logiranje** — osnovno, verbatim i LLM response debug.
- **Vanjski API integracija** — podrška za LM Studio, OpenAI, Gemini, Qwen.
- **Dvostruka potvrda izlaza** radi zaštite od slučajnog prekida.
- **Fallback mehanizam** pri `HTTP 500` ili `Timeout` greškama lokalnog LLM-a.

---

## 2. TEHNIČKI ZAHTJEVI I DEPENDENCIES

### 2.1 Hardverski minimum
| Komponenta | Preporuka |
|---|---|
| CPU | 4+ jezgre |
| RAM | 16 GB+ |
| GPU | NVIDIA RTX (za LM Studio + TTS) |
| Disk | 50 GB slobodno za biblioteke i cache |

### 2.2 Softverski stack
- **OS:** Windows 10/11
- **Terminal:** Git Bash (MSYS2) — **obavezno**, zbog POSIX putanja i `./start` sintakse
- **Python:** 3.10 ili noviji
- **LM Studio:** lokalni API server na `http://127.0.0.1:1234/v1`
- **TTS engine:** lokalni (npr. `edge-tts`, `Coqui TTS` ili `piper`)

### 2.3 Python paketi (`requirements.txt`)
```txt
python-docx>=1.1.0
PyPDF2>=3.0.0
pdfplumber>=0.10.0
ebooklib>=0.18
beautifulsoup4>=4.12.0
python-magic>=0.4.27
regex>=2023.12.25
requests>=2.31.0
edge-tts>=6.1.9
colorama>=0.4.6
tqdm>=4.66.0
pyyaml>=6.0.1
```

---

## 3. STRUKTURA DIREKTORIJA I DATOTEKA

### 3.1 Princip organizacije

Root direktorij projekta sadrži **isključivo kod i globalnu konfiguraciju**. Svi radni direktoriji (ulaz, izlaz, prijevodi, audio, logovi, state) smješteni su unutar `work/` direktorija kako bi:

- Root projekta bio čist i pregledan.
- `.gitignore` bio jednostavan (samo ignorirati `work/`).
- Backup i migracija bili lakši (kopirati samo `work/`).
- Struktura bila jasno odvojena: kod vs. podaci.

### 3.2 Kompletna struktura

```
project_root/
│
├── ./start                          # Bash bootstrap skripta (ulazna točka)
├── main.py                          # Glavna Python skripta (CLI + orkestracija)
├── requirements.txt                 # Lista pip paketa
├── .gitignore                       # Git ignore pravila
│
├── config/                          # Globalni konfiguracijski profili (YAML)
│   ├── profile_sf_literature.yaml
│   ├── profile_it_technical.yaml
│   └── profile_general.yaml
│
└── work/                            # Svi radni direktoriji
    │
    ├── input/                       # Ulazni direktorij (samo sirovi dokumenti)
    │   ├── Dune.epub
    │   ├── Clean_Code.pdf
    │   └── ...
    │
    ├── output/                      # Međufaza (TXT/MD + [fixed] + konfiguracija + memorija)
    │   ├── Dune/                    # Direktorij po knjizi
    │   │   ├── Dune.txt             # Sirova konverzija
    │   │   ├── Dune [fixed].txt     # Očišćena verzija (spremna za prijevod)
    │   │   ├── config.yaml          # Per-book konfiguracija (YAML)
    │   │   └── Dune_memorija.json   # Likovi, glosar, gramatika (auto-kreiran pri [fixed])
    │   │
    │   └── Clean_Code/
    │       ├── Clean_Code.md
    │       ├── Clean_Code [fixed].md
    │       ├── config.yaml
    │       └── Clean_Code_memorija.json
    │
    ├── translated/                  # Konačni prijevodi (bez [fixed] sufiksa)
    │   ├── Dune/
    │   │   └── Dune.txt             # Konačni prijevod s header metapodacima
    │   └── Clean_Code/
    │       └── Clean_Code.md
    │
    ├── audiobooks/                  # Finalni MP3 izlazi PO PARAGRAFIMA
    │   ├── Dune/                    # Direktorij po knjizi
    │   │   ├── 001.mp3              # Prvi paragraf
    │   │   ├── 002.mp3              # Drugi paragraf
    │   │   ├── 003.mp3
    │   │   └── ...
    │   └── Clean_Code/
    │       ├── 001.mp3
    │       └── ...
    │
    ├── state/                       # Perzistencija checkpointa
    │   ├── translation_checkpoints.json
    │   └── last_test.json           # Zadnji testni parametri
    │
    └── logs/                        # Log datoteke po datumu
        ├── 2026-07-30_142211_dynamic_book_translator_v4.3.0_debug.log
        ├── 2026-07-30_142211_dynamic_book_translator_v4.3.0_verbatim.log
        └── llm_responses/           # LLM odgovori po knjizi
            ├── Dune/
            │   ├── chunk_001.json
            │   └── ...
            └── Clean_Code/
                └── ...
```

### 3.3 Ključna promjena: Memorija vezana za obrađeni tekst

**ZAŠTO memorija NIJE u `input/`:**
- `input/` sadrži **samo sirove dokumente** (epub, pdf, docx) koji se još nisu obrađivali.
- Memorija (likovi, glosar, gramatika) odnosi se na **obrađeni i očišćeni tekst** koji se šalje na prijevod.
- Memorija je kontekstualno vezana za `[fixed]` datoteku — ne za sirovi input.
- Sve vezano za jednu knjigu (konverzija, čišćenje, konfiguracija, memorija) mora biti na **jednom mjestu** — u `work/output/<Knjiga>/`.

**KADA se kreira memorija:**
- Memorija se **automatski kreira s placeholderima** prilikom Faze 2 (čišćenje tehničkog šuma).
- Kada skripta generira `Dune [fixed].txt`, istovremeno kreira `Dune_memorija.json` s praznom strukturom.
- Korisnik može ručno popuniti memoriju prije pokretanja Faze 3 (prevođenje).

### 3.4 Automatsko kreiranje direktorija

Pri prvom pokretanju skripta automatski kreira sve potrebne direktorije:

```python
DIRECTORIES = [
    "work/input",
    "work/output",
    "work/translated",
    "work/audiobooks",
    "work/state",
    "work/logs",
    "config"
]

for dir_path in DIRECTORIES:
    os.makedirs(dir_path, exist_ok=True)
```

---

## 4. BOOTSTRAP MEHANIZAM — `./start` DATOTEKA

### 4.1 Svrha
`./start` je Bash skripta koja služi kao **jedina ulazna točka** u aplikaciju. Pri svakom pokretanju izvršava:

1. Provjeru postojanja Python interpretera.
2. Provjeru postojanja virtualnog okruženja (`venv/`).
3. Kreiranje `venv/` ako ne postoji.
4. **Sinkronizaciju pip paketa** — usporedbu `requirements.txt` s instaliranim paketima i instalaciju nedostajućih.
5. Aktivaciju `venv`-a.
6. Pokretanje `main.py`.

### 4.2 Mehanizam provjere paketa
Skripta koristi `comm -23` za skupovnu razliku:
- **Lijevi skup:** paketi iz `requirements.txt` (bez verzija).
- **Desni skup:** instalirani paketi iz `pip freeze`.
- **Rezultat:** samo nedostajući paketi → instaliraju se tiho (`--quiet`).

Ovaj mehanizam osigurava da se **svaki puta pri pokretanju** provjeri integritet okruženja, bez ponovne instalacije već prisutnih paketa.

---

## 5. KONFIGURACIJSKI SUSTAV — YAML FORMAT I PER-BOOK DIREKTORJI

### 5.1 Globalna konfiguracija u `main.py`

Svi globalni parametri definirani su na vrhu skripte u jasno označenom bloku:

```python
# ============================================================
# KONFIGURACIJA I VARIJABLE
# ============================================================

SCRIPT_NAME = "Dynamic Book Translator"
SCRIPT_VERSION = "4.3.0"

# --- Boje za CLI ---
CLR_YELLOW = "\033[93m"
CLR_GREEN = "\033[92m"
CLR_RED = "\033[91m"
CLR_BLUE = "\033[94m"
CLR_CYAN = "\033[96m"
CLR_RESET = "\033[0m"

# --- Direktoriji ---
WORK_DIR = "./work"
INPUT_DIR = f"{WORK_DIR}/input"
OUTPUT_DIR = f"{WORK_DIR}/output"
TRANSLATED_DIR = f"{WORK_DIR}/translated"
AUDIOBOOKS_DIR = f"{WORK_DIR}/audiobooks"
STATE_DIR = f"{WORK_DIR}/state"
LOGS_DIR = f"{WORK_DIR}/logs"
CONFIG_DIR = "./config"

# --- API konfiguracija ---
API_PROVIDER = "lm_studio"  # Opcije: "lm_studio", "openai", "gemini", "qwen"
API_BASE_URL = "http://127.0.0.1:1234/v1"
API_KEY = ""  # Prazno za lokalni LM Studio, obavezno za cloud API-je
DEFAULT_MODEL = "local-model"

# --- Logiranje ---
LOG_VERBATIM = False       # Detaljni trace svake akcije (default: OFF)
LOG_LLM_RESPONSES = False  # Snimanje punih LLM odgovora (default: OFF)
ENABLE_REASONING = False   # Dozvoli reasoning/thinking u outputu (default: OFF)

# --- TTS konfiguracija ---
TTS_ENGINE = "edge-tts"
TTS_VOICE = "hr-HR-GabrijelaNeural"
TTS_RATE = "+0%"
TTS_VOLUME = "+0%"
```

### 5.2 Per-book konfiguracija — YAML format

Svaka knjiga ima vlastiti `config.yaml` unutar svog direktorija u `work/output/`. YAML format omogućuje:

- **Multi-line stringove** s `|` (literal block) — savršen za system prompt.
- **Komentare** s `#` — dokumentacija unutar konfiguracije.
- **Čitljivost** bolju od JSON-a.
- **Copy/paste friendly** — nema escape karaktera.
- **Strukturiranost** — jasna hijerarhija podataka.

### 5.3 Struktura `work/output/Dune/config.yaml`

```yaml
# ============================================================
# KONFIGURACIJA KNJIGE: Dune
# ============================================================

# --- Osnovni podaci ---
book_title: "Dune"
author: "Frank Herbert"
original_file: "Dune.epub"

# --- API konfiguracija (override globalnih postavki) ---
api_provider: "lm_studio"  # Opcije: "lm_studio", "openai", "gemini", "qwen"
model: "local-model"
api_key_override: ""  # Prazno = koristi globalni API_KEY

# --- System prompt (multi-line, copy/paste friendly) ---
system_prompt: |
  Ti si stručni prevoditelj s engleskog na hrvatski za žanr znanstvene fantastike.
  Zadrži literarni stil, emociju i ritam rečenica.
  Koristi bogat rječnik, ali izbjegavaj arhaizme i posuđenice iz srpskog/bosanskog.
  Koristi isključivo standardni hrvatski jezik.
  Poštuj rod likova prema uputama iz JSON memorije.
  Ako naiđeš na tehnički termin koji nema etablirani hrvatski ekvivalent, ostavi ga na engleskom.
  
  STIL:
  - Koristi kratke, udarne rečenice za akciju.
  - Koristi duže, tečne rečenice za opise i introspekciju.
  - Izbjegavaj pasivne konstrukcije gdje je moguće.
  
  TON:
  - Misteriozan i napet.
  - Filozofski gdje je prikladno.
  - Nikada kolokvijalan ili moderan.

# --- Parametri modela ---
parameters:
  temperature: 0.25
  top_p: 0.80
  top_k: 15
  min_p: 0.05
  max_tokens: 4096
  repeat_penalty: 1.1

# --- Chunking konfiguracija ---
chunking:
  max_tokens_per_chunk: 1500
  overlap_tokens: 100

# --- JSON memorija (likovi, glosar, gramatika) ---
memorija_file: "Dune_memorija.json"

# --- Reasoning toggle ---
enable_reasoning: false  # false = čisti  <think> i  tagove iz outputa

# --- Metadata ---
created_at: "2026-07-30T14:22:11"
updated_at: "2026-07-30T14:22:11"
```

### 5.4 Učitavanje YAML konfiguracije

Skripta učitava `config.yaml` koristeći `pyyaml` biblioteku:

```python
import yaml
from pathlib import Path

def load_book_config(book_dir):
    """Učitava config.yaml iz direktorija knjige."""
    config_path = Path(book_dir) / "config.yaml"
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    return config
```

### 5.5 Globalni profili u `config/`

Globalni profili (`profile_sf_literature.yaml`, `profile_it_technical.yaml`, `profile_general.yaml`) koriste se kao **template** pri kreiranju novog `config.yaml` za knjigu. Sadrže predefinirane parametre i system prompt za različite žanrove.

---

## 6. ARHITEKTURA GLAVNOG IZBORNIKA (CLI)

### 6.1 Navigacijski princip
- Jedinstvena tipka **`X`** (ili `x`) za povratak na prethodnu razinu.
- U glavnom izborniku `X` pokreće **sigurnosni izlaz s dvostrukom potvrdom**.
- Numerički izbori (`1`, `2`, `3`…) za akcije.
- **Batch odabir:** `1,3,5` ili `1-5` ili `*` za sve datoteke.

### 6.2 Stablo izbornika

```
[GLAVNI IZBORNIK]
│
├── [Y] TEST: [Opis zadnjeg testa]  ← samo ako postoji last_test.json
│
├── [Checkpointi]  ← dinamički, samo ako postoje spremljeni radovi
│   └── [n] Nastavi: [Naslov] — XX.XX%
│
├── [1] Konverzija dokumenata → TXT/MD
│   └── Lista iz work/input/
│       └── Odabir: 1,3,5 (batch)
│           ├── [1] → .txt
│           ├── [2] → .md
│           └── [X] povratak
│
├── [2] Čišćenje tehničkog šuma ([fixed]) + kreiranje memorije
│   └── Lista iz work/output/
│       └── Odabir: 1-5 (batch)
│           ├── [1] pokreni čišćenje
│           └── [X] povratak
│
├── [3] Prevođenje (LLM)
│   ├── [1] Napravi testni prevod
│   │   ├── Odabir datoteke
│   │   ├── Odabir profila
│   │   ├── Odabir testa (paragrafi/rečenice/sl)
│   │   └── Unesi broj
│   │
│   └── [2] Prevedi cijelu knjigu
│       └── Lista [fixed] datoteka iz work/output/
│           └── Odabir: 1,3,5 (batch)
│
├── [4] TTS sinteza → MP3 (po paragrafima)
│   └── Lista iz work/translated/
│       └── Odabir: 2,4 (batch)
│           ├── [1] pokreni sintezu
│           └── [X] povratak
│
└── [X] Izlaz
    └── "Jeste li sigurni? (Y/N)"
```

---

## 7. FAZA 1 — KONVERZIJA DOKUMENATA U TXT/MD

### 7.1 Podržani ulazni formati
| Ekstenzija | Parser |
|---|---|
| `.docx` | `python-docx` |
| `.doc` | LibreOffice headless konverzija (fallback) |
| `.pdf` | `pdfplumber` (layout-aware) + `PyPDF2` |
| `.epub` | `ebooklib` + `BeautifulSoup` |
| `.mobi` | konverzija u EPUB pa parsiranje |

### 7.2 Tijek obrade
1. Čitanje svih datoteka iz `work/input/`.
2. Prikaz numerirane liste korisniku.
3. Odabir formata izvoza (`.txt` ili `.md`) — podržan batch odabir.
4. Parsiranje → čišćenje binarnih artefakata → normalizacija UTF-8.
5. Kreiranje direktorija `work/output/<NazivKnjige>/`.
6. Zapis u `work/output/<NazivKnjige>/<NazivKnjige>.txt|md`.

### 7.3 Markdown specifičnosti
Kada je odabran `.md` izvoz:
- Naslovi poglavlja se mapiraju u `#`, `##`, `###`.
- Kurzivi i podebljani tekstovi zadržavaju `*...*` i `**...**` sintaksu.
- Liste ostaju kao `-` ili `1.`.
- Slike se ispuštaju (TTS ih ne čita), ali se zadržava alt-tekst kao komentar.

---

## 8. FAZA 2 — ČIŠĆENJE TEHNIČKOG ŠUMA (`[fixed]`) + KREIRANJE MEMORIJE

### 8.1 Problem
PDF i EPUB izvori često umeću:
- **Zaglavlja (header):** naziv knjige/poglavlja na vrhu svake stranice.
- **Podnožja (footer):** broj stranice, ime autora.
- **Prelomljene rečenice:** misao se prekida na granici stranice, a između se ubacuje header/footer.

Bez čišćenja, TTS bi čitao npr. *"...i tada je shvatio da je 42 stranica Dune Frank Herbert 1965. sve bilo uzalud..."* — što ruši audio iskustvo.

### 8.2 Algoritam čišćenja
1. **Detekcija ponavljajućih obrazaca:** ako se isti string pojavljuje na ≥3 stranice na istoj poziciji (vrh/dno) → klasificira se kao header/footer.
2. **Uklanjanje izoliranih brojeva stranica** (`^\s*\d+\s*$`).
3. **Spajanje prelomljenih rečenica:** ako red završava bez točke/zareza, a sljedeći ne počinje velikim slovom → spajanje bez razmaka.
4. **Normalizacija whitespace-a:** višestruki razmaci i prazni redovi se sažimaju.

### 8.3 Izlaz
Datoteka se sprema u `work/output/<Knjiga>/` s obaveznim sufiksom:
```
work/input/Dune.epub  
  → work/output/Dune/Dune.txt  
    → work/output/Dune/Dune [fixed].txt
```

Sufiks `[fixed]` služi kao **signal** za Fazu 3 da je datoteka prošla kontrolu kvalitete i spremna je za prijevod.

### 8.4 Automatsko kreiranje memorije

**Ključna promjena:** Prilikom generiranja `[fixed]` datoteke, skripta **automatski kreira** pripadajuću `memorija.json` datoteku s praznom strukturom (placeholder).

**Struktura `work/output/Dune/Dune_memorija.json`:**

```json
{
  "CHARACTERS": {},
  "GLOSSARY": {},
  "GRAMMAR_FIXES": {}
}
```

**ZAŠTO se memorija kreira ovdje:**
- Memorija je kontekstualno vezana za **obrađeni tekst** koji se šalje na prijevod.
- Sve vezano za jednu knjigu (konverzija, čišćenje, konfiguracija, memorija) je na **jednom mjestu** — u `work/output/<Knjiga>/`.
- Korisnik može ručno popuniti memoriju **prije** pokretanja Faze 3 (prevođenje).
- Memorija sadrži specifičnosti koje se odnose na **konkretnu knjigu** (likovi, glosar, gramatička pravila).

**Primjer popunjene memorije za SF roman:**

```json
{
  "CHARACTERS": {
    "Paul Atreides": "Treat Paul as MASCULINE. Use masculine verb endings.",
    "Lady Jessica": "Treat Jessica as FEMININE. Translate as 'gospa Jessica'.",
    "Chani": "Treat Chani as FEMININE. Use feminine grammar consistently."
  },
  "GLOSSARY": {
    "spice": "začin / melange",
    "sandworm": "pješčani crv",
    "bene gesserit": "Bene Gesserit",
    "kwisatz haderach": "Kwisatz Haderach"
  },
  "GRAMMAR_FIXES": {
    "terminology": "Keep fictional terms in original form or use established Croatian translations.",
    "names": "Do not croatianize fictional names. Keep 'Paul', 'Jessica', 'Chani' as-is."
  }
}
```

**Primjer popunjene memorije za IT knjigu:**

```json
{
  "CHARACTERS": {
    "Author": "Technical expert. Use professional, neutral language."
  },
  "GLOSSARY": {
    "backend": "backend",
    "frontend": "frontend",
    "thread": "thread",
    "database": "baza podataka",
    "framework": "framework"
  },
  "GRAMMAR_FIXES": {
    "technical_terms": "DO NOT translate established IT terms. Keep 'backend', 'thread', 'pipeline' in English.",
    "register": "Maintain professional, academic register. No poetic metaphors."
  }
}
```

---

## 9. FAZA 3 — PREVOĐENJE PREKO LOKALNOG LLM-A

### 9.1 API endpoint
```
POST http://127.0.0.1:1234/v1/chat/completions
Content-Type: application/json

{
  "model": "lokalni-model",
  "messages": [
    {"role": "system", "content": "<system_prompt iz config.yaml> + <JSON memorija>"},
    {"role": "user",   "content": "<odlomak za prijevod>"}
  ],
  "temperature": 0.25,
  "top_p": 0.80,
  "max_tokens": 4096,
  "stream": false
}
```

### 9.2 Tijek obrade
1. Filtriranje `work/output/` — prikazuju se **samo** datoteke s `[fixed]` u nazivu.
2. Odabir datoteke — podržan batch odabir.
3. Učitavanje `config.yaml` iz direktorija knjige.
4. Učitavanje `memorija.json` iz istog direktorija.
5. Injekcija memorije u system prompt.
6. Chunkiranje teksta na odlomke (po ~1500 tokena).
7. Slanje odlomak-po-odlomak na LLM API.
8. Čišćenje odgovora od XML tagova (ako `enable_reasoning: false`).
9. Zapis u `work/translated/<Knjiga>/<Knjiga>.txt|md` (bez `[fixed]` sufiksa).
10. Ažuriranje `work/state/translation_checkpoints.json` nakon svakog odlomka.

### 9.3 Injekcija system prompta i memorije

```python
def build_system_prompt(config, memorija):
    """Kombinira system prompt iz config.yaml s JSON memorijom."""
    prompt = config['system_prompt']
    
    if memorija:
        prompt += "\n\n[DODATNA MEMORIJA — JSON]\n"
        prompt += f"CHARACTERS:\n"
        for name, desc in memorija.get('CHARACTERS', {}).items():
            prompt += f"  - {name}: {desc}\n"
        
        prompt += f"\nGLOSSARY:\n"
        for term, translation in memorija.get('GLOSSARY', {}).items():
            prompt += f"  - {term} → {translation}\n"
        
        prompt += f"\nGRAMMAR_FIXES:\n"
        for rule, desc in memorija.get('GRAMMAR_FIXES', {}).items():
            prompt += f"  - {rule}: {desc}\n"
    
    return prompt
```

---

## 10. FAZA 4 — TTS Sinteza u MP3 po paragrafima

### 10.1 Ulaz
Datoteke iz `work/translated/` (gotovi hrvatski prijevodi).

### 10.2 Tijek
1. Čitanje teksta po paragrafima (ne po rečenicama — kako je ranije bilo).
2. Za svaki paragraf generira se zasebna `.mp3` datoteka.
3. Slanje svakog paragrafa u TTS engine (npr. `edge-tts` s glasom `hr-HR-GabrijelaNeural`).
4. Zapis u `work/audiobooks/<Knjiga>/` s numeriranim nazivima:
   - `001.mp3` — prvi paragraf
   - `002.mp3` — drugi paragraf
   - `003.mp3` — treći paragraf
   - ...

### 10.3 Zašto po paragrafima
- **Fleksibilnost:** korisnik može preskočiti ili ponoviti pojedini paragraf.
- **Organizacija:** lakše upravljanje velikim knjigama.
- **Backup:** ako jedan MP3 faila, ostali su sigurni.
- **Streaming:** moguće streamati audio po paragrafima.

### 10.4 Zašto `[fixed]` faza kritična za MP3
Budući da je u Fazi 2 uklonjen sav tehnički šum, TTS glas čita **isključivo tečni narativ** — bez iznenadnih prekida, brojeva stranica ili ponavljanja zaglavlja usred rečenice.

---

## 11. BATCH PROCESSING MEHANIZAM

### 11.1 Princip rada

Svaki podizbornik omogućuje **višestruki odabir** datoteka koristeći:
- Pojedinačni odabir: `1` (samo prva datoteka)
- Višestruki odabir: `1,3,5` (datoteke 1, 3 i 5)
- Raspon: `1-5` (datoteke od 1 do 5)
- Sve: `*` (sve datoteke)
- Povratak: `X`

### 11.2 Implementacija u CLI

```python
def get_file_selection(file_list):
    """Omogućuje batch odabir datoteka."""
    print("\nDostupne datoteke:")
    for i, f in enumerate(file_list, 1):
        print(f"  [{i}] {f}")
    
    print("\nOdaberi datoteke (npr. '1', '1,3,5', '1-5', '*' za sve, 'X' za povratak):")
    selection = input("> ").strip()
    
    if selection.upper() == 'X':
        return None
    
    indices = parse_selection(selection, len(file_list))
    return [file_list[i] for i in indices]

def parse_selection(selection, max_count):
    """Parsira '1,3,5' ili '1-5' ili '*' u listu indeksa."""
    if selection == '*':
        return list(range(max_count))
    
    indices = []
    parts = selection.split(',')
    for part in parts:
        if '-' in part:
            start, end = part.split('-')
            indices.extend(range(int(start)-1, int(end)))
        else:
            indices.append(int(part)-1)
    
    return sorted(set(i for i in indices if 0 <= i < max_count))
```

### 11.3 Batch obrada u svakoj fazi

**Faza 1 (Konverzija):**
```
[1] Konverzija dokumenata → TXT/MD
├── Lista datoteka iz work/input/
├── Odabir: 1,3,5 (batch)
├── Odabir formata: [1] TXT, [2] MD
└── Batch konverzija svih odabranih datoteka
```

**Faza 2 (Čišćenje + memorija):**
```
[2] Čišćenje tehničkog šuma + kreiranje memorije
├── Lista sirovih .txt/.md iz work/output/
├── Odabir: 1-5 (batch)
└── Batch čišćenje + auto-kreiranje memorija.json za svaku knjigu
```

**Faza 3 (Prevođenje):**
```
[3] Prevođenje (LLM)
├── Lista [fixed] datoteka
├── Odabir: * (sve)
└── Batch prevođenje s učitavanjem memorije za svaku knjigu
```

**Faza 4 (TTS):**
```
[4] TTS sinteza → MP3 (po paragrafima)
├── Lista prevedenih datoteka
├── Odabir: 2,4 (batch)
└── Batch TTS sinteza — svaki paragraf u zasebni MP3
```

### 11.4 Progress tracking za batch

Za batch operacije prikazuje se ukupni progress:
```
[INFO] Pokrećem batch konverziju za 5 datoteka...
[1/5] Konvertiram Dune.epub → Dune.txt ... OK
[2/5] Konvertiram Foundation.epub → Foundation.txt ... OK
[3/5] Konvertiram Neuromancer.epub → Neuromancer.txt ... OK
[4/5] Konvertiram Snow Crash.epub → Snow Crash.txt ... OK
[5/5] Konvertiram Hyperion.epub → Hyperion.txt ... OK
[DONE] Batch konverzija završena: 5/5 uspješno
```

---

## 12. MULTI-CHECKPOINT SUSTAV PERZISTENCIJE

### 12.1 Struktura `work/state/translation_checkpoints.json`

```json
{
  "active_books": [
    {
      "id": "dune_fixed",
      "title": "Dune",
      "book_dir": "work/output/Dune",
      "source_file": "work/output/Dune/Dune [fixed].txt",
      "target_file": "work/translated/Dune/Dune.txt",
      "config_file": "work/output/Dune/config.yaml",
      "memorija_file": "work/output/Dune/Dune_memorija.json",
      "total_paragraphs": 2847,
      "current_paragraph": 749,
      "percent": 26.31,
      "last_updated": "2026-07-30T14:22:11"
    },
    {
      "id": "clean_code_fixed",
      "title": "Clean Code",
      "book_dir": "work/output/Clean_Code",
      "source_file": "work/output/Clean_Code/Clean Code [fixed].md",
      "target_file": "work/translated/Clean_Code/Clean Code.md",
      "config_file": "work/output/Clean_Code/config.yaml",
      "memorija_file": "work/output/Clean_Code/Clean_Code_memorija.json",
      "total_paragraphs": 1204,
      "current_paragraph": 855,
      "percent": 71.01,
      "last_updated": "2026-07-29T21:07:43"
    }
  ]
}
```

### 12.2 Ključna svojstva
- **Izolacija povijesti:** nastavak jedne knjige **nikada** ne dira checkpoint druge.
- **Maksimalan broj paralelnih naslova:** neograničen (preporuka ≤10 radi preglednosti).
- **Real-time ažuriranje:** nakon svakog uspješno prevedenog odlomka.
- **Atomski zapis:** `json.dump` u privremenu datoteku pa `os.replace` — zaštita od korupcije pri nestanku struje.

### 12.3 Nastavak rada
Kada korisnik odabere checkpoint iz glavnog izbornika:
1. Učitavaju se svi parametri (izvorišna datoteka, config.yaml, memorija.json).
2. Čita se `current_paragraph`.
3. Prevod se nastavlja **točno od tog odlomka**.
4. Tekst se **append-a** u postojeću `work/translated/` datoteku (ne prepisuje).

---

## 13. 1-CLICK TEST SUSTAV

### 13.1 Svrha

Sustav pamti **zadnje testne parametre** kako bi se moglo brzo ponoviti ista operacija s različitim modelom (za usporedbu kvalitete prijevoda).

### 13.2 Struktura `work/state/last_test.json`

```json
{
  "timestamp": "2026-07-30T14:22:11",
  "book_title": "Dune",
  "book_dir": "work/output/Dune",
  "book_file": "work/output/Dune/Dune [fixed].txt",
  "config_file": "work/output/Dune/config.yaml",
  "memorija_file": "work/output/Dune/Dune_memorija.json",
  "model": "local-model",
  "api_provider": "lm_studio",
  "test_mode": "paragraphs",
  "test_count": 2,
  "description": "Prevođenje knjige Dune - prva 2 paragrafa"
}
```

### 13.3 Prikaz u glavnom izborniku

Ako postoji `last_test.json`, u glavnom izborniku se prikazuje:

```
╔══════════════════════════════════════════════════╗
║  GLAVNI IZBORNIK                                 ║
╠══════════════════════════════════════════════════╣
║  [Y] TEST: Prevođenje knjige Dune - prva 2 paragrafa
║      (Model: local-model, Provider: lm_studio)   ║
║                                                  ║
║  [1] Konverzija dokumenata → TXT/MD              ║
║  [2] Čišćenje tehničkog šuma + memorija          ║
║  [3] Prevođenje (LLM)                            ║
║  [4] TTS sinteza u MP3 (po paragrafima)          ║
║  [X] Izlaz                                       ║
╚══════════════════════════════════════════════════╝
```

### 13.4 Podizbornik "Napravi testni prevod"

Unutar Faze 3 (Prevođenje) dodaje se podizbornik:

```
[3] Prevođenje (LLM)
├── [1] Napravi testni prevod
│   ├── Odabir datoteke: [lista [fixed] datoteka]
│   ├── Odabir profila: [1] SF, [2] IT, [3] General
│   ├── Odabir testa:
│   │   ├── [1] Prvih N paragrafa (default: 2)
│   │   ├── [2] Prvih N rečenica (default: 5)
│   │   └── [3] Slučajnih N odlomaka (default: 3)
│   └── Unesi broj: [input]
│
├── [2] Prevedi cijelu knjigu
└── [X] Povratak
```

---

## 14. TRORAZINSKO LOGIRANJE

### 14.1 Razine logiranja

| Razina | Parametar | Default | Opis |
|---|---|---|---|
| **Osnovno** | Uvijek aktivno | ON | Bilježi početak/kraj svake knjige, greške, checkpoint ažuriranja |
| **Verbatim** | `LOG_VERBATIM` | OFF | Detaljni trace svake akcije, ulazni/izlazni podaci |
| **LLM Debug** | `LOG_LLM_RESPONSES` | OFF | Snima pune LLM odgovore za analizu halucinacija |

### 14.2 Struktura log datoteka

```
work/logs/
├── 2026-07-30_142211_dynamic_book_translator_v4.3.0_debug.log
├── 2026-07-30_142211_dynamic_book_translator_v4.3.0_verbatim.log
└── llm_responses/
    ├── Dune/
    │   ├── chunk_001.json
    │   ├── chunk_002.json
    │   └── ...
    └── Clean_Code/
        └── ...
```

### 14.3 Format log headera

Svaka log datoteka počinje s headerom:

```
DYNAMIC BOOK TRANSLATOR  v4.3.0
LOG PATH:    C:\Users\mamba\project\work\logs\2026-07-30_142211_dynamic_book_translator_v4.3.0_debug.log
DATE:        2026-07-30 14:22:11
------------------------------------------------------------

14:22:11 [INFO] Pokrećem prijevod knjige: Dune
14:22:11 [INFO] Koristim model: local-model (provider: lm_studio)
14:25:33 [INFO] Završeno prevođenje knjige: Dune (2847 odlomaka, 100%)
14:25:33 [INFO] Checkpoint ažuriran: Dune → 100%
```

### 14.4 Implementacija logiranja

```python
import logging
from datetime import datetime
import json
import os

def setup_logging():
    """Inicijalizira log sustav s headerom."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    script_name_safe = SCRIPT_NAME.lower().replace(' ', '_')
    log_filename = f"{timestamp}_{script_name_safe}_v{SCRIPT_VERSION}_debug.log"
    log_path = os.path.join(LOGS_DIR, log_filename)
    
    # Header
    header = f"""
{SCRIPT_NAME.upper()}  v{SCRIPT_VERSION}
LOG PATH:    {os.path.abspath(log_path)}
DATE:        {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
------------------------------------------------------------
"""
    
    # Osnovni logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    # Zapiši header
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write(header)
    
    # Verbatim logger (ako je uključen)
    if LOG_VERBATIM:
        verbatim_filename = f"{timestamp}_{script_name_safe}_v{SCRIPT_VERSION}_verbatim.log"
        verbatim_path = os.path.join(LOGS_DIR, verbatim_filename)
        
        verbatim_logger = logging.getLogger('verbatim')
        verbatim_logger.setLevel(logging.DEBUG)
        vh = logging.FileHandler(verbatim_path, encoding='utf-8')
        vh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S'))
        verbatim_logger.addHandler(vh)
    
    # LLM response logger
    if LOG_LLM_RESPONSES:
        os.makedirs(f"{LOGS_DIR}/llm_responses", exist_ok=True)

def log_basic(message):
    """Osnovni log - uvijek aktivan."""
    logging.info(message)

def log_verbatim(message):
    """Detaljni trace - samo ako LOG_VERBATIM=True."""
    if LOG_VERBATIM:
        logging.getLogger('verbatim').debug(message)

def log_llm_response(book_title, chunk_index, prompt, response):
    """Snima LLM odgovor - samo ako LOG_LLM_RESPONSES=True."""
    if LOG_LLM_RESPONSES:
        book_dir = f"{LOGS_DIR}/llm_responses/{book_title}"
        os.makedirs(book_dir, exist_ok=True)
        
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "chunk_index": chunk_index,
            "prompt": prompt,
            "response": response
        }
        
        with open(f"{book_dir}/chunk_{chunk_index:03d}.json", 'w', encoding='utf-8') as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
```

## 14.5 Reasoning toggle

Parametar `ENABLE_REASONING` kontrolira hoće li se LLM odgovori čistiti od `

Parametar `ENABLE_REASONING` kontrolira hoće li se LLM odgovori čistiti od reasoning tagova. Kada je `enable_reasoning: false` u `config.yaml`, skripta automatski uklanja sve sadržaje između `<think>` i `</think>` tagova te `<reasoning>` i `</reasoning>` tagova prije spremanja prijevoda. Ovo je važno jer neki modeli generiraju interno razmišljanje koje ne treba završiti u finalnom prijevodu.

---

## 15. VANJSKI API INTEGRACIJA

### 15.1 Podržani provideri

| Provider | API Base URL | Autentikacija | Napomene |
|---|---|---|---|
| `lm_studio` | `http://127.0.0.1:1234/v1` | Nema | Lokalni, OpenAI-kompatibilan |
| `openai` | `https://api.openai.com/v1` | `API_KEY` | GPT-4, GPT-3.5 |
| `gemini` | `https://generativelanguage.googleapis.com/v1beta` | `API_KEY` | Google Gemini |
| `qwen` | `https://dashscope.aliyuncs.com/api/v1` | `API_KEY` | Alibaba Qwen |

### 15.2 Konfiguracija

Globalni API parametri definirani su u `main.py`:
- `API_PROVIDER` — odabir providera
- `API_BASE_URL` — endpoint URL
- `API_KEY` — API ključ (prazno za lokalni LM Studio)
- `DEFAULT_MODEL` — naziv modela

### 15.3 Per-book API override

Svaka knjiga može imati vlastiti API provider i model u `config.yaml`:
- `api_provider` — override globalnog providera
- `model` — override globalnog modela
- `api_key_override` — opcionalni API ključ specifičan za knjigu

### 15.4 Unificirani API client

Skripta koristi unificirani API client koji automatski prilagođava poziv prema odabranom provideru. Za LM Studio i OpenAI koristi se OpenAI-kompatibilan format. Za Gemini i Qwen implementirani su specifični adapteri.

---

## 16. AUTOMATSKA DETEKCIJA LIKOVA — ANALIZA IZVEDIVOSTI

### 16.1 Pitanje

Postoji li mogućnost prilikom obrade dokumenta da se pronađu svi likovi koji se spominju u dokumentu, kako bi se kasnije mogao jednostavnije napraviti prompt (zbog prevoda ispravnog gendera) — ili to mora odraditi AI?

### 16.2 Odgovor

**Da, postoji mogućnost automatske detekcije likova, ali s ograničenjima.**

#### Opcija A: Heuristička detekcija (bez AI)

**Prednosti:**
- Brzo (lokalno, bez API poziva)
- Besplatno
- Radi offline

**Nedostaci:**
- Niska preciznost (~60-70%)
- Ne može odrediti rod automatski
- Propušta složena imena (npr. "Paul Atreides" vs "Paul")
- Ne razlikuje likove od sporednih imena (gradovi, organizacije)

**Implementacija:**
Koristi regex za ekstrakciju capitalized words nakon točke ili u dijalogu, filtrira česte riječi (ne imena), vraća najčešća imena.

#### Opcija B: AI-bazirana detekcija (preporučeno)

**Prednosti:**
- Visoka preciznost (~95%)
- Može odrediti rod iz konteksta
- Razlikuje likove od ostalih imena
- Razumije kontekst (npr. "Dr. Smith" vs "Smith")

**Nedostaci:**
- Zahtijeva API poziv (troši token)
- Sporije od heuristike

**Implementacija:**
Šalje se prvi poglavlje knjige na LLM s promptom: "Izdvoji sve likove iz teksta, odredi njihov rod i napiši kratki opis."

### 16.3 Preporuka

Za produkcijski sustav preporučuje se **Opcija B (AI-bazirana detekcija)** jer:
- Preciznost je kritična za točan prijevod roda.
- Jednom detektirani likovi spremaju se u `memorija.json` i koriste se za sve buduće prijevode.
- Trošak API poziva je jednokratan (samo pri prvom čišćenju).

### 16.4 Implementacija u Fazi 2

Prilikom čišćenja tehničkog šuma (Faza 2), skripta može opcionalno pokrenuti AI detekciju likova:
1. Čita prvi poglavlje `[fixed]` datoteke.
2. Šalje na LLM s promptom za ekstrakciju likova.
3. Automatski popunjava `CHARACTERS` sekciju u `memorija.json`.
4. Korisnik može ručno doraditi ako treba.

---

## 17. .GITIGNORE SPECIFIKACIJA

### 17.1 Princip

Root direktorij projekta sadrži samo kod i globalnu konfiguraciju. Svi radni podaci su u `work/` direktoriju koji se **u potpunosti ignorira** u Git-u.

### 17.2 Kompletni `.gitignore`

```gitignore
# ============================================================
# Python
# ============================================================
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
ENV/
.venv

# ============================================================
# Radni direktorij (svi podaci)
# ============================================================
work/

# ============================================================
# Virtualno okruženje
# ============================================================
venv/
ENV/
env/

# ============================================================
# IDE i editori
# ============================================================
.vscode/
.idea/
*.swp
*.swo
*~
.DS_Store

# ============================================================
# Logovi i privremene datoteke
# ============================================================
*.log
*.tmp
*.bak

# ============================================================
# OS specifično
# ============================================================
Thumbs.db
.DS_Store
desktop.ini
```

### 17.3 .gitkeep datoteke

Za očuvanje strukture direktorija u Git-u (iako je `work/` ignoriran), koriste se `.gitkeep` datoteke u praznim direktorijima koji su dio koda:

```
config/
├── .gitkeep
├── profile_sf_literature.yaml
├── profile_it_technical.yaml
└── profile_general.yaml
```

### 17.4 Što se commita u Git

- `main.py` — glavna skripta
- `./start` — bootstrap skripta
- `requirements.txt` — liste paketa
- `.gitignore` — ignore pravila
- `config/*.yaml` — globalni profili
- `README.md` — dokumentacija (opcionalno)

### 17.5 Što se NE commita u Git

- `work/` — svi radni podaci (input, output, translated, audiobooks, state, logs)
- `venv/` — virtualno okruženje
- `__pycache__/` — Python cache
- `*.log` — log datoteke
- `*.mp3` — audio datoteke

---

## 18. SIGURNOSNO RUKOVANJE GREŠKAMA

### 18.1 Tipične greške i odgovor sustava

| Greška | Uzrok | Reakcija |
|---|---|---|
| `HTTP 500` | LM Studio crash / OOM na GPU | Fallback na izvorni EN tekst + zapis checkpointa |
| `Timeout` | Zagušenje VRAM-a (RTX 5080) | Retry 2x, pa fallback |
| `ConnectionRefused` | LM Studio nije pokrenut | Poruka korisniku + povratak u izbornik |
| `JSONDecodeError` | Koruptiran odgovor LLM-a | Čišćenje XML tagova + retry |
| `FileNotFoundError` | Nedostaje `config/` ili `work/` | Auto-kreiranje direktorija |
| `UnicodeDecodeError` | Sirovi PDF s čudnim encodingom | Fallback na `latin-1` pa retry |
| `YAMLError` | Koruptiran `config.yaml` | Poruka korisniku + povratak u izbornik |

### 18.2 Fallback lanac

```
1. Pokušaj 1 → API poziv
2. Ako fail → Retry (2x s 5s delay)
3. Ako i dalje fail → Pass-through (kopija EN teksta)
4. Zapis u checkpoint + log u work/logs/
5. Povratak u izbornik — korisnik može restartati LM Studio i nastaviti
```

### 18.3 Logiranje grešaka

Sve greške se zapisuju u `work/logs/` s vremenskom oznakom, nazivom knjige, indeksom odlomka i tipom greške. Osnovni log (`*_debug.log`) uvijek je aktivan. Verbatim log (`*_verbatim.log`) samo ako je `LOG_VERBATIM=True`.

### 18.4 Atomski zapis checkpointa

Pri ažuriranju `translation_checkpoints.json` skripta koristi atomski zapis:
1. Zapiše u privremenu datoteku `translation_checkpoints.json.tmp`.
2. Koristi `os.replace()` za atomsku zamjenu.
3. Ako se dogodi crash tijekom zapisa, originalna datoteka ostaje netaknuta.

---

## 19. PROTOKOL SIGURNOG IZLAZA

### 19.1 Tok

```
Korisnik: X
Sustav:   [UPOZORENJE] Pokrenuli ste izlaz iz aplikacije.
          Trenutni rad u batchu bit će pauziran.
          Jeste li sigurni da želite izaći? (Y/N):
```

### 19.2 Grananje

**`Y` / `y`:**
1. Flush svih otvorenih file buffera.
2. Atomski zapis zadnjeg checkpointa u `work/state/translation_checkpoints.json`.
3. Zatvaranje HTTP sesija prema LLM API-ju.
4. `sys.exit(0)`.

**`N` / `n` / bilo što drugo:**
1. Poništenje izlaza.
2. Osvježavanje glavnog izbornika.
3. Nastavak rada bez gubitka stanja.

### 19.3 Sigurnosne provjere

Pri izlazu skripta provjerava:
- Postoji li aktivan batch proces u tijeku?
- Postoje li nespremljeni checkpointi?
- Postoje li otvorene datoteke koje nisu zatvorene?

Ako bilo što od navedenoga postoji, skripta prikazuje dodatno upozorenje i traži eksplicitnu potvrdu.

---

## 20. HEADER METAPODACI U PREVEDENOM TEKSTU

### 20.1 Svrha

Svaki prevedeni tekst dobiva **header** s metapodacima o modelu, knjizi i vremenu nastanka. Ovo je kritično za:
- **Verzionalnost:** korisnik zna koji model je korišten.
- **Debug:** ako je prijevod loš, korisnik može provjeriti parametre.
- **Audit:** tko, što, kada, kako.

### 20.2 Struktura headera

```
================================================================================
DYNAMIC BOOK TRANSLATOR & PARSER v4.3.0
================================================================================
Knjiga:        Dune
Autor:         Frank Herbert
Original:      Dune.epub
================================================================================
Model:         local-model
Provider:      lm_studio
Kvantizacija:  Q4_K_M (ako je dostupno)
Temperature:   0.25
Top-p:         0.80
================================================================================
Prijevod započet:  2026-07-30 14:22:11
Prijevod završen:  2026-07-30 15:45:33
Ukupno odlomaka:   2847
================================================================================

[POČETAK TEKSTA]
Paul je stajao na rubu pustinje...
```

### 20.3 Dinamičko dohvaćanje informacija o modelu

Skripta pokušava dohvatiti informacije o modelu od API-ja:
- Za LM Studio: `GET /v1/models` vraća listu modela s detaljima.
- Za OpenAI/Gemini/Qwen: API vraća model info u response headeru.
- Ako nije dostupno, koristi se `DEFAULT_MODEL` iz konfiguracije.

### 20.4 Implementacija

Header se generira automatski pri završetku prijevoda i sprema na vrh `work/translated/<Knjiga>/<Knjiga>.txt|md`. Sadrži:
- Naziv i verzija skripte (iz `main.py` konfiguracije).
- Podaci o knjizi (iz `config.yaml`).
- Podaci o modelu (iz API-ja ili konfiguracije).
- Vremenske oznake početka i završetka.
- Ukupni broj odlomaka.

---

## KRAJ DOKUMENTACIJE

Ovo je kompletna tehnička specifikacija sustava **DYNAMIC BOOK TRANSLATOR & PARSER V4.3-PRO**. Dokument pokriva:

- ✅ Strukturu direktorija s `work/` izolacijom
- ✅ YAML konfiguraciju s multi-line promptovima
- ✅ Per-book direktorije s memorijom vezanom za `[fixed]` datoteke
- ✅ Batch processing u svim fazama
- ✅ MP3 po paragrafima u direktoriju knjige
- ✅ Multi-checkpoint perzistenciju
- ✅ 1-Click test sustav
- ✅ Trorazinsko logiranje s formatiranim headerom
- ✅ Vanjski API integraciju (LM Studio, OpenAI, Gemini, Qwen)
- ✅ Automatsku detekciju likova (AI-bazirana preporuka)
- ✅ `.gitignore` specifikaciju
- ✅ Sigurnosno rukovanje greškama
- ✅ Protokol sigurnog izlaza
- ✅ Header metapodatke u prevedenom tekstu

**Sljedeći korak:** Implementacija Python koda (`main.py`, `./start`, `requirements.txt`, primjeri YAML konfiguracija).

