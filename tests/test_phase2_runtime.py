from pathlib import Path
import subprocess
import tempfile
import unittest
from confluence_release.runtime_guard import ReleaseRuntimeGuard, StaleReleaseRuntimeError
from confluence_release.release_lock import public_release_lock, PublicReleaseBusyError


class RuntimeTests(unittest.TestCase):
    def test_lock_releases_after_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=Path(tmp)
            with self.assertRaises(RuntimeError):
                with public_release_lock(r):raise RuntimeError('synthetic')
            with public_release_lock(r):pass
    def test_lock_prevents_concurrent_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            with public_release_lock(Path(tmp)):
                with self.assertRaises(PublicReleaseBusyError):
                    with public_release_lock(Path(tmp)):pass
    def test_capture_and_dirty_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def git(*a):return subprocess.run(['git',*a],cwd=root,check=True,capture_output=True)
            git('init');git('config','user.email','test@example.invalid');git('config','user.name','Synthetic test')
            (root/'src/confluence_release').mkdir(parents=True)
            p=root/'src/confluence_release/example.py';p.write_text('pass\n')
            git('add','.');git('commit','-m','synthetic baseline')
            guard=ReleaseRuntimeGuard.capture(root);guard.assert_current()
            p.write_text('changed\n')
            with self.assertRaises(StaleReleaseRuntimeError):guard.assert_current()
            with self.assertRaises(StaleReleaseRuntimeError):ReleaseRuntimeGuard.capture(root)
    def test_commit_change_requires_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def git(*a):return subprocess.run(['git',*a],cwd=root,check=True,capture_output=True)
            git('init');git('config','user.email','test@example.invalid');git('config','user.name','Synthetic test')
            git('commit','--allow-empty','-m','first');g=ReleaseRuntimeGuard.capture(root)
            git('commit','--allow-empty','-m','second')
            with self.assertRaises(StaleReleaseRuntimeError):g.assert_current()

if __name__=='__main__':unittest.main()
