"""Synthetic two-origin readback; not an external deployment or real JOB test."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from release_safety_test_support import HTML, artifact, seal
from confluence_pressroom.release_checksums import (
    ReleaseReadbackMismatch, checksum_entries, verify_local_artifact,
)
from confluence_pressroom.release_http import (
    ReadbackResponse, ReleaseReadbackUnavailable, target_url, validate_base,
)
from confluence_pressroom.public_release_readback import verify_public_artifact


class ReadbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pin = artifact(self.root)
        self.bases = ('https://host.invalid/release', 'https://router.invalid/confluence')
        self.calls = []
        self.remote = {}
        self.sync()

    def sync(self):
        self.remote = {target_url(base, p.relative_to(self.root).as_posix()): ReadbackResponse(200, p.read_bytes())
                       for base in self.bases for p in self.root.rglob('*') if p.is_file()}

    def fetch(self, url):
        self.calls.append(url)
        return self.remote.get(url, ReadbackResponse(404, b''))

    def verify(self, **kw):
        return verify_public_artifact(self.root, here_now_base=self.bases[0], nol_base=self.bases[1],
                                      expected_manifest_sha256=self.pin, fetch=self.fetch, **kw)

    def provider_html(self, base, relative, *, title="Confluence",
                      description="A synthetic site for testing publication workflows and content retrieval.",
                      og_url=None, og_type="website", twitter="summary", extra=b"", duplicate=False):
        local = (self.root / relative).read_bytes()
        url = target_url(base, relative) if og_url is None else og_url
        block = (
            f'<meta property="og:title" content="{title}" />\n'
            f'<meta property="og:description" content="{description}" />\n'
            f'<meta property="og:url" content="{url}" />\n'
            f'<meta property="og:type" content="{og_type}" />\n'
            f'<meta name="twitter:card" content="{twitter}" />'
        ).encode()
        if duplicate:
            block += b"\n" + block
        block += extra
        return local.replace(b"</head>", block + b"</head>", 1)


    def test_exact_two_origin_artifact_and_removed_paths_pass(self):
        result = self.verify(removed_paths=('ja/articles/art8999.html',))
        self.assertEqual(result['checksums'], 'exact')
        self.assertEqual(result['origins'], 2)
        self.assertEqual(result['external_discovery'], 'discouraged')
        self.assertIn(self.bases[1] + '/ja/articles/art9001.html', self.calls)
        self.assertIn(self.bases[0] + '/ja/articles/art8999.html', self.calls)

    def test_exact_provider_social_meta_injection_is_accepted_for_html_only(self):
        html_paths = ('index.html', 'browse.html', 'ja/articles/art9001.html')
        for base in self.bases:
            for relative in html_paths:
                self.remote[target_url(base, relative)] = ReadbackResponse(
                    200, self.provider_html(base, relative)
                )
        result = self.verify()
        self.assertEqual(result['checksums'], 'exact-with-provider-html-policy')
        self.assertEqual(result['provider_html_transforms'], len(html_paths) * len(self.bases))

    def test_provider_meta_og_url_is_bound_to_exact_origin_and_route(self):
        relative = 'ja/articles/art9001.html'
        target = target_url(self.bases[1], relative)
        wrong_urls = (
            target_url(self.bases[0], relative),
            self.bases[1] + '/ja/articles/other.html',
            target + '?x=1',
            target + '#fragment',
        )
        for wrong in wrong_urls:
            with self.subTest(og_url=wrong):
                self.sync()
                self.remote[target] = ReadbackResponse(
                    200, self.provider_html(self.bases[1], relative, og_url=wrong)
                )
                with self.assertRaises(ReleaseReadbackMismatch):
                    self.verify()

    def test_provider_meta_values_and_exact_five_tag_shape_are_fixed(self):
        relative = 'index.html'
        target = target_url(self.bases[0], relative)
        cases = (
            dict(title='Other'),
            dict(description='Other description'),
            dict(og_type='article'),
            dict(twitter='summary_large_image'),
            dict(extra=b'\n<meta name="extra" content="not-allowed" />'),
            dict(duplicate=True),
        )
        for values in cases:
            with self.subTest(values=values):
                self.sync()
                self.remote[target] = ReadbackResponse(
                    200, self.provider_html(self.bases[0], relative, **values)
                )
                with self.assertRaises(ReleaseReadbackMismatch):
                    self.verify()

    def test_provider_meta_must_be_immediately_before_head_close(self):
        relative = 'index.html'
        target = target_url(self.bases[0], relative)
        valid = self.provider_html(self.bases[0], relative)
        block_start = valid.index(b'<meta property="og:title"')
        block_end = valid.index(b'</head>')
        block = valid[block_start:block_end]
        local = (self.root / relative).read_bytes()
        moved = local.replace(b'<body>', block + b'<body>', 1)
        self.remote[target] = ReadbackResponse(200, moved)
        with self.assertRaises(ReleaseReadbackMismatch):
            self.verify()

    def test_provider_meta_does_not_hide_any_other_html_change(self):
        relative = 'ja/articles/art9001.html'
        target = target_url(self.bases[1], relative)
        transformed = self.provider_html(self.bases[1], relative)
        self.remote[target] = ReadbackResponse(
            200, transformed.replace(b'synthetic</article>', b'tampered</article>')
        )
        with self.assertRaises(ReleaseReadbackMismatch):
            self.verify()

    def test_provider_policy_never_normalizes_non_html_files(self):
        target = target_url(self.bases[0], 'search.json')
        self.remote[target] = ReadbackResponse(
            200, self.remote[target].body + b'\n<!-- provider-looking change -->'
        )
        with self.assertRaises(ReleaseReadbackMismatch):
            self.verify()

    def test_each_surface_checksum_is_independent(self):
        for base in self.bases:
            for name in ('index.html', 'browse.html', 'search.json', 'ja/articles/art9001.html'):
                with self.subTest(base=base, surface=name):
                    self.sync()
                    self.remote[base + '/' + name] = ReadbackResponse(200, b'wrong')
                    with self.assertRaises(ReleaseReadbackMismatch):
                        self.verify()

    def test_appended_article_body_fails(self):
        url = self.bases[1] + '/ja/articles/art9001.html'
        self.remote[url] = ReadbackResponse(200, HTML.encode() + b'<p>extra synthetic body</p>')
        with self.assertRaises(ReleaseReadbackMismatch):
            self.verify()

    def test_removed_route_present_on_either_base_fails(self):
        for base in self.bases:
            with self.subTest(base=base):
                self.sync()
                self.remote[base + '/ja/articles/art8999.html'] = ReadbackResponse(200, HTML.encode())
                with self.assertRaises(ReleaseReadbackMismatch):
                    self.verify(removed_paths=('ja/articles/art8999.html',))

    def test_soft_404_unknown_route_fails(self):
        self.remote[self.bases[1] + '/__pressroom-release-worker-not-found__'] = ReadbackResponse(200, b'Not found')
        with self.assertRaises(ReleaseReadbackMismatch):
            self.verify()

    def test_unknown_transport_is_not_withdrawal_success(self):
        def fetch(_url):
            raise ReleaseReadbackUnavailable('synthetic timeout')
        with self.assertRaises(ReleaseReadbackUnavailable):
            verify_public_artifact(self.root, here_now_base=self.bases[0], nol_base=self.bases[1],
                                   expected_manifest_sha256=self.pin, fetch=fetch,
                                   removed_paths=('ja/articles/art8999.html',))

    def test_local_artifact_edit_fails_before_network(self):
        (self.root / 'index.html').write_text(HTML + '<p>extra</p>')
        with self.assertRaises(ReleaseReadbackMismatch):
            self.verify()
        self.assertEqual(self.calls, [])

    def test_manifest_and_body_tamper_does_not_change_private_pin(self):
        (self.root / 'index.html').write_text(HTML + '<p>extra</p>')
        seal(self.root)
        with self.assertRaises(ReleaseReadbackMismatch):
            self.verify()
        self.assertEqual(self.calls, [])

    def test_manifest_duplicate_and_traversal_rejected(self):
        digest = hashlib.sha256(b'x').hexdigest()
        for relative in ('../private', '/absolute', 'a/../private', 'a//b', 'a%2fb', 'a\\b', 'a?x', 'a#x', 'checksums.sha256'):
            with self.subTest(path=relative):
                raw = f'{digest}  {relative}\n'.encode()
                (self.root / 'checksums.sha256').write_bytes(raw)
                with self.assertRaises(ReleaseReadbackMismatch):
                    checksum_entries(self.root, expected_manifest_sha256=hashlib.sha256(raw).hexdigest())
        raw = (f'{digest}  index.html\n' * 2).encode()
        (self.root / 'checksums.sha256').write_bytes(raw)
        with self.assertRaises(ReleaseReadbackMismatch):
            checksum_entries(self.root, expected_manifest_sha256=hashlib.sha256(raw).hexdigest())

    def test_invalid_digest_and_empty_manifest_fail(self):
        for raw in (b'', b'x' * 64 + b'  index.html\n', b'bad separator index.html\n'):
            (self.root / 'checksums.sha256').write_bytes(raw)
            with self.assertRaises(ReleaseReadbackMismatch):
                checksum_entries(self.root, expected_manifest_sha256=hashlib.sha256(raw).hexdigest())

    def test_extra_missing_and_symlink_files_fail(self):
        extra = self.root / 'private.txt'
        extra.write_text('synthetic non-public')
        with self.assertRaises(ReleaseReadbackMismatch):
            self.verify()
        extra.unlink()
        (self.root / 'search.json').unlink()
        with self.assertRaises(ReleaseReadbackMismatch):
            self.verify()
        self.pin = artifact(self.root)
        (self.root / 'search.json').unlink()
        (self.root / 'search.json').symlink_to(self.root / 'index.html')
        with self.assertRaises(ReleaseReadbackMismatch):
            self.verify()

    def test_noindex_and_conflicting_directives_fail_even_when_hashed(self):
        for content in ('<html><head></head></html>', HTML.replace('noindex', 'index'),
                        HTML.replace('</head>', '<meta name="robots" content="all"></head>')):
            (self.root / 'index.html').write_text(content)
            self.pin = seal(self.root)
            self.sync()
            with self.subTest(content=content), self.assertRaises(ReleaseReadbackMismatch):
                self.verify()

    def test_sitemap_and_robots_sitemap_directive_fail(self):
        (self.root / 'sitemap.xml').write_text('<synthetic/>')
        self.pin = seal(self.root)
        with self.assertRaises(ReleaseReadbackMismatch):
            self.verify()
        (self.root / 'sitemap.xml').unlink()
        (self.root / 'robots.txt').write_text('Sitemap: https://example.invalid/sitemap.xml')
        self.pin = seal(self.root)
        with self.assertRaises(ReleaseReadbackMismatch):
            self.verify()

    def test_host_robots_exception_is_explicit_and_local_to_first_base(self):
        url = self.bases[0] + '/robots.txt'
        self.remote[url] = ReadbackResponse(200, b'# host-owned\nUser-agent: *\nAllow: /\n')
        with self.assertRaises(ReleaseReadbackMismatch):
            self.verify()
        self.assertEqual(self.verify(here_now_robots='host-owned-open')['reserved'], 1)
        self.remote[self.bases[1] + '/robots.txt'] = self.remote[url]
        with self.assertRaises(ReleaseReadbackMismatch):
            self.verify(here_now_robots='host-owned-open')

    def test_host_robots_exception_does_not_bypass_html_noindex(self):
        (self.root / 'index.html').write_text(HTML.replace('noindex', 'index'))
        self.pin = seal(self.root)
        self.sync()
        with self.assertRaises(ReleaseReadbackMismatch):
            self.verify(here_now_robots='host-owned-open')

    def test_invalid_config_and_removed_paths_fail_without_network(self):
        for base in ('https://user:pass@x.invalid', 'https://x.invalid/a/../b',
                     'https://x.invalid/%2fprivate', 'http://x.invalid', 'https://x.invalid?q=x',
                     'https://x.invalid//a', 'https://x.invalid/a#b'):
            with self.subTest(base=base), self.assertRaises(ReleaseReadbackMismatch):
                validate_base(base)
        with self.assertRaises(ReleaseReadbackMismatch):
            self.verify(removed_paths=('../private',))
        with self.assertRaises(ReleaseReadbackMismatch):
            self.verify(removed_paths=('index.html',))
        self.assertEqual(self.calls, [])

    def test_base_prefix_and_unicode_filename_are_preserved(self):
        path = self.root / 'assets' / '窓 1.txt'
        path.parent.mkdir()
        path.write_text('synthetic')
        self.pin = seal(self.root)
        self.sync()
        self.verify()
        self.assertIn(self.bases[1] + '/assets/%E7%AA%93%201.txt', self.calls)

    def test_remote_manifest_tamper_fails(self):
        self.remote[self.bases[1] + '/checksums.sha256'] = ReadbackResponse(200, b'wrong manifest')
        with self.assertRaises(ReleaseReadbackMismatch):
            self.verify()

    def test_remote_stale_sitemap_fails(self):
        self.remote[self.bases[1] + '/sitemap.xml'] = ReadbackResponse(200, b'<stale/>')
        with self.assertRaises(ReleaseReadbackMismatch):
            self.verify()

    def test_direct_local_verification_uses_pinned_digest(self):
        self.assertEqual(len(verify_local_artifact(self.root, expected_manifest_sha256=self.pin)), 5)
        with self.assertRaises(ReleaseReadbackMismatch):
            verify_local_artifact(self.root, expected_manifest_sha256='0' * 64)


if __name__ == '__main__':
    unittest.main()
