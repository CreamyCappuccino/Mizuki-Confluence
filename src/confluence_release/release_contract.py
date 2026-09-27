"""Adapted from AIL pressroom/release_contract.py; article publish/withdraw only."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from .config import ReleaseConfig, digest


@dataclass(frozen=True)
class ReleaseContext:
    job_id: UUID
    attempt_id: UUID
    job_ref: str
    approval_ref: str
    publication_ref: str
    manuscript_ref: str
    revision_ref: str
    revision_no: int
    manuscript_id: UUID
    revision_id: UUID
    destination_key: str
    destination_capabilities: dict[str, object]
    destination_config: dict[str, object]
    attempt_action: str
    attempt_status: str
    attempt_payload_sha256: str
    attempt_payload_snapshot: dict[str, object]
    candidate_status: str
    candidate_payload_sha256: str
    candidate_pipeline_key: str
    candidate_action: str
    job_pipeline_key: str
    job_action: str
    approver: Any
    receipts: dict[str, Any] = field(default_factory=dict)


def build_release_context(job, candidate, attempt, binding, destination,
                          manuscript, revision) -> ReleaseContext:
    from pressroom.domain import Actor

    if (candidate.binding_id != binding.id or candidate.target_revision_id != revision.id
            or attempt.revision_id != revision.id or revision.manuscript_id != manuscript.id):
        raise ValueError('release identity mismatch')
    if not candidate.approver_name:
        raise ValueError('approved JOB is missing approver identity')
    ref = f'ART{manuscript.manuscript_no:04d}'
    return ReleaseContext(
        job_id=job.id, attempt_id=attempt.id, job_ref=f'JOB{job.job_no:04d}',
        approval_ref=f'APR{candidate.approval_no:04d}',
        publication_ref=f'PUB{attempt.publication_no:04d}',
        manuscript_ref=ref, revision_ref=f'{ref}-R{revision.revision_no:02d}',
        revision_no=revision.revision_no, manuscript_id=manuscript.id, revision_id=revision.id,
        destination_key=destination.key, destination_capabilities=dict(destination.capabilities),
        destination_config=dict(destination.public_config), attempt_action=attempt.action,
        attempt_status=attempt.status, attempt_payload_sha256=attempt.payload_sha256,
        attempt_payload_snapshot=dict(attempt.payload_snapshot), candidate_status=candidate.status,
        candidate_payload_sha256=candidate.payload_sha256,
        candidate_pipeline_key=candidate.pipeline_key, candidate_action=candidate.action,
        job_pipeline_key=job.pipeline_key, job_action=job.action,
        approver=Actor(name=candidate.approver_name, provider=candidate.approver_provider,
                       client=candidate.approver_client, model=candidate.approver_model,
                       session_ref=candidate.approver_session_ref),
        receipts=dict(job.receipts or {}),
    )


def validate_release_contract(context: ReleaseContext, config: ReleaseConfig) -> None:
    if context.destination_key != 'confluence':
        raise ValueError('release destination mismatch')
    if context.job_action not in {'publish', 'unpublish'}:
        raise ValueError('Phase 2A handles articles only')
    if not context.attempt_action == context.candidate_action == context.job_action:
        raise ValueError('release action mismatch')
    if context.candidate_status != 'approved':
        raise ValueError('release has no approved APR')
    if (context.candidate_payload_sha256 != context.attempt_payload_sha256
            or digest(context.attempt_payload_snapshot) != context.attempt_payload_sha256):
        raise ValueError('approved payload hash mismatch')
    if not context.job_pipeline_key == context.candidate_pipeline_key == config.pipeline_key:
        raise ValueError('release pipeline changed after approval')
    caps = context.destination_capabilities
    if caps.get('publication_mode') != 'durable_release' or caps.get('pipeline_key') != config.pipeline_key:
        raise ValueError('destination durable release contract changed')
    if context.destination_config != config.public_config:
        raise ValueError('destination configuration changed after approval')


def validate_reconcile_dispatch(context: ReleaseContext, dispatch) -> None:
    # Same identity invariants as AIL, plus recomputation of the approved hash.
    checks = ((dispatch.attempt_ref, context.publication_ref),
              (dispatch.action, context.job_action),
              (dispatch.manuscript_id, context.manuscript_id),
              (dispatch.revision_id, context.revision_id),
              (dispatch.destination_key, context.destination_key),
              (dispatch.payload_sha256, context.attempt_payload_sha256),
              (digest(dispatch.payload_snapshot), context.attempt_payload_sha256))
    if any(a != b for a, b in checks):
        raise ValueError('reconciled dispatch does not match approved JOB')
