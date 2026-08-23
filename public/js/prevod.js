/**
 * prevod.js — Logika za Korak 3: LLM Prijevod
 * Slajder, Toggle, Dropdown — sve promjene šalju POST na /api/options
 * Provider Dropdown šalje POST na /api/provider
 */

(function () {
  'use strict';

  let optionsDebounce = null;

  async function loadFixedFiles() {
    const select = document.getElementById('fixed-select');
    if (!select) return;

    try {
      const res = await fetch('/api/fixed-files');
      const data = await res.json();
      const files = data.files || [];

      select.innerHTML = '<option value="">-- Odaberite datoteku --</option>';
      files.forEach(d => {
        const opt = document.createElement('option');
        opt.value = d.rel_path;
        opt.textContent = `${d.book ? d.book + '/' : ''}${d.name}  [${d.modified}]`;
        select.appendChild(opt);
      });

      // Event listener za promjenu odabira — učitaj metapodatke
      function showSelectedFile() {
        const relPath = select.value;
        const container = document.getElementById('metadata-container');
        if (!container) return;

        if (!relPath) {
          container.classList.add('hidden');
          container.innerHTML = '';
          return;
        }

        if (typeof MetadataForm === 'undefined') {
          console.error('[prevod.js] MetadataForm nije učitan!');
          return;
        }
        container.innerHTML = MetadataForm.generirajHTML();
        container.classList.remove('hidden');
        MetadataForm.init('metadata-container', relPath);
        MetadataForm.postaviSpremi('metadata-container', relPath);
      }

      select.addEventListener('change', showSelectedFile);
      showSelectedFile();
    } catch (err) {
      showToast('Greška pri učitavanju datoteka: ' + err.message, 'error');
    }
  }

  async function loadProfiles() {
    const select = document.getElementById('profile-select');
    if (!select) return;

    try {
      const res = await fetch('/api/profiles');
      const data = await res.json();
      select.innerHTML = '';
      (data.profiles || []).forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.name;
        select.appendChild(opt);
      });
    } catch (err) {
      // Ignoriraj
    }
  }

  async function loadActiveProvider() {
    const select = document.getElementById('provider-select');
    if (!select) return;
    try {
      const res = await fetch('/api/provider');
      const data = await res.json();

      // Dinamički popuni opcije ako ih server šalje
      if (data.providers) {
        select.innerHTML = '';
        data.providers.forEach(model => {
          const opt = document.createElement('option');
          opt.value = `${model.provider}:${model.model}`;
          opt.textContent = model.title;
          select.appendChild(opt);
        });
      }

      select.value = data.active || 'lmstudio:local';
    } catch (err) {
      // Ignoriraj — ostaje default iz HTML-a
    }
  }

  async function changeProvider(providerKey) {
    const warnEl = document.getElementById('provider-warn');
    try {
      const res = await fetch('/api/provider', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: providerKey })
      });
      const data = await res.json();
      if (!res.ok) {
        showToast('Greška: ' + (data.detail || 'Nepoznata greška'), 'error');
        return;
      }
      if (!data.key_ok && data.message) {
        if (warnEl) {
          warnEl.textContent = '⚠ ' + data.message;
          warnEl.classList.remove('hidden');
        }
        showToast(data.message, 'warn');
      } else {
        if (warnEl) warnEl.classList.add('hidden');
        showToast(`Provider: ${data.title}`, 'info');
      }
    } catch (e) {
      showToast('Greška pri promjeni providera: ' + e.message, 'error');
    }
  }

  async function loadOptions() {
    try {
      const res = await fetch('/api/options');
      const data = await res.json();

      const slider = document.getElementById('count-slider');
      const sliderVal = document.getElementById('count-val');
      const toggle = document.getElementById('header-toggle');
      const granSelect = document.getElementById('granularity-select');
      const profileSelect = document.getElementById('profile-select');

      if (slider && sliderVal) {
        slider.value = data.count || 1;
        sliderVal.textContent = data.count || 1;
      }
      if (toggle) toggle.checked = data.header !== false;
      if (granSelect) granSelect.value = data.granularity || 'paragraph';
      const maxCharsInput = document.getElementById('max-chars-input');
      if (maxCharsInput) maxCharsInput.value = data.max_chars || 5000;
      toggleMaxCharsField();
      if (profileSelect && data.profile) profileSelect.value = data.profile;
    } catch (err) {
      // Ignoriraj
    }
  }

  function saveOptions() {
    clearTimeout(optionsDebounce);
    optionsDebounce = setTimeout(async () => {
      const slider = document.getElementById('count-slider');
      const toggle = document.getElementById('header-toggle');
      const granSelect = document.getElementById('granularity-select');
      const profileSelect = document.getElementById('profile-select');
      const maxCharsInput = document.getElementById('max-chars-input');

      const payload = {
        count: slider ? parseInt(slider.value) : undefined,
        header: toggle ? toggle.checked : undefined,
        granularity: granSelect ? granSelect.value : undefined,
        profile: profileSelect ? profileSelect.value : undefined,
        max_chars: maxCharsInput ? parseInt(maxCharsInput.value) : undefined
      };

      try {
        await fetch('/api/options', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        showToast('Opcije spremljene.', 'info');
      } catch (e) {
        showToast('Greška pri spremanju opcija.', 'error');
      }
    }, 600);
  }

  function toggleMaxCharsField() {
    const container = document.getElementById('max-chars-container');
    const input = document.getElementById('max-chars-input');
    const granSelect = document.getElementById('granularity-select');
    if (!container || !granSelect) return;
    const isMaxChars = granSelect.value === 'max_chars';
    container.classList.toggle('hidden', !isMaxChars);
    if (input && isMaxChars && !input.value) input.value = 5000;
  }

  document.addEventListener('DOMContentLoaded', async () => {
    await loadProfiles();
    await loadFixedFiles();
    await loadOptions();
    await loadActiveProvider();

    // Provider dropdown
    document.getElementById('provider-select')?.addEventListener('change', function () {
      changeProvider(this.value);
    });

    // Slajder
    const slider = document.getElementById('count-slider');
    const sliderVal = document.getElementById('count-val');
    slider?.addEventListener('input', () => {
      if (sliderVal) sliderVal.textContent = slider.value;
      saveOptions();
    });

    // Toggle
    document.getElementById('header-toggle')?.addEventListener('change', saveOptions);

    // Dropdowni
    document.getElementById('granularity-select')?.addEventListener('change', () => {
      toggleMaxCharsField();
      saveOptions();
    });
    document.getElementById('profile-select')?.addEventListener('change', saveOptions);

    // Unos maks. broja znakova
    document.getElementById('max-chars-input')?.addEventListener('input', saveOptions);

    // Gumb TEST
    document.getElementById('btn-test')?.addEventListener('click', () => startTranslation('test'));

    // Gumb Produkcijski
    document.getElementById('btn-production')?.addEventListener('click', () => startTranslation('production'));
  });

  // ─── Modal: Progress prijevoda ────────────────────────────────────────────
  let modalWs = null;
  let modalReconnectTimer = null;
  let modalFileName = null;

  function openModal(mode) {
    const modal = document.getElementById('translation-modal');
    if (!modal) return;

    // Resetiraj modal
    document.getElementById('modal-title').textContent = mode === 'test' ? '🧪 TEST Prijevod' : '🚀 Produkcijski prijevod';
    document.getElementById('modal-model-name').textContent = '';
    document.getElementById('modal-status').textContent = 'Priprema segmenata...';
    document.getElementById('modal-progress-text').textContent = '0%';
    document.getElementById('modal-progress-details').textContent = 'Segment 0/0';
    document.getElementById('modal-progress-words').textContent = '';
    document.getElementById('modal-progress-eta').textContent = '';
    document.getElementById('modal-progress-bar').style.width = '0%';
    document.getElementById('modal-result').classList.add('hidden');
    document.getElementById('modal-copy').classList.add('hidden');
    document.getElementById('modal-text').value = '';
    modalFileName = null;

    modal.classList.remove('hidden');
    modal.classList.add('flex');

    // Spoji se na log stream za real-time progress
    connectModalWS();
  }

  let activeTranslationBook = null;

  function requestCancelTranslation() {
    // Pošalji zahtjev serveru da čisto zaustavi aktivni prijevod (oslobađa model)
    if (!activeTranslationBook) return;
    const bookName = activeTranslationBook.split('/')[0];
    fetch('/api/translation/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ book_name: bookName })
    }).catch(() => {});
  }

  function closeModal() {
    // Ako je prijevod još uvijek u tijeku, prvo ga zaustavi
    requestCancelTranslation();
    const modal = document.getElementById('translation-modal');
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
   * @param {string} etaText - Sirovi ETA tekst iz backenda (npr. "5m 30s", "U završnoj fazi")
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
    // Progress linija: [Progres] : [██████] 33% | Segment 1/3 | riječi: 30/90 (33%) | ETA: 5m 30s
    if (line.includes('[Progres]')) {
      const percentMatch = line.match(/(\d+)%/);
      const segmentMatch = line.match(/Segment (\d+)\/(\d+)/);
      const wordsMatch = line.match(/riječi: ([\d\/]+) \((\d+)%\)/);
      // ETA format: "ETA: 5m 30s" ili "ETA: U završnoj fazi" ili "ETA: < 1min"
      const etaMatch = line.match(/ETA:\s*(.+?)(?:\s*\||\s*$)/);

      if (percentMatch) {
        const pct = parseInt(percentMatch[1]);
        document.getElementById('modal-progress-text').textContent = pct + '%';
        document.getElementById('modal-progress-bar').style.width = pct + '%';
      }
      if (segmentMatch) {
        document.getElementById('modal-progress-details').textContent = `Segment ${segmentMatch[1]}/${segmentMatch[2]}`;
      }
      if (wordsMatch) {
        document.getElementById('modal-progress-words').textContent = `riječi: ${wordsMatch[1]} (${wordsMatch[2]}%)`;
      }
      // ETA — s zaštitom za negativne vrijednosti
      const etaEl = document.getElementById('modal-progress-eta');
      if (etaEl) {
        if (etaMatch) {
          const safeEta = sanitizeEta(etaMatch[1]);
          etaEl.textContent = safeEta ? `⏱ ${safeEta}` : '';
        }
        // Ako nema ETA u liniji, ostavi prethodnu vrijednost (ne briši)
      }
      // Status — uvijek samo "Prevođenje u tijeku..." (naziv modela ide u zasebni redak iznad)
      document.getElementById('modal-status').textContent = 'Prevođenje u tijeku...';
    }

    // Dohvat naziva aktivnog modela iz backend log linija (NE iz dropdown-a)
    // Format: "[LOKALNI MODEL] Detektiran aktivan model: <naziv>. Pokrećem prevođenje."
    if (line.includes('[LOKALNI MODEL]') && line.includes('Detektiran aktivan model:')) {
      const modelMatch = line.match(/Detektiran aktivan model:\s*(.+?)\s*\.\s*Pokrećem/);
      if (modelMatch) {
        document.getElementById('modal-model-name').textContent = modelMatch[1].trim();
      }
    }
    // Alternativni format: "✅ Auto-detektovan LM Studio model: <naziv>"
    if (line.includes('Auto-detektovan') && line.includes('model:')) {
      const modelMatch = line.match(/model:\s*(.+?)$/);
      if (modelMatch) {
        document.getElementById('modal-model-name').textContent = modelMatch[1].trim();
      }
    }

    // Završetak prijevoda
    if (line.includes('[PRIJEVOD] Završen')) {
      const nameMatch = line.match(/Završen (?:test|produkcijski): (.+?)(?:\s*\(status=.*\))?$/);
      if (nameMatch) {
        modalFileName = nameMatch[1].trim();
      }
      document.getElementById('modal-status').textContent = 'Završeno! Učitavam tekst...';
      document.getElementById('modal-progress-text').textContent = '100%';
      document.getElementById('modal-progress-bar').style.width = '100%';
    }
  }

  async function showResult(relPath) {
    try {
      const res = await fetch('/api/translated-content', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rel_path: relPath })
      });
      if (!res.ok) throw new Error('Ne mogu učitati tekst');
      const data = await res.json();

      document.getElementById('modal-text').value = data.content;
      document.getElementById('modal-file-name').textContent = data.name;
      document.getElementById('modal-result').classList.remove('hidden');
      document.getElementById('modal-copy').classList.remove('hidden');
      document.getElementById('modal-title').textContent = '✅ Prijevod završen';
      document.getElementById('modal-status').textContent = 'Tekst je spreman za pregled.';
    } catch (e) {
      document.getElementById('modal-status').textContent = 'Greška pri učitavanju teksta.';
      showToast('Greška pri učitavanju teksta: ' + e.message, 'error');
    }
  }

  async function startTranslation(mode) {
    const select = document.getElementById('fixed-select');
    const relPath = select?.value;
    if (!relPath) {
      showToast('Odaberite datoteku za prijevod.', 'warn');
      return;
    }

    // Ako je produkcijski prijevod, provjeri postoji li checkpoint
    if (mode === 'production') {
      try {
        const res = await fetch(`/api/checkpoint-status?rel_path=${encodeURIComponent(relPath)}`);
        const data = await res.json();
        if (data.has_checkpoint) {
          // Pitaj korisnika želi li nastaviti ili započeti novi
          const choice = await new Promise((resolve) => {
            const modal = document.createElement('div');
            modal.className = 'fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm';
            modal.innerHTML = `
              <div class="bg-slate-800 border border-slate-600 rounded-2xl shadow-2xl w-full max-w-md mx-4 p-6">
                <h3 class="text-lg font-bold text-white mb-3">⏳ Nastavi prijevod?</h3>
                <p class="text-sm text-gray-300 mb-4">
                  Postoji spremljeni checkpoint za ovu knjigu:
                  <span class="text-blue-400 font-semibold">${data.progress_percent}%</span> dovršeno
                  (segment ${data.current_segment}/${data.total_segments}).
                </p>
                <div class="flex gap-3">
                  <button id="resume-yes" class="flex-1 px-4 py-3 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-sm rounded-lg transition-colors">
                    ▶ Nastavi
                  </button>
                  <button id="resume-no" class="flex-1 px-4 py-3 bg-slate-700 hover:bg-slate-600 text-white font-semibold text-sm rounded-lg transition-colors">
                    🆕 Započni novi
                  </button>
                  <button id="resume-cancel" class="px-4 py-3 bg-red-800 hover:bg-red-700 text-white font-semibold text-sm rounded-lg transition-colors">
                    ✕ Odustani
                  </button>
                </div>
              </div>
            `;
            document.body.appendChild(modal);

            modal.querySelector('#resume-yes').addEventListener('click', () => {
              modal.remove();
              resolve('resume');
            });
            modal.querySelector('#resume-no').addEventListener('click', () => {
              modal.remove();
              resolve('fresh');
            });
            modal.querySelector('#resume-cancel').addEventListener('click', () => {
              modal.remove();
              resolve('cancel');
            });
          });

          if (choice === 'cancel') {
            return;
          }
          // Ako je izabrano resume, postavljamo resume: true
          // Ako je fresh, idemo normalno (resume: false)
          if (choice === 'resume') {
            await _doTranslation(relPath, mode, true);
            return;
          }
          // choice === 'fresh' → nastavi normalno ispod s resume: false
        }
      } catch (e) {
        console.error('Greška pri provjeri checkpointa:', e);
        // Nastavi normalno ako provjera padne
      }
    }

    await _doTranslation(relPath, mode, false);
  }

  async function _doTranslation(relPath, mode, resume) {
    const slider = document.getElementById('count-slider');
    const toggle = document.getElementById('header-toggle');
    const granSelect = document.getElementById('granularity-select');
    const profileSelect = document.getElementById('profile-select');
    const maxCharsInput = document.getElementById('max-chars-input');

    const payload = {
      rel_path: relPath,
      mode,
      granularity: granSelect?.value || 'paragraph',
      count: slider ? parseInt(slider.value) : 1,
      header: toggle ? toggle.checked : true,
      max_chars: maxCharsInput ? parseInt(maxCharsInput.value) : 5000,
      profile: profileSelect?.value || 'sf_literature',
      resume: resume
    };

    const btnId = mode === 'test' ? 'btn-test' : 'btn-production';
    const btn = document.getElementById(btnId);
    if (btn) { btn.disabled = true; btn.textContent = 'Prijevod u tijeku...'; }

    // Otvori modal s progress barom
    activeTranslationBook = relPath;
    openModal(mode);

    try {
      const res = await fetch('/api/translate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Greška servera');
      }

      const data = await res.json();

      // Prikaži prevedeni tekst u modalu
      const translatedRelPath = data.output;
      await showResult(translatedRelPath);

      // Prikaži informacije o izlaznoj putanji i datoteci
      const outputDirEl = document.getElementById('modal-output-dir');
      const outputFileEl = document.getElementById('modal-output-file');
      const outputInfoEl = document.getElementById('modal-output-info');
      if (outputDirEl && data.output_dir) {
        outputDirEl.textContent = data.output_dir;
        outputDirEl.title = data.output_dir;
      }
      if (outputFileEl && data.filename) {
        outputFileEl.textContent = data.filename;
        outputFileEl.title = data.filename;
      }
      if (outputInfoEl) {
        outputInfoEl.classList.remove('hidden');
      }

      showToast(`Prijevod (${mode}) završen: ${data.output}`, 'info');
    } catch (e) {
      document.getElementById('modal-status').textContent = 'Greška: ' + e.message;
      showToast('Greška: ' + e.message, 'error');
    } finally {
      activeTranslationBook = null;
      if (btn) {
        btn.disabled = false;
        btn.textContent = mode === 'test' ? '🧪 Pokreni TEST' : '🚀 Produkcijski prijevod';
      }
    }
  }

  // ─── Modal event listeners ────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('modal-close')?.addEventListener('click', closeModal);
    document.getElementById('modal-close-bottom')?.addEventListener('click', closeModal);
    document.getElementById('modal-copy')?.addEventListener('click', () => {
      const tekst = document.getElementById('modal-text');
      if (tekst) {
        tekst.select();
        navigator.clipboard.writeText(tekst.value).then(() => {
          showToast('Tekst kopiran u međuspremnik.', 'info');
        }).catch(() => {
          document.execCommand('copy');
          showToast('Tekst kopiran u međuspremnik.', 'info');
        });
      }
    });
  });

})();
