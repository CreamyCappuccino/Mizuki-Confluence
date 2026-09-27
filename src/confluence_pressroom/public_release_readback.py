"""Confluence adaptation of AIL bd69012 public release readback; see docs."""
from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Literal

from .release_checksums import (
    MANIFEST, ReleaseReadbackMismatch, checksum_entries, safe_relative_path, verify_local_artifact,
)
from .release_http import ReadbackResponse, read_url, target_url, validate_base

MAX_READBACK_WORKERS = 6
UNKNOWN_ROUTE = "__pressroom-release-worker-not-found__"


def verify_public_artifact(
    artifact: Path,
    *,
    here_now_base: str,
    nol_base: str,
    expected_manifest_sha256: str,
    removed_paths: tuple[str, ...] = (),
    here_now_robots: Literal["exact", "host-owned-open"] = "exact",
    allow_loopback_http: bool = False,
    fetch: Callable[[str], ReadbackResponse] = read_url,
) -> dict[str, object]:
    """GET-only verification; bases and manifest pin come from the frozen release.

    Keep AIL's `nol_base` parameter name for the Nor routing seam. This does not
    import AIL, register a destination or provide publication authorization.
    """
    if here_now_robots not in {"exact", "host-owned-open"}:
        raise ReleaseReadbackMismatch("unknown host robots policy")
    bases = tuple(validate_base(base, allow_loopback_http=allow_loopback_http)
                  for base in (here_now_base, nol_base))
    if bases[0] == bases[1]:
        raise ReleaseReadbackMismatch("two distinct configured delivery bases required")
    expected = verify_local_artifact(artifact, expected_manifest_sha256=expected_manifest_sha256)
    removed = tuple(safe_relative_path(path) for path in removed_paths)
    if set(removed) & (set(expected) | {MANIFEST}) or UNKNOWN_ROUTE in expected:
        raise ReleaseReadbackMismatch("present and removed/reserved paths overlap")
    reads = [(target_url(base, relative), digest)
             for i, base in enumerate(bases) for relative, digest in expected.items()
             if not (i == 0 and relative == "robots.txt" and here_now_robots == "host-owned-open")]
    reads.extend((target_url(base, MANIFEST), expected_manifest_sha256) for base in bases)
    with ThreadPoolExecutor(max_workers=min(MAX_READBACK_WORKERS, max(1, len(reads))),
                            thread_name_prefix="confluence-readback") as executor:
        futures = [executor.submit(_require_checksum, fetch, url, digest) for url, digest in reads]
        for future in futures:
            future.result()
    if here_now_robots == "host-owned-open":
        _require_open_robots(fetch, target_url(bases[0], "robots.txt"))
    for base in bases:
        _require_not_found(fetch, target_url(base, UNKNOWN_ROUTE))
        _require_not_found(fetch, target_url(base, "sitemap.xml"))
        for relative in removed:
            _require_not_found(fetch, target_url(base, relative))
    return {"files": len(expected), "origins": 2, "checksums": "exact", "unknown": 404,
            "removed": len(removed), "reserved": int(here_now_robots == "host-owned-open"),
            "external_discovery": "discouraged", "manifest_sha256": expected_manifest_sha256}


def _require_checksum(fetch, url: str, expected: str) -> None:
    response = fetch(url)
    if response.status != 200 or hashlib.sha256(response.body).hexdigest() != expected:
        raise ReleaseReadbackMismatch("remote release status/checksum mismatch")


def _require_not_found(fetch, url: str) -> None:
    if fetch(url).status != 404:
        raise ReleaseReadbackMismatch("removed/unknown route did not return 404")


def _require_open_robots(fetch, url: str) -> None:
    response = fetch(url)
    if response.status != 200:
        raise ReleaseReadbackMismatch("host-owned robots is unavailable")
    try:
        lines = {" ".join(line.strip().lower().split()) for line in response.body.decode("utf-8").splitlines()}
    except UnicodeError as exc:
        raise ReleaseReadbackMismatch("host-owned robots is not UTF-8") from exc
    if not {"user-agent: *", "allow: /"} <= lines:
        raise ReleaseReadbackMismatch("host-owned robots differs from the AIL compatibility policy")


__all__ = ["checksum_entries", "verify_local_artifact", "verify_public_artifact"]
