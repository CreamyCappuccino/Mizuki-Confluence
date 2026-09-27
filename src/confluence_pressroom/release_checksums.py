"""AIL checksum readback adapted to Confluence's pinned build-receipt boundary."""
from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path

MANIFEST = "checksums.sha256"
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
ROBOTS = frozenset({"noindex", "nofollow", "noarchive"})
MAX_MANIFEST_BYTES = 2_000_000
MAX_ARTIFACT_FILE_BYTES = 32_000_000


class ReleaseReadbackMismatch(ValueError):
    """Definite mismatch; do not finalize a release on this evidence."""


def safe_relative_path(relative: str) -> str:
    if (not isinstance(relative, str) or not relative
            or any(c in relative for c in "\\%?#")
            or any(ord(c) < 32 or ord(c) == 127 for c in relative)
            or any(p in {"", ".", ".."} for p in relative.split("/"))):
        raise ReleaseReadbackMismatch("invalid release-relative path")
    return relative


def _regular_file(root: Path, relative: str) -> Path:
    safe_relative_path(relative)
    path = root
    for part in relative.split("/"):
        path = path / part
        if path.is_symlink():
            raise ReleaseReadbackMismatch("release artifacts must not contain symlinks")
    if not path.is_file():
        raise ReleaseReadbackMismatch(f"release file missing: {relative}")
    return path


def checksum_entries(root: Path, *, expected_manifest_sha256: str) -> dict[str, str]:
    """The digest comes from the build receipt, not the directory being checked."""
    if not isinstance(expected_manifest_sha256, str) or not DIGEST.fullmatch(expected_manifest_sha256):
        raise ReleaseReadbackMismatch("a pinned manifest SHA-256 is required")
    path = _regular_file(root, MANIFEST)
    with path.open("rb") as stream:
        raw = stream.read(MAX_MANIFEST_BYTES + 1)
    if (len(raw) > MAX_MANIFEST_BYTES
            or hashlib.sha256(raw).hexdigest() != expected_manifest_sha256):
        raise ReleaseReadbackMismatch("release manifest hash/size mismatch")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise ReleaseReadbackMismatch("release manifest is not UTF-8") from exc
    entries = {}
    for line in lines:
        digest, separator, relative = line.partition("  ")
        if separator != "  " or not DIGEST.fullmatch(digest):
            raise ReleaseReadbackMismatch("invalid checksums.sha256")
        safe_relative_path(relative)
        if relative == MANIFEST or relative in entries:
            raise ReleaseReadbackMismatch("duplicate/self-referential checksum entry")
        entries[relative] = digest
    if not entries:
        raise ReleaseReadbackMismatch("checksums.sha256 is empty")
    return entries


class _RobotsHints(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_head = False
        self.hints: list[set[str]] = []

    def handle_starttag(self, tag, attrs):
        if tag == "head":
            self.in_head = True
        if tag == "meta" and self.in_head:
            values = dict(attrs)
            if (values.get("name") or "").lower() == "robots":
                self.hints.append(set(re.split(r"[\s,]+", (values.get("content") or "").lower())))

    def handle_endtag(self, tag):
        if tag == "head":
            self.in_head = False


def _check_discovery(relative: str, content: bytes) -> None:
    name = relative.rsplit("/", 1)[-1].lower()
    if name.startswith("sitemap"):
        raise ReleaseReadbackMismatch("sitemap must not be generated")
    if name.endswith((".html", ".htm")):
        try:
            parser = _RobotsHints()
            parser.feed(content.decode("utf-8"))
            parser.close()
        except (UnicodeError, ValueError) as exc:
            raise ReleaseReadbackMismatch("invalid HTML discovery metadata") from exc
        if (not parser.hints or any(not ROBOTS <= hints for hints in parser.hints)
                or any({"all", "index", "follow", "archive"} & hints for hints in parser.hints)):
            raise ReleaseReadbackMismatch(f"missing/conflicting noindex policy: {relative}")
    if name == "robots.txt":
        try:
            lines = content.decode("utf-8").splitlines()
        except UnicodeError as exc:
            raise ReleaseReadbackMismatch("invalid robots text") from exc
        if any(line.strip().lower().startswith("sitemap:") for line in lines):
            raise ReleaseReadbackMismatch("robots must not advertise a sitemap")


def verify_local_artifact(root: Path, *, expected_manifest_sha256: str) -> dict[str, str]:
    """Verify exact files and local discovery policy before any remote reads."""
    root = root.expanduser()
    if root.is_symlink():
        raise ReleaseReadbackMismatch("artifact root must not be a symlink")
    expected = checksum_entries(root, expected_manifest_sha256=expected_manifest_sha256)
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ReleaseReadbackMismatch("release artifacts must not contain symlinks")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    if actual != set(expected) | {MANIFEST}:
        raise ReleaseReadbackMismatch("release file set differs from manifest")
    for relative, digest in expected.items():
        path = _regular_file(root, relative)
        with path.open("rb") as stream:
            raw = stream.read(MAX_ARTIFACT_FILE_BYTES + 1)
        if len(raw) > MAX_ARTIFACT_FILE_BYTES or hashlib.sha256(raw).hexdigest() != digest:
            raise ReleaseReadbackMismatch(f"local release checksum mismatch: {relative}")
        _check_discovery(relative, raw)
    return expected
