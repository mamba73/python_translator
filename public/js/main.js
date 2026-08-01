/**
 * main.js — Zajednički WebSocket klijent i Live Console za sve stranice
 * MambaBookVoice Web GUI
 */

(function () {
  'use strict';

  // ─── WebSocket Live Console ───────────────────────────────────────────────
  let ws = null;
  let reconnectTimer = null;
  const MAX_CONSOLE_LINES = 200;

  function initLiveConsole() {
    const console_ = document.getElementById('live-console');
    if (!console_) return;

    connectWS(console_);
  }

  function connectWS(consoleEl) {
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${protocol}://${location.host}/stream-logs`;

    ws = new WebSocket(url);

    ws.onopen = () => {
      appendLog(consoleEl, 'INFO Spojen na log stream...', 'text-green-400');
      clearTimeout(reconnectTimer);
    };

    ws.onmessage = (evt) => {
      if (evt.data === 'PING') return;
      const cls = getLogClass(evt.data);
      appendLog(consoleEl, evt.data, cls);
    };

    ws.onclose = () => {
      appendLog(consoleEl, 'WARN Veza prekinuta. Pokušavam ponovo za 5s...', 'text-yellow-400');
      reconnectTimer = setTimeout(() => connectWS(consoleEl), 5000);
    };

    ws.onerror = () => {
      appendLog(consoleEl, 'ERROR WebSocket greška.', 'text-red-400');
    };
  }

  function appendLog(el, text, cls) {
    const line = document.createElement('div');
    line.className = cls || 'text-green-400';
    const ts = new Date().toTimeString().slice(0, 8);
    line.textContent = `[${ts}] ${text}`;
    el.appendChild(line);

    // Ograniči broj redova
    while (el.children.length > MAX_CONSOLE_LINES) {
      el.removeChild(el.firstChild);
    }

    // Auto-scroll na dno
    el.scrollTop = el.scrollHeight;
  }

  function getLogClass(msg) {
    const upper = msg.toUpperCase();
    if (upper.startsWith('ERROR') || upper.includes('[ERROR]')) return 'text-red-400';
    if (upper.startsWith('WARNING') || upper.startsWith('WARN') || upper.includes('[WARN]')) return 'text-yellow-400';
    if (upper.startsWith('INFO') || upper.includes('[INFO]') || upper.includes('[KONVERZIJA]') ||
        upper.includes('[ČIŠĆENJE]') || upper.includes('[PRIJEVOD]') || upper.includes('[TTS]')) {
      return 'text-green-400';
    }
    if (upper.includes('[SPREMLJENO]') || upper.includes('ZAVRŠENO') || upper.includes('OK')) return 'text-cyan-400';
    return 'text-gray-300';
  }

  // ─── Statusna traka ───────────────────────────────────────────────────────
  function initStatusBar() {
    const bar = document.getElementById('status-bar');
    if (!bar) return;

    refreshStatus();
    setInterval(refreshStatus, 10000);
  }

  async function refreshStatus() {
    try {
      const res = await fetch('/api/status');
      const data = await res.json();

      const lmDot = document.getElementById('lm-status-dot');
      const lmTxt = document.getElementById('lm-status-txt');
      if (lmDot && lmTxt) {
        lmDot.className = data.lm_studio_online
          ? 'inline-block w-2 h-2 rounded-full bg-green-400 mr-1'
          : 'inline-block w-2 h-2 rounded-full bg-red-500 mr-1';
        lmTxt.textContent = data.lm_studio_online ? 'LM Studio: Online' : 'LM Studio: Offline';
      }

      const cpCount = document.getElementById('cp-count');
      if (cpCount) {
        cpCount.textContent = `Checkpointi: ${data.checkpointi.length}`;
      }

      if (data.sys_info && data.sys_info.cpu !== null) {
        const cpuEl = document.getElementById('sys-cpu');
        const ramEl = document.getElementById('sys-ram');
        if (cpuEl) cpuEl.textContent = `CPU: ${data.sys_info.cpu}%`;
        if (ramEl) ramEl.textContent = `RAM: ${data.sys_info.ram_gb} GB`;
      }
    } catch (e) {
      // Server ne odgovara
    }
  }

  // ─── Sortiranje tablica ───────────────────────────────────────────────────
  window.initSortableTable = function (tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;

    const headers = table.querySelectorAll('th[data-sort]');
    let sortCol = null;
    let sortAsc = true;

    headers.forEach(th => {
      th.style.cursor = 'pointer';
      th.title = 'Klikni za sortiranje';

      th.addEventListener('click', () => {
        const col = th.dataset.sort;
        if (sortCol === col) {
          sortAsc = !sortAsc;
        } else {
          sortCol = col;
          sortAsc = true;
        }

        // Ažuriraj ikone zaglavlja
        headers.forEach(h => {
          const ico = h.querySelector('.sort-icon');
          if (ico) ico.textContent = h === th ? (sortAsc ? ' ▲' : ' ▼') : ' ⇅';
        });

        sortTable(table, col, sortAsc);
      });

      // Dodaj ikonu
      const ico = document.createElement('span');
      ico.className = 'sort-icon text-gray-500 text-xs';
      ico.textContent = ' ⇅';
      th.appendChild(ico);
    });
  };

  function sortTable(table, col, asc) {
    const tbody = table.querySelector('tbody');
    if (!tbody) return;

    const rows = Array.from(tbody.querySelectorAll('tr'));
    rows.sort((a, b) => {
      const aVal = a.querySelector(`[data-col="${col}"]`)?.textContent?.trim() || '';
      const bVal = b.querySelector(`[data-col="${col}"]`)?.textContent?.trim() || '';
      const cmp = aVal.localeCompare(bVal, 'hr', { numeric: true });
      return asc ? cmp : -cmp;
    });

    rows.forEach(r => tbody.appendChild(r));
  }

  // ─── Toast obavijesti ─────────────────────────────────────────────────────
  window.showToast = function (msg, tip) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    const colorCls = tip === 'error' ? 'bg-red-700 border-red-500'
      : tip === 'warn' ? 'bg-yellow-700 border-yellow-500'
      : 'bg-gray-800 border-green-500';

    toast.className = `border-l-4 ${colorCls} text-white px-4 py-3 rounded shadow-lg mb-2 text-sm transition-all`;
    toast.textContent = msg;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  };

  // ─── Init ─────────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    initLiveConsole();
    initStatusBar();
  });

})();
