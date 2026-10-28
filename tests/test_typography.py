"""Local synthetic behavior checks. Real browser layout remains separate QA."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TypographyTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node required for title-fit behavior')
    def test_title_fitting_behavior(self):
        result = subprocess.run(['node', 'tests/typography_title_fit.mjs'], cwd=ROOT,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_readable_css_fallback_and_final_layer(self):
        css = (ROOT / 'prototype/assets/typography.css').read_text()
        styles = (ROOT / 'prototype/assets/styles.css').read_text()
        self.assertTrue(styles.rstrip().endswith("@import url('./typography.css');"))
        self.assertIn('var(--cf-title-fit, var(--cf-title-base))', css)
        self.assertIn('white-space: normal; overflow: visible;', css)
        self.assertIn('.reading-body { font-size: 1.125rem; }', css)
        self.assertNotIn('text-size-adjust', css)


if __name__ == '__main__':
    unittest.main()
