"""
app/translator.py — Unificirani prevoditelj s više providera
Ref: doc/README_TechDoc.md §9
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
import urllib.error
from typing import Any, Optional
from datetime import datetime
from pathlib import Path

from app.utils import (
    unificiraj_navodnike,
    ocisti_leaked_prijevod,
    detektiraj_x_tipku,
    prikazi_progres,
)
from app.checkpoint import CheckpointManager
from app.logger import log_llm_response, log_verbatim


class Translator:
    """Unificirani prevoditelj s podrškom za više API providera.

    Uz osnovno prevođenje, podržava:
      - Per-book memoriju: učitava `[ime_knjige]_memorija.json` (CHARACTERS,
        GLOSSARY, GRAMMAR_FIXES) i injektira je u system prompt
        (CHARACTER GENDER REGISTER blok) — kao u mamba_voice.py.
      - Detaljan progress bar s brojem riječi (akumulirano/ukupno + %).
    """

    # Memorija za trenutnu knjigu (CHARACTERS, GLOSSARY, GRAMMAR_FIXES)
    _UCITANA_MEMORIJA: dict[str, Any] = {}

    def __init__(self, config: dict[str, Any], checkpoint_manager: CheckpointManager) -> None:
        self._cfg = config
        self._cp = checkpoint_manager
        self._api_cfg = config.get("api", {})
        self._trans_cfg = config.get("translation", {})
        self._provider = self._api_cfg.get("provider", "lm_studio")
        self._timeout = self._api_cfg.get("timeout", 120)
        self._book_system_prompt: str | None = None  # Per-book system prompt iz config.yaml
        self._memorija_file: str | None = None       # Ime memorija datoteke iz config.yaml
        self._book_dir: str | None = None            # Direktorij knjige
        self._book_memorija_id: str | None = None    # ID za prepoznavanje promjene knjige

    # -----------------------------------------------------------------------
    # Per-book memorija ([ime_knjige]_memorija.json)
    # -----------------------------------------------------------------------

    def postavi_knjigu(self, book_dir: str, book_config: dict[str, Any] | None = None) -> None:
        """Postavlja trenutnu knjigu i učitava njezinu memoriju.

        Ekvivalent `postavi_trenutnu_knjigu()` iz mamba_voice.py — umjesto
        `likovi_memorija.json` koristi `[ime_knjige]_memorija.json` (npr.
        `Foundation---Isaac-Asimov_memorija.json`).

        Args:
            book_dir: Putanja do direktorija knjige (work/output/<Knjiga>/).
            book_config: Per-book config.yaml (opcionalno; sadrži system_prompt
                i memorija_file).
        """
        self._book_dir = book_dir
        self._book_system_prompt = None
        self._memorija_file = None

        if book_config:
            self._book_system_prompt = book_config.get("system_prompt")
            self._memorija_file = book_config.get("memorija_file")

        memorija_putanja = self._pronadi_memorija_datoteku(book_dir, self._memorija_file)

        # Resetiraj memoriju ako se knjiga promijenila
        novi_id = f"{book_dir}:{memorija_putanja}"
        if novi_id != self._book_memorija_id:
            type(self)._UCITANA_MEMORIJA = {}
            self._book_memorija_id = novi_id

        if not memorija_putanja or not os.path.exists(memorija_putanja):
            logging.info("ℹ️ Memorija datoteka ne postoji - koristim standardni system prompt")
            return

        try:
            with open(memorija_putanja, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data:
                type(self)._UCITANA_MEMORIJA = data
                logging.info(f"✅ Učitano {len(data)} sekcija memorije iz: {memorija_putanja}")
            else:
                logging.info("ℹ️ Memorija datoteka je prazna - koristim standardni system prompt")
        except Exception as e:
            logging.warning(f"Greška pri učitavanju memorija datoteke: {e}")

    def _generiraj_system_prompt(self) -> str:
        """Generira finalni system prompt s opcionalnim injektom memorije.

        Ekvivalent `generiraj_system_prompt_sa_likovima()` iz mamba_voice.py —
        formatira memoriju (CHARACTERS + GLOSSARY + GRAMMAR_FIXES) u STRICT
        blok i dodaje ga ispred per-book (ili default) system prompt-a.

        Returns:
            Modificirani system prompt string (s memorijom ili bez).
        """
        base_prompt = self._book_system_prompt or self._generiraj_default_system_prompt()
        memorija = type(self)._UCITANA_MEMORIJA

        if not memorija:
            return base_prompt

        linije: list[str] = []

        # CHARACTERS -> CHARACTER GENDER REGISTER
        characters = memorija.get("CHARACTERS") or {}
        for ime, opis in characters.items():
            linije.append(f"{ime}: {opis}")

        # GLOSSARY -> pojam = prijevod
        glossary = memorija.get("GLOSSARY") or {}
        for pojam, prijevod in glossary.items():
            linije.append(f"{pojam} = {prijevod} (GLOSSARY)")

        # GRAMMAR_FIXES -> naziv: pravilo
        grammar = memorija.get("GRAMMAR_FIXES") or {}
        for naziv, pravilo in grammar.items():
            linije.append(f"{naziv}: {pravilo} (GRAMMAR_FIXES)")

        if not linije:
            return base_prompt

        memorijski_blok = (
            "CHARACTER GENDER REGISTER (STRICT DIRECTIVE):\n"
            "For the duration of this text, adhere to these strictly locked character profiles:\n"
            + "\n".join(linije) + "\n"
            + "-" * 80 + "\n"
        )

        logging.debug(f"Injektovan memorijski blok u system prompt ({len(linije)} stavki)")
        return memorijski_blok + base_prompt

    @staticmethod
    def _pronadi_memorija_datoteku(book_dir: str, memorija_file: str | None) -> str | None:
        """Pronalazi `[ime_knjige]_memorija.json` u direktoriju knjige.

        Prvo koristi `memorija_file` iz config.yaml; ako nije definiran, traži
        bilo koju `*_memorija.json` datoteku u book_dir.

        Args:
            book_dir: Putanja do direktorija knjige.
            memorija_file: Ime memorija datoteke iz config.yaml (opcionalno).

        Returns:
            Apsolutna putanja do memorija datoteke ili None.
        """
        dir_path = Path(book_dir)
        if not dir_path.exists() or not dir_path.is_dir():
            return None

        if memorija_file:
            kandidat = dir_path / memorija_file
            if kandidat.exists():
                return str(kandidat)

        for kandidat in dir_path.glob("*_memorija.json"):
            return str(kandidat)

        return None

    # -----------------------------------------------------------------------
    # Javne metode za prevođenje
    # -----------------------------------------------------------------------

    def prevedi_segment(self, tekst: str, system_prompt: str | None = None) -> str:
        """Unificirana metoda za prevođenje segmenta (odlomak/paragraf/rečenica).

        Ako system_prompt nije proslijeđen, koristi memoriju knjige
        (CHARACTER GENDER REGISTER) iz `_generiraj_system_prompt()`.

        Args:
            tekst: Tekst za prevođenje.
            system_prompt: Opcionalni system prompt (ako None, koristi memoriju/default).

        Returns:
            Prevedeni tekst.
        """
        if len(tekst.strip()) <= 2:
            return tekst

        if self._je_strukturni_ili_kratak(tekst):
            logging.debug(f"Preskačem LLM za kratki/strukturni segment: '{tekst[:50]}...'")
            return tekst

        if system_prompt is None:
            system_prompt = self._generiraj_system_prompt()

        # P1: Verbatim log originalnog teksta prije slanja
        log_verbatim(tekst, "prevedi_segment - input")

        response = self._api_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": tekst}
            ]
        )

        # Post-processing
        response = unificiraj_navodnike(response)
        response = ocisti_leaked_prijevod(response)

        # P1: Verbatim log prevedenog teksta
        log_verbatim(response, "prevedi_segment - output")

        return response

    def prevedi_knjigu(self, tekst: str, output_path: str, book_id: str,
                      granularnost: str = "paragraph",
                      resume_from: int = 0) -> tuple[str, bool]:
        """Produkcijski prijevod cijele knjige s checkpointingom i detaljnim progressom.

        Progress bar prikazuje broj riječi (akumulirano/ukupno + %) kao u
        mamba_voice.py. Koristi per-book memoriju iz `postavi_knjigu()`.

        P2: Podržava nastavak od određenog segmenta (resume_from) za
        checkpoint resume funkcionalnost.

        Args:
            tekst: Cijeli tekst knjige.
            output_path: Putanja za spremanje prevedenog teksta.
            book_id: Jedinstveni ID knjige za checkpointing.
            granularnost: Granularnost segmentacije (paragraph/sentence).
            resume_from: Indeks segmenta od kojeg se nastavlja (0 = od početka).

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

        # Očisti prazne segmente
        segmenti = [s.strip() for s in segmenti if s.strip()]

        if not segmenti:
            return "", False

        ukupno = len(segmenti)
        ukupno_rijeci = sum(len(s.split()) for s in segmenti)
        akumulirane_rijeci = 0
        je_prekinuto = False
        prevedeni: list[str] = []

        # P2: Resume - učitaj postojeći prijevod i preskoči već prevedene segmente
        if resume_from > 0 and os.path.exists(output_path):
            try:
                with open(output_path, 'r', encoding='utf-8') as f:
                    postojeci_tekst = f.read()
                postojeci_segmenti = postojeci_tekst.split('\n\n') if granularnost == "paragraph" else postojeci_tekst.split(' ')
                postojeci_segmenti = [s.strip() for s in postojeci_segmenti if s.strip()]
                prevedeni = postojeci_segmenti[:resume_from]
                akumulirane_rijeci = sum(len(s.split()) for s in prevedeni)
                logging.info(f"✅ Resume: učitano {len(prevedeni)} prevedenih segmenata, nastavljam od {resume_from}")
            except Exception as e:
                logging.warning(f"Greška pri učitavanju postojećeg prijevoda za resume: {e}")

        for idx, segment in enumerate(segmenti):
            # P2: Preskoči već prevedene segmente pri resume-u
            if idx < resume_from:
                continue

            rijeci_u_segmentu = len(segment.split())

            # Detekcija prekida
            if detektiraj_x_tipku():
                akcija = self._prikazi_prekid_meni()
                if akcija == "finish":
                    je_prekinuto = True
                    break
                elif akcija == "abort":
                    return "", True
                # "continue" - nastavi normalno

            # Prevođenje
            try:
                prijevod = self.prevedi_segment(segment)
                prevedeni.append(prijevod)
            except Exception as e:
                logging.error(f"Greška pri prevođenju segmenta {idx + 1}/{ukupno}: {e}")
                prevedeni.append(segment)  # Fallback na original

            akumulirane_rijeci += rijeci_u_segmentu

            # Checkpoint
            self._cp.spremi_checkpoint({
                "book_id": book_id,
                "current_segment": idx + 1,
                "total_segments": ukupno,
                "output_path": output_path
            })

            # Progress s brojem riječi
            dodatno = ""
            if ukupno_rijeci > 0:
                postotak = int(akumulirane_rijeci / ukupno_rijeci * 100)
                dodatno = f"riječi: {akumulirane_rijeci}/{ukupno_rijeci} ({postotak}%)"
            prikazi_progres(idx + 1, ukupno, f"Segment {idx + 1}/{ukupno}", dodatno)

        # Spremanje
        final_tekst = '\n\n'.join(prevedeni) if granularnost == "paragraph" else ' '.join(prevedeni)

        if not je_prekinuto:
            self._cp.atomic_write(output_path, final_tekst)
            self._cp.obrisi_checkpoint(book_id)

        return final_tekst, je_prekinuto

    def prevedi_test(self, tekst: str, granularnost: str = "paragraph",
                     kolicina: int = 1, header: bool = True) -> str:
        """Testni prijevod s opcionalnim headerom.

        Vraća prevedeni tekst (s opcionalnim headerom) — pozivatelj
        sam sprema u željeni direktorij. Koristi per-book memoriju.

        Args:
            tekst: Izvorni tekst.
            granularnost: Granularnost (paragraph/sentence).
            kolicina: Broj segmenata za prevođenje.
            header: Uključi header u output.

        Returns:
            Prevedeni tekst (s headerom ako je uključen).
        """
        # Segmentacija
        if granularnost == "paragraph":
            segmenti = tekst.split('\n\n')
        elif granularnost == "sentence":
            segmenti = re.split(r'(?<=[.!?])\s+', tekst)
        else:
            segmenti = [tekst]

        segmenti = [s.strip() for s in segmenti if s.strip()][:kolicina]

        # Test prijevod s progress barom (broj riječi)
        ukupno_rijeci = sum(len(s.split()) for s in segmenti)
        akumulirane_rijeci = 0
        prevedeni = []
        for i, seg in enumerate(segmenti):
            prijevod = self.prevedi_segment(seg)
            prevedeni.append(prijevod)
            akumulirane_rijeci += len(seg.split())
            dodatno = ""
            if ukupno_rijeci > 0:
                postotak = int(akumulirane_rijeci / ukupno_rijeci * 100)
                dodatno = f"riječi: {akumulirane_rijeci}/{ukupno_rijeci} ({postotak}%)"
            prikazi_progres(i + 1, len(segmenti),
                            f"Segment {i + 1}/{len(segmenti)}", dodatno)

        # Spremanje
        output = []
        if header:
            output.append(self._generiraj_test_header(kolicina, granularnost))

        output.extend(prevedeni)
        return '\n\n'.join(output)

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
        model = provider_cfg.get("model", "gemini-2.0-flash")
        api_key = provider_cfg.get("api_key", "")

        # Gemini koristi specifičan contents format
        # Injektiramo system instruction i user upite na pravilan način za Gemini
        system_instruction = None
        gemini_contents = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "").strip()
            if not content:
                continue

            if role == "system":
                system_instruction = {"parts": [{"text": content}]}
            elif role == "user":
                gemini_contents.append({"role": "user", "parts": [{"text": content}]})
            elif role == "assistant":
                gemini_contents.append({"role": "model", "parts": [{"text": content}]})

        payload: dict[str, Any] = {
            "contents": gemini_contents,
            "generationConfig": {
                "temperature": self._trans_cfg.get("temperature", 0.25),
                "maxOutputTokens": self._trans_cfg.get("max_tokens", 4000),
            }
        }

        if system_instruction:
            payload["systemInstruction"] = system_instruction

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
                    result = response_data["choices"][0]["message"]["content"].strip()
                    # P1: Logiraj LLM razgovor (prompt + response)
                    user_msg = ""
                    for m in payload.get("messages", []):
                        if m.get("role") == "user":
                            user_msg = m.get("content", "")
                            break
                    log_llm_response(user_msg, result, {
                        "provider": self._provider,
                        "url": url,
                        "model": payload.get("model", ""),
                    })
                    return result
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
        """Generira header za testni prijevod s detaljima aktivnog modela.

        P3: Uključuje ime modela, parametre, quantization, context length
        i sve dostupne detalje iz API-ja.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # P3: Dohvati detalje modela iz API-ja
        detalji = self.dohvati_detalje_modela()
        model_name = detalji.get("model", "") or self.detektiraj_aktivni_model() or "Nepoznat"

        lines = [
            "=" * 80,
            f"TEST PRIJEVOD — Dynamic Book Translator v{self._cfg.get('project', {}).get('version', '0.4.0')}",
            "=" * 80,
            f"Vrijeme: {timestamp}",
            f"Granularnost: {granularnost}",
            f"Količina: {kolicina} segmenata",
            f"Provider: {self._provider}",
            f"Model: {model_name}",
        ]

        # Dodaj detalje modela ako su dostupni
        parametri = detalji.get("parametri", "")
        quantization = detalji.get("quantization", "")
        context_length = detalji.get("context_length", "")
        size = detalji.get("size", "")
        owned_by = detalji.get("owned_by", "")

        if parametri:
            lines.append(f"Parametri: {parametri}")
        if quantization:
            lines.append(f"Quantization: {quantization}")
        if context_length:
            lines.append(f"Context length: {context_length}")
        if size:
            # Pretvori bytes u čitljiv format
            try:
                size_bytes = int(size)
                if size_bytes >= 1024 * 1024 * 1024:
                    size_str = f"{size_bytes / (1024**3):.1f} GB"
                elif size_bytes >= 1024 * 1024:
                    size_str = f"{size_bytes / (1024**2):.1f} MB"
                else:
                    size_str = f"{size_bytes / 1024:.1f} KB"
                lines.append(f"Veličina modela: {size_str}")
            except (ValueError, TypeError):
                lines.append(f"Veličina modela: {size}")
        if owned_by:
            lines.append(f"Owned by: {owned_by}")

        # Dodaj parametre prijevoda
        lines.append("=" * 80)
        lines.append(f"Temperature: {self._trans_cfg.get('temperature', 0.25)} | "
                     f"Top-p: {self._trans_cfg.get('top_p', 0.80)} | "
                     f"Top-k: {self._trans_cfg.get('top_k', 15)} | "
                     f"Max tokens: {self._trans_cfg.get('max_tokens', 4000)}")
        lines.append("=" * 80)
        lines.append("")

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

    # -----------------------------------------------------------------------
    # Auto-detekcija modela (P3 - popravak regresije)
    # -----------------------------------------------------------------------

    def _detect_lm_studio_model(self) -> str:
        """Detektira aktivni model iz LM Studio API-ja (GET /v1/models).

        Ekvivalent detektiraj_aktivni_model() iz mamba_voice.py.

        Returns:
            Naziv modela ili prazan string.
        """
        provider_cfg = self._api_cfg.get("providers", {}).get("lm_studio", {})
        base_url = provider_cfg.get("base_url", "http://127.0.0.1:1234/v1")
        models_url = f"{base_url}/models"

        try:
            request = urllib.request.Request(models_url, method="GET")
            with urllib.request.urlopen(request, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                if data.get("data") and len(data["data"]) > 0:
                    model_id = data["data"][0]["id"]
                    logging.info(f"✅ Auto-detektovan LM Studio model: {model_id}")
                    return model_id
        except Exception as e:
            logging.warning(f"LM Studio auto-detect nije uspio: {e}")
        return ""

    def _detect_ollama_model(self) -> str:
        """Detektira aktivni model iz lokalnog Ollama API-ja (GET /api/tags).

        Returns:
            Naziv modela ili prazan string.
        """
        provider_cfg = self._api_cfg.get("providers", {}).get("ollama_local", {})
        base_url = provider_cfg.get("base_url", "http://127.0.0.1:11434/api")
        tags_url = f"{base_url}/tags"

        try:
            request = urllib.request.Request(tags_url, method="GET")
            with urllib.request.urlopen(request, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                if data.get("models") and len(data["models"]) > 0:
                    model_name = data["models"][0]["name"]
                    logging.info(f"✅ Auto-detektovan Ollama model: {model_name}")
                    return model_name
        except Exception as e:
            logging.warning(f"Ollama auto-detect nije uspio: {e}")
        return ""

    def dohvati_detalje_modela(self) -> dict[str, Any]:
        """Dohvaća detalje o aktivnom modelu iz API-ja.

        Za LM Studio: GET /v1/models vraća listu s id, object, owned_by, itd.
        Za Ollama: GET /api/tags vraća listu s name, size, details (parametri, quantization).

        Returns:
            Rječnik s detaljima modela (model, provider, parametri, quantization, size, ...).
        """
        detalji: dict[str, Any] = {
            "model": "",
            "provider": self._provider,
            "parametri": "",
            "quantization": "",
            "size": "",
            "context_length": "",
            "raw": None,
        }

        try:
            if self._provider == "lm_studio":
                provider_cfg = self._api_cfg.get("providers", {}).get("lm_studio", {})
                base_url = provider_cfg.get("base_url", "http://127.0.0.1:1234/v1")
                models_url = f"{base_url}/models"
                request = urllib.request.Request(models_url, method="GET")
                with urllib.request.urlopen(request, timeout=5) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    if data.get("data") and len(data["data"]) > 0:
                        model_info = data["data"][0]
                        detalji["model"] = model_info.get("id", "")
                        detalji["raw"] = model_info
                        # LM Studio može vratiti dodatne metapodatke
                        detalji["context_length"] = model_info.get("context_length", "")
                        detalji["owned_by"] = model_info.get("owned_by", "")
            elif self._provider == "ollama_local":
                provider_cfg = self._api_cfg.get("providers", {}).get("ollama_local", {})
                base_url = provider_cfg.get("base_url", "http://127.0.0.1:11434/api")
                tags_url = f"{base_url}/tags"
                request = urllib.request.Request(tags_url, method="GET")
                with urllib.request.urlopen(request, timeout=5) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    if data.get("models") and len(data["models"]) > 0:
                        model_info = data["models"][0]
                        detalji["model"] = model_info.get("name", "")
                        detalji["raw"] = model_info
                        # Ollama details sekcija
                        details = model_info.get("details", {})
                        detalji["parametri"] = details.get("parameter_size", "")
                        detalji["quantization"] = details.get("quantization_level", "")
                        detalji["size"] = model_info.get("size", "")
                        detalji["context_length"] = details.get("context_length", "")
        except Exception as e:
            logging.warning(f"Dohvat detalja modela nije uspio: {e}")

        return detalji
