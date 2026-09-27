"""Explicit local operations for Confluence's existing Pressroom approval chain.

`plan` needs no credentials. `run` consumes approved JOBs; it never approves an
article. No service, migration, publishing, or credential read happens on import.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path

from .config import ReleaseConfig


@dataclass(frozen=True)
class LocalSettings:
    release: ReleaseConfig
    project_root: Path
    release_root: Path


def load_settings(path: Path) -> LocalSettings:
    values = json.loads(path.read_text(encoding='utf-8'))
    required = {'site_base', 'here_now_slug', 'nor_base', 'project_root', 'release_root'}
    if not isinstance(values, dict) or set(values) != required:
        raise ValueError('config fields: site_base, here_now_slug, nor_base, project_root, release_root')
    project = Path(values['project_root']).expanduser()
    release = Path(values['release_root']).expanduser()
    if not project.is_absolute() or not release.is_absolute():
        raise ValueError('project_root/release_root must be absolute local paths')
    return LocalSettings(ReleaseConfig(values['site_base'], values['here_now_slug'], values['nor_base']),
                         project.resolve(), release.resolve())


def _environment(name: str) -> str:
    value = os.environ.get(name, '')
    if not value:
        raise ValueError(f'{name} is required in the local process environment')
    return value


def _worker(settings: LocalSettings):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from .composition import create_release_worker
    from .here_now_client import HereNowClient, load_here_now_api_key
    engine = create_engine(_environment('CONFLUENCE_PRESSROOM_DATABASE_URL'))
    return create_release_worker(sessionmaker(engine, expire_on_commit=False),
        config=settings.release,
        projection_database_url=_environment('CONFLUENCE_PROJECTION_DATABASE_URL'),
        project_root=settings.project_root, release_root=settings.release_root,
        here_now_client=HereNowClient(load_here_now_api_key()))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('plan', help='read configuration only; no DB or network')
    sub.add_parser('init-projection', help='create Confluence projection schema in the explicit target DB')
    run = sub.add_parser('run', help='run one already-approved JOB')
    run.add_argument('job_ref', nargs='?')
    for action in ('reconcile', 'retry'):
        sub.add_parser(action).add_argument('job_ref')
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.config)
        if args.action == 'plan':
            print('Confluence Phase 2A | article publish/withdraw')
            print(f'pipeline: {settings.release.pipeline_key}')
            print('discovery: discouraged | approval: Pressroom APR | runtime: not started')
            return 0
        if args.action == 'init-projection':
            from .projection import PostgresProjectionStore
            PostgresProjectionStore(_environment('CONFLUENCE_PROJECTION_DATABASE_URL')).initialize_schema()
            print('projection: initialized | publication: not requested')
            return 0
        worker = _worker(settings)
        if args.action == 'retry':
            worker.jobs.retry(args.job_ref)
            print(f'{args.job_ref} | retry queued | not yet published')
            return 0
        result = (worker.reconcile(args.job_ref) if args.action == 'reconcile'
                  else worker.run_once(args.job_ref))
        print(f'{result.job_ref or "-"} | {result.status} | {result.step} | {result.detail}')
        return 0 if result.status in {'published', 'unpublished', 'idle', 'busy'} else 1
    except Exception as exc:
        # Connection errors may contain private connection strings. Keep CLI
        # diagnostics bounded; detailed receipts remain in the local JOB ledger.
        print(f'confluence-release: stopped | {type(exc).__name__} | check local configuration and private JOB receipts')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
