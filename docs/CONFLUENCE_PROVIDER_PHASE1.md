# Confluence Pressroom provider — Phase 1 implementation

Status: implementation branch; private rehearsal only. No production destination registration or real manuscript publication is authorized by this document.

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

Readback verifies route, revision/payload markers, exact prepared article body, internal listings and sitemap absence. `lookup` can recognize a completed filesystem side effect even when a local operation receipt is absent, covering the external-success / ledger-finalization recovery seam.

Withdrawal removes both the body and all listing/search/browse references; the old article route must return 404 in the private HTTP smoke.

## Offline verification

New provider tests:

```sh
PYTHONPATH=src:tools python3 -m unittest tests/test_phase1_provider.py -v
```

At handoff: 30/30 new tests pass, including real-renderer seam normalization, deterministic payload hashing, internal discovery, no sitemap, same-key idempotency, body tamper readback, revision replacement, recovery lookup and HTTP 200 -> 404 withdrawal.

The existing 19 contract tests remain a separate gate, so the combined branch target is 49 tests once exercised from the repository checkout.

## Before main / before rehearsal

The branch must still be run against the actual local Pressroom checkout used for rehearsal:

1. existing 19 contract tests + new 30 provider tests;
2. `renderer/verify_fixture.py --rerender` from the pinned Pressroom environment;
3. `pressroom_adapter.py` import/signature compatibility with local Pressroom HEAD;
4. if available, a temporary/rehearsal DB + private temp staging prepare/dispatch/readback smoke.

No production DB, running destination registry, external URL or real manuscript is needed for these checks.
