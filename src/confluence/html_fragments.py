"""Deterministic pre-PUB heading IDs and local-fragment resolution.

Exact original IDs win; otherwise an NFC/whitespace-normalized heading label
resolves to its first occurrence. Repeated labels have distinct generated IDs.
No fuzzy matching, remote resolution, or title-derived article routing.
"""
import re
import unicodedata
from urllib.parse import unquote
from .config import ConfluenceError

HEADINGS = frozenset(f"h{i}" for i in range(1, 7))
SAFE_ID = re.compile(r"cf-n-[0-9]{4,}\Z")


def normalized_label(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split())


def decode_fragment(value: str) -> str:
    if re.search(r"%(?![0-9A-Fa-f]{2})", value):
        raise ConfluenceError("malformed local fragment encoding")
    try:
        decoded = unquote(value, encoding="utf-8", errors="strict")
    except UnicodeError as exc:
        raise ConfluenceError("invalid UTF-8 local fragment") from exc
    if not decoded or len(decoded) > 1000 or any(ord(c) < 32 or ord(c) == 127 for c in decoded):
        raise ConfluenceError("invalid local fragment")
    return unicodedata.normalize("NFC", decoded)


def assign_fragments(nodes):
    explicit, labels, assigned = {}, {}, {}
    for index, node in enumerate(nodes, 1):
        old = node.get("id")
        if old is not None:
            old = unicodedata.normalize("NFC", old)
            if (not old or len(old) > 256 or old in explicit
                    or any(c.isspace() or ord(c) < 32 for c in old)):
                raise ConfluenceError("invalid or duplicate renderer ID")
            explicit[old] = assigned[node] = f"cf-n-{index:04d}"
        elif node.tag in HEADINGS:
            assigned[node] = f"cf-n-{index:04d}"
    for node in nodes:
        if node.tag in HEADINGS:
            label = normalized_label("".join(node.itertext()))
            if label:
                labels.setdefault(label, assigned[node])
    return explicit, labels, assigned


def resolve_fragment(value: str, explicit: dict, labels: dict) -> str:
    decoded = decode_fragment(value)
    target = explicit.get(decoded) or labels.get(normalized_label(decoded))
    if target is None:
        raise ConfluenceError("HTML has an unresolved local fragment")
    return target
