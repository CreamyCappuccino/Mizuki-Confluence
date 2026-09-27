"""AIL authority->projection pattern, using Confluence's frozen PUB payloads."""
from __future__ import annotations
from copy import deepcopy

from .projection import ProjectionArticle, validate_projection


class CanonicalReleaseReader:
    def __init__(self, session_factory):
        self.factory = session_factory

    def published_articles(self) -> tuple[ProjectionArticle, ...]:
        from sqlalchemy import select
        from pressroom.persistence import Destination, PublicationBinding, PublicationAttempt
        articles = []
        with self.factory() as s:
            bindings = s.scalars(select(PublicationBinding).join(Destination).where(
                Destination.key == 'confluence', PublicationBinding.state == 'published')).all()
            for b in bindings:
                attempts = s.scalars(select(PublicationAttempt).where(
                    PublicationAttempt.binding_id == b.id, PublicationAttempt.action == 'publish',
                    PublicationAttempt.status == 'published',
                    PublicationAttempt.revision_id == b.published_revision_id
                ).order_by(PublicationAttempt.completed_at.desc(), PublicationAttempt.publication_no.desc())).all()
                a = next((v for v in attempts if not v.payload_snapshot.get('operation_kind')), None)
                if a is None:
                    raise ValueError('published Confluence binding has no successful article attempt')
                articles.append(ProjectionArticle(b.manuscript_id, b.published_revision_id,
                    deepcopy(a.payload_snapshot), a.payload_sha256))
        result = tuple(articles)
        validate_projection(result)
        return result

    def desired_articles(self, context) -> tuple[ProjectionArticle, ...]:
        articles = {str(a.manuscript_id): a for a in self.published_articles()}
        if context.job_action == 'publish':
            articles[str(context.manuscript_id)] = ProjectionArticle(context.manuscript_id,
                context.revision_id, deepcopy(context.attempt_payload_snapshot), context.attempt_payload_sha256)
        else:
            articles.pop(str(context.manuscript_id), None)
        result = tuple(articles.values())
        validate_projection(result)
        return result

    def published_on(self, manuscript_id):
        from sqlalchemy import select
        from pressroom.persistence import Destination, PublicationBinding, PublicationAttempt
        with self.factory() as s:
            rows = s.scalars(select(PublicationAttempt).join(PublicationBinding).join(Destination).where(
                Destination.key == 'confluence', PublicationBinding.manuscript_id == manuscript_id,
                PublicationAttempt.action == 'publish', PublicationAttempt.status == 'published'
            ).order_by(PublicationAttempt.completed_at.desc(), PublicationAttempt.publication_no.desc())).all()
            for a in rows:
                if not a.payload_snapshot.get('operation_kind'):
                    return a.payload_snapshot.get('published_on')
        return None

    def revision_ref(self, manuscript_id, revision_id):
        from sqlalchemy import select
        from pressroom.persistence import Manuscript, ManuscriptRevision
        with self.factory() as s:
            row = s.execute(select(Manuscript.manuscript_no, ManuscriptRevision.revision_no)
                .join(ManuscriptRevision, ManuscriptRevision.manuscript_id == Manuscript.id)
                .where(Manuscript.id == manuscript_id, ManuscriptRevision.id == revision_id)).one_or_none()
            if row is None:
                raise ValueError('exact published revision not found')
            return f'ART{row[0]:04d}-R{row[1]:02d}'

    def status(self, manuscript_ref, resolver):
        from pressroom.destinations import PublicationStatus
        from pressroom.persistence import PublicationLedgerRepository
        current = resolver.get(manuscript_ref)
        with self.factory() as s:
            binding = PublicationLedgerRepository(s).find_binding_for_destination(
                manuscript_id=current.manuscript_id, destination_key='confluence')
            state = binding.state if binding else 'never_published'
            published_id = binding.published_revision_id if binding else None
            url = binding.destination_url if binding else None
        published_ref = self.revision_ref(current.manuscript_id, published_id) if published_id else None
        return PublicationStatus(manuscript_ref=current.manuscript_ref, destination='confluence',
            state=state, current_revision_ref=current.revision_ref,
            published_revision_ref=published_ref, destination_url=url if published_id else None)
