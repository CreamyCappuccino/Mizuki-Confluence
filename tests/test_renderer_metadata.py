"""Renderer-owned metadata and ordinary exact readback, using synthetic data."""
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest
from uuid import UUID

from confluence_pressroom.release_http import ReadbackResponse, target_url
from confluence_release.artifacts import ReleaseBuilder, read_files, verify_local_artifact
from confluence_release.config import ROBOTS, ReleaseConfig, digest
from confluence_release.projection import ProjectionArticle
from confluence_release.readback import ReadbackUnknown, verify_public_artifact
from confluence_release.site_renderer import render_pages

CONFIG = ReleaseConfig('https://reader.example.invalid/confluence', 'synthetic-metadata',
                       'https://reader.example.invalid/confluence')


def sample(**changes):
    payload = dict(schema_version='confluence.publication.v1', destination_key='confluence',
        visibility='public', manuscript_ref='ART99999001', revision_ref='ART99999001-R01',
        revision_no=1, locale='ja',
        destination_url=CONFIG.site_base + '/ja/articles/art99999001.html',
        title='合成の窓', excerpt='公開済みの要約。', published_on='2026-01-01',
        rendered_html='<p>Approved body &amp; unchanged.</p>', category_paths=[], tags=[],
        authors=[], author_label='Synthetic writer')
    payload.update(changes)
    return ProjectionArticle(UUID(int=1), UUID(int=2), payload, digest(payload))


