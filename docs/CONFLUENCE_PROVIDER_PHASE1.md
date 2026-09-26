# Confluence Pressroom provider — Phase 1 implementation

Status: RLY2890 corrections implemented; exact-SHA local integration recheck pending; private rehearsal only. No production destination registration or real manuscript publication is authorized by this document.

## Purpose

This layer turns a Pressroom manuscript revision into a frozen Confluence publication candidate, then projects that approved payload into an isolated static staging site with deterministic readback and withdrawal behavior.

Dependency direction remains:

```text
Confluence -> Pressroom
Pressroom -X-> Confluence
```

Pressroom remains the editorial/ledger authority. Confluence owns pre-PUB presentation normalization, routes, site-wide discovery policy, static projection, destination delivery and readback.

## Dependency evidence

The real-renderer handoff fixture is rooted at `tests/fixtures/confluence/renderer/` and was produced from:

- Pressroom local checkout `b5ce8d9422f0b90377145471bcb96f870e3e9263`
- md-converter local checkout `0d98198dd2da1abf82e4cf17c1bf8658027f021c`
- `md-converter 0.1.0`
- `markdown-it-py 4.2.0`
- `nh3 0.3.6`
- `PyYAML 6.0.3`

The Pressroom commit was local-only at review time, and the converter checkout had no origin remote. These identities plus resolved versions are rehearsal pins, not deployed-runtime attestation. `dependency_pin.py` deliberately reads the fixture provenance rather than pretending those sources can be fetched from public GitHub.

## Preparation boundary

`html_prepare.py` operates on already-sanitized Pressroom renderer output **before PUB**. It is not a replacement sanitizer.

It deterministically:

- assigns `cf-h-*` IDs to headings from normalized heading text;
- gives repeated heading text unique IDs;
- maps raw percent-encoded local Markdown fragments to the first matching heading;
- removes only the known renderer `rel="noopener noreferrer"` seam;
- retains validated absolute HTTPS links;
- fails closed on unsupported elements, attributes, links or unresolved fragments.

The prepared HTML and preparation-version marker enter the payload before the candidate is frozen and hashed. Dispatch never repairs or re-renders an approved payload.

## Provider core and adapter

`provider_core.py` is Pressroom-independent and owns deterministic candidate construction. It requires an explicit Confluence `published_on`; it does not invent current-clock publication metadata.

`canonical_reader.py` reads revision content and calls
`AuthorIdentityRepository.list_many((revision_ref,))` for exact-revision
attributions inside the same transaction. Only the six public author fields
are copied; standalone `manuscript_snapshot().authors` is not relied on.

`dispatch_validation.py` checks the canonical payload hash against the immutable
Pressroom dispatch before a file is written. Publish, withdrawal, and lookup
also check action, destination, exact revision UUIDs, and the configured route.
Lookup does not reject an old published revision merely because a new draft now
exists, but stale publish dispatch is still rejected. Missing withdrawal identity
evidence remains unknown; it is never inferred from the newest draft.

`pressroom_adapter.py` is the thin Pressroom-facing adapter. When composed with the pinned local Pressroom checkout it provides the existing durable-release shape:

- `prepare`
- `resolve_manuscript_id`
- `publish_dispatch`
- `unpublish_dispatch`
- `lookup_dispatch`

Direct `publish` / `unpublish` are rejected because Confluence uses the PUB -> APR -> JOB durable path.

## Private staging projection

`staging.py` requires an explicit absolute private output root. It writes no external URL and uses no network transport.

A verified publish produces:

- locale article detail page;
- Confluence-internal index listing;
- search JSON;
- category/tag browse projection;
- private operation receipts for idempotency/recovery.

Every HTML surface carries `noindex, nofollow, noarchive`; no sitemap is generated. Article `visibility=public` only means the verified article is listed/readable inside Confluence. Draft/private content never enters this projection.

Readback compares the complete article's UTF-8 bytes with deterministic output
from the approved payload, not a substring or a digest read from the artifact.
Index, search, and browse are independently compared with the expected projection
of all remaining articles. Browse therefore preserves shared taxonomy with the
correct counts. The same independent checks apply after withdrawal, along with
absence of the old detail route and sitemap. Read errors remain unknown. `lookup` can recognize a completed filesystem side effect even when a local operation receipt is absent, covering the external-success / ledger-finalization recovery seam.

Withdrawal consumes Pressroom's actual minimal unpublish dispatch payload (`operation_kind`, destination ref/URL, published revision UUID), not the original article payload. It removes both the body and all listing/search/browse references; the old article route must return 404 in the private HTTP smoke. The private staging history retains the approved display date so status/unpublish preview and later republish do not invent a new date.

## Offline verification

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m compileall -q src tools tests
python3 tests/fixtures/confluence/renderer/verify_fixture.py
```

The correction pass reran the original 19 contract + 35 provider tests and 25
new regressions: **79 tests pass**. The new adapter tests call Confluence's real
adapter with explicit Pressroom boundary doubles; they are not a DB integration
claim. Whole artifact append/tamper, each stale withdrawal surface, shared
category counts, exact authors, invalid dispatch hashes and UUIDs, operation-key
conflicts, and missing evidence are covered. Existing loopback HTTP 200 -> 404,
renderer-seam preparation, and date/idempotency regressions remain green.

Stored renderer fixture byte integrity and compileall pass. Actual rerendering
against the local Pressroom/converter environment must still be run separately.
See `CONFLUENCE_RLY2890_VERIFICATION.md` for evidence and the review checklist.

## Before main / before rehearsal

The Pressroom-side collaborator reviews the new exact SHA in the actual pinned
checkout. Confluence implementation remains the ChatGPT-side responsibility.
Recheck the 79 tests, real renderer `--rerender`, adapter import/signatures and
an isolated PG/private-staging reproduction of all four RLY2890 counterexamples.
Do not reuse PASS results for the old SHA. Main stays held until that evidence
is returned. A provider review PASS is not completion of the full APR/JOB durable
chain and is not production deployment authorization.

No production DB, running destination registry, external URL or real manuscript
is needed for this recheck.
