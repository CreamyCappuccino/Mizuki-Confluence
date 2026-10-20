/* Lightweight edge filaments. No network, tracking, text mutation or dependencies. */
export function createResonanceField() {
  const root = document.documentElement;
  const canvas = document.createElement('canvas');
  canvas.className = 'cf-field';
  canvas.setAttribute('aria-hidden', 'true');
  document.body.prepend(canvas);
  const ctx = canvas.getContext('2d', { alpha: true });
  if (!ctx) {
    canvas.remove();
    return { setEnabled() {}, refresh() {}, destroy() {} };
  }
  const mobile = matchMedia('(max-width: 900px), (pointer: coarse)');
  const contrast = matchMedia('(forced-colors: active)');
  let width = 0, height = 0, frame = 0, last = 0, elapsed = 0;
  let enabled = false, signal = '#23765f', gold = '#95713b';
  let pointer = .5;

  function curveY(progress) { return -24 + progress * (height + 48); }
  function curveX(progress, index, side, time) {
    const edge = Math.min(width * (mobile.matches ? .105 : .15), 208);
    const wave = Math.sin(progress * Math.PI * 2.2 + index * .39 + time * .08);
    const cross = Math.cos(progress * Math.PI * 3.7 - index * .28 - time * .045);
    const x = 9 + edge * (.34 + wave * .23 + cross * .09 + index * .052);
    const attraction = enabled && !mobile.matches ? (pointer - .5) * 5 : 0;
    return side === 0 ? x + attraction : width - x + attraction;
  }

  function draw(time) {
    ctx.clearRect(0, 0, width, height);
    if (contrast.matches) return;
    const lines = mobile.matches ? 5 : 8;
    ctx.lineWidth = .65;
    for (let side = 0; side < 2; side += 1) {
      for (let line = 0; line < lines; line += 1) {
        ctx.strokeStyle = line % 3 === 0 ? gold : signal;
        ctx.globalAlpha = mobile.matches ? .13 : .16 + (line % 3) * .027;
        ctx.beginPath();
        for (let step = 0; step <= 64; step += 1) {
          const p = step / 64;
          const x = curveX(p, line, side, time), y = curveY(p);
          if (step === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
        const p = ((line * .143 + side * .21 + time * (.009 + line * .0007)) % 1);
        const x = curveX(p, line, side, time), y = curveY(p);
        ctx.globalAlpha = .72;
        ctx.fillStyle = line % 3 === 0 ? gold : signal;
        ctx.beginPath(); ctx.arc(x, y, line % 2 ? 1.4 : 2, 0, Math.PI * 2); ctx.fill();
        if (line % 3 === 0) {
          ctx.globalAlpha = .13;
          ctx.beginPath(); ctx.arc(x, y, 6, 0, Math.PI * 2); ctx.fill();
          ctx.globalAlpha = .34;
          ctx.beginPath(); ctx.moveTo(x - 5, y); ctx.lineTo(x + 5, y);
          ctx.moveTo(x, y - 5); ctx.lineTo(x, y + 5); ctx.stroke();
        }
      }
    }
    ctx.globalAlpha = 1;
  }

  function canAnimate() { return enabled && !document.hidden && !mobile.matches && !contrast.matches; }
  function tick(now) {
    frame = 0;
    if (!canAnimate()) return;
    if (!last || now - last >= 40) {
      elapsed += last ? Math.min((now - last) / 1000, .1) : 0;
      last = now; draw(elapsed);
    }
    frame = requestAnimationFrame(tick);
  }
  function sync() {
    cancelAnimationFrame(frame); frame = 0; last = 0;
    if (!document.hidden) draw(enabled ? elapsed : 0);
    if (canAnimate()) frame = requestAnimationFrame(tick);
  }
  function refresh() {
    width = window.innerWidth; height = window.innerHeight;
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const style = getComputedStyle(root);
    signal = style.getPropertyValue('--cf-signal').trim() || '#23765f';
    gold = style.getPropertyValue('--cf-gold').trim() || '#95713b';
    sync();
  }
  function onPointer(event) { if (canAnimate()) pointer = event.clientX / Math.max(width, 1); }
  function onVisibility() { sync(); }
  window.addEventListener('pointermove', onPointer, { passive: true });
  window.addEventListener('resize', refresh, { passive: true });
  document.addEventListener('visibilitychange', onVisibility);
  mobile.addEventListener?.('change', refresh);
  contrast.addEventListener?.('change', refresh);
  refresh();
  return {
    setEnabled(value) { enabled = Boolean(value); sync(); },
    refresh,
    destroy() {
      enabled = false; cancelAnimationFrame(frame);
      window.removeEventListener('pointermove', onPointer);
      window.removeEventListener('resize', refresh);
      document.removeEventListener('visibilitychange', onVisibility);
      mobile.removeEventListener?.('change', refresh);
      contrast.removeEventListener?.('change', refresh);
      canvas.remove();
    },
  };
}
