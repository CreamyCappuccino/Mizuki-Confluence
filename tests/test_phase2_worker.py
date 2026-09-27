from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from confluence_release.artifacts import ReleaseBuilder
from confluence_release.delivery import ReleaseDelivery
from confluence_release.here_now_client import HereNowReceipt
from confluence_release.worker import ReleaseWorker
from phase2_support import CONFIG, FakeJobs, ProjectionDouble, article, assets, context, dispatch


class WorkerTests(unittest.TestCase):
    def test_success_after_bridge_only(self):
        jobs=FakeJobs(context())
        bridge=SimpleNamespace(run=lambda *a,**k:'published',may_have_delivered=lambda c:False)
        r=ReleaseWorker(jobs,bridge,CONFIG).run_once()
        self.assertEqual(r.status,'published');self.assertEqual(jobs.completed,['published'])
    def test_unknown_does_not_complete(self):
        jobs=FakeJobs(context())
        def run(*a,**k):raise OSError('after delivery')
        bridge=SimpleNamespace(run=run,may_have_delivered=lambda c:True)
        r=ReleaseWorker(jobs,bridge,CONFIG).run_once()
        self.assertEqual(r.status,'unknown_reconcile');self.assertEqual(jobs.completed,[])
    def test_preflight_failure_is_not_claimed_as_success(self):
        jobs=FakeJobs(context(candidate_status='awaiting_approval'))
        bridge=SimpleNamespace(run=lambda *a,**k:self.fail('should not run'),may_have_delivered=lambda c:False)
        r=ReleaseWorker(jobs,bridge,CONFIG).run_once()
        self.assertEqual(r.status,'failed_retriable')
    def test_busy_no_claim(self):
        jobs=FakeJobs(context())
        @contextmanager
        def busy():yield False
        jobs.site_lock=busy
        r=ReleaseWorker(jobs,None,CONFIG).run_once()
        self.assertEqual(r.status,'busy');self.assertEqual(jobs.claimed,0)
    def test_idle_no_side_effect(self):
        jobs=FakeJobs(None)
        self.assertEqual(ReleaseWorker(jobs,None,CONFIG).run_once().status,'idle')
    def test_guard_before_claim(self):
        jobs=FakeJobs(context())
        def fail():raise ValueError('stale')
        guard=SimpleNamespace(assert_current=fail)
        with self.assertRaises(ValueError):ReleaseWorker(jobs,None,CONFIG,runtime_guard=guard).run_once()
        self.assertEqual(jobs.claimed,0)
    def test_reconcile_uses_reconcile_path(self):
        jobs=FakeJobs(context()); called=[]
        bridge=SimpleNamespace(run=lambda c,**k:(called.append(k) or 'published'),may_have_delivered=lambda c:True)
        ReleaseWorker(jobs,bridge,CONFIG).reconcile('JOB99990001')
        self.assertEqual(called,[{'reconcile':True}])


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.c=context();self.jobs=FakeJobs(self.c);self.projection=ProjectionDouble()
        self.builder=ReleaseBuilder(source_assets=assets(self.root),config=CONFIG,source_commit='synthetic')
        self.events=[]
        self.client=SimpleNamespace(publish=self.publish,reconcile=self.reconcile)
        self.authority=SimpleNamespace(desired_articles=lambda c:(article(),))
    def tearDown(self):self.temp.cleanup()
    def publish(self,*args):
        self.events.append('publish')
        return HereNowReceipt('synthetic-confluence','v1',1,False)
    def reconcile(self,*args):
        self.events.append('reconcile')
        return HereNowReceipt('synthetic-confluence','v1',0,True)
    def make(self,**kw):
        return ReleaseDelivery(self.c,config=CONFIG,jobs=self.jobs,authority=self.authority,
            projection=self.projection,builder=self.builder,client=self.client,
            release_root=self.root/'releases',readback=kw.pop('readback',lambda *a,**k: {'checksums':'exact'}),**kw)
    def test_build_freezes_before_upload(self):
        d=self.make();d.prepare()
        self.assertEqual(self.events,[]);self.assertIn('static_build',self.jobs.saved)
        d.perform(dispatch(self.c));self.assertEqual(self.events,['publish'])
        self.assertIn('public_readback',self.jobs.saved)
    def test_reconcile_no_reupload_no_rebuild(self):
        d=self.make();d.prepare();first=d.receipt.checksums.copy()
        self.builder.build=lambda *a,**k:self.fail('must not rebuild')
        new=self.make();new.prepare();self.assertTrue(new.lookup(dispatch(self.c)))
        self.assertEqual(self.events,['reconcile']);self.assertEqual(new.receipt.checksums,first)
    def test_lookup_mismatch_not_success(self):
        d=self.make();d.prepare();self.client.reconcile=lambda *a:None
        self.assertFalse(d.lookup(dispatch(self.c)))
    def test_readback_failure_keeps_delivery_marker(self):
        def fail(*a,**k):raise OSError('readback')
        d=self.make(readback=fail);d.prepare()
        with self.assertRaises(OSError):d.perform(dispatch(self.c))
        self.assertIn('here_now_started',self.jobs.saved);self.assertNotIn('public_readback',self.jobs.saved)
    def test_hash_mismatch_before_upload(self):
        d=self.make();d.prepare();bad=dispatch(self.c);bad.payload_sha256='0'*64
        with self.assertRaises(ValueError):d.perform(bad)
        self.assertEqual(self.events,[])
    def test_saved_artifact_tamper_stops_reconcile(self):
        d=self.make();d.prepare();(d.receipt.output/'index.html').write_text('extra')
        with self.assertRaises(ValueError):self.make().prepare()
        self.assertEqual(self.events,[])
    def test_runtime_guard_before_remote(self):
        def fail():raise ValueError('stale runtime')
        guard=SimpleNamespace(assert_current=lambda:None)
        d=self.make(runtime_guard=guard);d.prepare()
        guard.assert_current=fail
        with self.assertRaises(ValueError):d.perform(dispatch(self.c))
        self.assertNotIn('here_now_started',self.jobs.saved);self.assertEqual(self.events,[])

if __name__=='__main__':unittest.main()
