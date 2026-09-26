"""Immutable, local-only destination configuration, distinct from article intent."""
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
import hashlib
import json
import re
from .html_policy import POLICY_VERSION, LIBXML_VERSION


class ConfluenceError(ValueError):
    """Bounded diagnostics. Never include manuscript content or secrets."""


def canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError) as exc:
        raise ConfluenceError("value is not canonical JSON") from exc


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


SITE_POLICY = {
    "external_discovery": "discouraged",
    "robots": "noindex, nofollow, noarchive",
    "generate_sitemap": False,
}
PRESSROOM_COMMIT = "b5ce8d9422f0b90377145471bcb96f870e3e9263"


@dataclass(frozen=True)
class RehearsalConfig:
    """No network delivery endpoint, DB URL, or default output directory."""
    root: Path
    site_base_url: str = "https://confluence.invalid"
    pipeline_key: str = "confluence-staging-v1"
    timezone: str = "Asia/Taipei"
    external_discovery: str = "discouraged"
    robots: str = "noindex, nofollow, noarchive"
    generate_sitemap: bool = False

    def __post_init__(self):
        base = urlsplit(self.site_base_url)
        if (base.scheme != "https" or base.netloc != "confluence.invalid"
                or base.path not in ("", "/") or base.query or base.fragment):
            raise ConfluenceError("rehearsal requires the non-deployment .invalid origin")
        if self.pipeline_key != "confluence-staging-v1" or self.timezone != "Asia/Taipei":
            raise ConfluenceError("unreviewed pipeline/timezone")
        if self.site_policy != SITE_POLICY:
            raise ConfluenceError("site discovery policy changed")
        requested = Path(self.root).absolute()
        if requested.is_symlink():
            raise ConfluenceError("rehearsal root must not be a symlink")
        root = requested.resolve()
        if any((p / ".git").exists() for p in (root, *root.parents)):
            raise ConfluenceError("private rehearsal output must be outside a Git worktree")
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "site_base_url", self.site_base_url.rstrip("/"))

    @property
    def site_policy(self) -> dict:
        return {"external_discovery": self.external_discovery, "robots": self.robots,
                "generate_sitemap": self.generate_sitemap}

    @property
    def public_config(self) -> dict:
        return {"site_base_url": self.site_base_url, "site_policy": self.site_policy,
                "pipeline_key": self.pipeline_key, "timezone": self.timezone,
                "mode": "local-private-rehearsal", "schema": "confluence.publication.v1",
                "pressroom_commit": PRESSROOM_COMMIT, "html_policy": POLICY_VERSION, "libxml_version": list(LIBXML_VERSION)}

    @property
    def fingerprint(self) -> str:
        # The private output location is also immutable, never exported to HTML.
        return digest({**self.public_config, "private_root": str(self.root)})

    def route(self, manuscript_ref: str, locale: str) -> str:
        if not re.fullmatch(r"ART[0-9]{4,}", manuscript_ref) or locale not in ("ja", "en"):
            raise ConfluenceError("invalid article identity/locale")
        return f"{locale}/articles/{manuscript_ref.lower()}.html"

    def url(self, manuscript_ref: str, locale: str) -> str:
        return self.site_base_url + "/" + self.route(manuscript_ref, locale)
