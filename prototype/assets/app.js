/* Shared progressive enhancement. No fetch, analytics, credentials, or posting. */
(() => {
  'use strict';
  const prefs = window.ConfluencePrefs;
  if (!prefs) return;
  const root = document.documentElement;
  root.dataset.enhanced = 'true';
  const themeButton = document.querySelector('[data-theme-toggle]');
  const localeButton = document.querySelector('[data-locale-toggle]');
  const sceneControls = document.querySelector('[data-scene-controls]');
  const sceneButton = document.querySelector('[data-scene-toggle]');

  function translate() {
    document.querySelectorAll('[data-ja][data-en]').forEach((node) => {
      node.textContent = node.dataset[prefs.locale];
    });
    const label = document.querySelector('[data-theme-label]');
    const names = prefs.locale === 'ja' ? { system: '自動', light: '昼', dark: '夜' } : { system: 'Auto', light: 'Day', dark: 'Night' };
    if (label) label.textContent = names[prefs.theme];
    if (themeButton) {
      themeButton.title = `${names[prefs.theme]} · ${prefs.locale === 'ja' ? 'クリックで配色を切替' : 'Click to change theme'}`;
      themeButton.setAttribute('aria-label', themeButton.title);
    }
    if (localeButton) {
      localeButton.innerHTML = prefs.locale === 'ja' ? 'JA <span>/ EN</span>' : 'EN <span>/ JA</span>';
      localeButton.setAttribute('aria-label', prefs.locale === 'ja' ? 'Switch interface to English' : '表示言語を日本語へ');
    }
    const number = document.querySelector('[data-scene-number]');
    if (number) number.textContent = prefs.scene === 'window' ? '01 / 02' : '02 / 02';
    const query = document.getElementById('query');
    if (query) query.placeholder = prefs.locale === 'ja' ? 'タイトル・書き手・タグ' : 'Title, writer, or tag';
    document.dispatchEvent(new Event('confluence:locale'));
  }
  if (themeButton) {
    themeButton.hidden = false;
    themeButton.addEventListener('click', () => { prefs.cycleTheme(); translate(); });
  }
  if (localeButton) {
    localeButton.hidden = false;
    localeButton.addEventListener('click', () => { prefs.toggleLocale(); translate(); });
  }
  if (sceneControls && sceneButton) {
    sceneControls.hidden = false;
    sceneButton.addEventListener('click', () => { prefs.toggleScene(); translate(); });
  }
  document.addEventListener('confluence:preferences', translate);
  translate();

  const menu = document.querySelector('.menu');
  document.addEventListener('click', (event) => {
    if (menu && !menu.contains(event.target)) menu.open = false;
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && menu?.open) {
      menu.open = false;
      menu.querySelector('summary').focus();
    }
  });

  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const fine = window.matchMedia('(min-width: 901px) and (pointer: fine)');
  const hero = document.querySelector('.hero');
  let scheduled = false;
  function drift() {
    scheduled = false;
    if (!hero) return;
    if (reduced.matches || !fine.matches) {
      hero.style.removeProperty('--photo-drift');
      return;
    }
    const box = hero.getBoundingClientRect();
    if (box.bottom < 0) return;
    const y = Math.max(-8, Math.min(8, -box.top * .025));
    hero.style.setProperty('--photo-drift', `${y.toFixed(2)}px`);
  }
  function scheduleDrift() {
    if (!scheduled) { scheduled = true; requestAnimationFrame(drift); }
  }
  if (hero) {
    window.addEventListener('scroll', scheduleDrift, { passive: true });
    window.addEventListener('resize', scheduleDrift, { passive: true });
    reduced.addEventListener?.('change', drift);
    fine.addEventListener?.('change', drift);
    drift();
  }
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(({ isIntersecting, target }) => {
        if (!isIntersecting) return;
        if (!reduced.matches) target.classList.add('is-arriving');
        observer.unobserve(target);
      });
    }, { threshold: .05 });
    document.querySelectorAll('.entry').forEach((entry) => {
      if (entry.getBoundingClientRect().top > window.innerHeight) observer.observe(entry);
    });
  }
})();
