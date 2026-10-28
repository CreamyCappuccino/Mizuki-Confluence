/* AIL-inspired density + bounded measurement; never change editorial text. */
export function displayUnits(text) {
  return Array.from(text).reduce((sum, character) => sum + (
    /\s/u.test(character) ? .33 :
      /[\u2e80-\u9fff\uac00-\ud7af\uf900-\ufaff\uff01-\uff60]/u.test(character) ? 1 :
        /[A-Z]/u.test(character) ? .7 : .55), 0);
}

export function titleDensity(text) {
  const units = displayUnits(text);
  return units <= 17 ? 'display' : units <= 30 ? 'large' : units <= 52 ? 'regular' : 'compact';
}

export function renderedLines(title, view) {
  const lineHeight = Number.parseFloat(view.getComputedStyle(title).lineHeight);
  return lineHeight > 0 ? Math.max(1, Math.ceil((title.getBoundingClientRect().height - .5) / lineHeight)) : 1;
}

export function fitTitle(title, view, { baselineDpr = view.devicePixelRatio } = {}) {
  title.style.removeProperty('--cf-title-fit');
  title.dataset.cfTitleDensity = titleDensity(title.textContent);
  if (!title.getBoundingClientRect().width) return;
  const rootSize = Number.parseFloat(view.getComputedStyle(title.ownerDocument.documentElement).fontSize);
  const style = view.getComputedStyle(title);
  const start = Number.parseFloat(style.fontSize);
  const floor = Number.parseFloat(style.getPropertyValue('--cf-title-floor-rem')) * rootSize;
  const enlarged = rootSize > 16 || view.visualViewport?.scale > 1.05 ||
    view.devicePixelRatio > baselineDpr * 1.05 ||
    (view.outerWidth > 0 && view.innerWidth > 0 && view.outerWidth / view.innerWidth > 1.25);
  const limit = view.matchMedia('(max-width: 600px)').matches ? 4 : 3;
  if (!enlarged && Number.isFinite(start) && floor > 0 && renderedLines(title, view) > limit) {
    let low = Math.min(floor, start);
    let high = start;
    const size = (pixels) => title.style.setProperty('--cf-title-fit', `${pixels / rootSize}rem`);
    size(low);
    // If even the readable floor needs more lines, let the title grow vertically.
    if (renderedLines(title, view) <= limit) {
      for (let step = 0; step < 8; step += 1) {
        const candidate = (low + high) / 2;
        size(candidate);
        if (renderedLines(title, view) <= limit) low = candidate;
        else high = candidate;
      }
      size(low);
    }
  }
  title.dataset.cfTitleLines = String(renderedLines(title, view));
}

export function enhanceTitleFit(doc = document, view = window) {
  const titles = [...doc.querySelectorAll('.reading-heading h1')];
  if (!titles.length) return;
  const baselineDpr = view.devicePixelRatio;
  let frame = 0;
  const fit = () => {
    frame = 0;
    titles.forEach((title) => fitTitle(title, view, { baselineDpr }));
  };
  const schedule = () => {
    if (!frame) frame = view.requestAnimationFrame(fit);
  };
  view.addEventListener('resize', schedule, { passive: true });
  doc.addEventListener('confluence:locale', schedule);
  view.addEventListener('hashchange', schedule);
  doc.fonts?.ready.then(schedule);
  doc.fonts?.addEventListener?.('loadingdone', schedule);
  if (view.ResizeObserver) {
    const widths = new WeakMap();
    const observer = new view.ResizeObserver((entries) => {
      for (const entry of entries) {
        const width = Math.round(entry.contentRect.width);
        if (widths.get(entry.target) !== width) {
          widths.set(entry.target, width);
          schedule();
        }
      }
    });
    titles.forEach((title) => observer.observe(title.parentElement));
  }
  schedule();
}
