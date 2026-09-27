# Phase 2A RLY2923 correction — host profiles and synthetic input

2026-09-27 · Mizuki / ChatGPT · base `a235b796`.

- Read the full RLY2923 result in ERM000232; do not call its 151-test PASS a
  durable-chain PASS: creation stopped before PUB/APR/JOB.
- Add the missing synthetic persona_key to the PG probe's draft request;
  preserve unknown model and use only refs returned by Pressroom.
- Forward the host's existing writer_profiles into PressroomToolCore without
  replacing other host services or changing the production core.
- Add 10 focused constructor/input regressions. All pass locally; independently
  reintroducing each defect makes the tests fail. Edited-file compileall passes.
- Full 161-test target, actual host profile operations, renderer replay and PG
  chain await the new exact-SHA reviewer run. No result is borrowed from the base.
- Main, the separate release-safety branch, production and hosting are unchanged.
  Hosting readiness remains UNKNOWN.

Restart / reviewer entry: `docs/CONFLUENCE_RLY2923_REVIEW.md`.
