from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from confluence_release.cli import load_settings, main
from phase2_support import CONFIG


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'release.json'
        self.values = dict(site_base=CONFIG.site_base, here_now_slug=CONFIG.here_now_slug,
            nor_base=CONFIG.nor_base, project_root='/synthetic/project', release_root='/synthetic/releases')
        self.path.write_text(json.dumps(self.values))
    def tearDown(self):
        self.temp.cleanup()
    def test_plan_never_initializes_worker(self):
        out=StringIO()
        with patch('confluence_release.cli._worker', side_effect=AssertionError), redirect_stdout(out):
            self.assertEqual(main(['--config',str(self.path),'plan']),0)
        self.assertIn('runtime: not started',out.getvalue())
    def test_unknown_settings_are_rejected(self):
        self.path.write_text(json.dumps(dict(self.values, password='never-put-secrets-here')))
        with self.assertRaises(ValueError):load_settings(self.path)
    def test_relative_private_root_is_rejected(self):
        self.path.write_text(json.dumps(dict(self.values, release_root='relative')))
        with self.assertRaises(ValueError):load_settings(self.path)
    def test_connection_error_never_prints_secret(self):
        out=StringIO()
        with patch('confluence_release.cli._worker',side_effect=ValueError('private-dsn')),redirect_stdout(out):
            self.assertEqual(main(['--config',str(self.path),'run','JOB99990001']),1)
        self.assertNotIn('private-dsn',out.getvalue())
