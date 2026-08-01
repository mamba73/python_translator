# Dizajn: Refaktoriranje sustava logiranja

## Arhitekturni pregled

```
app/logger.py          ← jedini vlasnik LoggingSession + FlushFileHandler
    |
    +-- setup_logging(config) → kreira session_YYYYMMDD_HHMMSS/
    +-- get_session_log_dir() → vraća Path aktivne sesije (ili None)
    +-- log_verbatim()       → piše u verbatim.log (logger + direktni fallback)
    +-- log_llm_response()   → piše u llm_responses.log (logger + direktni fallback)

web_server.py
    |
    +-- _startup() → poziva setup_logging(config) umjesto _init_web_logging()
    +-- /stream-logs → čita app.log iz get_session_log_dir()
    +-- FlushFileHandler import iz app.logger (ne duplicira)

translator.py          ← poziva log_verbatim() i log_llm_response() (već implementirano)
    |
    +-- _http_request() → log_verbatim(payload_str, "request")
    +-- _http_request() → log_llm_response(prompt, response, metadata)
```

---

## Izmjene po datoteci

### 1. `app/logger.py`

#### Nova globalna varijabla

```python
# Putanja do aktivne sesije — postavlja setup_logging(), čita get_session_log_dir()
_SESSION_LOG_DIR: Path | None = None
```

#### Izmjena `setup_logging()`

```python
def setup_logging(config: dict[str, Any]) -> None:
    global _SESSION_LOG_DIR

    base_log_dir = Path(config["directories"]["logs"])

    # Kreiraj sesijski poddirektorij s vremenskim žigom
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = base_log_dir / f"session_{timestamp}"
    session_dir.mkdir(parents=True, exist_ok=True)
    _SESSION_LOG_DIR = session_dir

    root = logging.getLogger()
    # ... ostatak inicijalizacije s putanjama unutar session_dir ...
```

#### Nova javna funkcija

```python
def get_session_log_dir() -> Path | None:
    """Vraća putanju do direktorija aktivne sesije ili None ako nije inicijaliziran."""
    return _SESSION_LOG_DIR
```

#### Izmjena `log_verbatim()` — direktni fallback

```python
def log_verbatim(content: str, context: str = "") -> None:
    logger = logging.getLogger("verbatim")
    linija = f"=== {context} ===\n{content}\n"
    if logger.handlers:
        logger.info(linija)
    elif _SESSION_LOG_DIR:
        # Direktni upis ako logger nije konfiguriran ali sesija postoji
        path = _SESSION_LOG_DIR / "verbatim.log"
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%H:%M:%S')} - {linija}\n")
            f.flush()
```

Isti pattern za `log_llm_response()`.

---

### 2. `web_server.py`

#### Ukloniti

- `FlushFileHandler` klasu (duplicikat) — importati iz `app.logger`
- `_init_web_logging()` funkciju
- `WEB_LOG_FILE` konstantu
- Poziv `_init_web_logging()` pri importu i u `_startup()`

#### Dodati import

```python
from app.logger import FlushFileHandler, setup_logging, get_session_log_dir
```

#### Novi `_startup()`

```python
@app.on_event("startup")
async def _startup() -> None:
    from app.config_loader import load_global_config
    config = load_global_config()
    setup_logging(config)
    logging.info("MambaBookVoice Web GUI pokrenut.")
```

#### Izmjena `/stream-logs` WebSocket

```python
@app.websocket("/stream-logs")
async def stream_logs(websocket: WebSocket):
    await websocket.accept()
    try:
        await websocket.send_text("INFO Spojen na MambaBookVoice log stream.")

        # Dinamički dohvati putanju iz aktivne sesije
        session_dir = get_session_log_dir()
        if session_dir is None:
            await websocket.send_text("WARNING Log sesija još nije inicijalizirana.")
            await asyncio.sleep(1)
            session_dir = get_session_log_dir()

        log_file = (session_dir / "app.log") if session_dir else (LOG_DIR / "app.log")
        log_file.touch(exist_ok=True)

        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)  # skoči na kraj — ne šalji stare logove
            while True:
                # ... tail -f petlja identična trenutnoj implementaciji ...
```

---

### 3. `translator.py`

#### Izmjena `_http_request()` — verbatim upis payloada

Trenutna implementacija poziva `log_llm_response()` tek nakon uspješnog odgovora.
Potrebno je dodati upis payloada **prije** slanja zahtjeva:

```python
def _http_request(self, url: str, payload: dict[str, Any], ...) -> str:
    # NOVO: Verbatim upis cjelovitog payloada prije slanja
    try:
        import json as _json
        payload_str = _json.dumps(payload, ensure_ascii=False, indent=2)
        from app.logger import log_verbatim
        log_verbatim(payload_str, f"HTTP REQUEST → {url}")
    except Exception:
        pass

    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    # ... ostatak metode ...

    # Postojeći log_llm_response() poziv ostaje nepromjenjen
```

**Napomena**: `log_verbatim()` u `prevedi_segment()` već logira sirovi tekst segmenta.
U `_http_request()` logiramo kompletan payload (s modelom, temperaturom, sistemskim promptom).
Oba upisa su komplementarna — ne dupliciraju se.

---

## Redoslijed inicijalizacije

```
1. web_server.py se importira
   → nema više _init_web_logging() na razini modula

2. uvicorn pokreće server
   → FastAPI okida _startup() event

3. _startup():
   a. load_global_config() — učitava settings.yaml
   b. setup_logging(config) — kreira session_YYYYMMDD_HHMMSS/
      → postavlja root logger → app.log (unutar session dir)
      → postavlja verbatim logger → verbatim.log (unutar session dir)
      → postavlja llm_responses logger → llm_responses.log (unutar session dir)
      → sprema putanju u _SESSION_LOG_DIR
   c. logging.info("Server pokrenut.") → piše u session dir/app.log

4. WebSocket /stream-logs se spaja
   → get_session_log_dir() vraća sesijsku putanju
   → tail -f čita app.log iz sesijskog direktorija

5. API /api/prevedi poziva Translator._http_request()
   → log_verbatim(payload, "HTTP REQUEST") → verbatim.log ← VIŠE NIJE PRAZAN
   → log_llm_response(prompt, response) → llm_responses.log ← VIŠE NIJE PRAZAN
```

---

## Što se NE mijenja

- `log_verbatim()` i `log_llm_response()` potpisi ostaju isti
- `prevedi_segment()` u `translator.py` ostaje nepromjenjen
- CLI workflow (`main.py` → `setup_logging(config)`) već radi ispravno
- TTS engine, document processor, checkpoint manager — nema izmjena
- `settings.yaml` struktura ostaje ista
