"""AIL run_once/reconcile lifecycle adapted to Confluence's existing workflow.

The injected bridge calls Pressroom PublicationWorkflow / recovery. Publication
is complete only after the destination adapter's remote readback has succeeded.
"""
from __future__ import annotations
from dataclasses import dataclass

from .config import ReleaseConfig
from .release_contract import ReleaseContext, validate_release_contract


@dataclass(frozen=True)
class WorkerResult:
    job_ref: str | None
    status: str
    step: str
    detail: str


class ReleaseWorker:
    def __init__(self, jobs, bridge, config: ReleaseConfig, *, runtime_guard=None, required_job_ref: str | None = None):
        self.jobs, self.bridge, self.config = jobs, bridge, config
        self.runtime_guard = runtime_guard
        self.required_job_ref = required_job_ref

    def run_once(self, job_ref: str | None = None) -> WorkerResult:
        return self._run(job_ref, reconcile=False)

    def reconcile(self, job_ref: str) -> WorkerResult:
        return self._run(job_ref, reconcile=True)

    def _run(self, job_ref, *, reconcile):
        if self.required_job_ref is not None and job_ref != self.required_job_ref:
            raise ValueError('relocated artifact worker requires its exact JOB')
        # As in current AIL, normal releases and presentation share this lock.
        if self.runtime_guard is not None:
            self.runtime_guard.assert_current()
        with self.jobs.site_lock() as acquired:
            if not acquired:
                return WorkerResult(job_ref, 'busy', 'claim', 'another site release holds the lock')
            if self.runtime_guard is not None:
                self.runtime_guard.assert_current()
            context = self.jobs.claim(job_ref, reconcile=reconcile)
            if context is None:
                return WorkerResult(job_ref, 'idle', 'claim', 'no eligible approved job')
            try:
                validate_release_contract(context, self.config)
                if self.runtime_guard is not None:
                    self.runtime_guard.assert_current()
                result = self.bridge.run(context, reconcile=reconcile)
                expected = 'published' if context.job_action == 'publish' else 'unpublished'
                if result != expected:
                    raise ValueError('destination did not reach the expected verified outcome')
                if self.runtime_guard is not None:
                    self.runtime_guard.assert_current()
                self.jobs.complete(context.job_id, outcome=expected)
                return WorkerResult(context.job_ref, expected, 'complete', 'here.now and Nor readback verified; see receipt comparison mode')
            except Exception as exc:
                # The bridge knows whether a mutating external call may have run.
                # Never label such a failure safe to retry just because its class
                # is a generic socket/DB exception rather than a vendor exception.
                unknown = self.bridge.may_have_delivered(context)
                self.jobs.fail(context.job_id, code=type(exc).__name__.lower(),
                               summary='release not finalized; inspect private step receipts', unknown=unknown)
                status = 'unknown_reconcile' if unknown else 'failed_retriable'
                return WorkerResult(context.job_ref, status, 'pipeline', type(exc).__name__)
