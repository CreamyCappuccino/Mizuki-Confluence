# Confluence Phase 1 provider implementation

Date: 2026-09-27

## Added

- incorporated the real Pressroom renderer handoff fixture from `56b3c3a`;
- deterministic pre-PUB heading/fragment normalization for current renderer output;
- public-safe deterministic publication payload construction;
- Pressroom-independent provider core plus thin durable-release adapter;
- isolated filesystem staging with index/search/browse/detail projection;
- site-wide external-discovery suppression (`noindex, nofollow, noarchive`, no sitemap);
- idempotent publish/unpublish receipts and readback/recovery checks;
- revision replacement and full withdrawal from article/listing surfaces.

## Verification in ChatGPT workspace

- `python3 -m compileall`: pass
- new provider suite: **30 tests pass**
- private HTTP smoke: article 200 before withdrawal, 404 after withdrawal; sitemap 404
- no production DB, destination registry, external transport or real manuscript used

The existing 19 contract tests were not re-run in this isolated workspace because only the new implementation slice was materialized locally. The integration branch contains both suites; local Pressroom review is requested before main fast-forward.

## Remaining gate

Run the combined suite and real renderer replay against Pressroom local `b5ce8d9...`, then verify adapter contract compatibility and a temp-DB/private-staging smoke. If that gate passes, fast-forward main; real PUB/APR/JOB with returned synthetic ART refs remains a separate rehearsal step.
