"""
app/translator.py — Unificirani prevoditelj s više providera
Ref: doc/README_TechDoc.md §9
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
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

    def __init__(self, config: dict[str, Any], checkpoint_manager: CheckpointManager,
                 web_mode: bool = False) -> None:
        self._cfg = config
        self._cp = checkpoint_manager
        self._web_mode = web_mode  # True = Web GUI (bez input() blokiranja)
        self._api_cfg = config.get("api", {})
        self._trans_cfg = config.get("translation", {})
        self._provider_name = self._api_cfg.get("provider", "lmstudio") # Koristimo provider_name i model_name
        self._model_name = self._api_cfg.get("model", "local") # za dohvat provider_cfg iz liste
        self._timeout = self._api_cfg.get("timeout", 120)
        self._book_system_prompt: str | None = None  # Per-book system prompt iz config.yaml
        self._memorija_file: str | None = None       # Ime memorija datoteke iz config.yaml
        self._book_dir: str | None = None            # Direktorij knjige
        self._book_memorija_id: str | None = None    # ID za prepoznavanje promjene knjige

        self._current_provider_cfg: dict[str, Any] = self._dohvati_provider_konfiguraciju() # Dohvati cijelu config za aktivni provider

        # Cache detektiranih lokalnih modela — izbjegava HTTP poziv na /models
        # pri svakom segmentu i spriječava spam [LOKALNI MODEL] logova.
        self._lokalni_modeli_cache: list[str] | None = None

        # Kratka povijest nedavnih segmenata koristi se za očuvanje konteksta
        # bez ponavljanja cjelokupnog system prompta na svakom zahtjevu.
        self._recent_context: list[dict[str, str]] = []
        self._max_recent_context_pairs = max(0, int(self._api_cfg.get("recent_context_pairs", 2)))

    def _dohvati_provider_konfiguraciju(self) -> dict[str, Any]:
        """Dohvaća kompletnu konfiguraciju za aktivni provider i model iz liste."""
        providers_list = self._api_cfg.get("providers", [])
        for p_cfg in providers_list:
            if p_cfg.get("provider") == self._provider_name and p_cfg.get("model") == self._model_name:
                return p_cfg
        return {} # Vraca prazan rječnik ako nije pronađen

    # -----------------------------------------------------------------------
    # Per-book memorija ([ime_knjige]_memorija.json)
    # -----------------------------------------------------------------------

    def postavi_knjigu(self, book_dir: str, book_config: dict[str, Any] | None = None) -> None:
        """Postavlja trenutnu knjigu i učitava njezinu memoriju.

        Ekvivalent `postavi_trenutnu_knjigu()` iz mamba_voice.py — umjesto
        `likovi_memorija.json` koristi `[ime_knjige]_memorija.json` (npr.
        `Foundation---Isaac-Asimov_memorija.json`).

        Također spaja per-book parametre iz config.yaml (parameters) u
        efektivnu translation konfiguraciju, tako da per-book vrijednosti
        (temperature, top_p, top_k, min_p, max_tokens, repeat_penalty,
        thinking_config) imaju prioritet nad globalnim settings.yaml.

        Args:
            book_dir: Putanja do direktorija knjige (work/output/<Knjiga>/).
            book_config: Per-book config.yaml (opcionalno; sadrži system_prompt
                i memorija_file).
        """
        self._book_dir = book_dir
        self._book_system_prompt = None
        self._memorija_file = None
        self._book_title = Path(book_dir).name
        self._book_author = "Unknown"

        if book_config:
            self._book_system_prompt = book_config.get("system_prompt")
            self._memorija_file = book_config.get("memorija_file")
            self._book_title = book_config.get("book_title", Path(book_dir).name)
            self._book_author = book_config.get("author", "Unknown")

            # Per-book parametri (parameters) imaju prioritet nad globalnim
            book_params = book_config.get("parameters") or {}
            if book_params:
                merged_trans = dict(self._trans_cfg)
                for key, value in book_params.items():
                    if key == "thinking_config":
                        # Rekurzivno spoji thinking_config
                        tc_merged = dict(merged_trans.get("thinking_config") or {})
                        tc_merged.update(value or {})
                        merged_trans["thinking_config"] = tc_merged
                    else:
                        merged_trans[key] = value
                self._trans_cfg = merged_trans

            # Per-book api_parameters lista (ako postoji) ima prioritet
            book_api_params = book_config.get("api_parameters")
            if book_api_params:
                self._trans_cfg["api_parameters"] = book_api_params

        memorija_putanja = self._pronadi_memorija_datoteku(book_dir, self._memorija_file)

        # Resetiraj memoriju ako se knjiga promijenila
        novi_id = f"{book_dir}:{memorija_putanja}"
        if novi_id != self._book_memorija_id:
            type(self)._UCITANA_MEMORIJA = {}
            self._book_memorija_id = novi_id

        if not memorija_putanja or not os.path.exists(memorija_putanja):
            logging.info("Memorija datoteka ne postoji - koristim standardni system prompt")
            return

        try:
            with open(memorija_putanja, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Osiguraj da je data rječnik s potrebnim ključevima
            if not isinstance(data, dict):
                data = {}
            data.setdefault("CHARACTERS", {})
            data.setdefault("GLOSSARY", {})
            data.setdefault("GRAMMAR_FIXES", {})
            
            if data:
                type(self)._UCITANA_MEMORIJA = data
                logging.info(f"Učitano {len(data)} sekcija memorije iz: {memorija_putanja}")
            else:
                logging.info("Memorija datoteka je prazna ili neispravna - koristim standardni system prompt")
        except Exception as e:
            logging.warning(f"Greška pri učitavanju memorija datoteke: {e}")

    def _generiraj_system_prompt(self) -> str:
        """Generira kompaktnu verziju system prompta s memorijom.

        Zadržava ključna pravila i najvažniju memoriju, ali smanjuje opterećenje
        prompta po segmentu kako bi veći modeli imali više prostora za stvarni
        prijevod. Niz recent context poruka održava kontinuitet između segmenata
        bez ponavljanja cijelog glossary-ja u svakom requestu.
        """
        base_prompt = self._book_system_prompt or self._generiraj_default_system_prompt()
        memorija = type(self)._UCITANA_MEMORIJA

        if not memorija:
            return base_prompt

        max_chars = 6
        max_glossary = 16
        max_grammar = 6

        linije: list[str] = []
        characters = memorija.get("CHARACTERS") or {}
        for ime, opis in list(characters.items())[:max_chars]:
            linije.append(f"{ime}: {opis}")

        glossary = memorija.get("GLOSSARY") or {}
        for pojam, prijevod in list(glossary.items())[:max_glossary]:
            linije.append(f"{pojam} = {prijevod} (GLOSSARY)")

        grammar = memorija.get("GRAMMAR_FIXES") or {}
        for naziv, pravilo in list(grammar.items())[:max_grammar]:
            linije.append(f"{naziv}: {pravilo} (GRAMMAR_FIXES)")

        if not linije:
            return base_prompt

        memorijski_blok = (
            "CHARACTER GENDER REGISTER (STRICT DIRECTIVE):\n"
            "For the duration of this text, adhere to these strictly locked character profiles:\n"
            + "\n".join(linije)
            + "\n[Supplementary glossary entries are condensed and recent conversation history maintains continuity.]\n"
        )

        compact = memorijski_blok + "\n" + base_prompt
        if len(compact) > 5000:
            compact = (
                "CHARACTER GENDER REGISTER (STRICT DIRECTIVE):\n"
                "Keep the character/terminology profile stable for this book.\n"
                + "\n".join(linije[:20])
                + "\n[Compact context mode: full glossary is not resent on every segment.]\n\n"
                + base_prompt
            )

        logging.debug(f"Injektovan kompaktniji memorijski blok u system prompt ({len(linije)} stavki)")
        return compact

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

    def _ocisti_razmisljanje(self, tekst: str) -> str:
        """Uklanja LLM thinking/reasoning tagove iz odgovora.

        Koristi regex s DOTALL flagom za uklanjanje:
        - blokove
        - <thought>...</thought> blokove

        Args:
            tekst: Čisti tekst s potencijalnim thinking tagovima.

        Returns:
            Očišćeni tekst bez thinking tagova.
        """
        if not tekst:
            return tekst

        # Ukloni  (multiline, DOTALL)
        tekst = re.sub(r'<think>.*?', '', tekst, flags=re.DOTALL | re.IGNORECASE)
        
        # Ukloni <thought>...</thought> (multiline, DOTALL)
        tekst = re.sub(r'<thought>.*?</thought>', '', tekst, flags=re.DOTALL | re.IGNORECASE)
        
        # Očisti višak praznih redova i vrati stripped rezultat
        return tekst.strip()

    def _ucitaj_blank_response_policy(self) -> dict[str, Any]:
        """Učitava config-driven fallback policy za prazne odgovore.

        Policy je lista koraka; preporučena default vrijednost je 3 koraka, ali se
        može definirati bilo koji broj koraka bez hardkodiranja modela.
        """
        fallback_cfg = self._cfg.get("fallback") or {}
        blank_cfg = fallback_cfg.get("blank_response") or {}
        if not isinstance(blank_cfg, dict):
            blank_cfg = {}

        policy = blank_cfg.get("policy") or [
            {"action": "reduce_prompt", "mode": "compact"},
            {"action": "reduce_prompt", "mode": "minimal"},
            {"action": "record", "message": "MODEL VRAĆA PRAZAN STRING"},
        ]

        return {
            "enabled": bool(blank_cfg.get("enabled", True)),
            "policy": policy,
        }

    def _smanji_prompt_za_retry(self, system_prompt: str, mode: str) -> str:
        """Smanjuje system prompt za retry bez hardkodiranog model-switcha."""
        base_prompt = self._book_system_prompt or self._generiraj_default_system_prompt()
        default_translation = base_prompt.split("\n\nSTRICT DIRECTIVE", 1)[0].strip()

        if mode == "minimal":
            return (
                "Translate the following English text to Croatian. "
                "Output only the final translation, with no explanation, no notes, and no preamble."
            )

        if mode == "compact":
            compact_base = default_translation or self._generiraj_default_system_prompt()
            return (
                compact_base
                + "\n\nKeep the translation strict and concise. "
                "Output only the final Croatian translation, nothing else."
            )

        return system_prompt

    def _obradi_prazan_odgovor(self, messages: list[dict[str, str]], system_prompt: str) -> str:
        """Applies config-driven retry policy for blank completions."""
        policy_cfg = self._ucitaj_blank_response_policy()
        if not policy_cfg.get("enabled", False):
            return ""

        current_prompt = system_prompt
        for item in policy_cfg.get("policy", []):
            action = str(item.get("action", "")).lower()
            if action == "reduce_prompt":
                retry_prompt = self._smanji_prompt_za_retry(current_prompt, str(item.get("mode", "compact")))
                retry_messages = [dict(msg) for msg in messages]
                retry_messages[0]["content"] = retry_prompt
                try:
                    response = self._api_call(messages=retry_messages)
                except ValueError as exc:
                    if "prazan odgovor" not in str(exc).lower():
                        raise
                    response = ""
                response = self._ocisti_razmisljanje(response)
                if response and response.strip():
                    return response
                current_prompt = retry_prompt
                continue

            if action == "record":
                message = str(item.get("message") or "MODEL VRAĆA PRAZAN STRING")
                logging.warning(f"[BLANK RESPONSE] {message}")
                return ""

            if action == "raise":
                message = str(item.get("message") or "Model vraća prazan string.")
                raise RuntimeError(message)

        return ""

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

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if self._recent_context:
            messages.extend(self._recent_context[-(self._max_recent_context_pairs * 2):])
        messages.append({"role": "user", "content": tekst})

        try:
            response = self._api_call(messages=messages)
        except ValueError as exc:
            if "prazan odgovor" not in str(exc).lower():
                raise
            response = self._obradi_prazan_odgovor(messages, system_prompt)
            if not response or not response.strip():
                logging.error(f"[PRIJEVOD] Greška: {exc}")
                return ""

        # Post-processing: očisti thinking tagove PRIJE standardnog čišćenja
        response = self._ocisti_razmisljanje(response)

        if not response or not response.strip():
            response = self._obradi_prazan_odgovor(messages, system_prompt)

        if not response or not response.strip():
            logging.error("[PRIJEVOD] Greška: LLM vratio prazan odgovor.")
            return ""

        # Zadrži kratku povijest recent contexta kako bismo očuvali kontinuitet
        # bez ponavljanja cijelog system prompta za svaki segment.
        self._recent_context.extend([
            {"role": "user", "content": tekst},
            {"role": "assistant", "content": response},
        ])
        if len(self._recent_context) > self._max_recent_context_pairs * 2:
            self._recent_context = self._recent_context[-(self._max_recent_context_pairs * 2):]
        
        # Standardno post-processing
        response = unificiraj_navodnike(response)
        response = ocisti_leaked_prijevod(response)

        # P1: Verbatim log prevedenog teksta
        log_verbatim(response, "prevedi_segment - output")

        return response

    def _je_grupiranje_odlomcima(self, granularnost: str) -> bool:
        """Vraća True za granularnosti koje održavaju odlomke (separator '\n\n')."""
        return granularnost in ("paragraph", "max_chars")

    def _grupiraj_po_znakovima(self, tekst: str, max_chars: int) -> list[str]:
        """Grupira KOMPLETNE odlomke u segmente do max_chars znakova.

        Odlomak koji sam premašuje max_chars ostaje kao vlastiti segment —
        odlomak se nikad ne cijepa kako bismo uvijek proslijedili puni tekst.
        Time se mnogi kratki odlomci (naslovi, pojedinačne rečenice...) šalju
        u jednom zahtjevu i smanjuje potrošnja tokena.
        """
        max_chars = max(1, int(max_chars))
        odlomci = [p.strip() for p in tekst.split('\n\n') if p.strip()]
        if not odlomci:
            return []

        segmenti: list[str] = []
        trenutni: list[str] = []
        duljina = 0
        for odlomak in odlomci:
            duljina_odlomka = len(odlomak)
            # Ako dodavanje sljedećeg odlomka premaši max_chars, zatvori segment
            if trenutni and duljina + duljina_odlomka + 2 > max_chars:
                segmenti.append('\n\n'.join(trenutni))
                trenutni = []
                duljina = 0
            trenutni.append(odlomak)
            duljina += duljina_odlomka + 2  # +2 za '\n\n' separator

        if trenutni:
            segmenti.append('\n\n'.join(trenutni))
        return segmenti

    def _segmentiraj(self, tekst: str, granularnost: str,
                     max_chars: int = 5000,
                     kolicina: int | None = None) -> list[str]:
        """Razbija tekst u segmente prema odabranoj granularnosti.

        granularnost:
          - "paragraph" — svaki odlomak je zaseban segment;
          - "sentence"  — svaka rečenica je zaseban segment;
          - "max_chars" — grupira kompletne odlomke do max_chars znakova;
          - ostalo      — cijeli tekst je jedan segment.

        Args:
            tekst: Izvorni tekst za segmentaciju.
            granularnost: Granularnost segmentacije.
            max_chars: Maksimalni broj znakova po segmentu (za "max_chars").
            kolicina: Maksimalni broj segmenata (opcionalno, za test).

        Returns:
            Lista očišćenih segmenata.
        """
        if granularnost == "paragraph":
            segmenti = tekst.split('\n\n')
        elif granularnost == "sentence":
            segmenti = re.split(r'(?<=[.!?])\s+', tekst)
        elif granularnost == "max_chars":
            segmenti = self._grupiraj_po_znakovima(tekst, max_chars)
        else:
            segmenti = [tekst]

        segmenti = [s.strip() for s in segmenti if s.strip()]
        if kolicina is not None:
            segmenti = segmenti[:kolicina]
        return segmenti

    def prevedi_knjigu(self, tekst: str, output_path: str, book_id: str,
                      granularnost: str = "paragraph",
                      max_chars: int = 5000,
                      resume_from: int = 0) -> tuple[str, bool]:
        """Produkcijski prijevod cijele knjige s checkpointingom i detaljnim progressom.

        Progress bar prikazuje broj riječi (akumulirano/ukupno + %) kao u
        mamba_voice.py. Koristi per-book memoriju iz `postavi_knjigu()`.

        P2: Podržava nastavak od određenog segmenta (resume_from) za
        checkpoint resume funkcionalnost.

        P4: Real-time spremanje — svaki uspješno prevedeni chunk odmah se
        appenda u izlaznu datoteku (mode='a'). Ako skripta pukne ili je
        korisnik zaustavi (Ctrl+C), svi dotadašnji prijevodi su sačuvani.

        P4: Resume logika — prije početka provjerava postoji li već
        djelomično prevedena datoteka. Ako da, učitava je i nastavlja od
        mjesta gdje je stala (brojanjem već prevedenih chunkova).

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
        segmenti = self._segmentiraj(tekst, granularnost, max_chars)

        if not segmenti:
            return "", False

        ukupno = len(segmenti)
        ukupno_rijeci = sum(len(s.split()) for s in segmenti)
        akumulirane_rijeci = 0
        je_prekinuto = False
        prevedeni: list[str] = []

        # P4: Resume - automatski učitaj postojeći prijevod i preskoči već prevedene chunkove
        if resume_from <= 0 and os.path.exists(output_path):
            try:
                with open(output_path, 'r', encoding='utf-8') as f:
                    postojeci_tekst = f.read()
                separator = '\n\n' if self._je_grupiranje_odlomcima(granularnost) else ' '
                postojeci_segmenti = postojeci_tekst.split(separator)
                postojeci_segmenti = [s.strip() for s in postojeci_segmenti if s.strip()]
                resume_from = len(postojeci_segmenti)
                prevedeni = postojeci_segmenti
                akumulirane_rijeci = sum(len(s.split()) for s in prevedeni)
                postotak_resume = int(resume_from / ukupno * 100) if ukupno > 0 else 0
                logging.info(
                    f"[RESUME] Nastavljam od chunka {resume_from}/{ukupno} "
                    f"(prethodno prevedeno {postotak_resume}%)."
                )
            except Exception as e:
                logging.warning(f"Greška pri učitavanju postojećeg prijevoda za resume: {e}")
                resume_from = 0
        elif resume_from > 0 and os.path.exists(output_path):
            try:
                with open(output_path, 'r', encoding='utf-8') as f:
                    postojeci_tekst = f.read()
                separator = '\n\n' if self._je_grupiranje_odlomcima(granularnost) else ' '
                postojeci_segmenti = postojeci_tekst.split(separator)
                postojeci_segmenti = [s.strip() for s in postojeci_segmenti if s.strip()]
                prevedeni = postojeci_segmenti[:resume_from]
                akumulirane_rijeci = sum(len(s.split()) for s in prevedeni)
                logging.info(f"Resume: učitano {len(prevedeni)} prevedenih segmenata, nastavljam od {resume_from}")
            except Exception as e:
                logging.warning(f"Greška pri učitavanju postojećeg prijevoda za resume: {e}")

        # P4: Ctrl+C handler - omogućava čisto zaustavljanje s spremanjem napretka
        try:
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
                    prijevod = self._prevedi_s_fallbackom(segment, granularnost)
                    prevedeni.append(prijevod)
                except (KeyboardInterrupt, InterruptedError) as e:
                    logging.warning(f"Prevođenje prekinuto od strane korisnika: {e}")
                    je_prekinuto = True
                    break
                except RuntimeError as e:
                    # Fail-fast greške (401/403/404) — prekid s spremanjem checkpointa
                    # kako bi korisnik mogao promijeniti provider i nastaviti.
                    logging.error(
                        f"KRITIČNA GREŠKA pri segmentu {idx + 1}/{ukupno}: {e}. "
                        f"Prekidam prijevod — napredak je spremljen."
                    )
                    je_prekinuto = True
                    break
                except Exception as e:
                    logging.error(f"Greška pri prevođenju segmenta {idx + 1}/{ukupno}: {e}")
                    prijevod = segment  # Fallback na original
                    prevedeni.append(prijevod)

                akumulirane_rijeci += rijeci_u_segmentu

                # P4: Real-time spremanje - odmah appendaj prevedeni chunk u izlaznu datoteku
                self._append_prijevod(output_path, prijevod, granularnost, idx, resume_from)

                # Checkpoint
                self._cp.spremi_checkpoint({
                    "book_id": book_id,
                    "book_title": self._book_title,
                    "author": self._book_author,
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
        except KeyboardInterrupt:
            # P4: Ctrl+C handler - spremi napredak i izađi čisto
            print("\nZaustavljeno od strane korisnika. Napredak spremljen.")
            logging.warning("Zaustavljeno od strane korisnika (Ctrl+C). Napredak spremljen.")
            je_prekinuto = True

        # Spremanje
        final_tekst = '\n\n'.join(prevedeni) if self._je_grupiranje_odlomcima(granularnost) else ' '.join(prevedeni)

        if not je_prekinuto:
            self._cp.obrisi_checkpoint(book_id)

        return final_tekst, je_prekinuto

    def _append_prijevod(self, output_path: str, prijevod: str,
                         granularnost: str, idx: int, resume_from: int) -> None:
        """P4: Append-a prevedeni chunk u izlaznu datoteku u realnom vremenu.

        Koristi mode='a' (append) umjesto mode='w' (write). Dodaje separator
        '\n\n' između chunkova za formatiranje.

        Args:
            output_path: Putanja izlazne datoteke.
            prijevod: Prevedeni tekst chunka.
            granularnost: Granularnost (paragraph/sentence) - određuje separator.
            idx: Indeks trenutnog chunka.
            resume_from: Indeks od kojeg se nastavlja (za logiranje).
        """
        separator = '\n\n' if self._je_grupiranje_odlomcima(granularnost) else ' '
        try:
            with open(output_path, 'a', encoding='utf-8') as f:
                # Dodaj separator prije prvog chunka samo ako datoteka već ima sadržaj
                if os.path.getsize(output_path) > 0:
                    f.write(separator)
                f.write(prijevod)
            logging.info(f"Spremljen chunk {idx + 1} u {os.path.basename(output_path)}")
        except Exception as e:
            logging.error(f"Greška pri spremanju chunka {idx + 1}: {e}")

    def _prevedi_s_fallbackom(self, segment: str, granularnost: str) -> str:
        """Prevodi segment uz sigurnosnu mrežu — nikada ne gubi odlomke.

        Za granularnost `max_chars` segment može sadržavati više odlomaka.
        Mali lokalni modeli katkad vrate prazan rezultat ili preskoče ostatak
        velikog bloka (prevedu samo prvi odlomak). Ako se to dogodi, segment se
        ponovno prevodi odlomak po odlomak kako bi kompletan sadržaj ostao
        sačuvan. U najgorem slučaju vraća se originalni tekst umjesto praznine.
        """
        prijevod = self.prevedi_segment(segment)
        if not prijevod or not prijevod.strip():
            prijevod = None

        odlomci = [p.strip() for p in segment.split('\n\n') if p.strip()]

        if granularnost == "max_chars" and len(odlomci) > 1:
            # Provjera cjelovitosti: izlaz ne smije imati manje odlomaka od ulaza
            # (znak da je model preskočio dio sadržaja).
            broj_izlaznih = len([p for p in (prijevod or '').split('\n\n') if p.strip()])
            if prijevod is None or broj_izlaznih < len(odlomci):
                dijelovi = []
                for odlomak in odlomci:
                    dio = self.prevedi_segment(odlomak)
                    dijelovi.append(dio if dio and dio.strip() else odlomak)
                return '\n\n'.join(dijelovi)

        return prijevod if prijevod is not None else segment
    def prevedi_test(self, tekst: str, granularnost: str = "paragraph",
                     max_chars: int = 5000, kolicina: int = 1,
                     header: bool = True) -> str:
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
        segmenti = self._segmentiraj(tekst, granularnost, max_chars, kolicina)

        # Test prijevod s progress barom (broj riječi)
        ukupno_rijeci = sum(len(s.split()) for s in segmenti)
        akumulirane_rijeci = 0
        prevedeni = []
        for i, seg in enumerate(segmenti):
            prijevod = self._prevedi_s_fallbackom(seg, granularnost)
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

        # Ako je model "local", automatski detektiraj aktivni model
        if self._model_name == "local":
            return self._api_call_local(messages)

        # Dinamički kreiraj ime adapter metode (npr. _call_lmstudio)
        adapter_name = f"_call_{self._provider_name}"
        adapter = getattr(self, adapter_name, None)

        if adapter is None:
            raise ValueError(f"Nepodržani provider: {self._provider_name}")

        return adapter(messages)

    def _api_call_local(self, messages: list[dict[str, str]]) -> str:
        """API poziv za 'local' model bez auto-switcha na druge modele.

        Kada je `model: local`, dohvaća se lista dostupnih modela, ali se koristi
        samo PRVI model za trenutni request. Ne iterira se kroz cijeli popis nakon
        praznog odgovora ili 404. Prazan output se obrađuje kroz config policy
        (`fallback.blank_response`), a ne kroz zamjenu modela.
        """
        # Cache detekciju: samo prvi poziv dohvaća modele s HTTP endpointa.
        if self._lokalni_modeli_cache is None:
            modeli = self._dohvati_lokalne_modele()
            if not modeli:
                base_url = self._current_provider_cfg.get("apiBase", "")
                raise RuntimeError(
                    f"Nema dostupnih lokalnih modela na {base_url}/models"
                )
            self._lokalni_modeli_cache = modeli
            logging.info(
                f"[LOKALNI MODEL] Detektiran aktivan model: {modeli[0]}. "
                f"Pokrećem prevođenje."
            )
        else:
            modeli = self._lokalni_modeli_cache

        model = modeli[0]
        try:
            return self._api_call_s_modelom(messages, model)
        except Exception as e:
            logging.warning(
                f"[LOKALNI MODEL] Model '{model}' nije uspio: {e}. "
                f"Ne prebacujem se na drugi lokalni model; predajem se config fallback policy."
            )
            raise

    def _dohvati_lokalne_modele(self) -> list[str]:
        """Dohvaća listu dostupnih modela s lokalnog endpointa {base_url}/models.

        Podržava OpenAI-compatible format (LM Studio) i Ollama format.
        Za Ollama dodaje fallback na /api/tags ako /models ne postoji.

        Returns:
            Lista naziva modela (prazna lista ako nijedan nije dostupan).
        """
        base_url = self._current_provider_cfg.get("apiBase", "")
        if not base_url:
            base_url = {
                "lmstudio": "http://127.0.0.1:1234",
                "unsloth": "http://127.0.0.1:8888",
            }.get(self._provider_name, "http://127.0.0.1:11434")

        # Normaliziraj base_url za OpenAI-compatible (LM Studio, unsloth)
        # — ako već sadrži /v1, ne dodaj ga ponovno
        if self._provider_name in ("lmstudio", "unsloth") and not base_url.rstrip("/").endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"

        models_url = f"{base_url}/models"
        detect_timeout = self._api_cfg.get("auto_detect_timeout", 5)

        try:
            request = urllib.request.Request(models_url, method="GET", headers=self._dohvati_headers())
            with urllib.request.urlopen(request, timeout=detect_timeout) as response:
                data = json.loads(response.read().decode('utf-8'))

                # OpenAI-compatible format: {"data": [{"id": "model1"}, ...]}
                if isinstance(data, dict) and "data" in data:
                    modeli = [m.get("id", "") for m in data["data"] if m.get("id")]
                    return [m for m in modeli if m]

                # Ollama format: {"models": [{"name": "model1"}, ...]}
                if isinstance(data, dict) and "models" in data:
                    modeli = [m.get("name", "") for m in data["models"] if m.get("name")]
                    return [m for m in modeli if m]

                # Fallback: pokušaj parsirati kao listu
                if isinstance(data, list):
                    modeli = []
                    for m in data:
                        if isinstance(m, str):
                            modeli.append(m)
                        elif isinstance(m, dict):
                            modeli.append(m.get("id", "") or m.get("name", ""))
                    return [m for m in modeli if m]
        except Exception as e:
            logging.warning(f"[LOKALNI MODEL] Dohvat modela nije uspio: {e}")

        # Fallback za Ollama: pokušaj /api/tags
        if self._provider_name == "ollama":
            try:
                tags_url = f"{base_url}/api/tags"
                request = urllib.request.Request(tags_url, method="GET")
                with urllib.request.urlopen(request, timeout=detect_timeout) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    if isinstance(data, dict) and "models" in data:
                        modeli = [m.get("name", "") for m in data["models"] if m.get("name")]
                        return [m for m in modeli if m]
            except Exception as e:
                logging.warning(f"[LOKALNI MODEL] Ollama /api/tags dohvat nije uspio: {e}")

        return []

    def _api_call_s_modelom(self, messages: list[dict[str, str]], model: str) -> str:
        """API poziv s eksplicitno navedenim modelom.

        Privremeno postavlja model u provider config, poziva odgovarajući
        adapter, pa vraća originalni model.

        Args:
            messages: Lista poruka za LLM.
            model: Naziv modela za korištenje.

        Returns:
            Odgovor od modela.
        """
        # Dinamički kreiraj ime adapter metode (npr. _call_lmstudio)
        adapter_name = f"_call_{self._provider_name}"
        adapter = getattr(self, adapter_name, None)

        if adapter is None:
            raise ValueError(f"Nepodržani provider: {self._provider_name}")

        # Privremeno postavi model u provider config
        original_model = self._current_provider_cfg.get("model", "")
        self._current_provider_cfg["model"] = model
        try:
            return adapter(messages)
        finally:
            self._current_provider_cfg["model"] = original_model

    def _dohvati_api_parametre(self) -> list[str]:
        """Dohvaća listu API parametara iz konfiguracije (settings.yaml / config.yaml).

        Prioritet ima per-book `api_parameters` lista; inače se koristi
        globalna lista iz settings.yaml; u krajnjem slučaju default lista.

        Returns:
            Lista imena API parametara.
        """
        api_params = self._trans_cfg.get("api_parameters", [])
        if api_params:
            return list(api_params)
        return [
            "temperature", "max_tokens", "top_p", "min_p",
            "top_k", "repeat_penalty", "thinking_config"
        ]

    def _build_payload(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        """Gradi API payload na temelju konfiguracije.

        Koristi dinamičku listu `api_parameters` iz settings.yaml (ili
        per-book config.yaml) da odredi koje ključeve iz translation bloka
        uključiti u API payload. Novi parametri dodani u YAML automatski
        ulaze u payload bez promjene koda.
        """
        payload: dict[str, Any] = {
            "messages": messages,
            "stream": False
        }

        api_parameters = self._dohvati_api_parametre()

        # Dinamički učitaj samo API parametre definirane u api_parameters listi
        for key in api_parameters:
            if key not in self._trans_cfg:
                continue

            value = self._trans_cfg[key]

            # Map parameters if needed for specific providers
            if self._provider_name == "gemini":
                if key == "max_tokens":
                    if "generationConfig" not in payload: payload["generationConfig"] = {}
                    payload["generationConfig"]["maxOutputTokens"] = value
                    continue
                if key == "thinking_config":
                    if "generationConfig" not in payload: payload["generationConfig"] = {}
                    # Gemini prihvaća SAMO thinkingBudget (cijeli broj).
                    # includeThinkingConfig NIJE podržan i uzrokuje HTTP 400.
                    try:
                        thinking_budget = int(value.get("thinking_budget", 0))
                    except (TypeError, ValueError):
                        thinking_budget = 0
                    payload["generationConfig"]["thinkingConfig"] = {
                        "thinkingBudget": thinking_budget
                    }
                    continue

            payload[key] = value

        # Local OpenAI-compatible servers are picky about unsupported root-level
        # flags; keep standard values at the root but move provider-specific knobs
        # into extra_body to avoid HTTP 400s.
        if self._provider_name in ("lmstudio", "unsloth", "ollama"):
            extra_body = payload.setdefault("extra_body", {})

            for key, extra_key in (
                ("top_k", "top_k"),
                ("min_p", "min_p"),
                ("repeat_penalty", "repetition_penalty"),
            ):
                if key in self._trans_cfg:
                    extra_body[extra_key] = self._trans_cfg[key]

            if self._provider_name == "unsloth":
                extra_body["enable_thinking"] = not bool(self._trans_cfg.get("disable_reasoning", True))
                for key in ("enable_tools", "enabled_tools", "tool_choice"):
                    if key in self._trans_cfg:
                        extra_body[key] = self._trans_cfg[key]

            # Root-level reasoning flags are not universally supported and can
            # trigger 400 Bad Request against local OpenAI-compatible servers.
            payload.pop("reasoning", None)
            payload.pop("thinking", None)

        elif self._provider_name == "gemini":
            if self._trans_cfg.get("disable_reasoning", True):
                if "generationConfig" not in payload:
                    payload["generationConfig"] = {}
                if "thinkingConfig" not in payload["generationConfig"]:
                    payload["generationConfig"]["thinkingConfig"] = {}
                payload["generationConfig"]["thinkingConfig"]["thinkingBudget"] = 0

        return payload

    def _call_ollama(self, messages: list[dict[str, str]]) -> str:
        """Adapter za Ollama (lokalni ili cloud)."""
        # Koristimo _current_provider_cfg koji je vec dohvacen u __init__
        base_url = self._current_provider_cfg.get("apiBase", "http://127.0.0.1:11434")
        model = self._current_provider_cfg.get("model", "llama3.2")
        api_key = self._current_provider_cfg.get("api_key", "")

        payload = self._build_payload(messages)
        payload["model"] = model

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Ollama API ima /api/chat endpoint za chat completions (ne /v1/chat/completions)
        return self._http_request(f"{base_url}/api/chat", payload, headers)

    def _call_lmstudio(self, messages: list[dict[str, str]]) -> str:
        """Adapter za LM Studio (OpenAI-compatible)."""
        # Koristimo _current_provider_cfg koji je vec dohvacen u __init__
        base_url = self._current_provider_cfg.get("apiBase", "http://127.0.0.1:1234")
        model = self._current_provider_cfg.get("model", "")

        # Normaliziraj base_url — ako već sadrži /v1, ne dodaj ga ponovno
        if not base_url.rstrip("/").endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"

        payload = self._build_payload(messages)
        if model:
            payload["model"] = model

        return self._http_request(f"{base_url}/chat/completions", payload)

    def _call_unsloth(self, messages: list[dict[str, str]]) -> str:
        """Adapter za unsloth (OpenAI-compatible, lokalni server na :8888)."""
        # Koristimo _current_provider_cfg koji je vec dohvacen u __init__
        base_url = self._current_provider_cfg.get("apiBase", "http://127.0.0.1:8888")
        model = self._current_provider_cfg.get("model", "")

        # Normaliziraj base_url — ako već sadrži /v1, ne dodaj ga ponovno
        if not base_url.rstrip("/").endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"

        payload = self._build_payload(messages)
        if model and model != "local":
            payload["model"] = model

        headers = {"Content-Type": "application/json"}
        # unsloth zahtijeva Authorization: Bearer sk-unsloth-... na svakom zahtjevu.
        headers.update(self._dohvati_headers())

        return self._http_request(f"{base_url}/chat/completions", payload, headers)

    def _call_openai(self, messages: list[dict[str, str]]) -> str:
        """Adapter za OpenAI (ili Qwen putem OpenAI kompatibilnog API-ja)."""
        # Koristimo _current_provider_cfg koji je vec dohvacen u __init__
        base_url = self._current_provider_cfg.get("apiBase", "https://api.openai.com/v1")
        model = self._current_provider_cfg.get("model", "gpt-4o")
        api_key = self._current_provider_cfg.get("api_key", "")

        payload = self._build_payload(messages)
        payload["model"] = model

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        return self._http_request(f"{base_url}/chat/completions", payload, headers)

    def _call_gemini(self, messages: list[dict[str, str]]) -> str:
        """Adapter za Google Gemini."""
        # Koristimo _current_provider_cfg koji je vec dohvacen u __init__
        base_url = self._current_provider_cfg.get("apiBase", "https://generativelanguage.googleapis.com/v1beta")
        model = self._current_provider_cfg.get("model", "gemini-2.0-flash")
        api_key = self._current_provider_cfg.get("api_key", "")

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

        # Use unificirani payload builder and adapt it for Gemini
        base_payload = self._build_payload(messages)
        
        payload: dict[str, Any] = {
            "contents": gemini_contents,
            "generationConfig": base_payload.get("generationConfig", {})
        }

        # Gemini generacijske parametre mapiraj na ispravne nazive (camelCase)
        # i preskoči parametre koje Gemini API ne podržava (min_p, repeat_penalty,
        # ...) — oni uzrokuju HTTP 400 Bad Request.
        gemini_param_map = {
            "temperature": "temperature",
            "top_p": "topP",
            "top_k": "topK",
            "candidate_count": "candidateCount",
            "stop_sequences": "stopSequences",
            "presence_penalty": "presencePenalty",
            "frequency_penalty": "frequencyPenalty",
            "seed": "seed",
        }
        for k, v in base_payload.items():
            if k in ("messages", "stream", "generationConfig", "contents", "systemInstruction"):
                continue
            gemini_key = gemini_param_map.get(k)
            if gemini_key is None:
                logging.debug(f"Gemini: preskačem nepodržani parametar '{k}'")
                continue
            payload["generationConfig"][gemini_key] = v

        if system_instruction:
            payload["systemInstruction"] = system_instruction

        headers = {"Content-Type": "application/json"}
        if api_key:
            url = f"{base_url}/models/{model}:generateContent?key={api_key}"
        else:
            url = f"{base_url}/models/{model}:generateContent"

        response = self._http_request(url, payload, headers)
        # Gemini response format je drugačiji — _http_request vraća parsirani dict.
        # Ako je iz nekog razloga string, pokušaj json.loads; inače koristi dict direktno.
        if isinstance(response, str):
            try:
                data = json.loads(response)
            except json.JSONDecodeError:
                data = None
        else:
            data = response

        result = ""
        if isinstance(data, dict):
            try:
                result = data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError, TypeError):
                logging.warning("Gemini: ne mogu parsirati tekst iz odgovora, vraćam prazan string.")
                result = ""
        else:
            result = str(response)

        # Logiraj Gemini LLM razgovor
        user_msg = ""
        for msg in messages:
            if msg.get("role") == "user":
                user_msg = msg.get("content", "")
                break
        log_llm_response(user_msg, result, {
            "provider": self._provider_name,
            "url": url,
            "model": model,
        })
        return result

    # Uklonjen _call_ollama_local i _call_ollama_cloud jer ih zamjenjuje _call_ollama
    # Uklonjen _call_qwen jer ga pokriva _call_openai (koristi isti API)
    # Uklonjen _call_custom jer nije dio nove arhitekture


    # -----------------------------------------------------------------------
    # HTTP request helper
    # -----------------------------------------------------------------------

    def _dohvati_headers(self) -> dict[str, str]:
        """Buildira HTTP zaglavlja s opcionalnim Bearer tokenom (npr. unsloth).

        Za provajdere koji zahtijevaju API ključ (key_env) uključuje
        Authorization: Bearer <ključ> zaglavlje; inače vraća prazan rječnik.
        """
        headers: dict[str, str] = {}
        api_key = self._current_provider_cfg.get("api_key", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers


    def _http_request(self, url: str, payload: dict[str, Any],
                     headers: dict[str, str] | None = None) -> Any:
        """Izvršava HTTP POST request s automatskim retry mehanizmom za HTTP 429 (Too Many Requests).

        Parametri za retry (max_attempts, initial_delay, backoff_factor) čitaju se iz konfiguracije (settings.yaml).
        Tijekom svakog automatskog pokušaja ispisuje se vizualno odbrojavanje sekundu po sekundu.
        Nakon iscrpljenog broja automatskih pokušaja, korisnika se pita želi li pokušati ponovno [Y] ili prekinuti [X].
        """
        if headers is None:
            headers = {"Content-Type": "application/json; charset=utf-8", "Accept": "application/json"}

        # Verbatim upis cjelovitog payloada prije slanja
        try:
            payload_str = json.dumps(payload, ensure_ascii=False, indent=2)
            log_verbatim(payload_str, f"HTTP REQUEST → {url}")
        except Exception:
            pass

        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')

        pokusaj = 0
        max_automatskih = self._api_cfg.get("retry_max_attempts", 3)
        pocetni_delay = self._api_cfg.get("retry_initial_delay", 10)
        backoff_factor = self._api_cfg.get("retry_backoff_factor", 2)
        trenutni_delay = pocetni_delay

        while True:
            request = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    response_data = json.loads(response.read().decode('utf-8'))
                    # Standard OpenAI format
                    if "choices" in response_data:
                        choice = response_data["choices"][0]
                        message = choice.get("message", {}) if isinstance(choice, dict) else {}
                        content = message.get("content", "") if isinstance(message, dict) else ""
                        result = content.strip() if isinstance(content, str) else str(content).strip()
                        if not result:
                            raise ValueError("LLM vratio prazan odgovor.")
                        # P1: Logiraj LLM razgovor (prompt + response)
                        user_msg = ""
                        for m in payload.get("messages", []):
                            if m.get("role") == "user":
                                user_msg = m.get("content", "")
                                break
                        log_llm_response(user_msg, result, {
                            "provider": self._provider_name,
                            "url": url,
                            "model": payload.get("model", ""),
                        })
                        return result
                    # Fallback - vrati parsirani response (dict).
                    # Provider adapteri (npr. Gemini) sami parsiraju strukturu.
                    return response_data
            except urllib.error.HTTPError as e:
                # P4: Fail-fast logika - trajne greške odmah zaustavljaju skriptu
                if e.code in (401, 403, 404):
                    logging.error(f"KRITIČNA GREŠKA {e.code}: {e.reason}")
                    raise RuntimeError(
                        f"Prekid zbog neautoriziranog pristupa (HTTP {e.code}: {e.reason})."
                    ) from e
                # P4: Retry s exponential backoff za 429 i 5xx greške (max 3 pokušaja)
                elif e.code == 429 or e.code >= 500:
                    pokusaj += 1
                    if pokusaj <= max_automatskih:
                        wait_time = pocetni_delay * (backoff_factor ** (pokusaj - 1))
                        logging.warning(
                            f"Greška {e.code}. Pokušaj {pokusaj}/{max_automatskih}. Čekam {wait_time}s..."
                        )
                        # Odbrojavanje na ekranu sekundu po sekundu
                        for preostalo in range(wait_time, 0, -1):
                            print(f"\rOdbrojavanje do sljedećeg pokušaja: {preostalo}s...   ", end="", flush=True)
                            time.sleep(1)
                        print("\r" + " " * 60 + "\r", end="", flush=True)  # očisti liniju
                        continue
                    else:
                        # Maksimalan broj automatskih pokušaja premašen
                        print(f"\nSvi automatski pokušaji ponavljanja (HTTP {e.code}) su neuspješni.")
                        if self._web_mode:
                            # Web GUI: ne blokiramo na input() — automatski prekid.
                            # prevedi_knjigu hvata InterruptedError, sprema checkpoint
                            # i vraća is_interrupted=True.
                            logging.error(
                                f"HTTP {e.code}: Svi automatski pokušaji su neuspješni. "
                                f"Prekidam prijevod — napredak je spremljen."
                            )
                            raise InterruptedError(
                                f"HTTP {e.code}: Prekid nakon iscrpljenih automatskih pokušaja. "
                                f"Napredak je spremljen — možete promijeniti provider i nastaviti."
                            )
                        # CLI: pitaj korisnika
                        while True:
                            izbor = input("Želite li pokušati ponovno [Y] ili prekinuti proces [X]? (Y/X): ").strip().upper()
                            if izbor in ("Y", "D", "DA", "YES", "P"):
                                pokusaj = 0  # resetiraj pokušaje
                                trenutni_delay = pocetni_delay  # resetiraj delay
                                break
                            elif izbor in ("X", "N", "NE", "NO"):
                                logging.error(f"HTTP {e.code}: Korisnik je odabrao prekid procesa.")
                                raise InterruptedError(f"Proces prekinut od strane korisnika na HTTP {e.code} grešci.")
                else:
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
        """Detektira je li tekst strukturni ili prekratak za LLM (koristeći parametre iz konfiga)."""
        tekst = tekst.strip()
        min_len = self._trans_cfg.get("min_segment_length", 10)
        if len(tekst) < min_len:
            return True
        # Samo brojevi, znakovi, prazno
        if re.match(r'^[\d\s\-\*\#\.]+$', tekst):
            return True
        return False

    def _generiraj_default_system_prompt(self) -> str:
        """Generira default system prompt iz konfiguracije."""
        base_prompt = self._trans_cfg.get(
            "default_system_prompt",
            "Ti si stručni prevoditelj s engleskog na hrvatski. Prevedi dani tekst točno i prirodno."
        )
        
        # Dodaj eksplicitne upute protiv razmišljanja za reasoning modele
        no_thinking_directive = (
            "\n\nSTRICT DIRECTIVE — NO THINKING OR REASONING:\n"
            "Do NOT perform chain-of-thought, do NOT include any thinking process, "
            "reasoning steps, or do NOT use <thought>...</thought> tags. "
            "Output ONLY the raw final translation directly, without any preamble, "
            "explanation, or meta-commentary."
        )
        
        return base_prompt + no_thinking_directive

    def _generiraj_test_header(self, kolicina: int, granularnost: str) -> str:
        """Generira header za testni prijevod s detaljima aktivnog modela.

        P3: Uključuje ime modela, parametre, quantization, context length
        i sve dostupne detalje iz API-ja.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # P3: Dohvati detalje modela iz API-ja
        detalji = self.dohvati_detalje_modela()
        model_name = detalji.get("model", "") or self.detektiraj_aktivni_model() or "Nepoznat"

        # Dinamički izgradi parametre iz api_parameters liste iz konfiguracije
        # (settings.yaml ili per-book config.yaml) — bez hardkodiranja.
        # thinking_config se prikazuje zasebno u vlastitoj liniji.
        api_parameters = self._dohvati_api_parametre()
        params = []
        for key in api_parameters:
            if key == "thinking_config" or key not in self._trans_cfg:
                continue
            value = self._trans_cfg[key]
            # Uredan naziv: max_tokens -> Max tokens, top_p -> Top-p, itd.
            label = key.replace("_", " ").title().replace("Top P", "Top-p").replace("Top K", "Top-k")
            params.append(f"{label}: {value}")

        # Podijeli parametre uredno u DVIJE linije
        mid = (len(params) + 1) // 2
        line1_params = " | ".join(params[:mid]) if params else "—"
        line2_params = " | ".join(params[mid:]) if params[mid:] else "—"

        lines = [
            "=" * 80,
            f"TEST PRIJEVOD — Dynamic Book Translator v{self._cfg.get('project', {}).get('version', '0.4.0')}",
            "=" * 80,
            f"Vrijeme: {timestamp} | Granularnost: {granularnost} | Količina: {kolicina} segm.",
            f"Provider: {self._provider_name} | Model: {model_name}",
        ]

        # Dodaj detalje modela ako su dostupni
        extra_info = []
        if detalji.get("parametri"): extra_info.append(f"Parametri: {detalji['parametri']}")
        if detalji.get("quantization"): extra_info.append(f"Quant: {detalji['quantization']}")
        if detalji.get("context_length"): extra_info.append(f"Context: {detalji['context_length']}")
        
        if extra_info:
            lines.append(" | ".join(extra_info))

        # Dodaj parametre prijevoda dinamički
        lines.append("-" * 80)
        lines.append(line1_params)
        lines.append(line2_params)
        
        # Thinking config if present
        thinking = self._trans_cfg.get("thinking_config", {})
        if thinking and thinking.get("thinking_budget", 0) > 0:
            lines.append(f"Thinking: Level {thinking.get('thinking_level', 'N/A')} | Budget: {thinking.get('thinking_budget')} tokens")

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
        # Auto-detect logika - zavisi od providera
        try:
            if self._provider_name == "lmstudio":
                return self._detect_lm_studio_model()
            elif self._provider_name == "unsloth":
                # unsloth koristi isti OpenAI-compatible /v1/models endpoint kao LM Studio
                return self._detect_lm_studio_model()
            elif self._provider_name == "ollama":
                return self._detect_ollama_model()
        except Exception as e:
            logging.warning(f"Auto-detect modela nije uspio: {e}")

        # Ako auto-detekcija nije aktivna ili ne uspije, vrati model iz konfiguracije
        return self._model_name if self._model_name else ""

    # -----------------------------------------------------------------------
    # Auto-detekcija modela (P3 - popravak regresije)
    # -----------------------------------------------------------------------

    def _detect_lm_studio_model(self) -> str:
        """Detektira aktivni model iz LM Studio API-ja (GET /v1/models).

        Ekvivalent detektiraj_aktivni_model() iz mamba_voice.py.

        Returns:
            Naziv modela ili prazan string.
        """
        base_url = self._current_provider_cfg.get("apiBase", "http://127.0.0.1:1234")
        # Normaliziraj base_url — ako već sadrži /v1, ne dodaj ga ponovno
        if not base_url.rstrip("/").endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"
        models_url = f"{base_url}/models"
        detect_timeout = self._api_cfg.get("auto_detect_timeout", 5)

        try:
            request = urllib.request.Request(models_url, method="GET", headers=self._dohvati_headers())
            with urllib.request.urlopen(request, timeout=detect_timeout) as response:
                data = json.loads(response.read().decode('utf-8'))
                if data.get("data") and len(data["data"]) > 0:
                    model_id = data["data"][0]["id"]
                    logging.info(f"Auto-detektovan LM Studio model: {model_id}")
                    return model_id
        except Exception as e:
            logging.warning(f"LM Studio auto-detect nije uspio: {e}")
        return ""

    def _detect_ollama_model(self) -> str:
        """Detektira aktivni model iz lokalnog Ollama API-ja (GET /api/tags).

        Returns:
            Naziv modela ili prazan string.
        """
        base_url = self._current_provider_cfg.get("apiBase", "http://127.0.0.1:11434")
        tags_url = f"{base_url}/api/tags"
        detect_timeout = self._api_cfg.get("auto_detect_timeout", 5)

        try:
            request = urllib.request.Request(tags_url, method="GET")
            with urllib.request.urlopen(request, timeout=detect_timeout) as response:
                data = json.loads(response.read().decode('utf-8'))
                if data.get("models") and len(data["models"]) > 0:
                    model_name = data["models"][0]["name"]
                    logging.info(f"Auto-detektovan Ollama model: {model_name}")
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
            "provider": self._provider_name,
            "parametri": "",
            "quantization": "",
            "size": "",
            "context_length": "",
            "raw": None,
        }
        detect_timeout = self._api_cfg.get("auto_detect_timeout", 5)

        try:
            if self._provider_name in ("lmstudio", "unsloth"):
                base_url = self._current_provider_cfg.get("apiBase", "http://127.0.0.1:1234")
                # Normaliziraj base_url — ako već sadrži /v1, ne dodaj ga ponovno
                if not base_url.rstrip("/").endswith("/v1"):
                    base_url = base_url.rstrip("/") + "/v1"
                models_url = f"{base_url}/models"
                request = urllib.request.Request(models_url, method="GET", headers=self._dohvati_headers())
                with urllib.request.urlopen(request, timeout=detect_timeout) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    if data.get("data") and len(data["data"]) > 0:
                        model_info = data["data"][0]
                        detalji["model"] = model_info.get("id", "")
                        detalji["raw"] = model_info
                        detalji["context_length"] = model_info.get("context_length", "")
                        detalji["owned_by"] = model_info.get("owned_by", "")
            elif self._provider_name == "ollama":
                base_url = self._current_provider_cfg.get("apiBase", "http://127.0.0.1:11434")
                tags_url = f"{base_url}/api/tags"
                request = urllib.request.Request(tags_url, method="GET")
                with urllib.request.urlopen(request, timeout=detect_timeout) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    if data.get("models") and len(data["models"]) > 0:
                        # Tražimo detalje za aktivni model, ne prvi s liste
                        model_info = next((m for m in data["models"] if m.get("name") == self._model_name), None)
                        if model_info:
                            detalji["model"] = model_info.get("name", "")
                            detalji["raw"] = model_info
                            details = model_info.get("details", {})
                            detalji["parametri"] = details.get("parameter_size", "")
                            detalji["quantization"] = details.get("quantization_level", "")
                            detalji["size"] = model_info.get("size", "")
                            detalji["context_length"] = details.get("context_length", "")
        except Exception as e:
            logging.warning(f"Dohvat detalja modela nije uspio: {e}")

        return detalji