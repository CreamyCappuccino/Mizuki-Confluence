# Project-local storage and immutable-receipt location

Owner: Mizuki / ChatGPT. Baseline: 3c753eb7. Date: 2026-10-10.

- Keep the existing project root; relocate only the old Confluence local store.
- Add an explicit one-JOB/UUID/pipeline/receipt/manifest-pinned ArtifactLocation.
  Saved static_build and artifact bytes remain unchanged; only the in-memory
  physical locator changes. No symlink, fallback, DB rewriting or automatic build.
- Carry the location through CLI/factory/bridge/delivery, with exact JOB selection
  before claim and relocation evidence on later successful readback.
- Add filesystem-only plan/verified-copy/visible-rollback-archive operations; no
  DB, network, service or publication operations. Ignore private local roots.
- Tests cover unchanged old receipts, missing old path, content/path/identity
  failures, loader boundaries, real guard/readback and safe copy/archive.
- HTML policy and nine-meta STOP remain unchanged. Local deployment/pin updates,
  current JOB proof and real filesystem cutover remain a separate local receipt.

Entry: docs/CONFLUENCE_STORAGE_RELOCATION.md.

Cloud verification: Python 3.13.5, 319/319 full tests (280 inherited + 39 new),
compileall, stored renderer byte integrity PASS. Three safeguard-removal
mutations (receipt binding, relocated byte verification, copy verification before
archive) were detected; original source restored and all 39 focused tests passed
again. The source archive's baseline Git tree was independently reconstructed as
0ea8e3a2f9a7dfe80a5e099eec8d443ee2ccc96d, matching the 3c baseline.
These are cloud/local-temporary tests, not M4 cutover or real PG/provider success.
