"""Synthetic support for Phase 2 focused tests. No real PUB/APR/JOB or network."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from confluence_release.config import ReleaseConfig, digest
from confluence_release.projection import ProjectionArticle
from confluence_release.release_contract import ReleaseContext

CONFIG = ReleaseConfig('https://nor.example.invalid/confluence', 'synthetic-confluence',
                       'https://nor.example.invalid/confluence')
ID = UUID('00000000-0000-4000-8000-000000000001')
REV = UUID('00000000-0000-4000-8000-000000000002')


def payload(ref='ART99990001', number=1):
    return dict(schema_version='confluence.publication.v1', destination_key='confluence',
        manuscript_ref=ref, revision_ref=f'{ref}-R{number:02d}', revision_no=number,
        edition_ref=None, locale='ja', destination_ref=f'confluence:{ref}',
        destination_url=f'{CONFIG.site_base}/ja/articles/{ref.lower()}.html',
        title='合成記事 — 新しい窓', excerpt='これは接続試験専用です。',
        rendered_html='<h2 id="cf-example">合成見出し</h2><p>本文 &amp; 記録</p>',
        renderer_version='synthetic-test/v1', author_label='合成作者', authors=[dict(
            author_ref='AUT99990001', persona_name='合成作者', harness=None, model=None,
            role='primary', provenance_source='supplied')],
        category_paths=[['研究', '接続']], tags=['合成'], published_on='2026-09-27',
        content_updated_at=None, visibility='public')


def article(ref='ART99990001', number=1):
    p = payload(ref, number)
    return ProjectionArticle(ID if ref == 'ART99990001' else UUID(int=int(ID) + 10),
                             REV, p, digest(p))


def context(**changes):
    p = payload()
    c = ReleaseContext(job_id=UUID(int=3), attempt_id=UUID(int=4), job_ref='JOB99990001',
        approval_ref='APR99990001', publication_ref='PUB99990001',
        manuscript_ref=p['manuscript_ref'], revision_ref=p['revision_ref'], revision_no=1,
        manuscript_id=ID, revision_id=REV, destination_key='confluence',
        destination_capabilities=dict(publication_mode='durable_release', pipeline_key=CONFIG.pipeline_key),
        destination_config=CONFIG.public_config, attempt_action='publish', attempt_status='awaiting_confirmation',
        attempt_payload_sha256=digest(p), attempt_payload_snapshot=p,
        candidate_status='approved', candidate_payload_sha256=digest(p),
        candidate_pipeline_key=CONFIG.pipeline_key, candidate_action='publish',
        job_pipeline_key=CONFIG.pipeline_key, job_action='publish', approver=SimpleNamespace(name='合成実行者'))
    return replace(c, **changes)


def dispatch(c):
    return SimpleNamespace(attempt_id=c.attempt_id, attempt_ref=c.publication_ref,
        action=c.job_action, idempotency_key=str(c.attempt_id), manuscript_id=c.manuscript_id,
        revision_id=c.revision_id, destination_key=c.destination_key,
        payload_sha256=c.attempt_payload_sha256, payload_snapshot=deepcopy(c.attempt_payload_snapshot))


class FakeJobs:
    def __init__(self, c):
        self.c, self.saved, self.completed, self.failed, self.claimed = c, {}, [], [], 0
    @contextmanager
    def site_lock(self):
        yield True
    def claim(self, ref=None, *, reconcile=False):
        self.claimed += 1
        return self.c
    def record(self, job, step, data):
        self.saved[step] = deepcopy(data)
    def receipts(self, job):
        return deepcopy(self.saved)
    def complete(self, job, *, outcome):
        self.completed.append(outcome)
    def fail(self, job, **kwargs):
        self.failed.append(kwargs)


class ProjectionDouble:
    def __init__(self):
        self.rows = ()
    def replace_all(self, rows):
        self.rows = deepcopy(rows)
    def list_published(self):
        return deepcopy(self.rows)


def assets(root: Path):
    p = root / 'assets'
    p.mkdir()
    # Contract tests use tiny assets, not a claim of actual browser/UI testing.
    for name in ('styles.css', 'preferences.js', 'app.js', 'mark.svg'):
        (p / name).write_text('/* synthetic */', encoding='utf-8')
    return p
