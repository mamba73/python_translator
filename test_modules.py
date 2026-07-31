#!/usr/bin/env python3
"""
Test script za verifikaciju modula
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

print("Testing module imports...")

try:
    from app.config_loader import load_global_config
    print("[OK] app.config_loader")
except Exception as e:
    print(f"[FAIL] app.config_loader: {e}")
    sys.exit(1)

try:
    from app.file_manager import FileManager
    print("[OK] app.file_manager")
except Exception as e:
    print(f"[FAIL] app.file_manager: {e}")
    sys.exit(1)

try:
    from app.logger import setup_logging
    print("[OK] app.logger")
except Exception as e:
    print(f"[FAIL] app.logger: {e}")
    sys.exit(1)

try:
    from app.utils import sanitiziraj_naziv
    print("[OK] app.utils")
except Exception as e:
    print(f"[FAIL] app.utils: {e}")
    sys.exit(1)

try:
    from app.document_processor import DocumentProcessor
    print("[OK] app.document_processor")
except Exception as e:
    print(f"[FAIL] app.document_processor: {e}")
    sys.exit(1)

try:
    from app.text_cleaner import TextCleaner
    print("[OK] app.text_cleaner")
except Exception as e:
    print(f"[FAIL] app.text_cleaner: {e}")
    sys.exit(1)

try:
    from app.translator import Translator
    print("[OK] app.translator")
except Exception as e:
    print(f"[FAIL] app.translator: {e}")
    sys.exit(1)

try:
    from app.checkpoint import CheckpointManager
    print("[OK] app.checkpoint")
except Exception as e:
    print(f"[FAIL] app.checkpoint: {e}")
    sys.exit(1)

try:
    from app.tts_engine import TTSEngine
    print("[OK] app.tts_engine")
except Exception as e:
    print(f"[FAIL] app.tts_engine: {e}")
    sys.exit(1)

try:
    from app.menu import Menu
    print("[OK] app.menu")
except Exception as e:
    print(f"[FAIL] app.menu: {e}")
    sys.exit(1)

print("\nAll modules imported successfully!")

# Test config loading
try:
    config = load_global_config()
    print(f"\n[OK] Config loaded: {config.get('project', {}).get('name')} v{config.get('project', {}).get('version')}")
except Exception as e:
    print(f"\n[FAIL] Config loading failed: {e}")
    sys.exit(1)

print("\n[OK] All tests passed!")
