"""Owner-local profile handling and explicit CLI opt-in. No DB/provider calls."""
from contextlib import redirect_stdout
from dataclasses import asdict
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from confluence_release.html_policy import load_html_policy
from confluence_release.cli import main
from phase2_support import CONFIG
from test_here_now_html_policy import policy


class HtmlPolicyLoadingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.path = self.root / 'profile.json'
        self.path.write_text(json.dumps(asdict(policy()))); self.path.chmod(0o600)
        self.config = self.root / 'release.json'
        self.config.write_text(json.dumps(dict(site_base=CONFIG.site_base, here_now_slug=CONFIG.here_now_slug,
            nor_base=CONFIG.nor_base, project_root='/synthetic/project', release_root='/synthetic/releases')))

    def test_loads_explicit_profile_and_captures_hash(self):
        self.assertEqual(load_html_policy(self.path), policy())

    def test_missing_unknown_and_duplicate_fields_rejected(self):
        values = asdict(policy())
        for raw in (json.dumps(dict(values, token='do-not-load')),
                    json.dumps({k: v for k, v in values.items() if k != 'format'}),
                    json.dumps(values)[:-1] + ',"title":"different"}', '[]'):
            with self.subTest(raw=raw):
                self.path.write_text(raw)
                with self.assertRaises(ValueError): load_html_policy(self.path)

    def test_file_is_bounded(self):
        self.path.write_bytes(b' ' * 16385)
        with self.assertRaises(ValueError): load_html_policy(self.path)

    def test_permissions_must_be_0600(self):
        for mode in (0o644, 0o660, 0o400, 0o777):
            self.path.chmod(mode)
            with self.assertRaises(ValueError): load_html_policy(self.path)

    def test_other_owner_rejected(self):
        with patch('confluence_release.html_policy.os.getuid', return_value=os.getuid() + 1):
            with self.assertRaises(ValueError): load_html_policy(self.path)

    def test_symlink_and_non_regular_file_rejected(self):
        link = self.root / 'link'; link.symlink_to(self.path)
        with self.assertRaises((OSError, ValueError)): load_html_policy(link)
        with self.assertRaises((OSError, ValueError)): load_html_policy(self.root)
        fifo = self.root / 'fifo'; os.mkfifo(fifo, 0o600)
        with self.assertRaises((OSError, ValueError)): load_html_policy(fifo)

    def test_plan_shows_policy_hash_without_constructing_worker(self):
        out = StringIO()
        with patch('confluence_release.cli._worker', side_effect=AssertionError), redirect_stdout(out):
            result = main(['--config', str(self.config), '--html-policy', str(self.path), 'plan'])
        self.assertEqual(result, 0)
        self.assertIn(policy().sha256, out.getvalue())
        self.assertNotIn('Synthetic description.', out.getvalue())

    def test_reconcile_passes_immutable_profile_to_worker(self):
        from types import SimpleNamespace
        captured = []
        class Worker:
            def reconcile(self, ref):
                captured.append(ref)
                return SimpleNamespace(job_ref=ref, status='published', step='complete', detail='test')
        with patch('confluence_release.cli._worker', return_value=Worker()) as factory, redirect_stdout(StringIO()):
            result = main(['--config', str(self.config), '--html-policy', str(self.path), 'reconcile', 'JOB0154'])
        self.assertEqual(result, 0)
        self.assertEqual(factory.call_args.kwargs['html_policy'], policy())
        self.assertEqual(captured, ['JOB0154'])

    def test_wrong_target_stops_before_worker(self):
        self.path.write_text(json.dumps(asdict(policy(nor_base='https://other.invalid/confluence'))))
        with patch('confluence_release.cli._worker') as worker, redirect_stdout(StringIO()):
            self.assertEqual(main(['--config', str(self.config), '--html-policy', str(self.path), 'reconcile', 'JOB0154']), 1)
        worker.assert_not_called()

    def test_no_silent_profile_for_other_commands_or_unscoped_run(self):
        for args in (['retry', 'JOB0154'], ['init-projection'], ['run']):
            with self.subTest(args=args), patch('confluence_release.cli._worker') as worker, redirect_stdout(StringIO()):
                result = main(['--config', str(self.config), '--html-policy', str(self.path), *args])
                self.assertEqual(result, 1)
                worker.assert_not_called()
