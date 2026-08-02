/**
 * mp3.js — Logika za Korak 4: TTS sinteza u MP3
 * Autodupliciranje audiobook mape ako već postoji
 * Modal s progress barom i ETA za real-time praćenje TTS sinteze
 */

(function () {
  'use strict';

  let datoteke = [];
  let odabraniIdx = null;

  // ─── Modal: Progress TTS sinteze ──────────────────────────────────────────
  let modalWs = null;
  let modalReconnectTimer = null;

  function otvoriModal() {
    const modal = document.getElementById('tts-modal');
    if (!modal) return;

    // Resetiraj modal
    document.getElementById('tts-modal-naslov').textContent = '🎧 TTS sinteza u tijeku...';
    document.getElementById('tts-modal-status').textContent = 'Priprema segmenata...';
    document.getElementById('tts-modal-progress-tekst').textContent = '0%';
    document.getElementById('tts-modal-progress-detalji').textContent = 'Segment 0/0';
    document.getElementById('tts-modal-progress-eta').textContent = '';
    document.getElementById('tts-modal-progress-info').textContent = '';
    document.getElementById('tts-modal-progress-bar').style.width = '0%';
    document.getElementById('tts-modal-rezultat').classList.add('hidden');

    modal.classList.remove('hidden');
    modal.classList.add('flex');

    // Spoji se na log stream za real-time progress
    spojiModalWS();
  }

  function zatvoriModal() {
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

  function spojiModalWS() {
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${protocol}://${location.host}/stream-logs`;

    modalWs = new WebSocket(url);

    modalWs.onmessage = (evt) => {
      if (evt.data === 'PING') return;
      obradiModalLog(evt.data);
    };

    modalWs.onclose = () => {
      modalReconnectTimer = setTimeout(spojiModalWS, 3000);
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
  function sanitizirajEta(etaText) {
    if (!etaText || typeof etaText !== 'string') return '';
    const trimmed = etaText.trim();
    if (!trimmed) return '';

    // Ako backend već šalje "U završnoj fazi" ili "< 1min", prihvati kao jest
    if (trimmed === 'U završnoj fazi' || trimmed === '< 1min') return trimmed;

    // Zaštita: ako tekst sadrži negativne brojeve, zamijeni s "U završnoj fazi"
    if (trimmed.includes('-')) return 'U završnoj fazi';

    // Inače vrati kakvo jest (npr. "5m 30s", "1h 15m")
    return trimmed;
  }

  function obradiModalLog(linija) {
    // Progress linija: [Progres] : [██████] 33% | Segment 1/3 | MP3: 001_Ch01_part001.mp3 | ETA: 5m 30s
    if (linija.includes('[Progres]')) {
      const postotakMatch = linija.match(/(\d+)%/);
      const segmentMatch = linija.match(/Segment (\d+)\/(\d+)/);
      const mp3Match = linija.match(/MP3:\s*(\S+)/);
      // ETA format: "ETA: 5m 30s" ili "ETA: U završnoj fazi" ili "ETA: < 1min"
      const etaMatch = linija.match(/ETA:\s*(.+?)(?:\s*\||\s*$)/);

      if (postotakMatch) {
        const pct = parseInt(postotakMatch[1]);
        document.getElementById('tts-modal-progress-tekst').textContent = pct + '%';
        document.getElementById('tts-modal-progress-bar').style.width = pct + '%';
      }
      if (segmentMatch) {
        document.getElementById('tts-modal-progress-detalji').textContent = `Segment ${segmentMatch[1]}/${segmentMatch[2]}`;
      }
      if (mp3Match) {
        document.getElementById('tts-modal-progress-info').textContent = `Generiram: ${mp3Match[1]}`;
      }
      // ETA — s zaštitom za negativne vrijednosti
      const etaEl = document.getElementById('tts-modal-progress-eta');
      if (etaEl) {
        if (etaMatch) {
          const safeEta = sanitizirajEta(etaMatch[1]);
          etaEl.textContent = safeEta ? `⏱ ${safeEta}` : '';
        }
        // Ako nema ETA u liniji, ostavi prethodnu vrijednost (ne briši)
      }
      // Status
      document.getElementById('tts-modal-status').textContent = 'TTS sinteza u tijeku...';
    }

    // TTS priprema segmenata
    if (linija.includes('[TTS] Priprema segmenata')) {
      document.getElementById('tts-modal-status').textContent = 'Analiziram poglavlja i pripremam segmente...';
    }
    if (linija.includes('[TTS] Ukupno segmenata')) {
      const match = linija.match(/Ukupno segmenata za sintezu:\s*(\d+)/);
      if (match) {
        document.getElementById('tts-modal-progress-detalji').textContent = `Segment 0/${match[1]}`;
        document.getElementById('tts-modal-status').textContent = `Pripremljeno ${match[1]} segmenata. Krećem s sintezom...`;
      }
    }

    // Završetak TTS sinteze
    if (linija.includes('[TTS] Završeno')) {
      const folderMatch = linija.match(/Završeno:\s*(.+)$/);
      if (folderMatch) {
        document.getElementById('tts-modal-ime-foldera').textContent = folderMatch[1].trim();
      }
      document.getElementById('tts-modal-status').textContent = 'Završeno!';
      document.getElementById('tts-modal-progress-tekst').textContent = '100%';
      document.getElementById('tts-modal-progress-bar').style.width = '100%';
      document.getElementById('tts-modal-progress-eta').textContent = '';
    }
    if (linija.includes('Ukupno generirano') && linija.includes('MP3 datoteka')) {
      const match = linija.match(/Ukupno generirano (\d+) MP3 datoteka/);
      if (match) {
        document.getElementById('tts-modal-broj-mp3').textContent = `Ukupno generirano: ${match[1]} MP3 datoteka`;
        document.getElementById('tts-modal-rezultat').classList.remove('hidden');
        document.getElementById('tts-modal-naslov').textContent = '✅ TTS sinteza završena';
      }
    }
  }

  async function ucitajDatoteke() {
    const tbody = document.getElementById('translated-tbody');
    if (!tbody) return;

    try {
      const res = await fetch('/api/translated-datoteke');
      const data = await res.json();
      datoteke = data.datoteke || [];

      tbody.innerHTML = '';

      if (datoteke.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center py-8 text-gray-500">Nema prevedenih datoteka u work/translated/</td></tr>';
        return;
      }

      datoteke.forEach((d, i) => {
        const testBadge = d.je_test
          ? '<span class="px-2 py-0.5 rounded bg-yellow-900 text-yellow-300 text-xs">TEST</span>'
          : '<span class="px-2 py-0.5 rounded bg-green-900 text-green-300 text-xs">produkcija</span>';

        const tr = document.createElement('tr');
        tr.className = 'border-b border-gray-700 hover:bg-gray-800 transition-colors cursor-pointer';
        tr.dataset.idx = i;
        tr.innerHTML = `
          <td class="py-2 px-3">
            <input type="radio" name="mp3-odabir" class="row-rb w-4 h-4 accent-blue-500 cursor-pointer"
              data-idx="${i}">
          </td>
          <td class="py-2 px-3 font-mono text-sm text-gray-200" data-col="ime">
            ${escHtml(d.knjiga ? d.knjiga + '/' : '')}${escHtml(d.ime)}
          </td>
          <td class="py-2 px-3" data-col="tip">${testBadge}</td>
          <td class="py-2 px-3 text-xs text-gray-400" data-col="velicina">${escHtml(d.velicina)}</td>
          <td class="py-2 px-3 text-xs text-gray-400 whitespace-nowrap" data-col="izmijenjeno">${escHtml(d.izmijenjeno)}</td>
        `;
        tbody.appendChild(tr);

        // Klik na redak aktivira radio
        tr.addEventListener('click', () => {
          const rb = tr.querySelector('.row-rb');
          if (rb) { rb.checked = true; odabraniIdx = i; }
        });
      });

      document.querySelectorAll('.row-rb').forEach(rb => {
        rb.addEventListener('change', e => {
          odabraniIdx = parseInt(e.target.dataset.idx);
        });
      });

      initSortableTable('translated-table');
    } catch (err) {
      showToast('Greška pri učitavanju: ' + err.message, 'error');
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    ucitajDatoteke();

    document.getElementById('btn-generiraj-mp3')?.addEventListener('click', async () => {
      if (odabraniIdx === null) {
        showToast('Odaberite datoteku za TTS sintezu.', 'warn');
        return;
      }

      const nacin = document.querySelector('input[name="nacin"]:checked')?.value || 'zasebne';
      const d = datoteke[odabraniIdx];

      const btn = document.getElementById('btn-generiraj-mp3');
      btn.disabled = true;
      btn.textContent = 'TTS sinteza u tijeku...';

      // Progress indikator (stari spinner — ostaje za kompatibilnost)
      const progressEl = document.getElementById('tts-progress');
      if (progressEl) progressEl.classList.remove('hidden');

      // Otvori modal s progress barom
      otvoriModal();

      try {
        const res = await fetch('/api/generiraj-mp3', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ rel_path: d.rel_path, nacin })
        });

        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Greška servera');
        }

        const data = await res.json();
        showToast(`TTS završen: ${data.izlaz}`, 'info');

        // Ako modal već nije prikazao rezultat (npr. WebSocket linije su propuštene),
        // osvježi ime foldera iz API odgovora
        const folderEl = document.getElementById('tts-modal-ime-foldera');
        if (folderEl && !folderEl.textContent) {
          folderEl.textContent = data.izlaz;
        }
        const rezEl = document.getElementById('tts-modal-rezultat');
        if (rezEl && rezEl.classList.contains('hidden')) {
          rezEl.classList.remove('hidden');
          document.getElementById('tts-modal-naslov').textContent = '✅ TTS sinteza završena';
          document.getElementById('tts-modal-status').textContent = 'Završeno!';
          document.getElementById('tts-modal-progress-tekst').textContent = '100%';
          document.getElementById('tts-modal-progress-bar').style.width = '100%';
        }
      } catch (e) {
        document.getElementById('tts-modal-status').textContent = 'Greška: ' + e.message;
        showToast('Greška: ' + e.message, 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Generiraj MP3 audiobook';
        if (progressEl) progressEl.classList.add('hidden');
      }
    });

    // Modal event listeners
    document.getElementById('tts-modal-zatvori')?.addEventListener('click', zatvoriModal);
    document.getElementById('tts-modal-zatvori-dno')?.addEventListener('click', zatvoriModal);
  });

  function escHtml(str) {
    return String(str).replace(/&/g, '&').replace(/</g, '<').replace(/>/g, '>');
  }

})();