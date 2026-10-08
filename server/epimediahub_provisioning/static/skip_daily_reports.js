(() => {
  'use strict';
  const dialog = document.getElementById('episcene-report-dialog');
  const state = document.getElementById('episcene-report-state');
  const frame = document.getElementById('episcene-report-frame');
  if (!dialog || !frame) return;
  let shown = null;
  let returnFocus = null;
  function remember() {
    if (shown) {
      try { localStorage.setItem('episcene-report-seen-v1', shown); } catch (_) { /* private browsing */ }
    }
  }
  document.getElementById('episcene-report-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => {
    remember();
    if (returnFocus && typeof returnFocus.focus === 'function') returnFocus.focus();
  });
  async function check() {
    try {
      const response = await fetch('/admin/skip/reports/latest', {cache: 'no-store', credentials: 'same-origin'});
      if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw new Error('report_unavailable');
      const result = await response.json();
      if (!result.day) {
        state.textContent = 'Noch kein Tagesbericht vorhanden. Die erste Auswertung wird nach der Einrichtung bereitgestellt.';
        return;
      }
      if (result.day !== result.expected_day) {
        state.textContent = `Der aktuelle Bericht fehlt noch. Letzter verfügbarer Bericht: ${result.day}. Bitte den Berichtsdienst prüfen.`;
        return;
      }
      state.textContent = `Bericht vom ${result.day} verfügbar · Zeitraum jeweils 07:00 bis 07:00 Uhr`;
      let seen;
      try { seen = localStorage.getItem('episcene-report-seen-v1'); } catch (_) { /* private browsing */ }
      if (seen === result.day || shown === result.day || dialog.open) return;
      if (typeof dialog.showModal !== 'function') return;
      returnFocus = document.activeElement;
      frame.src = `/admin/skip/reports?day=${encodeURIComponent(result.day)}&embedded=1`;
      shown = result.day;
      dialog.showModal();
      document.getElementById('episcene-report-close').focus();
    } catch (_) {
      state.textContent = 'Der Tagesbericht konnte gerade nicht geladen werden. Über „Tagesbericht & Archiv öffnen“ erneut versuchen.';
    }
  }
  check();
  // An already open dashboard notices the new morning report as well.
  setInterval(() => { if (!document.hidden) check(); }, 60000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) check(); });
})();
