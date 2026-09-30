"""Offline replay command remains read-only and does not call a provider."""
from contextlib import redirect_stdout
from dataclasses import asdict
import hashlib
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from replay_here_now_html import main
from phase2_support import CONFIG
from test_here_now_html_policy import SOURCE, literal_block, policy


class EvidenceReplayTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.profile = self.root / 'policy.json'
        self.profile.write_text(json.dumps(asdict(policy()))); self.profile.chmod(0o600)
        self.original = self.root / 'original.html'; self.original.write_bytes(SOURCE)
        self.remote = self.root / 'remote.html'
        self.remote.write_bytes(SOURCE.replace(b'</head>', literal_block(CONFIG.nor_base) + b'</head>'))
        self.args = ['--profile', str(self.profile), '--original', str(self.original),
                     '--remote', str(self.remote), '--expected-sha256', hashlib.sha256(SOURCE).hexdigest(),
                     '--base', CONFIG.nor_base, '--relative', 'index.html']

    def test_transformed_pair_passes_without_modifying_files(self):
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        out = StringIO()
        with redirect_stdout(out): self.assertEqual(main(self.args), 0)
        self.assertIn('here-now-og/v1', out.getvalue())
        self.assertIn('not JOB completion', out.getvalue())
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_raw_pair_reports_raw_exact(self):
        self.remote.write_bytes(SOURCE)
        out = StringIO()
        with redirect_stdout(out): self.assertEqual(main(self.args), 0)
        self.assertIn('comparison=raw-exact', out.getvalue())

    def test_wrong_trusted_original_hash_rejects(self):
        args = list(self.args); args[args.index('--expected-sha256') + 1] = '0' * 64
        with redirect_stdout(StringIO()): self.assertEqual(main(args), 1)

    def test_remote_extra_bytes_reject(self):
        self.remote.write_bytes(self.remote.read_bytes() + b'changed')
        with redirect_stdout(StringIO()): self.assertEqual(main(self.args), 1)
