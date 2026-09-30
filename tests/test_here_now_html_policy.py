"""Policy unit tests: literal expected bytes, not a permissive HTML normalizer."""
from dataclasses import FrozenInstanceError, replace
import unittest

from confluence_pressroom.here_now_html import HereNowHtmlPolicy
from confluence_pressroom.release_checksums import ReleaseReadbackMismatch
from phase2_support import CONFIG

SOURCE = b'<!doctype html><html><head><title>Original</title></head><body>unchanged</body></html>'


def policy(**changes):
    return replace(HereNowHtmlPolicy(CONFIG.here_now_base, CONFIG.nor_base,
                                    'Confluence', 'Synthetic description.'), **changes)


def literal_block(base, relative='index.html'):
    # Independent fixture serialization, intentionally not calling predict().
    return ('\n<meta property="og:title" content="Confluence" />\n'
            '<meta property="og:description" content="Synthetic description." />\n'
            f'<meta property="og:url" content="{base}/{relative}" />\n'
            '<meta property="og:type" content="website" />\n'
            '<meta name="twitter:card" content="summary" />\n').encode()


class HtmlPolicyTests(unittest.TestCase):
    def test_literal_expected_five_tags_and_position(self):
        result = policy().predict(SOURCE, base=CONFIG.nor_base, relative='index.html')
        self.assertEqual(result, SOURCE.replace(b'</head>', literal_block(CONFIG.nor_base) + b'</head>'))
        self.assertEqual(result.count(b'<meta '), 5)

    def test_each_origin_uses_its_own_full_requested_path(self):
        for base in (CONFIG.here_now_base, CONFIG.nor_base):
            for path in ('index.html', 'ja/articles/art0084.html', 'writers.html'):
                with self.subTest(base=base, path=path):
                    got = policy().predict(SOURCE, base=base, relative=path)
                    self.assertIn(f'content="{base}/{path}"'.encode(), got)
                    self.assertEqual(got, SOURCE.replace(b'</head>', literal_block(base, path) + b'</head>'))

    def test_unicode_source_offset_is_byte_correct(self):
        original = SOURCE.replace(b'Original', '潮さんの書庫\u2028🌷'.encode())
        got = policy().predict(original, base=CONFIG.nor_base, relative='index.html')
        self.assertEqual(got, original.replace(b'</head>', literal_block(CONFIG.nor_base) + b'</head>'))

    def test_multiline_source_offset_is_byte_correct(self):
        original = SOURCE.replace(b'<head>', b'<head>\r\n').replace(b'</title>', b'</title>\n')
        got = policy().predict(original, base=CONFIG.nor_base, relative='index.html')
        self.assertEqual(got, original.replace(b'</head>', literal_block(CONFIG.nor_base) + b'</head>'))

    def test_metadata_attribute_escaping(self):
        got = policy(title='A & "B"', description="<tag> 'quote'").predict(
            SOURCE, base=CONFIG.nor_base, relative='index.html')
        self.assertIn(b'A &amp; &quot;B&quot;', got)
        self.assertIn(b'&lt;tag&gt; &#x27;quote&#x27;', got)
        self.assertNotIn(b'<tag>', got)

    def test_unicode_path_is_encoded_not_taken_from_remote(self):
        got = policy().predict(SOURCE, base=CONFIG.nor_base, relative='ja/潮.html')
        self.assertIn(b'/ja/%E6%BD%AE.html', got)

    def test_policy_is_immutable_and_hash_stable(self):
        self.assertEqual(policy().sha256, policy().sha256)
        with self.assertRaises(FrozenInstanceError):
            policy().title = 'other'
        for field, value in (('title', 'Other'), ('block_prefix', ''),
                             ('expected_manifest_sha256', 'a' * 64)):
            self.assertNotEqual(policy().sha256, policy(**{field: value}).sha256)

    def test_manifest_and_origin_scope_are_separate(self):
        bases = (CONFIG.here_now_base, CONFIG.nor_base)
        p = policy(expected_manifest_sha256='a' * 64)
        p.validate_scope(bases, 'a' * 64)
        for pair, digest in ((bases[::-1], 'a' * 64), (bases, 'b' * 64)):
            with self.assertRaises(ReleaseReadbackMismatch): p.validate_scope(pair, digest)

    def test_profile_requires_site_origin_and_https_mount(self):
        for field, value in (
            ('here_now_base', CONFIG.here_now_base + '/path'),
            ('here_now_base', 'https://example.invalid'),
            ('nor_base', CONFIG.here_now_base), ('nor_base', CONFIG.nor_base + '/'),
            ('nor_base', 'http://localhost/confluence'),
            ('nor_base', CONFIG.nor_base + '?x=y'),
            ('format', 'anything'), ('expected_manifest_sha256', 'bad'),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                policy(**{field: value})

    def test_metadata_rejects_controls_or_invalid_unicode(self):
        for value in ('', None, True, 'a\nb', '\x00', '\x7f', '\ud800', 'x' * 4097):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                policy(description=value)

    def test_only_bounded_ascii_whitespace_is_configurable(self):
        for value in ('<script>', '\x00', '\u00a0', 'x', '\n' * 33):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                policy(tag_separator=value)
        p = policy(block_prefix='', tag_separator='\r\n  ', block_suffix='')
        self.assertNotEqual(p.sha256, policy().sha256)

    def test_ineligible_head_forms_fail_closed(self):
        samples = (
            b'<body>No head</body>', b'<!-- </head> --><body>x</body>',
            b'<html><head><script>"</head>"</script><body>x</body></html>',
            SOURCE.replace(b'</head>', b'</HEAD>'),
            SOURCE.replace(b'</head>', b'</head></head>'),
            SOURCE.replace(b'<head>', b'<head><head>'),
            SOURCE.replace(b'</head>', b'<!-- </head> --></head>'),
            SOURCE.replace(b'Original', b'\xff'),
        )
        for sample in samples:
            with self.subTest(sample=sample), self.assertRaises(ValueError):
                policy().predict(sample, base=CONFIG.nor_base, relative='index.html')

    def test_existing_og_or_twitter_is_not_removed_or_overwritten(self):
        for meta in (b'<meta property="og:title" content="own" />',
                     b'<meta name="twitter:card" content="own">',
                     b'<meta property="og:image" content="own">'):
            source = SOURCE.replace(b'</head>', meta + b'</head>')
            with self.assertRaises(ValueError):
                policy().predict(source, base=CONFIG.nor_base, relative='index.html')

    def test_path_and_origin_cannot_escape_profile(self):
        for relative in ('../x.html', '/x.html', 'x%2f.html', 'x.html?url=evil', 'style.css'):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                policy().predict(SOURCE, base=CONFIG.nor_base, relative=relative)
        with self.assertRaises(ValueError):
            policy().predict(SOURCE, base='https://other.invalid', relative='index.html')
