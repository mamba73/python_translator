"""
app/translator.py — Unificirani prevoditelj s više providera
Ref: doc/README_TechDoc.md §9
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
import urllib.error
from typing import Any, Optional
from datetime import datetime

from app.utils import unificiraj_navodnike, ocisti_leaked_prijevod, detektiraj_x_tipku
from app.checkpoint import CheckpointManager


class Translator:
    """Unificirani prevoditelj s podrškom za više API providera."""

    def __init__(self, config: dict[str, Any], checkpoint_manager: CheckpointManager) -> None:
        self._cfg = config
        self._cp = checkpoint_manager
        self._api_cfg = config.get("api", {})
        self._trans_cfg = config.get("translation", {})
        self._provider = self._api_cfg.get("provider", "lm_studio")
        self._timeout = self._api_cfg.get("timeout", 120)

    # -----------------------------------------------------------------------
    # Javne metode za prevođenje
    # -----------------------------------------------------------------------

    def prevedi_segment(self, tekst: str, system_prompt: str | None = None) -> str:
        """Unificirana metoda za prevođenje segmenta (odlomak/paragraf/rečenica).

        Args:
            tekst: Tekst za prevođenje.
            system_prompt: Opcionalni system prompt (ako None, koristi default).

        Returns:
            Prevedeni tekst.
        """
        if len(tekst.strip()) <= 2:
            return tekst

        if self._je_strukturni_ili_kratak(tekst):
            logging.debug(f"Preskačem LLM za kratki/strukturni segment: '{tekst[:50]}...'")
            return tekst

        if system_prompt is None:
            system_prompt = self._generiraj_default_system_prompt()

        response = self._api_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": tekst}
            ]
        )

        # Post-processing
        response = unificiraj_navodnike(response)
        response = ocisti_leaked_prijevod(response)

        return response

    def prevedi_knjigu(self, tekst: str, output_path: str, book_id: str,
                      granularnost: str = "paragraph") -> tuple[str, bool]:
        """Produkcijski prijevod cijele knjige s checkpointingom.

        Args:
            tekst: Cijeli tekst knjige.
            output_path: Putanja za spremanje prevedenog teksta.
            book_id: Jedinstveni ID knjige za checkpointing.
            granularnost: Granularnost segmentacije (paragraph/sentence).

        Returns:
            (prevedeni_tekst, je_prekinuto)
        """
        # Segmentacija
        if granularnost == "paragraph":
            segmenti = tekst.split('\n\n')
        elif granularnost == "sentence":
            segmenti = re.split(r'(?<=[.!?])\s+', tekst)
        else:
            segmenti = [tekst]  # Odlomak - cijeli tekst

        ukupno = len(segmenti)
        prevedeni = []

        for idx, segment in enumerate(segmenti):
            # Detekcija prekida
            if detektiraj_x_tipku():
                akcija = self._prikazi_prekid_meni()
                if akcija == "finish":
                    break
                elif akcija == "abort":
                    return "", True

            # Prevođenje
            try:
                prijevod = self.prevedi_segment(segment)
                prevedeni.append(prijevod)
            except Exception as e:
                logging.error(f"Greška pri prevođenju segmenta {idx + 1}/{ukupno}: {e}")
                prevedeni.append(segment)  # Fallback na original

            # Checkpoint
            self._cp.spremi_checkpoint({
                "book_id": book_id,
                "current_segment": idx + 1,
                "total_segments": ukupno,
                "output_path": output_path
            })

            # Progress
            from app.utils import prikazi_progres
            prikazi_progres(idx + 1, ukupno, f"Segment {idx + 1}/{ukupno}")

        # Spremanje
        final_tekst = '\n\n'.join(prevedeni) if granularnost == "paragraph" else ' '.join(prevedeni)
        self._cp.atomic_write(output_path, final_tekst)

        # Čišćenje checkpointa
        self._cp.obrisi_checkpoint(book_id)

        return final_tekst, False

    def prevedi_test(self, tekst: str, output_path: str, granularnost: str = "paragraph",
                     kolicina: int = 1, include_header: bool = True) -> None:
        """Testni prijevod s opcionalnim headerom.

        Args:
            tekst: Izvorni tekst.
            output_path: Putanja za spremanje testa.
            granularnost: Granularnost (paragraph/sentence).
            kolicina: Broj segmenata za prevođenje.
            include_header: Uključi header u output.
        """
        # Segmentacija
        if granularnost == "paragraph":
            segmenti = tekst.split('\n\n')
        elif granularnost == "sentence":
            segmenti = re.split(r'(?<=[.!?])\s+', tekst)
        else:
            segmenti = [tekst]

        segmenti = segmenti[:kolicina]
        prevedeni = [self.prevedi_segment(seg) for seg in segmenti]

        # Spremanje
        output = []
        if include_header:
            output.append(self._generiraj_test_header(kolicina, granularnost))

        output.extend(prevedeni)
        self._cp.atomic_write(output_path, '\n\n'.join(output))

        # Spremi last_test parametre
        self._cp.spremi_last_test({
            "granularity": granularnost,
            "count": kolicina,
            "include_header": include_header
        })

    # -----------------------------------------------------------------------
    # API pozivi i provider adaptori
    # -----------------------------------------------------------------------

    def _api_call(self, messages: list[dict[str, str]]) -> str:
        """Privatna metoda za API poziv - delegira na odgovarajući adapter."""
        adapter = getattr(self, f"_call_{self._provider}", None)
        if adapter is None:
            raise ValueError(f"Nepodržani provider: {self._provider}")

        return adapter(messages)

    def _build_payload(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        """Gradi API payload na temelju konfiguracije."""
        payload = {
            "messages": messages,
            "temperature": self._trans_cfg.get("temperature", 0.25),
            "max_tokens": self._trans_cfg.get("max_tokens", 4000),
            "top_p": self._trans_cfg.get("top_p", 0.80),
            "top_k": self._trans_cfg.get("top_k", 15),
            "min_p": self._trans_cfg.get("min_p", 0.05),
            "repeat_penalty": self._trans_cfg.get("repeat_penalty", 1.20),
            "stream": False
        }

        if self._trans_cfg.get("disable_reasoning", True):
            payload["reasoning"] = False
            payload["thinking"] = False

        return payload

    def _call_lm_studio(self, messages: list[dict[str, str]]) -> str:
        """Adapter za LM Studio (OpenAI-compatible)."""
        provider_cfg = self._api_cfg.get("providers", {}).get("lm_studio", {})
        base_url = provider_cfg.get("base_url", "http://127.0.0.1:1234/v1")
        model = provider_cfg.get("model", "")

        payload = self._build_payload(messages)
        if model:
            payload["model"] = model

        return self._http_request(f"{base_url}/chat/completions", payload)

    def _call_ollama_local(self, messages: list[dict[str, str]]) -> str:
        """Adapter za lokalni Ollama."""
        provider_cfg = self._api_cfg.get("providers", {}).get("ollama_local", {})
        base_url = provider_cfg.get("base_url", "http://127.0.0.1:11434/api")
        model = provider_cfg.get("model", "llama3.2")

        payload = self._build_payload(messages)
        payload["model"] = model

        return self._http_request(f"{base_url}/chat", payload)

    def _call_ollama_cloud(self, messages: list[dict[str, str]]) -> str:
        """Adapter za Ollama cloud."""
        provider_cfg = self._api_cfg.get("providers", {}).get("ollama_cloud", {})
        base_url = provider_cfg.get("base_url", "https://api.ollama.ai/v1")
        model = provider_cfg.get("model", "llama3.2")
        api_key = provider_cfg.get("api_key", "")

        payload = self._build_payload(messages)
        payload["model"] = model

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        return self._http_request(f"{base_url}/chat/completions", payload, headers)

    def _call_openai(self, messages: list[dict[str, str]]) -> str:
        """Adapter za OpenAI."""
        provider_cfg = self._api_cfg.get("providers", {}).get("openai", {})
        base_url = provider_cfg.get("base_url", "https://api.openai.com/v1")
        model = provider_cfg.get("model", "gpt-4o")
        api_key = provider_cfg.get("api_key", "")

        payload = self._build_payload(messages)
        payload["model"] = model

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        return self._http_request(f"{base_url}/chat/completions", payload, headers)

    def _call_gemini(self, messages: list[dict[str, str]]) -> str:
        """Adapter za Google Gemini."""
        provider_cfg = self._api_cfg.get("providers", {}).get("gemini", {})
        base_url = provider_cfg.get("base_url", "https://generativelanguage.googleapis.com/v1beta")
        model = provider_cfg.get("model", "gemini-1.5-pro")
        api_key = provider_cfg.get("api_key", "")

        # Gemini koristi drugačiji format
        payload = {
            "contents": [{"parts": [{"text": msg["content"]} for msg in messages if msg["role"] == "user"]}],
            "generationConfig": {
                "temperature": self._trans_cfg.get("temperature", 0.25),
                "maxOutputTokens": self._trans_cfg.get("max_tokens", 4000),
            }
        }

        headers = {"Content-Type": "application/json"}
        if api_key:
            url = f"{base_url}/models/{model}:generateContent?key={api_key}"
        else:
            url = f"{base_url}/models/{model}:generateContent"

        response = self._http_request(url, payload, headers)
        # Gemini response format je drugačiji
        try:
            data = json.loads(response)
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, json.JSONDecodeError):
            return response

    def _call_qwen(self, messages: list[dict[str, str]]) -> str:
        """Adapter za Qwen (Alibaba)."""
        provider_cfg = self._api_cfg.get("providers", {}).get("qwen", {})
        base_url = provider_cfg.get("base_url", "https://dashscope.aliyuncs.com/api/v1")
        model = provider_cfg.get("model", "qwen-turbo")
        api_key = provider_cfg.get("api_key", "")

        payload = self._build_payload(messages)
        payload["model"] = model

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        return self._http_request(f"{base_url}/chat/completions", payload, headers)

    def _call_custom(self, messages: list[dict[str, str]]) -> str:
        """Adapter za custom provider."""
        provider_cfg = self._api_cfg.get("providers", {}).get("custom", {})
        base_url = provider_cfg.get("base_url", "")
        model = provider_cfg.get("model", "")
        api_key = provider_cfg.get("api_key", "")

        if not base_url:
            raise ValueError("Custom provider base_url nije definiran")

        payload = self._build_payload(messages)
        if model:
            payload["model"] = model

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        return self._http_request(base_url, payload, headers)

    # -----------------------------------------------------------------------
    # HTTP request helper
    # -----------------------------------------------------------------------

    def _http_request(self, url: str, payload: dict[str, Any],
                     headers: dict[str, str] | None = None) -> str:
        """Izvršava HTTP POST request."""
        if headers is None:
            headers = {"Content-Type": "application/json; charset=utf-8", "Accept": "application/json"}

        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                response_data = json.loads(response.read().decode('utf-8'))
                # Standard OpenAI format
                if "choices" in response_data:
                    return response_data["choices"][0]["message"]["content"].strip()
                # Fallback - vrati cijeli response
                return str(response_data)
        except urllib.error.HTTPError as e:
            logging.error(f"HTTP greška: {e.code} - {e.reason}")
            raise
        except urllib.error.URLError as e:
            logging.error(f"URL greška: {e.reason}")
            raise
        except json.JSONDecodeError as e:
            logging.error(f"JSON decode error: {e}")
            raise

    # -----------------------------------------------------------------------
    # Pomoćne metode
    # -----------------------------------------------------------------------

    def _je_strukturni_ili_kratak(self, tekst: str) -> bool:
        """Detektira je li tekst strukturni ili prekratak za LLM."""
        tekst = tekst.strip()
        if len(tekst) < 10:
            return True
        # Samo brojevi, znakovi, prazno
        if re.match(r'^[\d\s\-\*\#\.]+$', tekst):
            return True
        return False

    def _generiraj_default_system_prompt(self) -> str:
        """Generira default system prompt."""
        return "Ti si stručni prevoditelj s engleskog na hrvatski. Prevedi dani tekst točno i prirodno."

    def _generiraj_test_header(self, kolicina: int, granularnost: str) -> str:
        """Generira header za testni prijevod."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "=" * 80,
            f"TEST PRIJEVOD — Dynamic Book Translator v{self._cfg.get('project', {}).get('version', '0.4.0')}",
            "=" * 80,
            f"Vrijeme: {timestamp}",
            f"Granularnost: {granularnost}",
            f"Količina: {kolicina} segmenata",
            f"Provider: {self._provider}",
            "=" * 80,
            ""
        ]
        return '\n'.join(lines)

    def _prikazi_prekid_meni(self) -> str:
        """Prikazuje meni za prekid i vraća akciju."""
        print("\n")
        print("=" * 60)
        print("⏸️  PREKID DETECTED - Odaberite opciju:")
        print("=" * 60)
        print("  1. Sačekaj kraj segmenta → spremi → izađi")
        print("  2. Prekini odmah → spremi što je do sada → izađi")
        print("  3. Nastavi prevođenje")
        print("  X. Prekini odmah bez spremanja")
        print("=" * 60)

        while True:
            odgovor = input("Odabir: ").strip().upper()
            if odgovor == "1":
                return "finish"
            elif odgovor == "2":
                return "finish"
            elif odgovor == "3":
                return "continue"
            elif odgovor == "X":
                return "abort"

    def detektiraj_aktivni_model(self) -> str:
        """Detektira aktivni model (ako je auto_detect_model uključen)."""
        if not self._api_cfg.get("auto_detect_model", True):
            provider_cfg = self._api_cfg.get("providers", {}).get(self._provider, {})
            return provider_cfg.get("model", "")

        # Auto-detect logika - zavisi od providera
        try:
            if self._provider == "lm_studio":
                return self._detect_lm_studio_model()
            elif self._provider == "ollama_local":
                return self._detect_ollama_model()
        except Exception as e:
            logging.warning(f"Auto-detect nije uspio: {e}")

        return ""
