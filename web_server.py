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
                    line = f.readline()
                    if not line:
                        break
                    line = line.strip()
                    if line:
                        try:
                            await websocket.send_text(line)
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
    checkpoints = _load_checkpoints()

    # Provjeri LM Studio dostupnost
    lm_studio_ok = await _check_lm_studio()

    # Sistemsko opterećenje (CPU/RAM ako psutil dostupan)
    sys_info = _get_system_info()

    return JSONResponse({
        "checkpoints": checkpoints,
        "lm_studio_online": lm_studio_ok,
        "sys_info": sys_info,
        "timestamp": datetime.now().isoformat()
    })


@app.get("/api/checkpoints")
async def api_checkpoints():
    return JSONResponse({"checkpoints": _load_checkpoints()})


@app.get("/api/checkpoint-status")
async def api_checkpoint_status(rel_path: str = ""):
    """Vraća status checkpointa za odabranu knjigu.

    Ako postoji checkpoint, vraća podatke o napretku i preporučuje
    resume. Frontend može pitati korisnika želi li nastaviti.
    """
    if not rel_path:
        return JSONResponse({"has_checkpoint": False})
    # book_id se gradi iz IMENA DIREKTORIJA knjige (book_dir.name),
    # identično kao u _run_production — ne iz stem-a datoteke.
    file_path = OUTPUT_DIR / rel_path
    book_dir_name = file_path.parent.name if file_path.parent != OUTPUT_DIR else Path(rel_path).stem
    book_id = f"{book_dir_name}_web"
    for cp in _load_checkpoints():
        if cp.get("book_id") == book_id:
            return JSONResponse({
                "has_checkpoint": True,
                "book_id": book_id,
                "current_segment": cp.get("current_segment", 0),
                "total_segments": cp.get("total_segments", 0),
                "progress_percent": cp.get("progress_percent", 0),
                "output_path": cp.get("output_path", ""),
            })
    return JSONResponse({"has_checkpoint": False})


# ---------------------------------------------------------------------------
# API — Metapodaci (naslov, autor, godina, jezik)
# ---------------------------------------------------------------------------
class MetadataRequest(BaseModel):
    rel_path: str
    title: str = ""
    author: str = ""
    year: str = ""
    language: str = "hr"


@app.get("/api/metadata")
async def api_get_metadata(rel_path: str = ""):
    """Vraća metapodatke za odabranu knjigu.

    Primarno učitava iz per-book config.yaml, a ako ne postoji, automatski ekstrahira.
    """
    try:
        from app.metadata import extract_book_metadata, load_book_metadata
        from app.config_loader import load_global_config, check_book_config

        config = load_global_config()

        # Pokušaj pronaći datoteku u work/input/, work/output/ ili work/translated/
        file_path = None
        for base in (INPUT_DIR, OUTPUT_DIR, TRANSLATED_DIR):
            candidate = base / rel_path
            if candidate.exists():
                file_path = candidate
                break

        if file_path is None:
            return JSONResponse({"title": "", "author": "", "year": "", "language": "hr", "source": "none"})

        # Automatska provjera i kreiranje per-book config.yaml i memorija.json
        book_dir = file_path.parent
        if book_dir != INPUT_DIR and book_dir != OUTPUT_DIR and book_dir != TRANSLATED_DIR:
            # Datoteka je unutar book direktorija — provjeri config
            check_book_config(book_dir)

        meta = load_book_metadata(file_path, INPUT_DIR, OUTPUT_DIR, TRANSLATED_DIR)

        # Ako smo u inputu i nemamo metapodatke, pokušaj ekstrakciju
        if not meta.get("title") and not meta.get("author"):
            meta = extract_book_metadata(file_path, config)

        return JSONResponse({
            "title": meta.get("title", ""),
            "author": meta.get("author", ""),
            "year": meta.get("year", ""),
            "language": meta.get("language", "hr"),
            "source": meta.get("source", "unknown"),
        })
    except Exception as e:
        logging.error(f"[METADATA] Greška pri dohvatu: {e}")
        return JSONResponse({"title": "", "author": "", "year": "", "language": "hr", "source": "error"})


