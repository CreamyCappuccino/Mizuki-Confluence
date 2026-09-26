"""Deterministic readback of complete artifacts and each discovery surface.

Expected bytes come from private projection state and the approved payload,
not from markers or digests copied out of the artifact being verified.
"""
from __future__ import annotations

from pathlib import Path

from .payload import payload_sha256
from .static_pages import render_article, render_browse, render_index, render_search


def exact_file(path: Path, expected: str) -> bool:
    # Missing output is not positive readback; other I/O errors remain unknown
    # at the caller rather than being mistaken for verified absence.
    try:
        actual = path.read_bytes()
    except FileNotFoundError:
        return False
    return actual == expected.encode("utf-8")


def article_matches(path: Path, payload: dict[str, object]) -> bool:
    return exact_file(path, render_article(payload, payload_sha256(payload)))


def mismatched_surfaces(site: Path, articles: dict) -> tuple[str, ...]:
    outputs = (
        ("index.html", render_index(articles)),
        ("search.json", render_search(articles)),
        ("browse.html", render_browse(articles)),
    )
    # Check every surface independently. In particular, NOT (index AND search)
    # cannot establish a successful withdrawal of either surface.
    return tuple(name for name, expected in outputs if not exact_file(site / name, expected))
