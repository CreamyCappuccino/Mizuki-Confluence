"""Captured renderer bytes -> pre-PUB policy; not live renderer/ledger evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote
from lxml import html

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]
from confluence.config import ConfluenceError, RehearsalConfig
from confluence.html_prepare import prepare_html, validate_prepared_html, POLICY_VERSION
from confluence.payload_schema import payload_sha256
from confluence.preparation import prepare_payload
from prepare_renderer_fixture import build_fixture, raw_fixture, resolved_fixture

RAW_SHA = "e72825edcb09a86c001c8861f755901b64886c28da9e353912582a7254ea87d7"
PREPARED_SHA = "094edc2045e8882e840c6d66b8621f371393cc793942b9a4a0f0b3c893aa1c0a"
PAYLOAD_SHA = "25a68ca36ee8bc507c02e78f08ef9e5da118d2ce5a4e4e756cb9d08d546f6dc6"


def tree(fragment):
    return html.fragment_fromstring(fragment, create_parent="div")


class RendererPreparationTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.provenance = raw_fixture()
        self.prepared = prepare_html(self.raw)

    def test_raw_evidence_retained(self):
        self.assertEqual(hashlib.sha256(self.raw.encode()).hexdigest(), RAW_SHA)
        self.assertFalse(tree(self.raw).xpath('.//*[@id]'))
        self.assertIn('rel="noopener noreferrer"', self.raw)

    def test_raw_is_not_an_approved_prepared_fragment(self):
        with self.assertRaises(ConfluenceError):
            validate_prepared_html(self.raw)

    def test_forward_japanese_links_share_first_heading(self):
        t = tree(self.prepared)
        headings = t.xpath('./h2[text()="日本語の見出し"]')
        links = t.xpath('.//a[starts-with(@href,"#")]')
        self.assertEqual(len(headings), 2)
        self.assertNotEqual(headings[0].get('id'), headings[1].get('id'))
        self.assertEqual([x.get('href') for x in links], ['#cf-n-0006'] * 2)
        self.assertEqual(headings[0].get('id'), 'cf-n-0006')

    def test_every_heading_has_a_unique_id(self):
        headings = tree(self.prepared).xpath('./h1|./h2|./h3')
        self.assertEqual(len({h.get('id') for h in headings}), 5)
        self.assertTrue(all(h.get('id').startswith('cf-n-') for h in headings))

    def test_prose_and_code_characters_are_unchanged(self):
        a, b = tree(self.raw), tree(self.prepared)
        self.assertEqual(''.join(a.itertext()), ''.join(b.itertext()))
        self.assertEqual(a.xpath('.//pre/code/text()'), b.xpath('.//pre/code/text()'))
        self.assertEqual(a.xpath('.//pre/code/@class'), b.xpath('.//pre/code/@class'))
        self.assertFalse(b.xpath('.//synthetic'))
        self.assertEqual(len(b.xpath('.//table//td')), 4)

    def test_known_rel_removed_before_freeze_only(self):
        self.assertFalse(tree(self.prepared).xpath('.//a/@rel'))
        self.assertEqual(tree(self.prepared).xpath('.//a[not(starts-with(@href,"#"))]/@href'),
                         ['https://example.invalid/synthetic'])
        with self.assertRaises(ConfluenceError):
            validate_prepared_html('<p><a href="https://example.invalid" rel="noopener">a</a></p>')

    def test_golden_prepared_hash(self):
        self.assertEqual(hashlib.sha256(self.prepared.encode()).hexdigest(), PREPARED_SHA)

    def test_repeated_preparation_has_identical_bytes(self):
        self.assertEqual(prepare_html(self.raw), self.prepared)
        self.assertEqual(prepare_html(self.prepared), self.prepared)
        validate_prepared_html(self.prepared)

    def test_explicit_ids_and_encoded_links(self):
        text = '<p><a href="#%E7%AB%A0">go</a></p><h2 id="章">Title</h2>'
        t = tree(prepare_html(text))
        self.assertEqual(t.xpath('.//a/@href'), ['#' + t.xpath('./h2/@id')[0]])

    def test_explicit_id_wins_over_a_heading_label(self):
        text = '<h2>chapter</h2><p id="chapter">Target</p><a href="#chapter">go</a>'
        t = tree(prepare_html(text))
        self.assertEqual(t.xpath('.//a/@href'), ['#cf-n-0002'])

    def test_heading_text_nfc_and_whitespace_alias(self):
        text = '<h2> Café   / <em>章</em> </h2><a href="#' + quote('Cafe\u0301 / 章') + '">go</a>'
        t = tree(prepare_html(text))
        self.assertEqual(t.xpath('.//a/@href'), ['#cf-n-0001'])

    def test_duplicates_and_missing_fragments_are_rejected(self):
        for text in ['<p id="x">a</p><p id="x">b</p>', '<a href="#none">go</a>',
                     '<h2>A</h2><h2>A</h2><a href="#A-2">go</a>']:
            with self.subTest(text=text), self.assertRaises(ConfluenceError):
                prepare_html(text)

    def test_malformed_fragment_encoding_is_rejected(self):
        for fragment in ['%zz', '%FF', '%00', '%2563hapter', '']:
            with self.subTest(fragment=fragment), self.assertRaises(ConfluenceError):
                prepare_html('<h2>chapter</h2><a href="#' + fragment + '">go</a>')

    def test_relative_dangerous_and_credential_urls_rejected(self):
        for url in ['javascript:alert(1)', 'java&#x09;script:alert(1)', '//example.invalid',
                    '../private.md', 'data:text/html,x', 'file:///etc/passwd',
                    'https://u:p@example.invalid', 'https://example.invalid\\x']:
            with self.subTest(url=url), self.assertRaises(ConfluenceError):
                prepare_html('<p><a href="' + url + '">go</a></p>')

    def test_unsupported_markup_is_not_silently_lost(self):
        for text in ['<script>x</script>', '<svg></svg>', '<iframe></iframe>',
                     '<p onclick="x()">x</p>', '<p style="color:red">x</p>',
                     '<img src="x">', '<p hidden>x</p>', '<base href="x">',
                     '<p><a href="https://example.invalid" rel="opener">x</a></p>',
                     '<p><a href="https://example.invalid" target="_blank">x</a></p>',
                     '<!--comment--><p>x</p>', '<!DOCTYPE html><p>x</p>',
                     '<p id="a" id="b">x</p>']:
            with self.subTest(text=text), self.assertRaises(ConfluenceError):
                prepare_html(text)

    def test_unbalanced_html_not_auto_repaired(self):
        for text in ['<p>x', '<p>x</h2>', '<p>a<div>x</div></p>', '<p/>']:
            with self.subTest(text=text), self.assertRaises(ConfluenceError):
                prepare_html(text)

    def test_post_pub_validation_never_normalizes(self):
        for text in ['<h2>A</h2>', '<p title="bad">x</p>', '<p>&#65;</p>',
                     '<h2 id="old">A</h2>', '<p><a href="#none">go</a></p>']:
            with self.subTest(text=text), self.assertRaises(ConfluenceError):
                validate_prepared_html(text)

    def test_safely_escaped_attributes_and_voids(self):
        value = prepare_html('<p lang="ja">例<br/>文</p><hr/><ol start="2"><li>a</li></ol>')
        validate_prepared_html(value)
        self.assertIn('<br>', value)
        self.assertIn('<ol start="2">', value)

    def test_size_depth_and_invalid_unicode_limits(self):
        for text in ['<p>\x00</p>', '<p>\ud800</p>', '<p>' + 'x' * 1_500_001 + '</p>',
                     '<span>' * 81 + 'a' + '</span>' * 81]:
            with self.subTest(length=len(text)), self.assertRaises(ConfluenceError):
                prepare_html(text)
        with patch('confluence.html_prepare.MAX_NODES', 1), self.assertRaises(ConfluenceError):
            validate_prepared_html('<p>a</p><p>b</p>')

    def test_parser_version_mismatch_fails_closed(self):
        with patch('confluence.html_prepare.LXML_VERSION', (0, 0, 0)), self.assertRaises(ConfluenceError):
            prepare_html(self.raw)
        with patch('confluence.html_prepare.LIBXML_VERSION', (0, 0, 0)), self.assertRaises(ConfluenceError):
            validate_prepared_html(self.prepared)


class PreparedPayloadTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.config = RehearsalConfig(Path(self.folder.name))
        self.resolved = resolved_fixture()

    def prepare(self, metadata=None, previous=None):
        return prepare_payload(self.resolved, metadata, self.config, previous)

    def test_new_golden_fixture_is_reproducible(self):
        value = build_fixture()
        stored = json.loads((ROOT / 'tests/fixtures/confluence/prepared_renderer_v1.json').read_text())
        self.assertEqual(value, stored)
        self.assertEqual(payload_sha256(value['payload_snapshot']), PAYLOAD_SHA)

    def test_real_renderer_version_and_policy_both_preserved(self):
        p = self.prepare({'published_on': '2026-09-26'})
        self.assertTrue(p['renderer_version'].endswith('|' + POLICY_VERSION))
        self.assertIn('nh3/0.3.6', p['renderer_version'])
        self.assertEqual(self.config.public_config['html_policy'], POLICY_VERSION)

    def test_first_prepare_requires_destination_display_date(self):
        with self.assertRaises(ConfluenceError):
            self.prepare()

    def test_republication_keeps_display_date(self):
        old = self.prepare({'published_on': '2026-09-26'})
        self.assertEqual(self.prepare(previous=old)['published_on'], '2026-09-26')
        self.assertEqual(self.prepare({'published_on': '2026-09-27'}, old)['published_on'], '2026-09-27')

    def test_prior_article_or_locale_cannot_be_reused(self):
        old = self.prepare({'published_on': '2026-09-26'})
        self.resolved.snapshot.manuscript_ref = 'ART99990002'
        with self.assertRaises(ConfluenceError):
            self.prepare(previous=old)
        self.resolved.snapshot.manuscript_ref = 'ART99990001'
        self.resolved.snapshot.locale = 'en'
        with self.assertRaises(ConfluenceError):
            self.prepare(previous=old)

    def test_metadata_is_bounded(self):
        for meta in [[], [('published_on', '2026-09-26')],
                     {'published_on': '2026-09-26', 'state': 'published'},
                     {'published_on': '2026-09-26', 'visibility': 'private'}]:
            with self.subTest(meta=meta), self.assertRaises(ConfluenceError):
                self.prepare(meta)

    def test_publication_and_actor_state_never_copied(self):
        s = self.resolved.snapshot
        s.actor = {'secret': 'fixture-secret'}
        s.is_published = True
        s.published_at = '1999-01-01'
        s.authors[0].session_ref = 'fixture-secret'
        p = self.prepare({'published_on': '2026-09-26'})
        self.assertNotIn('fixture-secret', json.dumps(p))
        for key in ['state', 'is_published', 'first_published_at', 'last_published_at', 'actor']:
            self.assertNotIn(key, p)
        self.assertEqual(p['published_on'], '2026-09-26')

    def test_unknown_excerpt_and_model_stay_null(self):
        self.resolved.snapshot.excerpt = None
        p = self.prepare({'published_on': '2026-09-26'})
        self.assertIsNone(p['excerpt'])
        self.assertIsNone(p['authors'][0]['model'])

    def test_no_mutation_or_clock_restamping(self):
        before = deepcopy(vars(self.resolved.snapshot))
        a = self.prepare({'published_on': '2026-09-26'})
        b = self.prepare({'published_on': '2026-09-26'})
        self.assertEqual(a, b)
        self.assertEqual(vars(self.resolved.snapshot), before)

    def test_discovery_policy_separate_from_listing_intent(self):
        p = self.prepare({'published_on': '2026-09-26'})
        self.assertEqual(p['visibility'], 'public')
        self.assertEqual(self.config.external_discovery, 'discouraged')
        self.assertFalse(self.config.generate_sitemap)
        self.assertNotIn('site_policy', p)

    def test_rehearsal_cannot_target_production_or_git(self):
        with self.assertRaises(ConfluenceError):
            RehearsalConfig(Path(self.folder.name), site_base_url='https://example.com')
        (Path(self.folder.name) / '.git').mkdir()
        with self.assertRaises(ConfluenceError):
            RehearsalConfig(Path(self.folder.name))


if __name__ == '__main__':
    unittest.main()
