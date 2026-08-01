/**
 * konverzija.js — Logika za Korak 1: Konverzija dokumenata
 */

(function () {
  'use strict';

  let datoteke = [];
  let odabraneSet = new Set();

  async function ucitajDatoteke() {
    const tbody = document.getElementById('input-tbody');
    const emptyMsg = document.getElementById('empty-msg');
    if (!tbody) return;

    try {
      const res = await fetch('/api/input-datoteke');
      const data = await res.json();
      datoteke = data.datoteke || [];

      tbody.innerHTML = '';

      if (datoteke.length === 0) {
        if (emptyMsg) emptyMsg.classList.remove('hidden');
        return;
      }
      if (emptyMsg) emptyMsg.classList.add('hidden');

      datoteke.forEach((d, i) => {
        const tr = document.createElement('tr');
        tr.className = 'border-b border-gray-700 hover:bg-gray-800 transition-colors';
        tr.innerHTML = `
          <td class="py-2 px-3">
            <input type="checkbox" class="row-cb w-4 h-4 accent-blue-500 cursor-pointer"
              data-idx="${i}" ${odabraneSet.has(i) ? 'checked' : ''}>
          </td>
          <td class="py-2 px-3 font-mono text-sm text-gray-200" data-col="ime">${escHtml(d.ime)}</td>
          <td class="py-2 px-3 text-xs text-gray-400" data-col="tip">
            <span class="px-2 py-0.5 rounded bg-blue-900 text-blue-300">${escHtml(d.tip)}</span>
          </td>
          <td class="py-2 px-3 text-xs text-gray-400" data-col="velicina">${escHtml(d.velicina)}</td>
          <td class="py-2 px-3 text-xs text-gray-400 whitespace-nowrap" data-col="izmijenjeno">${escHtml(d.izmijenjeno)}</td>
        `;
        tbody.appendChild(tr);
      });

      // Checkboxes
      document.querySelectorAll('.row-cb').forEach(cb => {
        cb.addEventListener('change', e => {
          const idx = parseInt(e.target.dataset.idx);
          if (e.target.checked) odabraneSet.add(idx);
          else odabraneSet.delete(idx);
          azurirajBrojOdabranih();
        });
      });

      initSortableTable('input-table');
    } catch (err) {
      showToast('Greška pri učitavanju datoteka: ' + err.message, 'error');
    }
  }

  function azurirajBrojOdabranih() {
    const el = document.getElementById('odabrano-count');
    if (el) el.textContent = `Odabrano: ${odabraneSet.size}`;
  }

  document.addEventListener('DOMContentLoaded', () => {
    ucitajDatoteke();

    // Odaberi sve
    document.getElementById('select-all')?.addEventListener('click', () => {
      odabraneSet = new Set(datoteke.map((_, i) => i));
      document.querySelectorAll('.row-cb').forEach(cb => cb.checked = true);
      azurirajBrojOdabranih();
    });

    // Poništi odabir
    document.getElementById('select-none')?.addEventListener('click', () => {
      odabraneSet.clear();
      document.querySelectorAll('.row-cb').forEach(cb => cb.checked = false);
      azurirajBrojOdabranih();
    });

    // Gumb Konvertiraj
    document.getElementById('btn-konvertuj')?.addEventListener('click', async () => {
      if (odabraneSet.size === 0) {
        showToast('Odaberite barem jednu datoteku.', 'warn');
        return;
      }

      const format = document.querySelector('input[name="format"]:checked')?.value || 'txt';
      const odabraneList = Array.from(odabraneSet).map(i => datoteke[i].rel_path);

      const btn = document.getElementById('btn-konvertuj');
      btn.disabled = true;
      btn.textContent = 'Konverzija u tijeku...';

      try {
        const res = await fetch('/api/konvertuj', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ datoteke: odabraneList, format })
        });
        const data = await res.json();

        let ok = 0, err = 0;
        (data.rezultati || []).forEach(r => {
          if (r.status === 'ok') ok++;
          else err++;
        });

        showToast(`Konverzija završena: ${ok} ok, ${err} grešaka.`, err > 0 ? 'warn' : 'info');
        await ucitajDatoteke();
      } catch (e) {
        showToast('Greška: ' + e.message, 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Pokreni konverziju';
      }
    });
  });

  function escHtml(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

})();
