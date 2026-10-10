"""Real relocated-file/lock/guard/readback seam; explicit JOB/provider doubles.

No actual PostgreSQL, production files, provider or canonical finalization here.
"""
from dataclasses import asdict, replace
from functools import partial
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_artifact_location as location_fixture
from confluence_pressroom.release_http import ReadbackResponse, target_url
from confluence_release.artifacts import read_files
from confluence_release.composition import create_release_worker
from confluence_release.delivery import ReleaseDelivery
from confluence_release.html_policy import load_html_policy
from confluence_release.readback import verify_public_artifact
from confluence_release.release_lock import public_release_lock
from confluence_release.worker import ReleaseWorker
from image_html_test_support import image_policy, literal_image_block
from phase2_support import CONFIG, dispatch


class ImageRelocatedRecoveryTests(unittest.TestCase):
    # Reuse only synthetic setup/helpers; don't inflate counts by inheriting tests.
    write_profile = location_fixture.LocationTests.write_profile
    fetch = location_fixture.LocationTests.fetch

    def setUp(self):
        location_fixture.LocationTests.setUp(self)
        self.files = read_files(self.new_output)
        p=image_policy(expected_manifest_sha256=self.old.checksums['checksums.sha256'])
        path=self.root/'image-policy.json';path.write_text(json.dumps(asdict(p)));path.chmod(0o600)
        self.html_policy=load_html_policy(path)
        for base in (CONFIG.here_now_base,CONFIG.nor_base):
            for name,data in self.files.items():
                raw=data.replace(b'</head>',literal_image_block(base,name)+b'</head>',1) if name.endswith('.html') else data
                self.remote[target_url(base,name)]=ReadbackResponse(200,raw)
        shutil.rmtree(self.old_root)

    def delivery(self, with_policy=True):
        return ReleaseDelivery(self.c,config=CONFIG,jobs=self.jobs,
            authority=SimpleNamespace(desired_articles=self.no_build),
            projection=SimpleNamespace(replace_all=self.no_build),
            builder=SimpleNamespace(build=self.no_build),client=self.client,
            release_root=self.new_root,runtime_guard=self.guard,
            artifact_location=self.location,
            html_policy=self.html_policy if with_policy else None,
            readback=partial(verify_public_artifact,fetch=self.fetch))

    def worker(self, with_policy=True):
        d=self.delivery(with_policy)
        def run(c, *, reconcile=False):
            self.assertTrue(reconcile)
            d.prepare(allow_build=False)
            if not d.lookup(dispatch(c)): raise ValueError('not verified')
            return 'published'  # Existing canonical workflow boundary double.
        return ReleaseWorker(self.jobs,SimpleNamespace(run=run,may_have_delivered=lambda c:True),
            CONFIG,runtime_guard=self.guard,required_job_ref=self.location.job_ref)

    def test_same_job_recovery_with_both_policies_preserves_history_and_bytes(self):
        result=self.worker().reconcile(self.c.job_ref)
        self.assertEqual(result.status,'published')
        self.assertEqual(self.jobs.completed,['published'])
        self.assertEqual(self.jobs.saved['static_build'],self.original)
        self.assertEqual(read_files(self.new_output),self.files)
        self.assertFalse(self.old_root.exists())
        self.assertIn(b'frozen-old-commit',self.files['release-manifest.json'])
        evidence=self.jobs.saved['public_readback']
        self.assertEqual(evidence['artifact_location']['sha256'],self.location.sha256)
        self.assertEqual(evidence['html_policy']['sha256'],self.html_policy.sha256)
        self.assertEqual(evidence['transformed_html'],8)
        self.assertEqual(self.client.reconcile.call_count,1)
        self.assertEqual(self.client.reconcile.call_args.args[1].output,self.new_output)
        self.client.publish.assert_not_called();self.no_build.assert_not_called()

    def test_no_profile_stays_unknown_without_completing_or_uploading(self):
        self.assertEqual(self.worker(with_policy=False).reconcile(self.c.job_ref).status,'unknown_reconcile')
        self.assertEqual(self.jobs.completed,[])
        self.assertNotIn('public_readback',self.jobs.saved)
        self.assertEqual(self.jobs.saved['static_build'],self.original)
        self.client.publish.assert_not_called();self.no_build.assert_not_called()

    def test_extra_remote_tag_stays_unknown_and_does_not_complete(self):
        url=target_url(CONFIG.nor_base,'writers.html')
        self.remote[url]=ReadbackResponse(200,self.remote[url].body.replace(b'</head>',
            b'<meta name="extra" content="no" /></head>'))
        self.assertEqual(self.worker().reconcile(self.c.job_ref).status,'unknown_reconcile')
        self.assertEqual(self.jobs.completed,[])
        self.assertNotIn('public_readback',self.jobs.saved)
        self.assertEqual(self.jobs.saved['static_build'],self.original)
        self.client.publish.assert_not_called()

    def test_wrong_html_manifest_or_location_manifest_never_looks_up_provider(self):
        self.html_policy=replace(self.html_policy,expected_manifest_sha256='b'*64)
        self.assertEqual(self.worker().reconcile(self.c.job_ref).status,'unknown_reconcile')
        self.assertEqual(self.calls,[]);self.client.reconcile.assert_not_called()
        self.html_policy=replace(self.html_policy,expected_manifest_sha256=self.location.manifest_sha256)
        self.location=replace(self.location,manifest_sha256='b'*64)
        self.assertEqual(self.worker().reconcile(self.c.job_ref).status,'unknown_reconcile')
        self.assertEqual(self.calls,[]);self.client.reconcile.assert_not_called()

    def test_changed_saved_receipt_does_not_gain_new_location_authority(self):
        self.jobs.saved['static_build']['output']=str(self.new_output)
        self.assertEqual(self.worker().reconcile(self.c.job_ref).status,'unknown_reconcile')
        self.client.reconcile.assert_not_called(); self.client.publish.assert_not_called()

    def test_changed_relocated_byte_cannot_be_hidden_by_image_policy(self):
        target=self.new_output/'index.html';target.write_bytes(target.read_bytes()+b'x')
        self.assertEqual(self.worker().reconcile(self.c.job_ref).status,'unknown_reconcile')
        self.client.reconcile.assert_not_called();self.assertEqual(self.jobs.completed,[])

    def test_other_job_is_rejected_before_claim_even_with_html_policy(self):
        with self.assertRaises(ValueError):self.worker().reconcile('JOB99998888')
        self.assertEqual(self.jobs.claimed,0);self.client.reconcile.assert_not_called()

    def test_stale_runtime_and_site_lock_still_precede_recovery(self):
        with public_release_lock(self.new_root):
            self.assertEqual(self.worker().reconcile(self.c.job_ref).status,'busy')
        self.assertEqual(self.jobs.claimed,0);self.client.reconcile.assert_not_called()
        (self.guard_root/'tools/build.py').write_text('#changed')
        with self.assertRaises(RuntimeError):self.worker().reconcile(self.c.job_ref)
        self.assertEqual(self.jobs.claimed,0);self.client.reconcile.assert_not_called()

    def test_factory_preserves_both_policies_and_shared_guard_without_store_side_effects(self):
        with patch('confluence_release.composition.ReleaseJobStore',return_value=self.jobs),patch(
            'confluence_release.composition.PostgresProjectionStore',return_value=object()),patch(
            'confluence_release.composition.ReleaseBuilder',return_value=object()):
            w=create_release_worker(None,config=CONFIG,projection_database_url='test-only',
                project_root=self.guard_root,release_root=self.new_root,here_now_client=self.client,
                html_policy=self.html_policy,artifact_location=self.location)
        self.assertIs(w.bridge.html_policy,self.html_policy)
        self.assertIs(w.bridge.artifact_location,self.location)
        self.assertIs(w.runtime_guard,w.bridge.runtime_guard)
        w.runtime_guard.assert_current()
        self.client.reconcile.assert_not_called();self.client.publish.assert_not_called()
