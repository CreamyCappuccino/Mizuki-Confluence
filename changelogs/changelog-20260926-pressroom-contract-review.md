# 2026-09-26 — Confluence / Pressroom contract review gate

## Changed
- Added `docs/CONFLUENCE_PRESSROOM_CONTRACT_V1.md` after checking the
  Pressroom snapshot, destination/dispatch/ledger contracts, and review feedback.
- Added one synthetic article at
  `tests/fixtures/confluence/publication_v1.json`; fake IDs are offline-only.
- Added a standard-library offline payload/HTML-policy checker and 18 unit tests.
- Kept the visual v0.2 prototype and running Pressroom/AIL untouched.

## Why
Freeze the exact adapter field names and responsibility boundaries before
building or registering a destination. Keep candidate intent separate from
verified publication, and preserve hierarchical taxonomy and stable hashes.

## Verified here
- `python3 tools/validate_confluence_contract.py tests/fixtures/confluence/publication_v1.json`
- `python3 -m unittest discover -s tests -p 'test_confluence_contract.py' -v`
- 18 tests passed (with additional negative cases inside subtests).
- Contract-checker source files remain below 300 lines.
- No network, database, live manuscript, PUB/APR/JOB, or destination write was
  used by these checks. No lifecycle or browser verification is claimed.

## Next / review
The Pressroom maintainer should confirm the route/date choices, local contract
revision, provider composition, production sanitizer, and isolated staging
storage/transport. Then connect fixture rendering and implement the one-article
staging lifecycle. This commit is a review package, not a live publication GO.
