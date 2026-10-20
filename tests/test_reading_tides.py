"""Node unit checks for decoration state; no browser or public network involved."""
import base64
from pathlib import Path
import shutil
import subprocess
import unittest


ASSETS = Path(__file__).resolve().parents[1] / 'prototype/assets'
FIXTURE = r"""
import assert from 'node:assert/strict';
globalThis.document = {hidden:false};
globalThis.innerHeight = 1000;
let reads = 0;
function node(top, height) {
  return {
    top, height,
    classList: {values:new Set(), add(s){this.values.add(s)}, remove(s){this.values.delete(s)}},
    getBoundingClientRect(){reads++; return {top:this.top,bottom:this.top+this.height,height:this.height}},
    set textContent(value){throw Error('text mutation')},
    set innerHTML(value){throw Error('HTML mutation')},
  };
}
const a=node(100,80), b=node(400,80), c=node(1100,80);
const article=node(50,2000);
article.style={values:new Map(),setProperty(k,v){this.values.set(k,v)}};
article.querySelectorAll=(selector)=>{assert.equal(selector,':scope > p'); return [a,b,c]};
"""


class ReadingTidesTests(unittest.TestCase):
    def run_js(self, body):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is needed for the event-state unit test')
        module = base64.b64encode((ASSETS / 'resonance-interaction.js').read_bytes()).decode()
        source = f"import {{createReadingTides}} from 'data:text/javascript;base64,{module}';\n"
        result = subprocess.run([node, '--input-type=module', '-e', source + FIXTURE + body],
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_non_article_pages_are_inert(self):
        self.run_js("const tides=createReadingTides(null); tides.setEnabled(true); tides.update(); assert.equal(reads,0);")

    def test_focus_tracks_viewport_without_mutating_text(self):
        self.run_js("""
const tides=createReadingTides(article); tides.setEnabled(true);
assert.equal(article.style.values.get('--cf-reader-y'),'390.0px');
assert(b.classList.values.has('cf-reading-current'));
a.top=400; b.top=-100; tides.update();
assert(a.classList.values.has('cf-reading-current'));
assert(!b.classList.values.has('cf-reading-current'));
assert(!c.classList.values.has('cf-reading-current'));
""")

    def test_off_and_hidden_do_not_read_or_update_geometry(self):
        self.run_js("""
const tides=createReadingTides(article); tides.setEnabled(true);
const y=article.style.values.get('--cf-reader-y');
tides.setEnabled(false); reads=0; article.top=-300; tides.update();
assert.equal(reads,0); assert.equal(article.style.values.get('--cf-reader-y'),y);
assert(!b.classList.values.has('cf-reading-current'));
document.hidden=true; tides.setEnabled(true); tides.update(); assert.equal(reads,0);
document.hidden=false; tides.update(); assert(reads>0);
""")

    def test_offscreen_article_clears_the_current_marker(self):
        self.run_js("""
const tides=createReadingTides(article); tides.setEnabled(true);
article.top=1200; tides.update();
assert(!b.classList.values.has('cf-reading-current'));
""")

    def test_css_keeps_decorations_noninteractive_and_provides_still_modes(self):
        css = (ASSETS / 'resonance.css').read_text()
        tides = css.split('/* Reading Tides:', 1)[1].split('.reading-body > h2', 1)[0]
        self.assertIn('pointer-events: none', tides)
        self.assertIn('z-index: -1', tides)
        self.assertIn('prefers-reduced-motion: reduce', tides)
        self.assertIn('forced-colors: active', tides)
        self.assertIn('print', tides)
        self.assertIn('--cf-tide-strength: .4', tides)
        self.assertNotIn('mix-blend-mode', tides)
        self.assertNotIn('filter:', tides)


if __name__ == '__main__':
    unittest.main()
