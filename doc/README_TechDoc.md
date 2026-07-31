# TEHNIČKA DOKUMENTACIJA SUSTAVA — KOMPLETNA SPECIFIKACIJA

## DYNAMIC BOOK TRANSLATOR & PARSER — V0.4
**Datum:** 31. srpnja 2026.  
**Autor:** mamba  
**Platforma:** Windows + Git Bash (MSYS2/MinGW)  
**Jezik:** Python 3.10+  
**Status:** Produkcijska specifikacija — Refactoring release

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
13. [TEST sustav — brzi testni prijevod](#13-test-sustav--brzi-testni-prijevod)
14. [Trorazinsko logiranje](#14-trorazinsko-logiranje)
15. [Vanjski API integracija](#15-vanjski-api-integracija)
16. [Automatska detekcija likova — analiza izvedivosti](#16-automatska-detekcija-likova)
17. [.gitignore specifikacija](#17-gitignore-specifikacija)
18. [Sigurnosno rukovanje greškama](#18-sigurnosno-rukovanje-greškama)
19. [Protokol sigurnog izlaza](#19-protokol-sigurnog-izlaza)
20. [Header metapodaci u prevedenom tekstu](#20-header-metapodaci-u-prevedenom-tekstu)
21. [Refactoring — modularna arhitektura](#21-refactoring--modularna-arhitektura)
22. [Upravljanje direktorijima i datotekama — unificirana metoda](#22-upravljanje-direktorijima-i-datotekama--unificirana-metoda)
23. [MP3 imenovanje i metapodaci](#23-mp3-imenovanje-i-metapodaci)

---

## 1. SAŽETAK SUSTAVA

Sustav je četverofazni CLI alat namijenjen automatiziranoj pripremi, prijevodu i audio-sintezi knjiga različitih žanrova (književna SF literatura, stručna IT literatura, općenito). Ključne karakteristike:

- **Bootstrap provjera okruženja** pri svakom pokretanju putem `./start` datoteke.
- **Unificirana `X` navigacija** kroz sve razine izbornika s kretanjem kursorskim tipkama.
- **Per-book direktoriji** — svaka knjiga ima vlastiti direktorij s izoliranom konfiguracijom i memorijom.
- **YAML konfiguracija** — sva vanjska konfiguracija isključivo u YAML formatima.
- **Čista modularna struktura** — `app/` direktorij s odvojenim modulima, `main.py` kao orkestracija.
- **Memorija vezana za obrađeni tekst** — JSON s likovima/glosarom kreira se uz `[fixed]` datoteku.
- **Batch processing** — višestruki odabir datoteka u svakoj fazi.
- **MP3 po paragrafima** — imenovanje `001_Ch01_part001.mp3` s embedded ID3 metapodacima.
- **Multi-checkpoint perzistencija** — do 6+ paralelnih naslova s neovisnim postotkom napretka.
- **TEST sustav** — brzi testni prijevod za odlomak / paragraf / rečenicu, s opcionalnim headerom (uključen/isključen u OPCIJAMA).
- **Trorazinsko logiranje** — osnovno, verbatim i LLM response debug.
- **Vanjski API integracija** — lokalni LM Studio, lokalni Ollama, Ollama cloud, OpenAI, Gemini, Qwen i ostali; API ključevi u `.env` datoteci.
- **`.env` zaštita** — API ključevi nikada nisu u kodu ni YAML-u, čitaju se isključivo iz `.env` (u `.gitignore`).
- **Dvostruka potvrda izlaza** radi zaštite od slučajnog prekida.
- **Fallback mehanizam** pri `HTTP 500` ili `Timeout` greškama lokalnog LLM-a.
- **Unificirana metoda za rad s direktorijima** — jedna metoda za kreiranje, detekciju i suffix-increment.

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
mutagen>=1.47.0
python-dotenv>=1.0.0
```

> **Napomena:** `mutagen` za ID3 metapodatke u MP3; `python-dotenv` za čitanje `.env` datoteke s API ključevima.

---

## 3. STRUKTURA DIREKTORIJA I DATOTEKA

### 3.1 Princip organizacije

Root direktorij projekta sadrži **isključivo kod i globalnu konfiguraciju**. Svi radni direktoriji smješteni su unutar `work/` direktorija. Python moduli su isključivo unutar `app/` direktorija.

### 3.2 Kompletna struktura

```
project_root/
│
├── ./start                          # Bash bootstrap skripta (ulazna točka)
├── main.py                          # Glavna Python skripta (orkestracija, poziva app/ module)
├── requirements.txt                 # Lista pip paketa
├── .gitignore
│
├── app/                             # SVI Python moduli (refactoring)
│   ├── config_loader.py             # Učitavanje i spajanje YAML konfiguracije
│   ├── menu.py                      # CLI izbornici s kursorskom navigacijom
│   ├── document_processor.py        # Faza 1: konverzija dokumenata
│   ├── text_cleaner.py              # Faza 2: čišćenje [fixed] + kreiranje memorije
│   ├── translator.py                # Faza 3: LLM prevođenje (odlomak/paragraf/rečenica)
│   ├── tts_engine.py                # Faza 4: TTS sinteza u MP3
│   ├── file_manager.py              # Unificirana metoda za direktorije i datoteke
│   ├── checkpoint.py                # Multi-checkpoint perzistencija
│   ├── logger.py                    # Trorazinsko logiranje
│   └── utils.py                     # Zajedničke pomoćne funkcije
│
├── config/                          # Globalni konfiguracijski profili (YAML)
│   ├── settings.yaml                # Globalne postavke (API, TTS, direktoriji, logiranje)
│   ├── profile_sf_literature.yaml
│   ├── profile_it_technical.yaml
│   └── profile_general.yaml
│
└── work/                            # Svi radni direktoriji
    ├── input/
    ├── output/
    │   └── Dune/
    │       ├── Dune.txt
    │       ├── Dune [fixed].txt
    │       ├── config.yaml
    │       └── Dune_memorija.json
    ├── translated/
    │   └── Dune/
    │       ├── Dune.txt                              # Produkcijski prijevod — ČISTI TEKST, bez headera (spreman za TTS→MP3)
    │       └── Dune_test_2026-07-31_110820.txt       # Testni prijevod — s opcionalnim headerom (uklj/isklj u OPCIJAMA)
    ├── audiobooks/
    │   └── Dune/
    │       ├── 001_Ch01_part001.mp3
    │       ├── 002_Ch02_part001.mp3
    │       └── ...
    ├── state/
    │   ├── translation_checkpoints.json
    │   └── last_test.json
    └── logs/
        ├── 2026-07-31_110000_dynamic_book_translator_v0.4_debug.log
        └── llm_responses/
```

### 3.3 Ključna pravila strukture

- `app/` — isključivo Python moduli, nema konfiga ni podataka.
- `config/` — isključivo YAML datoteke; nema hardkodiranih vrijednosti u kodu.
- `work/` — svi radni podaci, potpuno ignoriran u `.gitignore`.
- `main.py` — jedina ulazna točka koja importa module iz `app/`.

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

---

## 5. KONFIGURACIJSKI SUSTAV — YAML FORMAT

### 5.1 Princip

**Sva konfiguracija je isključivo u YAML datotekama.** Nema hardkodiranih vrijednosti u Python kodu. Konfiguracija se dijeli na:

- **`config/settings.yaml`** — globalne postavke (API, TTS, direktoriji, logiranje, sanitizacija).
- **`config/profile_*.yaml`** — predlošci za žanrove (SF, IT, general).
- **`work/output/<Knjiga>/config.yaml`** — per-book konfiguracija generirana iz predloška.

### 5.2 Globalne postavke — `config/settings.yaml`

```yaml
# ============================================================
# GLOBALNE POSTAVKE
# ============================================================

project:
  name: "Dynamic Book Translator"
  version: "0.4.0"

directories:
  work: "./work"
  input: "./work/input"
  output: "./work/output"
  translated: "./work/translated"
  audiobooks: "./work/audiobooks"
  state: "./work/state"
  logs: "./work/logs"
  config: "./config"

api:
  provider: "lm_studio"       # lm_studio | openai | gemini | qwen
  base_url: "http://127.0.0.1:1234/v1"
  key: ""
  model: ""                   # prazno = auto-detect
  auto_detect_model: true
  timeout: 120

logging:
  verbatim: false
  llm_responses: false
  enable_reasoning: false

tts:
  engine: "edge-tts"
  narrator:
    voice: "hr-HR-SreckoNeural"
    rate: "+0%"
    pitch: "+0Hz"
  dialog:
    use_different_voice: true
    voice: "hr-HR-GabrijelaNeural"
    rate: "+2%"
    pitch: "+0Hz"
  dramatic_mode:
    enabled: true
    keywords_anxious: ["run", "explosion", "danger", "dead", "weapon", "fast", "shot", "kill"]
    rate_modifier_anxious: "+15%"

sanitization:
  replace_spaces_with: "-"
  prefix_padding: 3

chapter_patterns:
  - "^(CHAPTER|Chapter|POGLAVLJE|Poglavlje)\\s+\\d+"
  - "^(EPILOGUE|PROLOGUE|Epilogue|Prologue)"
  - "^[A-Z\\s]{4,25}$"
```

### 5.3 Per-book konfiguracija — `work/output/Dune/config.yaml`

```yaml
book_title: "Dune"
author: "Frank Herbert"
original_file: "Dune.epub"

api_provider: "lm_studio"
model: "local-model"
api_key_override: ""

system_prompt: |
  Ti si stručni prevoditelj s engleskog na hrvatski za žanr znanstvene fantastike.
  ...

parameters:
  temperature: 0.25
  top_p: 0.80
  top_k: 15
  min_p: 0.05
  max_tokens: 4096
  repeat_penalty: 1.1

chunking:
  max_tokens_per_chunk: 1500
  overlap_tokens: 100

memorija_file: "Dune_memorija.json"
enable_reasoning: false

created_at: "2026-07-31T11:00:00"
updated_at: "2026-07-31T11:00:00"
```

### 5.4 Učitavanje YAML konfiguracije

Modul `app/config_loader.py` odgovoran je za učitavanje i spajanje konfiguracije:

```python
import yaml
from pathlib import Path

def load_global_config(config_dir: Path) -> dict:
    """Učitava config/settings.yaml."""
    with open(config_dir / "settings.yaml", 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def load_book_config(book_dir: Path) -> dict:
    """Učitava config.yaml iz direktorija knjige."""
    with open(book_dir / "config.yaml", 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def merge_config(global_cfg: dict, book_cfg: dict) -> dict:
    """Spaja globalnu i per-book konfiguraciju; book_cfg ima prioritet."""
    merged = global_cfg.copy()
    merged.update(book_cfg)
    return merged
```

---

## 6. ARHITEKTURA GLAVNOG IZBORNIKA (CLI)

### 6.1 Navigacijski princip

- **Kursorske tipke** (↑ ↓) za kretanje kroz stavke.
- **Razmaknica ili Enter** za potvrdu odabira.
- **`X`** na dnu svakog (pod)izbornika za povratak na prethodni izbornik.
- U glavnom izborniku `X` pokreće **sigurnosni izlaz s potvrdom Y/N**.
- Svi izbornici su **CLI "GUI"** — vizualni highlight aktivne stavke.

### 6.2 Stablo izbornika

```
[GLAVNI IZBORNIK]
│
├── [Aktivni checkpointi]  ← dinamički blok, prikazuje se samo ako postoje nedovršeni prijevodi
│   ├── Ukupno nedovršenih: N prijevoda
│   ├── [1] Nastavi: Dune (Frank Herbert) — 26.31%  [↵ 1-click nastavak]
│   ├── [2] Nastavi: Foundation (Isaac Asimov) — 71.01%
│   └── ...
│
├── [Y] BRZI TEST: Dune — 2 paragrafa  ← samo ako postoji last_test.json
│       (Model: local-model | Paragraf | Header: DA)
│
├── [1] Konverzija dokumenata → TXT/MD
│
├── [2] Čišćenje tehničkog šuma ([fixed]) + memorija
│
├── [3] Prevođenje (LLM)
│   ├── [1] Napravi testni prevod       ← BRZI TEST (granularnost iz OPCIJA)
│   ├── [2] Prevedi cijelu knjigu
│   └── [0] Opcije
│       ├── [1] Header u testnoj datoteci:  [DA ▼] / [NE ▼]
│       ├── [2] Granularnost segmenata:     [Paragraf ▼] / [Odlomak ▼] / [Rečenica ▼]
│       └── [X] Povratak
│
├── [4] TTS sinteza → MP3
│   ├── [1] Zasebne datoteke po odlomcima (001_Ch01_part001.mp3...)
│   └── [2] Jedna datoteka za cijelu knjigu
│
└── [X] Izlaz
    └── "Jeste li sigurni? (Y/N)"
```

### 6.3 Batch odabir

- Pojedinačni: `1`
- Višestruki: `1,3,5`
- Raspon: `1-5`
- Sve: `*`
- Povratak: `X`

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
1. Čitanje datoteka iz `work/input/`.
2. Prikaz numerirane liste s kursorskom navigacijom.
3. Odabir formata izvoza (`.txt` ili `.md`).
4. Parsiranje → čišćenje binarnih artefakata → normalizacija UTF-8.
5. Kreiranje direktorija `work/output/<NazivKnjige>/` putem unificirane metode (`app/file_manager.py`).
6. Zapis u `work/output/<NazivKnjige>/<NazivKnjige>.txt|md`.

---

## 8. FAZA 2 — ČIŠĆENJE TEHNIČKOG ŠUMA (`[fixed]`) + KREIRANJE MEMORIJE

### 8.1 Problem
PDF i EPUB izvori često umeću headere/footere i prelomljene rečenice na granicama stranica. Algoritam detektira ponavljajuće obrasce (≥3 pojave na istoj poziciji) i uklanja ih.

### 8.2 Algoritam čišćenja
1. Detekcija ponavljajućih headera/footera (frekvenijska analiza).
2. Uklanjanje izoliranih brojeva stranica (`^\s*\d+\s*$`).
3. Spajanje prelomljenih rečenica.
4. Normalizacija whitespace-a.

### 8.3 Izlaz
```
work/input/Dune.epub
  → work/output/Dune/Dune.txt
    → work/output/Dune/Dune [fixed].txt
    → work/output/Dune/Dune_memorija.json  (auto-kreiran s placeholderima)
```

### 8.4 Automatsko kreiranje memorije

Uz `[fixed]` datoteku automatski se kreira `Dune_memorija.json`:

```json
{
  "CHARACTERS": {},
  "GLOSSARY": {},
  "GRAMMAR_FIXES": {}
}
```

Korisnik može ručno popuniti memoriju prije Faze 3.

---

## 9. FAZA 3 — PREVOĐENJE PREKO LOKALNOG LLM-A

### 9.1 Razlika: TEST vs. PRODUKCIJA

| Svojstvo | TEST prijevod | Produkcijski prijevod |
|---|---|---|
| **Header u outputu** | ⚙️ OPCIJA — uključen ili isključen (default: DA) | ❌ NIKAD — čisti tekst spreman za TTS→MP3 |
| **Ime izlazne datoteke** | `<naziv>_test_<timestamp>.txt` | `<naziv>.txt` |
| **Odabir količine** | Odlomak / Paragraf / Rečenica (dropdown u OPCIJAMA) | Cijela knjiga (isti granularni način slanja AI-u) |
| **Output direktorij** | `work/translated/<Knjiga>/` | `work/translated/<Knjiga>/` |
| **Granularnost slanja AI-u** | Definira se u OPCIJAMA (odlomak/paragraf/rečenica) | Ista postavka iz OPCIJA — vrijedi i za TEST i za produkciju |
| **Sprema last_test.json** | ✅ DA | ❌ NE |
| **Checkpoint (nastavak)** | ❌ NE (kratko, ne treba) | ✅ DA — atomski zapis nakon svakog segmenta |

> **Ključno pravilo:** Produkcijska datoteka je uvijek **čisti prevedeni tekst** bez ikakvih dodataka — jer se direktno provlači kroz TTS i pretvara u MP3. Header u MP3 audiobuku ne smije postojati.

### 9.2 Granularnost — OPCIJE (zajedničke za TEST i produkciju)

Granularnost definira kako se tekst šalje AI modelu. Postavlja se u OPCIJAMA izbornika `[3] → [0] Opcije`:

```
OPCIJE — Prevođenje:
  ┌─────────────────────────────────────────────┐
  │ [1] Header u testnoj datoteci:   [DA  ▼]   │
  │ [2] Granularnost segmenata:      [Paragraf ▼]│
  │                                             │
  │ [X] Povratak                                │
  └─────────────────────────────────────────────┘
```

- Obje opcije su CLI dropdown (kursorske tipke ↑↓ za odabir vrijednosti).
- Promjena se **odmah primjenjuje** i prikazuje u svim prikaze (živi preview).
- Vrijednosti se sprema u `config/settings.yaml` (`translation.test_header`, `translation.granularity`).

**Dostupne granularnosti:**
- **Odlomak** — chunk od ~1500 tokena (više paragrafa zajedno)
- **Paragraf** — jedan `\n\n` blok
- **Rečenica** — jedna rečenica (najsporije, ali najkvalitetnije)

**Default vrijednosti** (ako nema zapisa u konfiguraciji): Paragraf, 1 komad, Header: DA.

### 9.3 TEST prijevod — tijek i izlaz

1. Korisnik bira datoteku i broj komada (1 odlomak, 2 paragrafa, 3 rečenice...).
2. Postavke granularnosti i headera preuzimaju se iz OPCIJA.
3. Prijevod se izvršava za odabrani broj segmenata.
4. **Ime izlazne datoteke:** `Dune_test_2026-07-31_110820.txt`
5. **Header (ako je uključen):**

```
================================================================================
TEST PRIJEVOD — Dynamic Book Translator v0.4.0
================================================================================
Knjiga:        Dune
Autor:         Frank Herbert
Model:         local-model
Provider:      lm_studio
Temperature:   0.25 | Top-p: 0.80 | Top-k: 15
================================================================================
Granularnost:  Paragraf
Obrađeno:      2 paragrafa | 347 riječi | 2.104 znakova
Brzina:        42 tok/s
Početak:       2026-07-31 11:08:20
Kraj:          2026-07-31 11:09:05
Trajanje:      0m 45s
================================================================================

[POČETAK PRIJEVODA]
Paul je stajao na rubu pustinje...
```

6. Parametri se sprema u `work/state/last_test.json` za BRZI TEST.

### 9.4 Struktura `work/state/last_test.json`

```json
{
  "timestamp": "2026-07-31T11:08:20",
  "book_title": "Dune",
  "book_dir": "work/output/Dune",
  "book_file": "work/output/Dune/Dune [fixed].txt",
  "config_file": "work/output/Dune/config.yaml",
  "memorija_file": "work/output/Dune/Dune_memorija.json",
  "model": "local-model",
  "api_provider": "lm_studio",
  "test_granularity": "paragraph",
  "test_count": 2,
  "include_header": true,
  "description": "Dune — 2 paragrafa"
}
```

### 9.5 Produkcijski prijevod — tijek i izlaz

1. Odabir `[fixed]` datoteke — batch podržan.
2. Učitavanje `config.yaml` i `memorija.json`.
3. Injekcija memorije u system prompt.
4. Segmentiranje prema postavci iz OPCIJA (odlomak/paragraf/rečenica).
5. Slanje segment-po-segment na LLM API.
6. Čišćenje reasoning tagova (ako `enable_reasoning: false`).
7. Zapis **ČISTOG TEKSTA** (bez headera) u `work/translated/<Knjiga>/<Knjiga>.txt`.
8. Atomski zapis checkpointa nakon svakog segmenta.
9. Opcionalno: **statistike u zasebnoj datoteci** `<Knjiga>_stats.txt` (ako je opcija uključena).

**Zasebna statistička datoteka** `work/translated/Dune/Dune_stats.txt` (opcionalno):
```
================================================================================
PRODUKCIJSKI PRIJEVOD — Dynamic Book Translator v0.4.0
================================================================================
Knjiga:        Dune | Autor: Frank Herbert
Model:         local-model | Provider: lm_studio
Temperature:   0.25 | Top-p: 0.80
Granularnost:  Paragraf
Ukupno:        2847 paragrafa | 187.543 riječi | 1.142.670 znakova
Prosj. brzina: 38 tok/s
Početak:       2026-07-31 11:00:00
Kraj:          2026-07-31 14:22:11
================================================================================
```

### 9.6 API endpoint

```
POST http://127.0.0.1:1234/v1/chat/completions
{
  "model": "lokalni-model",
  "messages": [
    {"role": "system", "content": "<system_prompt> + <JSON memorija>"},
    {"role": "user",   "content": "<segment>"}
  ],
  "temperature": 0.25,
  "top_p": 0.80,
  "max_tokens": 4096,
  "stream": false
}
```

---

## 10. FAZA 4 — TTS SINTEZA U MP3

### 10.1 Opcije izlaza (OPCIJE izbornik)

Korisnik bira unutar OPCIJA:

| Opcija | Opis |
|---|---|
| **Zasebne datoteke po odlomcima** | Svaki odlomak → poseban `.mp3` (preporučeno) |
| **Jedna datoteka** | Cijela knjiga u jednom `.mp3` |

### 10.2 Imenovanje MP3 datoteka

Format: `NNN_ChXX_partXXX.mp3`

```
001_Ch01_part001.mp3
002_Ch02_part001.mp3
003_Ch02_part002.mp3
004_Ch02_part003.mp3
005_Ch03_part001.mp3
```

- `NNN` — globalni redni broj (001, 002, 003...)
- `ChXX` — redni broj poglavlja (Ch01, Ch02...)
- `partXXX` — redni broj dijela unutar poglavlja (part001, part002...)

### 10.3 ID3 metapodaci u MP3

Svaka MP3 datoteka dobiva embedded metapodatke (via `mutagen`):

```
Artist:  Frank Herbert
Album:   Dune
Title:   Chapter 1 — Part 1
Track:   001
Comment: Generated by Dynamic Book Translator v0.4.0
```

### 10.4 Direktorij izlaza

MP3 datoteke se sprema u `work/audiobooks/<Knjiga>/`. Kreiranje direktorija i suffix-increment rade se putem unificirane metode iz `app/file_manager.py`.

---

## 11. BATCH PROCESSING MEHANIZAM

### 11.1 Princip rada

Svaki podizbornik omogućuje višestruki odabir datoteka koristeći:
- `1` — jedan odabir
- `1,3,5` — višestruki odabir
- `1-5` — raspon
- `*` — sve datoteke
- `X` — povratak

### 11.2 Batch u svakoj fazi

- **Faza 1 (Konverzija):** batch odabir iz `work/input/`, odabir formata TXT/MD.
- **Faza 2 (Čišćenje):** batch odabir sirovih `.txt/.md` iz `work/output/`.
- **Faza 3 (Prevođenje):** batch odabir `[fixed]` datoteka ili jedna po jedna s resumeom.
- **Faza 4 (TTS):** batch odabir prevedenih datoteka iz `work/translated/`.

---

## 12. MULTI-CHECKPOINT SUSTAV PERZISTENCIJE

### 12.1 Svrha

Svaki prijevod koji se prekine (struja, crash, X prekid) automatski se sprema u checkpoint. Pri sljedećem pokretanju aplikacije, glavni izbornik odmah prikazuje sve nedovršene prijevode s postotkom napretka. Odabir jednog od njih **1-klikom nastavlja** prijevod od zadnje točke.

### 12.2 Struktura `work/state/translation_checkpoints.json`

```json
{
  "active_books": [
    {
      "id": "dune_fixed",
      "title": "Dune",
      "author": "Frank Herbert",
      "book_dir": "work/output/Dune",
      "source_file": "work/output/Dune/Dune [fixed].txt",
      "target_file": "work/translated/Dune/Dune.txt",
      "config_file": "work/output/Dune/config.yaml",
      "memorija_file": "work/output/Dune/Dune_memorija.json",
      "total_paragraphs": 2847,
      "current_paragraph": 749,
      "percent": 26.31,
      "granularity": "paragraph",
      "last_updated": "2026-07-31T11:00:00"
    },
    {
      "id": "foundation_fixed",
      "title": "Foundation",
      "author": "Isaac Asimov",
      "book_dir": "work/output/Foundation",
      "source_file": "work/output/Foundation/Foundation [fixed].txt",
      "target_file": "work/translated/Foundation/Foundation.txt",
      "config_file": "work/output/Foundation/config.yaml",
      "memorija_file": "work/output/Foundation/Foundation_memorija.json",
      "total_paragraphs": 1204,
      "current_paragraph": 855,
      "percent": 71.01,
      "granularity": "paragraph",
      "last_updated": "2026-07-30T21:07:43"
    }
  ]
}
```

### 12.3 Prikaz u glavnom izborniku

Blok s nedovršenim prijevodima prikazuje se **odmah na vrhu** glavnog izbornika, iznad BRZI TEST opcije:

```
  NEDOVRŠENI PRIJEVODI (2):
  [1] ▶ Nastavi: Dune (Frank Herbert) ........... 26.31%  [749/2847 par.]
  [2] ▶ Nastavi: Foundation (Asimov) ............. 71.01%  [855/1204 par.]
```

Odabir numeričke opcije iz ovog bloka **odmah nastavlja prijevod** — bez dodatnih pitanja.

### 12.4 Ključna svojstva
- Izolacija: nastavak jedne knjige nikad ne dira checkpoint druge.
- Real-time ažuriranje: atomski zapis nakon svakog segmenta.
- Atomski zapis: `json.dump` u `.tmp` → `os.replace()` — zaštita od korupcije pri nestanku struje.
- Nastavak: tekst se **append-a** u postojeću `work/translated/` datoteku — ne prepisuje.
- Maksimalni broj paralelnih naslova: neograničen (preporuka ≤10).

---

## 13. TEST SUSTAV — BRZI TESTNI PRIJEVOD

### 13.1 Svrha

Brzi testni prijevod za provjeru kvalitete modela i parametara. Podržava tri razine granularnosti jer je ponekad potreban tekst kraći od odlomka:

- **Odlomak** — chunk od ~1500 tokena (više paragrafa zajedno)
- **Paragraf** — jedan `\n\n` blok
- **Rečenica** — jedna rečenica

### 13.2 Ključne razlike TEST vs. PRODUKCIJA

| | TEST | PRODUKCIJA |
|---|---|---|
| **Header** | OPCIJA — DA ili NE (default: DA) | NIKAD — čisti tekst za TTS |
| **Statistička datoteka** | U samom headeru (ako uključen) | Zasebna `_stats.txt` datoteka (opcionalno) |
| **Naziv datoteke** | `<naziv>_test_<timestamp>.txt` | `<naziv>.txt` |
| **Checkpoint** | NE (kratka obrada) | DA — nastavak nakon prekida |

> **Zašto je produkcija uvijek čista?**  
> Produkcijska `.txt` datoteka se direktno provlači kroz TTS i pretvara u MP3. Header s tehničkim detaljima u audiobuku ne smije postojati — slušatelj bi čuo "Model: local-model | Temperature: 0.25...".

### 13.3 Header u testnoj datoteci

Ako je uključen (opcija u OPCIJAMA), testna datoteka sadrži:

```
================================================================================
TEST PRIJEVOD — Dynamic Book Translator v0.4.0
================================================================================
Knjiga:        Dune
Autor:         Frank Herbert
Model:         local-model
Provider:      lm_studio
Temperature:   0.25 | Top-p: 0.80 | Top-k: 15 | Repeat penalty: 1.1
================================================================================
Granularnost:  Paragraf
Obrađeno:      2 paragrafa | 347 riječi | 2.104 znakova
Brzina:        42 tok/s
Početak:       2026-07-31 11:08:20
Kraj:          2026-07-31 11:09:05
Trajanje:      0m 45s
================================================================================

[POČETAK PRIJEVODA]
Paul je stajao na rubu pustinje...
```

### 13.4 BRZI TEST u glavnom izborniku

```
╔══════════════════════════════════════════════════════════╗
║  DYNAMIC BOOK TRANSLATOR v0.4                            ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  NEDOVRŠENI PRIJEVODI:                                   ║
║  [1] ▶ Nastavi: Dune (Frank Herbert) ........... 26.31% ║
║  [2] ▶ Nastavi: Foundation (Asimov) ............ 71.01% ║
║                                                          ║
║  [Y] BRZI TEST: Dune — 2 paragrafa                      ║
║       Model: local-model | Paragraf | Header: DA         ║
║                                                          ║
║  [1] Konverzija dokumenata → TXT/MD                      ║
║  [2] Čišćenje tehničkog šuma + memorija                  ║
║  [3] Prevođenje (LLM)                                    ║
║  [4] TTS sinteza u MP3                                   ║
║  [X] Izlaz                                               ║
╚══════════════════════════════════════════════════════════╝
```

- Blok nedovršenih prijevoda prikazuje se samo ako postoje checkpointi.
- Svaki checkpoint je 1-click nastavak — odabir brojke odmah nastavlja prijevod.
- `[Y]` ponavlja zadnji test s istim parametrima — 1-click pokretanje.

### 13.5 OPCIJE izbornik

```
╔══════════════════════════════════════════════════╗
║  OPCIJE — Prevođenje                             ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  [1] Header u testnoj datoteci:                  ║
║      ● DA                                        ║
║      ○ NE                                        ║
║                                                  ║
║  [2] Granularnost segmenata:                     ║
║      ○ Odlomak  (~1500 tokena)                   ║
║      ● Paragraf (jedan \\n\\n blok)              ║
║      ○ Rečenica                                  ║
║                                                  ║
║  [X] Povratak                                    ║
╚══════════════════════════════════════════════════╝
```

- Kretanje: ↑↓ kursorske tipke.
- Odabir: Enter ili Razmaknica.
- Promjena se odmah odražava u prikazu glavnog izbornika (BRZI TEST linija).
- Vrijednosti se atomski sprema u `config/settings.yaml`.

---

## 14. TRORAZINSKO LOGIRANJE

### 14.1 Razine logiranja

| Razina | Parametar u settings.yaml | Default | Opis |
|---|---|---|---|
| **Osnovno** | Uvijek aktivno | ON | Početak/kraj knjige, greške, checkpoint |
| **Verbatim** | `logging.verbatim` | OFF | Trace svake akcije |
| **LLM Debug** | `logging.llm_responses` | OFF | Puni LLM odgovori za analizu |

### 14.2 Reasoning toggle

Parametar `logging.enable_reasoning` (ili per-book `enable_reasoning` u `config.yaml`) kontrolira brisanje `<think>...</think>` i `<reasoning>...</reasoning>` tagova iz LLM odgovora.

---

## 15. VANJSKI API INTEGRACIJA

### 15.1 Podržani provideri

| Provider | Tip | API Base URL | Autentikacija |
|---|---|---|---|
| `lm_studio` | Lokalni | `http://127.0.0.1:1234/v1` | Nema |
| `ollama_local` | Lokalni | `http://127.0.0.1:11434/api` | Nema |
| `ollama_cloud` | Cloud | `https://api.ollama.ai/v1` | `.env: OLLAMA_API_KEY` |
| `openai` | Cloud | `https://api.openai.com/v1` | `.env: OPENAI_API_KEY` |
| `gemini` | Cloud | `https://generativelanguage.googleapis.com/v1beta` | `.env: GEMINI_API_KEY` |
| `qwen` | Cloud | `https://dashscope.aliyuncs.com/api/v1` | `.env: QWEN_API_KEY` |
| `custom` | Bilo koji | Konfigurabilno | `.env: CUSTOM_API_KEY` |

Sustav je dizajniran za **lako dodavanje novih providera** — svaki provider implementira isti adapter interface u `app/translator.py`.

### 15.2 Pohrana API ključeva — `.env` datoteka

**Svi API ključevi čitaju se isključivo iz `.env` datoteke** u root direktoriju projekta. Ključevi se **nikada** ne upisuju u YAML konfiguraciju ni Python kod.

**`.env` datoteka (root direktorij):**
```
# Dynamic Book Translator — API Keys
# NE COMMITATI u Git — .gitignore ignorira ovu datoteku

OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AI...
QWEN_API_KEY=sk-...
OLLAMA_API_KEY=...
CUSTOM_API_KEY=...
```

**Python učitavanje (via `python-dotenv`):**
```python
from dotenv import load_dotenv
import os

load_dotenv()  # Čita .env iz root direktorija

api_key = os.getenv("OPENAI_API_KEY", "")
```

`python-dotenv` dodan u `requirements.txt`.

### 15.3 Konfiguracija providera u `config/settings.yaml`

```yaml
api:
  provider: "lm_studio"    # Aktivni provider
  auto_detect_model: true  # Auto-detekcija iz LM Studio / Ollama

  providers:
    lm_studio:
      base_url: "http://127.0.0.1:1234/v1"
      model: ""            # Prazno = auto-detect
    ollama_local:
      base_url: "http://127.0.0.1:11434/api"
      model: "llama3.2"
    ollama_cloud:
      base_url: "https://api.ollama.ai/v1"
      model: "llama3.2"
      key_env: "OLLAMA_API_KEY"
    openai:
      base_url: "https://api.openai.com/v1"
      model: "gpt-4o"
      key_env: "OPENAI_API_KEY"
    gemini:
      base_url: "https://generativelanguage.googleapis.com/v1beta"
      model: "gemini-1.5-pro"
      key_env: "GEMINI_API_KEY"
    qwen:
      base_url: "https://dashscope.aliyuncs.com/api/v1"
      model: "qwen-turbo"
      key_env: "QWEN_API_KEY"
    custom:
      base_url: ""
      model: ""
      key_env: "CUSTOM_API_KEY"
```

### 15.4 Per-book API override

Svaka knjiga može override-ati globalnog providera kroz `work/output/<Knjiga>/config.yaml`:
```yaml
api_provider: "openai"   # override globalnog providera
model: "gpt-4o"          # override modela
# API ključ se uvijek čita iz .env — nikad ne piše u config.yaml
```

### 15.5 Dodavanje novog providera

Za dodavanje novog providera dovoljno je:
1. Dodati blok u `config/settings.yaml` pod `api.providers`.
2. Dodati `KEY=...` u `.env`.
3. Implementirati adapter u `app/translator.py` koji nasljeđuje `BaseAPIAdapter`.

---

## 16. AUTOMATSKA DETEKCIJA LIKOVA

### 16.1 Opcija A: Heuristička detekcija (lokalno, brzo, ~60-70% preciznosti)
### 16.2 Opcija B: AI-bazirana detekcija (preporučeno, ~95% preciznosti)

Preporuka: **Opcija B** — šalje se prvo poglavlje na LLM s promptom za ekstrakciju likova i roda, rezultat se automatski upisuje u `CHARACTERS` sekciju `memorija.json`.

---

## 17. .GITIGNORE SPECIFIKACIJA

```gitignore
__pycache__/
*.py[cod]
venv/
env/
.venv
work/
*.log
*.tmp
*.bak
.vscode/
.idea/
Thumbs.db
.DS_Store

# API ključevi — NIKAD u Git
.env
.env.*
!.env.example
```

> **Bitno:** `.env.example` se **commita** kao predložak (s praznim vrijednostima) da novi korisnik zna koje ključeve treba postaviti.

Što se commita: `main.py`, `app/*.py`, `./start`, `requirements.txt`, `.gitignore`, `.env.example`, `config/*.yaml`, `doc/`.

---

## 18. SIGURNOSNO RUKOVANJE GREŠKAMA

| Greška | Uzrok | Reakcija |
|---|---|---|
| `HTTP 500` | LM Studio crash | Fallback + zapis checkpointa |
| `Timeout` | Zagušenje VRAM-a | Retry 2x, pa fallback |
| `ConnectionRefused` | LM Studio nije pokrenut | Poruka + povratak u izbornik |
| `JSONDecodeError` | Koruptiran LLM odgovor | Čišćenje tagova + retry |
| `FileNotFoundError` | Nedostaje direktorij | Auto-kreiranje |
| `UnicodeDecodeError` | Neobičan encoding | Fallback na `latin-1` |
| `YAMLError` | Koruptiran YAML | Poruka + povratak u izbornik |

---

## 19. PROTOKOL SIGURNOG IZLAZA

```
[X]  →  "Jeste li sigurni da želite izaći? (Y/N):"
[Y]  →  Flush buffera → atomski checkpoint → zatvaranje HTTP sesija → sys.exit(0)
[N]  →  Poništenje, povratak u izbornik
```

---

## 20. HEADER METAPODACI U PREVEDENOM TEKSTU

### 20.1 Produkcijski prijevod — UVIJEK bez headera

Produkcijska datoteka je **čisti prevedeni tekst i ništa više**. Razlog: datoteka se direktno šalje u TTS engine koji ju pretvara u MP3 audiobook. Header s tehničkim detaljima bi se čitao kao naracija — "Model: local-model, Temperature: nula point dvadeset pet..." — što je neprihvatljivo za audio iskustvo.

**Primjer produkcijskog outputa** (`work/translated/Dune/Dune.txt`):
```
Paul je stajao na rubu pustinje, osjećajući pijesak ispod sandala...

Bila je to ona vrsta tišine koja prethodi oluji...
```

### 20.2 Produkcijska statistička datoteka — opcionalno

Ako korisnik želi metapodatke o produkcijskom prijevodu, oni se sprema u **zasebnu datoteku** koja se nikad ne šalje u TTS:

`work/translated/Dune/Dune_stats.txt`:
```
================================================================================
PRODUKCIJSKI PRIJEVOD — Dynamic Book Translator v0.4.0
================================================================================
Knjiga:        Dune | Autor: Frank Herbert
Model:         local-model | Provider: lm_studio
Temperature:   0.25 | Top-p: 0.80 | Top-k: 15
Granularnost:  Paragraf
Ukupno:        2847 paragrafa | 187.543 riječi | 1.142.670 znakova
Prosj. brzina: 38 tok/s
Početak:       2026-07-31 11:00:00
Kraj:          2026-07-31 14:22:11
================================================================================
```

### 20.3 Testni prijevod — header je OPCIJA

Header u testnoj datoteci je **opcija** koja se uključuje/isključuje u OPCIJAMA izbornika. Default: uključen.

Razlog zašto je za TEST koristan:
- Korisnik uspoređuje prijevode različitih modela — header govori koji model je koji.
- Vidljivi su parametri koji su korišteni za taj prijevod.
- Brzina (tok/s) i trajanje pomažu pri odabiru optimalnog modela.

**Format testnog headera** (vidi sekciju 13.3).

---

## 21. REFACTORING — MODULARNA ARHITEKTURA

### 21.1 Princip

`main.py` je **isključivo orkestrator** — importa module iz `app/` i koordinira tok izvršavanja. Nema logike u `main.py` — samo pozivi metoda iz modula.

### 21.2 Moduli u `app/`

| Modul | Odgovornost |
|---|---|
| `config_loader.py` | Učitavanje i spajanje YAML konfiguracije |
| `menu.py` | CLI izbornici s kursorskom navigacijom (↑↓ + Enter/Space + X) |
| `document_processor.py` | Faza 1: parsiranje dokumenata (PDF, EPUB, DOCX, MOBI, TXT) |
| `text_cleaner.py` | Faza 2: čišćenje headera/footera, kreiranje `[fixed]` i `memorija.json` |
| `translator.py` | Faza 3: LLM prijevod (odlomak, paragraf, rečenica; TEST i produkcija) |
| `tts_engine.py` | Faza 4: TTS sinteza, generiranje MP3 s ID3 tagovima |
| `file_manager.py` | Unificirana metoda za direktorije, datoteke i suffix-increment |
| `checkpoint.py` | Multi-checkpoint perzistencija, atomski zapis |
| `logger.py` | Trorazinsko logiranje |
| `utils.py` | Sanitizacija naziva, progress bar, detekcija X tipke, čišćenje ekrana |

### 21.3 Pravilo bez duplikacija

Svaka funkcionalnost postoji **na jednom mjestu**:
- Kreiranje direktorija i suffix-increment → isključivo `file_manager.py`
- API pozivi → isključivo `translator.py`
- Sve navigacijske rutine → isključivo `menu.py`

Kod koji radi identičan posao **mora** biti u zajedničkoj metodi s parametrima, ne kopiran.

### 21.4 Primjer: `main.py` struktura

```python
# main.py — isključivo orkestracija
from app.config_loader import load_global_config
from app.menu import MainMenu
from app.document_processor import DocumentProcessor
from app.text_cleaner import TextCleaner
from app.translator import Translator
from app.tts_engine import TTSEngine
from app.checkpoint import CheckpointManager
from app.logger import setup_logging
from app.file_manager import FileManager

def main():
    config = load_global_config()
    setup_logging(config)
    fm = FileManager(config)
    fm.ensure_directories()
    
    checkpoint_mgr = CheckpointManager(config)
    menu = MainMenu(config, checkpoint_mgr)
    
    while True:
        action = menu.show_main()
        if action == "exit":
            break
        elif action == "test":
            Translator(config, fm).run_test(menu.last_test)
        elif action == "phase1":
            DocumentProcessor(config, fm).run(menu.selection)
        elif action == "phase2":
            TextCleaner(config, fm).run(menu.selection)
        elif action == "phase3":
            Translator(config, fm).run_full(menu.selection)
        elif action == "phase4":
            TTSEngine(config, fm).run(menu.selection)

if __name__ == "__main__":
    main()
```

---

## 22. UPRAVLJANJE DIREKTORIJIMA I DATOTEKAMA — UNIFICIRANA METODA

### 22.1 Svrha

Sva logika kreiranja direktorija, detekcije postojanja i suffix-incrementa je u **jednoj metodi** u `app/file_manager.py`. Parametri definiraju što se kreira i gdje.

### 22.2 API metode `FileManager`

```python
class FileManager:
    def ensure_dir(self, dir_path: str, suffix_if_exists: bool = False) -> str:
        """Kreira direktorij. Ako postoji i suffix_if_exists=True,
        dodaje suffix _001, _002... Vraća finalnu putanju."""
    
    def ensure_file_path(self, file_path: str, suffix_if_exists: bool = False) -> str:
        """Generira sigurnu putanju za datoteku.
        Ako postoji i suffix_if_exists=True, dodaje (001), (002)..."""
    
    def ensure_directories(self) -> None:
        """Kreira sve potrebne direktorije iz konfiguracije pri pokretanju."""
    
    def book_output_dir(self, book_title: str, author: str) -> str:
        """Vraća putanju work/translated/<sanitized_title>---<sanitized_author>.
        Automatski dodaje suffix ako postoji."""
    
    def audiobook_dir(self, book_title: str, author: str) -> str:
        """Isto kao book_output_dir ali za work/audiobooks/."""
```

### 22.3 Suffix format

- Direktoriji: `foundation---isaac-asimov`, `foundation---isaac-asimov_001`, `_002`...
- Datoteke: `Dune.txt`, `Dune(001).txt`, `Dune(002).txt`...

Prefiks se uvijek oblikuje s 3 znamenke (`%03d`).

---

## 23. MP3 IMENOVANJE I METAPODACI

### 23.1 Format naziva

```
001_Ch01_part001.mp3   ← globalni redni broj + poglavlje + dio poglavlja
002_Ch02_part001.mp3
003_Ch02_part002.mp3
004_Ch02_part003.mp3
005_Ch03_part001.mp3
```

### 23.2 ID3 metapodaci (via `mutagen`)

| Tag | Vrijednost |
|---|---|
| `TPE1` (Artist) | Autor knjige |
| `TALB` (Album) | Naslov knjige |
| `TIT2` (Title) | `Chapter X — Part Y` |
| `TRCK` (Track) | Globalni redni broj (001, 002...) |
| `COMM` (Comment) | `Generated by Dynamic Book Translator v0.4.0` |

### 23.3 Izlazni direktorij

MP3 se sprema u `work/audiobooks/<naslov-autor>/`. Ako direktorij postoji → suffix `_001`, `_002`... putem `FileManager.audiobook_dir()`.

---

## KRAJ DOKUMENTACIJE

Ovo je kompletna tehnička specifikacija sustava **DYNAMIC BOOK TRANSLATOR & PARSER V0.4**. Dokument pokriva:

- ✅ Modularnu arhitekturu (`app/` direktorij)
- ✅ Isključivo YAML konfiguraciju (nema hardkodiranih vrijednosti u kodu)
- ✅ API ključevi isključivo u `.env` (`.gitignore` zaštićeno)
- ✅ CLI "GUI" s kursorskom navigacijom (↑↓ + Enter/Space + X)
- ✅ TEST sustav s opcionalnim headerom (DA/NE u OPCIJAMA) — testna datoteka s timestampom
- ✅ Produkcijski prijevod — uvijek čisti tekst bez headera (spreman za TTS→MP3)
- ✅ OPCIJE izbornik s dropdown granularnosti (odlomak/paragraf/rečenica)
- ✅ Per-book direktorije s memorijom (CHARACTERS + GLOSSARY + GRAMMAR_FIXES)
- ✅ Multi-checkpoint s 1-click nastavkom iz glavnog izbornika
- ✅ Unificiranu metodu za direktorije i suffix-increment (`FileManager`)
- ✅ MP3 imenovanje (`001_Ch01_part001.mp3`) s ID3 metapodacima
- ✅ Batch processing u svim fazama
- ✅ Lokalni LM Studio + lokalni Ollama + Ollama cloud + OpenAI + Gemini + Qwen + Custom
- ✅ Trorazinsko logiranje
- ✅ Sigurnosno rukovanje greškama i protokol izlaza

**Sljedeći korak:** Implementacija refactoringa — kreiranje `app/` strukture i migracija koda iz `mamba_voice.py`.
