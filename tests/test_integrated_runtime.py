"""Real worker/delivery + real shared lock/guard, explicit JOB/hosting doubles.

These are wiring regressions, not a PostgreSQL or deployment acceptance claim.
"""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from confluence_pressroom import public_release_lock as safety_lock
from confluence_pressroom import release_runtime_guard as safety_guard
from confluence_release import release_lock, runtime_guard
from confluence_release.artifacts import ReleaseBuilder
from confluence_release.delivery import ReleaseDelivery
from confluence_release.here_now_client import HereNowReceipt
from confluence_release.job_store import ReleaseJobStore
from confluence_release.worker import ReleaseWorker
from phase2_support import CONFIG, FakeJobs, ProjectionDouble, article, assets, context, dispatch
from release_safety_test_support import repository


class IntegratedRuntimeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.project = self.root/'project'
        self.project.mkdir()
        repository(self.project)
        self.guard = runtime_guard.ReleaseRuntimeGuard.capture(self.project)
        self.c = context()
        self.jobs = FakeJobs(self.c)
        self.store = ReleaseJobStore(None, CONFIG, self.root/'releases')
        self.jobs.site_lock = self.store.site_lock
        self.projection = ProjectionDouble()
        self.builder = ReleaseBuilder(source_assets=assets(self.root), config=CONFIG,
                                      source_commit=self.guard.source_commit)
        self.events = []
        self.client = SimpleNamespace(publish=self.publish, reconcile=self.reconcile)
        self.authority = SimpleNamespace(desired_articles=lambda c: (article(),))
        self.readback = lambda *a, **k: {'checksums': 'exact'}

    def dirty(self):
        (self.project/'tools/build.py').write_text('# changed after startup\n')

    def publish(self, *args):
        self.events.append('publish')
        return HereNowReceipt('synthetic-confluence', 'v1', 1, False)

    def reconcile(self, *args):
        self.events.append('reconcile')
        return HereNowReceipt('synthetic-confluence', 'v1', 0, True)

    def delivery(self):
        return ReleaseDelivery(self.c, config=CONFIG, jobs=self.jobs, authority=self.authority,
            projection=self.projection, builder=self.builder, client=self.client,
            release_root=self.root/'releases', runtime_guard=self.guard, readback=self.readback)

    def worker(self, run, *, delivered=True):
        bridge = SimpleNamespace(run=run, may_have_delivered=lambda c: delivered)
        return ReleaseWorker(self.jobs, bridge, CONFIG, runtime_guard=self.guard)

    def test_aliases_share_classes_functions_and_errors(self):
        self.assertIs(release_lock.public_release_lock, safety_lock.public_release_lock)
        self.assertIs(release_lock.PublicReleaseBusyError, safety_lock.PublicReleaseBusyError)
        self.assertIs(runtime_guard.ReleaseRuntimeGuard, safety_guard.ReleaseRuntimeGuard)
        self.assertIs(runtime_guard.StaleReleaseRuntimeError, safety_guard.StaleReleaseRuntimeError)

    def test_shared_guard_covers_both_packages_and_tools(self):
        self.assertTrue({'src/confluence_release', 'src/confluence_pressroom', 'prototype', 'tools'} <= set(runtime_guard.RUNTIME_INPUTS))
        folder = self.project/'src/confluence_release'
        folder.mkdir()
        (folder/'worker.py').write_text('# new untracked runtime source\n')
        with self.assertRaises(runtime_guard.StaleReleaseRuntimeError): self.guard.assert_current()

    def test_helper_lock_blocks_worker_before_normal_or_reconcile_claim(self):
        with safety_lock.public_release_lock(self.root/'releases'):
            w = self.worker(lambda *a, **k: self.fail('must not run'))
            self.assertEqual(w.run_once().status, 'busy')
            self.assertEqual(w.reconcile(self.c.job_ref).status, 'busy')
        self.assertEqual(self.jobs.claimed, 0)

    def test_worker_holds_shared_lock_through_finalization(self):
        complete = self.jobs.complete
        def finish(job, **kwargs):
            with self.assertRaises(release_lock.PublicReleaseBusyError):
                with safety_lock.public_release_lock(self.root/'releases'): pass
            complete(job, **kwargs)
        self.jobs.complete = finish
        result = self.worker(lambda *a, **k: 'published').run_once()
        self.assertEqual(result.status, 'published')
        with safety_lock.public_release_lock(self.root/'releases'): pass

    def test_stale_before_claim_cannot_start_worker(self):
        self.dirty()
        with self.assertRaises(runtime_guard.StaleReleaseRuntimeError):
            self.worker(lambda *a, **k: self.fail('not called')).run_once()
        self.assertEqual(self.jobs.claimed, 0)

    def test_stale_during_claim_cannot_enter_bridge(self):
        old = self.jobs.claim
        def claim(*a, **k):
            c = old(*a, **k)
            self.dirty()
            return c
        self.jobs.claim = claim
        r = self.worker(lambda *a, **k: self.fail('bridge must not run'), delivered=False).run_once()
        self.assertEqual(r.status, 'failed_retriable')
        self.assertEqual(self.jobs.completed, [])

    def test_stale_prepare_cannot_write_projection_or_artifact(self):
        self.dirty()
        with self.assertRaises(runtime_guard.StaleReleaseRuntimeError): self.delivery().prepare()
        self.assertEqual(self.projection.rows, ())
        self.assertEqual(self.jobs.saved, {})

    def test_change_while_building_stops_before_external_delivery(self):
        build = self.builder.build
        def changed(*args):
            value = build(*args)
            self.dirty()
            return value
        self.builder.build = changed
        with self.assertRaises(runtime_guard.StaleReleaseRuntimeError): self.delivery().prepare()
        self.assertIn('static_build', self.jobs.saved)
        self.assertEqual(self.events, [])

    def test_change_during_upload_blocks_readback_and_ledger_return(self):
        def changed(*args):
            value = self.publish(*args)
            self.dirty()
            return value
        self.client.publish = changed
        self.readback = lambda *a, **k: self.fail('stale code must stop before readback')
        d = self.delivery(); d.prepare()
        with self.assertRaises(runtime_guard.StaleReleaseRuntimeError): d.perform(dispatch(self.c))
        self.assertNotIn('public_readback', self.jobs.saved)

    def test_change_during_readback_never_returns_for_ledger_finalization(self):
        finalized = []
        def changed(*args, **kwargs):
            self.dirty()
            return {'checksums': 'exact'}
        self.readback = changed
        d = self.delivery()
        def run(*a, **k):
            d.prepare(); d.perform(dispatch(self.c))
            finalized.append('canonical ledger would finalize')
            return 'published'
        result = self.worker(run).run_once()
        self.assertEqual(result.status, 'unknown_reconcile')
        self.assertEqual(finalized, [])
        self.assertEqual(self.jobs.completed, [])
        self.assertNotIn('public_readback', self.jobs.saved)

    def test_reconcile_uses_same_post_readback_guard_without_reupload(self):
        d = self.delivery(); d.prepare()
        def changed(*args, **kwargs):
            self.dirty()
            return {'checksums': 'exact'}
        self.readback = changed
        recovered = self.delivery(); recovered.prepare(allow_build=False)
        with self.assertRaises(runtime_guard.StaleReleaseRuntimeError): recovered.lookup(dispatch(self.c))
        self.assertEqual(self.events, ['reconcile'])
        self.assertNotIn('public_readback', self.jobs.saved)

    def test_change_while_recording_evidence_stops_before_ledger_return(self):
        d = self.delivery(); d.prepare()
        record = self.jobs.record
        def changed(job, step, value):
            record(job, step, value)
            if step == 'public_readback': self.dirty()
        self.jobs.record = changed
        with self.assertRaises(runtime_guard.StaleReleaseRuntimeError): d.perform(dispatch(self.c))
        self.assertEqual(self.events, ['publish'])

    def test_change_after_bridge_blocks_job_completion_and_releases_lock(self):
        def run(*a, **k):
            self.dirty()
            return 'published'
        r = self.worker(run).run_once()
        self.assertEqual(r.status, 'unknown_reconcile')
        self.assertEqual(self.jobs.completed, [])
        with safety_lock.public_release_lock(self.root/'releases'): pass


if __name__ == '__main__': unittest.main()
