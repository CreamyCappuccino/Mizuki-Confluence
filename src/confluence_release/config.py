"""Destination-specific configuration; never borrow AIL deployment defaults."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from urllib.parse import urlsplit

ROBOTS = 'noindex, nofollow, noarchive'


def json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(',', ':')).encode('utf-8')


def digest(value: object) -> str:
    return hashlib.sha256(json_bytes(value)).hexdigest()


def https_base(value: str) -> str:
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError('release base must be a normalized HTTPS URL')
    p = urlsplit(value)
    if (p.scheme != 'https' or not p.hostname or p.username is not None
            or p.password is not None or p.query or p.fragment
            or '%' in value or '\\' in value or '//' in p.path
            or any(x in {'.', '..'} for x in p.path.split('/'))):
        raise ValueError('release base must be a normalized HTTPS URL')
    _ = p.port
    return value.rstrip('/')


@dataclass(frozen=True)
class ReleaseConfig:
    site_base: str
    here_now_slug: str
    nor_base: str

    def __post_init__(self) -> None:
        object.__setattr__(self, 'site_base', https_base(self.site_base))
        object.__setattr__(self, 'nor_base', https_base(self.nor_base))
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', self.here_now_slug):
            raise ValueError('invalid here.now slug')
        if self.site_base != self.nor_base:
            raise ValueError('Confluence canonical base must match its Nor base')

    @property
    def here_now_base(self) -> str:
        return f'https://{self.here_now_slug}.here.now'

    @property
    def public_config(self) -> dict[str, object]:
        return dict(site_base_url=self.site_base, here_now_slug=self.here_now_slug,
                    nor_base=self.nor_base, external_discovery='discouraged',
                    robots=ROBOTS, sitemap=False, destination_key='confluence')

    @property
    def pipeline_key(self) -> str:
        # APR and JOB already pin pipeline_key. Reuse that boundary rather than
        # introducing another approval object or changing the article schema.
        return 'confluence-here-now-v1-' + digest(self.public_config)
