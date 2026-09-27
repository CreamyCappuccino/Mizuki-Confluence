"""Loopback HTTP integration for migrated readback; no external hosts or DB."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import URLError

from release_safety_test_support import HTML, artifact, repository
from confluence_pressroom.release_checksums import ReleaseReadbackMismatch
from confluence_pressroom.release_http import ReleaseReadbackUnavailable, read_url, validate_base
from confluence_pressroom.release_runtime_guard import ReleaseRuntimeGuard
from confluence_pressroom.release_execution import run_guarded_release
from confluence_pressroom.public_release_readback import verify_public_artifact


class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = {}
        cls.seen = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                cls.seen.append((self.path, self.headers.get('User-Agent')))
                status, body, headers = cls.paths.get(self.path, (404, b'', {}))
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.server.daemon_threads = True
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        type(self).paths.clear()
        type(self).seen.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'artifact'
        self.root.mkdir()
        self.pin = artifact(self.root)
        for base in ('/host', '/router/confluence'):
            for path in self.root.rglob('*'):
                if path.is_file():
                    self.paths[base + '/' + path.relative_to(self.root).as_posix()] = (200, path.read_bytes(), {})

    def verify(self):
        return verify_public_artifact(self.root, here_now_base=self.origin + '/host',
                                      nol_base=self.origin + '/router/confluence',
                                      expected_manifest_sha256=self.pin,
                                      removed_paths=('ja/articles/art8999.html',),
                                      allow_loopback_http=True)

    def test_real_loopback_reads_and_404_pass(self):
        self.assertEqual(self.verify()['origins'], 2)
        self.assertIn(('/router/confluence/ja/articles/art8999.html', 'confluence-release-worker/1.0'), self.seen)

    def test_http_requires_explicit_loopback_exception(self):
        with self.assertRaises(ReleaseReadbackMismatch):
            validate_base(self.origin)
        self.assertEqual(validate_base(self.origin, allow_loopback_http=True), self.origin)

    def test_http_redirect_is_not_followed_to_success(self):
        self.paths['/redirect'] = (302, b'', {'Location': self.origin + '/target'})
        self.paths['/target'] = (200, b'should not be read', {})
        with self.assertRaises(ReleaseReadbackMismatch):
            read_url(self.origin + '/redirect')
        self.assertNotIn('/target', [p for p, _ in self.seen])

    def test_server_failure_is_unknown_not_404(self):
        self.paths['/failed'] = (503, b'unavailable', {})
        with self.assertRaises(ReleaseReadbackUnavailable):
            read_url(self.origin + '/failed')

    def test_timeout_propagates_as_unknown(self):
        with patch('confluence_pressroom.release_http.build_opener') as opener:
            opener.return_value.open.side_effect = URLError('synthetic timeout')
            with self.assertRaises(ReleaseReadbackUnavailable):
                read_url(self.origin + '/timeout')

    def test_post_delivery_tamper_blocks_finalize(self):
        project = Path(self.temp.name) / 'project'
        project.mkdir()
        repository(project)
        events = []

        def deliver(*args):
            events.append('deliver')
            self.paths['/router/confluence/ja/articles/art9001.html'] = (200, HTML.encode() + b'extra body', {})
            return 'synthetic receipt'

        with self.assertRaises(ReleaseReadbackMismatch):
            run_guarded_release(
                guard=ReleaseRuntimeGuard.capture(project), release_root=Path(self.temp.name) / 'release',
                claim=lambda: 'synthetic job', build=lambda _: self.root, deliver=deliver,
                readback=lambda *_: self.verify(), finalize=lambda *_: events.append('finalize'))
        self.assertEqual(events, ['deliver'])

    def test_complete_safety_envelope_with_http_readback(self):
        project = Path(self.temp.name) / 'project'
        project.mkdir()
        repository(project)
        events = []
        result = run_guarded_release(
            guard=ReleaseRuntimeGuard.capture(project), release_root=Path(self.temp.name) / 'release',
            claim=lambda: 'synthetic job', build=lambda _: self.root,
            deliver=lambda *_: events.append('deliver') or 'receipt',
            readback=lambda *_: self.verify(),
            finalize=lambda _, evidence: events.append('finalize') or evidence['checksums'])
        self.assertEqual(result, 'exact')
        self.assertEqual(events, ['deliver', 'finalize'])


if __name__ == '__main__':
    unittest.main()
