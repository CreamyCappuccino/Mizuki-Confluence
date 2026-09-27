"""Actual loopback HTTP, not a here.now/Nor publication claim."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
import shutil
import tempfile
import unittest

from confluence_release.artifacts import ReleaseBuilder
from confluence_release.readback import ReadbackUnknown, verify_public_artifact
from phase2_support import CONFIG, article, assets


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class LoopbackTests(unittest.TestCase):
    def test_actual_file_readback_and_missing_route(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            builder = ReleaseBuilder(source_assets=assets(root), config=CONFIG, source_commit='synthetic')
            receipt = builder.build((article(),), root/'artifact')
            for mount in ('one', 'two'):
                shutil.copytree(receipt.output, root/mount)
            server = ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(root)))
            thread = Thread(target=server.serve_forever,daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            # A readback port double only: production ReleaseConfig still
            # requires explicit HTTPS origins. Never weaken runtime validation.
            endpoints = SimpleNamespace(here_now_base=base+'/one',nor_base=base+'/two')
            try:
                result=verify_public_artifact(receipt,endpoints,removed_paths=('ja/articles/old.html',),allow_loopback_http=True)
                self.assertEqual(result['checksums'],'exact')
                self.assertEqual(result['origins'],2)
                with self.assertRaises(ReadbackUnknown):
                    verify_public_artifact(receipt,endpoints,removed_paths=('index.html',),allow_loopback_http=True)
            finally:
                server.shutdown();server.server_close();thread.join(timeout=2)
