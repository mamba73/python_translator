# TODO — Dynamic Book Translator v0.4

> Ref: `doc/README_TechDoc.md` · `doc/2026-07-31_110820_analiza_upgrade01.md`

---

## FAZA 1 — Struktura direktorija i konfiguracija

- [ ] Kreirati `app/` direktorij (prazni moduli kao placeholder)
- [ ] Kreirati `work/input/`
- [ ] Kreirati `work/output/`
- [ ] Kreirati `work/translated/`
- [ ] Kreirati `work/audiobooks/`
- [ ] Kreirati `work/state/`
- [ ] Kreirati `work/logs/`
- [ ] Kreirati `config/settings.yaml` — migrirati iz `config/settings.py`
- [ ] Kreirati `config/profile_sf_literature.yaml`
- [ ] Kreirati `config/profile_it_technical.yaml`
- [ ] Kreirati `config/profile_general.yaml`
- [ ] Kreirati `.env.example` (prazni ključevi: OPENAI, GEMINI, QWEN, OLLAMA, CUSTOM)
- [ ] Dodati `.env` i `work/` u `.gitignore`
- [ ] Ažurirati `requirements.txt` — dodati `pyyaml`, `python-dotenv`, `mutagen`

---

## FAZA 2 — Infrastrukturni moduli (`app/`)

- [ ] `app/config_loader.py`
  - [ ] `load_global_config()` — čita `config/settings.yaml`
  - [ ] `load_book_config()` — čita `work/output/<Knjiga>/config.yaml`
  - [ ] `merge_config()` — spaja global + book config
  - [ ] Čitanje API ključeva iz `.env` via `python-dotenv`

- [ ] `app/file_manager.py`
  - [ ] `ensure_dir(path, suffix_if_exists)` — kreira dir, suffix `_001`
  - [ ] `ensure_file_path(path, suffix_if_exists)` — suffix `(001)`
  - [ ] `ensure_directories()` — kreira sve `work/` direktorije pri startu
  - [ ] `book_output_dir(title, author)` — `work/translated/<naziv---autor>/`
  - [ ] `audiobook_dir(title, author)` — `work/audiobooks/<naziv---autor>/`

- [ ] `app/logger.py`
  - [ ] `setup_logging(config)` — osnovno + verbatim + LLM response log
  - [ ] `log_basic()`, `log_verbatim()`, `log_llm_response()`

- [ ] `app/utils.py`
  - [ ] `sanitiziraj_naziv()` — migrirati iz `mamba_voice.py`
  - [ ] `prikazi_progres()` — migrirati
  - [ ] `ocisti_ekran()` — migrirati
  - [ ] `detektiraj_x_tipku()` — migrirati (Windows + Linux)
  - [ ] `unificiraj_navodnike()` — migrirati
  - [ ] `ocisti_leaked_prijevod()` — migrirati

---

## FAZA 3 — Funkcionalni moduli (migracija iz `mamba_voice.py`)

- [ ] `app/document_processor.py`
  - [ ] `ucitaj_izvorni_tekst()` — migrirati (.pdf, .docx, .txt, .epub, .mobi)
  - [ ] `analiziraj_i_izvuci_tekst()` — migrirati (header/footer detekcija)
  - [ ] `segmentiraj_poglavlja()` — migrirati
  - [ ] Ukloniti `segmentiraj_poglavlja_po_odlomcima()` — mrtav kod

- [ ] `app/text_cleaner.py`
  - [ ] `ocisti_dokument()` — wrapper koji pokreće čišćenje i sprema `[fixed]`
  - [ ] `kreiraj_memoriju()` — auto-kreiranje `<Knjiga>_memorija.json` s CHARACTERS/GLOSSARY/GRAMMAR_FIXES
  - [ ] `kreiraj_book_config()` — generira `work/output/<Knjiga>/config.yaml` iz profil predloška

