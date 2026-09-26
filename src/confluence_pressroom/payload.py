"""Confluence Phase 1 prepared publication payload."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import re
from urllib.parse import urlsplit

from .html_prepare import PreparedHTML

SCHEMA_VERSION = "confluence.publication.v1"
ART = re.compile(r"ART[0-9]{4,}\Z")
REV = re.compile(r"ART[0-9]{4,}-R[0-9]{2,}\Z")
EDN = re.compile(r"EDN[0-9]{4,}\Z")


@dataclass(frozen=True, slots=True)
class CandidateArticle:
    manuscript_ref: str
    revision_ref: str
    revision_no: int
    edition_ref: str | None
    locale: str
    title: str
    excerpt: str | None
    author_label: str | None
    authors: tuple[dict[str, object], ...]
    category_paths: tuple[tuple[str, ...], ...]
    tags: tuple[str, ...]
    content_updated_at: datetime | None
    renderer_version: str
    prepared_html: PreparedHTML


def payload_sha256(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _route(site_base_url: str, locale: str, manuscript_ref: str) -> str:
    parsed = urlsplit(site_base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError("site_base_url must be a normalized HTTPS origin/base")
    return f'{site_base_url.rstrip("/")}/{locale}/articles/{manuscript_ref.lower()}.html'


def build_publication_payload(
    article: CandidateArticle,
    *,
    site_base_url: str,
    published_on: date,
    visibility: str = "public",
) -> dict[str, object]:
    if not ART.fullmatch(article.manuscript_ref):
        raise ValueError("manuscript_ref must be ART reference")
    if not REV.fullmatch(article.revision_ref):
        raise ValueError("revision_ref must be ART-R reference")
    expected = f"{article.manuscript_ref}-R{article.revision_no:02d}"
    if article.revision_ref != expected:
        raise ValueError("revision_ref/revision_no mismatch")
    if article.edition_ref is not None and not EDN.fullmatch(article.edition_ref):
        raise ValueError("edition_ref must be EDN reference or null")
    if article.locale not in {"ja", "en"}:
        raise ValueError("Phase 1 locale must be ja/en")
    if visibility != "public":
        raise ValueError("Phase 1 supports Confluence-internal public listing only")
    if not article.title.strip():
        raise ValueError("title is required")
    return {
        "schema_version": SCHEMA_VERSION,
        "destination_key": "confluence",
        "manuscript_ref": article.manuscript_ref,
        "revision_ref": article.revision_ref,
        "revision_no": article.revision_no,
        "edition_ref": article.edition_ref,
        "locale": article.locale,
        "destination_ref": f"confluence:{article.manuscript_ref}",
        "destination_url": _route(site_base_url, article.locale, article.manuscript_ref),
        "title": article.title,
        "excerpt": article.excerpt,
        "rendered_html": article.prepared_html.html,
        "renderer_version": f"{article.renderer_version}|{article.prepared_html.preparation_version}",
        "author_label": article.author_label,
        "authors": [dict(value) for value in article.authors],
        "category_paths": [list(path) for path in article.category_paths],
        "tags": list(article.tags),
        "published_on": published_on.isoformat(),
        "content_updated_at": (
            article.content_updated_at.isoformat() if article.content_updated_at else None
        ),
        "visibility": visibility,
    }
