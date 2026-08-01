/**
 * prevod.js — Logika za Korak 3: LLM Prijevod
 * Slajder, Toggle, Dropdown — sve promjene šalju POST na /api/opcije
 * Provider Dropdown šalje POST na /api/provider
 */

(function () {
  'use strict';

  let opcijeDebounce = null;

  async function ucitajFixedDatoteke() {
    const select = document.getElementById('fixed-select');
    if (!select) return;

    try {
      const res = await fetch('/api/fixed-datoteke');
      const data = await res.json();
      const datoteke = data.datoteke || [];

      select.innerHTML = '<option value="">-- Odaberite datoteku --</option>';
      datoteke.forEach(d => {
        const opt = document.createElement('option');
        opt.value = d.rel_path;
        opt.textContent = `${d.knjiga ? d.knjiga + '/' : ''}${d.ime}  [${d.izmijenjeno}]`;
        select.appendChild(opt);
      });
    } catch (err) {
      showToast('Greška pri učitavanju datoteka: ' + err.message, 'error');
    }
  }

  async function ucitajProfile() {
    const select = document.getElementById('profil-select');
    if (!select) return;

    try {
      const res = await fetch('/api/profili');
      const data = await res.json();
      select.innerHTML = '';
      (data.profili || []).forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.ime;
        select.appendChild(opt);
      });
    } catch (err) {
      // Ignoriraj
    }
  }

  async function ucitajAktivniProvider() {
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

  async function promijeniProvider(providerKey) {
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
      if (!data.key_ok && data.poruka) {
        if (warnEl) {
          warnEl.textContent = '⚠ ' + data.poruka;
          warnEl.classList.remove('hidden');
        }
        showToast(data.poruka, 'warn');
      } else {
        if (warnEl) warnEl.classList.add('hidden');
        showToast(`Provider: ${data.title}`, 'info');
      }
    } catch (e) {
      showToast('Greška pri promjeni providera: ' + e.message, 'error');
    }
  }

  async function ucitajOpcije() {
    try {
      const res = await fetch('/api/opcije');
      const data = await res.json();

      const slider = document.getElementById('kolicina-slider');
      const sliderVal = document.getElementById('kolicina-val');
      const toggle = document.getElementById('header-toggle');
      const granSelect = document.getElementById('granularnost-select');
      const profilSelect = document.getElementById('profil-select');

      if (slider && sliderVal) {
        slider.value = data.kolicina || 1;
        sliderVal.textContent = data.kolicina || 1;
      }
      if (toggle) toggle.checked = data.header !== false;
      if (granSelect) granSelect.value = data.granularnost || 'paragraph';
      if (profilSelect && data.profil) profilSelect.value = data.profil;
    } catch (err) {
      // Ignoriraj
    }
  }

  function spremiOpcije() {
    clearTimeout(opcijeDebounce);
    opcijeDebounce = setTimeout(async () => {
      const slider = document.getElementById('kolicina-slider');
      const toggle = document.getElementById('header-toggle');
      const granSelect = document.getElementById('granularnost-select');
      const profilSelect = document.getElementById('profil-select');

      const payload = {
        kolicina: slider ? parseInt(slider.value) : undefined,
        header: toggle ? toggle.checked : undefined,
        granularnost: granSelect ? granSelect.value : undefined,
        profil: profilSelect ? profilSelect.value : undefined
      };

      try {
        await fetch('/api/opcije', {
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

  document.addEventListener('DOMContentLoaded', async () => {
    await ucitajProfile();
    await ucitajFixedDatoteke();
    await ucitajOpcije();
    await ucitajAktivniProvider();

    // Provider dropdown
    document.getElementById('provider-select')?.addEventListener('change', function () {
      promijeniProvider(this.value);
    });

    // Slajder
    const slider = document.getElementById('kolicina-slider');
    const sliderVal = document.getElementById('kolicina-val');
    slider?.addEventListener('input', () => {
      if (sliderVal) sliderVal.textContent = slider.value;
      spremiOpcije();
    });

    // Toggle
    document.getElementById('header-toggle')?.addEventListener('change', spremiOpcije);

    // Dropdowni
    document.getElementById('granularnost-select')?.addEventListener('change', spremiOpcije);
    document.getElementById('profil-select')?.addEventListener('change', spremiOpcije);

    // Gumb TEST
    document.getElementById('btn-test')?.addEventListener('click', () => pokreniPrejevod('test'));

    // Gumb Produkcijski
    document.getElementById('btn-produkcija')?.addEventListener('click', () => pokreniPrejevod('produkcija'));
  });

  async function pokreniPrejevod(tip) {
    const select = document.getElementById('fixed-select');
    const relPath = select?.value;
    if (!relPath) {
      showToast('Odaberite datoteku za prijevod.', 'warn');
      return;
    }

    const slider = document.getElementById('kolicina-slider');
    const toggle = document.getElementById('header-toggle');
    const granSelect = document.getElementById('granularnost-select');
    const profilSelect = document.getElementById('profil-select');

    const payload = {
      rel_path: relPath,
      tip,
      granularnost: granSelect?.value || 'paragraph',
      kolicina: slider ? parseInt(slider.value) : 1,
      header: toggle ? toggle.checked : true,
      profil: profilSelect?.value || 'sf_literature'
    };

    const btnId = tip === 'test' ? 'btn-test' : 'btn-produkcija';
    const btn = document.getElementById(btnId);
    if (btn) { btn.disabled = true; btn.textContent = 'Prijevod u tijeku...'; }

    try {
      const res = await fetch('/api/prevedi', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Greška servera');
      }

      const data = await res.json();
      showToast(`Prijevod (${tip}) završen: ${data.izlaz}`, 'info');
    } catch (e) {
      showToast('Greška: ' + e.message, 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = tip === 'test' ? '🧪 Pokreni TEST' : '🚀 Produkcijski prijevod';
      }
    }
  }

})();
