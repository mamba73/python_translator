# TODO — Dynamic Book Translator v0.4

> Ref: `doc/README_TechDoc.md` · `doc/2026-07-31_110820_analiza_upgrade01.md`

---

## FAZA 1 — Struktura direktorija i konfiguracija ✅

- [x] Kreirati `app/` direktorij (prazni moduli kao placeholder)
- [x] Kreirati `work/input/`
- [x] Kreirati `work/output/`
- [x] Kreirati `work/translated/`
- [x] Kreirati `work/audiobooks/`
- [x] Kreirati `work/state/`
- [x] Kreirati `work/logs/`
- [x] Kreirati `config/settings.yaml` — migrirati iz `config/settings.py`
- [x] Kreirati `config/profile_sf_literature.yaml`
- [x] Kreirati `config/profile_it_technical.yaml`
- [x] Kreirati `config/profile_general.yaml`
- [x] Kreirati `.env.example` (prazni ključevi: OPENAI, GEMINI, QWEN, OLLAMA, CUSTOM)
- [x] Dodati `.env` i `work/` u `.gitignore`
- [x] Ažurirati `requirements.txt` — dodati `pyyaml`, `python-dotenv`, `mutagen`

---

## FAZA 2 — Infrastrukturni moduli (`app/`) ✅

- [x] `app/config_loader.py`
  - [x] `load_global_config()` — čita `config/settings.yaml`
  - [x] `load_book_config()` — čita `work/output/<Knjiga>/config.yaml`
  - [x] `merge_config()` — spaja global + book config
  - [x] Čitanje API ključeva iz `.env` via `python-dotenv`

- [x] `app/file_manager.py`
  - [x] `ensure_dir(path, suffix_if_exists)` — kreira dir, suffix `_001`
  - [x] `ensure_file_path(path, suffix_if_exists)` — suffix `(001)`
  - [x] `ensure_directories()` — kreira sve `work/` direktorije pri startu
  - [x] `book_output_dir(title, author)` — `work/translated/<naziv---autor>/`
  - [x] `audiobook_dir(title, author)` — `work/audiobooks/<naziv---autor>/`

- [x] `app/logger.py`
  - [x] `setup_logging(config)` — osnovno + verbatim + LLM response log
  - [x] `log_basic()`, `log_verbatim()`, `log_llm_response()`

- [x] `app/utils.py`
  - [x] `sanitiziraj_naziv()` — migrirati iz `mamba_voice.py`
  - [x] `prikazi_progres()` — migrirati
  - [x] `ocisti_ekran()` — migrirati
  - [x] `detektiraj_x_tipku()` — migrirati (Windows + Linux)
  - [x] `unificiraj_navodnike()` — migrirati
  - [x] `ocisti_leaked_prijevod()` — migrirati

---

## FAZA 3 — Funkcionalni moduli (migracija iz `mamba_voice.py`) ⚠️

- [x] `app/document_processor.py`
  - [x] `ucitaj_izvorni_tekst()` — migrirati (.pdf, .docx, .txt, .epub, .mobi)
  - [x] `analiziraj_i_izvuci_tekst()` — migrirati (header/footer detekcija)
  - [x] `segmentiraj_poglavlja()` — migrirati
  - [x] Ukloniti `segmentiraj_poglavlja_po_odlomcima()` — mrtav kod

- [x] `app/text_cleaner.py`
  - [x] `ocisti_dokument()` — wrapper koji pokreće čišćenje i sprema `[fixed]`
  - [x] `kreiraj_memoriju()` — auto-kreiranje `<Knjiga>_memorija.json` s CHARACTERS/GLOSSARY/GRAMMAR_FIXES
  - [x] `kreiraj_book_config()` — generira `work/output/<Knjiga>/config.yaml` iz profil predloška

- [x] `app/translator.py`
  - [x] `_api_call(messages, config)` — privatna metoda, objedinjuje duplikat koda
  - [x] `_build_payload()` — gradi API payload
  - [x] `_http_request()` — potpun HTTP 429 retry mehanizam s odbrojavanjem sekundu po sekundu, konfigurabilnim retry parametrima (`retry_max_attempts`, `retry_initial_delay`, `retry_backoff_factor`) i korisničkim odabirom (Y/X) nakon iscrpljenih pokušaja
  - [x] Adaptori po provideru: `lm_studio`, `ollama_local`, `ollama_cloud`, `openai`, `gemini`, `qwen`, `custom`
  - [x] `detektiraj_aktivni_model()` — automatska detekcija LM Studio / Ollama aktivnog modela s detaljima
  - [x] `je_strukturni_ili_kratak()` — migrirati (konfigurabilna minimalna duljina)
  - [x] `generiraj_system_prompt_sa_memorijom()` — proširiti na CHARACTERS + GLOSSARY + GRAMMAR_FIXES
  - [x] `prevedi_segment()` — unificirana metoda za odlomak/paragraf/rečenicu
  - [x] `prevedi_knjigu()` — produkcijski prijevod, čisti output, checkpoint
  - [x] `prevedi_test()` — testni prijevod, header kao opcija, sprema `last_test.json`
  - [x] `prikazi_prekid_meni()` — migrirati
  - [x] **Zero Hardcoding** — sve konfiguracijske postavke čitaju se iz `config/settings.yaml` i `config.yaml`

