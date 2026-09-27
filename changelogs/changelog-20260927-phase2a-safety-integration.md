# Phase 2A and release safety integration

Owner: Mizuki / ChatGPT. Date: 2026-09-27.

- Preserve both reviewed parents: Phase 2A c44725d9 and safety fcbf97d6.
- Re-export a single host lock and Git runtime guard; monitor both source packages.
- Wire private receipt inventory + pinned manifest + discovery checks into build,
  upload/recovery and exact two-origin readback. Default GETs reject redirects
  and bound response size; explicit test ports are still available.
- Check runtime through projection/build/upload/readback and before returning
  to canonical ledger/JOB completion. No double-lock or new approval engine.
- Existing PG probe now uses the real shared guard and integrated readback.
- Full local suite: 230 tests PASS (204 inherited + 26 wiring), compileall and
  stored renderer integrity PASS. Test-only port adjustments are documented;
  no test is removed or skipped.
- Offline CI is restricted to this integration branch (plus manual dispatch),
  uses read-only repository permissions, and stores public source/test evidence.
- Update current README/docs to distinguish reviewed parents from combined SHA.
- Final exact-SHA real renderer/host/isolated PG review is required before main.
  Production DB, registry, AIL, live credentials, hosting and manuscripts untouched.

Entry: docs/CONFLUENCE_PHASE2A_SAFETY_INTEGRATION.md.
