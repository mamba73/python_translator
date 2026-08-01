/**
 * ciscenje.js — Logika za Korak 2: Čišćenje i [fixed] priprema
 * Prikazuje SVE datoteke uključujući _001, _002 sufikse
 */

(function () {
  'use strict';

  let datoteke = [];
  let odabraneSet = new Set();

  async function ucitajDatoteke() {
    const tbody = document.getElementById('output-tbody');
    if (!tbody) return;

    try {
      const res = await fetch('/api/output-datoteke');
      const data = await res.json();
      datoteke = data.datoteke || [];

      tbody.innerHTML = '';

      if (datoteke.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center py-8 text-gray-500">Nema datoteka u work/output/</td></tr>';
        return;
      }

      datoteke.forEach((d, i) => {
        const fixedBadge = d.je_fixed
          ? '<span class="px-2 py-0.5 rounded bg-green-900 text-green-300 text-xs">[fixed]</span>'
          : '<span class="px-2 py-0.5 rounded bg-gray-700 text-gray-400 text-xs">sirova</span>';

        const tr = document.createElement('tr');
        tr.className = 'border-b border-gray-700 hover:bg-gray-800 transition-colors';
        tr.innerHTML = `
          <td class="py-2 px-3">
            <input type="checkbox" class="row-cb w-4 h-4 accent-blue-500 cursor-pointer"
              data-idx="${i}" ${d.je_fixed ? 'disabled title="[fixed] datoteka se ne čisti ponovo"' : ''}>
          </td>
          <td class="py-2 px-3 font-mono text-sm text-gray-200" data-col="ime">
            ${escHtml(d.knjiga ? d.knjiga + '/' : '')}${escHtml(d.ime)}
          </td>
          <td class="py-2 px-3" data-col="status">${fixedBadge}</td>
          <td class="py-2 px-3 text-xs text-gray-400" data-col="velicina">${escHtml(d.velicina)}</td>
          <td class="py-2 px-3 text-xs text-gray-400 whitespace-nowrap" data-col="izmijenjeno">${escHtml(d.izmijenjeno)}</td>
        `;
        tbody.appendChild(tr);
      });

      document.querySelectorAll('.row-cb:not(:disabled)').forEach(cb => {
        cb.addEventListener('change', e => {
          const idx = parseInt(e.target.dataset.idx);
          if (e.target.checked) odabraneSet.add(idx);
          else odabraneSet.delete(idx);
          azurirajBrojOdabranih();
        });
      });

      initSortableTable('output-table');
    } catch (err) {
      showToast('Greška pri učitavanju: ' + err.message, 'error');
    }
  }

  function azurirajBrojOdabranih() {
    const el = document.getElementById('odabrano-count');
    if (el) el.textContent = `Odabrano: ${odabraneSet.size}`;
  }

  document.addEventListener('DOMContentLoaded', () => {
    ucitajDatoteke();

    document.getElementById('select-all')?.addEventListener('click', () => {
      odabraneSet.clear();
      document.querySelectorAll('.row-cb:not(:disabled)').forEach(cb => {
        cb.checked = true;
        odabraneSet.add(parseInt(cb.dataset.idx));
      });
      azurirajBrojOdabranih();
    });

    document.getElementById('select-none')?.addEventListener('click', () => {
      odabraneSet.clear();
      document.querySelectorAll('.row-cb').forEach(cb => cb.checked = false);
      azurirajBrojOdabranih();
    });

    document.getElementById('btn-ocisti')?.addEventListener('click', async () => {
      if (odabraneSet.size === 0) {
        showToast('Odaberite barem jednu sirovu datoteku.', 'warn');
        return;
      }

      const odabraneList = Array.from(odabraneSet).map(i => datoteke[i].rel_path);
      const btn = document.getElementById('btn-ocisti');
      btn.disabled = true;
      btn.textContent = 'Čišćenje u tijeku...';

      try {
        const res = await fetch('/api/ocisti', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ datoteke: odabraneList })
        });
        const data = await res.json();

        let ok = 0, err = 0;
        (data.rezultati || []).forEach(r => {
          if (r.status === 'ok') ok++;
          else err++;
        });

        showToast(`Čišćenje završeno: ${ok} ok, ${err} grešaka.`, err > 0 ? 'warn' : 'info');
        odabraneSet.clear();
        await ucitajDatoteke();
      } catch (e) {
        showToast('Greška: ' + e.message, 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Očisti i fiksiraj';
      }
    });
  });

  function escHtml(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

})();
