"""
app/tts_engine.py — TTS sinteza u MP3 sa segmentacijom
Ref: doc/README_TechDoc.md §10
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any
from datetime import datetime

import edge_tts
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TCOM

from app.file_manager import FileManager
from app.utils import prikazi_progres
from app.metadata import generate_lrc_file, generate_metadata_file, split_sentences, estimate_duration


class TTSEngine:
    """TTS engine za generiranje MP3 datoteka s edge-tts."""

    def __init__(self, config: dict[str, Any], file_manager: FileManager) -> None:
        self._cfg = config
        self._fm = file_manager
        self._tts_cfg = config.get("tts", {})
        self._segment_cfg = self._tts_cfg.get("segment", {})

    def izracunaj_segmente(self, recenice: list[str]) -> list[list[str]]:
        """Pre-calculation algoritam za ravnomjernu segmentaciju.

        Args:
            recenice: Lista rečenica iz poglavlja.

        Returns:
            Lista segmenata, svaki segment je lista rečenica.
        """
        if not recenice:
            return []

        soft_limit = self._segment_cfg.get("word_limit_soft", 500)
        hard_limit = self._segment_cfg.get("word_limit_hard", 600)

        # Prebroji riječi po rečenici
        rijeci_po_recenici = [len(r.split()) for r in recenice]
        ukupno_rijeci = sum(rijeci_po_recenici)

        # Izračunaj broj segmenata i target po segmentu
        n_segmenata = max(1, (ukupno_rijeci + soft_limit - 1) // soft_limit)  # ceil
        target = ukupno_rijeci / n_segmenata

        segmenti = []
        trenutni_segment = []
        trenutni_zbroj = 0

        for i, recenica in enumerate(recenice):
            rijeci_u_recenici = rijeci_po_recenici[i]

            # Ako dodavanje ove rečenice ne bi premašilo hard limit
            if trenutni_zbroj + rijeci_u_recenici <= hard_limit:
                trenutni_segment.append(recenica)
                trenutni_zbroj += rijeci_u_recenici

                # Ako smo dosegli target, zatvori segment (osim ako je zadnja rečenica)
                if trenutni_zbroj >= target and i < len(recenice) - 1:
                    segmenti.append(trenutni_segment)
                    trenutni_segment = []
                    trenutni_zbroj = 0
            else:
                # Premašili bismo hard limit - zatvori trenutni segment
                if trenutni_segment:
                    segmenti.append(trenutni_segment)
                trenutni_segment = [recenica]
                trenutni_zbroj = rijeci_u_recenici

        # Dodaj zadnji segment ako ima sadržaja
        if trenutni_segment:
            segmenti.append(trenutni_segment)

        # Spoji zadnja dva segmenta ako je zadnji premali
        min_segment_words = self._segment_cfg.get("min_segment_words", 50)
        if len(segmenti) > 1:
            zadnji_rijeci = sum(len(r.split()) for r in segmenti[-1])
            if zadnji_rijeci < min_segment_words:
                segmenti[-2].extend(segmenti[-1])
                segmenti.pop()

        return segmenti

    async def generiraj_segment_mp3(self, tekst: str, putanja: Path,
                                   chapter_num: int, part_num: int,
                                   book_title: str, author: str) -> None:
        """Generira MP3 za jedan segment koristeći edge-tts.

        Args:
            tekst: Tekst segmenta.
            putanja: Putanja za spremanje MP3.
            chapter_num: Broj poglavlja.
            part_num: Broj dijela unutar poglavlja.
            book_title: Naslov knjige za ID3.
            author: Autor za ID3.
        """
        # Osiguraj da roditeljski direktorij postoji prije spremanja
        putanja.parent.mkdir(parents=True, exist_ok=True)

        # Odredi glas na temelju sadržaja (dijalog vs naracija)
        voice, rate, pitch = self._odredi_glas(tekst)

        communicate = edge_tts.Communicate(tekst, voice, rate=rate, pitch=pitch)
        await communicate.save(str(putanja))

        # Provjeri da je edge-tts uspio zapisati MP3 (ne samo praznu datoteku)
        if not putanja.exists() or putanja.stat().st_size == 0:
            raise RuntimeError(
                f"edge-tts nije uspio zapisati MP3: {putanja} "
                f"(postoji={putanja.exists()}, "
                f"veličina={putanja.stat().st_size if putanja.exists() else 0}B)"
            )

        # Dodaj ID3 tagove
        self._upisi_id3_tagove(putanja, chapter_num, part_num, book_title, author)

    def _odredi_glas(self, tekst: str) -> tuple[str, str, str]:
        """Odredi glas, brzinu i visinu na temelju teksta.

        Args:
            tekst: Tekst za analizu.

        Returns:
            (voice, rate, pitch)
        """
        narrator_cfg = self._tts_cfg.get("narrator", {})
        dialog_cfg = self._tts_cfg.get("dialog", {})
        dramatic_cfg = self._tts_cfg.get("dramatic_mode", {})

        # Default narator
        voice = narrator_cfg.get("voice", "hr-HR-SreckoNeural")
        rate = narrator_cfg.get("rate", "+0%")
        pitch = narrator_cfg.get("pitch", "+0Hz")

        # Detekcija dijaloga
        if dialog_cfg.get("use_different_voice", True):
            navodnici = tekst.count('"')
            if navodnici >= 2:
                voice = dialog_cfg.get("voice", "hr-HR-GabrijelaNeural")
                rate = dialog_cfg.get("rate", "+")

        # Dramatski mod
        if dramatic_cfg.get("enabled", True):
            keywords = dramatic_cfg.get("keywords_anxious", [])
            if any(kw.lower() in tekst.lower() for kw in keywords):
                rate = dramatic_cfg.get("rate_modifier_anxious", "+15%")

        return voice, rate, pitch

    def _upisi_id3_tagove(self, putanja: Path, chapter_num: int, part_num: int,
                         book_title: str, author: str) -> None:
        """Upisuje ID3 metapodatke u MP3 datoteku.

        Args:
            putanja: Putanja do MP3 datoteke.
            chapter_num: Broj poglavlja.
            part_num: Broj dijela.
            book_title: Naslov knjige.
            author: Autor knjige.
        """
        # Provjeri da datoteka postoji i nije prazna — edge-tts mora biti zapisao MP3
        if not putanja.exists() or putanja.stat().st_size == 0:
            msg = (f"MP3 datoteka nije ispravno zapisana od edge-tts: {putanja} "
                   f"(postoji={putanja.exists()}, "
                   f"veličina={putanja.stat().st_size if putanja.exists() else 0}B)")
            logging.error(msg)
            raise RuntimeError(msg)

        try:
            audio = MP3(putanja, ID3=ID3)

            # Kreiraj ID3 tag ako ne postoji
            if audio.tags is None:
                audio.add_tags()

            # Title: Chapter X — Part Y
            title = f"Chapter {chapter_num} — Part {part_num}"
            audio.tags.add(TIT2(encoding=3, text=title))

            # Artist: Author
            audio.tags.add(TPE1(encoding=3, text=author))

            # Album: Book Title
            audio.tags.add(TALB(encoding=3, text=book_title))

            # Track: Globalni broj
            global_track = (chapter_num - 1) * 100 + part_num
            audio.tags.add(TRCK(encoding=3, text=str(global_track)))

            # Comment: Generator info
            version = self._cfg.get("project", {}).get("version", "0.4.0")
            comment = f"Generated by Dynamic Book Translator v{version}"
            audio.tags.add(TCOM(encoding=3, text=comment))

            audio.save()
        except Exception as e:
            logging.warning(f"Neuspješno pisanje ID3 tagova: {e}")

    async def generiraj_audiobook(self, tekst: str, output_dir: Path,
                                  book_title: str, book_config: dict[str, Any] | None = None,
                                  merge_single: bool = False,
                                  resume_from: int = 0) -> list[Path]:
        """Orkestracija: segmenti → MP3 → ID3 s resume podrškom.

        Resume logika (ekvivalent prijevodu): ako output_dir već sadrži MP3
        datoteke, nastavlja od mjesta gdje je stalo — preskače već generirane
        segmente i dodaje samo nove. Broj postojećih MP3 datoteka određuje
        resume_from indeks.

        Args:
            tekst: Cijeli tekst knjige.
            output_dir: Direktorij za spremanje MP3.
            book_title: Naslov knjige.
            book_config: Per-book konfiguracija (za author i TTS postavke).
            merge_single: Ako True, spaja sve segmente u jednu MP3 datoteku.
            resume_from: Indeks segmenta od kojeg se nastavlja (0 = od početka).
                Ako je 0, automatski se detektira iz postojećih MP3 datoteka.

        Returns:
            Lista putanja do generiranih MP3 datoteka.
        """
        author = (book_config or {}).get("author", "Unknown")

        # Podijeli na poglavlja (jednostavna heuristika - po \n\n\n)
        poglavlja_tekst = tekst.split('\n\n\n')

        # Direktorij mora biti unaprijed osiguran od pozivatelja (menu)
        # s unique suffix logikom — ovdje samo kreiramo ako nedostaje,
        # bez ponovnog sufiksiranja (izbjegava dvostruki _001).
        output_dir = self._fm.ensure_dir(output_dir, suffix_if_exists=False)

        # Pre-izračunaj ukupan broj segmenata za progress bar + ETA
        # (potrebno je segmentirati sva poglavlja unaprijed)
        logging.info("[TTS] Priprema segmenata — analiziram poglavlja...")
        sva_poglavlja_segmenti: list[tuple[int, list[list[str]]]] = []
        ukupno_segmenata = 0
        for ch_idx, poglavlje in enumerate(poglavlja_tekst, 1):
            recenice = re.split(r'(?<=[.!?])\s+', poglavlje)
            segmenti = self.izracunaj_segmente(recenice)
            sva_poglavlja_segmenti.append((ch_idx, segmenti))
            ukupno_segmenata += len(segmenti)
        logging.info(f"[TTS] Ukupno segmenata za sintezu: {ukupno_segmenata}")

        # Resume logika: detektiraj postojeće MP3 datoteke u output_dir
        # i nastavi od mjesta gdje je stalo (ekvivalent prijevodu).
        postojece_mp3 = sorted(output_dir.glob("*.mp3")) if output_dir.exists() else []
        if resume_from <= 0 and postojece_mp3:
            resume_from = len(postojece_mp3)
            postotak_resume = int(resume_from / ukupno_segmenata * 100) if ukupno_segmenata > 0 else 0
            logging.info(
                f"[TTS RESUME] Nastavljam od segmenta {resume_from}/{ukupno_segmenata} "
                f"(prethodno generirano {postotak_resume}%)."
            )
        elif resume_from > 0:
            logging.info(f"[TTS RESUME] Nastavljam od segmenta {resume_from}/{ukupno_segmenata}")

        global_counter = 1
        obradeno = 0
        sve_mp3_putanje = list(postojece_mp3)  # Učitaj postojeće u listu
        segment_metadata: list[dict[str, Any]] = []  # Za metadata.yaml

        for ch_idx, segmenti in sva_poglavlja_segmenti:
            for part_idx, segment in enumerate(segmenti, 1):
                # Preskoči već generirane segmente pri resume-u
                if obradeno < resume_from:
                    obradeno += 1
                    global_counter += 1
                    continue

                # Imenovanje: NNN_ChXX_partXXX.mp3
                filename = f"{global_counter:03d}_Ch{ch_idx:02d}_part{part_idx:03d}.mp3"
                mp3_path = output_dir / filename

                segment_tekst = ' '.join(segment)
                try:
                    await self.generiraj_segment_mp3(
                        segment_tekst, mp3_path, ch_idx, part_idx, book_title, author
                    )
                    sve_mp3_putanje.append(mp3_path)

                    # Generiraj LRC datoteku za sinkronizirani prikaz teksta
                    recenice = split_sentences(segment_tekst)
                    lrc_path = generate_lrc_file(mp3_path, recenice)

                    # Izmjeri stvarno trajanje MP3 za metadata.yaml
                    duration = 0.0
                    try:
                        audio = MP3(mp3_path)
                        duration = float(audio.info.length) if audio.info else 0.0
                    except Exception:
                        duration = estimate_duration(segment_tekst)

                    # Spremi metapodatke segmenta
                    segment_metadata.append({
                        "file": filename,
                        "chapter": ch_idx,
                        "part": part_idx,
                        "track": global_counter,
                        "duration": duration,
                        "lrc": lrc_path.name if lrc_path.exists() else "",
                    })

                    logging.info(f"Generiran MP3: {filename} (LRC: {lrc_path.name})")
                except Exception as seg_err:
                    # Greška u jednom segmentu ne smije srušiti cijelu knjigu —
                    # logiraj, ukloni eventualnu praznu datoteku i nastavi.
                    logging.error(
                        f"Greška pri generiranju segmenta {filename}: {seg_err}"
                    )
                    if mp3_path.exists() and mp3_path.stat().st_size == 0:
                        try:
                            mp3_path.unlink()
                        except OSError:
                            pass
                global_counter += 1
                obradeno += 1

                # Progress bar s ETA — koristi isti [Progres] format kao i
                # prijevod, tako da WebSocket /stream-logs šalje linije koje
                # frontend modal parsira i prikazuje u realnom vremenu.
                dodatno = f"MP3: {filename}"
                prikazi_progres(
                    obradeno, ukupno_segmenata,
                    f"Segment {obradeno}/{ukupno_segmenata}",
                    dodatno
                )

        # Ako je merge_single, spoji sve MP3 u jedan
        if merge_single and len(sve_mp3_putanje) > 1:
            merged_path = output_dir / f"{global_counter:03d}_merged.mp3"
            # Spajanje MP3 datoteka putem ffmpeg-a ili drugog alata
            logging.info(f"Spajanje {len(sve_mp3_putanje)} MP3 datoteka u jedan.")
            # TODO: Implementirati spajanje MP3 (npr. pomoću pydub ili ffmpeg)
            # Za sada vraćamo sve MP3 putanje
            logging.warning("Merge single nije implementiran — vraćam sve segmente.")

        # Generiraj metadata.yaml s popisom svih segmenata, poglavlja i trajanja
        if segment_metadata:
            book_cfg = book_config or {}
            generate_metadata_file(
                audiobook_dir=output_dir,
                book_title=book_title,
                author=author,
                segments=segment_metadata,
                year=book_cfg.get("year", ""),
                language=book_cfg.get("language", "hr"),
                source_file=book_cfg.get("original_file", ""),
            )

        logging.info(f"Ukupno generirano {len(sve_mp3_putanje)} MP3 datoteka.")
        return sve_mp3_putanje



