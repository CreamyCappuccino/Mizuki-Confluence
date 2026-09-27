"""Execute from an EMPTY dedicated local Pressroom PG harness, never production.

Adapted from AIL test_canonical_release_worker_worldline.py. Pressroom gateway,
renderer, PUB/APR/JOB, ORM and Confluence PostgreSQL projection are real. External
hosting is an explicit in-memory port double. Implementation: Mizuki / ChatGPT.
"""
from __future__ import annotations
from io import BytesIO
import json
from pathlib import Path
from urllib.error import HTTPError
from uuid import uuid4


def _require(condition, message):
    if not condition:
        raise AssertionError(message)


def _returned_ref(value):
    if isinstance(value, str):
        return _returned_ref(json.loads(value))
    if isinstance(value, dict):
        if isinstance(value.get('manuscript_ref'), str):
            return value['manuscript_ref']
        for child in value.values():
            if isinstance(child, (dict, list)):
                found = _returned_ref(child)
                if found:
                    return found
    if isinstance(value, list):
        for child in value:
            found = _returned_ref(child) if isinstance(child,(dict,list)) else None
            if found:
                return found
    return None


def _isolated_url(value):
    from sqlalchemy.engine import make_url
    url = make_url(value)
    _require(url.host in {'localhost','127.0.0.1','::1'}, 'probe requires loopback PostgreSQL')
    _require((url.database or '').startswith('confluence_phase2a_'), 'probe requires a dedicated confluence_phase2a_ database')


class _Response(BytesIO):
    status = 200


class MemoryHosting:
    """External transport double only; no sockets, DNS, credentials or deployment."""
    def __init__(self, config):
        self.config, self.files, self.upload_calls, self.lose_reply = config, {}, 0, True
    def publish(self, slug, receipt):
        from confluence_release.artifacts import read_files
        from confluence_release.here_now_client import HereNowOutcomeUnknownError, HereNowReceipt
        self.files = read_files(receipt.output)
        self.upload_calls += 1
        if self.lose_reply:
            self.lose_reply = False
            raise HereNowOutcomeUnknownError('synthetic lost finalize reply')
        return HereNowReceipt(slug, str(self.upload_calls), len(self.files), False)
    def reconcile(self, slug, receipt):
        from confluence_release.artifacts import read_files
        from confluence_release.here_now_client import HereNowReceipt
        if read_files(receipt.output) != self.files:
            return None
        return HereNowReceipt(slug, str(self.upload_calls), 0, True)
    def open(self, request, **kwargs):
        for base in (self.config.here_now_base,self.config.nor_base):
            prefix = base + '/'
            if request.full_url.startswith(prefix):
                path = request.full_url[len(prefix):]
                if path in self.files:
                    return _Response(self.files[path])
                raise HTTPError(request.full_url,404,'synthetic missing route',{},None)
        raise AssertionError('unexpected external URL in in-memory hosting port')


def _synthetic_create_request():
    """Build the probe's draft request without touching a DB or publication API.

    b5ce8d9 requires persona_key when author_ref is omitted. This synthetic key
    is local to the dedicated probe database; real refs still come from create.
    """
    from pressroom.domain import AuthorAttributionInput
    from pressroom.services import ManuscriptManageInput

    return ManuscriptManageInput(action='create',
        title='合成 Phase 2A publication probe', markdown='# 合成記事\n\n接続確認専用の本文です。',
        slug='confluence-probe-'+uuid4().hex, locale='ja',
        author=AuthorAttributionInput(persona_name='合成作者',
            persona_key='confluence-phase2a-probe', harness='Probe', model=None),
        actor_name='Confluence synthetic probe', format='json')


