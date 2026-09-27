"""Bounded GET-only readback transport. No credentials, deployment or retry."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .release_checksums import MAX_ARTIFACT_FILE_BYTES, ReleaseReadbackMismatch, safe_relative_path

USER_AGENT = "confluence-release-worker/1.0"


class ReleaseReadbackUnavailable(RuntimeError):
    """Readback cannot establish an outcome; reconcile, don't infer absence."""


@dataclass(frozen=True)
class ReadbackResponse:
    status: int
    body: bytes


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_base(base: str, *, allow_loopback_http: bool = False) -> str:
    if (not isinstance(base, str) or not base or any(c in base for c in "\\%?#")
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in base)):
        raise ReleaseReadbackMismatch("invalid configured readback base")
    parts = urlsplit(base)
    try:
        _ = parts.port
    except ValueError as exc:
        raise ReleaseReadbackMismatch("invalid configured readback port") from exc
    loopback = allow_loopback_http and parts.hostname in {"127.0.0.1", "::1", "localhost"}
    if (not parts.hostname or parts.username is not None or parts.password is not None
            or parts.scheme not in ({"https", "http"} if loopback else {"https"})):
        raise ReleaseReadbackMismatch("explicit HTTPS readback base required")
    normalized = base.rstrip("/")
    if parts.path.strip("/"):
        safe_relative_path(parts.path.strip("/"))
    if "//" in parts.path or any(p in {".", ".."} for p in parts.path.split("/")):
        raise ReleaseReadbackMismatch("ambiguous readback base path")
    return normalized


def target_url(base: str, relative: str) -> str:
    # Concatenation deliberately preserves the configured base-path prefix.
    return base + "/" + quote(safe_relative_path(relative), safe="/-._~")


def read_url(url: str) -> ReadbackResponse:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
    try:
        with build_opener(_NoRedirect).open(request, timeout=20) as response:  # noqa: S310
            body = response.read(MAX_ARTIFACT_FILE_BYTES + 1)
            if len(body) > MAX_ARTIFACT_FILE_BYTES:
                raise ReleaseReadbackMismatch("remote release file exceeds readback bound")
            return ReadbackResponse(response.status, body)
    except HTTPError as exc:
        status = exc.code
        exc.close()
        if status == 404:
            return ReadbackResponse(404, b"")
        if 300 <= status < 400:
            raise ReleaseReadbackMismatch("redirect is not exact route readback") from exc
        raise ReleaseReadbackUnavailable(f"readback HTTP {status}") from exc
    except (OSError, URLError, TimeoutError) as exc:
        raise ReleaseReadbackUnavailable("readback transport unavailable") from exc
