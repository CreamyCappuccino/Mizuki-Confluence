# Explicit here.now HTML verification and immutable-release recovery

Owner: Mizuki / ChatGPT. Date: 2026-10-01.
Base: 06e2dade56543d2f0d2c0eeb6a94901b9a799849.

- Respond to the synthetic release's UNKNOWN readback, caused by observed
  provider-owned OG/Twitter insertion, without changing the stored release.
- Add an explicit immutable site/metadata/format profile with optional original
  manifest pin. Predict the sole alternate HTML document; never normalize away
  received changes. Default and all non-HTML readback remain raw exact.
- Wire the optional profile through the real worker/bridge/delivery path, retaining
  guards, lock, existing receipts, same-artifact reconcile and no implicit retry.
- Record raw/transformed comparison modes, separate digests and policy hash.
- Add owner-only profile loading and a bounded offline saved-file replay tool.
- Full local suite: 280 PASS (234 inherited + 46 new); compileall and stored
  renderer integrity PASS. Three safeguard-removal mutations detected.
- Four insertion-block hashes match the independently supplied saved evidence.
  Complete saved-file replay, actual local Pressroom review and live recovery
  are pending; no production success is claimed. Existing site/JOB untouched.

Entry: docs/CONFLUENCE_HTML_TRANSFORM_V1.md.