@app.post("/api/metadata")
async def api_save_metadata(req: MetadataRequest):
    """Sprema metapodatke primarno u per-book config.yaml."""
    try:
        from app.metadata import save_book_metadata

        # Pronađi datoteku
        file_path = None
        for base in (INPUT_DIR, OUTPUT_DIR, TRANSLATED_DIR):
            candidate = base / req.rel_path
            if candidate.exists():
                file_path = candidate
                break

        if file_path is None:
            raise HTTPException(status_code=404, detail="Datoteka ne postoji")

        meta_path = save_book_metadata(
            file_path,
            title=req.title,
            author=req.author,
            year=req.year,
            language=req.language,
            source="config.yaml",
            input_dir=INPUT_DIR,
            output_dir=OUTPUT_DIR,
            translated_dir=TRANSLATED_DIR,
        )

        logging.info(f"[METADATA] Spremljeno u: {meta_path.name}")
        return JSONResponse({"status": "ok", "title": req.title, "author": req.author})
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"[METADATA] Greška pri spremanju: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# API — Provjera i kreiranje per-book konfiguracije
# ---------------------------------------------------------------------------
class CheckBookConfigRequest(BaseModel):
    rel_path: str = ""
    book_dir: str = ""


@app.post("/api/check-book-config")
async def api_check_book_config(req: CheckBookConfigRequest):
    """Provjerava i automatski kreira config.yaml i memorija.json za knjigu.

    Ako datoteke ne postoje, kreira ih s defaultnim postavkama i izvučenim
    metapodacima (naslov, autor) iz samog teksta ili naziva datoteke.
    Ako već postoje, jednostavno ih učitava.

    Ova funkcija se poziva na početku svakog od 4 WebUI koraka kako bi se
    osigurala per-book izolacija konfiguracije i memorije.
    """
    try:
        from app.config_loader import load_global_config, check_book_config
        from app.metadata import extract_book_metadata, load_book_metadata

        config = load_global_config()

        # Odredi book_dir — iz req.book_dir ili iz req.rel_path
        book_dir = None
        file_path = None

        if req.book_dir:
            book_dir = Path(req.book_dir)
        elif req.rel_path:
            # Pokušaj pronaći datoteku u work/input/, work/output/ ili work/translated/
            for base in (INPUT_DIR, OUTPUT_DIR, TRANSLATED_DIR):
                candidate = base / req.rel_path
                if candidate.exists():
                    file_path = candidate
                    break

            if file_path:
                book_dir = file_path.parent
                # Ako je datoteka u rootu output/ ili translated/, book_dir je roditelj
                if book_dir == OUTPUT_DIR or book_dir == TRANSLATED_DIR or book_dir == INPUT_DIR:
                    # Datoteka je u rootu — koristi stem kao naziv knjige
                    book_dir = OUTPUT_DIR / file_path.stem
                else:
                    # Datoteka je unutar book direktorija
                    pass

        if book_dir is None:
            return JSONResponse({
                "status": "error",
                "message": "Nije moguće odrediti direktorij knjige."
            })

        # Ekstrahiraj metapodatke ako imamo izvornu datoteku
        book_title = ""
        author = ""
        year = ""
        language = "hr"
        original_file = ""

        if file_path and file_path.exists():
            original_file = file_path.name
            meta = extract_book_metadata(file_path, config)
            book_title = meta.get("title", "") or file_path.stem
            author = meta.get("author", "") or "Unknown"
            year = meta.get("year", "")
            language = meta.get("language", "hr") or "hr"

        # Provjeri i kreiraj config.yaml i memorija.json
        book_cfg = check_book_config(
            book_dir,
            book_title=book_title,
            author=author,
            original_file=original_file,
            year=year,
            language=language,
        )

        # Vrati metapodatke iz config-a
        return JSONResponse({
            "status": "ok",
            "title": book_cfg.get("book_title", book_title),
            "author": book_cfg.get("author", author),
            "year": book_cfg.get("year", year),
            "language": book_cfg.get("language", language),
            "source": "config.yaml",
            "config_exists": True,
            "memorija_exists": True,
            "book_dir": str(book_dir),
        })
    except Exception as e:
        logging.error(f"[CONFIG] Greška pri provjeri book config: {e}")
        return JSONResponse({
            "status": "error",
            "message": str(e)
        })


