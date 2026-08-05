/**
 * metadata.js — Reusable metadata form component
 * Automatski se popunjava iz /api/metadata i omogućava ručno uređivanje.
 * Prije prikaza forme, poziva /api/check-book-config koji osigurava
 * postojanje config.yaml i memorija.json za odabranu knjigu.
 * Koristi se u svim koracima: konverzija, čišćenje, prijevod, MP3.
 */

(function () {
  'use strict';

  // ─── Stanje ──────────────────────────────────────────────────────────────
  let currentRelPath = null;
  let currentSource = '';

  /**
   * Inicijalizira metadata formu.
   * Najprije poziva /api/check-book-config da osigura postojanje
   * config.yaml i memorija.json, zatim učitava metapodatke.
   * @param {string} containerId - ID kontejnera u kojem je forma
   * @param {string} relPath - Relativna putanja do datoteke
   */
  function initMetadataForm(containerId, relPath) {
    const container = document.getElementById(containerId);
    if (!container) return;

    currentRelPath = relPath;
    ensureBookConfig(containerId, relPath);
  }

  /**
   * Poziva /api/check-book-config da automatski kreira config.yaml
   * i memorija.json ako ne postoje. Nakon toga učitava metapodatke.
   */
  async function ensureBookConfig(containerId, relPath) {
    const container = document.getElementById(containerId);
    if (!container || !relPath) return;

    try {
      const res = await fetch('/api/check-book-config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rel_path: relPath })
      });
      const data = await res.json();

      if (data.status === 'ok') {
        console.log('[metadata.js] Book config provjeren:', data.book_dir);
      } else {
        console.warning('[metadata.js] Book config greška:', data.message);
      }
    } catch (err) {
      console.error('[metadata.js] Greška pri provjeri book config:', err);
    }

    // Nakon provjere, učitaj metapodatke
    ucitajMetapodatke(containerId, relPath);
  }

  /**
   * Učitava metapodatke iz /api/metadata i popunjava formu.
   */
  async function ucitajMetapodatke(containerId, relPath) {
    const container = document.getElementById(containerId);
    if (!container || !relPath) return;

    // Prikaži loading
    const titleEl = container.querySelector('[data-meta="title"]');
    const authorEl = container.querySelector('[data-meta="author"]');
    const yearEl = container.querySelector('[data-meta="year"]');
    const langEl = container.querySelector('[data-meta="language"]');
    const sourceEl = container.querySelector('[data-meta="source"]');

    try {
      const res = await fetch(`/api/metadata?rel_path=${encodeURIComponent(relPath)}`);
      const data = await res.json();

      if (titleEl) titleEl.value = data.title || '';
      if (authorEl) authorEl.value = data.author || '';
      if (yearEl) yearEl.value = data.year || '';
      if (langEl) langEl.value = data.language || 'hr';
      if (sourceEl) {
        sourceEl.textContent = data.source || '';
        sourceEl.classList.remove('hidden');
      }

      currentSource = data.source || '';
    } catch (err) {
      console.error('Greška pri učitavanju metapodataka:', err);
    }
  }

  /**
   * Spremanje metapodataka na /api/metadata.
   * @param {string} containerId - ID kontejnera
   * @param {string} relPath - Relativna putanja
   * @returns {Promise<boolean>} - true ako je uspješno
   */
  async function spremiMetapodatke(containerId, relPath) {
    const container = document.getElementById(containerId);
    if (!container || !relPath) return false;

    const titleEl = container.querySelector('[data-meta="title"]');
    const authorEl = container.querySelector('[data-meta="author"]');
    const yearEl = container.querySelector('[data-meta="year"]');
    const langEl = container.querySelector('[data-meta="language"]');

    const payload = {
      rel_path: relPath,
      title: titleEl ? titleEl.value.trim() : '',
      author: authorEl ? authorEl.value.trim() : '',
      year: yearEl ? yearEl.value.trim() : '',
      language: langEl ? langEl.value : 'hr'
    };

    try {
      const res = await fetch('/api/metadata', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Greška pri spremanju');
      }

      const data = await res.json();
      showToast(`Metapodaci spremljeni: ${data.title} | ${data.author}`, 'info');
      return true;
    } catch (err) {
      showToast('Greška pri spremanju metapodataka: ' + err.message, 'error');
      return false;
    }
  }

  /**
   * Generira HTML za metadata formu.
   * @returns {string} - HTML string
   */
  function generirajFormuHTML() {
    return `
      <div class="bg-slate-800 border border-slate-700 rounded-xl p-4 mb-4">
        <div class="flex items-center justify-between mb-3">
          <div class="text-sm font-semibold text-gray-200">📋 Metapodaci knjige</div>
          <span class="text-xs text-gray-500" data-meta="source"></span>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label class="block text-xs text-gray-400 mb-1">Naslov knjige</label>
            <input type="text" data-meta="title" placeholder="Npr. Foundation"
              class="w-full bg-gray-900 border border-gray-600 text-gray-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500">
          </div>
          <div>
            <label class="block text-xs text-gray-400 mb-1">Autor</label>
            <input type="text" data-meta="author" placeholder="Npr. Isaac Asimov"
              class="w-full bg-gray-900 border border-gray-600 text-gray-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500">
          </div>
          <div>
            <label class="block text-xs text-gray-400 mb-1">Godina izdanja</label>
            <input type="text" data-meta="year" placeholder="Npr. 1951"
              class="w-full bg-gray-900 border border-gray-600 text-gray-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500">
          </div>
          <div>
            <label class="block text-xs text-gray-400 mb-1">Jezik</label>
            <select data-meta="language"
              class="w-full bg-gray-900 border border-gray-600 text-gray-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500 appearance-none cursor-pointer">
              <option value="hr">Hrvatski (hr)</option>
              <option value="en">Engleski (en)</option>
              <option value="de">Njemački (de)</option>
              <option value="fr">Francuski (fr)</option>
              <option value="it">Talijanski (it)</option>
              <option value="es">Španjolski (es)</option>
            </select>
          </div>
        </div>
        <div class="flex justify-end mt-3">
          <button type="button" data-meta="spremi"
            class="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold rounded-lg transition-colors">
            💾 Spremi metapodatke
          </button>
        </div>
      </div>
    `;
  }

  /**
   * Postavlja event listener za gumb "Spremi metapodatke".
   * @param {string} containerId - ID kontejnera
   * @param {string} relPath - Relativna putanja
   */
  function postaviSpremiListener(containerId, relPath) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const btn = container.querySelector('[data-meta="spremi"]');
    if (!btn) return;

    const newBtn = btn.cloneNode(true);
    btn.parentNode.replaceChild(newBtn, btn);
    newBtn.addEventListener('click', () => spremiMetapodatke(containerId, relPath));
  }

  // Eksportiraj globalne funkcije
  window.MetadataForm = {
    init: initMetadataForm,
    ucitaj: ucitajMetapodatke,
    spremi: spremiMetapodatke,
    generirajHTML: generirajFormuHTML,
    postaviSpremi: postaviSpremiListener
  };

  console.log('[metadata.js] MetadataForm loaded and exposed on window');

})();