- [x] `app/checkpoint.py`
  - [x] `atomic_write()` / `atomic_write_json()` — migrirati
  - [x] `spremi_checkpoint(book_data)` — multi-book struktura (`translation_checkpoints.json`)
  - [x] `ucitaj_checkpointe()` — vraća listu svih aktivnih
  - [x] `obrisi_checkpoint(book_id)`
  - [x] `spremi_last_test(params)` — sprema `last_test.json`
  - [x] `ucitaj_last_test()`

- [x] `app/tts_engine.py`
  - [x] `izracunaj_segmente(recenice, config)` — pre-calculation algoritam (ref: TechDoc §10.5)
  - [x] `generiraj_segment_mp3(tekst, putanja, config)` — async edge-tts, naracija+dijalog+dramatski mod
  - [x] `upiši_id3_tagove(putanja, metadata)` — via `mutagen`
  - [x] `generiraj_audiobook(book_config, fm)` — orchestracija: segmenti → MP3 → ID3
  - [x] Imenovanje: `NNN_ChXX_partXXX.mp3` (globalni + poglavlje + dio brojač)
  - [x] Merge zadnjeg segmenta ako < `min_segment_words` (ref: TechDoc §10.5.3)

---

## FAZA 4 — CLI sučelje ✅

- [x] `app/menu.py`
  - [x] Kursorska navigacija (↑↓ + Enter/Space) — Windows (`msvcrt`+ANSI) + Linux (`curses`)
  - [x] `show_main()` — glavni izbornik s checkpoint blokom i BRZI TEST linijom
  - [x] `show_phase1()` — konverzija, batch odabir
  - [x] `show_phase2()` — čišćenje, batch odabir
  - [x] `show_phase3()` — prevođenje: `[1]` test / `[2]` knjiga / `[0]` opcije
  - [x] `show_opcije()` — dropdown Header (DA/NE) + Granularnost + Količina
  - [x] `show_phase4()` — TTS: zasebni segmenti / jedna datoteka
  - [x] Notifikacijska linija u `[3]`: `── Granularnost: Paragraf | Količina: 1 | Header: DA ──`
  - [x] `[X]` povratak na svakom podizbjorniku
  - [x] Izlaz s potvrdom `Y/N`

---

## FAZA 5 — Integracija i `main.py` ⚠️

- [x] `main.py` — čisti orkestrator, samo pozivi modula iz `app/`
- [x] Checkpoint blok na vrhu glavnog izbornika — podržava 1-click nastavak preko `Menu.run()` i `resume_from` parametra u `prevedi_knjigu()`
- [x] BRZI TEST (`Y`) — 1-click pokretanje iz `last_test.json`
- [x] Batch odabir: `1`, `1,3,5`, `1-5`, `*` — u svim fazama
- [x] Per-book `config.yaml` — kreirati pri prvoj obradi ako ne postoji
- [x] TEST output → `<naziv>_test_<timestamp>.txt` (header po opciji)
- [x] Produkcija output → `<naziv>.txt` (uvijek čisti tekst)
- [ ] Produkcija statistike → `<naziv>_stats.txt` — **NEDOSTAJE** (nije generirana; TechDoc §9.5 zahtijeva zasebnu datoteku s parametrima, brojem riječi/znakova, brzinom)

---

## FAZA 6 — Poliranje i verifikacija ⚠️

- [ ] TTS "Jedna datoteka" (`merge_single`) — **NEDOVRŠENO** (`tts_engine.py` ima TODO placeholder; vraća sve segmente umjesto spojene MP3)
- [x] Trorazinsko logiranje — `log_verbatim()` i `log_llm_response()` su integrirani i aktivni u `translator.py`

- [x] Zamijeniti sve globalne varijable s instance atributima klasa
- [x] Ukloniti `mamba_voice.py` nakon što su svi moduli migrirani i verificirani
- [x] Ukloniti `config/settings.py` nakon migracije na `settings.yaml`
- [x] End-to-end test: konverzija → čišćenje → TEST prijevod → produkcijski prijevod → TTS
- [x] Verificirati `.gitignore` (`.env`, `work/`, `__pycache__`)
- [x] Ažurirati `./start` bootstrap skriptu za novu strukturu
