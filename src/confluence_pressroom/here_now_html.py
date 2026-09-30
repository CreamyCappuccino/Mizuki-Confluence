"""Predict one explicitly authorized five-meta insertion; never strip remote HTML."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from html import escape
from html.parser import HTMLParser
import json
import re

from .release_checksums import DIGEST, ReleaseReadbackMismatch, safe_relative_path
from .release_http import target_url, validate_base

FORMAT = 'here-now-og/v1'


class _HeadBoundary(HTMLParser):
    """Locate the real closing head, not a string inside a comment/script."""
    def __init__(self, source: str):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.opens = self.closes = 0
        self.inside = False
        self.closing_offset: int | None = None
        self.owned_meta = False

    def handle_starttag(self, tag, attrs):
        if tag == 'head':
            self.opens += 1
            self.inside = True
        if tag == 'meta':
            for name, value in attrs:
                if name in {'name', 'property'} and value is not None:
                    key = value.lower()
                    if key.startswith(('og:', 'twitter:')):
                        self.owned_meta = True

    def handle_endtag(self, tag):
        if tag == 'head':
            self.closes += 1
            if not self.inside:
                raise ReleaseReadbackMismatch('ambiguous source head')
            line, column = self.getpos()
            lines = self.source.split('\n')
            offset = sum(len(part) + 1 for part in lines[:line - 1]) + column
            self.closing_offset = len(self.source[:offset].encode('utf-8'))
            self.inside = False


def _head_offset(original: bytes) -> int:
    if original.count(b'</head>') != 1:
        raise ReleaseReadbackMismatch('ambiguous source closing head')
    try:
        source = original.decode('utf-8')
        parser = _HeadBoundary(source)
        parser.feed(source)
        parser.close()
    except (UnicodeError, ValueError) as exc:
        raise ReleaseReadbackMismatch('invalid source HTML for transformation') from exc
    if (parser.opens != 1 or parser.closes != 1 or parser.inside
            or parser.owned_meta or parser.closing_offset is None
            or original[parser.closing_offset:parser.closing_offset + 7] != b'</head>'):
        raise ReleaseReadbackMismatch('source HTML is ineligible for five-meta insertion')
    return parser.closing_offset


@dataclass(frozen=True, slots=True)
class HereNowHtmlPolicy:
    """Pinned operator expectations, independent of bytes served by the provider.

    Whitespace is an exact serialization setting, not a normalization option.
    No values are learned from the remote document. Default callers use no policy.
    """
    here_now_base: str
    nor_base: str
    title: str
    description: str
    block_prefix: str = '\n'
    tag_separator: str = '\n'
    block_suffix: str = '\n'
    expected_manifest_sha256: str | None = None
    format: str = FORMAT

    def __post_init__(self):
        if self.format != FORMAT:
            raise ReleaseReadbackMismatch('unsupported HTML transformation policy')
        for base in (self.here_now_base, self.nor_base):
            if validate_base(base) != base:
                raise ReleaseReadbackMismatch('profile bases must be normalized')
        if (self.here_now_base == self.nor_base or not re.fullmatch(
                r'https://[a-z0-9]+(?:-[a-z0-9]+)*\.here\.now', self.here_now_base)):
            raise ReleaseReadbackMismatch('profile requires a here.now site and distinct mount')
        for value in (self.title, self.description):
            if (not isinstance(value, str) or not value or len(value) > 4096
                    or any(ord(c) < 32 or ord(c) == 127 for c in value)):
                raise ReleaseReadbackMismatch('invalid pinned meta content')
            try:
                value.encode('utf-8')
            except UnicodeError as exc:
                raise ReleaseReadbackMismatch('invalid Unicode in pinned meta') from exc
        for value in (self.block_prefix, self.tag_separator, self.block_suffix):
            if (not isinstance(value, str) or len(value) > 32
                    or any(c not in ' \t\r\n' for c in value)):
                raise ReleaseReadbackMismatch('invalid pinned insertion whitespace')
        pin = self.expected_manifest_sha256
        if pin is not None and (not isinstance(pin, str) or not DIGEST.fullmatch(pin)):
            raise ReleaseReadbackMismatch('invalid profile manifest pin')

    @property
    def sha256(self) -> str:
        raw = json.dumps(asdict(self), sort_keys=True, ensure_ascii=False,
                         separators=(',', ':'), allow_nan=False).encode('utf-8')
        return hashlib.sha256(raw).hexdigest()

    def validate_bases(self, bases: tuple[str, str]) -> None:
        if bases != (self.here_now_base, self.nor_base):
            raise ReleaseReadbackMismatch('HTML policy does not match delivery bases')

    def validate_scope(self, bases: tuple[str, str], manifest_sha256: str) -> None:
        self.validate_bases(bases)
        if (self.expected_manifest_sha256 is not None
                and self.expected_manifest_sha256 != manifest_sha256):
            raise ReleaseReadbackMismatch('HTML policy does not match the frozen manifest')

    def predict(self, original: bytes, *, base: str, relative: str) -> bytes:
        """Build the only alternate accepted representation, from trusted inputs."""
        if base not in (self.here_now_base, self.nor_base):
            raise ReleaseReadbackMismatch('HTML policy origin mismatch')
        safe_relative_path(relative)
        if not relative.lower().endswith(('.html', '.htm')):
            raise ReleaseReadbackMismatch('HTML transformation cannot cover non-HTML')
        position = _head_offset(original)
        url = target_url(base, relative)
        tags = (
            f'<meta property="og:title" content="{escape(self.title, quote=True)}" />',
            f'<meta property="og:description" content="{escape(self.description, quote=True)}" />',
            f'<meta property="og:url" content="{escape(url, quote=True)}" />',
            '<meta property="og:type" content="website" />',
            '<meta name="twitter:card" content="summary" />',
        )
        block = (self.block_prefix + self.tag_separator.join(tags) + self.block_suffix).encode('utf-8')
        return original[:position] + block + original[position:]
