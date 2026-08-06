/**
 * ciscenje.js — Logika za Korak 2: Čišćenje i [fixed] priprema
 * Prikazuje SVE datoteke uključujući _001, _002 sufikse
 */

(function () {
  'use strict';

  let files = [];
  let selectedSet = new Set();
  let metadataInitialized = false;

  /**
   * Prikazuje metadata formu za prvu odabranu datoteku.
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

    const idx = Array.from(selectedSet).sort((a, b) => a - b)[0];
    const d = files[idx];
    if (!d) return;

    if (!metadataInitialized || container.dataset.relPath !== d.rel_path) {
      if (typeof MetadataForm === 'undefined') {
        console.error('[ciscenje.js] MetadataForm nije učitan!');
        return;
      }
      container.innerHTML = MetadataForm.generirajHTML();
      container.dataset.relPath = d.rel_path;
      container.classList.remove('hidden');
      MetadataForm.init('metadata-container', d.rel_path);
      MetadataForm.postaviSpremi('metadata-container', d.rel_path);
      metadataInitialized = true;
    }
  }

  async function loadFiles() {
    const tbody = document.getElementById('output-tbody');
    if (!tbody) return;

    try {
      const res = await fetch('/api/output-files');
      const data = await res.json();
      files = data.files || [];

      tbody.innerHTML = '';

      if (files.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center py-8 text-gray-500">Nema datoteka u work/output/</td></tr>';
        return;
      }

      files.forEach((d, i) => {
        const fixedBadge = d.is_fixed
          ? '<span class="px-2 py-0.5 rounded bg-green-900 text-green-300 text-xs">[fixed]</span>'
          : '<span class="px-2 py-0.5 rounded bg-gray-700 text-gray-400 text-xs">sirova</span>';

        const tr = document.createElement('tr');
        tr.className = 'border-b border-gray-700 hover:bg-gray-800 transition-colors';
        tr.innerHTML = `
          <td class="py-2 px-3">
            <input type="checkbox" class="row-cb w-4 h-4 accent-blue-500 cursor-pointer"
              data-idx="${i}" ${d.is_fixed ? 'disabled title="[fixed] datoteka se ne čisti ponovo"' : ''}>
          </td>
          <td class="py-2 px-3 font-mono text-sm text-gray-200" data-col="name">
            ${escHtml(d.book ? d.book + '/' : '')}${escHtml(d.name)}
          </td>
          <td class="py-2 px-3" data-col="status">${fixedBadge}</td>
          <td class="py-2 px-3 text-xs text-gray-400" data-col="size">${escHtml(d.size)}</td>
          <td class="py-2 px-3 text-xs text-gray-400 whitespace-nowrap" data-col="modified">${escHtml(d.modified)}</td>
        `;
        tbody.appendChild(tr);
      });

      document.querySelectorAll('.row-cb:not(:disabled)').forEach(cb => {
        cb.addEventListener('change', e => {
          const idx = parseInt(e.target.dataset.idx);
          if (e.target.checked) selectedSet.add(idx);
          else selectedSet.delete(idx);
          updateSelectedCount();
          showMetadataForm();
        });
      });

      initSortableTable('output-table');
    } catch (err) {
      showToast('Greška pri učitavanju: ' + err.message, 'error');
    }
  }

  function updateSelectedCount() {
    const el = document.getElementById('selected-count');
    if (el) el.textContent = `Odabrano: ${selectedSet.size}`;
  }

  // ─── Modal: Progress čišćenja ──────────────────────────────────────────────
  let modalWs = null;
  let modalReconnectTimer = null;

  function openCleaningModal() {
    const modal = document.getElementById('cleaning-modal');
    if (!modal) return;

    // Resetiraj modal
    document.getElementById('cleaning-modal-title').textContent = '🧹 Čišćenje u tijeku...';
    document.getElementById('cleaning-modal-status').textContent = 'Priprema datoteka...';
    document.getElementById('cleaning-modal-progress-text').textContent = '0%';
    document.getElementById('cleaning-modal-progress-details').textContent = 'Datoteka 0/0';
    document.getElementById('cleaning-modal-progress-eta').textContent = '';
    document.getElementById('cleaning-modal-progress-bar').style.width = '0%';
    document.getElementById('cleaning-modal-result').classList.add('hidden');

    modal.classList.remove('hidden');
    modal.classList.add('flex');

    // Spoji se na log stream za real-time progress
    connectCleaningModalWS();
  }

  function closeCleaningModal() {
    const modal = document.getElementById('cleaning-modal');
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

  function connectCleaningModalWS() {
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${protocol}://${location.host}/stream-logs`;

    modalWs = new WebSocket(url);

    modalWs.onmessage = (evt) => {
      if (evt.data === 'PING') return;
      processCleaningModalLog(evt.data);
    };

    modalWs.onclose = () => {
      modalReconnectTimer = setTimeout(connectCleaningModalWS, 3000);
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

  function processCleaningModalLog(line) {
    // Progress linija: [Progres] : [██████] 33% | Datoteka 1/3 | ETA: 5m 30s
    if (line.includes('[Progres]')) {
      const percentMatch = line.match(/(\d+)%/);
      const fileMatch = line.match(/Datoteka (\d+)\/(\d+)/);
      const etaMatch = line.match(/ETA:\s*(.+?)(?:\s*\||\s*$)/);

      if (percentMatch) {
        const pct = parseInt(percentMatch[1]);
        document.getElementById('cleaning-modal-progress-text').textContent = pct + '%';
        document.getElementById('cleaning-modal-progress-bar').style.width = pct + '%';
      }
      if (fileMatch) {
        document.getElementById('cleaning-modal-progress-details').textContent = `Datoteka ${fileMatch[1]}/${fileMatch[2]}`;
      }
      // ETA — s zaštitom za negativne vrijednosti
      const etaEl = document.getElementById('cleaning-modal-progress-eta');
      if (etaEl) {
        if (etaMatch) {
          const safeEta = sanitizeEta(etaMatch[1]);
          etaEl.textContent = safeEta ? `⏱ ${safeEta}` : '';
        }
      }
      // Status
      document.getElementById('cleaning-modal-status').textContent = 'Čišćenje u tijeku...';
    }

    // Završetak čišćenja
    if (line.includes('[ČIŠĆENJE] Završeno')) {
      document.getElementById('cleaning-modal-status').textContent = 'Završeno!';
      document.getElementById('cleaning-modal-progress-text').textContent = '100%';
      document.getElementById('cleaning-modal-progress-bar').style.width = '100%';
      document.getElementById('cleaning-modal-progress-eta').textContent = '';
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    loadFiles();

    document.getElementById('select-all')?.addEventListener('click', () => {
      selectedSet.clear();
      document.querySelectorAll('.row-cb:not(:disabled)').forEach(cb => {
        cb.checked = true;
        selectedSet.add(parseInt(cb.dataset.idx));
      });
      updateSelectedCount();
      showMetadataForm();
    });

    document.getElementById('select-none')?.addEventListener('click', () => {
      selectedSet.clear();
      document.querySelectorAll('.row-cb').forEach(cb => cb.checked = false);
      updateSelectedCount();
      showMetadataForm();
    });

    document.getElementById('btn-clean')?.addEventListener('click', async () => {
      if (selectedSet.size === 0) {
        showToast('Odaberite barem jednu sirovu datoteku.', 'warn');
        return;
      }

      const selectedList = Array.from(selectedSet).map(i => files[i].rel_path);
      const btn = document.getElementById('btn-clean');
      btn.disabled = true;
      btn.textContent = 'Čišćenje u tijeku...';

      // Otvori modal s progress barom
      openCleaningModal();

      try {
        const res = await fetch('/api/clean', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ files: selectedList })
        });
        const data = await res.json();

        let ok = 0, err = 0;
        (data.results || []).forEach(r => {
          if (r.status === 'ok') ok++;
          else err++;
        });

        // Prikaži rezultat u modalu
        document.getElementById('cleaning-modal-summary').textContent = 
          `Uspješno: ${ok} datoteka${err > 0 ? `, Greške: ${err}` : ''}`;
        document.getElementById('cleaning-modal-result').classList.remove('hidden');
        document.getElementById('cleaning-modal-title').textContent = '✅ Čišćenje završeno';

        // Prikaži informacije o izlaznoj putanji i datoteci (prva uspješna)
        const firstOk = (data.results || []).find(r => r.status === 'ok');
        if (firstOk) {
          const dirEl = document.getElementById('cleaning-modal-output-dir');
          const fileEl = document.getElementById('cleaning-modal-output-file');
          const infoEl = document.getElementById('cleaning-modal-output-info');
          if (dirEl && firstOk.output_dir) {
            dirEl.textContent = firstOk.output_dir;
            dirEl.title = firstOk.output_dir;
          }
          if (fileEl && firstOk.output) {
            fileEl.textContent = firstOk.output;
            fileEl.title = firstOk.output;
          }
          if (infoEl) infoEl.classList.remove('hidden');
        }

        showToast(`Čišćenje završeno: ${ok} ok, ${err} greška.`, err > 0 ? 'warn' : 'info');
        selectedSet.clear();
        await loadFiles();
      } catch (e) {
        document.getElementById('cleaning-modal-status').textContent = 'Greška: ' + e.message;
        showToast('Greška: ' + e.message, 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Očisti i fiksiraj';
      }
    });

    // Modal event listeners
    document.getElementById('cleaning-modal-close')?.addEventListener('click', closeCleaningModal);
    document.getElementById('cleaning-modal-close-bottom')?.addEventListener('click', closeCleaningModal);
  });

  function escHtml(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

})();
