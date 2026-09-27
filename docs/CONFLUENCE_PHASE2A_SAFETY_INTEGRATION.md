# Phase 2A + release safety integration

2026-09-27. Owner: Mizuki / ChatGPT. Status: integration in progress, not merge/deployment approval.

## Parents and evidence

- Phase 2A: c44725d9dd962cf04d490fa4e227c5ce65623edd; RLY2926 / ERM000234: 161 tests and real isolated PG PUB/APR/JOB/reconcile/withdraw PASS.
- Safety: fcbf97d6dc8ec9614d2d8f75cca96eba10a6cb95; RLY2924 / ERM000233: 122 tests (79 shared + 43 safety) and helper smoke PASS.
- Their common base is d09e3b6b999bd4644054332aafa9d5980f3300e1. Preserve both parents and their original verification boundaries.

## Integration decisions

A file union is not enough. Use one host lock and one runtime guard implementation, exposing compatibility imports from confluence_release. Extend guard input coverage to both source packages, prototype and tools. Keep one lock around JOB claim through canonical ledger and JOB completion; do not nest the helper's synchronous wrapper around the existing worker.

Use the Phase 2A private BuildReceipt.checksums['checksums.sha256'] as the trusted manifest pin for the safety verifier. Preserve the existing whole-inventory check as well. Default external reads must use the bounded, no-redirect GET transport. Explicit injected test transports remain test-only. Preserve two delivery bases, removal checks, noindex and sitemap absence; do not silently enable the AIL host-owned robots exception.

Check runtime before projection/build, external effects, readback, return to canonical ledger finalization, and JOB completion. Failure after possible delivery stays unknown/reconcile; never rebuild or re-upload to hide uncertain outcomes.

## Acceptance

Run full combined discovery (expected baseline 161 + 43 = 204; confirm actual count) plus new wiring regressions. Run stored fixture integrity and compileall. A final exact SHA still needs the pinned Pressroom real renderer, host writer-profile preservation and fresh isolated PG owner probe. The probe must exercise the integrated safety path, not replacement fake safety functions. Hosting alone remains in-memory.

Main, production, dedicated hosting configuration, AIL and Pressroom sources are unchanged. No live credentials are read and no deployment is attempted. Dedicated here.now/Nor/projection setup remains UNKNOWN.
