"""Canonical revision/author projection without depending on AI Inner Life."""
from __future__ import annotations

from .provider_core import PublicAuthor, ResolvedArticle


class _CanonicalReader:
    def __init__(self, session_factory) -> None:
        from pressroom.persistence import ManuscriptRepositoryProfile

        self._session_factory = session_factory
        self._profile = ManuscriptRepositoryProfile(destination_key="confluence")

    def get(self, ref: str, *, mode: str = "current") -> ResolvedArticle:
        from pressroom.persistence import (
            ManuscriptClassificationRepository,
            ManuscriptRepository,
            session_scope,
        )
        from pressroom.persistence.author_repository import AuthorIdentityRepository
        from pressroom.services.manuscript_projection import manuscript_snapshot

        with session_scope(self._session_factory) as session:
            record = ManuscriptRepository(session, profile=self._profile).get(ref, mode=mode)
            classification = ManuscriptClassificationRepository(
                session, profile=self._profile
            ).load(
                revision_id=record.revision.id,
                manuscript_id=record.manuscript.id,
                mode=mode,
            )
            snapshot = manuscript_snapshot(
                record,
                profile=self._profile,
                classification=classification,
            )
            # Standalone manuscript_snapshot does not populate authors. Resolve
            # attributions for this exact revision in the same read transaction.
            attributions = AuthorIdentityRepository(
                session, manuscript_profile=self._profile
            ).list_many((snapshot.revision_ref,))[snapshot.revision_ref]
            authors = tuple(
                PublicAuthor(
                    author_ref=value.author_ref,
                    persona_name=value.persona_name,
                    harness=value.harness,
                    model=value.model,
                    role=value.role,
                    provenance_source=value.provenance_source,
                )
                for value in attributions
            )
            return ResolvedArticle(
                manuscript_id=record.manuscript.id,
                revision_id=record.revision.id,
                manuscript_ref=snapshot.manuscript_ref,
                revision_ref=snapshot.revision_ref,
                revision_no=snapshot.revision_no,
                edition_ref=snapshot.edition_ref,
                locale=snapshot.locale,
                title=snapshot.title,
                excerpt=snapshot.excerpt,
                author_label=snapshot.author_label,
                authors=authors,
                category_paths=snapshot.category_paths,
                tags=snapshot.tags,
                content_updated_at=snapshot.content_updated_at,
                rendered_html=snapshot.rendered_html,
                renderer_version=snapshot.renderer_version,
            )

