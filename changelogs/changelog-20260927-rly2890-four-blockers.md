# Confluence: close the four RLY2890 code defects

Date: 2026-09-27. Base: 8edc0c61. Author: Mizuki / Confluence ChatGPT side.

- Load exact-revision authors via AuthorIdentityRepository, not snapshot.authors.
- Verify the frozen dispatch hash before side effects; maintain action,
  destination, exact UUID/revision, route and operation-key checks in recovery.
- Compare each index/search/browse surface with remaining-state output after
  withdrawal; preserve shared taxonomy and verify absence of the detail page.
- Replace body-substring checks with exact full-artifact UTF-8 comparison.
- Split canonical reading, dispatch guards and readback into named modules.
- Preserve the renderer fixture, prototype UI, contract payload and main branch.

Verification in ChatGPT container: baseline 54 PASS; new counterexamples failed
before correction; corrected suite 79 PASS, compileall PASS, stored renderer byte
integrity PASS. Tests use explicit Pressroom doubles, not a production DB.

Next: Pressroom-side exact-SHA local rerender/PG negative-case recheck; main stays
held until that review. Confluence implementation is not delegated to Pressroom.
Details: docs/CONFLUENCE_RLY2890_VERIFICATION.md.
