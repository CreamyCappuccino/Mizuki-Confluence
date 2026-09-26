"""Strict pre-PUB HTML reserialization for the private rehearsal provider.

Uses libxml2 HTML parsing, then constructs new markup from fixed tags/attributes
and escaped text. It does not upgrade the offline HTMLParser fixture checker.
Unsupported constructs are rejected, not silently lost. This deliberately small
policy still needs destination security review before any production composition.
"""
from html import escape
import re
from urllib.parse import unquote
from lxml import etree, html
from .config import ConfluenceError
from .payload_schema import validate_https_url

POLICY_VERSION = "confluence-prose-v1+lxml-6.1.1"
TAGS = frozenset("p h1 h2 h3 h4 h5 h6 blockquote pre code ul ol li strong em b i s del a br hr sup sub table caption thead tbody tfoot tr th td span".split())
VOID = frozenset({"br", "hr"})
HEADINGS = frozenset(f"h{i}" for i in range(1, 7))
SAFE_ID = re.compile(r"cf-n-[0-9]{4,}\Z")
LANG = re.compile(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*\Z")


def _parse(raw: str):
    if not isinstance(raw, str) or not raw.strip() or len(raw.encode("utf8")) > 1_500_000:
        raise ConfluenceError("HTML fragment empty or too large")
    if re.search(r"<\s*(?:!|\?|/?(?:html|head|body|base)(?:\s|>))", raw, re.I):
        raise ConfluenceError("document wrappers/declarations are not article fragments")
    try:
        parser = html.HTMLParser(no_network=True, encoding="utf-8")
        return html.fragment_fromstring(raw, create_parent="div", parser=parser)
    except (ValueError, etree.ParserError) as exc:
        raise ConfluenceError("renderer did not produce a parseable fragment") from exc


def _attributes(node, ids, *, canonical):
    attrs = {}
    for name, value in node.attrib.items():
        tag = node.tag
        if name == "id":
            if canonical and not SAFE_ID.fullmatch(value):
                raise ConfluenceError("HTML is not prepared under this policy")
            attrs[name] = value if canonical else ids[value]
        elif name == "lang" and LANG.fullmatch(value):
            attrs[name] = value
        elif tag == "a" and name == "href":
            if value.startswith("#"):
                target = unquote(value[1:])
                if target not in ids:
                    raise ConfluenceError("HTML has an unresolved local fragment")
                attrs[name] = "#" + (target if canonical else ids[target])
            else:
                # Relative links, network-path refs, credentials and assets are
                # deferred until a separate resolver is specified.
                validate_https_url(value)
                attrs[name] = value
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


def prepare_html(raw: str) -> str:
    """Rebuild a fragment before approval, namespacing IDs AND local links."""
    root = _parse(raw)
    nodes = list(root.iterdescendants())
    if len(nodes) > 50000:
        raise ConfluenceError("HTML node limit exceeded")
    ids, assigned = {}, {}
    for i, node in enumerate(nodes, 1):
        if not isinstance(node.tag, str) or node.tag not in TAGS:
            raise ConfluenceError("unsupported HTML element before publication")
        if len(list(node.iterancestors())) > 80:
            raise ConfluenceError("HTML nesting limit exceeded")
        old = node.get("id")
        if old is not None:
            if not old or len(old) > 256 or old in ids:
                raise ConfluenceError("invalid or duplicate renderer ID")
            ids[old] = assigned[node] = f"cf-n-{i:04d}"
        elif node.tag in HEADINGS:
            assigned[node] = f"cf-n-{i:04d}"

    def emit(node):
        attrs = _attributes(node, ids, canonical=False)
        if node in assigned:
            attrs["id"] = assigned[node]
        attr_text = "".join(f' {key}="{escape(value, quote=True)}"' for key, value in sorted(attrs.items()))
        if node.tag in VOID:
            return f"<{node.tag}{attr_text}>" + escape(node.tail or "")
        inside = escape(node.text or "") + "".join(emit(child) for child in node)
        return f"<{node.tag}{attr_text}>{inside}</{node.tag}>" + escape(node.tail or "")

    output = escape(root.text or "") + "".join(emit(child) for child in root)
    validate_prepared_html(output)
    return output


def validate_prepared_html(raw: str) -> None:
    """Dispatch validates immutable output; NEVER rewrites it after approval."""
    root = _parse(raw)
    nodes = list(root.iterdescendants())
    ids = {}
    for node in nodes:
        if not isinstance(node.tag, str) or node.tag not in TAGS:
            raise ConfluenceError("unsupported prepared HTML element")
        value = node.get("id")
        if value is not None:
            if value in ids or not SAFE_ID.fullmatch(value):
                raise ConfluenceError("invalid prepared HTML ID")
            ids[value] = value
    for node in nodes:
        _attributes(node, ids, canonical=True)
