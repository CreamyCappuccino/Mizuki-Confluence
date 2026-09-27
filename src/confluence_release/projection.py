"""Disposable projection, following AIL PublicProjectionStore.replace_all.

Canonical editing/approval stays in Pressroom. This store contains frozen public
payloads only, and is fully replaceable from the release's authority snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from uuid import UUID

from .config import digest


@dataclass(frozen=True)
class ProjectionArticle:
    manuscript_id: UUID
    revision_id: UUID
    payload: dict[str, object]
    payload_sha256: str

    def validate(self) -> None:
        p = self.payload
        if (p.get('destination_key') != 'confluence' or p.get('visibility') != 'public'
                or p.get('schema_version') != 'confluence.publication.v1'):
            raise ValueError('non-Confluence/public payload in projection')
        ref, number = p.get('manuscript_ref'), p.get('revision_no')
        if (not isinstance(ref, str) or not re.fullmatch(r'ART\d{4,}', ref)
                or type(number) is not int or number < 1
                or p.get('revision_ref') != f'{ref}-R{number:02d}'):
            raise ValueError('projection revision identity mismatch')
        if digest(p) != self.payload_sha256:
            raise ValueError('projection payload hash mismatch')


def validate_projection(articles: tuple[ProjectionArticle, ...]) -> None:
    for a in articles:
        a.validate()
    for values in ([str(a.manuscript_id) for a in articles],
                   [a.payload['manuscript_ref'] for a in articles],
                   [a.payload['destination_url'] for a in articles]):
        if len(set(values)) != len(values):
            raise ValueError('duplicate projection identity or route')


def projection_digest(articles: tuple[ProjectionArticle, ...]) -> str:
    validate_projection(articles)
    return digest([a.payload for a in sorted(articles, key=lambda a: str(a.payload['manuscript_ref']))])


class PostgresProjectionStore:
    """Same atomic rebuild pattern as AIL; isolated schema, never AIL tables."""
    def __init__(self, database_url: str) -> None:
        if not database_url.startswith(('postgresql://', 'postgres://', 'postgresql+psycopg://')):
            raise ValueError('Confluence projection requires PostgreSQL')
        self._url = database_url.replace('postgresql+psycopg://', 'postgresql://', 1)

    def _connect(self):
        import psycopg
        return psycopg.connect(self._url)

    def initialize_schema(self) -> None:
        # Explicit setup only. Importing/constructing this store never migrates.
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute('CREATE SCHEMA IF NOT EXISTS confluence_public')
            cur.execute('''CREATE TABLE IF NOT EXISTS confluence_public.articles (
                manuscript_id uuid PRIMARY KEY, revision_id uuid NOT NULL,
                manuscript_ref text NOT NULL UNIQUE, revision_ref text NOT NULL,
                payload_sha256 text NOT NULL, payload jsonb NOT NULL)''')

    def replace_all(self, articles: tuple[ProjectionArticle, ...]) -> None:
        from psycopg.types.json import Jsonb
        validate_projection(articles)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute('LOCK TABLE confluence_public.articles IN EXCLUSIVE MODE')
            cur.execute('DELETE FROM confluence_public.articles')
            if articles:
                cur.executemany('''INSERT INTO confluence_public.articles
                    (manuscript_id,revision_id,manuscript_ref,revision_ref,payload_sha256,payload)
                    VALUES (%s,%s,%s,%s,%s,%s)''', [
                        (a.manuscript_id, a.revision_id, a.payload['manuscript_ref'],
                         a.payload['revision_ref'], a.payload_sha256, Jsonb(a.payload))
                        for a in articles])

    def list_published(self) -> tuple[ProjectionArticle, ...]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute('''SELECT manuscript_id,revision_id,payload,payload_sha256
                FROM confluence_public.articles ORDER BY manuscript_ref''')
            rows = tuple(ProjectionArticle(*r) for r in cur.fetchall())
        validate_projection(rows)
        return rows
