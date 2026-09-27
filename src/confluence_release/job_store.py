"""Adapted AIL ReleaseJobStore using the existing Pressroom tables.

Delta: explicit job selection is destination-scoped, and a whole-site lock
serializes snapshot publication. No new JOB/approval database is introduced.
"""
from __future__ import annotations
from contextlib import contextmanager, ExitStack
from datetime import UTC, datetime
import re

from .release_contract import build_release_context


class ReleaseJobStore:
    def __init__(self, session_factory, config, release_root):
        self.factory, self.config, self.release_root = session_factory, config, release_root

    @contextmanager
    def site_lock(self):
        from .release_lock import public_release_lock, PublicReleaseBusyError
        with ExitStack() as stack:
            try:
                stack.enter_context(public_release_lock(self.release_root))
            except PublicReleaseBusyError:
                yield False
                return
            yield True

    def claim(self, job_ref=None, *, reconcile=False):
        from sqlalchemy import select
        from pressroom.persistence import (ApprovalCandidate, Destination, Manuscript,
            ManuscriptRevision, PublicationAttempt, PublicationBinding, ReleaseJob, session_scope)
        if job_ref is not None and not re.fullmatch(r'JOB\d{4,}', job_ref):
            raise ValueError('exact JOB reference required')
        with session_scope(self.factory) as s:
            # Unknown/stuck releases must be resolved before a different full-site
            # artifact is activated. This is not an author/authentication gate.
            outstanding = s.scalar(select(ReleaseJob.job_no)
                .join(ApprovalCandidate, ApprovalCandidate.id == ReleaseJob.approval_id)
                .join(PublicationBinding, PublicationBinding.id == ApprovalCandidate.binding_id)
                .join(Destination, Destination.id == PublicationBinding.destination_id).where(
                Destination.key == 'confluence',
                ReleaseJob.status.in_(('processing', 'unknown_reconcile'))).limit(1))
            if outstanding is not None and job_ref != f'JOB{outstanding:04d}':
                return None
            query = (select(ReleaseJob, ApprovalCandidate, PublicationAttempt,
                            PublicationBinding, Destination, Manuscript, ManuscriptRevision)
                .join(ApprovalCandidate, ApprovalCandidate.id == ReleaseJob.approval_id)
                .join(PublicationAttempt, PublicationAttempt.id == ApprovalCandidate.attempt_id)
                .join(PublicationBinding, PublicationBinding.id == PublicationAttempt.binding_id)
                .join(Destination, Destination.id == PublicationBinding.destination_id)
                .join(Manuscript, Manuscript.id == PublicationBinding.manuscript_id)
                .join(ManuscriptRevision, ManuscriptRevision.id == PublicationAttempt.revision_id)
                .where(Destination.key == 'confluence', ReleaseJob.pipeline_key == self.config.pipeline_key)
                .with_for_update(of=ReleaseJob, skip_locked=True))
            if job_ref is None:
                query = query.where(ReleaseJob.status == 'approved').order_by(ReleaseJob.created_at, ReleaseJob.job_no)
            else:
                query = query.where(ReleaseJob.job_no == int(job_ref[3:]))
            row = s.execute(query.limit(1)).one_or_none()
            if row is None:
                return None
            job, candidate, attempt, binding, destination, manuscript, revision = row
            allowed = {'unknown_reconcile', 'processing'} if reconcile else {'approved'}
            if job.status not in allowed:
                raise ValueError('JOB state is not eligible for the requested operation')
            # Do not supersede an operation whose external result is unknown.
            stale = (job.action == 'publish' and manuscript.current_revision_id != revision.id)
            if stale and attempt.status == 'awaiting_confirmation':
                now = datetime.now(UTC)
                job.status, job.current_step = 'superseded', 'candidate_superseded'
                job.completed_at = job.updated_at = now
                candidate.status, candidate.superseded_at = 'superseded', now
                return None
            job.status, job.current_step = 'processing', 'reconcile' if reconcile else 'preflight'
            job.started_at = job.started_at or datetime.now(UTC)
            job.updated_at = datetime.now(UTC)
            return build_release_context(*row)

    def record(self, job_id, step, receipt):
        from pressroom.persistence import ReleaseJob, session_scope
        with session_scope(self.factory) as s:
            job = s.get(ReleaseJob, job_id, with_for_update=True)
            if job is None or job.pipeline_key != self.config.pipeline_key:
                raise LookupError('Confluence JOB not found')
            job.receipts = {**job.receipts, step: receipt}
            job.current_step, job.updated_at = step, datetime.now(UTC)

    def receipts(self, job_id):
        from pressroom.persistence import ReleaseJob
        with self.factory() as s:
            job = s.get(ReleaseJob, job_id)
            if job is None or job.pipeline_key != self.config.pipeline_key:
                raise LookupError('Confluence JOB not found')
            return dict(job.receipts)

    def fail(self, job_id, *, code, summary, unknown):
        from pressroom.persistence import ReleaseJob, session_scope
        with session_scope(self.factory) as s:
            job = s.get(ReleaseJob, job_id, with_for_update=True)
            if job is None or job.pipeline_key != self.config.pipeline_key:
                raise LookupError('Confluence JOB not found')
            job.status = 'unknown_reconcile' if unknown else 'failed_retriable'
            job.error_code, job.error_summary = code[:120], summary[:1000]
            job.updated_at = datetime.now(UTC)

    def complete(self, job_id, *, outcome):
        from pressroom.persistence import ReleaseJob, session_scope
        with session_scope(self.factory) as s:
            job = s.get(ReleaseJob, job_id, with_for_update=True)
            if job is None or job.pipeline_key != self.config.pipeline_key or job.status != 'processing':
                raise ValueError('JOB completion state mismatch')
            now = datetime.now(UTC)
            job.status, job.outcome, job.current_step = 'completed', outcome, 'public_readback_complete'
            job.completed_at = job.updated_at = now
            job.error_code = job.error_summary = None

    def publication_status(self, job_id):
        from sqlalchemy import select
        from pressroom.persistence import ReleaseJob, ApprovalCandidate, PublicationAttempt
        with self.factory() as s:
            status = s.scalar(select(PublicationAttempt.status)
                .join(ApprovalCandidate, ApprovalCandidate.attempt_id == PublicationAttempt.id)
                .join(ReleaseJob, ReleaseJob.approval_id == ApprovalCandidate.id)
                .where(ReleaseJob.id == job_id, ReleaseJob.pipeline_key == self.config.pipeline_key))
            if status is None:
                raise LookupError('Confluence publication attempt not found')
            return status

    def retry(self, job_ref):
        from sqlalchemy import select
        from pressroom.persistence import ReleaseJob, PublicationAttempt, ApprovalCandidate, session_scope
        if not re.fullmatch(r'JOB\d{4,}', job_ref):
            raise ValueError('exact JOB reference required')
        with session_scope(self.factory) as s:
            job = s.scalar(select(ReleaseJob).where(ReleaseJob.job_no == int(job_ref[3:]),
                ReleaseJob.pipeline_key == self.config.pipeline_key).with_for_update())
            if job is None or job.status != 'failed_retriable':
                raise ValueError('only failed_retriable JOBs can be retried; unknown needs reconcile')
            attempt_status = s.scalar(select(PublicationAttempt.status)
                .join(ApprovalCandidate, ApprovalCandidate.attempt_id == PublicationAttempt.id)
                .where(ApprovalCandidate.id == job.approval_id))
            if attempt_status != 'awaiting_confirmation':
                raise ValueError('only pre-dispatch failure can retry; active PUB needs reconcile, failed PUB needs new preview/approval')
            job.status, job.current_step = 'approved', 'retry_requested'
            job.error_code = job.error_summary = None
            job.updated_at = datetime.now(UTC)
