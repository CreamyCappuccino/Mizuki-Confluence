"""Real two-origin verifier, explicit synthetic response bytes; no live GETs."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from confluence_pressroom.public_release_readback import _require_checksum, UNKNOWN_ROUTE
from confluence_pressroom.release_checksums import ReleaseReadbackMismatch, MANIFEST
from confluence_pressroom.release_http import ReadbackResponse, target_url
from confluence_release.artifacts import ReleaseBuilder, read_files, sha256
from confluence_release.readback import ReadbackUnknown, verify_public_artifact
from image_html_test_support import IMAGE, SOURCE, image_policy, literal_image_block
from test_here_now_html_policy import policy, literal_block
from phase2_support import CONFIG, article, assets


class ImageHtmlReadbackTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.receipt=ReleaseBuilder(source_assets=assets(self.root),config=CONFIG,
            source_commit='old-frozen-source').build((article(),),self.root/'releases'/'first')
        self.files=read_files(self.receipt.output)
        self.bases=(CONFIG.here_now_base,CONFIG.nor_base)
        self.profile=image_policy(expected_manifest_sha256=self.receipt.checksums[MANIFEST])
        self.calls=[]; self.fill()

    def fill(self, transformed=True):
        self.remote={}
        for base in self.bases:
            for name, data in self.files.items():
                raw=(data.replace(b'</head>',literal_image_block(base,name)+b'</head>',1)
                     if transformed and name.endswith('.html') else data)
                self.remote[target_url(base,name)]=ReadbackResponse(200,raw)

    def fetch(self,url):
        self.calls.append(url)
        return self.remote.get(url,ReadbackResponse(404,b''))

    def verify(self,profile=True,**kwargs):
        return verify_public_artifact(self.receipt,CONFIG,fetch=self.fetch,
            html_policy=self.profile if profile else None,**kwargs)

    def test_all_eight_html_and_non_html_verify_with_honest_evidence(self):
        result=self.verify()
        self.assertEqual(result['transformed_html'],8)
        self.assertEqual(result['checksums'],'exact+declared-html-transform')
        self.assertEqual(result['html_policy'],dict(format='here-now-og/v2',sha256=self.profile.sha256))
        for row in result['html_readbacks']:
            self.assertEqual(row['comparison'],'here-now-og/v2')
            self.assertEqual(row['original_sha256'],self.receipt.checksums[row['path']])
            self.assertEqual(row['delivered_sha256'],sha256(self.remote[row['url']].body))
        self.assertNotIn(IMAGE,self.calls)  # Image reference, NOT pixels, is attested.

    def test_default_and_preserved_five_tag_policy_do_not_accept_nine(self):
        with self.assertRaises(ReadbackUnknown): self.verify(profile=False)
        self.profile=policy(expected_manifest_sha256=self.receipt.checksums[MANIFEST])
        with self.assertRaises(ReadbackUnknown): self.verify()

    def test_v2_does_not_silently_fall_back_to_old_five_tag_response(self):
        for base in self.bases:
            for name,data in self.files.items():
                if name.endswith('.html'):
                    old=literal_block(base,name).strip(b'\n')
                    self.remote[target_url(base,name)]=ReadbackResponse(200,
                        data.replace(b'</head>',old+b'</head>',1))
        with self.assertRaises(ReadbackUnknown): self.verify()

    def test_original_raw_exact_response_stays_exact_with_v2(self):
        self.fill(transformed=False)
        result=self.verify()
        self.assertEqual(result['checksums'],'exact'); self.assertEqual(result['transformed_html'],0)
        self.assertTrue(all(r['comparison']=='raw-exact' for r in result['html_readbacks']))

    def test_independent_tag_value_order_attribute_whitespace_position_negatives(self):
        base=self.bases[1]; relative='index.html'
        block=literal_image_block(base,relative)
        candidates=[block.replace(b'1280',b'1281'),block.replace(b'720',b'721'),
            block.replace(b'summary_large_image',b'summary'),
            block.replace(IMAGE.encode(),b'https://here.now/og/other.jpg',1),
            block.replace(IMAGE.encode(),IMAGE.encode()+b'?cache=1'),
            block.replace(base.encode(),self.bases[0].encode()),
            block.replace(b'/index.html',b'/writers.html'),
            block.replace(b'/index.html',b'/index.html?x=1'),
            block.replace(b'/index.html',b'/index.html#x'),
            block.replace(b'Confluence',b'Other'),block.replace(b'Synthetic description.',b'Changed'),
            block.replace(b'website',b'article'),block.replace(b'property=',b'name=',1),
            block.replace(b' />',b'>',1),block.replace(b' />',b' data-x="1" />',1),
            block.replace(b'\n',b'\r\n'),b'\n'+block,block+b'\n',b' '+block,block+b' ',
            b'\n'.join(reversed(block.split(b'\n'))),block+b'\n'+block,
            block+b'\n<meta name="extra" content="x" />']
        local=self.files[relative]
        url=target_url(base,relative)
        raw_list=[local.replace(b'</head>',c+b'</head>',1) for c in candidates]
        raw_list.extend([local.replace(b'<body>',block+b'<body>',1),
                         local.replace(b'</head>',block+b'</head>',1)+b'x',
                         local.replace(b'</head>',block+b'<script>x</script></head>',1)])
        for raw in raw_list:
            with self.subTest(sha=sha256(raw)):
                self.remote[url]=ReadbackResponse(200,raw)
                with self.assertRaises(ReadbackUnknown): self.verify()

    def test_each_byte_xor1_of_synthetic_pair_is_rejected(self):
        # Calls the actual checksum/whole-document verification branch each time.
        # This is synthetic per-byte mutation, not a claim about saved live HTML.
        p=image_policy(); total=0
        for base in self.bases:
            url=target_url(base,'index.html')
            raw=SOURCE.replace(b'</head>',literal_image_block(base)+b'</head>',1)
            for index in range(len(raw)):
                mutated=raw[:index]+bytes([raw[index]^1])+raw[index+1:]
                with self.assertRaises(ReleaseReadbackMismatch):
                    _require_checksum(lambda _:ReadbackResponse(200,mutated),url,sha256(SOURCE),
                        original=SOURCE,policy=p,base=base,relative='index.html')
                total+=1
        self.assertGreater(total,1000)

    def test_non_html_and_manifest_cannot_be_normalized(self):
        for base in self.bases:
            for name in ('search.json','assets/styles.css',MANIFEST):
                url=target_url(base,name); before=self.remote[url]
                self.remote[url]=ReadbackResponse(200,before.body+b' ')
                with self.subTest(base=base,name=name),self.assertRaises(ReadbackUnknown): self.verify()
                self.remote[url]=before

    def test_new_sitemap_and_unknown_removed_routes_rejected_on_both_origins(self):
        for base in self.bases:
            for name in ('sitemap.xml',UNKNOWN_ROUTE,'ja/articles/old.html'):
                url=target_url(base,name);self.remote[url]=ReadbackResponse(200,b'existing')
                with self.subTest(base=base,name=name),self.assertRaises(ReadbackUnknown):
                    self.verify(removed_paths=('ja/articles/old.html',))
                del self.remote[url]

    def test_policy_manifest_or_base_mismatch_fails_before_fetch(self):
        for p in (replace(self.profile,expected_manifest_sha256='0'*64),
                  replace(self.profile,nor_base='https://other.invalid/confluence')):
            self.calls.clear()
            with self.assertRaises(ReadbackUnknown):
                verify_public_artifact(self.receipt,CONFIG,fetch=self.fetch,html_policy=p)
            self.assertEqual(self.calls,[])

    def test_local_snapshot_race_cannot_be_accepted_using_a_newly_read_html(self):
        from confluence_pressroom import public_release_readback as m
        verify=m.verify_local_artifact
        def race(*args,**kwargs):
            value=verify(*args,**kwargs)
            target=self.receipt.output/'index.html';target.write_bytes(target.read_bytes()+b'x')
            return value
        with patch.object(m,'verify_local_artifact',side_effect=race),self.assertRaises(ReadbackUnknown):
            self.verify()
        self.assertEqual(self.calls,[])

    def test_status_not_200_and_redirect_transport_still_unknown(self):
        url=target_url(self.bases[0],'index.html');before=self.remote[url]
        for status in (301,302,404,500):
            self.remote[url]=ReadbackResponse(status,before.body)
            with self.subTest(status=status),self.assertRaises(ReadbackUnknown): self.verify()

    def test_withdrawal_requires_its_own_manifest_not_old_profile(self):
        old_profile=self.profile
        self.receipt=ReleaseBuilder(source_assets=self.root/'assets',config=CONFIG,
            source_commit='new-validator-source').build((),self.root/'releases'/'withdraw')
        self.files=read_files(self.receipt.output); self.fill(); self.calls.clear()
        with self.assertRaises(ReadbackUnknown): self.verify()
        self.assertEqual(self.calls,[])
        self.profile=replace(old_profile,expected_manifest_sha256=self.receipt.checksums[MANIFEST])
        result=self.verify(removed_paths=('ja/articles/old.html',))
        self.assertNotEqual(self.profile.sha256,old_profile.sha256)
        self.assertEqual(result['removed'],1)