# ---------------------------------------------------------------------------
# API — Konverzija (Korak 1)
# ---------------------------------------------------------------------------
@app.get("/api/input-files")
async def api_input_files():
    """Lista datoteka u work/input/ s metapodacima."""
    if not INPUT_DIR.exists():
        return JSONResponse({"files": []})

    supported = {'.pdf', '.docx', '.doc', '.epub', '.mobi', '.txt'}
    files = []
    for p in INPUT_DIR.rglob("*"):
        if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in supported:
            try:
                st = p.stat()
                files.append({
                    "name": p.name,
                    "rel_path": str(p.relative_to(INPUT_DIR)).replace("\\", "/"),
                    "type": p.suffix.upper().lstrip("."),
                    "size": _format_size(st.st_size),
                    "size_bytes": st.st_size,
                    "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "mtime": st.st_mtime
                })
            except OSError:
                pass

    files.sort(key=lambda x: x["mtime"], reverse=True)
    return JSONResponse({"files": files})


class ConvertRequest(BaseModel):
    files: list[str]
    format: str = "txt"  # "txt" ili "md"


@app.post("/api/convert")
async def api_convert(req: ConvertRequest):
    """Pokreće konverziju odabranih datoteka."""
    try:
        from app.config_loader import load_global_config
        from app.document_processor import DocumentProcessor
        from app.file_manager import FileManager
        from app.config_loader import check_book_config

        config = load_global_config()
        fm = FileManager(config)
        dp = DocumentProcessor(config)

        # Automatska ekstrakcija metapodataka (naslov, autor) na početku obrade
        from app.metadata import extract_book_metadata, copy_metadata_to_target
        from app.utils import prikazi_progres

        results = []
        total_files = len(req.files)
        processed = 0

        for rel_path in req.files:
            file_path = INPUT_DIR / rel_path
            if not file_path.exists():
                results.append({"file": rel_path, "status": "error", "message": "Datoteka ne postoji"})
                processed += 1
                continue
            try:
                # Progress od samog početka: parsiranje metapodataka
                prikazi_progres(processed, total_files,
                                f"Konverzija {processed + 1}/{total_files}",
                                f"Započinjem: {rel_path}")
                logging.info(f"[KONVERZIJA] Počinje: {rel_path}")

                # 1. Automatsko čitanje naslova i autora od samog početka
                logging.info(f"[METADATA] Čitam metapodatke iz: {file_path.name}")
                meta = extract_book_metadata(file_path, config)
                book_title = meta.get("title") or file_path.stem
                author = meta.get("author") or "Unknown"
                year = meta.get("year", "")
                language = meta.get("language", "hr")
                logging.info(f"[METADATA] Naslov: {book_title} | Autor: {author}")

                # 2. Učitaj tekst
                logging.info(f"[KONVERZIJA] Čitam tekst iz: {file_path.name}")
                text = dp.ucitaj_izvorni_tekst(str(file_path))

                # 3. Kreiraj per-book direktorij
                book_dir = fm.work_output_book_dir(book_title)
                ext = f".{req.format}"
                output_path = fm.ensure_file_path(book_dir / f"{book_title}{ext}", suffix_if_exists=True)
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(text)

                # 4. Provjeri i kreiraj config.yaml i memorija.json ako ne postoje
                check_book_config(
                    book_dir,
                    book_title=book_title,
                    author=author,
                    original_file=file_path.name,
                    year=year,
                    language=language,
                )

                # 5. Presnimi metapodatke iz input datoteke na output datoteku
                try:
                    copy_metadata_to_target(file_path, output_path, INPUT_DIR, OUTPUT_DIR, TRANSLATED_DIR)
                except Exception as meta_err:
                    logging.warning(f"[METADATA] Greška pri kopiranju metapodataka: {meta_err}")

                logging.info(f"[KONVERZIJA] Završeno: {output_path.name} (autor: {author})")
                prikazi_progres(processed + 1, total_files,
                                f"Konverzija {processed + 1}/{total_files}",
                                f"Završeno: {output_path.name}")
                results.append({
                    "file": rel_path, "status": "ok",
                    "output": str(output_path.name),
                    "output_dir": str(output_path.parent),
                    "title": book_title, "author": author
                })
            except Exception as e:
                logging.error(f"[KONVERZIJA] Greška {rel_path}: {e}")
                results.append({"file": rel_path, "status": "error", "message": str(e)})
            finally:
                processed += 1

        return JSONResponse({"results": results})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# API — Čišćenje (Korak 2)