class Head(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.inside = False
        self.meta, self.canonicals, self.tags = {}, [], []
        self.feed(html)

    def handle_starttag(self, tag, attributes):
        if tag == 'head':
            self.inside = True
        if not self.inside:
            return
        attrs = dict(attributes)
        self.tags.append(tag)
        if tag == 'meta':
            key = attrs.get('property') or attrs.get('name')
            if key:
                self.meta.setdefault(key, []).append(attrs.get('content'))
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonicals.append(attrs['href'])

    def handle_endtag(self, tag):
        if tag == 'head':
            self.inside = False


class RendererMetadataTests(unittest.TestCase):
    def head(self, pages, path):
        return Head(pages[path].decode('utf-8'))

    def test_every_html_has_one_basic_metadata_set(self):
        pages = render_pages((sample(),), CONFIG)
        for path, raw in pages.items():
            if not path.endswith('.html'):
                continue
            with self.subTest(path=path):
                head = self.head(pages, path)
                og = {k: v for k, v in head.meta.items() if k.startswith('og:')}
                self.assertEqual(set(og), {'og:title', 'og:description', 'og:type', 'og:url'})
                self.assertTrue(all(len(v) == 1 for v in og.values()))
                self.assertEqual(head.meta['description'], head.meta['og:description'])
                self.assertEqual(head.meta['robots'], [ROBOTS])
                self.assertEqual(head.canonicals, head.meta['og:url'])
                self.assertFalse(any(k.startswith('twitter:') for k in head.meta))

    def test_navigation_pages_have_distinct_canonical_routes(self):
        pages = render_pages((), CONFIG)
        for path, suffix, title in (
            ('index.html', '/', 'Confluence'),
            ('browse.html', '/browse.html', 'Browse — Confluence'),
            ('writers.html', '/writers.html', 'Writers — Confluence'),
        ):
            with self.subTest(path=path):
                head = self.head(pages, path)
                self.assertEqual(head.canonicals, [CONFIG.site_base + suffix])
                self.assertEqual(head.meta['og:title'], [title])
                self.assertEqual(head.meta['og:type'], ['website'])

    def test_article_uses_approved_title_excerpt_and_route(self):
        row = sample()
        path = 'ja/articles/art99999001.html'
        pages = render_pages((row,), CONFIG)
        head = self.head(pages, path)
        self.assertEqual(head.meta['og:title'], [row.payload['title'] + ' — Confluence'])
        self.assertEqual(head.meta['og:description'], [row.payload['excerpt']])
        self.assertEqual(head.meta['og:type'], ['article'])
        self.assertEqual(head.canonicals, [row.payload['destination_url']])
        self.assertIn(row.payload['rendered_html'].encode(), pages[path])
        self.assertIn(b'../../assets/styles.css', pages[path])

    def test_missing_excerpt_uses_site_copy_not_body(self):
        for excerpt in (None, ''):
            with self.subTest(excerpt=excerpt):
                row = sample(excerpt=excerpt, rendered_html='<p>Not a generated summary.</p>')
                pages = render_pages((row,), CONFIG)
                head = self.head(pages, 'ja/articles/art99999001.html')
                self.assertEqual(head.meta['description'], ['A writing shared on Confluence.'])
                self.assertNotIn('Not a generated summary.', str(head.meta))
                self.assertEqual(row.payload['excerpt'], excerpt)

    def test_english_article_metadata_uses_english_route(self):
        row = sample(locale='en', title='A window', excerpt='An approved excerpt.',
            destination_url=CONFIG.site_base + '/en/articles/art99999001.html')
        pages = render_pages((row,), CONFIG)
        head = self.head(pages, 'en/articles/art99999001.html')
        self.assertEqual(head.canonicals, [row.payload['destination_url']])
        self.assertEqual(head.meta['og:title'], ['A window — Confluence'])

    def test_quotes_and_markup_remain_attribute_text(self):
        title = '\" & <script>alert(1)</script> 日本語'
        excerpt = '\"><meta property="og:url" content="https://bad.invalid"> & note'
        pages = render_pages((sample(title=title, excerpt=excerpt),), CONFIG)
        head = self.head(pages, 'ja/articles/art99999001.html')
        self.assertEqual(head.meta['og:title'], [title + ' — Confluence'])
        self.assertEqual(head.meta['og:description'], [excerpt])
        self.assertEqual(len(head.meta['og:url']), 1)
        self.assertEqual(head.tags.count('script'), 1)  # Existing preference script only.

    def test_build_is_deterministic_without_altering_payload(self):
        row = sample()
        before = digest(row.payload)
        self.assertEqual(render_pages((row,), CONFIG), render_pages((row,), CONFIG))
        self.assertEqual(digest(row.payload), before)
        self.assertEqual(row.payload_sha256, before)

    def test_canonical_mount_is_used_once_and_provider_is_not_canonical(self):
        pages = render_pages((sample(),), CONFIG)
        for path in (p for p in pages if p.endswith('.html')):
            url = self.head(pages, path).canonicals[0]
            self.assertEqual(url.count('/confluence'), 1)
            self.assertTrue(url.startswith(CONFIG.site_base + '/'))
            self.assertNotIn(CONFIG.here_now_base, url)

    def test_withdrawal_removes_article_but_keeps_metadata_on_empty_site(self):
        pages = render_pages((), CONFIG)
        self.assertEqual(set(pages), {'index.html', 'browse.html', 'writers.html', 'search.json'})
        self.assertEqual(pages['search.json'], b'[]\n')
        for path in ('index.html', 'browse.html', 'writers.html'):
            self.assertEqual(self.head(pages, path).meta['og:type'], ['website'])


class MetadataReadbackTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        assets = self.root / 'assets'
        assets.mkdir()
        (assets / 'styles.css').write_text('/* synthetic */')
        self.builder = ReleaseBuilder(source_assets=assets, config=CONFIG,
                                      source_commit='synthetic-metadata-source')
        self.receipt = self.builder.build((sample(),), self.root / 'release')
        self.files = read_files(self.receipt.output)
        self.remote = {target_url(base, path): ReadbackResponse(200, data)
            for base in (CONFIG.here_now_base, CONFIG.nor_base)
            for path, data in self.files.items()}

    def fetch(self, url):
        return self.remote.get(url, ReadbackResponse(404, b''))

    def test_two_origins_use_existing_exact_path_without_profile(self):
        out = verify_public_artifact(self.receipt, CONFIG, fetch=self.fetch)
        self.assertEqual(out['checksums'], 'exact')
        self.assertEqual(out['origins'], 2)
        self.assertNotIn('html_policy', out)
        self.assertNotIn('transformed_html', out)
        verify_local_artifact(self.receipt)

    def test_repeat_readback_leaves_frozen_artifact_unchanged(self):
        before = self.receipt.as_record()
        for _ in range(2):
            verify_public_artifact(self.receipt, CONFIG, fetch=self.fetch)
        self.assertEqual(self.receipt.as_record(), before)
        self.assertEqual(read_files(self.receipt.output), self.files)

    def test_single_byte_change_is_not_normalized_away(self):
        url = target_url(CONFIG.nor_base, 'index.html')
        self.remote[url] = ReadbackResponse(200, self.remote[url].body + b' ')
        with self.assertRaises(ReadbackUnknown):
            verify_public_artifact(self.receipt, CONFIG, fetch=self.fetch)

    def test_provider_insertion_is_not_learned_or_accepted(self):
        url = target_url(CONFIG.here_now_base, 'index.html')
        raw = self.remote[url].body.replace(b'</head>',
            b'<meta property="og:image" content="https://bad.invalid/x.jpg"></head>')
        self.remote[url] = ReadbackResponse(200, raw)
        with self.assertRaises(ReadbackUnknown):
            verify_public_artifact(self.receipt, CONFIG, fetch=self.fetch)


if __name__ == '__main__':
    unittest.main()
