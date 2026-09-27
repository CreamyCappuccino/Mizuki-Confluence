from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

from confluence_release.artifacts import ReleaseBuilder, verify_local_artifact, read_files, safe_relative
from confluence_release.config import digest
from confluence_release.readback import verify_public_artifact, ReadbackUnknown
from confluence_release.site_renderer import article_path
from phase2_support import CONFIG, article, assets


class Response:
    def __init__(self,data,status=200):self.data,self.status=data,status
    def read(self, size=-1):return self.data if size < 0 else self.data[:size]
    def __enter__(self):return self
    def __exit__(self,*args):pass


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.builder=ReleaseBuilder(source_assets=assets(self.root),config=CONFIG,source_commit='synthetic-source')
    def tearDown(self):self.temp.cleanup()
    def build(self,rows=None,name='release'):
        return self.builder.build((article(),) if rows is None else rows,self.root/name)
    def opener(self,receipt,extra=None):
        files=read_files(receipt.output)
        def call(req,**kwargs):
            url=req.full_url
            base=next(b for b in (CONFIG.nor_base,CONFIG.here_now_base) if url.startswith(b+'/'))
            path=url[len(base)+1:]
            if extra and path in extra:return Response(extra[path])
            if path in files:return Response(files[path])
            raise HTTPError(url,404,'not found',{},None)
        return call
    def test_deterministic_build(self):
        a=self.build(); b=self.build(name='other')
        self.assertEqual(a.checksums,b.checksums)
        self.assertEqual(a.content_digest,b.content_digest)
    def test_real_data_replaces_sample_content(self):
        r=self.build(); text=(r.output/'index.html').read_text()
        self.assertIn('合成記事',text); self.assertNotIn('PROTOTYPE 0.2',text)
        self.assertNotIn('AIと散歩する',text)
    def test_append_body_is_rejected(self):
        r=self.build(); p=r.output/r.article_routes[0]
        p.write_bytes(p.read_bytes()+b'<p>extra</p>')
        with self.assertRaises(ValueError):verify_local_artifact(r)
    def test_extra_file_rejected(self):
        r=self.build(); (r.output/'unexpected.html').write_text('extra')
        with self.assertRaises(ValueError):verify_local_artifact(r)
    def test_missing_file_rejected(self):
        r=self.build(); (r.output/'browse.html').unlink()
        with self.assertRaises(ValueError):verify_local_artifact(r)
    def test_no_sitemap_and_noindex_all_html(self):
        r=self.build(); files=read_files(r.output)
        self.assertNotIn('sitemap.xml',files)
        for name,data in files.items():
            if name.endswith('.html'):self.assertIn(b'noindex, nofollow, noarchive',data)
    def test_no_ail_endpoints(self):
        r=self.build()
        for data in read_files(r.output).values():
            self.assertNotIn(b'granite-lemon',data)
            self.assertNotIn(b'nol.strangebasket',data)
    def test_withdrawal_keeps_other_article_and_shared_taxonomy(self):
        before=self.build((article(),article('ART99990002')))
        after=self.build((article('ART99990002'),),name='after')
        files=read_files(after.output)
        self.assertNotIn(before.article_routes[0],files)
        self.assertIn('ja/articles/art99990002.html',files)
        self.assertIn(b'<small>1</small>',files['browse.html'])
        self.assertNotIn(b'<span>2</span>',files['browse.html'])
    def test_nor_prefix_not_duplicated_inside_artifact(self):
        r=self.build(); self.assertIn('ja/articles/art99990001.html',r.checksums)
        self.assertNotIn('confluence/ja/articles/art99990001.html',r.checksums)
        self.assertIn(b'../../assets/styles.css',(r.output/r.article_routes[0]).read_bytes())
    def test_html_metadata_is_escaped(self):
        a=article(); p={**a.payload,'title':'<script>unsafe</script>'}
        r=self.build((replace(a,payload=p,payload_sha256=digest(p)),))
        self.assertIn(b'&lt;script&gt;', (r.output/'index.html').read_bytes())
    def test_both_origins_exact_readback(self):
        r=self.build(); out=verify_public_artifact(r,CONFIG,opener=self.opener(r))
        self.assertEqual(out['origins'],2)
    def test_bad_remote_file_not_success(self):
        r=self.build()
        with self.assertRaises(ReadbackUnknown):
            verify_public_artifact(r,CONFIG,opener=self.opener(r,{'index.html':b'extra'}))
    def test_removed_route_is_checked(self):
        r=self.build(rows=()); old='ja/articles/art99990001.html'
        verify_public_artifact(r,CONFIG,removed_paths=(old,),opener=self.opener(r))
        with self.assertRaises(ReadbackUnknown):
            verify_public_artifact(r,CONFIG,removed_paths=(old,),opener=self.opener(r,{old:b'old body'}))
    def test_timeout_is_unknown(self):
        r=self.build()
        def fail(*a,**k):raise URLError('timeout')
        with self.assertRaises(ReadbackUnknown):verify_public_artifact(r,CONFIG,opener=fail)
    def test_path_traversal(self):
        for path in ('../x','/x','a/../../x','a//b','x%2fy','x\\y'):
            with self.subTest(path=path),self.assertRaises(ValueError):safe_relative(path)
    def test_output_not_overwritten(self):
        self.build()
        with self.assertRaises(ValueError):self.build()

if __name__=='__main__':unittest.main()
