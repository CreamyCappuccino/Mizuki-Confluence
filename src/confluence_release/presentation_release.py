"""Owner-invoked asset refresh; no manuscript, approval or historical JOB mutation."""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path

from .config import ReleaseConfig
from .here_now_client import manifest_hashes, required_text
from .presentation_artifact import PresentationCandidate, ordinary_path, validate_candidate
from .readback import verify_public_artifact
from .release_lock import public_release_lock
from .runtime_guard import ReleaseRuntimeGuard


class PresentationUnknown(RuntimeError):
    """An attempted refresh must be observed, not blindly published again."""


class PresentationRelease:
    def __init__(self, *, config: ReleaseConfig, project_root: Path, release_root: Path,
                 client, readback=verify_public_artifact):
        self.config, self.client, self.readback = config, client, readback
        self.root = ordinary_path(release_root)
        self.guard = ReleaseRuntimeGuard.capture(project_root)

    def _validate(self, candidate, expected_sha):
        if candidate.sha256 != expected_sha:
            raise ValueError('presentation candidate differs from the reviewed SHA')
        validate_candidate(candidate, config=self.config)
        self.guard.assert_current()
        if candidate.source_commit != self.guard.source_commit:
            raise ValueError('candidate was built for a different executing source')
        if (not candidate.base.output.is_relative_to(self.root)
                or not candidate.artifact.output.is_relative_to(self.root)):
            raise ValueError('presentation artifacts must be under the configured release root')

    def _directory(self, candidate):
        return ordinary_path(self.root / '.presentation' / candidate.sha256)

    @staticmethod
    def _save_new(path, value):
        # Write each stage once; failed attempts keep their original evidence.
        ordinary_path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.open('x', encoding='utf-8') as stream:
            path.chmod(0o600)
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write('\n')

    def _matching_remote(self, receipt, version=None):
        current = self.client.site_details(self.config.here_now_slug)
        if version is not None and required_text(current, 'currentVersionId') != version:
            raise ValueError('the active provider version changed')
        if manifest_hashes(current) != receipt.checksums:
            raise ValueError('the active provider manifest changed')
        return required_text(current, 'currentVersionId')

    def _verify(self, candidate, provider):
        version = provider.version_id
        self._matching_remote(candidate.artifact, version)
        evidence = self.readback(candidate.artifact, self.config)
        if evidence.get('checksums') != 'exact':
            raise ValueError('asset refresh requires normal raw-exact readback')
        self._matching_remote(candidate.artifact, version)
        self._validate(candidate, candidate.sha256)
        return dict(format='confluence-presentation-result/v1', status='verified',
                    candidate_sha256=candidate.sha256, source_job=candidate.source_job,
                    provider=asdict(provider), readback=evidence,
                    content_digest=candidate.artifact.content_digest,
                    verified_at=datetime.now(timezone.utc).isoformat())

    def promote(self, candidate: PresentationCandidate, *, expected_sha: str,
                confirm: bool = False) -> dict:
        if confirm is not True:
            raise ValueError('explicit presentation publication confirmation required')
        with public_release_lock(self.root):
            self._validate(candidate, expected_sha)
            directory = self._directory(candidate)
            if directory.exists():
                raise PresentationUnknown('presentation attempt already exists; reconcile it')
            self._matching_remote(candidate.base, candidate.base_version)
            base_evidence = self.readback(candidate.base, self.config)
            if base_evidence.get('checksums') != 'exact':
                raise ValueError('base is not a verified raw-exact deployment')
            self._matching_remote(candidate.base, candidate.base_version)
            self._validate(candidate, expected_sha)
            self._save_new(directory / 'started.json', dict(candidate=candidate.as_record(),
                           candidate_sha256=expected_sha, base_readback=base_evidence,
                           started_at=datetime.now(timezone.utc).isoformat()))
            try:
                provider = self.client.publish(self.config.here_now_slug, candidate.artifact,
                                               base_version_id=candidate.base_version)
                self._save_new(directory / 'provider.json', asdict(provider))
                result = self._verify(candidate, provider)
                self._save_new(directory / 'verified.json', result)
                return result
            except Exception as exc:
                # The durable started record remains even if publication status is unknown.
                raise PresentationUnknown('presentation outcome unverified; reconcile same candidate') from exc

    def reconcile(self, candidate: PresentationCandidate, *, expected_sha: str) -> dict:
        """Only observes existing publication; it never uploads or rewrites a JOB."""
        with public_release_lock(self.root):
            self._validate(candidate, expected_sha)
            directory = self._directory(candidate)
            started = directory / 'started.json'
            ordinary_path(started)
            if not started.is_file():
                raise ValueError('no recorded presentation attempt to reconcile')
            prior = json.loads(started.read_text(encoding='utf-8'))
            if prior.get('candidate_sha256') != expected_sha or prior.get('candidate') != candidate.as_record():
                raise ValueError('recorded candidate identity differs')
            provider = self.client.reconcile(self.config.here_now_slug, candidate.artifact)
            if provider is None:
                raise PresentationUnknown('candidate is not the active manifest; no retry was made')
            result = self._verify(candidate, provider)
            destination = directory / 'verified.json'
            if not destination.exists():
                self._save_new(destination, result)
            return result
