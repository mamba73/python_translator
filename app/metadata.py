"""
app/metadata.py — Automatska ekstrakcija i generiranje metapodataka

Omogućuje:
  1. Automatsko čitanje naslova i autora iz ulaznih datoteka
     (TXT, PDF, EPUB, DOCX, MOBI) — iz strukture dokumenta ili naziva datoteke.
  2. Generiranje metadata.yaml datoteke u audiobook direktoriju s
     popisom poglavlja/segmenata, nazivima datoteka, rednim brojevima i trajanjem.
  3. Generiranje .lrc datoteka za sinkronizirani prikaz teksta u playerima.

Ref: doc/README_TechDoc.md §7 (prošireno)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

# Pokušaj uvoza za EPUB / PDF / DOCX — neobavezni paketi
try:
    from pypdf import PdfReader
    _PDF_AVAILABLE = True
except ImportError:
    _PDF_AVAILABLE = False

try:
    from docx import Document
    _DOCX_AVAILABLE = True
except ImportError:
    _DOCX_AVAILABLE = False

try:
    import ebooklib
    from ebooklib import epub
    _EPUB_AVAILABLE = True
except ImportError:
    _EPUB_AVAILABLE = False


# ================================================================================
# 1. AUTOMATSKA EKSTRAKCIJA NASLOVA I AUTORA
# ================================================================================

_FILENAME_TITLE_AUTHOR_PATTERNS = [
    re.compile(
        r'^(?:\d+\s*[\.\-_]\s*)?(?P<title>.+?)\s*[-–—]\s*'
        r'(?P<author>[A-Z][A-Za-z0-9\s\.\'\-\u010d\u0107\u0161\u0111\u017e\u017d\u0160\u0110\u010c\u0106]+)$'
    ),
    re.compile(
        r'^(?P<title>.+?)\s+by\s+'
        r'(?P<author>[A-Z][A-Za-z0-9\s\.\'\-\u010d\u0107\u0161\u0111\u017e\u017d\u0160\u0110\u010c\u0106]+)$',
        re.IGNORECASE
    ),
    re.compile(
        r'^(?P<title>.+?)[_](?P<author>[A-Z][A-Za-z0-9\s\.\'\-\u010d\u0107\u0161\u0111\u017e\u017d\u0160\u0110\u010c\u0106]+)$'
    ),
]

_TXT_TITLE_PATTERNS = [
    re.compile(r'^(?:Title|Naslov|Knjiga)\s*[:\-]\s*(?P<title>.+)$', re.IGNORECASE),
    re.compile(r'^(?:Author|Autor|Pisac)\s*[:\-]\s*(?P<author>.+)$', re.IGNORECASE),
    re.compile(
        r'^(?:by|od)\s+(?P<author>[A-Z][A-Za-z0-9\s\.\'\-\u010d\u0107\u0161\u0111\u017e\u017d\u0160\u0110\u010c\u0106]+)$',
        re.IGNORECASE
    ),
]

_BY_AUTHOR_PATTERN = re.compile(
    r'^\s*(?:by|od)\s+(?P<author>[A-Z][A-Za-z0-9\s\.\'\-\u010d\u0107\u0161\u0111\u017e\u017d\u0160\u0110\u010c\u0106]+)\s*$',
    re.IGNORECASE
)


def extract_book_metadata(file_path: str | Path,
                          config: dict[str, Any] | None = None) -> dict[str, str]:
    """Automatski izvlači naslov i autora iz ulazne datoteke.

    Redoslijed pokušaja:
      1. Struktura dokumenta (EPUB metadata, PDF metadata, DOCX core properties).
      2. Prvi redovi teksta (TXT — Title:/Author: linije ili "by Author").
      3. Naziv datoteke (regex parsiranje).

    Args:
        file_path: Putanja do ulazne datoteke (TXT, PDF, EPUB, DOCX, MOBI).
        config: Globalna konfiguracija (opcionalno, za fallback jezik).

    Returns:
        Rječnik s ključevima: title, author, year, language, source.
    """
    path = Path(file_path)
    if not path.exists():
        logging.warning(f"[METADATA] Datoteka ne postoji: {path}")
        return _fallback_from_filename(path)

    ekstenzija = path.suffix.lower()
    metadata: dict[str, str] = {
        "title": "",
        "author": "",
        "year": "",
        "language": "",
        "source": "unknown",
    }

    # 1. Pokušaj iz strukture dokumenta
    try:
        if ekstenzija == '.epub' and _EPUB_AVAILABLE:
            metadata = _extract_epub_metadata(path)
        elif ekstenzija == '.pdf' and _PDF_AVAILABLE:
            metadata = _extract_pdf_metadata(path)
        elif ekstenzija == '.docx' and _DOCX_AVAILABLE:
            metadata = _extract_docx_metadata(path)
        elif ekstenzija == '.txt':
            metadata = _extract_txt_metadata(path)
    except Exception as e:
        logging.warning(f"[METADATA] Greška pri ekstrakciji iz {ekstenzija}: {e}")

    # 2. Ako struktura nije dala naslov/autora, pokušaj iz naziva datoteke
    if not metadata.get("title") or not metadata.get("author"):
        filename_meta = _parse_filename(path)
        if not metadata.get("title"):
            metadata["title"] = filename_meta.get("title", "")
        if not metadata.get("author"):
            metadata["author"] = filename_meta.get("author", "")
        if not metadata.get("year"):
            metadata["year"] = filename_meta.get("year", "")
        if metadata.get("source") == "unknown":
            metadata["source"] = filename_meta.get("source", "filename")

    # 3. Finalni fallback — naziv datoteke bez ekstenzije
    if not metadata.get("title"):
        metadata["title"] = path.stem
        metadata["source"] = "filename_stem"

    if not metadata.get("author"):
        metadata["author"] = "Unknown"

    # 4. Default jezik iz konfiguracije ako nije pronađen
    if not metadata.get("language") and config:
        metadata["language"] = config.get("translation", {}).get("target_language", "hr")

    logging.info(
        f"[METADATA] Ekstrahirano: title='{metadata['title']}', "
        f"author='{metadata['author']}', year='{metadata.get('year', '')}', "
        f"source='{metadata.get('source', '')}'"
    )
    return metadata


def _metadata_file_for_path(file_path: str | Path,
                            input_dir: Path,
                            output_dir: Path,
                            translated_dir: Path) -> Path:
    """Odredi per-book metadata datoteku za zadanu datoteku."""
    path = Path(file_path)

    if path.parent == input_dir:
        return path.with_suffix(path.suffix + ".metadata.yaml")

    if path.parent == output_dir or path.parent == translated_dir:
        return path.with_suffix(path.suffix + ".metadata.yaml")

    # Ako je datoteka unutar book direktorija, spremi u metadata.yaml u tom direktoriju
    if input_dir in path.parents or output_dir in path.parents or translated_dir in path.parents:
        return path.parent / "metadata.yaml"

    return path.parent / "metadata.yaml"


def load_book_metadata(file_path: str | Path,
                       input_dir: Path,
                       output_dir: Path,
                       translated_dir: Path) -> dict[str, str]:
    """Učitaj metapodatke koristeći per-book config.yaml (primary source)."""
    path = Path(file_path)

    # 1. Prioritet: config.yaml unutar book direktorija
    book_dir = path.parent if path.parent not in (input_dir, output_dir, translated_dir) else None
    
    # Ako je datoteka u rrootu outputa ili translateda, možda je u poddirektoriju
    if not book_dir and (output_dir in path.parents or translated_dir in path.parents):
         book_dir = path.parent

    if book_dir:
        config_file = book_dir / "config.yaml"
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    book_cfg = yaml.safe_load(f) or {}
                return {
                    "title": str(book_cfg.get("book_title", "")),
                    "author": str(book_cfg.get("author", "")),
                    "year": str(book_cfg.get("year", "")),
                    "language": str(book_cfg.get("language", "hr")) if book_cfg.get("language") is not None else "hr",
                    "source": "config.yaml"
                }
            except Exception:
                pass

    # 2. Fallback: .metadata.yaml datoteka (ako još postoji)
    metadata_file = _metadata_file_for_path(path, input_dir, output_dir, translated_dir)
    if metadata_file.exists():
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            return {
                "title": str(data.get("title", "")),
                "author": str(data.get("author", "")),
                "year": str(data.get("year", "")),
                "language": str(data.get("language", "hr")) if data.get("language") is not None else "hr",
                "source": str(data.get("source", "metadata.yaml"))
            }
        except Exception:
            pass

    return extract_book_metadata(path)


def save_book_metadata(file_path: str | Path,
                       title: str,
                       author: str,
                       year: str,
                       language: str,
                       source: str,
                       input_dir: Path,
                       output_dir: Path,
                       translated_dir: Path) -> Path:
    """Spremi per-book metapodatke primarno u config.yaml."""
    path = Path(file_path)
    
    # 1. Pokušaj spremiti u config.yaml ako book direktorij postoji
    book_dir = path.parent if path.parent not in (input_dir, output_dir, translated_dir) else None
    if not book_dir and (output_dir in path.parents or translated_dir in path.parents):
         book_dir = path.parent

    if book_dir and book_dir.exists():
        config_file = book_dir / "config.yaml"
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    book_cfg = yaml.safe_load(f) or {}
                
                book_cfg["book_title"] = title
                book_cfg["author"] = author
                book_cfg["year"] = year
                book_cfg["language"] = language
                book_cfg["updated_at"] = _now_iso()

                with open(config_file, 'w', encoding='utf-8') as f:
                    yaml.dump(book_cfg, f, Dumper=yaml.SafeDumper, allow_unicode=True, default_flow_style=False, sort_keys=False)
                
                logging.info(f"[METADATA] Ažuriran config.yaml: {config_file}")
                # Vraćamo config_file kao referencu gdje je spremljeno
                return config_file
            except Exception as e:
                logging.warning(f"[METADATA] Greška pri spremanju u config.yaml: {e}")

    # 2. Fallback na staru .metadata.yaml lokaciju (npr. za datoteke u work/input/)
    metadata_file = _metadata_file_for_path(path, input_dir, output_dir, translated_dir)
    metadata_file.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, Any] = {}
    if metadata_file.exists():
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                existing = yaml.safe_load(f) or {}
        except Exception:
            existing = {}

    payload = {
        "title": title,
        "author": author,
        "year": year,
        "language": language,
        "source": source,
        "updated_at": _now_iso(),
    }
    payload.update({k: v for k, v in existing.items() if k not in payload})

    with open(metadata_file, 'w', encoding='utf-8') as f:
        yaml.dump(payload, f, Dumper=yaml.SafeDumper, allow_unicode=True, default_flow_style=False, sort_keys=False)
    
    return metadata_file


def copy_metadata_to_target(src_file: str | Path,
                            target_file: str | Path,
                            input_dir: Path,
                            output_dir: Path,
                            translated_dir: Path) -> Path:
    """Kopiraj postojeće metapodatke na novu per-book lokaciju."""
    meta = load_book_metadata(src_file, input_dir, output_dir, translated_dir)
    return save_book_metadata(
        target_file,
        title=meta.get("title", ""),
        author=meta.get("author", ""),
        year=meta.get("year", ""),
        language=meta.get("language", "hr"),
        source=meta.get("source", "copied"),
        input_dir=input_dir,
        output_dir=output_dir,
        translated_dir=translated_dir,
    )


def _extract_epub_metadata(path: Path) -> dict[str, str]:
    """Izvlači naslov i autora iz EPUB metadata."""
    if not _EPUB_AVAILABLE:
        return {"title": "", "author": "", "year": "", "language": "", "source": "unknown"}

    knjiga = epub.read_epub(str(path))
    meta = knjiga.get_metadata('DC', 'title')
    title = meta[0][0] if meta else ""

    meta_author = knjiga.get_metadata('DC', 'creator')
    author = meta_author[0][0] if meta_author else ""

    meta_year = knjiga.get_metadata('DC', 'date')
    year = ""
    if meta_year:
        year_raw = meta_year[0][0]
        year_match = re.search(r'\b(19|20)\d{2}\b', year_raw)
        if year_match:
            year = year_match.group(0)

    meta_lang = knjiga.get_metadata('DC', 'language')
    language = meta_lang[0][0] if meta_lang else ""

    return {
        "title": title.strip(),
        "author": author.strip(),
        "year": year,
        "language": language,
        "source": "epub_metadata",
    }


def _extract_pdf_metadata(path: Path) -> dict[str, str]:
    """Izvlači naslov i autora iz PDF metadata."""
    if not _PDF_AVAILABLE:
        return {"title": "", "author": "", "year": "", "language": "", "source": "unknown"}

    reader = PdfReader(str(path))
    info = reader.metadata
    if not info:
        return {"title": "", "author": "", "year": "", "language": "", "source": "unknown"}

    title = str(info.get('/Title', '') or '').strip()
    author = str(info.get('/Author', '') or '').strip()
    year = ""
    creation_date = str(info.get('/CreationDate', '') or '')
    year_match = re.search(r'\b(19|20)\d{2}\b', creation_date)
    if year_match:
        year = year_match.group(0)

    return {
        "title": title,
        "author": author,
        "year": year,
        "language": "",
        "source": "pdf_metadata",
    }


def _extract_docx_metadata(path: Path) -> dict[str, str]:
    """Izvlači naslov i autora iz DOCX core properties."""
    if not _DOCX_AVAILABLE:
        return {"title": "", "author": "", "year": "", "language": "", "source": "unknown"}

    doc = Document(str(path))
    props = doc.core_properties
    title = str(props.title or '').strip()
    author = str(props.author or '').strip()
    year = ""
    if props.created:
        year = str(props.created.year)

    return {
        "title": title,
        "author": author,
        "year": year,
        "language": "",
        "source": "docx_metadata",
    }


def _extract_txt_metadata(path: Path) -> dict[str, str]:
    """Izvlači naslov i autora iz prvih redaka TXT datoteke."""
    title = ""
    author = ""
    year = ""

    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            linije = [f.readline() for _ in range(30)]
    except Exception as e:
        logging.warning(f"[METADATA] Greška pri čitanju TXT: {e}")
        return {"title": "", "author": "", "year": "", "language": "", "source": "unknown"}

    for linija in linije:
        linija_clean = linija.strip()
        if not linija_clean:
            continue

        for pattern in _TXT_TITLE_PATTERNS:
            match = pattern.match(linija_clean)
            if match:
                if 'title' in match.groupdict() and match.group('title') and not title:
                    title = match.group('title').strip()
                if 'author' in match.groupdict() and match.group('author') and not author:
                    author = match.group('author').strip()
                break

        by_match = _BY_AUTHOR_PATTERN.match(linija_clean)
        if by_match and not author:
            author = by_match.group('author').strip()

        year_match = re.search(r'\((\d{4})\)', linija_clean)
        if year_match and not year:
            year = year_match.group(1)

        if title and author:
            break

    return {
        "title": title,
        "author": author,
        "year": year,
        "language": "",
        "source": "txt_content",
    }


def _parse_filename(path: Path) -> dict[str, str]:
    """Parsira naslov i autora iz naziva datoteke."""
    stem = path.stem

    # Ukloni uobičajene sufikse prije parsiranja: [fixed], _001, (1), itd.
    stem = re.sub(r'\s*\[fixed\]\s*', ' ', stem, flags=re.IGNORECASE)
    stem = re.sub(r'_\d{3}$', '', stem)
    stem = re.sub(r'\s*\(\d+\)$', '', stem)
    stem = stem.strip()

    title = ""
    author = ""
    year = ""

    year_match = re.search(r'\((\d{4})\)', stem)
    if year_match:
        year = year_match.group(1)
        stem = stem.replace(f"({year})", "").strip()

    for pattern in _FILENAME_TITLE_AUTHOR_PATTERNS:
        match = pattern.match(stem)
        if match:
            title = match.group('title').strip()
            author = match.group('author').strip()
            break

    if not title or not author:
        by_match = re.search(
            r'^(?P<title>.+?)\s+by\s+'
            r'(?P<author>[A-Z][A-Za-z0-9\s\.\'\-\u010d\u0107\u0161\u0111\u017e\u017d\u0160\u0110\u010c\u0106]+)$',
            stem, re.IGNORECASE
        )
        if by_match:
            title = by_match.group('title').strip()
            author = by_match.group('author').strip()

    return {
        "title": title,
        "author": author,
        "year": year,
        "source": "filename",
    }


def _fallback_from_filename(path: Path) -> dict[str, str]:
    """Fallback kada datoteka ne postoji — parsira iz naziva."""
    meta = _parse_filename(path)
    if not meta.get("title"):
        meta["title"] = path.stem
    if not meta.get("author"):
        meta["author"] = "Unknown"
    return meta


# ================================================================================
# 2. GENERIRANJE METADATA.YAML
# ================================================================================

def generate_metadata_file(audiobook_dir: str | Path,
                           book_title: str,
                           author: str,
                           segments: list[dict[str, Any]],
                           year: str = "",
                           language: str = "hr",
                           source_file: str = "") -> Path:
    """Generira metadata.yaml u audiobook direktoriju.

    Args:
        audiobook_dir: Direktorij audiobooka (work/audiobooks/<Knjiga>---<Autor>/).
        book_title: Naslov knjige.
        author: Autor knjige.
        segments: Lista rječnika s podacima o segmentima:
            [{"file": "001_Ch01_part001.mp3", "chapter": 1, "part": 1,
              "track": 1, "duration": 12.5, "text": "..."}]
        year: Godina izdanja (opcionalno).
        language: Jezik (default: "hr").
        source_file: Naziv izvorne datoteke (opcionalno).

    Returns:
        Putanja do generirane metadata.yaml datoteke.
    """
    dir_path = Path(audiobook_dir)
    dir_path.mkdir(parents=True, exist_ok=True)

    # Grupiraj segmente po poglavljima
    poglavlja: dict[int, list[dict[str, Any]]] = {}
    for seg in segments:
        ch = seg.get("chapter", 1)
        poglavlja.setdefault(ch, []).append(seg)

    poglavlja_lista = []
    for ch_num in sorted(poglavlja.keys()):
        ch_segments = poglavlja[ch_num]
        poglavlja_lista.append({
            "broj": ch_num,
            "naziv": f"Chapter {ch_num}",
            "segmenata": len(ch_segments),
            "trajanje": round(sum(s.get("duration", 0) for s in ch_segments), 2),
            "segmenti": [
                {
                    "file": s.get("file", ""),
                    "track": s.get("track", 0),
                    "part": s.get("part", 0),
                    "duration": round(s.get("duration", 0), 2),
                    "lrc": s.get("lrc", ""),
                }
                for s in ch_segments
            ]
        })

    metadata: dict[str, Any] = {
        "book": {
            "title": book_title,
            "author": author,
            "year": year,
            "language": language,
            "source_file": source_file,
        },
        "generated_at": _now_iso(),
        "total_segments": len(segments),
        "total_duration": round(sum(s.get("duration", 0) for s in segments), 2),
        "chapters": poglavlja_lista,
    }

    metadata_path = dir_path / "metadata.yaml"
    try:
        with open(metadata_path, "w", encoding="utf-8") as f:
            yaml.dump(
                metadata,
                f,
                Dumper=yaml.SafeDumper,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False
            )
        logging.info(f"[METADATA] Generirana metadata.yaml: {metadata_path}")
    except Exception as e:
        logging.error(f"[METADATA] Greška pri generiranju metadata.yaml: {e}")

    return metadata_path


def _now_iso() -> str:
    """Vraća trenutni timestamp u ISO formatu."""
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


# ================================================================================
# 3. GENERIRANJE LRC DATOTEKA
# ================================================================================

# Prosječna brzina govora u riječima po minuti (za procjenu trajanja)
_WORDS_PER_MINUTE = 150
# Prosječno trajanje po znaku u sekundama (fallback)
_SECONDS_PER_CHAR = 0.08


def estimate_duration(text: str) -> float:
    """Procjenjuje trajanje izgovora teksta u sekundama.

    Koristi prosječnu brzinu govora (riječi po minuti) i duljinu teksta.
    Ako tekst ima malo riječi, koristi fallback po znaku.

    Args:
        text: Tekst za procjenu.

    Returns:
        Procijenjeno trajanje u sekundama.
    """
    if not text or not text.strip():
        return 0.0

    rijeci = len(text.split())
    if rijeci > 0:
        duration = (rijeci / _WORDS_PER_MINUTE) * 60.0
    else:
        duration = len(text) * _SECONDS_PER_CHAR

    # Minimalno trajanje: 1 sekunda
    return max(duration, 1.0)


def generate_lrc_file(mp3_path: str | Path,
                      sentences: list[str],
                      total_duration: float | None = None) -> Path:
    """Generira .lrc datoteku uz MP3 segment.

    LRC format: [mm:ss.xx] tekst
    Vremenski žigovi se procjenjuju proporcionalno duljini rečenica
    unutar ukupnog trajanja segmenta.

    Args:
        mp3_path: Putanja do MP3 datoteke.
        sentences: Lista rečenica u segmentu.
        total_duration: Ukupno trajanje segmenta u sekundama.
            Ako je None, procjenjuje se iz teksta.

    Returns:
        Putanja do generirane .lrc datoteke.
    """
    mp3 = Path(mp3_path)
    lrc_path = mp3.with_suffix(".lrc")

    if not sentences:
        lrc_path.write_text("", encoding="utf-8")
        return lrc_path

    # Ukupno trajanje — procjena ili zadano
    if total_duration is None or total_duration <= 0:
        total_duration = estimate_duration(" ".join(sentences))

    # Izračunaj proporcionalna trajanja po rečenici
    duljine = [max(len(s), 1) for s in sentences]
    ukupna_duljina = sum(duljine)

    linije: list[str] = []
    trenutno_vrijeme = 0.0

    for recenica in sentences:
        # Proporcionalno trajanje ove rečenice
        recenica_duration = (max(len(recenica), 1) / ukupna_duljina) * total_duration

        # Formatiraj timestamp: [mm:ss.xx]
        minute = int(trenutno_vrijeme // 60)
        sekunde = int(trenutno_vrijeme % 60)
        stotinke = int((trenutno_vrijeme - int(trenutno_vrijeme)) * 100)
        timestamp = f"[{minute:02d}:{sekunde:02d}.{stotinke:02d}]"

        linije.append(f"{timestamp} {recenica.strip()}")

        trenutno_vrijeme += recenica_duration

    try:
        lrc_path.write_text("\n".join(linije), encoding="utf-8")
        logging.debug(f"[LRC] Generirana LRC datoteka: {lrc_path.name} "
                      f"({len(linije)} linija, {total_duration:.1f}s)")
    except Exception as e:
        logging.error(f"[LRC] Greška pri generiranju LRC: {e}")

    return lrc_path


def split_sentences(text: str) -> list[str]:
    """Dijeli tekst na rečenice čuvajući graničnike.

    Args:
        text: Tekst za podjelu.

    Returns:
        Lista rečenica.
    """
    if not text or not text.strip():
        return []

    # Podijeli na rečenice na granicama . ! ? " ' ) ] itd.
    recenice = re.split(r'(?<=[.!?])\s+', text)
    recenice = [r.strip() for r in recenice if r.strip()]

    # Ako nema graničnika, podijeli na zareze ili na dijelove
    if len(recenice) <= 1 and len(text) > 200:
        recenice = re.split(r'(?<=[,;:])\s+', text)
        recenice = [r.strip() for r in recenice if r.strip()]

    return recenice
