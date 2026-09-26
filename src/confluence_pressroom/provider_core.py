"""Pressroom-independent preparation core for the Confluence adapter."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from .html_prepare import prepare_rendered_html
from .payload import CandidateArticle, build_publication_payload, payload_sha256


@dataclass(frozen=True, slots=True)
class PublicAuthor:
    author_ref: str
    persona_name: str
    harness: str | None
    model: str | None
    role: str
    provenance_source: str

    def as_payload(self) -> dict[str, object]:
        return {
            "author_ref": self.author_ref,
            "persona_name": self.persona_name,
            "harness": self.harness,
            "model": self.model,
            "role": self.role,
            "provenance_source": self.provenance_source,
        }


@dataclass(frozen=True, slots=True)
class ResolvedArticle:
    manuscript_id: UUID
    revision_id: UUID
    manuscript_ref: str
    revision_ref: str
    revision_no: int
    edition_ref: str | None
    locale: str
    title: str
    excerpt: str | None
    author_label: str | None
    authors: tuple[PublicAuthor, ...]
    category_paths: tuple[tuple[str, ...], ...]
    tags: tuple[str, ...]
    content_updated_at: datetime | None
    rendered_html: str
    renderer_version: str


class ArticleResolver(Protocol):
    def get(self, ref: str, *, mode: str = "current") -> ResolvedArticle: ...


@dataclass(frozen=True, slots=True)
class PreparedCandidate:
    manuscript_id: UUID
    revision_id: UUID
    manuscript_ref: str
    revision_ref: str
    destination_ref: str
    destination_url: str
    title: str
    payload_snapshot: dict[str, object]
    payload_sha256: str


class ConfluenceProviderCore:
    def __init__(self, resolver: ArticleResolver, *, site_base_url: str) -> None:
        self._resolver = resolver
        self._site_base_url = site_base_url

    def prepare(
        self,
        manuscript_ref: str,
        revision_ref: str | None,
        destination_metadata: dict[str, object] | None,
    ) -> PreparedCandidate:
        metadata = dict(destination_metadata or {})
        published_on = metadata.pop("published_on", None)
        if metadata:
            raise ValueError("unsupported Confluence destination metadata")
        if not isinstance(published_on, str):
            raise ValueError("published_on destination metadata is required")
        try:
            display_date = date.fromisoformat(published_on)
        except ValueError as exc:
            raise ValueError("published_on must be YYYY-MM-DD") from exc

        current = self._resolver.get(manuscript_ref)
        selected = self._resolver.get(revision_ref or manuscript_ref)
        if selected.manuscript_id != current.manuscript_id:
            raise ValueError("revision_ref must belong to manuscript_ref")
        prepared_html = prepare_rendered_html(selected.rendered_html)
        article = CandidateArticle(
            manuscript_ref=selected.manuscript_ref,
            revision_ref=selected.revision_ref,
            revision_no=selected.revision_no,
            edition_ref=selected.edition_ref,
            locale=selected.locale,
            title=selected.title,
            excerpt=selected.excerpt,
            author_label=selected.author_label,
            authors=tuple(author.as_payload() for author in selected.authors),
            category_paths=selected.category_paths,
            tags=selected.tags,
            content_updated_at=selected.content_updated_at,
            renderer_version=selected.renderer_version,
            prepared_html=prepared_html,
        )
        payload = build_publication_payload(
            article,
            site_base_url=self._site_base_url,
            published_on=display_date,
        )
        return PreparedCandidate(
            manuscript_id=selected.manuscript_id,
            revision_id=selected.revision_id,
            manuscript_ref=selected.manuscript_ref,
            revision_ref=selected.revision_ref,
            destination_ref=str(payload["destination_ref"]),
            destination_url=str(payload["destination_url"]),
            title=selected.title,
            payload_snapshot=payload,
            payload_sha256=payload_sha256(payload),
        )
