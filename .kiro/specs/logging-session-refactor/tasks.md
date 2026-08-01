# Implementation Plan: Refaktoriranje sustava logiranja

## Overview

Refaktoriranje logging modula u tri datoteke (`app/logger.py`, `web_server.py`, `translator.py`) kako bi se riješio asinkroni zastoj koji uzrokuje da `verbatim.log` i `llm_responses.log` ostaju prazni (0 KB). Uvodi se sesijski direktorij s vremenskim žigom, unificirana inicijalizacija loggera i dinamička WebSocket putanja.

## Tasks

- [ ] 1. Refaktorirati app/logger.py — sesijski direktorij i fallback upisi
  - Dodaj `from datetime import datetime` import na vrh datoteke
  - Dodaj globalnu varijablu `_SESSION_LOG_DIR: Path | None = None`
  - Modificiraj `setup_logging()`: generiraj timestamp, kreiraj `session_YYYYMMDD_HHMMSS/` poddirektorij unutar base_log_dir, postavi `_SESSION_LOG_DIR`, sve tri log datoteke kreiraj unutar session_dir
  - Dodaj javnu funkciju `get_session_log_dir() -> Path | None`
  - Modificiraj `log_verbatim()`: ako `logger.handlers` postoji → koristi logger; elif `_SESSION_LOG_DIR` postoji → direktni `open(path, "a")` s `f.flush()`; else → tiho ignoriraj
  - Modificiraj `log_llm_response()` s identičnim fallback patternom kao `log_verbatim()`
  - Provjeri da `_setup_verbatim_logger()` i `_setup_llm_logger()` ne dodaju handlere ako već postoje (if not logger.handlers — već implementirano, ostaje nepromijenjeno)

- [ ] 2. Refaktorirati web_server.py — ukloniti duplicirani logging kod
  - Dodaj import: `from app.logger import FlushFileHandler, setup_logging, get_session_log_dir`
  - Ukloni cijelu `FlushFileHandler` klasu iz `web_server.py` (duplicikat)
  - Ukloni cijelu `_init_web_logging()` funkciju
  - Ukloni konstantu `WEB_LOG_FILE` i njen poziv `_init_web_logging()` pri importu modula
  - Zamijeni tijelo `_startup()` event handlera: učitaj config, pozovi `setup_logging(config)`, logiraj startup poruku
  - Zadrži `LOG_DIR` konstantu (koristi se za fallback u WebSocket-u)
  - Depends on: 1

- [ ] 3. Modificirati WebSocket /stream-logs za dinamičnu putanju
  - Na početku `stream_logs()` dohvati sesijsku putanju: `session_dir = get_session_log_dir()` i `log_file = (session_dir / "app.log") if session_dir else (LOG_DIR / "app.log")`
  - Ako `session_dir` je None u trenutku spajanja, pošalji warning poruku klijentu i pokušaj ponovo nakon 1s (startup još nije završio)
  - Ostatak tail-f logike ostaje identičan — samo se mijenja izvor `log_file`
  - Depends on: 2

- [ ] 4. Dodati verbatim upis payloada u translator.py → _http_request()
  - Na početku `_http_request()`, **prije** `data = json.dumps(...)`, dodaj blok koji poziva `log_verbatim(payload_str, f"HTTP REQUEST → {url}")` unutar try/except
  - Provjeri da je `log_verbatim` već importiran na vrhu datoteke (jest — `from app.logger import log_llm_response, log_verbatim`)
  - Za Gemini adapter `_call_gemini()`: dodaj poziv `log_llm_response(user_msg, result, {...})` nakon parsiranja Gemini response formata, identično kao u standardnom `_http_request()` bloku
  - Depends on: 1

- [ ] 5. Verifikacija — statička provjera koda i ispravnost importa
  - Provjeri da `app/logger.py` ne sadrži sintaksne greške (get_diagnostics)
  - Provjeri da `web_server.py` ne sadrži sintaksne greške i nema više `FlushFileHandler` klase niti `_init_web_logging()` funkcije
  - Provjeri da `translator.py` nema sintaksnih grešaka i da `log_verbatim` poziv postoji u `_http_request()`
  - Provjeri da `get_session_log_dir` import postoji u `web_server.py`
  - Depends on: 3, 4

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": [1] },
    { "wave": 2, "tasks": [2, 4] },
    { "wave": 3, "tasks": [3] },
    { "wave": 4, "tasks": [5] }
  ]
}
```

## Notes

- `FlushFileHandler` mora biti samo u `app/logger.py` — `web_server.py` ga importira
- CLI workflow (`main.py`) već poziva `setup_logging(config)` ispravno — ne treba mijenjati
- `settings.yaml` već ima `logging.verbatim: true` i `logging.llm_responses: true`
- WebSocket fallback putanja `LOG_DIR / "app.log"` je za slučaj da se `_startup()` još nije izvršio
