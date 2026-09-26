/* Search and incremental display operate on already-rendered, public sample HTML. */
(() => {
  'use strict';
  const rows = [...document.querySelectorAll('[data-entry]')];
  if (!rows.length) return;
  const params = new URLSearchParams(location.search);
  const query = document.getElementById('query');
  const search = document.getElementById('search');
  const form = search.querySelector('form');
  const more = document.querySelector('[data-load-more]');
  const status = document.querySelector('[data-list-status]');
  const count = document.querySelector('[data-list-count]');
  const empty = document.querySelector('[data-empty]');
  const banner = document.querySelector('[data-filter-banner]');
  const locale = () => window.ConfluencePrefs?.locale || 'ja';
  const normalize = (value) => value.normalize('NFKC').toLocaleLowerCase().trim();
  let limit = params.has('all') ? rows.length : 6;
  query.value = params.get('q') || '';
  const filters = ['author', 'category', 'tag', 'year'].filter((key) => params.has(key));
  if (filters.length) {
    banner.hidden = false;
    banner.querySelector('[data-filter-label]').textContent = filters.map((key) => params.get(key)).join(' / ');
  }

  function selected(row) {
    const full = normalize(`${row.textContent} ${row.dataset.category} ${row.dataset.tags}`);
    if (query.value && !normalize(query.value).split(/\s+/).every((term) => full.includes(term))) return false;
    return filters.every((key) => {
      const value = params.get(key);
      if (key === 'tag') return row.dataset.tags.split(' ').includes(value);
      if (key === 'year') return row.dataset.date.startsWith(value);
      return row.dataset[key] === value;
    });
  }
  function render() {
    const matches = rows.filter(selected);
    const max = query.value.trim() || filters.length ? matches.length : limit;
    const shown = matches.slice(0, max);
    rows.forEach((row) => { row.hidden = !shown.includes(row); });
    more.hidden = shown.length >= matches.length;
    empty.hidden = matches.length > 0;
    count.textContent = `${matches.length} ${locale() === 'ja' ? '篇' : 'writings'}`;
    status.textContent = locale() === 'ja' ? `${shown.length} / ${matches.length} 篇を表示` : `${shown.length} of ${matches.length} writings`;
    return shown;
  }
  more.addEventListener('click', () => {
    const previous = render().length;
    limit += 6;
    const shown = render();
    shown[previous]?.querySelector('h3 a').focus({ preventScroll: true });
  });
  function rememberQuery() {
    const updated = new URL(location.href);
    if (query.value) updated.searchParams.set('q', query.value);
    else updated.searchParams.delete('q');
    // file:// history can be restricted; search still works when it is.
    try { history.replaceState(null, '', updated.href); } catch { /* Keep local UI state. */ }
  }
  query.addEventListener('input', () => { render(); rememberQuery(); });
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    render(); rememberQuery();
  });
  function openSearch() {
    if (location.hash !== '#search' && !query.value) return;
    search.open = true;
    if (location.hash === '#search') query.focus({ preventScroll: true });
  }
  window.addEventListener('hashchange', openSearch);
  document.addEventListener('confluence:locale', render);
  openSearch();
  render();
})();