# ---------------------------------------------------------------------------
@app.get("/api/output-files")
async def api_output_files():
    """Lista svih .txt datoteka iz work/output/ uključujući _001 sufikse."""
    if not OUTPUT_DIR.exists():
        return JSONResponse({"files": []})

    files = []
    for p in OUTPUT_DIR.rglob("*.txt"):
        if p.is_file() and "_memorija" not in p.name:
            try:
                st = p.stat()
                is_fixed = "[fixed]" in p.stem.lower()
                files.append({
                    "name": p.name,
                    "rel_path": str(p.relative_to(OUTPUT_DIR)).replace("\\", "/"),
                    "book": p.parent.name if p.parent != OUTPUT_DIR else "",
                    "is_fixed": is_fixed,
                    "size": _format_size(st.st_size),
                    "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "mtime": st.st_mtime
                })
            except OSError:
                pass

    files.sort(key=lambda x: x["mtime"], reverse=True)
    return JSONResponse({"files": files})


class CleanRequest(BaseModel):
    files: list[str]


@app.post("/api/clean")
async def api_clean(req: CleanRequest):
    """Pokreće čišćenje odabranih datoteka."""
    try:
        from app.config_loader import load_global_config, check_book_config
        from app.metadata import copy_metadata_to_target, extract_book_metadata
        from app.text_cleaner import TextCleaner, generiraj_inkrementalnu_putanju
        from app.file_manager import FileManager

        config = load_global_config()
        fm = FileManager(config)
        tc = TextCleaner(fm, config)

        results = []
        for rel_path in req.files:
            file_path = OUTPUT_DIR / rel_path
            if not file_path.exists():
                results.append({"file": rel_path, "status": "error", "message": "Ne postoji"})
                continue
            try:
                logging.info(f"[ČIŠĆENJE] Počinje: {rel_path}")
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
                book_title = file_path.stem
                book_dir = file_path.parent if file_path.parent != OUTPUT_DIR else fm.work_output_book_dir(book_title)

                # Provjeri i kreiraj config.yaml i memorija.json ako ne postoje
                meta = extract_book_metadata(file_path, config)
                check_book_config(
                    book_dir,
                    book_title=meta.get("title", book_title),
                    author=meta.get("author", "Unknown"),
                    original_file=file_path.name,
                    year=meta.get("year", ""),
                    language=meta.get("language", "hr"),
                )

                cleaned = tc.ocisti_dokument(text, book_title)
                output_path = Path(generiraj_inkrementalnu_putanju(str(book_dir), book_title, ".txt"))
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(cleaned)
                try:
                    copy_metadata_to_target(file_path, output_path, INPUT_DIR, OUTPUT_DIR, TRANSLATED_DIR)
                except Exception as meta_err:
                    logging.warning(f"[METADATA] Greška pri kopiranju metapodataka tijekom čišćenja: {meta_err}")
                logging.info(f"[ČIŠĆENJE] Završeno: {output_path.name}")
                results.append({
                    "file": rel_path, "status": "ok",
                    "output": output_path.name,
                    "output_dir": str(output_path.parent)
                })
            except Exception as e:
                logging.error(f"[ČIŠĆENJE] Greška {rel_path}: {e}")
                results.append({"file": rel_path, "status": "error", "message": str(e)})

        return JSONResponse({"results": results})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# API — Prijevod (Korak 3)
