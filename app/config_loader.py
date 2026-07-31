"""
app/config_loader.py — Učitavanje i spajanje YAML konfiguracije
Ref: doc/README_TechDoc.md §5
"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Any

import yaml

try:
    from dotenv import load_dotenv
    _DOTENV_AVAILABLE = True
except ImportError:
    _DOTENV_AVAILABLE = False

# ---------------------------------------------------------------------------
# Konstante
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _ROOT / "config"
_SETTINGS_FILE = _CONFIG_DIR / "settings.yaml"
_CHAR_MAP = str.maketrans("čćšđžŽŠĐČĆ", "ccsdzZSDCC")


# ---------------------------------------------------------------------------
# Javne funkcije
# ---------------------------------------------------------------------------

def load_global_config() -> dict[str, Any]:
    """Učitava config/settings.yaml i puni API ključeve iz .env.

    Returns:
        Rječnik s globalnom konfiguracijom.

    Raises:
        FileNotFoundError: ako settings.yaml ne postoji.
        yaml.YAMLError: ako je YAML neispravan.
    """
    _load_dotenv()

    with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
        cfg: dict[str, Any] = yaml.safe_load(f)

    # Ubaci CHAR_MAP koji se ne može pohraniti u YAML
    cfg.setdefault("_internal", {})["char_map"] = _CHAR_MAP

    # Popuni api_key za aktivni provider iz .env
    cfg = _inject_api_keys(cfg)

    # Normaliziraj direktorije na apsolutne putanje
    cfg = _resolve_directories(cfg)

    logging.debug("config/settings.yaml učitan.")
    return cfg


def load_book_config(book_dir: Path | str) -> dict[str, Any]:
    """Učitava work/output/<Knjiga>/config.yaml.

    Args:
        book_dir: Putanja do direktorija knjige.

    Returns:
        Rječnik s per-book konfiguracijom.
    """
    config_path = Path(book_dir) / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_profile(profile_name: str) -> dict[str, Any]:
    """Učitava config/profile_<name>.yaml predložak.

    Args:
        profile_name: 'sf_literature' | 'it_technical' | 'general'

    Returns:
        Rječnik s profilom.
    """
    profile_path = _CONFIG_DIR / f"profile_{profile_name}.yaml"
    if not profile_path.exists():
        raise FileNotFoundError(f"Profil nije pronađen: {profile_path}")
    with open(profile_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def merge_config(global_cfg: dict[str, Any],
                 book_cfg: dict[str, Any]) -> dict[str, Any]:
    """Spaja globalnu i per-book konfiguraciju. Book config ima prioritet.

    Args:
        global_cfg: Globalna konfiguracija iz settings.yaml.
        book_cfg:   Per-book konfiguracija iz work/output/<K>/config.yaml.

    Returns:
        Spojena konfiguracija.
    """
    return _deep_merge(global_cfg, book_cfg)


def save_settings(cfg: dict[str, Any]) -> None:
    """Atomski zapis promijenjenih OPCIJA natrag u settings.yaml.

    Koristi se za persistenciju OPCIJA (granularnost, test_header, default_count).
    API ključevi se NE zapisuju — ostaju u .env.

    Args:
        cfg: Ažurirana konfiguracija.
    """
    # Ukloni interno stanje prije zapisa
    clean = {k: v for k, v in cfg.items() if not k.startswith("_")}

    tmp = str(_SETTINGS_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.dump(clean, f, allow_unicode=True, default_flow_style=False,
                  sort_keys=False)
    os.replace(tmp, _SETTINGS_FILE)
    logging.debug("config/settings.yaml ažuriran.")


def create_book_config(book_dir: Path | str,
                       book_title: str,
                       author: str,
                       original_file: str,
                       profile_name: str = "sf_literature",
                       api_provider: str | None = None) -> dict[str, Any]:
    """Generira i sprema work/output/<Knjiga>/config.yaml iz profil predloška.

    Poziva se pri prvoj obradi knjige ako config.yaml ne postoji.

    Args:
        book_dir:      Putanja do direktorija knjige (work/output/<K>/).
        book_title:    Naslov knjige.
        author:        Autor knjige.
        original_file: Naziv izvorne datoteke.
        profile_name:  Profil predložak koji se koristi.
        api_provider:  Override API providera (None = koristi globalni).

    Returns:
        Generirani book config rječnik.
    """
    from datetime import datetime

    profile = load_profile(profile_name)
    now = datetime.now().isoformat(timespec="seconds")

    book_cfg: dict[str, Any] = {
        "book_title":    book_title,
        "author":        author,
        "original_file": original_file,
        "api_provider":  api_provider or "",
        "model":         "",
        "api_key_override": "",
        "system_prompt": profile.get("system_prompt", ""),
        "parameters":    profile.get("parameters", {}),
        "chunking":      profile.get("chunking", {}),
        "memorija_file": f"{_sanitize_filename(book_title)}_memorija.json",
        "enable_reasoning": profile.get("enable_reasoning", False),
        "created_at":    now,
        "updated_at":    now,
    }

    book_dir = Path(book_dir)
    book_dir.mkdir(parents=True, exist_ok=True)
    config_path = book_dir / "config.yaml"

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(book_cfg, f, allow_unicode=True, default_flow_style=False,
                  sort_keys=False)

    logging.info(f"Kreiran book config: {config_path}")
    return book_cfg


# ---------------------------------------------------------------------------
# Interne pomoćne funkcije
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    """Učitava .env iz root direktorija ako python-dotenv postoji."""
    if not _DOTENV_AVAILABLE:
        logging.debug("python-dotenv nije instaliran — .env se ne učitava.")
        return
    env_path = _ROOT / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
        logging.debug(".env učitan (s override=True).")


def _inject_api_keys(cfg: dict[str, Any]) -> dict[str, Any]:
    """Za svaki provider koji ima key_env, popuni api_key iz environment varijable."""
    providers = cfg.get("api", {}).get("providers", {})
    for provider_name, provider_cfg in providers.items():
        key_env = provider_cfg.get("key_env")
        if key_env:
            value = os.getenv(key_env, "")
            provider_cfg["api_key"] = value
    return cfg


def _resolve_directories(cfg: dict[str, Any]) -> dict[str, Any]:
    """Pretvara relativne putanje direktorija u apsolutne."""
    dirs = cfg.get("directories", {})
    for key, rel_path in dirs.items():
        abs_path = str((_ROOT / rel_path).resolve())
        dirs[key] = abs_path
    return cfg


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Rekurzivno spaja override u base. Override vrijednosti imaju prioritet."""
    result = base.copy()
    for key, value in override.items():
        if (key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _sanitize_filename(name: str) -> str:
    """Minimalna sanitizacija za ime datoteke (bez dijakritika, razmaci → crtice)."""
    import re
    name = name.translate(_CHAR_MAP)
    name = re.sub(r'[^\w\s-]', '', name).strip().lower()
    name = re.sub(r'\s+', '-', name)
    return name
