"""V1 compatibility + strict, explicitly ordered nine-meta policy unit tests."""
from dataclasses import FrozenInstanceError, asdict, fields
import hashlib
import json
import unittest

from confluence_pressroom.here_now_html import HereNowHtmlPolicy
from confluence_pressroom.here_now_image_html import IMAGE_META_ORDER, HereNowImageHtmlPolicy
from phase2_support import CONFIG
from image_html_test_support import IMAGE, ORDER, SOURCE, image_policy, literal_image_block
from test_here_now_html_policy import policy, literal_block


class ImageHtmlPolicyTests(unittest.TestCase):
    def test_old_policy_schema_hash_and_serialization_unchanged(self):
        original_fields = ('here_now_base', 'nor_base', 'title', 'description',
                           'block_prefix', 'tag_separator', 'block_suffix',
                           'expected_manifest_sha256', 'format')
        self.assertEqual(tuple(f.name for f in fields(HereNowHtmlPolicy)), original_fields)
        raw = {'here_now_base': CONFIG.here_now_base, 'nor_base': CONFIG.nor_base,
               'title': 'Confluence', 'description': 'Synthetic description.',
               'block_prefix': '\n', 'tag_separator': '\n', 'block_suffix': '\n',
               'expected_manifest_sha256': None, 'format': 'here-now-og/v1'}
        digest = hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False,
                               separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        self.assertEqual(policy().sha256, digest)
        self.assertEqual(policy().predict(SOURCE, base=CONFIG.nor_base, relative='index.html'),
                         SOURCE.replace(b'</head>', literal_block(CONFIG.nor_base) + b'</head>'))

    def test_nine_tags_match_independent_literal_at_each_origin_surface(self):
        p = image_policy()
        self.assertIsInstance(p, HereNowHtmlPolicy)
        for base in (CONFIG.here_now_base, CONFIG.nor_base):
            for name in ('index.html', 'writers.html', 'browse.html', 'ja/articles/art0084.html'):
                with self.subTest(base=base, name=name):
                    predicted = p.predict(SOURCE, base=base, relative=name)
                    self.assertEqual(predicted, SOURCE.replace(b'</head>',
                        literal_image_block(base, name) + b'</head>'))
                    self.assertEqual(predicted.count(b'<meta '), 9)
                    self.assertEqual(predicted.count(IMAGE.encode()), 2)

    def test_exact_nine_name_order_is_fixed_and_not_configurable(self):
        self.assertEqual(IMAGE_META_ORDER, ORDER)
        self.assertEqual(len(set(IMAGE_META_ORDER)),9)
        with self.assertRaises(TypeError): image_policy(tag_order=list(ORDER))
        with self.assertRaises(TypeError): image_policy(extra_meta=['x'])

    def test_tag_fields_are_not_general_purpose_html_templates(self):
        for name in ('raw_html','tags','twitter_card','image_type','tag_order'):
            with self.subTest(name=name),self.assertRaises(TypeError):
                image_policy(**{name:'unreviewed'})

    def test_policy_is_immutable(self):
        p=image_policy(); digest=p.sha256
        with self.assertRaises(FrozenInstanceError): p.image_width=1
        with self.assertRaises(FrozenInstanceError): p.image_url='other'
        self.assertEqual(p.sha256,digest)

    def test_image_reference_bound_to_site_not_received_document(self):
        for url in (None, True, '', 'http://here.now/og/synthetic-confluence.jpg',
                    IMAGE+'?cache=1', IMAGE+'#x', IMAGE+'/', IMAGE.replace('.jpg', '.png'),
                    IMAGE.replace('synthetic-confluence', 'another-site'),
                    IMAGE.replace('here.now/', 'here.now:443/'),
                    IMAGE.replace('here.now/', 'user@here.now/'),
                    IMAGE.replace('here.now/', 'evil.invalid/'),
                    IMAGE.replace('/og/', '/og/../og/'), IMAGE.replace('/og/', '/%6fg/')):
            with self.subTest(url=url), self.assertRaises(ValueError): image_policy(image_url=url)

    def test_dimensions_are_bounded_integers_not_booleans_or_strings(self):
        for value in (None, True, False, 0, -1, 16385, 1.0, '1280', {}, []):
            for field in ('image_width', 'image_height'):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    image_policy(**{field: value})
        for field, value in (('image_width', 1), ('image_height', 16384)):
            self.assertNotEqual(image_policy(**{field: value}).sha256, image_policy().sha256)

    def test_requires_manifest_pin_and_exact_format(self):
        for pin in (None, '', 'x'*64, 'A'*64, 3):
            with self.subTest(pin=pin), self.assertRaises(ValueError):
                image_policy(expected_manifest_sha256=pin)
        for format in ('here-now-og/v1', 'here-now-og/v3', None):
            with self.subTest(format=format), self.assertRaises(ValueError): image_policy(format=format)

    def test_v2_whitespace_is_only_the_reported_serialization(self):
        for key, values in (('block_prefix', ('\n',' ','\r\n')),
                            ('block_suffix', ('\n',' ','\r\n')),
                            ('tag_separator', ('',' ','\r\n','\n\n'))):
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    image_policy(**{key:value})

    def test_canonical_hash_includes_all_image_fields_and_order(self):
        p = image_policy()
        independent = hashlib.sha256(json.dumps(asdict(p), sort_keys=True, ensure_ascii=False,
                         separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        self.assertEqual(p.sha256, independent)
        self.assertNotEqual(p.sha256, policy().sha256)
        self.assertNotEqual(image_policy(image_width=1279).sha256, p.sha256)

    def test_unicode_escaping_and_byte_boundary_are_preserved(self):
        original = SOURCE.replace(b'Original', '潮の書庫🌷\r\n'.encode())
        p = image_policy(title='A & "B"', description="<tag> 'quote'")
        actual = p.predict(original, base=CONFIG.nor_base, relative='ja/潮.html')
        self.assertIn('潮の書庫🌷\r\n'.encode(), actual)
        self.assertIn(b'A &amp; &quot;B&quot;', actual)
        self.assertIn(b'&lt;tag&gt; &#x27;quote&#x27;', actual)
        self.assertIn(b'/ja/%E6%BD%AE.html', actual)
        self.assertTrue(actual.endswith(b'</head><body>unchanged</body></html>'))

    def test_ineligible_source_and_non_html_stay_rejected(self):
        for source in (SOURCE.replace(b'</head>', b'</HEAD>'),
                       SOURCE.replace(b'</head>', b'</head></head>'),
                       SOURCE.replace(b'</head>', b'<meta name="twitter:image" content="own"></head>'),
                       SOURCE.replace(b'</head>', b'<!-- </head> --></head>'),
                       SOURCE.replace(b'Original', b'\xff')):
            with self.subTest(source=source), self.assertRaises(ValueError):
                image_policy().predict(source, base=CONFIG.nor_base, relative='index.html')
        for path in ('x.css','../index.html','index.html?x','a%2fb.html'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                image_policy().predict(SOURCE, base=CONFIG.nor_base, relative=path)

    def test_cross_base_and_manifest_scope_fail_closed(self):
        p = image_policy()
        for bases, digest in (((CONFIG.nor_base, CONFIG.here_now_base), 'a'*64),
                              ((CONFIG.here_now_base, CONFIG.nor_base), 'b'*64)):
            with self.assertRaises(ValueError): p.validate_scope(bases, digest)
        with self.assertRaises(ValueError):
            p.predict(SOURCE, base='https://other.invalid', relative='index.html')
