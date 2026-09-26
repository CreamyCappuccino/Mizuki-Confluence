# Renderer handoff integrated into pre-PUB preparation

Date: 2026-09-27 (+08). Session: Mizuki / Confluence 1b.
Branch: integration/provider-rehearsal-v1; main intentionally unchanged.

- Integrates the original five-file renderer handoff at 56b3c3a without rewriting
  raw output. Formal supplements recovered through CX-MSG0233.
- Adds deterministic Japanese heading/fragment mapping (repeated labels → first
  matching heading; explicit IDs win) and narrow pre-PUB rel normalization.
- Shares a versioned lxml/libxml2 policy across configuration and preparation;
  validates canonical prepared bytes without repairing them after approval.
- Rejects malformed input and cross-manuscript prior-date reuse.
- Adds a read-only preparation-provider half plus an explicit local dependency
  gate. No fallback to the old GitHub Pressroom snapshot; no dependency upload.
- Adds a separate prepared renderer fixture and replay/check commands.
- 38 new unit tests and Python compilation PASS. Chromium fragment checks at
  390/1440 px PASS. Not a live renderer rerun, ledger chain, or HTTP readback.

Details, hashes, commands and remaining work:
`docs/CONFLUENCE_RENDERER_PREPARATION_V1.md`.

No DB, registry, real manuscript, production endpoint or main branch was changed.
Next: verify actual local dependency composition, then complete the recoverable
adapter/authority/projection/private-staging vertical slice.
