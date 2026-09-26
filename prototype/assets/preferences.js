/* Runs before CSS. file:// and privacy modes may deny storage; both are supported. */
(() => {
  'use strict';
  const root = document.documentElement;
  const get = (key, fallback) => {
    try { return localStorage.getItem(`confluence.${key}`) || fallback; }
    catch { return fallback; }
  };
  const put = (key, value) => {
    try { localStorage.setItem(`confluence.${key}`, value); } catch { /* Ephemeral preferences. */ }
  };
  const systemDark = window.matchMedia('(prefers-color-scheme: dark)');
  let theme = get('theme', 'system');
  if (!['system', 'light', 'dark'].includes(theme)) theme = 'system';
  let locale = get('uiLocale', 'ja');
  if (!['ja', 'en'].includes(locale)) locale = 'ja';
  let scene = get('scene', 'window');
  if (!['window', 'afternoon'].includes(scene)) scene = 'window';

  function apply() {
    root.dataset.themePreference = theme;
    root.dataset.theme = theme === 'system' ? (systemDark.matches ? 'dark' : 'light') : theme;
    root.dataset.scene = scene;
    root.lang = locale;
  }
  apply();
  const onSystem = () => { apply(); document.dispatchEvent(new Event('confluence:preferences')); };
  if (systemDark.addEventListener) systemDark.addEventListener('change', onSystem);
  else if (systemDark.addListener) systemDark.addListener(onSystem);
  window.ConfluencePrefs = {
    get theme() { return theme; },
    get locale() { return locale; },
    get scene() { return scene; },
    cycleTheme() {
      theme = ['system', 'light', 'dark'][(['system', 'light', 'dark'].indexOf(theme) + 1) % 3];
      put('theme', theme); apply();
    },
    toggleLocale() { locale = locale === 'ja' ? 'en' : 'ja'; put('uiLocale', locale); apply(); },
    toggleScene() { scene = scene === 'window' ? 'afternoon' : 'window'; put('scene', scene); apply(); },
  };
})();
