"""Pre-PUB allowlist reserialization for the private rehearsal provider.

A syntax guard refuses lossy parser repair. libxml2 then parses the fragment;
we construct new markup with fixed tags/attributes and escaped text. This is
not the offline fixture checker and is not approved for production exposure.
Dispatch checks canonical prepared bytes without repairing an approved payload.
"""
from html import escape
from html.parser import HTMLParser
import re
import unicodedata
from lxml import etree, html
from .config import ConfluenceError
from .html_fragments import HEADINGS, SAFE_ID, assign_fragments, resolve_fragment
from .html_policy import POLICY_VERSION, LXML_VERSION, LIBXML_VERSION, MAX_HTML_BYTES, MAX_NODES, MAX_DEPTH
from .payload_schema import validate_https_url

TAGS = frozenset("p h1 h2 h3 h4 h5 h6 blockquote pre code ul ol li strong em b i s del a br hr sup sub table caption thead tbody tfoot tr th td span".split())
VOID = frozenset({"br", "hr"})
LANG = re.compile(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*\Z")


class _SyntaxGuard(HTMLParser):
    """Only reject malformed/unsupported source; never sanitize or emit HTML."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.count = [], 0

    def handle_starttag(self, tag, attrs):
        self.count += 1
        names = [name for name, _ in attrs]
        if tag not in TAGS or len(names) != len(set(names)) or any(v is None for _, v in attrs):
            raise ConfluenceError("unsupported element or duplicate/bare attribute")
        if self.count > MAX_NODES or len(self.stack) >= MAX_DEPTH:
            raise ConfluenceError("HTML structural limit exceeded")
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            raise ConfluenceError("HTML needs balanced explicit closing tags")

    def handle_startendtag(self, tag, attrs):
        if tag not in VOID:
            raise ConfluenceError("only br/hr may be self-closing")
        self.handle_starttag(tag, attrs)

    def handle_comment(self, _):
        raise ConfluenceError("article HTML cannot contain comments/declarations")

    handle_decl = handle_pi = unknown_decl = handle_comment


def _parse(raw: str):
    if etree.LXML_VERSION[:3] != LXML_VERSION or etree.LIBXML_VERSION != LIBXML_VERSION:
        raise ConfluenceError("HTML preparation dependency pin mismatch")
    try:
        invalid = not isinstance(raw, str) or not raw.strip() or len(raw.encode("utf8")) > MAX_HTML_BYTES
    except UnicodeError as exc:
        raise ConfluenceError("HTML must be valid UTF-8 text") from exc
    if invalid or any(ord(c) < 32 and c not in "\t\n\r" for c in raw):
        raise ConfluenceError("HTML fragment empty, oversized, or contains controls")
    guard = _SyntaxGuard()
    try:
        guard.feed(raw)
        guard.close()
        if guard.stack:
            raise ConfluenceError("HTML has unclosed elements")
        parser = html.HTMLParser(no_network=True, recover=False, encoding="utf-8")
        root = html.fragment_fromstring(raw, create_parent="div", parser=parser)
    except (ValueError, etree.ParserError, etree.XMLSyntaxError) as exc:
        if isinstance(exc, ConfluenceError):
            raise
        raise ConfluenceError("renderer did not produce a parseable fragment") from exc
    nodes = list(root.iterdescendants())
    if len(nodes) != guard.count or len(nodes) > MAX_NODES:
        raise ConfluenceError("HTML parser changed the source structure")
    for node in nodes:
        if not isinstance(node.tag, str) or node.tag not in TAGS or len(list(node.iterancestors())) > MAX_DEPTH:
            raise ConfluenceError("unsupported element or HTML nesting limit")
    return root, nodes


def _attributes(node, explicit, labels, *, canonical):
    attrs = {}
    for name, value in node.attrib.items():
        tag = node.tag
        if name == "id":
            if canonical and not SAFE_ID.fullmatch(value):
                raise ConfluenceError("HTML is not prepared under this policy")
            attrs[name] = value if canonical else explicit[unicodedata.normalize("NFC", value)]
        elif name == "lang" and LANG.fullmatch(value):
            attrs[name] = value
        elif tag == "a" and name == "href":
            if value.startswith("#"):
                if canonical:
                    target = value[1:]
                    if target not in explicit or not SAFE_ID.fullmatch(target):
                        raise ConfluenceError("unresolved prepared fragment")
                else:
                    target = resolve_fragment(value[1:], explicit, labels)
                attrs[name] = "#" + target
            else:
                validate_https_url(value)
                attrs[name] = value
        elif tag == "a" and name == "rel" and not canonical:
            if not value.split() or not set(value.split()) <= {"noopener", "noreferrer"}:
                raise ConfluenceError("unreviewed renderer link relation")
            # Current renderer adds these to same-tab links. Strip only here,
            # before approval, to match the agreed prepared-attribute allowlist.
        elif tag == "a" and name == "title":
            attrs[name] = value
        elif tag == "code" and name == "class" and re.fullmatch(r"language-[A-Za-z0-9_+-]{1,40}", value):
            attrs[name] = value
        elif tag == "ol" and name == "start" and re.fullmatch(r"[0-9]{1,6}", value):
            attrs[name] = value
        elif tag in {"th", "td"} and name in {"colspan", "rowspan"} and re.fullmatch(r"[1-9][0-9]?", value):
            attrs[name] = value
        else:
            raise ConfluenceError("unsupported HTML attribute before publication")
    return attrs


def _emit(root, explicit, labels, assigned, *, canonical):
    def emit(node):
        attrs = _attributes(node, explicit, labels, canonical=canonical)
        if node in assigned:
            attrs["id"] = assigned[node]
        attr_text = "".join(f' {k}="{escape(v, quote=True)}"' for k, v in sorted(attrs.items()))
        if node.tag in VOID:
            return f"<{node.tag}{attr_text}>" + escape(node.tail or "")
        inside = escape(node.text or "") + "".join(emit(child) for child in node)
        return f"<{node.tag}{attr_text}>{inside}</{node.tag}>" + escape(node.tail or "")
    return escape(root.text or "") + "".join(emit(child) for child in root)


def prepare_html(raw: str) -> str:
    """Pre-PUB only: deterministically namespace IDs and resolve local links."""
    root, nodes = _parse(raw)
    explicit, labels, assigned = assign_fragments(nodes)
    output = _emit(root, explicit, labels, assigned, canonical=False)
    validate_prepared_html(output)
    return output


def validate_prepared_html(raw: str) -> None:
    """Validate canonical immutable output; NEVER replace approved input bytes."""
    root, nodes = _parse(raw)
    ids = {}
    for node in nodes:
        value = node.get("id")
        if value is not None:
            if value in ids or not SAFE_ID.fullmatch(value):
                raise ConfluenceError("invalid prepared HTML ID")
            ids[value] = value
        elif node.tag in HEADINGS:
            raise ConfluenceError("prepared heading has no ID")
    if _emit(root, ids, {}, {}, canonical=True) != raw:
        raise ConfluenceError("prepared HTML bytes are not canonical")
