"""Full verifier + actual ReleaseBuilder; transport is an explicit byte fixture."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from confluence_pressroom.release_checksums import MANIFEST
from confluence_pressroom.release_http import ReadbackResponse, target_url
from confluence_pressroom.public_release_readback import UNKNOWN_ROUTE
from confluence_release.artifacts import ReleaseBuilder, read_files, sha256
from confluence_release.readback import ReadbackUnknown, verify_public_artifact
from phase2_support import CONFIG, article, assets
from test_here_now_html_policy import literal_block, policy


class ProviderHtmlReadbackTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.receipt = ReleaseBuilder(source_assets=assets(self.root), config=CONFIG,
            source_commit='old-frozen-source').build((article(),), self.root / 'artifact')
        self.files = read_files(self.receipt.output)
        self.profile = policy(expected_manifest_sha256=self.receipt.checksums[MANIFEST])
        self.bases = (CONFIG.here_now_base, CONFIG.nor_base)
        self.remote = {target_url(base, name): ReadbackResponse(200, raw)
                       for base in self.bases for name, raw in self.files.items()}
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        return self.remote.get(url, ReadbackResponse(404, b''))

    def inject(self):
        for base in self.bases:
            for name, raw in self.files.items():
                if name.endswith('.html'):
                    # Independent predicted fixture, no call to implementation.
                    self.remote[target_url(base, name)] = ReadbackResponse(
                        200, raw.replace(b'</head>', literal_block(base, name) + b'</head>', 1))

    def verify(self, profile=True):
        return verify_public_artifact(self.receipt, CONFIG, fetch=self.fetch,
                                      html_policy=self.profile if profile else None)

    def test_raw_exact_default_is_unchanged(self):
        evidence = self.verify(profile=False)
        self.assertEqual(evidence['checksums'], 'exact')
        self.assertNotIn('html_policy', evidence)

    def test_injection_without_explicit_profile_remains_unknown(self):
        self.inject()
        with self.assertRaises(ReadbackUnknown): self.verify(profile=False)

    def test_exact_declared_insertion_passes_both_origins_with_honest_receipt(self):
        self.inject()
        evidence = self.verify()
        self.assertEqual(evidence['checksums'], 'exact+declared-html-transform')
        self.assertEqual(evidence['html_policy']['sha256'], self.profile.sha256)
        html_count = 2 * sum(name.endswith('.html') for name in self.files)
        self.assertEqual(evidence['transformed_html'], html_count)
        self.assertEqual(len(evidence['html_readbacks']), html_count)
        for item in evidence['html_readbacks']:
            self.assertEqual(item['original_sha256'], self.receipt.checksums[item['path']])
            self.assertEqual(item['delivered_sha256'], sha256(self.remote[item['url']].body))
            self.assertNotEqual(item['original_sha256'], item['delivered_sha256'])
        self.assertEqual(evidence['manifest_sha256'], self.receipt.checksums[MANIFEST])
        self.assertEqual(read_files(self.receipt.output), self.files)

    def test_provider_not_injecting_is_still_raw_exact(self):
        evidence = self.verify()
        self.assertEqual(evidence['checksums'], 'exact')
        self.assertEqual(evidence['transformed_html'], 0)
        self.assertTrue(all(r['comparison'] == 'raw-exact' for r in evidence['html_readbacks']))

    def test_profile_does_not_have_to_apply_to_every_origin(self):
        self.inject()
        for name, raw in self.files.items():
            self.remote[target_url(CONFIG.nor_base, name)] = ReadbackResponse(200, raw)
        evidence = self.verify()
        self.assertEqual(evidence['transformed_html'], sum(n.endswith('.html') for n in self.files))

    def test_exact_transform_rejects_each_unapproved_change(self):
        self.inject()
        path = self.receipt.article_routes[0]
        for base in self.bases:
            url = target_url(base, path)
            original_response = self.remote[url]
            raw = original_response.body
            mutations = {
                'body append': raw + b'<p>extra</p>',
                'script append': raw + b'<script>bad()</script>',
                'body edit': raw.replace('合成見出し'.encode(), '別の本文'.encode()),
                'wrong title': raw.replace(b'content="Confluence"', b'content="Other"'),
                'wrong description': raw.replace(b'Synthetic description.', b'Unapproved.'),
                'wrong type': raw.replace(b'content="website"', b'content="article"'),
                'wrong twitter card': raw.replace(b'content="summary"', b'content="summary_large_image"'),
                'wrong origin': raw.replace(url.encode(), b'https://other.invalid/article.html'),
                'wrong path': raw.replace(url.encode(), (base + '/index.html').encode()),
                'attribute added': raw.replace(b'property="og:title"', b'property="og:title" data-x="1"'),
                'tag removed': raw.replace(b'<meta name="twitter:card" content="summary" />\n', b''),
                'duplicate meta': raw.replace(b'</head>', b'<meta property="og:title" content="Confluence" /></head>'),
                'other meta': raw.replace(b'</head>', b'<meta name="robots" content="index" /></head>'),
                'whitespace changed': raw.replace(b'<meta property="og:title"', b'<meta  property="og:title"'),
                'meta reordered': raw.replace(b'<meta property="og:type" content="website" />\n<meta name="twitter:card" content="summary" />',
                                             b'<meta name="twitter:card" content="summary" />\n<meta property="og:type" content="website" />'),
                'insertion outside head': self.files[path] + literal_block(base, path),
                'source newline added': b'\n' + raw,
                'noindex removed': raw.replace(b'noindex', b'index'),
                'original unrelated meta': raw.replace(b'charset="utf-8"', b'charset="ascii"'),
            }
            for label, changed in mutations.items():
                with self.subTest(base=base, mutation=label):
                    self.assertNotEqual(changed, raw, 'negative fixture did not change bytes')
                    self.remote[url] = ReadbackResponse(200, changed)
                    with self.assertRaises(ReadbackUnknown): self.verify()
            self.remote[url] = original_response

    def test_css_search_and_manifest_remain_raw_exact(self):
        self.inject()
        for base in self.bases:
            for name in ('assets/styles.css', 'search.json', MANIFEST, 'release-manifest.json'):
                url = target_url(base, name); saved = self.remote[url]
                with self.subTest(base=base, name=name):
                    self.remote[url] = ReadbackResponse(200, saved.body + b' ')
                    with self.assertRaises(ReadbackUnknown): self.verify()
                self.remote[url] = saved

    def test_scope_and_manifest_mismatch_precede_fetch(self):
        for changes in ({'expected_manifest_sha256': 'b' * 64},
                        {'nor_base': 'https://other.invalid/confluence'}):
            self.profile = replace(policy(), **changes)
            with self.assertRaises(ReadbackUnknown): self.verify()
            self.assertEqual(self.calls, [])

    def test_local_tamper_cannot_be_normalized_away(self):
        self.inject()
        p = self.receipt.output / 'index.html'
        p.write_bytes(p.read_bytes() + b'changed')
        with self.assertRaises(ValueError): self.verify()
        self.assertEqual(self.calls, [])

    def test_per_origin_404_sitemap_checks_still_apply(self):
        self.inject()
        for base in self.bases:
            for name in ('sitemap.xml', UNKNOWN_ROUTE, 'ja/articles/old.html'):
                url = target_url(base, name)
                self.remote[url] = ReadbackResponse(200, b'existing')
                with self.subTest(base=base, name=name), self.assertRaises(ReadbackUnknown):
                    verify_public_artifact(self.receipt, CONFIG, fetch=self.fetch,
                        html_policy=self.profile, removed_paths=('ja/articles/old.html',))
                del self.remote[url]

    def test_duplicate_source_meta_is_raw_only_not_generic_strip(self):
        # A separate fresh, valid manifest may itself contain author-owned OG.
        raw = self.files['index.html'].replace(b'</head>', b'<meta property="og:title" content="Own" /></head>')
        p = self.receipt.output / 'index.html'; p.write_bytes(raw)
        files = read_files(self.receipt.output); files.pop(MANIFEST)
        manifest = ''.join(f'{sha256(data)}  {name}\n' for name, data in sorted(files.items())).encode()
        (self.receipt.output / MANIFEST).write_bytes(manifest)
        self.files = read_files(self.receipt.output)
        self.receipt = replace(self.receipt, checksums={k: sha256(v) for k, v in self.files.items()})
        self.profile = policy(expected_manifest_sha256=self.receipt.checksums[MANIFEST])
        self.remote = {target_url(base, name): ReadbackResponse(200, data)
                       for base in self.bases for name, data in self.files.items()}
        self.assertEqual(self.verify()['checksums'], 'exact')
        self.inject()
        with self.assertRaises(ReadbackUnknown): self.verify()
