# Explicit nine-meta readback, preserving relocated frozen artifacts

Date: 2026-10-10. Owner: Mizuki / ChatGPT.
Base: 3580a8cb3856d56fd6df25e1031e2fd2dc785b05.

- Read RLY3104's actual nine-meta findings, then independently obtained the exact
  nine-name order from saved observed-blocks.json via CX-MSG0337. The public docs
  do not specify this byte serialization; do not infer a provider-wide guarantee.
- Add the separate immutable HereNowImageHtmlPolicy / here-now-og/v2. Fix the
  nine tags/order/card; explicitly bind image URL to the configured site and pin
  dimensions and original manifest. No remote learning, image fetch or stripping.
- Preserve v1 fields/serialization/canonical hashes and raw-exact default.
  Version dispatch in the owner0600 loader; no global runtime-policy change.
- Reuse the actual factory/delivery/readback path and migrated ArtifactLocation.
  New tests require original receipt/bytes/source identity unchanged, no old-path
  fallback, no upload/build/projection replacement, and real guard/lock behavior.
- Full baseline 319 PASS, final full364 PASS (45 new), Python3.13.5; compileall and
  stored renderer integrity PASS. Four removed safeguards detected, restored and
  full suite rerun. Independent literal fixtures and synthetic byte mutations.
- Saved original/remote full-byte replay remains the local evidence gate; one
  new current delivery check remains necessary before any authorized recovery.
  No main/production/source pin/config/JOB/site/metadata mutation here.

Entry: docs/CONFLUENCE_HTML_TRANSFORM_V2.md.