- [ ] `app/translator.py`
  - [ ] `_api_call(messages, config)` — privatna metoda, objedinjuje duplikat koda
  - [ ] `_build_payload()` — gradi API payload
  - [ ] Adaptori po provideru: `lm_studio`, `ollama_local`, `ollama_cloud`, `openai`, `gemini`, `qwen`, `custom`
  - [ ] `detektiraj_aktivni_model()` — migrirati
  - [ ] `je_strukturni_ili_kratak()` — migrirati
  - [ ] `generiraj_system_prompt_sa_memorijom()` — proširiti na CHARACTERS + GLOSSARY + GRAMMAR_FIXES
  - [ ] `prevedi_segment()` — unificirana metoda za odlomak/paragraf/rečenicu
  - [ ] `prevedi_knjugu()` — produkcijski prijevod, čisti output, checkpoint
  - [ ] `prevedi_test()` — testni prijevod, header kao opcija, sprema `last_test.json`
  - [ ] `prikazi_prekid_meni()` — migrirati

- [ ] `app/checkpoint.py`
  - [ ] `atomic_write()` / `atomic_write_json()` — migrirati
  - [ ] `spremi_checkpoint(book_data)` — multi-book struktura (`translation_checkpoints.json`)
  - [ ] `ucitaj_checkpointe()` — vraća listu svih aktivnih
  - [ ] `obrisi_checkpoint(book_id)`
  - [ ] `spremi_last_test(params)` — sprema `last_test.json`
  - [ ] `ucitaj_last_test()`

- [ ] `app/tts_engine.py`
  - [ ] `izracunaj_segmente(recenice, config)` — pre-calculation algoritam (ref: TechDoc §10.5)
  - [ ] `generiraj_segment_mp3(tekst, putanja, config)` — async edge-tts, naracija+dijalog+dramatski mod
  - [ ] `upiši_id3_tagove(putanja, metadata)` — via `mutagen`
  - [ ] `generiraj_audiobook(book_config, fm)` — orchestracija: segmenti → MP3 → ID3
  - [ ] Imenovanje: `NNN_ChXX_partXXX.mp3` (globalni + poglavlje + dio brojač)
  - [ ] Merge zadnjeg segmenta ako < `min_segment_words` (ref: TechDoc §10.5.3)

---

## FAZA 4 — CLI sučelje

- [ ] `app/menu.py`
  - [ ] Kursorska navigacija (↑↓ + Enter/Space) — Windows (`msvcrt`+ANSI) + Linux (`curses`)
  - [ ] `show_main()` — glavni izbornik s checkpoint blokom i BRZI TEST linijom
  - [ ] `show_phase1()` — konverzija, batch odabir
  - [ ] `show_phase2()` — čišćenje, batch odabir
  - [ ] `show_phase3()` — prevođenje: `[1]` test / `[2]` knjiga / `[0]` opcije
  - [ ] `show_opcije()` — dropdown Header (DA/NE) + Granularnost + Količina
  - [ ] `show_phase4()` — TTS: zasebni segmenti / jedna datoteka
  - [ ] Notifikacijska linija u `[3]`: `── Granularnost: Paragraf | Količina: 1 | Header: DA ──`
  - [ ] `[X]` povratak na svakom podizbjorniku
  - [ ] Izlaz s potvrdom `Y/N`

---

## FAZA 5 — Integracija i `main.py`

- [ ] `main.py` — čisti orkestrator, samo pozivi modula iz `app/`
- [ ] Checkpoint blok na vrhu glavnog izbornika — 1-click nastavak
- [ ] BRZI TEST (`Y`) — 1-click pokretanje iz `last_test.json`
- [ ] Batch odabir: `1`, `1,3,5`, `1-5`, `*` — u svim fazama
- [ ] Per-book `config.yaml` — kreirati pri prvoj obradi ako ne postoji
- [ ] TEST output → `<naziv>_test_<timestamp>.txt` (header po opciji)
- [ ] Produkcija output → `<naziv>.txt` (uvijek čisti tekst)
- [ ] Produkcija statistike → `<naziv>_stats.txt` (opcionalno)

---

## FAZA 6 — Poliranje i verifikacija

- [ ] Zamijeniti sve globalne varijable s instance atributima klasa
- [ ] Ukloniti `mamba_voice.py` nakon što su svi moduli migrirani i verificirani
- [ ] Ukloniti `config/settings.py` nakon migracije na `settings.yaml`
- [ ] End-to-end test: konverzija → čišćenje → TEST prijevod → produkcijski prijevod → TTS
- [ ] Verificirati `.gitignore` (`.env`, `work/`, `__pycache__`)
- [ ] Ažurirati `./start` bootstrap skriptu za novu strukturu