def run_probe(session_factory, manuscript_core, *, projection_database_url: str,
              project_root: Path, private_root: Path) -> dict:
    """Run real PUB->APR->JOB->unknown/reconcile->withdraw in supplied test PG.

    `manuscript_core` is the existing Pressroom host test core using THIS same
    session factory; it is not the running remote production MCP. No migrations
    of the canonical Pressroom schema or database drops are performed here.
    """
    from sqlalchemy import select,func
    from pressroom.domain import Actor
    from pressroom.persistence import Manuscript,ReleaseJob,PublicationAttempt
    from pressroom.services import ApprovalQueueService,PublicationManageInput,PublicationWorkflow
    from confluence_release.adapter import HereNowDestinationAdapter
    from confluence_release.artifacts import ReleaseBuilder
    from confluence_release.composition import PublicationBridge
    from confluence_release.config import ReleaseConfig
    from confluence_release.job_store import ReleaseJobStore
    from confluence_release.projection import PostgresProjectionStore
    from confluence_release.readback import verify_public_artifact
    from confluence_release.worker import ReleaseWorker

    with session_factory() as session:
        _isolated_url(session.get_bind().url)
        _require(session.scalar(select(func.count()).select_from(Manuscript)) == 0,
                 'probe requires an empty canonical manuscript database')
    _isolated_url(projection_database_url)
    _require(private_root.is_absolute(), 'private probe root must be absolute')
    config = ReleaseConfig('https://nor.example.invalid/confluence', 'synthetic-confluence',
                           'https://nor.example.invalid/confluence')
    reply = manuscript_core.manuscript_manage(_synthetic_create_request())
    ref = _returned_ref(reply)
    _require(ref is not None,'create must return its actual manuscript_ref')
    destination = HereNowDestinationAdapter(session_factory,config)
    workflow = PublicationWorkflow(session_factory,(destination,))
    queue = ApprovalQueueService(session_factory)
    preview = workflow.preview(PublicationManageInput(action='preview',manuscript_ref=ref,
        destination='confluence',destination_metadata={'published_on':'2026-09-27'},
        actor_name='Confluence synthetic probe'))
    candidate = queue.create_candidate(preview.publication_ref,pipeline_key=config.pipeline_key)
    job = queue.approve(candidate.approval_ref,actor=Actor(name='Synthetic test approval'))
    projection = PostgresProjectionStore(projection_database_url)
    projection.initialize_schema()
    jobs = ReleaseJobStore(session_factory,config,private_root)
    builder = ReleaseBuilder(source_assets=project_root/'prototype/assets',config=config,
                             source_commit='synthetic-probe-source')
    hosting = MemoryHosting(config)
    def readback(receipt,settings,**kwargs):
        return verify_public_artifact(receipt,settings,opener=hosting.open,**kwargs)
    bridge = PublicationBridge(session_factory,config,jobs,projection,builder,hosting,
                               private_root,None,readback=readback)
    worker = ReleaseWorker(jobs,bridge,config)
    first = worker.run_once(job.job_ref)
    _require(first.status=='unknown_reconcile','lost reply must remain unknown')
    with session_factory() as session:
        stored = session.scalar(select(ReleaseJob).where(ReleaseJob.id==job.job_id))
        _require(stored.status=='unknown_reconcile','JOB must not complete early')
    recovered = worker.reconcile(job.job_ref)
    _require(recovered.status=='published','exact frozen artifact must reconcile')
    _require(hosting.upload_calls==1,'reconcile must not reupload')
    _require(workflow.status(ref,'confluence').state=='published','canonical publish missing')
    _require(len(projection.list_published()[0].payload['authors'])==1,'exact author lost')

    withdrawal = workflow.preview_unpublish(PublicationManageInput(action='unpublish_preview',
        manuscript_ref=ref,destination='confluence',actor_name='Confluence synthetic probe'))
    removal = queue.create_candidate(withdrawal.publication_ref,pipeline_key=config.pipeline_key)
    removal_job = queue.approve(removal.approval_ref,actor=Actor(name='Synthetic test approval'))
    result = worker.run_once(removal_job.job_ref)
    _require(result.status=='unpublished','withdrawal did not finalize')
    _require(workflow.status(ref,'confluence').state=='unpublished','binding still published')
    _require(f'ja/articles/{ref.lower()}.html' not in hosting.files,'old route still served')
    _require(not projection.list_published(),'projection still contains withdrawn article')
    for name in ('index.html','search.json','browse.html'):
        _require(ref.encode() not in hosting.files[name],'withdrawn identity remains in a surface')
    return {'scope':'real isolated PG/PUB/APR/JOB; in-memory hosting, not deployment',
            'manuscript_ref':ref,'publication_ref':preview.publication_ref,
            'approval_ref':candidate.approval_ref,'job_ref':job.job_ref,
            'withdrawal_job_ref':removal_job.job_ref,'result':'PASS'}
