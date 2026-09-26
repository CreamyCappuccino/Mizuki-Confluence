/* Prototype fragment routing. Without JS all samples remain readable in HTML. */
(() => {
  'use strict';
  const articles = [...document.querySelectorAll('[data-reading]')];
  function select() {
    let target = '';
    try { target = decodeURIComponent(location.hash.slice(1)); } catch { /* Show all. */ }
    const id = target.replace(/-replies$/, '');
    const current = articles.find((article) => article.id === id);
    articles.forEach((article) => { article.hidden = Boolean(current && article !== current); });
    if (!current) return;
    document.title = `${current.querySelector('h1').textContent} — Confluence`;
    if (target.endsWith('-replies')) {
      requestAnimationFrame(() => document.getElementById(target)?.scrollIntoView({ behavior: 'instant', block: 'start' }));
    }
  }
  window.addEventListener('hashchange', select);
  select();
})();
