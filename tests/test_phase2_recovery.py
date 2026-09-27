"""Focused recovery delta tests; no real Pressroom or database involved."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from confluence_release.artifacts import ReleaseBuilder
from confluence_release.composition import PublicationBridge
from confluence_release.delivery import ReleaseDelivery
from confluence_release.job_store import ReleaseJobStore
from confluence_release.release_lock import PublicReleaseBusyError
from phase2_support import CONFIG, FakeJobs, ProjectionDouble, article, assets, context


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.c = context()
        self.jobs = FakeJobs(self.c)
        self.projection = ProjectionDouble()
        self.builder = ReleaseBuilder(source_assets=assets(self.root), config=CONFIG, source_commit='synthetic')
        self.authority = SimpleNamespace(desired_articles=lambda c: (article(),))
    def tearDown(self):
        self.temp.cleanup()
    def delivery(self, c=None):
        return ReleaseDelivery(c or self.c, config=CONFIG, jobs=self.jobs,
            authority=self.authority, projection=self.projection, builder=self.builder,
            client=None, release_root=self.root/'releases')
    def test_no_receipt_reconcile_never_builds(self):
        with self.assertRaises(ValueError):
            self.delivery().prepare(allow_build=False)
        self.assertFalse((self.root/'releases').exists())
        self.assertEqual(self.projection.rows, ())
    def test_active_or_completed_attempt_never_invents_artifact(self):
        for state in ('publishing', 'unpublishing', 'published', 'unpublished', 'failed'):
            with self.subTest(state=state), self.assertRaises(ValueError):
                self.delivery(replace(self.c, attempt_status=state)).prepare()
        self.assertEqual(self.projection.rows, ())
    def test_started_marker_without_receipt_never_rebuilds(self):
        self.jobs.saved['here_now_started'] = {'synthetic': True}
        with self.assertRaises(ValueError):
            self.delivery().prepare()
        self.assertFalse((self.root/'releases').exists())
    def test_saved_receipt_allowed_for_recovery(self):
        self.delivery().prepare()
        self.builder.build = lambda *a: self.fail('no rebuild')
        d = self.delivery(replace(self.c, attempt_status='publishing'))
        d.prepare(allow_build=False)
        self.assertIsNotNone(d.receipt)
    def test_failure_classification_reads_current_ledger_not_stale_context(self):
        self.jobs.publication_status = lambda job: 'publishing'
        bridge = PublicationBridge(None, CONFIG, self.jobs, None, None, None, None, None)
        self.assertTrue(bridge.may_have_delivered(self.c))
        self.jobs.publication_status = lambda job: 'failed'
        self.assertFalse(bridge.may_have_delivered(self.c))
    def test_missing_ledger_evidence_is_unknown(self):
        bridge = PublicationBridge(None, CONFIG, self.jobs, None, None, None, None, None)
        self.assertTrue(bridge.may_have_delivered(self.c))
    def test_site_lock_does_not_swallow_body_error(self):
        jobs = ReleaseJobStore(None, CONFIG, self.root/'locks')
        with self.assertRaises(PublicReleaseBusyError):
            with jobs.site_lock() as ok:
                self.assertTrue(ok)
                raise PublicReleaseBusyError('body failure, not lock acquisition')
        with jobs.site_lock() as ok:
            self.assertTrue(ok)
