"""Explicit runtime composition, not automatic production registration.

Pressroom's existing preview/approval services remain the publication API.
The worker supplies only Confluence's destination implementation.
"""
from __future__ import annotations
from pathlib import Path

from .adapter import HereNowDestinationAdapter
from .artifacts import ReleaseBuilder
from .authority import CanonicalReleaseReader
from .delivery import ReleaseDelivery
from .job_store import ReleaseJobStore
from .projection import PostgresProjectionStore
from .readback import verify_public_artifact
from .worker import ReleaseWorker


class PublicationBridge:
    def __init__(self, factory, config, jobs, projection, builder, client, release_root, runtime_guard,
                 *, readback=verify_public_artifact):
        self.factory, self.config, self.jobs = factory, config, jobs
        self.runtime_guard, self.readback = runtime_guard, readback
        self.projection, self.builder, self.client, self.root = projection, builder, client, release_root

    def may_have_delivered(self, context):
        try:
            return ('here_now_started' in self.jobs.receipts(context.job_id)
                    or self.jobs.publication_status(context.job_id)
                    in {'publishing', 'unpublishing', 'published', 'unpublished'})
        except Exception:
            return True

    def run(self, context, *, reconcile=False):
        from pressroom.domain import PublicationDispatch
        from pressroom.services import PublicationWorkflow, PublicationManageInput
        from pressroom.services.publication_recovery import PublicationRecoveryCoordinator
        delivery = ReleaseDelivery(context, config=self.config, jobs=self.jobs,
            authority=CanonicalReleaseReader(self.factory), projection=self.projection,
            builder=self.builder, client=self.client, release_root=self.root, runtime_guard=self.runtime_guard,
            readback=self.readback)
        delivery.prepare(allow_build=not reconcile)
        if self.runtime_guard is not None:
            self.runtime_guard.assert_current()
        adapter = HereNowDestinationAdapter(self.factory, self.config, delivery=delivery)
        workflow = PublicationWorkflow(self.factory, (adapter,))
        expected = 'published' if context.job_action == 'publish' else 'unpublished'
        if context.attempt_status in {'publishing', 'unpublishing'}:
            result = PublicationRecoveryCoordinator(self.factory, (adapter,)).reconcile(context.publication_ref)
            if result.outcome != 'succeeded':
                raise RuntimeError('delivery still unresolved; no automatic re-publish')
            return expected
        if context.attempt_status == expected:
            dispatch = PublicationDispatch(attempt_id=context.attempt_id, attempt_ref=context.publication_ref,
                action=context.job_action, idempotency_key=str(context.attempt_id),
                manuscript_id=context.manuscript_id, revision_id=context.revision_id,
                destination_key='confluence', payload_sha256=context.attempt_payload_sha256,
                payload_snapshot=context.attempt_payload_snapshot, actor=context.approver)
            if adapter.lookup_dispatch(dispatch).outcome != 'succeeded':
                raise RuntimeError('completed publication lacks current readback evidence')
            return expected
        if context.attempt_status != 'awaiting_confirmation':
            raise ValueError('terminal failed PUB needs a new preview/approval; do not reset its ledger')
        request = PublicationManageInput(action=context.job_action,
            manuscript_ref=context.manuscript_ref, revision_ref=context.revision_ref,
            destination='confluence', expected_revision=context.revision_no,
            publication_ref=context.publication_ref, actor_name=context.approver.name, confirm=True)
        if context.job_action == 'publish':
            result = workflow.publish_approved(request, approver=context.approver)
        else:
            result = workflow.unpublish_approved(request, approver=context.approver)
        return result.state


def create_release_worker(session_factory, *, config, projection_database_url: str,
                          project_root: Path, release_root: Path, here_now_client):
    """Construct an explicit local worker; do not migrate, register, or publish."""
    from .runtime_guard import ReleaseRuntimeGuard
    guard = ReleaseRuntimeGuard.capture(project_root)
    jobs = ReleaseJobStore(session_factory, config, release_root)
    projection = PostgresProjectionStore(projection_database_url)
    builder = ReleaseBuilder(source_assets=project_root / 'prototype/assets',
                             config=config, source_commit=guard.source_commit)
    bridge = PublicationBridge(session_factory, config, jobs, projection, builder,
                               here_now_client, release_root, guard)
    return ReleaseWorker(jobs, bridge, config, runtime_guard=guard)
