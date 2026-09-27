"""Real flock/git tests and explicit worker-stage doubles; not APR/JOB proof."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from release_safety_test_support import ROOT, git, repository
from confluence_pressroom.public_release_lock import PublicReleaseBusyError, public_release_lock
from confluence_pressroom.release_runtime_guard import ReleaseRuntimeGuard, StaleReleaseRuntimeError
from confluence_pressroom.release_execution import run_guarded_release


class ReleaseSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'project'
        self.project.mkdir()
        repository(self.project)
        self.guard = ReleaseRuntimeGuard.capture(self.project)
        self.release = self.root / 'release'
        self.events = []

    def execute(self, failure=None, dirty_after=None):
        def step(name, result):
            def call(*args):
                self.events.append(name)
                if dirty_after == name:
                    (self.project / 'src/confluence_pressroom/worker.py').write_text('# changed')
                if failure == name:
                    raise RuntimeError('synthetic ' + name)
                return result
            return call
        return run_guarded_release(
            guard=self.guard, release_root=self.release,
            claim=step('claim', 'job'), build=step('build', 'artifact'),
            deliver=step('deliver', 'receipt'), readback=step('readback', 'evidence'),
            finalize=step('finalize', 'done'),
        )

    def test_original_lock_structure_releases_on_exception(self):
        with self.assertRaisesRegex(RuntimeError, 'synthetic'):
            with public_release_lock(self.release):
                raise RuntimeError('synthetic')
        with public_release_lock(self.release):
            self.assertTrue((self.release / '.public-release.lock').exists())

    def test_other_process_cannot_claim_under_same_site_lock(self):
        code = '''import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from confluence_pressroom.public_release_lock import public_release_lock, PublicReleaseBusyError
try:
    with public_release_lock(Path(sys.argv[2])): pass
except PublicReleaseBusyError:
    sys.exit(23)
'''
        with public_release_lock(self.release):
            result = subprocess.run([sys.executable, '-c', code, str(ROOT / 'src'), str(self.release)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 23, result.stderr)
        result = subprocess.run([sys.executable, '-c', code, str(ROOT / 'src'), str(self.release)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_different_sites_do_not_block_each_other(self):
        with public_release_lock(self.release), public_release_lock(self.root / 'other'):
            pass

    def test_busy_worker_never_claims(self):
        with public_release_lock(self.release):
            with self.assertRaises(PublicReleaseBusyError):
                self.execute()
        self.assertEqual(self.events, [])

    def test_clean_runtime_and_ordered_success(self):
        self.assertEqual(self.execute(), 'done')
        self.assertEqual(self.events, ['claim', 'build', 'deliver', 'readback', 'finalize'])

    def test_finalization_is_inside_lock(self):
        def finalize(*args):
            with self.assertRaises(PublicReleaseBusyError):
                with public_release_lock(self.release):
                    pass
            return 'done'
        result = run_guarded_release(guard=self.guard, release_root=self.release,
                                     claim=lambda: 1, build=lambda _: 2,
                                     deliver=lambda *_: 3, readback=lambda *_: 4,
                                     finalize=finalize)
        self.assertEqual(result, 'done')

    def test_idle_worker_has_no_side_effect_stages(self):
        def unexpected(*args):
            self.fail('stage called with no claimed job')
        self.assertIsNone(run_guarded_release(
            guard=self.guard, release_root=self.release, claim=lambda: None,
            build=unexpected, deliver=unexpected, readback=unexpected, finalize=unexpected))

    def test_failure_never_automatically_retries_or_finalizes(self):
        stages = ['claim', 'build', 'deliver', 'readback', 'finalize']
        for index, failed in enumerate(stages):
            with self.subTest(stage=failed):
                self.events.clear()
                with self.assertRaisesRegex(RuntimeError, 'synthetic ' + failed):
                    self.execute(failure=failed)
                self.assertEqual(self.events, stages[:index + 1])
                with public_release_lock(self.release):
                    pass

    def test_dirty_startup_is_rejected_for_each_runtime_input(self):
        for name in ['src/confluence_pressroom/worker.py', 'prototype/index.html',
                     'tools/build.py', 'pyproject.toml', 'uv.lock']:
            with self.subTest(name=name):
                (self.project / name).write_text('# dirty')
                with self.assertRaises(StaleReleaseRuntimeError):
                    ReleaseRuntimeGuard.capture(self.project)
                git(self.project, 'restore', name)

    def test_staged_and_untracked_runtime_changes_are_rejected(self):
        name = 'src/confluence_pressroom/worker.py'
        (self.project / name).write_text('# staged')
        git(self.project, 'add', name)
        with self.assertRaises(StaleReleaseRuntimeError):
            self.guard.assert_current()
        git(self.project, 'restore', '--staged', name)
        git(self.project, 'restore', name)
        extra = self.project / 'tools/new_runtime.py'
        extra.write_text('# new')
        with self.assertRaises(StaleReleaseRuntimeError):
            self.guard.assert_current()

    def test_uncommitted_docs_are_outside_runtime_inputs(self):
        (self.project / 'docs/readme.md').write_text('editorial notes')
        self.guard.assert_current()

    def test_new_head_requires_restart_even_for_docs_commit(self):
        (self.project / 'docs/readme.md').write_text('editorial notes')
        git(self.project, 'add', '.')
        git(self.project, 'commit', '-qm', 'docs changed')
        with self.assertRaises(StaleReleaseRuntimeError):
            self.guard.assert_current()

    def test_stale_runtime_never_claims(self):
        (self.project / 'tools/build.py').write_text('# changed')
        with self.assertRaises(StaleReleaseRuntimeError):
            self.execute()
        self.assertEqual(self.events, [])

    def test_code_change_after_build_stops_before_deliver(self):
        with self.assertRaises(StaleReleaseRuntimeError):
            self.execute(dirty_after='build')
        self.assertEqual(self.events, ['claim', 'build'])

    def test_code_change_after_delivery_does_not_finalize(self):
        with self.assertRaises(StaleReleaseRuntimeError):
            self.execute(dirty_after='deliver')
        self.assertEqual(self.events, ['claim', 'build', 'deliver'])

    def test_non_git_checkout_fails_closed(self):
        empty = self.root / 'not-git'
        empty.mkdir()
        with self.assertRaises(subprocess.CalledProcessError):
            ReleaseRuntimeGuard.capture(empty)


if __name__ == '__main__':
    unittest.main()
