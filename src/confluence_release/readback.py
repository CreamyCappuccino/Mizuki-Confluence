"""Adapted AIL exact HTTP readback, with named origins instead of Nol defaults."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .artifacts import BuildReceipt, safe_relative, sha256, verify_local_artifact
from .config import ReleaseConfig


class ReadbackUnknown(RuntimeError):
    """Delivery may already be active; observe again without repeating upload."""


def verify_public_artifact(receipt: BuildReceipt, config: ReleaseConfig, *,
                           removed_paths: tuple[str, ...] = (), opener=urlopen) -> dict[str, object]:
    verify_local_artifact(receipt)
    bases = (config.here_now_base, config.nor_base)
    try:
        # Same bounded parallel readback as current AIL (bd69012), without
        # its AIL-only open robots requirement or deployment defaults.
        reads = [(f'{base}/{safe_relative(path)}', h)
                 for base in bases for path, h in receipt.checksums.items()]
        def check(item):
            url, expected = item
            request = Request(url, headers={'User-Agent': 'confluence-release-worker/1.0'})
            with opener(request, timeout=20) as response:
                if response.status != 200 or sha256(response.read()) != expected:
                    raise ReadbackUnknown('delivered artifact does not match the frozen bytes')
        with ThreadPoolExecutor(max_workers=min(6, max(1, len(reads)))) as pool:
            for result in pool.map(check, reads):
                pass
        for base in bases:
            for relative in tuple(removed_paths) + ('__confluence-release-not-found__',):
                request = Request(f'{base}/{safe_relative(relative)}',
                                  headers={'User-Agent': 'confluence-release-worker/1.0'})
                try:
                    with opener(request, timeout=20):
                        raise ReadbackUnknown('withdrawn/unknown route is still readable')
                except HTTPError as exc:
                    if exc.code != 404:
                        raise ReadbackUnknown('absence readback is not a verified 404') from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ReadbackUnknown('HTTP readback unavailable; reconcile without republishing') from exc
    return dict(files=len(receipt.checksums), origins=len(bases), checksums='exact',
                removed=len(removed_paths))
