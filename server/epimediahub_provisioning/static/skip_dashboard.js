/* Keep the search focus and edit forms while updating only the progress view. */
(() => {
  let pending, controller, generation = 0;
  const section = () => document.getElementById('series-progress');
  async function update(url, replaceHistory = false) {
    const root = section();
    if (!root) return;
    clearTimeout(pending);
    if (controller) controller.abort();
    controller = new AbortController();
    const mine = ++generation;
    const feedback = root.querySelector('.progress-feedback');
    feedback.textContent = 'Übersicht wird geladen …';
    root.setAttribute('aria-busy', 'true');
    const input = root.querySelector('[name="progress_search"]');
    const focused = document.activeElement === input;
    const selection = focused ? [input.selectionStart, input.selectionEnd] : null;
    try {
      const endpoint = new URL(root.dataset.progressUrl, location.href);
      endpoint.search = url.search;
      const response = await fetch(endpoint, {credentials: 'same-origin', signal: controller.signal,
        headers: {'Accept': 'application/json'}});
      if (!response.ok || response.redirected) throw new Error('request');
      const value = await response.json();
      if (mine !== generation) return;
      const fragment = document.createElement('template');
      fragment.innerHTML = value.html;
      const replacement = fragment.content.querySelector('#series-progress');
      if (!replacement) throw new Error('view');
      root.replaceWith(replacement);
      if (focused) {
        const next = replacement.querySelector('[name="progress_search"]');
        next.focus({preventScroll: true});
        next.setSelectionRange(...selection);
      }
      if (replaceHistory) history.replaceState(null, '', url);
      else history.pushState(null, '', url);
    } catch (error) {
      if (error.name === 'AbortError' || mine !== generation) return;
      root.removeAttribute('aria-busy');
      feedback.textContent = 'Die Übersicht konnte nicht geladen werden. Bitte erneut filtern.';
    }
  }
  function formUrl(form) {
    const url = new URL(location.href);
    for (const [key, value] of new FormData(form)) url.searchParams.set(key, value);
    url.searchParams.delete('progress_page');
    url.hash = 'series-progress';
    return url;
  }
  document.addEventListener('submit', event => {
    const root = section();
    if (!root || !root.contains(event.target) || event.target.method !== 'get') return;
    event.preventDefault();
    update(formUrl(event.target));
  });
  document.addEventListener('change', event => {
    if (event.target.name !== 'progress_filter' || !section()?.contains(event.target)) return;
    update(formUrl(event.target.form));
  });
  document.addEventListener('input', event => {
    if (event.target.name !== 'progress_search' || !section()?.contains(event.target)) return;
    const form = event.target.form;
    // Invalidate a result immediately when the user types more characters.
    ++generation;
    if (controller) controller.abort();
    clearTimeout(pending);
    pending = setTimeout(() => update(formUrl(form), true), 300);
  });
  document.addEventListener('click', event => {
    const anchor = event.target.closest('a');
    if (!anchor || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    if (!section()?.contains(anchor) || !anchor.closest('.pagination')) return;
    event.preventDefault();
    const url = new URL(location.href), link = new URL(anchor.href);
    for (const key of ['progress_filter', 'progress_search', 'progress_page']) {
      if (link.searchParams.has(key)) url.searchParams.set(key, link.searchParams.get(key));
      else url.searchParams.delete(key);
    }
    url.hash = 'series-progress';
    update(url);
  });
  window.addEventListener('popstate', () => update(new URL(location.href), true));
})();
