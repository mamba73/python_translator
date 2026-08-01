"""
web_server.py — FastAPI web server za MambaBookVoice Web GUI
Pokreće se opcijom [5] iz CLI izbornika ili direktno.
Port: http://localhost:8000
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from app.logger import FlushFileHandler, setup_logging, get_session_log_dir

# Učitaj .env odmah pri importu — prije bilo kakvih config poziva
try:
    from dotenv import load_dotenv as _load_dotenv_now
    _load_dotenv_now(dotenv_path=Path(__file__).resolve().parent / ".env", override=True)
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Putanje
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = ROOT / "public"
CONFIG_DIR = ROOT / "config"
WORK_DIR = ROOT / "work"
INPUT_DIR = WORK_DIR / "input"
OUTPUT_DIR = WORK_DIR / "output"
TRANSLATED_DIR = WORK_DIR / "translated"
STATE_DIR = WORK_DIR / "state"
LOG_DIR = WORK_DIR / "logs"

sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="MambaBookVoice Web GUI", version="1.0.0")

# Statičke datoteke
app.mount("/css", StaticFiles(directory=str(PUBLIC_DIR / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(PUBLIC_DIR / "js")), name="js")


@app.on_event("startup")
async def _startup() -> None:
    """Inicijalizira logging s vremenskim žigom sesije.

    Kreira work/logs/session_YYYYMMDD_HHMMSS/ i inicijalizira sve loggere
    (app.log, verbatim.log, llm_responses.log) unutar sesijskog direktorija.
    """
    from app.config_loader import load_global_config
    config = load_global_config()
    setup_logging(config)
    logging.info("MambaBookVoice Web GUI pokrenut.")


# ---------------------------------------------------------------------------
# HTML stranice
# ---------------------------------------------------------------------------
@app.get("/")
async def index():
    return FileResponse(str(PUBLIC_DIR / "index.html"))


@app.get("/konverzija")
async def konverzija_page():
    return FileResponse(str(PUBLIC_DIR / "konverzija.html"))


@app.get("/ciscenje")
async def ciscenje_page():
    return FileResponse(str(PUBLIC_DIR / "ciscenje.html"))


@app.get("/prevod")
async def prevod_page():
    return FileResponse(str(PUBLIC_DIR / "prevod.html"))


@app.get("/mp3")
async def mp3_page():
    return FileResponse(str(PUBLIC_DIR / "mp3.html"))


# ---------------------------------------------------------------------------
# WebSocket — live console log stream (tail -f mehanizam)
# ---------------------------------------------------------------------------
@app.websocket("/stream-logs")
async def stream_logs(websocket: WebSocket):
    """Čita app.log iz aktivne sesije kao 'tail -f' i šalje svaku novu liniju."""
    await websocket.accept()
    try:
        await websocket.send_text("INFO Spojen na MambaBookVoice log stream.")

        # Dinamički dohvati putanju iz aktivne sesije
        session_dir = get_session_log_dir()
        if session_dir is None:
            await websocket.send_text("WARNING Log sesija još nije inicijalizirana, čekam...")
            await asyncio.sleep(1)
            session_dir = get_session_log_dir()

        log_file = (session_dir / "app.log") if session_dir else (LOG_DIR / "app.log")
        log_file.touch(exist_ok=True)

        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            # Skoči na kraj datoteke — ne šalji stare logove
            f.seek(0, 2)

            while True:
                # Provjeri dolazi li disconnect od klijenta (non-blocking)
                try:
                    _ = await asyncio.wait_for(
                        websocket.receive_text(), timeout=0.1
                    )
                except asyncio.TimeoutError:
                    pass  # Nema poruke od klijenta — normalno, nastavi tail
                except WebSocketDisconnect:
                    break

                # Čitaj sve nove linije koje su stigle od zadnjeg čitanja
                while True:
                    linija = f.readline()
                    if not linija:
                        break
                    linija = linija.strip()
                    if linija:
                        try:
                            await websocket.send_text(linija)
                        except Exception:
                            return  # Klijent se odspojio

                # Kratka pauza da ne opteretimo CPU
                await asyncio.sleep(0.2)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logging.warning("WebSocket /stream-logs greška: %s", exc)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# API — Podaci za Dashboard (index)
# ---------------------------------------------------------------------------
@app.get("/api/status")
async def api_status():
    """Vraća status sustava: checkpointi, LM Studio veza."""
    checkpointi = _ucitaj_checkpointe()

    # Provjeri LM Studio dostupnost
    lm_studio_ok = await _provjeri_lm_studio()

    # Sistemsko opterećenje (CPU/RAM ako psutil dostupan)
    sys_info = _dohvati_sys_info()

    return JSONResponse({
        "checkpointi": checkpointi,
        "lm_studio_online": lm_studio_ok,
        "sys_info": sys_info,
        "timestamp": datetime.now().isoformat()
    })


@app.get("/api/checkpointi")
async def api_checkpointi():
    return JSONResponse({"checkpointi": _ucitaj_checkpointe()})


# ---------------------------------------------------------------------------
# API — Konverzija (Korak 1)
# ---------------------------------------------------------------------------
@app.get("/api/input-datoteke")
async def api_input_datoteke():
    """Lista datoteka u work/input/ s metapodacima."""
    if not INPUT_DIR.exists():
        return JSONResponse({"datoteke": []})

    podrzani = {'.pdf', '.docx', '.doc', '.epub', '.mobi', '.txt'}
    datoteke = []
    for p in INPUT_DIR.rglob("*"):
        if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in podrzani:
            try:
                st = p.stat()
                datoteke.append({
                    "ime": p.name,
                    "rel_path": str(p.relative_to(INPUT_DIR)).replace("\\", "/"),
                    "tip": p.suffix.upper().lstrip("."),
                    "velicina": _format_velicina(st.st_size),
                    "velicina_bytes": st.st_size,
                    "izmijenjeno": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "mtime": st.st_mtime
                })
            except OSError:
                pass

    datoteke.sort(key=lambda x: x["mtime"], reverse=True)
    return JSONResponse({"datoteke": datoteke})


class KonverzijaRequest(BaseModel):
    datoteke: list[str]
    format: str = "txt"  # "txt" ili "md"


@app.post("/api/konvertuj")
async def api_konvertuj(req: KonverzijaRequest):
    """Pokreće konverziju odabranih datoteka."""
    try:
        from app.config_loader import load_global_config
        from app.document_processor import DocumentProcessor
        from app.file_manager import FileManager
        from app.config_loader import create_book_config

        config = load_global_config()
        fm = FileManager(config)
        dp = DocumentProcessor(config)

        rezultati = []
        for rel_path in req.datoteke:
            putanja = INPUT_DIR / rel_path
            if not putanja.exists():
                rezultati.append({"datoteka": rel_path, "status": "greška", "poruka": "Datoteka ne postoji"})
                continue
            try:
                logging.info(f"[KONVERZIJA] Počinje: {rel_path}")
                tekst = dp.ucitaj_izvorni_tekst(str(putanja))
                book_title = putanja.stem
                book_dir = fm.work_output_book_dir(book_title)
                ext = f".{req.format}"
                izlazna = fm.ensure_file_path(book_dir / f"{book_title}{ext}", suffix_if_exists=True)
                with open(izlazna, 'w', encoding='utf-8') as f:
                    f.write(tekst)
                config_p = book_dir / "config.yaml"
                if not config_p.exists():
                    create_book_config(book_dir, book_title, "Autor", putanja.name)
                logging.info(f"[KONVERZIJA] Završeno: {izlazna.name}")
                rezultati.append({"datoteka": rel_path, "status": "ok", "izlaz": str(izlazna.name)})
            except Exception as e:
                logging.error(f"[KONVERZIJA] Greška {rel_path}: {e}")
                rezultati.append({"datoteka": rel_path, "status": "greška", "poruka": str(e)})

        return JSONResponse({"rezultati": rezultati})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# API — Čišćenje (Korak 2)
# ---------------------------------------------------------------------------
@app.get("/api/output-datoteke")
async def api_output_datoteke():
    """Lista svih .txt datoteka iz work/output/ uključujući _001 sufikse."""
    if not OUTPUT_DIR.exists():
        return JSONResponse({"datoteke": []})

    datoteke = []
    for p in OUTPUT_DIR.rglob("*.txt"):
        if p.is_file() and "_memorija" not in p.name:
            try:
                st = p.stat()
                je_fixed = "[fixed]" in p.stem.lower()
                datoteke.append({
                    "ime": p.name,
                    "rel_path": str(p.relative_to(OUTPUT_DIR)).replace("\\", "/"),
                    "knjiga": p.parent.name if p.parent != OUTPUT_DIR else "",
                    "je_fixed": je_fixed,
                    "velicina": _format_velicina(st.st_size),
                    "izmijenjeno": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "mtime": st.st_mtime
                })
            except OSError:
                pass

    datoteke.sort(key=lambda x: x["mtime"], reverse=True)
    return JSONResponse({"datoteke": datoteke})


class CiscanjeRequest(BaseModel):
    datoteke: list[str]


@app.post("/api/ocisti")
async def api_ocisti(req: CiscanjeRequest):
    """Pokreće čišćenje odabranih datoteka."""
    try:
        from app.config_loader import load_global_config
        from app.text_cleaner import TextCleaner, generiraj_inkrementalnu_putanju
        from app.file_manager import FileManager

        config = load_global_config()
        fm = FileManager(config)
        tc = TextCleaner(fm, config)

        rezultati = []
        for rel_path in req.datoteke:
            putanja = OUTPUT_DIR / rel_path
            if not putanja.exists():
                rezultati.append({"datoteka": rel_path, "status": "greška", "poruka": "Ne postoji"})
                continue
            try:
                logging.info(f"[ČIŠĆENJE] Počinje: {rel_path}")
                with open(putanja, 'r', encoding='utf-8') as f:
                    tekst = f.read()
                book_title = putanja.stem
                book_dir = putanja.parent if putanja.parent != OUTPUT_DIR else fm.work_output_book_dir(book_title)
                ociscen = tc.ocisti_dokument(tekst, book_title)
                izlaz = Path(generiraj_inkrementalnu_putanju(str(book_dir), book_title, ".txt"))
                with open(izlaz, 'w', encoding='utf-8') as f:
                    f.write(ociscen)
                logging.info(f"[ČIŠĆENJE] Završeno: {izlaz.name}")
                rezultati.append({"datoteka": rel_path, "status": "ok", "izlaz": izlaz.name})
            except Exception as e:
                logging.error(f"[ČIŠĆENJE] Greška {rel_path}: {e}")
                rezultati.append({"datoteka": rel_path, "status": "greška", "poruka": str(e)})

        return JSONResponse({"rezultati": rezultati})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# API — Prijevod (Korak 3)
# ---------------------------------------------------------------------------
@app.get("/api/fixed-datoteke")
async def api_fixed_datoteke():
    """Lista isključivo [fixed] datoteka iz work/output/."""
    if not OUTPUT_DIR.exists():
        return JSONResponse({"datoteke": []})

    datoteke = []
    for p in OUTPUT_DIR.rglob("*.txt"):
        if p.is_file() and "[fixed]" in p.stem.lower():
            try:
                st = p.stat()
                datoteke.append({
                    "ime": p.name,
                    "rel_path": str(p.relative_to(OUTPUT_DIR)).replace("\\", "/"),
                    "knjiga": p.parent.name,
                    "izmijenjeno": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "mtime": st.st_mtime
                })
            except OSError:
                pass

    datoteke.sort(key=lambda x: x["mtime"], reverse=True)
    return JSONResponse({"datoteke": datoteke})


@app.get("/api/profili")
async def api_profili():
    """Lista dostupnih konfiguracionih profila."""
    profili = []
    for p in CONFIG_DIR.glob("profile_*.yaml"):
        naziv = p.stem.replace("profile_", "")
        profili.append({"id": naziv, "ime": naziv.replace("_", " ").title()})
    return JSONResponse({"profili": profili})


@app.get("/api/provider")
async def api_get_provider():
    """Vraća trenutno aktivni provider i listu dostupnih iz settings.yaml."""
    try:
        from app.config_loader import load_global_config
        cfg = load_global_config()

        providers_list = cfg.get("api", {}).get("providers", [])
        active_provider_name = cfg.get("api", {}).get("provider", "")
        active_model_name = cfg.get("api", {}).get("model", "")

        active_title = "Unknown"
        for p_cfg in providers_list:
            if p_cfg.get("provider") == active_provider_name and p_cfg.get("model") == active_model_name:
                active_title = p_cfg.get("title", "Unknown")
                break

        return JSONResponse({
            "active": f"{active_provider_name}:{active_model_name}",
            "title": active_title,
            "providers": providers_list
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ProviderRequest(BaseModel):
    provider: str


@app.post("/api/provider")
async def api_set_provider(req: ProviderRequest):
    """Mijenja aktivni provider u settings.yaml."""
    try:
        import yaml
        from app.config_loader import load_global_config, save_settings
        config = load_global_config()

        # req.provider će biti u formatu "provider_type:model_name"
        provider_type, model_name = req.provider.split(":", 1)

        providers_list = config.get("api", {}).get("providers", [])
        selected_provider_cfg = None
        for p_cfg in providers_list:
            if p_cfg.get("provider") == provider_type and p_cfg.get("model") == model_name:
                selected_provider_cfg = p_cfg
                break

        if not selected_provider_cfg:
            raise HTTPException(status_code=400, detail=f"Nepoznati provider/model: {req.provider}")

        config.setdefault("api", {})["provider"] = provider_type
        config.setdefault("api", {})["model"] = model_name
        title = selected_provider_cfg.get("title", req.provider)

        # Provjeri je li ključ dostupan za novi provider
        key_env = selected_provider_cfg.get("key_env")
        key_ok = True
        key_poruka = ""
        if key_env:
            val = os.getenv(key_env, "")
            if not val:
                key_ok = False
                key_poruka = f"Upozorenje: {key_env} nije postavljen u .env!"
        
        save_settings(config)

        logging.info(f"[PROVIDER] Promijenjen na: {req.provider} ({title})")
        return JSONResponse({
            "status": "ok",
            "provider": req.provider,
            "title": title,
            "key_ok": key_ok,
            "poruka": key_poruka
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/opcije")
async def api_opcije():
    """Vraća trenutne opcije prevođenja iz settings.yaml."""
    try:
        from app.config_loader import load_global_config
        config = load_global_config()
        t = config.get("translation", {})
        return JSONResponse({
            "granularnost": t.get("granularity", "paragraph"),
            "kolicina": t.get("default_count", 1),
            "header": t.get("test_header", True),
            "profil": "sf_literature"
        })
    except Exception as e:
        return JSONResponse({"greška": str(e)}, status_code=500)


class OpcijeSpremiRequest(BaseModel):
    granularnost: str | None = None
    kolicina: int | None = None
    header: bool | None = None
    profil: str | None = None


@app.post("/api/opcije")
async def api_opcije_spremi(req: OpcijeSpremiRequest):
    """Sprema opcije prevođenja u settings.yaml."""
    try:
        from app.config_loader import load_global_config, save_settings
        config = load_global_config()
        t = config.setdefault("translation", {})
        if req.granularnost is not None:
            t["granularity"] = req.granularnost
        if req.kolicina is not None:
            t["default_count"] = req.kolicina
        if req.header is not None:
            t["test_header"] = req.header
        save_settings(config)
        logging.info(f"[OPCIJE] Ažurirane: granularnost={req.granularnost}, kolicina={req.kolicina}, header={req.header}")
        return JSONResponse({"status": "ok"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class PrevodRequest(BaseModel):
    rel_path: str
    tip: str = "test"  # "test" | "produkcija"
    granularnost: str = "paragraph"
    kolicina: int = 1
    header: bool = True
    profil: str = "sf_literature"


@app.post("/api/prevedi")
async def api_prevedi(req: PrevodRequest):
    """Pokreće prijevod (TEST ili produkcijski)."""
    try:
        from app.config_loader import load_global_config
        from app.file_manager import FileManager
        from app.checkpoint import CheckpointManager
        from app.translator import Translator
        import yaml

        # load_dotenv ponovo da budemo sigurni da su ključevi dostupni
        try:
            from dotenv import load_dotenv as _ld
            _ld(dotenv_path=ROOT / ".env", override=True)
        except ImportError:
            pass

        config = load_global_config()

        # Provjeri API ključ za aktivni provider/model
        active_provider_name = config.get("api", {}).get("provider", "")
        active_model_name = config.get("api", {}).get("model", "")

        active_provider_cfg = None
        for p_cfg in config.get("api", {}).get("providers", []):
            if p_cfg.get("provider") == active_provider_name and p_cfg.get("model") == active_model_name:
                active_provider_cfg = p_cfg
                break
        
        if active_provider_cfg:
            key_env = active_provider_cfg.get("key_env")
            if key_env:
                api_key = os.getenv(key_env, "")
                if not api_key:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"API ključ nije pronađen! Provider "
                            f"\'{active_provider_cfg.get("title", "Unknown")}\' zahtijeva "
                            f"varijablu "
                            f"\'{key_env}\' u .env datoteci. "
                            f"Otvori .env i dodaj: {key_env}=tvoj_kljuc"
                        )
                    )


        fm = FileManager(config)
        cp = CheckpointManager(config, fm)
        translator = Translator(config, cp)

        putanja = OUTPUT_DIR / req.rel_path
        if not putanja.exists():
            raise HTTPException(status_code=404, detail="Datoteka ne postoji")

        knjiga_dir = putanja.parent
        with open(putanja, 'r', encoding='utf-8') as f:
            tekst = f.read()

        config_p = knjiga_dir / "config.yaml"
        book_config = None
        if config_p.exists():
            with open(config_p, 'r') as f:
                book_config = yaml.safe_load(f)

        translator.postavi_knjigu(str(knjiga_dir), book_config)
        logging.info(f"[PRIJEVOD] Počinje {req.tip}: {putanja.name}")

        if req.tip == "test":
            prijevod = translator.prevedi_test(tekst, granularnost=req.granularnost, kolicina=req.kolicina, header=req.header)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            naziv = f"{putanja.stem}_test_{timestamp}.txt"
            translated_book_dir = fm.ensure_dir(fm.book_output_dir(knjiga_dir.name, book_config.get("author", "Unknown") if book_config else "Unknown"), suffix_if_exists=False)
            izlaz = fm.ensure_file_path(translated_book_dir / naziv, suffix_if_exists=True)
            with open(izlaz, 'w', encoding='utf-8') as f:
                f.write(prijevod)
            logging.info(f"[PRIJEVOD] Završen test: {izlaz.name}")
            return JSONResponse({"status": "ok", "izlaz": str(izlaz.name), "tip": "test"})
        else:
            translated_book_dir = fm.ensure_dir(fm.book_output_dir(knjiga_dir.name, book_config.get("author", "Unknown") if book_config else "Unknown"), suffix_if_exists=False)
            izlaz = fm.ensure_file_path(translated_book_dir / f"{knjiga_dir.name}.txt", suffix_if_exists=True)
            prijevod, je_prekinuto = translator.prevedi_knjigu(tekst, output_path=str(izlaz), book_id=f"{knjiga_dir.name}_web", granularnost=req.granularnost)
            status = "prekinuto" if je_prekinuto else "ok"
            logging.info(f"[PRIJEVOD] Završen produkcijski: {izlaz.name} (status={status})")
            return JSONResponse({"status": status, "izlaz": str(izlaz.name), "tip": "produkcija"})

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"[PRIJEVOD] Greška: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# API — TTS / MP3 (Korak 4)
# ---------------------------------------------------------------------------
@app.get("/api/translated-datoteke")
async def api_translated_datoteke():
    """Lista prevedenih .txt datoteka iz work/translated/."""
    if not TRANSLATED_DIR.exists():
        return JSONResponse({"datoteke": []})

    datoteke = []
    for p in TRANSLATED_DIR.rglob("*.txt"):
        if p.is_file():
            try:
                st = p.stat()
                datoteke.append({
                    "ime": p.name,
                    "rel_path": str(p.relative_to(TRANSLATED_DIR)).replace("\\", "/"),
                    "knjiga": p.parent.name,
                    "je_test": "_test_" in p.name,
                    "velicina": _format_velicina(st.st_size),
                    "izmijenjeno": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "mtime": st.st_mtime
                })
            except OSError:
                pass

    datoteke.sort(key=lambda x: x["mtime"], reverse=True)
    return JSONResponse({"datoteke": datoteke})


class TTSRequest(BaseModel):
    rel_path: str
    nacin: str = "zasebne"  # "zasebne" | "jedna"


@app.post("/api/generiraj-mp3")
async def api_generiraj_mp3(req: TTSRequest):
    """Pokreće TTS sintezu. Automatski duplicira audiobook mapu ako već postoji."""
    try:
        from app.config_loader import load_global_config
        from app.file_manager import FileManager
        from app.tts_engine import TTSEngine
        import yaml

        config = load_global_config()
        fm = FileManager(config)
        tts = TTSEngine(config, fm)

        putanja = TRANSLATED_DIR / req.rel_path
        if not putanja.exists():
            raise HTTPException(status_code=404, detail="Datoteka ne postoji")

        knjiga_dir = putanja.parent
        with open(putanja, 'r', encoding='utf-8') as f:
            tekst = f.read()

        config_p = knjiga_dir / "config.yaml"
        book_config = None
        if config_p.exists():
            with open(config_p, 'r') as f:
                book_config = yaml.safe_load(f)

        # Autodupliciranje: ako mapa postoji, kreira _001, _002 itd.
        audiobook_dir = fm.ensure_dir(
            fm.audiobook_dir(knjiga_dir.name, book_config.get("author", "Unknown") if book_config else "Unknown"),
            suffix_if_exists=True,
        )

        logging.info(f"[TTS] Počinje: {putanja.name} → {audiobook_dir.name}")
        tts.generiraj_audiobook(
            tekst=tekst,
            book_title=knjiga_dir.name,
            book_config=book_config or {},
            output_dir=audiobook_dir,
            merge_single=(req.nacin == "jedna")
        )
        logging.info(f"[TTS] Završeno: {audiobook_dir}")
        return JSONResponse({"status": "ok", "izlaz": str(audiobook_dir.name)})

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"[TTS] Greška: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Pomoćne funkcije
# ---------------------------------------------------------------------------
def _ucitaj_checkpointe() -> list[dict[str, Any]]:
    cp_file = STATE_DIR / "translation_checkpoints.json"
    if not cp_file.exists():
        return []
    try:
        with open(cp_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        checkpointi = list(data.values()) if isinstance(data, dict) else data
        for cp in checkpointi:
            total = cp.get("total_segments", 1) or 1
            current = cp.get("current_segment", 0)
            cp["postotak"] = round((current / total) * 100, 1)
        return checkpointi
    except Exception:
        return []


async def _provjeri_lm_studio() -> bool:
    try:
        import asyncio
        import aiohttp  # type: ignore
        async with aiohttp.ClientSession() as session:
            async with session.get("http://127.0.0.1:1234/v1/models", timeout=aiohttp.ClientTimeout(total=3)) as r:
                return r.status == 200
    except Exception:
        # aiohttp nije dostupan ili server nije pokrenut
        try:
            import httpx  # type: ignore
            r = httpx.get("http://127.0.0.1:1234/v1/models", timeout=3)
            return r.status_code == 200
        except Exception:
            return False


def _dohvati_sys_info() -> dict[str, Any]:
    try:
        import psutil  # type: ignore
        return {
            "cpu": psutil.cpu_percent(interval=0.1),
            "ram_posto": psutil.virtual_memory().percent,
            "ram_gb": round(psutil.virtual_memory().used / 1e9, 1)
        }
    except ImportError:
        return {"cpu": None, "ram_posto": None, "ram_gb": None}


def _format_velicina(bytes_: int) -> str:
    if bytes_ < 1024:
        return f"{bytes_} B"
    if bytes_ < 1024 * 1024:
        return f"{bytes_ / 1024:.1f} KB"
    return f"{bytes_ / (1024 * 1024):.1f} MB"


# ---------------------------------------------------------------------------
# Pokretanje servera
# ---------------------------------------------------------------------------
def pokreni_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Pokreće uvicorn server. Koristi se iz CLI izbornika (opcija 5)."""
    import webbrowser
    import threading

    def otvori_browser():
        import time
        time.sleep(1.5)
        webbrowser.open(f"http://{host}:{port}")

    threading.Thread(target=otvori_browser, daemon=True).start()
    print(f"\n  Web GUI dostupan na: http://{host}:{port}")
    print("  Pritisnite Ctrl+C za zaustavljanje servera.\n")

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    pokreni_server()
