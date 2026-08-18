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

def test_local_provider_payload_compatibility():
    cfg = {
        "api": {
            "provider": "unsloth",
            "model": "local",
            "providers": [
                {"provider": "unsloth", "model": "local", "apiBase": "http://127.0.0.1:8888/v1"},
                {"provider": "lmstudio", "model": "local", "apiBase": "http://127.0.0.1:1234/v1"},
            ],
        },
        "translation": {
            "temperature": 0.25,
            "max_tokens": 1024,
            "top_p": 0.8,
            "top_k": 15,
            "min_p": 0.05,
            "repeat_penalty": 1.2,
            "disable_reasoning": True,
            "api_parameters": [
                "temperature",
                "max_tokens",
                "top_p",
                "min_p",
                "top_k",
                "repeat_penalty",
                "thinking_config",
            ],
            "thinking_config": {"include_thinking_config": True, "thinking_budget": 0},
        },
    }

    for provider in ("unsloth", "lmstudio"):
        cfg["api"]["provider"] = provider
        translator = Translator(cfg, None)
        payload = translator._build_payload([{"role": "user", "content": "Test"}])

        assert payload["temperature"] == 0.25
        assert payload["max_tokens"] == 1024
        assert "reasoning" not in payload
        assert "thinking" not in payload
        assert "extra_body" in payload
        assert payload["extra_body"]["top_k"] == 15
        assert payload["extra_body"]["min_p"] == 0.05
        assert payload["extra_body"]["repetition_penalty"] == 1.2

        if provider == "unsloth":
            assert payload["extra_body"]["enable_thinking"] is False


if __name__ == "__main__":
    test_local_provider_payload_compatibility()
    print("\n[OK] Local provider payload compatibility passed!")
