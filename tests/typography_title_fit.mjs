// Synthetic geometry checks only; not browser typography or screenshot proof.
import assert from 'node:assert/strict';
import fs from 'node:fs';
const source = fs.readFileSync('prototype/assets/title-fit.js', 'utf8');
const { displayUnits, titleDensity, fitTitle, enhanceTitleFit } = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

function fixture({ text = '長い日本語の見出し'.repeat(6), root = 16,
  mobile = false, neededSize = 38, outer = 1440, inner = 1440,
  dpr = 2, pinch = 1, width = 720 } = {}) {
  const properties = new Map();
  let writes = 0;
  let measures = 0;
  const title = {
    textContent: text, dataset: {}, parentElement: {},
    ownerDocument: { documentElement: {} },
    style: {
      removeProperty: (name) => properties.delete(name),
      setProperty: (name, value) => { properties.set(name, value); writes++; },
    },
    getBoundingClientRect() {
      measures++;
      const current = Number.parseFloat(properties.get('--cf-title-fit') || '3') * root;
      return { width, height: current * 1.5 * (current <= neededSize ? 3 : 6) };
    },
  };
  const view = {
    devicePixelRatio: dpr, outerWidth: outer, innerWidth: inner,
    visualViewport: { scale: pinch }, matchMedia: () => ({ matches: mobile }),
    getComputedStyle(node) {
      const current = Number.parseFloat(properties.get('--cf-title-fit') || '3') * root;
      return node === title ? {
        fontSize: String(3 * root), lineHeight: String(current * 1.5),
        getPropertyValue: () => mobile ? '1.875' : '2.125',
      } : { fontSize: String(root) };
    },
  };
  return { title, view, properties, writes: () => writes, measures: () => measures };
}

assert.ok(displayUnits('瑞希') > displayUnits('ab'));
assert.equal(titleDensity('短いタイトル'), 'display');
assert.equal(titleDensity('A very long English title that still needs to be read in full '.repeat(4)), 'compact');

for (const text of ['日本語の長いタイトル'.repeat(8), 'A long English title '.repeat(14)]) {
  const f = fixture({ text });
  fitTitle(f.title, f.view);
  const size = Number.parseFloat(f.properties.get('--cf-title-fit')) * 16;
  assert.ok(size >= 34 && size <= 38);
  assert.equal(f.title.textContent, text);
  assert.equal(f.title.dataset.cfTitleLines, '3');
  assert.ok(f.measures() <= 13, 'bounded layout reads');
}

const overflowing = fixture({ mobile: true, neededSize: 20 });
fitTitle(overflowing.title, overflowing.view);
assert.equal(overflowing.properties.get('--cf-title-fit'), '1.875rem');
assert.equal(overflowing.title.dataset.cfTitleLines, '6', 'readable floor allows extra lines');

for (const options of [{ root: 20 }, { outer: 1440, inner: 720 }, { pinch: 2 }, { dpr: 4 }]) {
  const f = fixture(options);
  fitTitle(f.title, f.view, { baselineDpr: 2 });
  assert.equal(f.writes(), 0, 'enlargement must not be counteracted');
  assert.equal(f.properties.size, 0);
}
const hidden = fixture({ width: 0 });
fitTitle(hidden.title, hidden.view);
assert.equal(hidden.writes(), 0);

// Container resizing, fonts and locale can schedule; scroll never does.
const f = fixture();
const viewEvents = new Map();
const docEvents = new Map();
let scheduled = 0;
let run;
f.view.addEventListener = (name, fn) => viewEvents.set(name, fn);
f.view.requestAnimationFrame = (fn) => { scheduled++; run = fn; return scheduled; };
const doc = { querySelectorAll: () => [f.title], addEventListener: (n, fn) => docEvents.set(n, fn) };
enhanceTitleFit(doc, f.view);
assert.equal(scheduled, 1);
viewEvents.get('resize')();
docEvents.get('confluence:locale')();
assert.equal(scheduled, 1, 'coalesce pending updates');
run();
assert.equal(scheduled, 1, 'no recurring animation loop');
assert.ok(!viewEvents.has('scroll'));
viewEvents.get('resize')();
assert.equal(scheduled, 2);
console.log('PASS title density, JP/EN bounded fit, floor overflow, enlargement, hidden title, event scheduling');
