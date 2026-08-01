# Zahtjevi: Refaktoriranje sustava logiranja

## Kontekst

MambaBookVoice koristi tri log datoteke: `app.log`, `verbatim.log` i `llm_responses.log`.
Pozadinski procesi (prijevod, čišćenje, konverzija) rade ispravno, ali `verbatim.log` i
`llm_responses.log` ostaju trajno prazne (0 KB) jer moduli koji komuniciraju s LLM API-jem
nikad ne dobiju pristup odgovarajućim handlerima.

Dodatni problem: `web_server.py` inicijalizira vlastiti logging sustav neovisno od
`app/logger.py`, a WebSocket `/stream-logs` čita hardkodiranu putanju `web_server.log`
umjesto `app.log` koji prate pozadinski procesi.

---

## Funkcionalni zahtjevi

### REQ-1: Sesijski direktorij s vremenskim žigom

- Svako pokretanje (web server ili CLI) mora kreirati novi poddirektorij unutar `work/logs/`
  s formatom: `session_YYYYMMDD_HHMMSS/`
- Sve tri log datoteke (`app.log`, `verbatim.log`, `llm_responses.log`) moraju se kreirati
  isključivo unutar tog sesijskog direktorija
- Putanja aktivne sesije mora biti globalno dostupna unutar procesa

### REQ-2: Unificirana inicijalizacija loggera

- `web_server.py` ne smije duplicirati logiku inicijalizacije — mora pozivati `setup_logging()`
  iz `app/logger.py`
- `setup_logging()` mora biti idempotentno (sigurno za višestruke pozive, bez duplikacije
  handlera)
- Verbatim i LLM response loggeri moraju biti inicijalizirani uvijek kada je `web_server.py`
  aktivan, pod uvjetom da je `logging.verbatim` i `logging.llm_responses` uključen u
  `settings.yaml`

### REQ-3: Punjenje verbatim.log i llm_responses.log

- Svaki LLM API poziv u `translator.py` mora:
  - Prije slanja: zapisati kompletan payload (system prompt + user poruka + parametri) u
    `verbatim.log`
  - Nakon primitka: zapisati cijeli sirovi odgovor (s reasoning tokenima ako postoje) u
    `llm_responses.log`
- Oba upisa moraju koristiti `flush()` odmah nakon pisanja
- Upis mora funkcionirati i kada `logging` infrastruktura još nije inicijalizirana (fallback
  na direktni `open()` s `flush()`)

### REQ-4: WebSocket dinamična putanja

- `/stream-logs` WebSocket u `web_server.py` mora čitati `app.log` unutar **trenutno aktivne
  sesije** (`session_YYYYMMDD_HHMMSS/app.log`)
- WebSocket radi po `tail -f` principu: čita samo nove linije, ne šalje retroaktivne logove
- Putanja log datoteke mora biti dostupna iz globalnog stanja sesije, ne hardkodirana

---

## Nefunkcionalni zahtjevi

### REQ-5: Bez rušenja postojeće funkcionalnosti

- Svi API endpointi (`/api/konvertuj`, `/api/ocisti`, `/api/prevedi`, `/api/generiraj-mp3`)
  moraju nastaviti raditi identično
- CLI workflow kroz `main.py` mora nastaviti raditi identično
- `FlushFileHandler` klasa ne smije biti duplicirana — mora postojati samo u `app/logger.py`

### REQ-6: Trenutno ispiranje na disk

- Svaki `FileHandler` u sustavu mora koristiti `flush()` nakon svakog `emit()`
- Direktni upisi u `verbatim.log` i `llm_responses.log` (fallback put) moraju koristiti
  `with open(...) as f: f.write(...); f.flush()`
