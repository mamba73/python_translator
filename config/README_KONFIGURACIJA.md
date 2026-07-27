# Vodiču za konfiguraciju MambaBookVoice

## 🎯 Gdje se što konfigurira?

| Datoteka | Što se konfigurira | Trebate li editirati? |
|----------|-------------------|----------------------|
| **`config/settings.py`** | **SVE korisničke vrijednosti** (TRANSLATION, TTS, SANITIZATION, CHAPTER_PATTERNS) | ✅ **DA** - editirajte ovdje! |
| `mamba_voice.py` | Samo DIR putanje i CHAR_MAP (tehnički detalji) | ❌ Samo ako premještate projekt |
| `config/settings.json` | ~~Zastarjelo~~ OBRISANO | ❌ Više se ne koristi |

## ✅ Gdje trebam biti

**Sva konfiguracija ide u:** `config/settings.py`

Otvorite tu datoteku i editirajte što trebate. To je jedina datoteka koju trebate dodirivati za konfiguraciju!

---

## Kako funkcionira konfiguracija

1. **Python kod učitava minimalne vrijednosti** iz `mamba_voice.py` (DIR putanje, CHAR_MAP)
2. **Python kod učitava `config/settings.py`** ako postoji
3. **Vrijednosti iz `settings.py` zamjenjuju** zadane vrijednosti

**Rezultat:** Čista separacija - kod se ne mijenja, samo `settings.py`!

---

## ✅ Čisti Python format - BEZ escape znakova!

U `config/settings.py` se koristi običan Python syntax - **NIKAKVI backslash znakovi ili `\n` sekvence nisu potrebni**!

Koristiš **triple-quote stringove** (`"""..."""`) za multi-line tekstove:

```python
"SYSTEM_PROMPT": """Prvi red teksta.
Drugi red teksta.
Treći red teksta."""
```

To je to - čitljivo, jednostavno, bez escape znakova!

---

## Primjer: Promjena SYSTEM_PROMPT za hrvatsku prijevode

Otvorite `config/settings.py` i izmijenjte `TRANSLATION["SYSTEM_PROMPT"]`:

```python
SETTINGS = {
    "TRANSLATION": {
        "SYSTEM_PROMPT": """You are a professional translator specializing in English to standard, pure Croatian translation.
Your task is to translate the text from English to standard Croatian.

STRICT RULES:
1. Use ONLY standard Croatian vocabulary and grammar (standardni hrvatski književni jezik).
2. Absolutely DO NOT use any Serbian or Bosnian words, idioms, or syntax variations.
3. Pay strict attention to specific Croatian words:
   - Use: "tjedan", "tisuću", "kolovoz", "obitelj", "sustav", "uvjet", "utjecaj", "povijest", "zrakoplov", "vlastito".
   - NEVER use: "sedmica", "hiljada", "avgust", "porodica", "sistem", "uslov", "uticaj", "istorija", "avion", "sopstveno".
4. Maintain the original tone and context, but format the sentence structure to sound natural in Croatian.
5. Output ONLY the translated text, without explanations."""
    }
}
```

---

## Sve konfigurabilne vrijednosti

### TRANSLATION
- `API_URL` - URL do LM Studio API-ja (zadano: "http://localhost:1234/v1/chat/completions")
- `API_MODEL` - Naziv modela koji se koristi u LM Studio (trebate postaviti!)
- `TEMPERATURE` - Temperatura (0.0-2.0, niža = determinističnija, zadano: 0.3)
- `MAX_TOKENS` - Maksimalna dužina odgovora (zadano: 2048)
- `MIN_WORDS_FOR_LLM` - Minimalan broj riječi za prijevod kroz LLM (zadano: 4)
- `SYSTEM_PROMPT` - **Multi-line sistem prompt za LLM** (ključno za kvalitetu!) - koristi `"""..."""`
- `SCAN_PAGES_LIMIT` - Maksimalan broj stranica za analizu (zadano: 30)
- `HEADER_FOOTER_THRESHOLD` - Prag za detekciju zaglavlja/podnožja (zadano: 0.40)

