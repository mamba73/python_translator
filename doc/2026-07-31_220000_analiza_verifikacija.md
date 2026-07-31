# VERIFIKACIJA IMPLEMENTACIJE — mamba_voice.py vs. Nova Tehnička Specifikacija

**Datum:** 2026-07-31 22:00:00  
**Verzija analiziranog koda:** `app/` modularna arhitektura (refactoring stanje)  
**Specifikacija:** `README_TechDoc.md` v0.4  
**Prethodna analiza:** `doc/2026-07-31_110820_analiza_upgrade01.md`  
**Cilj:** Verificirati što je 100% implementirano i funkcionalno, a što je djelomično ili nedovršeno.

---

## 1. UKUPNI STATUS

| Kategorija | Ocjena | Napomena |
|---|---|---|
| Modularna arhitektura (`app/`) | ✅ Implementirano | 10 modula, `main.py` čisti orkestrator |
| YAML konfiguracija | ✅ Implementirano | `config/settings.yaml` + per-book `config.yaml` |
| CLI "GUI" s kursorskim tipkama | ✅ Implementirano | `msvcrt` (Win) / `curses` (Linux) |
| OPCIJE izbornik s dropdownom | ✅ Implementirano | Header / Granularnost / Količina |
| TEST vs. PRODUKCIJA — header logika | ✅ Implementirano | TEST header opcija, produkcija čista |
| Per-book memorija (`_memorija.json`) | ✅ Implementirano | CHARACTERS + GLOSSARY + GRAMMAR_FIXES |
| Multi-provider API | ✅ Implementirano | lm_studio, ollama, openai, gemini, qwen, custom + `.env` |
| MP3 imenovanje `NNN_ChXX_partXXX.mp3` | ✅ Implementirano | Globalni + poglavlje + dio brojač |
| ID3 metapodaci u MP3 | ✅ Implementirano | mutagen (TIT2, TPE1, TALB, TRCK, TCOM) |
| Unificirana `FileManager` klasa | ✅ Implementirano | ensure_dir/file_path/output/audiobook |
| Multi-checkpoint sustav | ⚠️ Djelomično | Spremanje radi, **nastavak (resume) NIJE funkcionalan** |
| Auto-detekcija modela | ❌ **Pokvareno** | `_detect_lm_studio_model`/`_detect_ollama_model` NE POSTOJE |
| **Produkcijska statistika `_stats.txt`** | ❌ **Nedostaje** | Nije generirana |
| **TTS "Jedna datoteka" (merge_single)** | ❌ **Nedovršeno** | TODO placeholder, vraća segmente |
| **Trorazinsko logiranje (LLM debug)** | ⚠️ Djelomično | Logger postoji, ali `log_llm_response()`/`log_verbatim()` se NE POZIVAJU |

---

## 2. ŠTO JE 100% IMPLEMENTIRANO I FUNKCIONALNO

### 2.1 Modularna arhitektura ✅
`main.py` je čisti orkestrator. Svi moduli u `app/`:
`config_loader.py`, `file_manager.py`, `logger.py`, `utils.py`, `document_processor.py`, `text_cleaner.py`, `translator.py`, `checkpoint.py`, `tts_engine.py`, `menu.py`.

### 2.2 YAML konfiguracija ✅
- `config/settings.yaml` — globalne postavke.
- `config/profile_*.yaml` — SF, IT, general predlošci.
- `work/output/<Knjiga>/config.yaml` — per-book, generiran pri prvoj obradi.
- API ključevi čitaju se iz `.env` via `python-dotenv` (`config_loader._inject_api_keys()`).

### 2.3 CLI GUI s kursorskom navigacijom ✅
`app/menu.py`:
- Kursorske tipke ↑↓ + Enter/Razmaknica — Windows (`msvcrt`) i Linux (`curses`).
- Batch odabir `1`, `1,3,5`, `1-5`, `*`, `X`.
- Notifikacijska linija u `[3] Prevođenje`.
- OPCIJE dropdown (Header DA/NE, Granularnost, Količina).

### 2.4 TEST vs. PRODUKCIJA — header logika ✅
- TEST → `<naziv>_test_<timestamp>.txt`, header kao OPCIJA (default DA).
- Produkcija → `<naziv>.txt`, uvijek čisti tekst bez headera.
- `prevedi_test()` / `prevedi_knjigu()` odvojeni u `translator.py`.

### 2.5 Per-book memorija ✅ (dodatak u ovom sessionu)
- `postavi_knjigu(book_dir, book_config)` u `translator.py` učitava `<Knjiga>_memorija.json`.
- `_generiraj_system_prompt()` injektira CHARACTERS + GLOSSARY + GRAMMAR_FIXES u **CHARACTER GENDER REGISTER** blok.
- Poziva se iz `_test_prijevod()`, `_produkcijski_prijevod()`, `_brzi_test()`.

