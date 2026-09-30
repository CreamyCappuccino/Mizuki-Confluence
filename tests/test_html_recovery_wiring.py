"""Recovery uses the frozen artifact with real delivery/readback/lock/guard.

JOB/provider/authority ports are explicit doubles; this is not a real PG run.
"""
from copy import deepcopy
from dataclasses import replace
from functools import partial
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from confluence_pressroom.release_http import ReadbackResponse, target_url
from confluence_release.artifacts import ReleaseBuilder, read_files
from confluence_release.composition import create_release_worker
from confluence_release.delivery import ReleaseDelivery
from confluence_release.here_now_client import HereNowReceipt
from confluence_release.job_store import ReleaseJobStore
from confluence_release.readback import verify_public_artifact
from confluence_release.runtime_guard import ReleaseRuntimeGuard
from confluence_release.worker import ReleaseWorker
from phase2_support import CONFIG, FakeJobs, article, assets, context, dispatch
from release_safety_test_support import repository
from test_here_now_html_policy import policy, literal_block


class HtmlRecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        project = self.root / 'project'; project.mkdir(); repository(project)
        self.guard = ReleaseRuntimeGuard.capture(project)
        self.c = context(attempt_status='publishing')
        self.jobs = FakeJobs(self.c)
        self.release_root = self.root / 'releases'
        self.jobs.site_lock = ReleaseJobStore(None, CONFIG, self.release_root).site_lock
        self.receipt = ReleaseBuilder(source_assets=assets(self.root), config=CONFIG,
            source_commit='original-published-build').build((article(),), self.release_root / str(self.c.job_id))
        self.jobs.saved['static_build'] = self.receipt.as_record()
        self.jobs.saved['here_now'] = dict(slug=CONFIG.here_now_slug, version_id='frozen-v1',
                                          uploaded_files=21, reconciled=False)
        self.files = read_files(self.receipt.output)
        self.orig_static = deepcopy(self.jobs.saved['static_build'])
        self.profile = policy(expected_manifest_sha256=self.receipt.checksums['checksums.sha256'])
        self.remote = {}
        for base in (CONFIG.here_now_base, CONFIG.nor_base):
            for name, data in self.files.items():
                raw = (data.replace(b'</head>', literal_block(base, name) + b'</head>', 1)
                       if name.endswith('.html') else data)
                self.remote[target_url(base, name)] = ReadbackResponse(200, raw)
        self.network = []
        self.client = SimpleNamespace(
            publish=Mock(side_effect=AssertionError('no re-upload')),
            reconcile=Mock(return_value=HereNowReceipt(CONFIG.here_now_slug, 'frozen-v1', 0, True)))
        self.builder = SimpleNamespace(build=Mock(side_effect=AssertionError('no rebuild')))
        self.projection = SimpleNamespace(replace_all=Mock(side_effect=AssertionError('no replace')))
        self.authority = SimpleNamespace(desired_articles=Mock(side_effect=AssertionError('no reproject')))

    def fetch(self, url):
        self.network.append(url)
        return self.remote.get(url, ReadbackResponse(404, b''))

    def delivery(self, profile=True):
        return ReleaseDelivery(self.c, config=CONFIG, jobs=self.jobs,
            authority=self.authority, projection=self.projection, builder=self.builder,
            client=self.client, release_root=self.release_root, runtime_guard=self.guard,
            readback=partial(verify_public_artifact, fetch=self.fetch),
            html_policy=self.profile if profile else None)

    def worker(self, delivery):
        def run(c, *, reconcile=False):
            self.assertTrue(reconcile)
            delivery.prepare(allow_build=False)
            if not delivery.lookup(dispatch(c)): raise ValueError('not verified')
            return 'published'  # Canonical boundary double; not real PUB proof.
        bridge = SimpleNamespace(run=run, may_have_delivered=lambda c: True)
        return ReleaseWorker(self.jobs, bridge, CONFIG, runtime_guard=self.guard)

    def test_reconcile_preserves_original_files_receipt_and_never_uploads(self):
        result = self.worker(self.delivery()).reconcile(self.c.job_ref)
        self.assertEqual(result.status, 'published')
        self.assertEqual(self.jobs.completed, ['published'])
        self.assertEqual(self.jobs.saved['static_build'], self.orig_static)
        self.assertEqual(read_files(self.receipt.output), self.files)
        self.assertIn(b'original-published-build', self.files['release-manifest.json'])
        self.assertEqual(self.jobs.saved['public_readback']['html_policy']['sha256'], self.profile.sha256)
        self.client.publish.assert_not_called(); self.builder.build.assert_not_called()
        self.projection.replace_all.assert_not_called(); self.authority.desired_articles.assert_not_called()
        self.assertEqual(self.client.reconcile.call_count, 1)

    def test_default_still_unknown_and_no_completion(self):
        result = self.worker(self.delivery(profile=False)).reconcile(self.c.job_ref)
        self.assertEqual(result.status, 'unknown_reconcile')
        self.assertEqual(self.jobs.completed, [])
        self.assertNotIn('public_readback', self.jobs.saved)
        self.client.publish.assert_not_called()

    def test_unapproved_remote_difference_never_completes_job(self):
        url = target_url(CONFIG.nor_base, self.receipt.article_routes[0])
        self.remote[url] = ReadbackResponse(200, self.remote[url].body + b'changed')
        result = self.worker(self.delivery()).reconcile(self.c.job_ref)
        self.assertEqual(result.status, 'unknown_reconcile')
        self.assertEqual(self.jobs.completed, [])
        self.assertEqual(self.jobs.saved['static_build'], self.orig_static)
        self.client.publish.assert_not_called()

    def test_wrong_manifest_policy_stops_before_provider_lookup(self):
        self.profile = replace(self.profile, expected_manifest_sha256='0' * 64)
        result = self.worker(self.delivery()).reconcile(self.c.job_ref)
        self.assertEqual(result.status, 'unknown_reconcile')
        self.client.reconcile.assert_not_called(); self.client.publish.assert_not_called()
        self.assertEqual(self.network, [])

    def test_guard_is_not_disabled_for_old_artifact(self):
        (self.guard.project_root / 'tools/build.py').write_text('# stale\n')
        with self.assertRaises(RuntimeError):
            self.worker(self.delivery()).reconcile(self.c.job_ref)
        self.assertEqual(self.network, [])
        self.client.reconcile.assert_not_called()

    def test_factory_propagates_profile_without_replacing_shared_guard(self):
        jobs = object(); projection = object(); builder = object()
        with patch('confluence_release.composition.ReleaseJobStore', return_value=jobs), patch(
            'confluence_release.composition.PostgresProjectionStore', return_value=projection), patch(
            'confluence_release.composition.ReleaseBuilder', return_value=builder):
            worker = create_release_worker(None, config=CONFIG, projection_database_url='test-only',
                project_root=self.guard.project_root, release_root=self.release_root,
                here_now_client=self.client, html_policy=self.profile)
        self.assertIs(worker.bridge.html_policy, self.profile)
        self.assertIs(worker.runtime_guard, worker.bridge.runtime_guard)
        worker.runtime_guard.assert_current()

    def test_factory_rejects_wrong_target_before_creating_stores(self):
        wrong = replace(self.profile, nor_base='https://other.invalid/confluence')
        with patch('confluence_release.composition.ReleaseJobStore') as jobs, self.assertRaises(ValueError):
            create_release_worker(None, config=CONFIG, projection_database_url='test-only',
                project_root=self.guard.project_root, release_root=self.release_root,
                here_now_client=self.client, html_policy=wrong)
        jobs.assert_not_called()
