from pathlib import Path
import json
import tempfile
import unittest
from urllib.error import URLError

from confluence_release.artifacts import ReleaseBuilder
from confluence_release.here_now_client import HereNowClient, HereNowError, HereNowOutcomeUnknownError
from phase2_support import CONFIG, article, assets
from test_phase2_artifacts import Response


class HereNowTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();r=Path(self.temp.name)
        self.receipt=ReleaseBuilder(source_assets=assets(r),config=CONFIG,source_commit='synthetic').build((article(),),r/'release')
        self.requests=[];self.active={};self.finalize_fail=False
    def tearDown(self):self.temp.cleanup()
    def opener(self,req,**kwargs):
        self.requests.append(req)
        if req.full_url.startswith('https://storage.example.invalid/'):
            self.assertIsNone(req.get_header('Authorization'));return Response(b'',200)
        if req.method=='GET':
            return Response(json.dumps(dict(manifest=[{'path':p,'hash':h} for p,h in self.active.items()],currentVersionId='v2')).encode())
        if req.method=='PUT':
            data=json.loads(req.data)
            self.assertFalse(data['spaMode'])
            self.pending={i['path']:i['hash'] for i in data['files']}
            return Response(json.dumps(dict(upload=dict(versionId='v2',finalizeUrl='https://here.now/api/v1/finalize',uploads=[
                {'path':p,'url':'https://storage.example.invalid/'+p} for p in self.pending]))).encode())
        if req.method=='POST':
            self.active=self.pending
            if self.finalize_fail:raise URLError('lost finalize response')
            return Response(b'{}')
        self.fail('unexpected request')
    def test_diff_upload_and_finalize(self):
        c=HereNowClient('synthetic-key',opener=self.opener)
        result=c.publish(CONFIG.here_now_slug,self.receipt)
        self.assertFalse(result.reconciled);self.assertEqual(self.active,self.receipt.checksums)
    def test_equal_manifest_skips_upload(self):
        self.active=dict(self.receipt.checksums)
        result=HereNowClient('synthetic-key',opener=self.opener).publish(CONFIG.here_now_slug,self.receipt)
        self.assertTrue(result.reconciled);self.assertEqual(len(self.requests),1)
    def test_unknown_finalize_then_observe_not_republish(self):
        c=HereNowClient('synthetic-key',opener=self.opener);self.finalize_fail=True
        with self.assertRaises(HereNowOutcomeUnknownError):c.publish(CONFIG.here_now_slug,self.receipt)
        before=len(self.requests);r=c.reconcile(CONFIG.here_now_slug,self.receipt)
        self.assertTrue(r.reconciled);self.assertEqual(len(self.requests),before+1)
    def test_api_key_not_sent_to_other_origin(self):
        c=HereNowClient('synthetic-key',opener=self.opener)
        with self.assertRaises(HereNowError):c._request('POST','https://other.invalid/api/finalize',{})
        self.assertEqual(self.requests,[])
    def test_local_tamper_before_any_network(self):
        (self.receipt.output/'index.html').write_bytes(b'tampered')
        with self.assertRaises(ValueError):HereNowClient('synthetic-key',opener=self.opener).publish(CONFIG.here_now_slug,self.receipt)
        self.assertEqual(self.requests,[])
    def test_reconcile_missing_manifest_returns_none(self):
        self.assertIsNone(HereNowClient('synthetic-key',opener=self.opener).reconcile(CONFIG.here_now_slug,self.receipt))

if __name__=='__main__':unittest.main()