### TTS (Text-to-Speech)
```python
"TTS": {
    "NARATOR": {
        "VOICE": "hr-HR-SreckoNeural",     # Glas za naraciju
        "RATE": "+0%",                     # Brzina govorenja
        "PITCH": "+0Hz"                    # Ton glasa
    },
    "DIJALOG": {
        "USE_DIFFERENT_VOICE": True,       # Koristi drugi glas za dijalog
        "VOICE": "hr-HR-GabrijelaNeural",
        "RATE": "+2%",
        "PITCH": "+0Hz"
    },
    "DRAMATIC_MODE": {
        "ENABLED": True,                   # Dramska moda (promijena glasa na dramatičnim scenama)
        "KEYWORDS_ANXIOUS": [...],         # Ključne riječi koje aktiviraju brži govor
        "RATE_MODIFIER_ANXIOUS": "+15%"    # Koliko brže govoriti pri anksioznosti
    }
}
```

### SANITIZATION
- `REPLACE_SPACES_WITH` - Zamijeni razmake sa (zadano: "-")
- `PREFIX_PADDING` - Broj znamenki za padding (zadano: 3, npr. "001", "002")

### CHAPTER_PATTERNS
Raw regex stringovi (koristi `r"..."` format):

```python
"CHAPTER_PATTERNS": [
    r"^(CHAPTER|Chapter|POGLAVLJE|Poglavlje)\s+\d+",
    r"^(EPILOGUE|PROLOGUE|Epilogue|Prologue)",
    r"^[A-Z\s]{4,25}$"
]
```

Nema potrebe za escape znakovima u Python rawstring formatu!

---

## Primjer: Kompletan settings.py sa više promjena

```python
SETTINGS = {
    "TRANSLATION": {
        "API_URL": "http://localhost:1234/v1/chat/completions",
        "API_MODEL": "mistral-7b",
        "TEMPERATURE": 0.2,
        "SYSTEM_PROMPT": """You are a translator.
Translate English to Croatian.
Output ONLY the translation."""
    },
    "TTS": {
        "NARATOR": {
            "VOICE": "hr-HR-SreckoNeural",
            "RATE": "+5%"
        }
    }
}
```

---

## Kako Python konfigurator funkcionira?

1. **Učitava** `config/settings.py` ako postoji
2. **Spaja** sve vrijednosti iz `settings.py` s hardkodiiranim zadanim vrijednostima
3. **Prioritet:** `settings.py` vrijednosti **ZAMJENJUJU** hardkodirane vrijednosti
4. **Ako Python datoteka ne postoji:** koriste se samo hardkodirane zadane vrijednosti
5. **Ako postoji greška u Python datoteci:** upozorenje se logira, ali program nastavlja sa zadanim vrijednostima

---

## Python syntax - brzi savjeti

| Trebam... | Koristi... |
|-----------|-----------|
| Tekst sa više redaka | `"""Linija 1` + novi red + `Linija 2"""` |
| Stringovi sa navodnicima | `"""Tekst sa "navodnicima" unutar"""` |
| Boolean vrijednosti | `True`, `False` (Python boolean) |
| Brojevne vrijednosti | `0.3`, `2048` (Python brojevi) |
| Liste | `["element1", "element2"]` |

---

## ❌ Što je obrisano?

- ~~`config/settings.json`~~ - Zastarjelo. Koristi se samo `settings.py` sada.

## Što se NE MOŽE konfigurirati kroz settings.py?

- **Direktoriji (`DIR`)** - trebaju biti dinamičke putanje (relativne na lokaciju skripte)
- **CHAR_MAP** - Python transformacija koja se ne može pohraniti

Ako trebate promijeniti direktorije, trebali biste ih promijeniti u `mamba_voice.py` (DIR sekcija).

---

## Pro savjet: Git-ignoriramo osjetljive vrijednosti

Kreirajte `config/settings.local.py` za lokalne tajne konfiguracije i dodajte u `.gitignore`:

```bash
# .gitignore
config/settings.local.py
```
