"""The Phase 2A BuildReceipt/transport seam uses the real safety verifier."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError
import tempfile
import unittest
from unittest.mock import patch

from confluence_pressroom.public_release_readback import UNKNOWN_ROUTE
from confluence_pressroom.release_checksums import MANIFEST
from confluence_pressroom.release_http import ReadbackResponse, target_url
from confluence_release.artifacts import ReleaseBuilder, read_files, sha256, verify_local_artifact
from confluence_release.readback import ReadbackUnknown, verify_public_artifact
from phase2_support import CONFIG, article, assets


class IntegratedReadbackTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.receipt = ReleaseBuilder(source_assets=assets(self.root), config=CONFIG,
            source_commit='synthetic-source').build((article(),), self.root/'release')
        self.bases = (CONFIG.here_now_base, CONFIG.nor_base)
        self.calls = []
        self.remote = {target_url(base, name): ReadbackResponse(200, data)
            for base in self.bases for name, data in read_files(self.receipt.output).items()}

    def fetch(self, url):
        self.calls.append(url)
        return self.remote.get(url, ReadbackResponse(404, b''))

    def verify(self, **kwargs):
        return verify_public_artifact(self.receipt, CONFIG, fetch=self.fetch, **kwargs)

    def reseal(self):
        """Simulate a newly built but policy-invalid artifact, not recovery repair."""
        files = read_files(self.receipt.output)
        files.pop(MANIFEST)
        raw = ''.join(f'{sha256(data)}  {name}\n' for name, data in sorted(files.items())).encode()
        (self.receipt.output/MANIFEST).write_bytes(raw)
        return replace(self.receipt, checksums={name: sha256(data)
            for name, data in read_files(self.receipt.output).items()})

    def test_receipt_pin_passes_through_real_safety_verifier(self):
        from confluence_release import readback
        with patch.object(readback, 'verify_safety_artifact', wraps=readback.verify_safety_artifact) as spy:
            evidence = self.verify()
        self.assertEqual(spy.call_args.kwargs['expected_manifest_sha256'], self.receipt.checksums[MANIFEST])
        self.assertEqual(evidence['manifest_sha256'], self.receipt.checksums[MANIFEST])
        self.assertEqual(evidence['files'], len(self.receipt.checksums))
        self.assertEqual(evidence['external_discovery'], 'discouraged')

    def test_receipt_pin_is_not_replaced_by_co_tampered_local_manifest(self):
        (self.receipt.output/'index.html').write_bytes(b'tampered')
        self.reseal()
        with self.assertRaises(ValueError):
            self.verify()
        self.assertEqual(self.calls, [])

    def test_noindex_policy_checked_even_with_fresh_consistent_hashes(self):
        p = self.receipt.output/'index.html'
        p.write_bytes(p.read_bytes().replace(b'noindex', b'index'))
        with self.assertRaises(ValueError):
            verify_local_artifact(self.reseal())

    def test_generated_sitemap_checked_even_with_fresh_consistent_hashes(self):
        (self.receipt.output/'sitemap.xml').write_bytes(b'<urlset/>')
        with self.assertRaises(ValueError):
            verify_local_artifact(self.reseal())

    def test_remote_manifest_uses_private_pin_at_each_origin(self):
        for base in self.bases:
            url = target_url(base, MANIFEST)
            before = self.remote[url]
            with self.subTest(base=base):
                self.remote[url] = ReadbackResponse(200, b'different manifest')
                with self.assertRaises(ReadbackUnknown): self.verify()
            self.remote[url] = before

    def test_each_remote_surface_is_independently_verified(self):
        for base in self.bases:
            for name in ('index.html', 'search.json', 'browse.html', self.receipt.article_routes[0]):
                url = target_url(base, name)
                before = self.remote[url]
                with self.subTest(base=base, surface=name):
                    self.remote[url] = ReadbackResponse(200, before.body + b'<p>extra</p>')
                    with self.assertRaises(ReadbackUnknown): self.verify()
                self.remote[url] = before

    def test_remote_sitemap_never_becomes_success(self):
        for base in self.bases:
            url = target_url(base, 'sitemap.xml')
            with self.subTest(base=base):
                self.remote[url] = ReadbackResponse(200, b'<stale/>')
                with self.assertRaises(ReadbackUnknown): self.verify()
            del self.remote[url]

    def test_unknown_and_removed_routes_checked_at_both_bases(self):
        for base in self.bases:
            for route in (UNKNOWN_ROUTE, 'ja/articles/old.html'):
                url = target_url(base, route)
                with self.subTest(base=base, route=route):
                    self.remote[url] = ReadbackResponse(200, b'not really missing')
                    with self.assertRaises(ReadbackUnknown):
                        self.verify(removed_paths=('ja/articles/old.html',))
                del self.remote[url]

    def test_default_transport_is_shared_bounded_no_redirect_reader(self):
        with patch('confluence_release.readback.read_url', side_effect=self.fetch) as reader:
            verify_public_artifact(self.receipt, CONFIG)
        self.assertGreater(reader.call_count, len(self.receipt.checksums))

    def test_explicit_opener_reads_are_bounded(self):
        sizes = []
        test = self
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, size):
                sizes.append(size)
                raise URLError('synthetic interruption')
        with self.assertRaises(ReadbackUnknown):
            verify_public_artifact(self.receipt, CONFIG, opener=lambda *a, **k: Response())
        self.assertTrue(sizes)
        self.assertTrue(all(0 < size <= 32_000_001 for size in sizes))

    def test_opener_that_followed_redirect_cannot_return_success(self):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def geturl(self): return 'https://wrong.invalid/redirected'
            def read(self, size): raise AssertionError('must reject before body read')
        with self.assertRaises(ReadbackUnknown):
            verify_public_artifact(self.receipt, CONFIG, opener=lambda *a, **k: Response())

    def test_two_origins_and_https_remain_required(self):
        for here, nor in ((CONFIG.nor_base, CONFIG.nor_base),
                          ('http://127.0.0.1/one', 'http://127.0.0.1/two')):
            with self.subTest(here=here), self.assertRaises(ReadbackUnknown):
                verify_public_artifact(self.receipt, SimpleNamespace(here_now_base=here, nor_base=nor), fetch=self.fetch)
        self.assertEqual(self.calls, [])

    def test_mutually_exclusive_test_transports(self):
        with self.assertRaises(ValueError):
            verify_public_artifact(self.receipt, CONFIG, opener=object(), fetch=self.fetch)


if __name__ == '__main__':
    unittest.main()
