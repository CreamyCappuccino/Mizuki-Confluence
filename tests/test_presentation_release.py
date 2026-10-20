"""Presentation service boundaries with real files/locks/guard and fake provider."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from confluence_release.artifacts import ReleaseBuilder, read_files
from confluence_release.here_now_client import HereNowReceipt
from confluence_release.presentation_artifact import build_candidate
from confluence_release.presentation_release import PresentationRelease, PresentationUnknown
from confluence_release.release_lock import public_release_lock, PublicReleaseBusyError
from phase2_support import CONFIG, article, assets
from release_safety_test_support import repository


class Provider:
    def __init__(self, base):
        self.hashes = dict(base.checksums); self.version = 'base-v1'
        self.published = 0; self.observed = 0; self.fail_after_publish = False
    def site_details(self, slug):
        return dict(currentVersionId=self.version, manifest=[dict(path=p, hash=h) for p,h in self.hashes.items()])
    def publish(self, slug, receipt, *, base_version_id=None):
        if base_version_id != self.version: raise ValueError('stale version')
        self.published += 1; self.hashes = dict(receipt.checksums); self.version = 'new-v2'
        if self.fail_after_publish: raise TimeoutError('synthetic uncertain finalize')
        return HereNowReceipt(slug, self.version, 3, False)
    def reconcile(self, slug, receipt):
        self.observed += 1
        if self.hashes != receipt.checksums: return None
        return HereNowReceipt(slug, self.version, 0, True)


class PresentationReleaseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve(); self.project = self.root/'source'
        self.project.mkdir(); repository(self.project)
        self.commit = subprocess.check_output(['git','-C',str(self.project),'rev-parse','HEAD'], text=True).strip()
        self.releases = self.root/'releases'
        self.base = ReleaseBuilder(source_assets=assets(self.root), config=CONFIG,
                                   source_commit='old-source').build((article(),), self.releases/'base')
        self.candidate = build_candidate(self.base, base_version='base-v1', source_commit=self.commit,
                            source_job='JOB99990001', config=CONFIG,
                            overlay={'assets/styles.css':b'body{color:#123}', 'assets/effect.js':b'/* effects */'},
                            output=self.releases/'candidate')
        self.original = read_files(self.base.output); self.client = Provider(self.base)
        self.reads = []; self.fail_new_readback = False
        self.service = PresentationRelease(config=CONFIG, project_root=self.project,
                            release_root=self.releases, client=self.client, readback=self.readback)
    def readback(self, receipt, config):
        self.reads.append(receipt.output)
        if self.fail_new_readback and receipt.output == self.candidate.artifact.output:
            raise TimeoutError('synthetic readback unavailable')
        return dict(checksums='exact', files=len(receipt.checksums), origins=2)
    def promote(self, **changes):
        kwargs = dict(expected_sha=self.candidate.sha256, confirm=True); kwargs.update(changes)
        return self.service.promote(self.candidate, **kwargs)

    def test_requires_explicit_confirmation_and_candidate_hash(self):
        for changes in ({'confirm':False},{'expected_sha':'0'*64}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.promote(**changes)
        self.assertEqual(self.client.published,0)

    def test_publish_preserves_content_and_records_separate_evidence(self):
        result = self.promote()
        self.assertEqual(result['status'],'verified')
        self.assertEqual(self.client.published,1)
        self.assertEqual(self.reads,[self.base.output,self.candidate.artifact.output])
        self.assertEqual(read_files(self.base.output),self.original)
        directory = self.releases/'.presentation'/self.candidate.sha256
        for path in ('started.json','provider.json','verified.json'):
            self.assertTrue((directory/path).is_file())
            self.assertEqual((directory/path).stat().st_mode&0o777,0o600)

    def test_second_publish_is_not_retried(self):
        self.promote()
        with self.assertRaises(PresentationUnknown): self.promote()
        self.assertEqual(self.client.published,1)

    def test_unknown_finalize_reconciles_without_upload(self):
        self.client.fail_after_publish=True
        with self.assertRaises(PresentationUnknown): self.promote()
        result=self.service.reconcile(self.candidate,expected_sha=self.candidate.sha256)
        self.assertEqual(result['status'],'verified')
        self.assertEqual(self.client.published,1);self.assertEqual(self.client.observed,1)

    def test_failed_readback_never_writes_verified(self):
        self.fail_new_readback=True
        with self.assertRaises(PresentationUnknown): self.promote()
        directory=self.releases/'.presentation'/self.candidate.sha256
        self.assertTrue((directory/'started.json').exists())
        self.assertFalse((directory/'verified.json').exists())
        self.fail_new_readback=False
        self.service.reconcile(self.candidate,expected_sha=self.candidate.sha256)
        self.assertEqual(self.client.published,1)

    def test_stale_version_and_manifest_fail_before_publication(self):
        self.client.version='some-newer-version'
        with self.assertRaises(ValueError):self.promote()
        self.client.version='base-v1';self.client.hashes={}
        with self.assertRaises(ValueError):self.promote()
        self.assertEqual(self.client.published,0)

    def test_shared_lock_blocks_other_release(self):
        with public_release_lock(self.releases),self.assertRaises(PublicReleaseBusyError):self.promote()
        self.assertEqual(self.client.published,0)

    def test_runtime_guard_blocks_stale_source(self):
        (self.project/'tools/build.py').write_text('# modified')
        with self.assertRaises(RuntimeError):self.promote()
        self.assertEqual(self.client.published,0)

    def test_reconcile_requires_existing_attempt(self):
        with self.assertRaises(ValueError):self.service.reconcile(self.candidate,expected_sha=self.candidate.sha256)
        self.assertEqual(self.client.observed,0)

    def test_completed_result_still_verifies_current_delivery(self):
        self.promote();self.client.hashes={}
        with self.assertRaises(PresentationUnknown):self.service.reconcile(self.candidate,expected_sha=self.candidate.sha256)
        self.assertEqual(self.client.published,1)


if __name__=='__main__':unittest.main()