# ---------------------------------------------------------------------------
@app.get("/api/fixed-files")
async def api_fixed_files():
    """Lista isključivo [fixed] datoteka iz work/output/."""
    if not OUTPUT_DIR.exists():
        return JSONResponse({"files": []})

    files = []
    for p in OUTPUT_DIR.rglob("*.txt"):
        if p.is_file() and "[fixed]" in p.stem.lower():
            try:
                st = p.stat()
                files.append({
                    "name": p.name,
                    "rel_path": str(p.relative_to(OUTPUT_DIR)).replace("\\", "/"),
                    "book": p.parent.name,
                    "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "mtime": st.st_mtime
                })
            except OSError:
                pass

    files.sort(key=lambda x: x["mtime"], reverse=True)
    return JSONResponse({"files": files})


@app.get("/api/profiles")
async def api_profiles():
    """Lista dostupnih konfiguracionih profila."""
    profiles = []
    for p in CONFIG_DIR.glob("profile_*.yaml"):
        name = p.stem.replace("profile_", "")
        profiles.append({"id": name, "name": name.replace("_", " ").title()})
    return JSONResponse({"profiles": profiles})


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
        key_message = ""
        if key_env:
            val = os.getenv(key_env, "")
            if not val:
                key_ok = False
                key_message = f"Upozorenje: {key_env} nije postavljen u .env!"

        save_settings(config)

        logging.info(f"[PROVIDER] Promijenjen na: {req.provider} ({title})")
        return JSONResponse({
            "status": "ok",
            "provider": req.provider,
            "title": title,
            "key_ok": key_ok,
            "message": key_message
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/options")
async def api_options():
    """Vraća trenutne opcije prevođenja iz settings.yaml."""
    try:
        from app.config_loader import load_global_config
        config = load_global_config()
        t = config.get("translation", {})
        return JSONResponse({
            "granularity": t.get("granularity", "paragraph"),
            "count": t.get("default_count", 1),
            "header": t.get("test_header", True),
            "max_chars": t.get("max_chars_per_segment", 5000),
            "profile": "sf_literature"
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


class OptionsSaveRequest(BaseModel):
    granularity: str | None = None
    count: int | None = None
    header: bool | None = None
    profile: str | None = None
    max_chars: int | None = None


@app.post("/api/options")
async def api_options_save(req: OptionsSaveRequest):
    """Sprema opcije prevođenja u settings.yaml."""
    try:
        from app.config_loader import load_global_config, save_settings
        config = load_global_config()
        t = config.setdefault("translation", {})
        if req.granularity is not None:
            t["granularity"] = req.granularity
        if req.count is not None:
            t["default_count"] = req.count
        if req.header is not None:
            t["test_header"] = req.header
        if req.max_chars is not None:
            t["max_chars_per_segment"] = req.max_chars
        save_settings(config)
        logging.info(f"[OPCIJE] Ažurirane: granularity={req.granularity}, count={req.count}, header={req.header}, max_chars={req.max_chars}")
        return JSONResponse({"status": "ok"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class TranslateRequest(BaseModel):
    rel_path: str
    mode: str = "test"  # "test" | "production"
    granularity: str = "paragraph"
    count: int = 1
    header: bool = True
    profile: str = "sf_literature"
    resume: bool = False  # True = nastavi od checkpointa
    max_chars: int = 5000


@app.post("/api/translate")
async def api_translate(req: TranslateRequest):
    """Pokreće prijevod (TEST ili produkcijski).

    Prijevod se pokreće u zasebnoj dretvi (asyncio.to_thread) kako bi
    event loop ostao slobodan — WebSocket može streamati progress linije
    u real-time dok se prijevod izvršava.
    """
    try:
        from app.config_loader import load_global_config, check_book_config
        from app.file_manager import FileManager
        from app.checkpoint import CheckpointManager
        from app.translator import Translator
        from app.metadata import copy_metadata_to_target, extract_book_metadata
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
        translator = Translator(config, cp, web_mode=True)

        file_path = OUTPUT_DIR / req.rel_path
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Datoteka ne postoji")

        book_dir = file_path.parent

        # Provjeri i kreiraj config.yaml i memorija.json ako ne postoje
        meta = extract_book_metadata(file_path, config)
        book_cfg = check_book_config(
            book_dir,
            book_title=meta.get("title", file_path.stem),
            author=meta.get("author", "Unknown"),
            original_file=file_path.name,
            year=meta.get("year", ""),
            language=meta.get("language", "hr"),
        )

        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()

        translator.postavi_knjigu(str(book_dir), book_cfg)
        logging.info(f"[PRIJEVOD] Počinje {req.mode}: {file_path.name}")

        # Pokreni prijevod u zasebnoj dretvi — event loop ostaje slobodan
        # za WebSocket streaming progress linija u real-time.
        if req.mode == "test":
            def _run_test():
                translation = translator.prevedi_test(
                    text, granularnost=req.granularity,
                    max_chars=req.max_chars,
                    kolicina=req.count, header=req.header
                )
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                name = f"{file_path.stem}_test_{timestamp}.txt"
                translated_book_dir = fm.ensure_dir(
                    fm.book_output_dir(
                        book_dir.name,
                        book_cfg.get("author", "Unknown")
                    ),
                    suffix_if_exists=False
                )
                output_path = fm.ensure_file_path(translated_book_dir / name, suffix_if_exists=True)
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(translation)
                try:
                    copy_metadata_to_target(file_path, output_path, INPUT_DIR, OUTPUT_DIR, TRANSLATED_DIR)
                except Exception as meta_err:
                    logging.warning(f"[METADATA] Greška pri kopiranju metapodataka tijekom prijevoda (test): {meta_err}")
                return {
                    "rel_path": str(output_path.relative_to(TRANSLATED_DIR)).replace("\\", "/"),
                    "output_dir": str(output_path.parent.relative_to(TRANSLATED_DIR)).replace("\\", "/"),
                    "filename": output_path.name
                }

            result = await asyncio.to_thread(_run_test)
            return JSONResponse({
                "status": "ok",
                "output": result["rel_path"],
                "output_dir": result["output_dir"],
                "filename": result["filename"],
                "mode": "test"
            })
        else:
            def _run_production():
                book_id = f"{book_dir.name}_web"
                translated_book_dir = fm.ensure_dir(
                    fm.book_output_dir(
                        book_dir.name,
                        book_cfg.get("author", "Unknown")
                    ),
                    suffix_if_exists=False
                )

                resume_from = 0
                if req.resume:
                    # Nastavi od checkpointa — koristi postojeću izlaznu datoteku
                    checkpoint = None
                    for checkpoint_data in cp.ucitaj_checkpointe():
                        if checkpoint_data.get("book_id") == book_id:
                            checkpoint = checkpoint_data
                            break
                    if checkpoint is None:
                        raise RuntimeError(
                            "Nema spremljenog checkpointa za ovu knjigu. "
                            "Pokrenite novi prijevod."
                        )
                    output_path = Path(checkpoint.get("output_path", ""))
                    if not output_path.exists():
                        raise RuntimeError(
                            f"Izlazna datoteka checkpointa ne postoji: {output_path}"
                        )
                    resume_from = checkpoint.get("current_segment", 0)
                    logging.info(
                        f"[PRIJEVOD] Nastavljam od segmenta {resume_from} "
                        f"({checkpoint.get('progress_percent', 0)}%)"
                    )
                else:
                    # Novi prijevod — kreiraj novu izlaznu datoteku i obriši stari checkpoint
                    output_path = fm.ensure_file_path(
                        translated_book_dir / f"{book_dir.name}.txt",
                        suffix_if_exists=True
                    )
                    cp.obrisi_checkpoint(book_id)

                translation, is_interrupted = translator.prevedi_knjigu(
                    text, output_path=str(output_path),
                    book_id=book_id,
                    max_chars=req.max_chars,
                    granularnost=req.granularity,
                    resume_from=resume_from
                )
                try:
                    copy_metadata_to_target(file_path, output_path, INPUT_DIR, OUTPUT_DIR, TRANSLATED_DIR)
                except Exception as meta_err:
                    logging.warning(f"[METADATA] Greška pri kopiranju metapodataka tijekom prijevoda (produkcija): {meta_err}")
                status = "interrupted" if is_interrupted else "ok"
                logging.info(f"[PRIJEVOD] Završen produkcijski: {output_path.name} (status={status})")
                return {
                    "rel_path": str(output_path.relative_to(TRANSLATED_DIR)).replace("\\", "/"),
                    "output_dir": str(output_path.parent.relative_to(TRANSLATED_DIR)).replace("\\", "/"),
                    "filename": output_path.name,
                    "status": status
                }

            result = await asyncio.to_thread(_run_production)
            return JSONResponse({
                "status": result["status"],
                "output": result["rel_path"],
                "output_dir": result["output_dir"],
                "filename": result["filename"],
                "mode": "production"
            })

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"[PRIJEVOD] Greška: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class TranslatedContentRequest(BaseModel):
    rel_path: str


@app.post("/api/translated-content")
async def api_translated_content(req: TranslatedContentRequest):
    """Vraća sadržaj prevedene datoteke za prikaz u modalu."""
    try:
        file_path = TRANSLATED_DIR / req.rel_path
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Datoteka ne postoji")
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return JSONResponse({"content": content, "name": file_path.name})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/translated-files")
async def api_translated_files():
    """Lista prevedenih .txt datoteka iz work/translated/."""
    if not TRANSLATED_DIR.exists():
        return JSONResponse({"files": []})

    files = []
    for p in TRANSLATED_DIR.rglob("*.txt"):
        if p.is_file():
            try:
                st = p.stat()
                files.append({
                    "name": p.name,
                    "rel_path": str(p.relative_to(TRANSLATED_DIR)).replace("\\", "/"),
                    "book": p.parent.name,
                    "is_test": "_test_" in p.name,
                    "size": _format_size(st.st_size),
                    "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "mtime": st.st_mtime
                })
            except OSError:
                pass

    files.sort(key=lambda x: x["mtime"], reverse=True)
    return JSONResponse({"files": files})


class TTSRequest(BaseModel):
    rel_path: str
    mode: str = "separate"  # "separate" | "single"
    resume: bool = False  # True = resume u postojećoj mapi


@app.post("/api/generate-mp3")
async def api_generate_mp3(req: TTSRequest):
    """Pokreće TTS sintezu s real-time progressom i resume podrškom.

    Ako je req.resume=True, traži postojeću audiobook mapu i nastavlja
    generiranje od mjesta gdje je stalo (preskače već generirane MP3).
    Inače, automatski duplicira audiobook mapu ako već postoji (_001, _002...).

    TTS se izvršava u zasebnoj dretvi (asyncio.to_thread) kako bi event loop
    ostao slobodan za WebSocket streaming progress linija u real-time.
    """
    try:
        from app.config_loader import load_global_config, check_book_config
        from app.file_manager import FileManager
        from app.tts_engine import TTSEngine
        from app.metadata import extract_book_metadata
        import yaml

        config = load_global_config()
        fm = FileManager(config)
        tts = TTSEngine(config, fm)

        file_path = TRANSLATED_DIR / req.rel_path
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Datoteka ne postoji")

        book_dir = file_path.parent

        # Provjeri i kreiraj config.yaml i memorija.json ako ne postoje
        meta = extract_book_metadata(file_path, config)
        book_cfg = check_book_config(
            book_dir,
            book_title=meta.get("title", file_path.stem),
            author=meta.get("author", "Unknown"),
            original_file=file_path.name,
            year=meta.get("year", ""),
            language=meta.get("language", "hr"),
        )

        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()

        author = book_cfg.get("author", "Unknown")
        base_audiobook_dir = fm.audiobook_dir(book_dir.name, author)

        # Resume: koristi postojeću mapu bez sufiksiranja
        if req.resume:
            if not base_audiobook_dir.exists():
                raise HTTPException(
                    status_code=404,
                    detail="Ne postoji audiobook mapa za nastavak. Pokrenite novu sintezu."
                )
            audiobook_dir = base_audiobook_dir
            audiobook_dir.mkdir(parents=True, exist_ok=True)
            logging.info(f"[TTS] Nastavak u postojećoj mapi: {audiobook_dir.name}")
        else:
            # Autodupliciranje: ako mapa postoji, kreira _001, _002 itd.
            audiobook_dir = fm.ensure_dir(
                base_audiobook_dir,
                suffix_if_exists=True,
            )

        logging.info(f"[TTS] Počinje: {file_path.name} → {audiobook_dir.name}")

        # Pokreni TTS u zasebnoj dretvi — event loop ostaje slobodan
        # za WebSocket streaming progress linija u real-time.
        # edge-tts je async, ali ga pokrećemo u zasebnom event loopu
        # unutar dretve kako ne bi blokirao glavni event loop.
        def _run_tts():
            # Kreiraj novi event loop za ovu dretvu
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    tts.generiraj_audiobook(
                        tekst=text,
                        book_title=book_dir.name,
                        book_config=book_cfg or {},
                        output_dir=audiobook_dir,
                        merge_single=(req.mode == "single"),
                        resume_from=0,  # automatska detekcija iz postojećih MP3
                    )
                )
            finally:
                loop.close()

        await asyncio.to_thread(_run_tts)

        # Broj generiranih MP3 datoteka
        mp3_count = len(list(audiobook_dir.glob("*.mp3")))
        logging.info(f"[TTS] Završeno: {audiobook_dir} ({mp3_count} MP3)")
        return JSONResponse({
            "status": "ok",
            "output": str(audiobook_dir.name),
            "output_dir": str(audiobook_dir),
            "mp3_count": mp3_count
        })

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"[TTS] Greška: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Pomoćne funkcije
# ---------------------------------------------------------------------------
def _load_checkpoints() -> list[dict[str, Any]]:
    cp_file = STATE_DIR / "translation_checkpoints.json"
    if not cp_file.exists():
        return []
    try:
        with open(cp_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        checkpoints = list(data.values()) if isinstance(data, dict) else data
        for cp in checkpoints:
            total = cp.get("total_segments", 1) or 1
            current = cp.get("current_segment", 0)
            cp["progress_percent"] = round((current / total) * 100, 1)
        return checkpoints
    except Exception:
        return []


async def _check_lm_studio() -> bool:
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


def _get_system_info() -> dict[str, Any]:
    try:
        import psutil  # type: ignore
        return {
            "cpu": psutil.cpu_percent(interval=0.1),
            "ram_percent": psutil.virtual_memory().percent,
            "ram_gb": round(psutil.virtual_memory().used / 1e9, 1)
        }
    except ImportError:
        return {"cpu": None, "ram_percent": None, "ram_gb": None}


def _format_size(bytes_: int) -> str:
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

    # access_log=False isključuje per-request logove (GET /api/status itd.)
    # koji spamuju terminal. Startup/shutdown poruke ostaju vidljive.
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=False)


if __name__ == "__main__":
    pokreni_server()
