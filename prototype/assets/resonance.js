/* Living Currents. Optional, local-only enhancement; original article stays intact. */
import { createResonanceField } from './resonance-field.js';
import { enhanceResonanceInteraction } from './resonance-interaction.js';

export function enhanceResonance() {
  const root = document.documentElement;
  if (root.dataset.cfReady) return;
  root.dataset.cfReady = 'true';
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const contrast = matchMedia('(forced-colors: active)');
  let preferred = true;
  try { preferred = localStorage.getItem('confluence.motion') !== 'off'; } catch { /* Private browsing. */ }
  let enabled = false;
  let field;
  try { field = createResonanceField(); } catch { /* Canvas is optional, not article content. */ }
  const dock = document.createElement('div');
  dock.className = 'cf-dock';
  const motion = document.createElement('button');
  motion.type = 'button'; motion.className = 'cf-motion';
  const label = document.createElement('span'); motion.append(label);
  const top = document.createElement('a');
  top.href = '#top'; top.className = 'cf-top'; top.textContent = '↑';
  dock.append(motion, top); document.body.append(dock);
  const progress = document.createElement('div');
  progress.className = 'cf-progress'; progress.setAttribute('aria-hidden', 'true');
  document.body.append(progress);
  const article = document.querySelector('.reading-body');
  if (article) {
    const track = document.createElement('div');
    track.className = 'cf-reading-line'; track.setAttribute('aria-hidden', 'true');
    document.body.append(track);
  }

  document.querySelectorAll('.reading-heading, .interior-heading, .hero').forEach((head) => {
    const ornament = document.createElement('div');
    ornament.className = 'cf-orrery'; ornament.setAttribute('aria-hidden', 'true');
    ['cf-orbit', 'cf-orbit-track', 'cf-orbit-track'].forEach((name) => {
      const ring = document.createElement('span'); ring.className = name; ornament.append(ring);
    });
    head.prepend(ornament);
  });

  function labels() {
    const ja = (window.ConfluencePrefs?.locale || root.lang).startsWith('ja');
    const forced = reduce.matches || contrast.matches;
    label.textContent = forced ? (ja ? '静止' : 'Still') : enabled ? (ja ? '動き ON' : 'Motion ON') : (ja ? '動き OFF' : 'Motion OFF');
    motion.setAttribute('aria-label', forced
      ? (ja ? '端末の設定に従い動きを停止中' : 'Motion disabled by your accessibility preference')
      : (ja ? '装飾の動きを切り替える' : 'Toggle decorative motion'));
    motion.setAttribute('aria-pressed', String(enabled));
    motion.disabled = forced;
    top.setAttribute('aria-label', ja ? 'ページ先頭に戻る' : 'Back to top');
    top.title = ja ? 'ページ先頭に戻る' : 'Back to top';
  }
  function sync() {
    enabled = preferred && !reduce.matches && !contrast.matches;
    root.dataset.cfMotion = enabled ? 'on' : 'off';
    root.classList.toggle('cf-live', enabled);
    root.classList.toggle('cf-sleep', document.hidden);
    field?.setEnabled(enabled); labels();
  }
  motion.addEventListener('click', () => {
    preferred = !preferred;
    try { localStorage.setItem('confluence.motion', preferred ? 'on' : 'off'); } catch { /* Ephemeral choice. */ }
    sync();
  });
  reduce.addEventListener?.('change', sync);
  contrast.addEventListener?.('change', sync);
  document.addEventListener('confluence:locale', labels);
  document.addEventListener('visibilitychange', sync);
  let priorTheme = root.dataset.theme, priorScene = root.dataset.scene, themeTimer = 0;
  const themeObserver = new MutationObserver(() => {
    if (root.dataset.theme === priorTheme && root.dataset.scene === priorScene) return;
    priorTheme = root.dataset.theme; priorScene = root.dataset.scene;
    field?.refresh(); labels();
    if (!enabled) return;
    root.classList.remove('cf-shifting');
    requestAnimationFrame(() => root.classList.add('cf-shifting'));
    clearTimeout(themeTimer);
    themeTimer = setTimeout(() => root.classList.remove('cf-shifting'), 850);
  });
  themeObserver.observe(root, { attributes: true, attributeFilter: ['data-theme', 'data-scene'] });
  const headings = [...document.querySelectorAll('.reading-body > h2, .reading-body > h3')];
  let scheduled = 0;
  function update() {
    scheduled = 0;
    const range = root.scrollHeight - innerHeight;
    const ratio = range > 0 ? Math.max(0, Math.min(1, scrollY / range)) : 0;
    root.style.setProperty('--cf-progress', ratio.toFixed(5));
    top.dataset.progress = String(Math.round(ratio * 100));
    let active = -1;
    headings.forEach((heading, index) => { if (heading.getBoundingClientRect().top < innerHeight * .4) active = index; });
    headings.forEach((heading, index) => heading.classList.toggle('cf-active', index === active));
  }
  function schedule() { if (!scheduled && !document.hidden) scheduled = requestAnimationFrame(update); }
  window.addEventListener('scroll', schedule, { passive: true });
  window.addEventListener('resize', schedule, { passive: true });
  window.addEventListener('load', schedule, { once: true });
  document.fonts?.ready.then(schedule);
  window.addEventListener('pageshow', () => { sync(); schedule(); });
  if ('ResizeObserver' in window) new ResizeObserver(schedule).observe(document.body);
  sync(); update();
  enhanceResonanceInteraction(() => enabled);
}
