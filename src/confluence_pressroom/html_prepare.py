"""Deterministic pre-PUB normalization for sanitized Pressroom renderer HTML.

The upstream renderer is expected to perform actual sanitization. This module
adds Confluence-owned heading IDs, resolves local fragments, normalizes the
small attribute seam, and fails closed on unsupported markup before approval.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from html import escape
from html.parser import HTMLParser
import re
import unicodedata
from urllib.parse import unquote, urlsplit

PREPARATION_VERSION = "confluence-html-prepare/v1"
ALLOWED_TAGS = frozenset(
    "p h1 h2 h3 h4 h5 h6 blockquote pre code ul ol li strong em b i s del "
    "a br hr sup sub table caption thead tbody tfoot tr th td span".split()
)
VOID_TAGS = frozenset({"br", "hr"})
HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
LANG = re.compile(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*\Z")
CODE_CLASS = re.compile(r"language-[A-Za-z0-9_+-]{1,40}\Z")
POSITIVE_INT = re.compile(r"[1-9][0-9]?\Z")


@dataclass(slots=True)
class _Node:
    tag: str | None
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["_Node | str"] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PreparedHTML:
    html: str
    preparation_version: str
    heading_ids: tuple[str, ...]


class _TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node(None)
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED_TAGS:
            raise ValueError("renderer output has unsupported element")
        node = _Node(tag)
        seen = set()
        for name, value in attrs:
            if name in seen or value is None:
                raise ValueError("renderer output has duplicate/bare attributes")
            seen.add(name)
            node.attrs[name] = value
        self.stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        if tag not in VOID_TAGS:
            raise ValueError("only br/hr may be self-closing")
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if len(self.stack) == 1 or self.stack[-1].tag != tag:
            raise ValueError("renderer output has unbalanced tags")
        self.stack.pop()

    def handle_data(self, data):
        self.stack[-1].children.append(data)

    def handle_comment(self, data):
        raise ValueError("renderer output comments are unsupported")

    def handle_decl(self, decl):
        raise ValueError("renderer output declarations are unsupported")

    def handle_pi(self, data):
        raise ValueError("renderer output processing instructions are unsupported")

    def close_checked(self):
        self.close()
        if len(self.stack) != 1:
            raise ValueError("renderer output has unclosed tags")


def _plain_text(node: _Node) -> str:
    pieces: list[str] = []
    for child in node.children:
        pieces.append(child if isinstance(child, str) else _plain_text(child))
    return unicodedata.normalize("NFC", "".join(pieces)).strip()


def _heading_base(text: str) -> str:
    if not text:
        raise ValueError("heading text may not be empty")
    digest = sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"cf-h-{digest}"


def _validate_https(value: str) -> None:
    if "\\" in value or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("link contains whitespace/control characters")
    try:
        parts = urlsplit(value)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
        ):
            raise ValueError("absolute links must be HTTPS without credentials")
        _ = parts.port
    except ValueError as exc:
        raise ValueError("invalid absolute link") from exc


def _normalize_attrs(node: _Node, heading_id: str | None, first_heading: dict[str, str]) -> dict[str, str]:
    attrs = dict(node.attrs)
    if node.tag in HEADING_TAGS:
        if set(attrs) - {"id"}:
            raise ValueError("heading has unsupported attributes")
        return {"id": heading_id} if heading_id else {}

    if node.tag == "a":
        if set(attrs) - {"href", "title", "rel"}:
            raise ValueError("link has unsupported attributes")
        href = attrs.get("href")
        if not href:
            raise ValueError("link href is required")
        if href.startswith("#"):
            target_text = unicodedata.normalize("NFC", unquote(href[1:])).strip()
            target = first_heading.get(target_text)
            if target is None:
                raise ValueError("local fragment does not resolve to a heading")
            result = {"href": f"#{target}"}
        else:
            _validate_https(href)
            result = {"href": href}
        if "title" in attrs:
            result["title"] = attrs["title"]
        rel = attrs.get("rel")
        if rel is not None and set(rel.split()) - {"noopener", "noreferrer"}:
            raise ValueError("link rel contains unsupported tokens")
        return result

    if node.tag == "code":
        allowed = {"class"}
        if "class" in attrs and not CODE_CLASS.fullmatch(attrs["class"]):
            raise ValueError("code class is unsupported")
    elif node.tag == "ol":
        allowed = {"start"}
        if "start" in attrs and not POSITIVE_INT.fullmatch(attrs["start"]):
            raise ValueError("ordered-list start is invalid")
    elif node.tag in {"th", "td"}:
        allowed = {"colspan", "rowspan"}
        for key in allowed & set(attrs):
            if not POSITIVE_INT.fullmatch(attrs[key]):
                raise ValueError("table span is invalid")
    else:
        allowed = {"lang"} if node.tag in {"p", "span"} else set()
        if "lang" in attrs and not LANG.fullmatch(attrs["lang"]):
            raise ValueError("lang attribute is invalid")
    if set(attrs) - allowed:
        raise ValueError("renderer output has unsupported attributes")
    return attrs


def _serialize(node: _Node, heading_ids: dict[int, str], first_heading: dict[str, str]) -> str:
    if node.tag is None:
        return "".join(
            escape(child, quote=False) if isinstance(child, str)
            else _serialize(child, heading_ids, first_heading)
            for child in node.children
        )
    attrs = _normalize_attrs(node, heading_ids.get(id(node)), first_heading)
    rendered_attrs = "".join(
        f' {name}="{escape(value, quote=True)}"' for name, value in sorted(attrs.items())
    )
    if node.tag in VOID_TAGS:
        return f"<{node.tag}{rendered_attrs}>"
    body = "".join(
        escape(child, quote=False) if isinstance(child, str)
        else _serialize(child, heading_ids, first_heading)
        for child in node.children
    )
    return f"<{node.tag}{rendered_attrs}>{body}</{node.tag}>"


def prepare_rendered_html(raw_html: str) -> PreparedHTML:
    if not isinstance(raw_html, str) or not raw_html.strip():
        raise ValueError("raw renderer HTML is required")
    parser = _TreeParser()
    parser.feed(raw_html)
    parser.close_checked()

    counts: dict[str, int] = {}
    first_heading: dict[str, str] = {}
    heading_ids: dict[int, str] = {}
    ordered_ids: list[str] = []

    def visit(node: _Node) -> None:
        if node.tag in HEADING_TAGS:
            text = _plain_text(node)
            base = _heading_base(text)
            counts[base] = counts.get(base, 0) + 1
            value = base if counts[base] == 1 else f"{base}-{counts[base]}"
            heading_ids[id(node)] = value
            ordered_ids.append(value)
            first_heading.setdefault(text, value)
        for child in node.children:
            if isinstance(child, _Node):
                visit(child)

    visit(parser.root)
    html = _serialize(parser.root, heading_ids, first_heading)
    return PreparedHTML(
        html=html,
        preparation_version=PREPARATION_VERSION,
        heading_ids=tuple(ordered_ids),
    )
