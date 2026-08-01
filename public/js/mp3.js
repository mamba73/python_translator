/**
 * mp3.js — Logika za Korak 4: TTS sinteza u MP3
 * Autodupliciranje audiobook mape ako već postoji
 */

(function () {
  'use strict';

  let datoteke = [];
  let odabraniIdx = null;

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

      // Progress indikator
      const progressEl = document.getElementById('tts-progress');
      if (progressEl) progressEl.classList.remove('hidden');

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
      } catch (e) {
        showToast('Greška: ' + e.message, 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Generiraj MP3 audiobook';
        if (progressEl) progressEl.classList.add('hidden');
      }
    });
  });

  function escHtml(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

})();
