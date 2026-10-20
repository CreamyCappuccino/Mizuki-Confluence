/* Small, event-driven accents. Never rewrite the author's text or intercept links. */
export function createReadingTides(article) {
  if (!article) return { setEnabled() {}, update() {} };
  article.classList.add('cf-tides');
  const paragraphs = [...article.querySelectorAll(':scope > p')];
  let enabled = false, current = null;
  function clear() {
    current?.classList.remove('cf-reading-current');
    current = null;
  }
  function update() {
    if (!enabled || document.hidden) return;
    const box = article.getBoundingClientRect();
    const focus = innerHeight * .44;
    if (box.bottom <= 0 || box.top >= innerHeight) { clear(); return; }
    const y = Math.max(0, Math.min(box.height, focus - box.top));
    // Read all positions before updating styles. The text itself is never touched.
    let nearest = null, distance = Infinity;
    for (const node of paragraphs) {
      const rect = node.getBoundingClientRect();
      if (rect.bottom < 0 || rect.top > innerHeight) continue;
      const gap = Math.abs((rect.top + rect.bottom) / 2 - focus);
      if (gap < distance) { nearest = node; distance = gap; }
    }
    article.style.setProperty('--cf-reader-y', `${y.toFixed(1)}px`);
    if (nearest !== current) {
      clear(); current = nearest;
      current?.classList.add('cf-reading-current');
    }
  }
  return {
    update,
    setEnabled(value) {
      enabled = value;
      if (enabled) update();
      else clear();
    },
  };
}

export function enhanceResonanceInteraction(isEnabled) {
  const fine = matchMedia('(pointer: fine)');
  const root = document.documentElement;
  const highlights = [...document.querySelectorAll('.entry, .writer-row, .browse-item, .reading-heading')];
  let pointerFrame = 0, pending = null;
  function paintPointer() {
    pointerFrame = 0;
    const hit = pending; pending = null;
    if (!hit || !isEnabled() || document.hidden || !fine.matches) return;
    const box = hit.node.getBoundingClientRect();
    hit.node.style.setProperty('--cf-x', `${(hit.x - box.left).toFixed(1)}px`);
    hit.node.style.setProperty('--cf-y', `${(hit.y - box.top).toFixed(1)}px`);
  }
  highlights.forEach((node) => {
    node.addEventListener('pointermove', (event) => {
      if (!isEnabled() || !fine.matches) return;
      pending = { node, x: event.clientX, y: event.clientY };
      if (!pointerFrame) pointerFrame = requestAnimationFrame(paintPointer);
    }, { passive: true });
    node.addEventListener('pointerleave', () => {
      if (pending?.node === node) pending = null;
      node.style.removeProperty('--cf-x'); node.style.removeProperty('--cf-y');
    }, { passive: true });
  });
  document.querySelectorAll('.reading-heading h1, .hero h1, .interior-heading h1').forEach((title) => {
    let reset = 0;
    title.addEventListener('pointerenter', () => {
      if (!isEnabled() || !fine.matches || title.classList.contains('cf-phase')) return;
      title.classList.add('cf-phase');
      clearTimeout(reset); reset = setTimeout(() => title.classList.remove('cf-phase'), 1550);
    }, { passive: true });
  });
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(({ target, isIntersecting }) => {
        if (!isIntersecting) return;
        if (isEnabled()) target.classList.add('cf-arrive');
        observer.unobserve(target);
      });
    }, { threshold: .06, rootMargin: '0px 0px -12px 0px' });
    document.querySelectorAll('.reading-body > p, .reading-body > h1, .reading-body > h2, .reading-body > h3, .reading-body > blockquote, .reading-body > pre, .reading-body > ul, .reading-body > ol, .browse-section, .writer-row').forEach((node) => observer.observe(node));
  }
  document.querySelectorAll('.icon-button, .theme-button, .locale-button, .cf-motion, .scene-controls button, .menu summary').forEach((control) => {
    control.addEventListener('pointerdown', (event) => {
      if (!isEnabled() || event.button !== 0 || control.querySelector('.cf-ripple')) return;
      const bounds = control.getBoundingClientRect();
      const ring = document.createElement('span');
      ring.className = 'cf-ripple'; ring.setAttribute('aria-hidden', 'true');
      ring.style.left = `${event.clientX - bounds.left}px`;
      ring.style.top = `${event.clientY - bounds.top}px`;
      control.append(ring);
      setTimeout(() => ring.remove(), 720);
    }, { passive: true });
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { cancelAnimationFrame(pointerFrame); pointerFrame = 0; pending = null; }
  });
  // Native multi-page transitions remain progressive: no prevented navigation or timers.
  root.classList.add('cf-interactive');
}
