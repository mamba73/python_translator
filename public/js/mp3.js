/**
 * mp3.js — Logika za Korak 4: TTS sinteza u MP3
 * Autodupliciranje audiobook mape ako već postoji
 * Modal s progress barom i ETA za real-time praćenje TTS sinteze
 * Resume funkcionalnost — nastavak prekinute TTS sinteze
 */

(function () {
  'use strict';

  let files = [];
  let selectedIdx = null;
  let metadataInitialized = false;

  /**
   * Prikazuje metadata formu za odabranu datoteku.
   */
  function showMetadataForm() {
    const container = document.getElementById('metadata-container');
    if (!container) return;

    if (selectedIdx === null || !files[selectedIdx]) {
      container.classList.add('hidden');
      container.innerHTML = '';
      metadataInitialized = false;
      return;
    }

    const d = files[selectedIdx];
    if (!metadataInitialized || container.dataset.relPath !== d.rel_path) {
      container.innerHTML = MetadataForm.generirajHTML();
      container.dataset.relPath = d.rel_path;
      container.classList.remove('hidden');
      MetadataForm.init('metadata-container', d.rel_path);
      MetadataForm.postaviSpremi('metadata-container', d.rel_path);
      metadataInitialized = true;
    }
  }

  // ─── Modal: Progress TTS sinteze ──────────────────────────────────────────
  let modalWs = null;
  let modalReconnectTimer = null;

  function openModal(resume = false) {
    const modal = document.getElementById('tts-modal');
    if (!modal) return;

    // Resetiraj modal
    document.getElementById('tts-modal-title').textContent = resume
      ? '⏯ Nastavak TTS sinteze...'
      : '🎧 TTS sinteza u tijeku...';
    document.getElementById('tts-modal-status').textContent = 'Priprema segmenata...';
    document.getElementById('tts-modal-progress-text').textContent = '0%';
    document.getElementById('tts-modal-progress-details').textContent = 'Segment 0/0';
    document.getElementById('tts-modal-progress-eta').textContent = '';
    document.getElementById('tts-modal-progress-info').textContent = '';
    document.getElementById('tts-modal-progress-bar').style.width = '0%';
    document.getElementById('tts-modal-result').classList.add('hidden');

    modal.classList.remove('hidden');
    modal.classList.add('flex');

    // Spoji se na log stream za real-time progress
    connectModalWS();
  }

  function closeModal() {
    const modal = document.getElementById('tts-modal');
    if (modal) {
      modal.classList.add('hidden');
      modal.classList.remove('flex');
    }
    if (modalWs) {
      modalWs.close();
      modalWs = null;
    }
    clearTimeout(modalReconnectTimer);
  }

  function connectModalWS() {
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${protocol}://${location.host}/stream-logs`;

    modalWs = new WebSocket(url);

    modalWs.onmessage = (evt) => {
      if (evt.data === 'PING') return;
      processModalLog(evt.data);
    };

    modalWs.onclose = () => {
      modalReconnectTimer = setTimeout(connectModalWS, 3000);
    };

    modalWs.onerror = () => {
      // Ignoriraj — reconnect će se dogoditi
    };
  }

  /**
   * Formatira ETA tekst za prikaz u modalu.
   * Uključuje strogu zaštitu protiv negativnih i nelogičnih vrijednosti.
   *
   * @param {string} etaText - Sirovi ETA tekst iz backenda
   * @returns {string} Siguran ETA tekst za prikaz
   */
  function sanitizeEta(etaText) {
    if (!etaText || typeof etaText !== 'string') return '';
    const trimmed = etaText.trim();
    if (!trimmed) return '';

    // Ako backend već šalje "U završnoj fazi" ili "< 1min", prihvati kao jest
    if (trimmed === 'U završnoj fazi' || trimmed === '< 1min') return trimmed;

    // Zaštita: ako tekst sadrži negativne brojeve, zamijeni s "U završnoj fazi"
    if (trimmed.includes('-')) return 'U završnoj fazi';

    // Inače vrati kakav jest (npr. "5m 30s", "1h 15m")
    return trimmed;
  }

  function processModalLog(line) {
    // Progress linija: [Progres] : [██████] 33% | Segment 1/3 | MP3: 001_Ch01_part001.mp3 | ETA: 5m 30s
    if (line.includes('[Progres]')) {
      const percentMatch = line.match(/(\d+)%/);
      const segmentMatch = line.match(/Segment (\d+)\/(\d+)/);
      const mp3Match = line.match(/MP3:\s*(\S+)/);
      // ETA format: "ETA: 5m 30s" ili "ETA: U završnoj fazi" ili "ETA: < 1min"
      const etaMatch = line.match(/ETA:\s*(.+?)(?:\s*\||\s*$)/);

      if (percentMatch) {
        const pct = parseInt(percentMatch[1]);
        document.getElementById('tts-modal-progress-text').textContent = pct + '%';
        document.getElementById('tts-modal-progress-bar').style.width = pct + '%';
      }
      if (segmentMatch) {
        document.getElementById('tts-modal-progress-details').textContent = `Segment ${segmentMatch[1]}/${segmentMatch[2]}`;
      }
      if (mp3Match) {
        document.getElementById('tts-modal-progress-info').textContent = `Generiram: ${mp3Match[1]}`;
      }
      // ETA — s zaštitom za negativne vrijednosti
      const etaEl = document.getElementById('tts-modal-progress-eta');
      if (etaEl) {
        if (etaMatch) {
          const safeEta = sanitizeEta(etaMatch[1]);
          etaEl.textContent = safeEta ? `⏱ ${safeEta}` : '';
        }
        // Ako nema ETA u liniji, ostavi prethodnu vrijednost (ne briši)
      }
      // Status
      document.getElementById('tts-modal-status').textContent = 'TTS sinteza u tijeku...';
    }

    // TTS priprema segmenata
    if (line.includes('[TTS] Priprema segmenata')) {
      document.getElementById('tts-modal-status').textContent = 'Analiziram poglavlja i pripremam segmente...';
    }
    if (line.includes('[TTS] Ukupno segmenata')) {
      const match = line.match(/Ukupno segmenata za sintezu:\s*(\d+)/);
      if (match) {
        document.getElementById('tts-modal-progress-details').textContent = `Segment 0/${match[1]}`;
        document.getElementById('tts-modal-status').textContent = `Pripremljeno ${match[1]} segmenata. Krećem sa sintezom...`;
      }
    }

    // TTS resume poruka
    if (line.includes('[TTS RESUME]')) {
      document.getElementById('tts-modal-status').textContent = 'Nastavljam prekinutu sintezu...';
      const match = line.match(/Nastavljam od segmenta (\d+)\/(\d+)/);
      if (match) {
        document.getElementById('tts-modal-progress-details').textContent = `Segment ${match[1]}/${match[2]}`;
      }
    }

    // Završetak TTS sinteze
    if (line.includes('[TTS] Završeno')) {
      const folderMatch = line.match(/Završeno:\s*(.+)$/);
      if (folderMatch) {
        document.getElementById('tts-modal-folder-name').textContent = folderMatch[1].trim();
      }
      document.getElementById('tts-modal-status').textContent = 'Završeno!';
      document.getElementById('tts-modal-progress-text').textContent = '100%';
      document.getElementById('tts-modal-progress-bar').style.width = '100%';
      document.getElementById('tts-modal-progress-eta').textContent = '';
    }
    if (line.includes('Ukupno generirano') && line.includes('MP3 datoteka')) {
      const match = line.match(/Ukupno generirano (\d+) MP3 datoteka/);
      if (match) {
        document.getElementById('tts-modal-mp3-count').textContent = `Ukupno generirano: ${match[1]} MP3 datoteka`;
        document.getElementById('tts-modal-result').classList.remove('hidden');
        document.getElementById('tts-modal-title').textContent = '✅ TTS sinteza završena';
      }
    }
  }

  async function loadFiles() {
    const tbody = document.getElementById('translated-tbody');
    if (!tbody) return;

    try {
      const res = await fetch('/api/translated-files');
      const data = await res.json();
      files = data.files || [];

      tbody.innerHTML = '';

      if (files.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center py-8 text-gray-500">Nema prevedenih datoteka u work/translated/</td></tr>';
        return;
      }

      files.forEach((d, i) => {
        const testBadge = d.is_test
          ? '<span class="px-2 py-0.5 rounded bg-yellow-900 text-yellow-300 text-xs">TEST</span>'
          : '<span class="px-2 py-0.5 rounded bg-green-900 text-green-300 text-xs">produkcija</span>';

        const tr = document.createElement('tr');
        tr.className = 'border-b border-gray-700 hover:bg-gray-800 transition-colors cursor-pointer';
        tr.dataset.idx = i;
        tr.innerHTML = `
          <td class="py-2 px-3">
            <input type="radio" name="mp3-selection" class="row-rb w-4 h-4 accent-blue-500 cursor-pointer"
              data-idx="${i}">
          </td>
          <td class="py-2 px-3 font-mono text-sm text-gray-200" data-col="name">
            ${escHtml(d.book ? d.book + '/' : '')}${escHtml(d.name)}
          </td>
          <td class="py-2 px-3" data-col="type">${testBadge}</td>
          <td class="py-2 px-3 text-xs text-gray-400" data-col="size">${escHtml(d.size)}</td>
          <td class="py-2 px-3 text-xs text-gray-400 whitespace-nowrap" data-col="modified">${escHtml(d.modified)}</td>
        `;
        tbody.appendChild(tr);

        // Klik na redak aktivira radio
        tr.addEventListener('click', () => {
          const rb = tr.querySelector('.row-rb');
          if (rb) { rb.checked = true; selectedIdx = i; checkAudiobookDir(); showMetadataForm(); }
        });
      });

      document.querySelectorAll('.row-rb').forEach(rb => {
        rb.addEventListener('change', e => {
          selectedIdx = parseInt(e.target.dataset.idx);
          checkAudiobookDir();
          showMetadataForm();
        });
      });

      initSortableTable('translated-table');
    } catch (err) {
      showToast('Greška pri učitavanju: ' + err.message, 'error');
    }
  }

  /**
   * Provjerava postoji li audiobook mapa za odabranu datoteku.
   * Ako postoji, prikazuje "Nastavi TTS" gumb.
   */
  async function checkAudiobookDir() {
    const btnResume = document.getElementById('btn-resume-mp3');
    if (!btnResume || selectedIdx === null) {
      if (btnResume) btnResume.classList.add('hidden');
      return;
    }

    // Audiobook mapa se zove <knjiga>---<autor> u work/audiobooks/
    // Frontend ne zna točnu putanju, ali možemo provjeriti preko API-ja
    // ako postoji endpoint. Za sada, gumb je uvijek vidljiv ako je datoteka
    // odabrana — backend će vratiti 404 ako mapa ne postoji.
    btnResume.classList.remove('hidden');
  }

  /**
   * Pokreće TTS sintezu — novu ili nastavak.
   * @param {boolean} resume - True za resume, False za novu sintezu
   */
  async function startTTS(resume = false) {
    if (selectedIdx === null) {
      showToast('Odaberite datoteku za TTS sintezu.', 'warn');
      return;
    }

    const mode = document.querySelector('input[name="mode"]:checked')?.value || 'separate';
    const d = files[selectedIdx];

    const btn = document.getElementById('btn-generate-mp3');
    const btnResume = document.getElementById('btn-resume-mp3');
    btn.disabled = true;
    btn.textContent = 'TTS sinteza u tijeku...';
    if (btnResume) btnResume.disabled = true;

    // Progress indikator (stari spinner — ostaje za kompatibilnost)
    const progressEl = document.getElementById('tts-progress');
    if (progressEl) progressEl.classList.remove('hidden');

    // Otvori modal s progress barom
    openModal(resume);

    try {
      const res = await fetch('/api/generate-mp3', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rel_path: d.rel_path, mode, resume })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Greška servera');
      }

      const data = await res.json();
      const message = resume
        ? `TTS nastavak završen: ${data.output} (${data.mp3_count} MP3)`
        : `TTS završen: ${data.output} (${data.mp3_count} MP3)`;
      showToast(message, 'info');

      // Ako modal već nije prikazao rezultat (npr. WebSocket linije su propuštene),
      // osvježi ime foldera iz API odgovora
      const folderEl = document.getElementById('tts-modal-folder-name');
      if (folderEl && !folderEl.textContent) {
        folderEl.textContent = data.output;
      }
      const resultEl = document.getElementById('tts-modal-result');
      if (resultEl && resultEl.classList.contains('hidden')) {
        resultEl.classList.remove('hidden');
        document.getElementById('tts-modal-title').textContent = '✅ TTS sinteza završena';
        document.getElementById('tts-modal-status').textContent = 'Završeno!';
        document.getElementById('tts-modal-progress-text').textContent = '100%';
        document.getElementById('tts-modal-progress-bar').style.width = '100%';
        const countEl = document.getElementById('tts-modal-mp3-count');
        if (countEl) countEl.textContent = `Ukupno generirano: ${data.mp3_count} MP3 datoteka`;
      }
    } catch (e) {
      document.getElementById('tts-modal-status').textContent = 'Greška: ' + e.message;
      showToast('Greška: ' + e.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Generiraj MP3 audiobook';
      if (btnResume) btnResume.disabled = false;
      if (progressEl) progressEl.classList.add('hidden');
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    loadFiles();

    // Gumb za novu TTS sintezu
    document.getElementById('btn-generate-mp3')?.addEventListener('click', () => startTTS(false));

    // Gumb za nastavak TTS sinteze (resume)
    document.getElementById('btn-resume-mp3')?.addEventListener('click', () => startTTS(true));

    // Modal event listeners
    document.getElementById('tts-modal-close')?.addEventListener('click', closeModal);
    document.getElementById('tts-modal-close-bottom')?.addEventListener('click', closeModal);
  });

  function escHtml(str) {
    return String(str).replace(/&/g, '&').replace(/</g, '<').replace(/>/g, '>');
  }

})();