### 2.6 Multi-provider API ✅
- Adaptori: `lm_studio`, `ollama_local`, `ollama_cloud`, `openai`, `gemini`, `qwen`, `custom`.
- API ključevi u `.env`, nikad u kodu/YAML.

### 2.7 MP3 imenovanje + ID3 ✅
`app/tts_engine.py`:
- Imenovanje `NNN_ChXX_partXXX.mp3`.
- Pre-calculation segmentacija (TechDoc §10.5).
- ID3 tagovi via `mutagen` (TIT2, TPE1, TALB, TRCK, TCOM).

---

## 3. ŠTO NIJE 100% — POTREBNO DOVRŠITI

### 3.1 🔴 Auto-detekcija modela — POKVARENO ❌
`app/translator.py` `detektiraj_aktivni_model()` poziva:
```python
if self._provider == "lm_studio":
    return self._detect_lm_studio_model()   # ← NE POSTOJI
elif self._provider == "ollama_local":
    return self._detect_ollama_model()      # ← NE POSTOJI
```
**Metode ne postoje** → `AttributeError` pri pozivu. Auto-detekcija (`auto_detect_model: true` je default) će **pasti s greškom**.
- **U mamba_voice.py:** `detektiraj_aktivni_model()` koristi `/v1/models` endpoint direktno.
- **Popravak:** Implementirati `_detect_lm_studio_model()` (GET `/v1/models`) i `_detect_ollama_model()` (GET `/api/tags`), kao u starijoj verziji.

### 3.2 🟡 Checkpoint — nastavak (resume) NIJE funkcionalan ⚠️
- `checkpoint.py` sprema/učita/brise checkpointe ✅.
- `menu.py` prikazuje blok aktivnih checkpointa ✅.
- **ALI:** `_odabir_checkpointa()` vraća `"resume:<index>"`, a `show_main()` to proslijeđuje, ali **`run()` ne rukuje `resume:`** — nema grane u `run()` koja bi nastavila prevođenje od checkpointa. Search `resume` u menu.py → **0 rezultata**.
- **U mamba_voice.py:** `prikazi_progress_izvjestaj()` → R/N/X dijalog + `resume_from` parametar u `prevedi_tekst_paragrafski()`.
- **Popravak:** U `Menu.run()` obraditi `resume:<index>`, učitati checkpoint, pozvati `prevedi_knjigu()` s parametrom `resume_from` (koji trenutno ne postoji u signaturi `prevedi_knjigu`).

### 3.3 🟡 Produkcijska statistika `_stats.txt` — NEDOSTAJE ❌
- TODO.md tvrdi `[x] Produkcija statistike → <naziv>_stats.txt (opcionalno)`.
- **Search `_stats`/`stats` u app/ → 0 rezultata.** Statistika **nije generirana**.
- **U mamba_voice.py / TechDoc §9.5:** zasebna `<Knjiga>_stats.txt` s parametrima, brojem riječi/znakova, brzinom.
- **Popravak:** Generirati u `prevedi_knjigu()` (ili u menu) nakon završetka.

### 3.4 🟡 TTS "Jedna datoteka" (merge_single) — NEDOVRŠENO ❌
`app/tts_engine.py` `generiraj_audiobook()`:
```python
if merge_single and len(sve_mp3_putanje) > 1:
    # TODO: Implementirati spajanje MP3 (npr. pomoću pydub ili ffmpeg)
    logging.warning("Merge single nije implementiran — vraćam sve segmente.")
```
**Funkcionalnost "Jedna MP3 datoteka" NIJE implementirana** — vraća sve segmente i logira upozorenje.

### 3.5 🟡 Trorazinsko logiranje — logger postoje, ali se ne pozivaju ⚠️
`app/logger.py` ima `setup_logging()`, `log_basic()`, `log_verbatim()`, `log_llm_response()`.
**Problemi:**
- `setup_logging()` poziva se u `main.py` ✅.
- **`log_verbatim()` i `log_llm_response()` se NIGDJE NE POZIVAJU** u kodu (`app/` search → 0 rezultata za `log_verbatim`/`log_llm_response`).
- Verbatim/LLM debug logovi su **mrtve funkcije** — definirane, ali neiskorištene.
- Specifikacija §14 zahtijeva tri razine logiranja, ali samo osnovna razina je aktivno spojena.

---

## 4. USPOREDBA S mamba_voice.py (stara verzija)

