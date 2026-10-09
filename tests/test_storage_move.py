"""Filesystem migration on temporary Git roots, no local operator machine."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from confluence_release.storage_move import (
    archive_source, copy_storage, inventory, migration_lock, plan_copy,
)


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


class StorageMoveTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.old = self.root/'old'; self.old.mkdir(mode=0o700)
        self.project = self.root/'existing-project'; self.project.mkdir()
        git(self.project, 'init', '-q')
        (self.project/'.gitignore').write_text('/runtime/\n/releases/\n/evidence/\n/checkpoints/\n')
        (self.project/'README.md').write_text('existing developer project, not overwritten')
        for name, data in {'source/src/code.py': b'# old source\n',
                           'releases/job/body.html': b'original',
                           'releases/.public-release.lock': b'',
                           'acceptance-before/raw.html': b'raw before',
                           'acceptance-recovery/raw/index.html': b'raw after',
                           'checkpoints/auth/catalog.txt': b'private checkpoint'}.items():
            p = self.old/name; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data); p.chmod(0o600)
        self.receipt = self.project/'checkpoints/path-migration/copy.json'
        self.before = inventory(self.old)

    def copy(self):
        plan = plan_copy(self.old, self.project)
        return copy_storage(self.old, self.project, expected_fingerprint=plan['fingerprint'],
                            receipt_path=self.receipt)

    def test_plan_is_read_only_and_fingerprint_stable(self):
        before = inventory(self.project)
        a = plan_copy(self.old, self.project); b = plan_copy(self.old, self.project)
        self.assertEqual(a, b); self.assertEqual(inventory(self.project), before)
        self.assertEqual([m['target'] for m in a['moves']],
            ['evidence/acceptance-before', 'evidence/acceptance-recovery', 'checkpoints', 'releases', 'runtime/source'])

    def test_copy_preserves_files_modes_source_and_existing_project(self):
        result = self.copy()
        self.assertEqual(result['status'], 'COPIED_NOT_ACTIVATED')
        self.assertEqual(inventory(self.old), self.before)
        self.assertEqual((self.project/'README.md').read_text(), 'existing developer project, not overwritten')
        for move in result['moves']:
            target = self.project/move['target']
            self.assertEqual(target.stat().st_mode & 0o777, 0o700)
            for rel, entry in move['inventory'].items():
                if entry['type'] == 'file':
                    self.assertEqual((target/rel).read_bytes(), (Path(move['source'])/rel).read_bytes())
                    self.assertEqual((target/rel).stat().st_mode & 0o777, entry['mode'])
        self.assertEqual(self.receipt.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(self.receipt.read_text())['fingerprint'], result['fingerprint'])

    def test_copy_cannot_be_repeated_or_overwrite(self):
        self.copy()
        with self.assertRaises(ValueError): self.copy()
        self.assertEqual(inventory(self.old), self.before)

    def test_stale_plan_and_wrong_fingerprint_rejected_before_data_copy(self):
        plan = plan_copy(self.old, self.project)
        (self.old/'acceptance-before/raw.html').write_bytes(b'changed')
        for pin in (plan['fingerprint'], '0'*64):
            with self.assertRaises(ValueError):
                copy_storage(self.old, self.project, expected_fingerprint=pin, receipt_path=self.receipt)
        self.assertFalse((self.project/'evidence').exists())

    def test_old_links_special_entries_and_unknown_top_level_rejected(self):
        link = self.old/'acceptance-before/link'; link.symlink_to(self.old/'source/src/code.py')
        with self.assertRaises(ValueError): plan_copy(self.old, self.project)
        link.unlink(); extra = self.old/'unexpected'; extra.mkdir()
        with self.assertRaises(ValueError): plan_copy(self.old, self.project)

    def test_unknown_owner_rejected(self):
        with patch('confluence_release.storage_move.os.getuid', return_value=os.getuid()+1):
            with self.assertRaises(ValueError): plan_copy(self.old, self.project)

    def test_project_must_exist_and_be_git_root_without_overlap(self):
        with self.assertRaises((ValueError, FileNotFoundError)):
            plan_copy(self.old, self.root/'missing-project')
        with self.assertRaises(ValueError): plan_copy(self.project, self.project)
        nested = self.project/'nested'; nested.mkdir()
        with self.assertRaises(ValueError): plan_copy(self.old, nested)

    def test_ignore_requirement_is_not_waived(self):
        (self.project/'.gitignore').write_text('')
        with self.assertRaises(subprocess.CalledProcessError): plan_copy(self.old, self.project)

    def test_tracked_private_destination_rejected_even_when_ignore_exists(self):
        target = self.project/'evidence/acceptance-before/tracked.txt'; target.parent.mkdir(parents=True); target.write_text('bad')
        git(self.project, 'add', '-f', 'evidence/acceptance-before/tracked.txt')
        with self.assertRaises(ValueError): plan_copy(self.old, self.project)

    def test_symlink_project_or_existing_parent_rejected(self):
        alias = self.root/'alias'; alias.symlink_to(self.project, target_is_directory=True)
        with self.assertRaises(ValueError): plan_copy(self.old, alias)
        outsider = self.root/'outsider'; outsider.mkdir()
        (self.project/'evidence').symlink_to(outsider, target_is_directory=True)
        with self.assertRaises(ValueError): self.copy()
        self.assertEqual(list(outsider.iterdir()), [])

    def test_changed_source_during_copy_retains_originals_and_no_completed_receipt(self):
        from confluence_release import storage_move
        original = storage_move._copy_file
        def mutate(src, target, mode):
            original(src, target, mode)
            src.write_bytes(src.read_bytes()+b'concurrent change')
        with patch.object(storage_move, '_copy_file', side_effect=mutate):
            with self.assertRaises(ValueError): self.copy()
        self.assertTrue(self.old.exists()); self.assertFalse(self.receipt.exists())
        self.assertFalse(any('copying-' in p.name for p in self.project.rglob('*')))

    def test_mutual_exclusion_blocks_second_operator(self):
        with migration_lock(self.project):
            with self.assertRaises(BlockingIOError): self.copy()
        self.assertEqual(inventory(self.old), self.before)

    def test_archive_moves_old_root_under_project_without_deleting_bytes(self):
        plan = self.copy()
        archive = self.project/'checkpoints/path-migration/legacy-root'
        archive_source(plan, archive=archive)
        self.assertFalse(self.old.exists())
        self.assertEqual(inventory(archive), self.before)
        self.assertTrue((self.project/'releases/job/body.html').is_file())

    def test_archive_refuses_changed_old_or_destination(self):
        plan = self.copy(); archive = self.project/'checkpoints/path-migration/legacy-root'
        file = self.project/'releases/job/body.html'; original = file.read_bytes()
        file.write_bytes(b'tampered copy')
        with self.assertRaises(ValueError): archive_source(plan, archive=archive)
        file.write_bytes(original)
        (self.old/'source/src/code.py').write_bytes(b'changed source')
        with self.assertRaises(ValueError): archive_source(plan, archive=archive)
        self.assertTrue(self.old.exists()); self.assertFalse(archive.exists())

    def test_archive_refuses_overwrite_outside_path_and_symlink(self):
        plan = self.copy()
        for archive in (self.root/'other', self.project/'runtime/archive', self.project/'checkpoints/path-migration'):
            with self.subTest(path=archive), self.assertRaises(ValueError): archive_source(plan, archive=archive)
        archive = self.project/'checkpoints/path-migration/legacy-root'; archive.mkdir()
        with self.assertRaises(ValueError): archive_source(plan, archive=archive)
        self.assertTrue(self.old.exists())

    def test_updated_runtime_source_requires_explicit_clean_commit(self):
        plan = self.copy(); target = self.project/'runtime/source'
        git(target, 'init', '-q'); git(target, 'config', 'user.name', 'Synthetic')
        git(target, 'config', 'user.email', 'synthetic@example.invalid')
        (target/'src/code.py').write_text('# reviewed new code')
        git(target, 'add', '.'); git(target, 'commit', '-qm', 'reviewed code')
        sha = git(target, 'rev-parse', 'HEAD')
        archive = self.project/'checkpoints/path-migration/legacy-root'
        with self.assertRaises(ValueError): archive_source(plan, archive=archive)
        with self.assertRaises(ValueError): archive_source(plan, archive=archive, executing_source_sha='0'*40)
        archive_source(plan, archive=archive, executing_source_sha=sha)
        self.assertFalse(self.old.exists()); self.assertEqual(inventory(archive), self.before)

    def test_dirty_runtime_source_not_archived(self):
        plan = self.copy(); target = self.project/'runtime/source'
        git(target, 'init', '-q'); git(target, 'config', 'user.name', 'Synthetic')
        git(target, 'config', 'user.email', 'synthetic@example.invalid')
        git(target, 'add', '.'); git(target, 'commit', '-qm', 'candidate')
        sha = git(target, 'rev-parse', 'HEAD'); (target/'src/code.py').write_text('dirty')
        with self.assertRaises(ValueError):
            archive_source(plan, archive=self.project/'checkpoints/path-migration/legacy-root', executing_source_sha=sha)
        self.assertTrue(self.old.exists())


if __name__ == '__main__': unittest.main()
