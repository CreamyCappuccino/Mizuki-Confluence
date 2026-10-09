"""Explicit one-JOB physical relocation of an unchanged private BuildReceipt."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from uuid import UUID

from confluence_pressroom.release_checksums import DIGEST, MANIFEST
from .artifacts import BuildReceipt, verify_local_artifact

FORMAT = 'confluence-artifact-location/v1'
MAX_LOCATION_BYTES = 16_384


def record_digest(record: dict) -> str:
    """Same compact, sorted JSON convention used for the private receipt evidence."""
    return hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def absolute_path(value: str) -> Path:
    if (not isinstance(value, str) or not value or '\\' in value
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError('invalid artifact location path')
    path = Path(value)
    if (not path.is_absolute() or str(path) != value
            or value.startswith('//') or '..' in path.parts):
        raise ValueError('artifact location needs a normalized absolute path')
    return path


def real_directory(path: Path) -> None:
    """Fail closed on every ancestor, not only the final artifact directory."""
    absolute_path(str(path))
    for part in (*reversed(path.parents), path):
        info = part.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError('artifact location must have ordinary directory ancestors')


@dataclass(frozen=True, slots=True)
class ArtifactLocation:
    job_ref: str
    job_id: str
    pipeline_key: str
    original_output: str
    relocated_output: str
    static_build_sha256: str
    manifest_sha256: str
    format: str = FORMAT

    def __post_init__(self):
        if self.format != FORMAT or not isinstance(self.job_ref, str) or not re.fullmatch(r'JOB\d{4,}', self.job_ref):
            raise ValueError('invalid artifact location identity')
        if not isinstance(self.job_id, str) or str(UUID(self.job_id)) != self.job_id:
            raise ValueError('artifact location needs canonical JOB UUID')
        if (not isinstance(self.pipeline_key, str) or not self.pipeline_key
                or len(self.pipeline_key) > 512
                or any(ord(c) < 33 or ord(c) == 127 for c in self.pipeline_key)):
            raise ValueError('invalid artifact location pipeline')
        old, new = absolute_path(self.original_output), absolute_path(self.relocated_output)
        if old == new or old.name != self.job_id or new.name != self.job_id:
            raise ValueError('artifact location must bind one unchanged JOB directory name')
        for value in (self.static_build_sha256, self.manifest_sha256):
            if not isinstance(value, str) or not DIGEST.fullmatch(value):
                raise ValueError('artifact location needs pinned SHA-256 values')

    @property
    def sha256(self) -> str:
        return record_digest(asdict(self))

    def validate_runtime(self, release_root: Path, pipeline_key: str) -> None:
        root = absolute_path(str(release_root))
        if (self.pipeline_key != pipeline_key
                or Path(self.relocated_output) != root / self.job_id):
            raise ValueError('artifact location does not match runtime root/pipeline')
        real_directory(root)

    def validate_job(self, job_ref: str) -> None:
        if job_ref != self.job_ref:
            raise ValueError('artifact location does not authorize this JOB')

    def locate(self, saved: dict, context, release_root: Path) -> BuildReceipt:
        self.validate_runtime(release_root, context.job_pipeline_key)
        self.validate_job(context.job_ref)
        if str(context.job_id) != self.job_id or context.destination_key != 'confluence':
            raise ValueError('artifact location does not match JOB identity/destination')
        if (record_digest(saved) != self.static_build_sha256
                or saved.get('output') != self.original_output):
            raise ValueError('private static_build differs from relocation authorization')
        original = BuildReceipt.from_record(saved)
        if original.checksums.get(MANIFEST) != self.manifest_sha256:
            raise ValueError('relocation manifest differs from private receipt')
        physical = Path(self.relocated_output)
        real_directory(physical)
        located = replace(original, output=physical)
        verify_local_artifact(located)
        return located

    def evidence(self) -> dict:
        return dict(format=self.format, sha256=self.sha256,
            job_ref=self.job_ref, original_output=self.original_output,
            relocated_output=self.relocated_output,
            static_build_sha256=self.static_build_sha256,
            manifest_sha256=self.manifest_sha256)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate artifact location field')
        result[key] = value
    return result


def load_artifact_location(path: Path) -> ArtifactLocation:
    """Read a local operator-owned record once; no DB/network/writes."""
    descriptor = os.open(path.expanduser(), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise ValueError('artifact location must be an owner-owned 0600 file')
        raw = stream.read(MAX_LOCATION_BYTES + 1)
    if len(raw) > MAX_LOCATION_BYTES:
        raise ValueError('artifact location file exceeds size bound')
    values = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object)
    if not isinstance(values, dict) or set(values) != {field.name for field in fields(ArtifactLocation)}:
        raise ValueError('invalid artifact location fields')
    return ArtifactLocation(**values)
