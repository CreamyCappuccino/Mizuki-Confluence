"""Asset-only immutable candidates. Public HTML and editorial data stay byte-exact."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import tempfile
import shutil

from .artifacts import BuildReceipt, read_files, sha256, verify_local_artifact
from .config import ReleaseConfig, digest, json_bytes
from confluence_pressroom.release_checksums import MANIFEST, safe_relative_path


@dataclass(frozen=True)
class PresentationCandidate:
    base: BuildReceipt
    artifact: BuildReceipt
    base_version: str
    source_commit: str
    source_job: str
    site: dict
    assets: tuple[str, ...]

    def as_record(self):
        return dict(format='confluence-presentation/v1', base=self.base.as_record(),
                    artifact=self.artifact.as_record(), base_version=self.base_version,
                    source_commit=self.source_commit, source_job=self.source_job,
                    site=self.site, assets=list(self.assets))

    @property
    def sha256(self):
        return digest(self.as_record())

    @classmethod
    def from_record(cls, value):
        expected = {'format', 'base', 'artifact', 'base_version', 'source_commit', 'source_job', 'site', 'assets'}
        if not isinstance(value, dict) or set(value) != expected or value['format'] != 'confluence-presentation/v1':
            raise ValueError('invalid presentation candidate record')
        return cls(BuildReceipt.from_record(value['base']), BuildReceipt.from_record(value['artifact']),
                   value['base_version'], value['source_commit'], value['source_job'],
                   value['site'], tuple(value['assets']))


def ordinary_path(path: Path) -> Path:
    path = path.expanduser()
    if not path.is_absolute() or '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('presentation paths must be absolute without symlinks')
    return path


def asset_path(path: str) -> str:
    safe_relative_path(path)
    if not path.startswith('assets/') or Path(path).suffix not in {'.css', '.js'}:
        raise ValueError('presentation overlay accepts only assets/*.css or assets/*.js')
    return path


def manifest(files):
    value = json.loads(files['release-manifest.json'])
    if not isinstance(value, dict) or value.get('format') != 'confluence-static-release/v1':
        raise ValueError('invalid base release manifest')
    return value


def build_candidate(base: BuildReceipt, *, base_version: str, source_commit: str,
                    source_job: str, config: ReleaseConfig, overlay: dict[str, bytes],
                    output: Path) -> PresentationCandidate:
    ordinary_path(base.output); verify_local_artifact(base)
    output = ordinary_path(output)
    if output.exists() or output.is_relative_to(base.output) or base.output.is_relative_to(output):
        raise ValueError('candidate output must be new and separate from the base')
    if not overlay or not isinstance(base_version, str) or not base_version:
        raise ValueError('explicit assets and base provider version are required')
    if not re.fullmatch(r'[0-9a-f]{40}', source_commit) or not re.fullmatch(r'JOB\d{4,}', source_job):
        raise ValueError('explicit source commit and canonical source JOB required')
    files = read_files(base.output)
    old_manifest = manifest(files)
    if old_manifest.get('content_digest') != base.content_digest or tuple(old_manifest.get('article_routes', ())) != base.article_routes:
        raise ValueError('base manifest differs from its frozen receipt')
    for path, data in overlay.items():
        asset_path(path)
        if not isinstance(data, bytes) or len(data) > 2_000_000:
            raise ValueError('asset must be bounded bytes')
        data.decode('utf-8')
        files[path] = data
    files['release-manifest.json'] = json_bytes(dict(old_manifest, source_commit=source_commit)) + b'\n'
    files.pop(MANIFEST)
    sums = {p: sha256(data) for p, data in sorted(files.items())}
    files[MANIFEST] = ''.join(f'{h}  {p}\n' for p, h in sums.items()).encode()
    sums[MANIFEST] = sha256(files[MANIFEST])
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='.presentation-', dir=output.parent))
    try:
        for name, raw in files.items():
            dest = tmp / safe_relative_path(name)
            dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            dest.write_bytes(raw); dest.chmod(0o600)
        # The owner release lock serializes creation/promotion; never replace an existing directory.
        if output.exists():
            raise FileExistsError(output)
        tmp.rename(output)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    candidate = PresentationCandidate(base, BuildReceipt(output, base.content_digest, sums, base.article_routes),
                                      base_version, source_commit, source_job, config.public_config,
                                      tuple(sorted(overlay)))
    validate_candidate(candidate, config=config)
    return candidate


def validate_candidate(candidate: PresentationCandidate, *, config: ReleaseConfig) -> None:
    if candidate.site != config.public_config or not candidate.base_version:
        raise ValueError('candidate destination mismatch')
    if not re.fullmatch(r'[0-9a-f]{40}', candidate.source_commit) or not re.fullmatch(r'JOB\d{4,}', candidate.source_job):
        raise ValueError('candidate source identity is invalid')
    if not candidate.assets or len(set(candidate.assets)) != len(candidate.assets):
        raise ValueError('candidate assets are empty or duplicated')
    assets = {asset_path(p) for p in candidate.assets}
    for receipt in (candidate.base, candidate.artifact):
        ordinary_path(receipt.output); verify_local_artifact(receipt)
    if candidate.base.output == candidate.artifact.output:
        raise ValueError('presentation cannot rewrite its base artifact')
    before, after = read_files(candidate.base.output), read_files(candidate.artifact.output)
    if set(after) != set(before) | assets:
        raise ValueError('presentation cannot remove files or add non-asset paths')
    for path in before.keys() - assets - {MANIFEST, 'release-manifest.json'}:
        if before[path] != after[path]:
            raise ValueError('presentation changed protected article or data bytes')
    old, new = manifest(before), manifest(after)
    if new != dict(old, source_commit=candidate.source_commit):
        raise ValueError('presentation changed editorial manifest fields')
    if (candidate.artifact.content_digest != candidate.base.content_digest
            or new.get('content_digest') != candidate.base.content_digest
            or candidate.artifact.article_routes != candidate.base.article_routes
            or tuple(new.get('article_routes', ())) != candidate.base.article_routes):
        raise ValueError('presentation content or routes changed')
