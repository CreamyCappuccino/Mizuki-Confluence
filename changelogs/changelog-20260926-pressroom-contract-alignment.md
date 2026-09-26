# Confluence × Pressroom Phase 1 contract alignment

Date: 2026-09-26

## What changed

- Closed the design-review delta for Phase 1 before provider wiring.
- Changed article intent from `visibility=unlisted` to `visibility=public` **inside Confluence**.
- Separated site-wide external discovery from article visibility:
  - `external_discovery=discouraged`
  - `noindex, nofollow, noarchive`
  - no generated sitemap in Phase 1
- Kept draft/private writing outside the public projection; per-article unlisted remains a future feature.
- Clarified that `first_published_at` / `last_published_at` are private ledger evidence after successful readback/finalization and are not initial build/readback inputs.
- Added the real-renderer gate: synthetic Markdown must pass through the actual Pressroom renderer plus Confluence pre-PUB normalization/sanitization before the rehearsal candidate is frozen and hashed.
- Expanded acceptance to positive Confluence-internal listing/search/browse readback and negative draft/private/withdrawn/body readback.
- Updated the synthetic fixture, validator, README, and tests to the reviewed policy.

## Verification

```text
contract: valid | ART99990001 / ART99990001-R01
sha256: 1661b7c19f54c629e001895ce9b7e40fb1d5b9a27a380f2ae50a186e6bd3fa58
visibility: public | external discovery: discouraged
mode: fixture-only | DB/network/publication: not used

Ran 19 tests
OK
```

The checks are offline contract tests only. No destination registration, real DB mutation, PUB/APR/JOB, external transport, or real manuscript publication occurred.

## Next implementation boundary

Pin the actual Pressroom local dependency/provider composition, then build the real-renderer-derived prepared fixture and private rehearsal provider/staging path before the synthetic one-ART vertical slice.
