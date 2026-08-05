/**
 * konverzija.js — Logika za Korak 1: Konverzija dokumenata
 */

(function () {
  'use strict';

  let files = [];
  let selectedSet = new Set();
  let metadataInitialized = false;

  /**
   * Prikazuje metadata formu za prvu odabranu datoteku.
   * Ako je odabrano više datoteka, forma se odnosi na prvu.
   */
  function showMetadataForm() {
    const container = document.getElementById('metadata-container');
    if (!container) return;

    if (selectedSet.size === 0) {
      container.classList.add('hidden');
      container.innerHTML = '';
      metadataInitialized = false;
      return;
    }

    // Prva odabrana datoteka
    const idx = Array.from(selectedSet).sort((a, b) => a - b)[0];
    const d = files[idx];
    if (!d) return;

    // Ako se datoteka promijenila, re-generiraj formu
    if (!metadataInitialized || container.dataset.relPath !== d.rel_path) {
      if (typeof MetadataForm === 'undefined') {
        console.error('[konverzija.js] MetadataForm nije učitan! Provjeri metadata.js.');
        return;
      }
      container.innerHTML = MetadataForm.generirajHTML();
      container.dataset.relPath = d.rel_path;
      container.classList.remove('hidden');
      MetadataForm.init('metadata-container', d.rel_path);
      MetadataForm.postaviSpremi('metadata-container', d.rel_path);
      metadataInitialized = true;
      console.log('[konverzija.js] Metadata forma prikazana za:', d.rel_path);
    }
  }

  async function loadFiles() {
    const tbody = document.getElementById('input-tbody');
    const emptyMsg = document.getElementById('empty-msg');
    if (!tbody) return;

    try {
      const res = await fetch('/api/input-files');
      const data = await res.json();
      files = data.files || [];

      tbody.innerHTML = '';

      if (files.length === 0) {
        if (emptyMsg) emptyMsg.classList.remove('hidden');
        return;
      }
      if (emptyMsg) emptyMsg.classList.add('hidden');

      files.forEach((d, i) => {
        const tr = document.createElement('tr');
        tr.className = 'border-b border-gray-700 hover:bg-gray-800 transition-colors';
        tr.innerHTML = `
          <td class="py-2 px-3">
            <input type="checkbox" class="row-cb w-4 h-4 accent-blue-500 cursor-pointer"
              data-idx="${i}" ${selectedSet.has(i) ? 'checked' : ''}>
          </td>
          <td class="py-2 px-3 font-mono text-sm text-gray-200" data-col="name">${escHtml(d.name)}</td>
          <td class="py-2 px-3 text-xs text-gray-400" data-col="type">
            <span class="px-2 py-0.5 rounded bg-blue-900 text-blue-300">${escHtml(d.type)}</span>
          </td>
          <td class="py-2 px-3 text-xs text-gray-400" data-col="size">${escHtml(d.size)}</td>
          <td class="py-2 px-3 text-xs text-gray-400 whitespace-nowrap" data-col="modified">${escHtml(d.modified)}</td>
        `;
        tbody.appendChild(tr);
      });

      // Checkboxes
      document.querySelectorAll('.row-cb').forEach(cb => {
        cb.addEventListener('change', e => {
          const idx = parseInt(e.target.dataset.idx);
          if (e.target.checked) selectedSet.add(idx);
          else selectedSet.delete(idx);
          updateSelectedCount();
          showMetadataForm();
        });
      });

      initSortableTable('input-table');
    } catch (err) {
      showToast('Greška pri učitavanju datoteka: ' + err.message, 'error');
    }
  }

  function updateSelectedCount() {
    const el = document.getElementById('selected-count');
    if (el) el.textContent = `Odabrano: ${selectedSet.size}`;
  }

  // ─── Modal: Progress konverzije ────────────────────────────────────────────
  let modalWs = null;
  let modalReconnectTimer = null;

  function openConversionModal() {
    const modal = document.getElementById('conversion-modal');
    if (!modal) return;

    // Resetiraj modal
    document.getElementById('conversion-modal-title').textContent = '🔄 Konverzija u tijeku...';
    document.getElementById('conversion-modal-status').textContent = 'Priprema datoteka...';
    document.getElementById('conversion-modal-progress-text').textContent = '0%';
    document.getElementById('conversion-modal-progress-details').textContent = 'Datoteka 0/0';
    document.getElementById('conversion-modal-progress-eta').textContent = '';
    document.getElementById('conversion-modal-progress-bar').style.width = '0%';
    document.getElementById('conversion-modal-result').classList.add('hidden');

    modal.classList.remove('hidden');
    modal.classList.add('flex');

    // Spoji se na log stream za real-time progress
    connectConversionModalWS();
  }

  function closeConversionModal() {
    const modal = document.getElementById('conversion-modal');
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

  function connectConversionModalWS() {
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${protocol}://${location.host}/stream-logs`;

    modalWs = new WebSocket(url);

    modalWs.onmessage = (evt) => {
      if (evt.data === 'PING') return;
      processConversionModalLog(evt.data);
    };

    modalWs.onclose = () => {
      modalReconnectTimer = setTimeout(connectConversionModalWS, 3000);
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

  function processConversionModalLog(line) {
    // Progress linija: [Progres] : [██████] 33% | Datoteka 1/3 | ETA: 5m 30s
    if (line.includes('[Progres]')) {
      const percentMatch = line.match(/(\d+)%/);
      const fileMatch = line.match(/Datoteka (\d+)\/(\d+)/);
      const etaMatch = line.match(/ETA:\s*(.+?)(?:\s*\||\s*$)/);

      if (percentMatch) {
        const pct = parseInt(percentMatch[1]);
        document.getElementById('conversion-modal-progress-text').textContent = pct + '%';
        document.getElementById('conversion-modal-progress-bar').style.width = pct + '%';
      }
      if (fileMatch) {
        document.getElementById('conversion-modal-progress-details').textContent = `Datoteka ${fileMatch[1]}/${fileMatch[2]}`;
      }
      // ETA — s zaštitom za negativne vrijednosti
      const etaEl = document.getElementById('conversion-modal-progress-eta');
      if (etaEl) {
        if (etaMatch) {
          const safeEta = sanitizeEta(etaMatch[1]);
          etaEl.textContent = safeEta ? `⏱ ${safeEta}` : '';
        }
      }
      // Status
      document.getElementById('conversion-modal-status').textContent = 'Konverzija u tijeku...';
    }

    // Završetak konverzije
    if (line.includes('[KONVERZIJA] Završeno')) {
      document.getElementById('conversion-modal-status').textContent = 'Završeno!';
      document.getElementById('conversion-modal-progress-text').textContent = '100%';
      document.getElementById('conversion-modal-progress-bar').style.width = '100%';
      document.getElementById('conversion-modal-progress-eta').textContent = '';
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    loadFiles();

    // Odaberi sve
    document.getElementById('select-all')?.addEventListener('click', () => {
      selectedSet = new Set(files.map((_, i) => i));
      document.querySelectorAll('.row-cb').forEach(cb => cb.checked = true);
      updateSelectedCount();
      showMetadataForm();
    });

    // Poništi odabir
    document.getElementById('select-none')?.addEventListener('click', () => {
      selectedSet.clear();
      document.querySelectorAll('.row-cb').forEach(cb => cb.checked = false);
      updateSelectedCount();
      showMetadataForm();
    });

    // Gumb Konvertiraj
    document.getElementById('btn-convert')?.addEventListener('click', async () => {
      if (selectedSet.size === 0) {
        showToast('Odaberite barem jednu datoteku.', 'warn');
        return;
      }

      const format = document.querySelector('input[name="format"]:checked')?.value || 'txt';
      const selectedList = Array.from(selectedSet).map(i => files[i].rel_path);

      const btn = document.getElementById('btn-convert');
      btn.disabled = true;
      btn.textContent = 'Konverzija u tijeku...';

      // Otvori modal s progress barom
      openConversionModal();

      try {
        const res = await fetch('/api/convert', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ files: selectedList, format })
        });
        const data = await res.json();

        let ok = 0, err = 0;
        (data.results || []).forEach(r => {
          if (r.status === 'ok') ok++;
          else err++;
        });

        // Prikaži rezultat u modalu
        document.getElementById('conversion-modal-summary').textContent = 
          `Uspješno: ${ok} datoteka${err > 0 ? `, Greške: ${err}` : ''}`;
        document.getElementById('conversion-modal-result').classList.remove('hidden');
        document.getElementById('conversion-modal-title').textContent = '✅ Konverzija završena';

        showToast(`Konverzija završena: ${ok} ok, ${err} greška.`, err > 0 ? 'warn' : 'info');
        await loadFiles();
      } catch (e) {
        document.getElementById('conversion-modal-status').textContent = 'Greška: ' + e.message;
        showToast('Greška: ' + e.message, 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Pokreni konverziju';
      }
    });

    // Modal event listeners
    document.getElementById('conversion-modal-close')?.addEventListener('click', closeConversionModal);
    document.getElementById('conversion-modal-close-bottom')?.addEventListener('click', closeConversionModal);
  });

  function escHtml(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

})();