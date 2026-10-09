"""AIL build/deploy/readback steps, bound to an exact approved Confluence JOB."""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
from functools import partial

from confluence_pressroom.here_now_html import HereNowHtmlPolicy
from confluence_pressroom.release_checksums import MANIFEST

from .artifacts import BuildReceipt, verify_local_artifact
from .artifact_location import ArtifactLocation
from .projection import projection_digest
from .readback import verify_public_artifact
from .release_contract import validate_reconcile_dispatch


class ReleaseDelivery:
    def __init__(self, context, *, config, jobs, authority, projection, builder, client,
                 release_root: Path, readback=verify_public_artifact, runtime_guard=None,
                 html_policy: HereNowHtmlPolicy | None = None,
                 artifact_location: ArtifactLocation | None = None):
        self.context, self.config, self.jobs = context, config, jobs
        self.runtime_guard = runtime_guard
        self.authority, self.projection, self.builder = authority, projection, builder
        self.client, self.root = client, release_root
        self.html_policy = html_policy
        self.artifact_location = artifact_location
        self.readback = (readback if html_policy is None else
                         partial(readback, html_policy=html_policy))
        if not release_root.is_absolute():
            raise ValueError('release_root must be absolute')
        self.receipt = None

    def _assert_current(self):
        if self.runtime_guard is not None:
            self.runtime_guard.assert_current()

    def _check_profile(self):
        if self.html_policy is not None:
            self.html_policy.validate_scope((self.config.here_now_base, self.config.nor_base),
                                            self.receipt.checksums[MANIFEST])

    def check_dispatch(self, dispatch):
        validate_reconcile_dispatch(self.context, dispatch)

    def _record(self, step, value):
        self.jobs.record(self.context.job_id, step, value)

    def prepare(self, *, allow_build=True):
        self._assert_current()
        receipts = self.jobs.receipts(self.context.job_id)
        saved = receipts.get('static_build')
        if saved:
            if self.artifact_location is not None:
                self.receipt = self.artifact_location.locate(saved, self.context, self.root)
            else:
                self.receipt = BuildReceipt.from_record(saved)
                expected = self.root / str(self.context.job_id)
                if self.receipt.output != expected:
                    raise ValueError('stored artifact is outside its configured JOB directory')
                verify_local_artifact(self.receipt)
            self._check_profile()
            self._assert_current()
            return
        if self.artifact_location is not None:
            raise ValueError('artifact location requires an existing frozen receipt; never rebuild')
        if (not allow_build or 'here_now_started' in receipts
                or self.context.attempt_status != 'awaiting_confirmation'):
            raise ValueError('frozen artifact receipt missing; recover evidence, never rebuild an uncertain release')
        articles = self.authority.desired_articles(self.context)
        self._assert_current()
        self.projection.replace_all(articles)
        actual = self.projection.list_published()
        if projection_digest(actual) != projection_digest(articles):
            raise ValueError('projection differs from the approved authority snapshot')
        self._record('projection', {'content_digest': projection_digest(articles), 'articles': len(articles)})
        self._assert_current()
        self.receipt = self.builder.build(actual, self.root / str(self.context.job_id))
        self._record('static_build', self.receipt.as_record())
        self._check_profile()
        self._assert_current()

    @property
    def removed_paths(self):
        if self.context.job_action != 'unpublish':
            return ()
        url = str(self.context.attempt_payload_snapshot['destination_url'])
        prefix = self.config.site_base + '/'
        if not url.startswith(prefix):
            raise ValueError('withdrawn route differs from the configured destination')
        return (url[len(prefix):],)

    def perform(self, dispatch):
        self.check_dispatch(dispatch)
        if self.receipt is None:
            raise ValueError('immutable artifact was not prepared before ledger claim')
        verify_local_artifact(self.receipt)
        self._check_profile()
        self._assert_current()
        self._record('here_now_started', {'slug': self.config.here_now_slug,
                                         'content_digest': self.receipt.content_digest})
        self._assert_current()
        receipt = self.client.publish(self.config.here_now_slug, self.receipt)
        self._record('here_now', asdict(receipt))
        self._assert_current()
        evidence = self.readback(self.receipt, self.config, removed_paths=self.removed_paths)
        self._assert_current()
        if self.artifact_location is not None:
            evidence = dict(evidence, artifact_location=self.artifact_location.evidence())
        self._record('public_readback', evidence)
        # Last check before returning to PublicationWorkflow's ledger finalization.
        self._assert_current()

    def lookup(self, dispatch):
        self._assert_current()
        self.check_dispatch(dispatch)
        if self.receipt is None:
            return False
        verify_local_artifact(self.receipt)
        self._check_profile()
        receipt = self.client.reconcile(self.config.here_now_slug, self.receipt)
        if receipt is None:
            return False
        self._assert_current()
        evidence = self.readback(self.receipt, self.config, removed_paths=self.removed_paths)
        self._assert_current()
        self._record('here_now', asdict(receipt))
        if self.artifact_location is not None:
            evidence = dict(evidence, artifact_location=self.artifact_location.evidence())
        self._record('public_readback', evidence)
        self._assert_current()
        return True