| Funkcionalnost | mamba_voice.py (staro) | Nova arhitektura (app/) | Status |
|---|---|---|---|
| Parsiranje (.pdf/.docx/.epub/.mobi) | `ucitaj_izvorni_tekst` ✅ | `document_processor.py` ✅ | ✅ |
| Header/footer detekcija (PDF) | `analiziraj_i_izvuci_tekst` ✅ | `document_processor.py` ✅ | ✅ |
| Čišćenje/sanitizacija | `unificiraj_navodnike`, `ocisti_leaked` ✅ | `utils.py` ✅ | ✅ |
| LLM prevođenje (paragraf/rečenica) | `prevedi_tekst_*` ✅ | `translator.py` ✅ | ✅ |
| Character lore memory | `likovi_memorija.json` (samo CHARACTERS) ⚠️ | `_memorija.json` (CHARACTERS+GLOSSARY+GRAMMAR) ✅ | ✅ (poboljšano) |
| Auto-detekcija modela | `detektiraj_aktivni_model()` via `/v1/models` ✅ | `detektiraj_aktivni_model()` → poziva nepostojeće metode ❌ | ❌ **REGRESIJA** |
| Checkpoint + resume | `spremi_progress` + `prikazi_progress_izvjestaj` (R/N/X) ✅ | `checkpoint.py` spremanje ✅ + resume u menu ❌ | ⚠️ |
| Progress bar s riječima | `prikazi_progres()` s `riječi: X/Y (Z%)` ✅ | `utils.py` `prikazi_progres()` + prevoditelj ✅ | ✅ |
| X tipka prekid | `detektiraj_x_tipku()` + `prikazi_prekid_meni()` ✅ | `utils.py` + `translator.py` ✅ | ✅ |
| TTS (naracija+dijalog+dramatski) | `generiraj_audio_poglavlje` ✅ | `tts_engine.py` ✅ | ✅ |
| MP3 imenovanje + ID3 | ❌ nije postojalo | `NNN_ChXX_partXXX` + ID3 ✅ | ✅ (novo) |
| FileManager | Dvije odvojene funkcije ⚠️ | `file_manager.py` klasa ✅ | ✅ |
| Ollama provider | ❌ nije postojao | `ollama_local` + `ollama_cloud` ✅ | ✅ (novo) |
| API ključevi `.env` | ❌ plain text u settings.py | `.env` via dotenv ✅ | ✅ |

---

## 5. PROBLEMI DETEKTIRANI U NOVOJ ARHITEKTURI

### 5.1 🔴 `detektiraj_aktivni_model()` — AttributeError
Poziva metode koje ne postoje. S default `auto_detect_model: true`, svaki `detektiraj_aktivni_model()` poziv puca.

### 5.2 🟡 `prevedi_knjigu()` — nema `resume_from` parametar
Checkpoint resume zahtijeva nastavak od određenog segmenta. Trenutna signatura `prevedi_knjigu(tekst, output_path, book_id, granularnost)` nema `resume_from`.

### 5.3 🟡 `Menu.run()` — ne rukuje `resume:` povratnom vrijednošću
Checkpoint blok je prikazan, ali odabir ne pokreće nastavak prijevoda.

### 5.4 🟡 `merge_single` — nedovršeno, TODO placeholder
"Jedna MP3 datoteka" opcija ne radi ispravno.

---

## 6. PLAN DORADE — PRIORITETI

### Prioritet 1 (kritično — pokvareno)
1. **Implementirati `_detect_lm_studio_model()` / `_detect_ollama_model()`** — popravak auto-detekcije.

### Prioritet 2 (funkcionalnost po specifikaciji — nedostaje)
2. **Implementirati checkpoint resume** — dodati `resume_from` u `prevedi_knjigu()`, obraditi `resume:` u `Menu.run()`.
3. **Generirati `_stats.txt`** — produkcijska statistika (paragrafi, riječi, znakovi, brzina, trajanje).

### Prioritet 3 (dovršiti)
4. **Implementirati `merge_single`** u `tts_engine.py` (pydub ili ffmpeg spajanje).
5. **Povezati `log_verbatim()` / `log_llm_response()`** u `translator.py` API pozive (trorazinsko logiranje postaje stvarno).

---

## 7. ZAKLJUČAK

Velika većina funkcionalnosti iz specifikacije i stare `mamba_voice.py` verzije je **uspješno migrirana i funkcionalna** (modularna arhitektura, YAML, CLI GUI, OPCIJE, header logika, per-book memorija, multi-provider API, `.env`, MP3 imenovanje, ID3, progress bar s riječima, X tipka).

**Kritični propusti koji NE SMEJU ostati:**
1. 🔴 **Auto-detekcija modela je pokvarena** (poziva nepostojeće metode) — regresija naspram mamba_voice.py.
2. 🟡 **Checkpoint resume nije funkcionalan** — blok se prikazuje, ali nastavak ne radi.
3. 🟡 **Produkcijska statistika `_stats.txt` ne postoji** — iako TODO tvrdi da jest.
4. 🟡 **TTS "Jedna datoteka" merge nije implementiran.**
5. 🟡 **LLM debug log (verbatim/llm_responses) je mrtav kod.**

TODO.md **treba ispraviti** — stavke koje tvrde "implementirano" a zapravo nisu funkcionalne moraju ostati neoznačene.
