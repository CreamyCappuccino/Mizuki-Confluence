"""Explicit nine-meta representation; no remote parsing, learning or image fetch."""
from __future__ import annotations

from dataclasses import dataclass
from html import escape

from .here_now_html import HereNowHtmlPolicy
from .release_checksums import DIGEST, ReleaseReadbackMismatch

IMAGE_FORMAT = 'here-now-og/v2'
IMAGE_META_ORDER = (
    'og:title', 'og:description', 'og:url', 'og:type', 'og:image',
    'og:image:width', 'og:image:height', 'twitter:image', 'twitter:card',
)


@dataclass(frozen=True, slots=True, kw_only=True)
class HereNowImageHtmlPolicy(HereNowHtmlPolicy):
    """One observed order, operator-pinned values, independent of remote bytes.

    V1 remains unchanged. Required v2 fields cannot be inferred on the caller's
    behalf. Every field is immutable; remote metadata cannot expand scope.
    """
    image_url: str
    image_width: int
    image_height: int
    block_prefix: str = ''
    tag_separator: str = '\n'
    block_suffix: str = ''
    format: str = IMAGE_FORMAT

    def __post_init__(self):
        if self.format != IMAGE_FORMAT:
            raise ReleaseReadbackMismatch('unsupported image HTML policy')
        self._validate_common()
        if (not isinstance(self.expected_manifest_sha256, str)
                or not DIGEST.fullmatch(self.expected_manifest_sha256)):
            raise ReleaseReadbackMismatch('image HTML policy requires a manifest pin')
        slug = self.here_now_base.removeprefix('https://').removesuffix('.here.now')
        if self.image_url != f'https://here.now/og/{slug}.jpg':
            raise ReleaseReadbackMismatch('image reference does not match the configured site')
        for value in (self.image_width, self.image_height):
            if type(value) is not int or not 1 <= value <= 16384:
                raise ReleaseReadbackMismatch('invalid declared image dimensions')
        if (self.block_prefix, self.tag_separator, self.block_suffix) != ('', '\n', ''):
            raise ReleaseReadbackMismatch('image policy requires the reported LF-only insertion')

    def _tags(self, url: str) -> tuple[str, ...]:
        values = {
            'og:title': self.title, 'og:description': self.description,
            'og:url': url, 'og:type': 'website', 'og:image': self.image_url,
            'og:image:width': str(self.image_width),
            'og:image:height': str(self.image_height),
            'twitter:image': self.image_url, 'twitter:card': 'summary_large_image',
        }
        # Exactly the order confirmed in all eight saved responses (CX-MSG0337).
        return tuple(
            f'<meta {"name" if key.startswith("twitter:") else "property"}="{key}" '
            f'content="{escape(values[key], quote=True)}" />'
            for key in IMAGE_META_ORDER
        )
