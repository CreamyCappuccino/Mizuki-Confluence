"""Real relocated files/guard/readback, explicit JOB/provider ports; no production."""
from copy import deepcopy
from dataclasses import asdict, replace
from functools import partial
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from confluence_pressroom.release_http import ReadbackResponse, target_url
from confluence_release.artifact_location import (
    ArtifactLocation, absolute_path, load_artifact_location, record_digest,
)
from confluence_release.artifacts import ReleaseBuilder, read_files
from confluence_release.cli import main
from confluence_release.composition import create_release_worker
from confluence_release.delivery import ReleaseDelivery
from confluence_release.here_now_client import HereNowReceipt
from confluence_release.job_store import ReleaseJobStore
from confluence_release.readback import verify_public_artifact
from confluence_release.runtime_guard import ReleaseRuntimeGuard, StaleReleaseRuntimeError
from confluence_release.worker import ReleaseWorker
from phase2_support import CONFIG, FakeJobs, article, assets, context, dispatch
from release_safety_test_support import repository


class LocationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.c = context(attempt_status='publishing')
        self.old_root = self.root / 'old/releases'
        self.new_root = self.root / 'project/releases'
        self.old = ReleaseBuilder(source_assets=assets(self.root), config=CONFIG,
            source_commit='frozen-old-commit').build((article(),), self.old_root / str(self.c.job_id))
        self.saved = self.old.as_record()
        self.original = deepcopy(self.saved)
        self.new_output = self.new_root / str(self.c.job_id)
        shutil.copytree(self.old.output, self.new_output)
        self.location = ArtifactLocation(job_ref=self.c.job_ref, job_id=str(self.c.job_id),
            pipeline_key=CONFIG.pipeline_key, original_output=str(self.old.output),
            relocated_output=str(self.new_output), static_build_sha256=record_digest(self.saved),
            manifest_sha256=self.old.checksums['checksums.sha256'])
        self.jobs = FakeJobs(self.c); self.jobs.saved['static_build'] = deepcopy(self.saved)
        self.jobs.site_lock = ReleaseJobStore(None, CONFIG, self.new_root).site_lock
        self.profile_file = self.root/'location.json'
        self.write_profile()
        self.client = SimpleNamespace(publish=Mock(side_effect=AssertionError('no upload')),
            reconcile=Mock(return_value=HereNowReceipt(CONFIG.here_now_slug, 'unchanged-v1', 0, True)))
        self.no_build = Mock(side_effect=AssertionError('no build/projection'))
        self.guard_root = self.root/'code'; self.guard_root.mkdir(); repository(self.guard_root)
        self.guard = ReleaseRuntimeGuard.capture(self.guard_root)
        self.calls = []
        self.remote = {target_url(base, name): ReadbackResponse(200, data)
            for base in (CONFIG.here_now_base, CONFIG.nor_base)
            for name, data in read_files(self.old.output).items()}

    def write_profile(self, values=None):
        self.profile_file.write_text(json.dumps(asdict(self.location) if values is None else values))
        self.profile_file.chmod(0o600)

    def fetch(self, url):
        self.calls.append(url)
        return self.remote.get(url, ReadbackResponse(404, b''))

    def delivery(self, location=True):
        return ReleaseDelivery(self.c, config=CONFIG, jobs=self.jobs,
            authority=SimpleNamespace(desired_articles=self.no_build),
            projection=SimpleNamespace(replace_all=self.no_build),
            builder=SimpleNamespace(build=self.no_build), client=self.client,
            release_root=self.new_root, runtime_guard=self.guard,
            artifact_location=self.location if location else None,
            readback=partial(verify_public_artifact, fetch=self.fetch))

    def test_relocated_bytes_preserve_original_receipt_and_old_source_commit(self):
        shutil.rmtree(self.old_root)
        relocated = self.location.locate(self.saved, self.c, self.new_root)
        self.assertEqual(relocated.output, self.new_output)
        self.assertEqual(relocated.checksums, self.old.checksums)
        self.assertEqual(self.saved, self.original)
        self.assertIn(b'frozen-old-commit', (relocated.output/'release-manifest.json').read_bytes())

    def test_real_readback_and_guard_use_only_new_physical_path_without_publish(self):
        shutil.rmtree(self.old_root)
        d = self.delivery(); d.prepare(allow_build=False)
        self.assertTrue(d.lookup(dispatch(self.c)))
        self.assertEqual(self.jobs.saved['static_build'], self.original)
        evidence = self.jobs.saved['public_readback']
        self.assertEqual(evidence['artifact_location']['sha256'], self.location.sha256)
        self.assertEqual(evidence['checksums'], 'exact')
        self.assertEqual(self.client.reconcile.call_args.args[1].output, self.new_output)
        self.client.publish.assert_not_called(); self.no_build.assert_not_called()

    def test_missing_explicit_record_does_not_rebind(self):
        with self.assertRaises(ValueError): self.delivery(location=False).prepare(allow_build=False)
        self.client.reconcile.assert_not_called(); self.assertEqual(self.calls, [])

    def test_missing_new_location_does_not_fall_back_to_existing_old_copy(self):
        shutil.rmtree(self.new_output)
        with self.assertRaises((ValueError, FileNotFoundError)): self.delivery().prepare(allow_build=False)
        self.client.reconcile.assert_not_called(); self.no_build.assert_not_called()

    def test_changed_saved_receipt_rejected_for_every_field(self):
        for key, value in (('output', str(self.new_output)), ('content_digest', '0'*64),
                           ('article_routes', []), ('checksums', {})):
            altered = deepcopy(self.saved); altered[key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                self.location.locate(altered, self.c, self.new_root)

    def test_changed_manifest_pin_rejected(self):
        loc = replace(self.location, manifest_sha256='0'*64)
        with self.assertRaises(ValueError): loc.locate(self.saved, self.c, self.new_root)

    def test_wrong_job_pipeline_destination_and_runtime_root_rejected(self):
        for changes in ({'job_ref': 'JOB99990002'}, {'job_id': self.c.attempt_id},
                        {'job_pipeline_key': 'other'}, {'destination_key': 'ai-inner-life'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.location.locate(self.saved, replace(self.c, **changes), self.new_root)
        with self.assertRaises(ValueError):
            self.location.locate(self.saved, self.c, self.root/'other')

    def test_one_byte_edit_extra_missing_and_symlink_all_fail_before_lookup(self):
        target = self.new_output/'index.html'
        before = target.read_bytes()
        mutations = ('changed', 'extra', 'missing', 'link')
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                if mutation == 'changed': target.write_bytes(before+b'x')
                elif mutation == 'extra': (self.new_output/'extra.txt').write_text('x')
                elif mutation == 'missing': target.unlink()
                else: target.unlink(); target.symlink_to(self.old.output/'index.html')
                with self.assertRaises(ValueError): self.delivery().prepare(allow_build=False)
                if target.is_symlink(): target.unlink()
                target.write_bytes(before)
                (self.new_output/'extra.txt').unlink(missing_ok=True)
        self.client.reconcile.assert_not_called()

    def test_symlink_ancestor_cannot_bypass_root_validation(self):
        alias = self.root/'alias'; alias.symlink_to(self.root/'project', target_is_directory=True)
        loc = replace(self.location, relocated_output=str(alias/'releases'/str(self.c.job_id)))
        with self.assertRaises(ValueError): loc.locate(self.saved, self.c, alias/'releases')

    def test_changed_local_file_after_prepare_fails_before_provider(self):
        d = self.delivery(); d.prepare(allow_build=False)
        (self.new_output/'index.html').write_bytes(b'tamper')
        with self.assertRaises(ValueError): d.lookup(dispatch(self.c))
        self.client.reconcile.assert_not_called()

    def test_stale_runtime_still_stops_before_location_use(self):
        (self.guard_root/'tools/build.py').write_text('# changed')
        with self.assertRaises(StaleReleaseRuntimeError): self.delivery().prepare(allow_build=False)
        self.client.reconcile.assert_not_called()

    def test_missing_static_receipt_never_builds(self):
        self.jobs.saved.clear()
        with self.assertRaises(ValueError): self.delivery().prepare()
        self.no_build.assert_not_called()

    def test_failed_readback_keeps_job_unknown_and_original_receipt(self):
        self.remote[target_url(CONFIG.nor_base, 'index.html')] = ReadbackResponse(200, b'9-meta mismatch')
        d = self.delivery()
        def run(c, **kwargs):
            d.prepare(allow_build=False); d.lookup(dispatch(c)); return 'published'
        bridge = SimpleNamespace(run=run, may_have_delivered=lambda c: True)
        worker = ReleaseWorker(self.jobs, bridge, CONFIG, runtime_guard=self.guard,
                               required_job_ref=self.location.job_ref)
        result = worker.reconcile(self.c.job_ref)
        self.assertEqual(result.status, 'unknown_reconcile')
        self.assertEqual(self.jobs.completed, [])
        self.assertEqual(self.jobs.saved['static_build'], self.original)
        self.assertNotIn('public_readback', self.jobs.saved)
        self.client.publish.assert_not_called()

    def test_other_or_unspecified_job_ref_cannot_claim(self):
        worker = ReleaseWorker(self.jobs, None, CONFIG, required_job_ref=self.location.job_ref)
        for ref in (None, 'JOB1234'):
            with self.subTest(ref=ref), self.assertRaises(ValueError): worker.run_once(ref)
        self.assertEqual(self.jobs.claimed, 0)

    def test_factory_rejects_wrong_location_scope_before_store_construction(self):
        loc = replace(self.location, pipeline_key='different')
        with patch('confluence_release.composition.PostgresProjectionStore') as store:
            with self.assertRaises(ValueError):
                create_release_worker(None, config=CONFIG, projection_database_url='unused',
                    project_root=self.guard_root, release_root=self.new_root,
                    here_now_client=self.client, artifact_location=loc)
            store.assert_not_called()

    def test_factory_carries_exact_location_to_worker_and_bridge(self):
        with patch('confluence_release.composition.PostgresProjectionStore'):
            worker = create_release_worker(None, config=CONFIG, projection_database_url='unused',
                project_root=self.guard_root, release_root=self.new_root,
                here_now_client=self.client, artifact_location=self.location)
        self.assertIs(worker.bridge.artifact_location, self.location)
        self.assertEqual(worker.required_job_ref, self.c.job_ref)

    def test_location_preparation_is_read_only_and_leaves_all_saved_steps_unchanged(self):
        self.jobs.saved['here_now'] = dict(version_id='old', uploaded_files=21)
        before = deepcopy(self.jobs.saved)
        d = self.delivery(); d.prepare(allow_build=False)
        self.assertEqual(self.jobs.saved, before)
        self.assertEqual(self.jobs.claimed, 0)
        self.assertEqual(self.calls, [])
        self.client.reconcile.assert_not_called(); self.client.publish.assert_not_called()

    def test_record_loader_is_immutable_and_hash_stable(self):
        loaded = load_artifact_location(self.profile_file)
        self.assertEqual(loaded, self.location)
        self.profile_file.write_text('{}')
        self.assertEqual(loaded.sha256, self.location.sha256)
        with self.assertRaises(AttributeError): loaded.job_ref = 'JOB0000'

    def test_loader_rejects_unknown_missing_duplicate_and_invalid_json(self):
        for text in ('{}', '{"format":"a","format":"a"}', '[' ,
                     json.dumps(dict(asdict(self.location), extra=True))):
            self.profile_file.write_text(text)
            with self.subTest(text=text[:30]), self.assertRaises(ValueError): load_artifact_location(self.profile_file)

    def test_loader_rejects_symlink_permissions_owner_and_size(self):
        alias = self.root/'link.json'; alias.symlink_to(self.profile_file)
        with self.assertRaises(OSError): load_artifact_location(alias)
        self.profile_file.chmod(0o644)
        with self.assertRaises(ValueError): load_artifact_location(self.profile_file)
        self.profile_file.chmod(0o600)
        with patch('confluence_release.artifact_location.os.getuid', return_value=os.getuid()+1):
            with self.assertRaises(ValueError): load_artifact_location(self.profile_file)
        self.profile_file.write_bytes(b'x'*16385)
        with self.assertRaises(ValueError): load_artifact_location(self.profile_file)

    def test_path_identity_and_digest_validation(self):
        for path in ('relative', '/a/../b', '//a/b', '/a//b', '/a/./b', '/a\nb'):
            with self.subTest(path=path), self.assertRaises(ValueError): absolute_path(path)
        for changes in ({'format':'other'}, {'job_id':'bad'}, {'job_ref':'not-job'},
                        {'relocated_output':str(self.old.output)}, {'manifest_sha256':'x'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): replace(self.location, **changes)

    def test_cli_plan_loads_record_without_worker_or_db(self):
        conf = self.root/'release.json'
        conf.write_text(json.dumps(dict(site_base=CONFIG.site_base, nor_base=CONFIG.nor_base,
            here_now_slug=CONFIG.here_now_slug, project_root=str(self.guard_root), release_root=str(self.new_root))))
        args = ['--config', str(conf), '--artifact-location', str(self.profile_file)]
        with patch('confluence_release.cli._worker') as worker:
            self.assertEqual(main(args+['plan', self.c.job_ref]), 0)
            self.assertEqual(main(args+['plan']), 1)
            self.assertEqual(main(args+['run']), 1)
            self.assertEqual(main(args+['retry', self.c.job_ref]), 1)
            self.assertEqual(main(args+['init-projection']), 1)
            worker.assert_not_called()


if __name__ == '__main__': unittest.main()
