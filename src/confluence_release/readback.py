"""Bridge the JOB's frozen BuildReceipt to the shared safety verifier.

Normal runtime uses bounded no-redirect GETs. The optional opener/fetch seams
are explicit test transports; neither reads credentials nor deploys anything.
"""
from __future__ import annotations
from urllib.error import HTTPError, URLError
from urllib.request import Request

from confluence_pressroom.here_now_html import HereNowHtmlPolicy
from confluence_pressroom.public_release_readback import (
    verify_public_artifact as verify_safety_artifact,
)
from confluence_pressroom.release_checksums import (
    MANIFEST, MAX_ARTIFACT_FILE_BYTES, ReleaseReadbackMismatch,
)
from confluence_pressroom.release_http import (
    ReadbackResponse, ReleaseReadbackUnavailable, read_url,
)

from .artifacts import BuildReceipt, verify_local_artifact
from .config import ReleaseConfig


class ReadbackUnknown(RuntimeError):
    """Delivery may be active; keep the existing JOB's reconciliation path."""


def _fetch_with_opener(opener, url: str) -> ReadbackResponse:
    """Adapt injected urllib-shaped transports, including the isolated PG probe."""
    request = Request(url, headers={'User-Agent': 'confluence-release-worker/1.0',
                                    'Accept-Encoding': 'identity'})
    try:
        with opener(request, timeout=20) as response:
            final_url = response.geturl() if hasattr(response, 'geturl') else None
            if final_url is not None and final_url != url:
                raise ReleaseReadbackMismatch('redirect is not exact route readback')
            body = response.read(MAX_ARTIFACT_FILE_BYTES + 1)
            if len(body) > MAX_ARTIFACT_FILE_BYTES:
                raise ReleaseReadbackMismatch('remote release file exceeds readback bound')
            return ReadbackResponse(response.status, body)
    except HTTPError as exc:
        status = exc.code
        exc.close()
        if status == 404:
            return ReadbackResponse(404, b'')
        if 300 <= status < 400:
            raise ReleaseReadbackMismatch('redirect is not exact route readback') from exc
        raise ReleaseReadbackUnavailable('readback HTTP unavailable') from exc
    except (OSError, URLError, TimeoutError) as exc:
        raise ReleaseReadbackUnavailable('readback transport unavailable') from exc


def verify_public_artifact(receipt: BuildReceipt, config: ReleaseConfig, *,
                           removed_paths: tuple[str, ...] = (), opener=None,
                           fetch=None, allow_loopback_http: bool = False,
                           html_policy: HereNowHtmlPolicy | None = None) -> dict[str, object]:
    # Retain Phase 2A's complete receipt inventory check as well as the safety
    # verifier's manifest/discovery checks. No rebuilt hashes or default host exception.
    verify_local_artifact(receipt)
    if opener is not None and fetch is not None:
        raise ValueError('choose one explicit readback transport')
    transport = read_url
    if fetch is not None:
        transport = fetch
    elif opener is not None:
        transport = lambda url: _fetch_with_opener(opener, url)
    try:
        result = verify_safety_artifact(receipt.output,
            here_now_base=config.here_now_base, nol_base=config.nor_base,
            expected_manifest_sha256=receipt.checksums[MANIFEST],
            removed_paths=removed_paths, allow_loopback_http=allow_loopback_http,
            fetch=transport, html_policy=html_policy)
    except (ReleaseReadbackMismatch, ReleaseReadbackUnavailable) as exc:
        # A definite mismatch still cannot complete a possibly activated release.
        # Preserve the existing adapter/workflow handling, not a new retry engine.
        raise ReadbackUnknown('declared readback not established; reconcile without republishing') from exc
    return dict(result, files=len(receipt.checksums))
