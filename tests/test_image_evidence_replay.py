"""V2 uses the existing offline pair replay tool, with no write or network."""
from contextlib import redirect_stdout
from dataclasses import asdict
import hashlib
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from replay_here_now_html import main
from image_html_test_support import SOURCE, image_policy, literal_image_block
from phase2_support import CONFIG


class ImageEvidenceReplayTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.profile=self.root/'image-profile.json'
        self.profile.write_text(json.dumps(asdict(image_policy())));self.profile.chmod(0o600)
        self.original=self.root/'original.html';self.original.write_bytes(SOURCE)
        self.remote=self.root/'remote.html'
        self.remote.write_bytes(SOURCE.replace(b'</head>',literal_image_block(CONFIG.nor_base)+b'</head>'))
        self.args=['--profile',str(self.profile),'--original',str(self.original),
            '--remote',str(self.remote),'--expected-sha256',hashlib.sha256(SOURCE).hexdigest(),
            '--base',CONFIG.nor_base,'--relative','index.html']

    def test_v2_pair_replay_reports_policy_and_does_not_rewrite_evidence(self):
        before={p.name:p.read_bytes() for p in self.root.iterdir()};out=StringIO()
        with redirect_stdout(out):self.assertEqual(main(self.args),0)
        self.assertIn('here-now-og/v2',out.getvalue())
        self.assertIn('not JOB completion',out.getvalue())
        self.assertEqual({p.name:p.read_bytes() for p in self.root.iterdir()},before)

    def test_raw_pair_is_not_mislabelled_as_transformed(self):
        self.remote.write_bytes(SOURCE);out=StringIO()
        with redirect_stdout(out):self.assertEqual(main(self.args),0)
        self.assertIn('comparison=raw-exact',out.getvalue())

    def test_wrong_original_pin_and_changed_image_reference_fail(self):
        args=list(self.args);args[args.index('--expected-sha256')+1]='0'*64
        with redirect_stdout(StringIO()):self.assertEqual(main(args),1)
        self.remote.write_bytes(self.remote.read_bytes().replace(b'/og/synthetic-confluence',b'/og/other'))
        with redirect_stdout(StringIO()):self.assertEqual(main(self.args),1)

    def test_remote_order_is_not_learned_by_replay(self):
        block=literal_image_block(CONFIG.nor_base)
        swapped=b'\n'.join(reversed(block.split(b'\n')))
        self.remote.write_bytes(SOURCE.replace(b'</head>',swapped+b'</head>'))
        with redirect_stdout(StringIO()):self.assertEqual(main(self.args),1)
