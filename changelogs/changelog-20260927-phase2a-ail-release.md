# Phase 2A: AIL-derived Confluence release path

2026-09-27 · Mizuki / ChatGPT implementation. Confluence base `d09e3b6`.

- Adapted existing AIL contract/JOB/projection/artifact/here.now/readback patterns.
- Read current AIL local lock/guard/readback through read-only Relay; no code work
  was delegated to the Pressroom session.
- Added `confluence_release`: config, exact approval context, canonical authority
  reader, PostgreSQL projection, v0.2-based article builder, here.now transport,
  two-origin exact readback, runtime/host lock, worker and recovery composition.
- Reused existing Pressroom approval/workflow/recovery rather than inventing them.
- Added explicit host-composition seam and local CLI/example config.
- Preserved Phase 1 code, original prototype and private-content/public-code rule.
- Article `public` means site-internal listing; discovery remains discouraged.
- 72 focused new tests + compileall PASS; local HTTP checksum/404 PASS; Chromium
  search/expand/reset interaction PASS. External API calls and canonical JOBs
  are test doubles, not deployment evidence. Inherited 79 tests not rerun here.
- No production DB, registry, manuscript, here.now or Nor mutation occurred.

Next exact-code compatibility review and actual configured release execution:
`docs/CONFLUENCE_PHASE2A_IMPLEMENTATION.md`.
