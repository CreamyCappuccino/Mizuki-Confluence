# Confluence renderer-owned HTML metadata (design v3)

Owner: Mizuki / ChatGPT
Date: 2026-10-18
Status: design baseline only — no code, runtime, JOB, or published-site changes in this document.

> “v3” identifies this design step, **not** a new `here-now-og/v3` transformation profile.

## 1. Users, purpose, and sufficient outcome

Ushio and the Confluence publication worker need to publish approved writings to the existing Here.now and Nor endpoints without designing a new HTML readback exception for each release.

The simplest normal flow is:

1. Pressroom supplies an approved Confluence publication snapshot.
2. Confluence builds one immutable site artifact. Its HTML already includes the basic page-specific Open Graph metadata.
3. The existing release worker publishes that artifact to the existing Here.now site, and Nor serves the corresponding public routes.
4. The existing readback verifies the delivered HTML and other files against the **same artifact bytes**. The normal release completes through the existing Pressroom JOB workflow.

This change is sufficient when routine future publications do not require a per-manifest five-/nine-meta exception and the published pages retain the current content, navigation, robots behavior, and release semantics.

## 2. Existing implementation and evidence

- `src/confluence_release/site_renderer.py`: `shell()` builds the shared head, while `render_pages()` knows whether the page is home, browse, writers, or an article. At `be6c7043`, Confluence does not author OG tags.
- `src/confluence_release/config.py`: `ReleaseConfig.site_base == nor_base` is the existing canonical-site contract; the Here.now origin is a separate delivery endpoint. Confluence keeps `noindex, nofollow, noarchive`.
- `src/confluence_pressroom/public_release_readback.py`: raw SHA-256 equality is **already the default** with `html_policy=None`. The optional HTML policy predicts one separately declared remote transformation only when bytes differ.
- `src/confluence_release/delivery.py`: publication/reconciliation, manifest pinning, artifact verification, guards, locks, and step receipts already exist.
- Reference, not a dependency: AIL's `src/ai_inner_life/public_site/layout.py:render_layout()` authors `og:title`, `og:description`, `og:type`, and `og:url` directly in HTML.
- The 2026-10-11 independent Here.now probe (TP1541; reported as RLY3177) observed raw-exact HTML for variants with pre-existing OG metadata, while the variant without OG tags gained provider-inserted metadata later. It supports this approach but does not guarantee behavior on every future provider version.
- The old `here-now-og/v2` implementation and the completed `JOB0154` recovery are documented in `docs/CONFLUENCE_HTML_TRANSFORM_V2.md`. They are historical evidence, not a pattern to extend for every new release.

## 3. Decisions

### 3.1 Confluence owns the generated metadata

Extend the existing renderer's head output; do not add a runtime HTML rewrite layer or require Pressroom to generate publication-site metadata.

For each real HTML page, emit one escaped, deterministic set of:

- `<meta name="description" ...>`
- `<meta property="og:title" ...>`
- `<meta property="og:description" ...>`
- `<meta property="og:type" ...>`
- `<meta property="og:url" ...>`
- `<link rel="canonical" ...>`

Keep the existing `<title>` and robots metadata. Site-wide metadata may use short fixed Confluence copy; an article uses its approved title and, if present, its approved excerpt. If an excerpt is absent, use a small site-owned fallback rather than parsing untrusted HTML to invent one. Escape all attribute values with the existing HTML escaping convention.

Use `og:type=article` for an article and `website` for index, browse, and writers. The page route is already known to `render_pages()`; pass the route and `ReleaseConfig` (or the validated canonical base) explicitly into the shell instead of inferring it from relative asset depth.

Build `og:url` and `canonical` from the **Nor canonical base** and the page's public route. The same original HTML bytes are then served through Here.now and Nor: there is **one canonical URL**, not a provider-origin-specific OG URL. Route/path encoding must follow the existing renderer's validated routing contract.

The first version does **not** add a mandatory OG image, auto-generated Here.now image URL, image dimensions, Twitter card, or nine-tag template. Those are not required to solve the observed problem. If there is a future editorial need for an image, design it from an owned asset rather than copying observed provider output.

### 3.2 Normal readback is already exact

For newly built renderer-owned-metadata artifacts, use the existing `verify_public_artifact(..., html_policy=None)` path: normal success means byte-exact HTML and other artifact files on both delivery origins, together with the existing manifest and removed/unknown-route checks.

Keep the existing checksums and frozen artifact as the independent expected source. Do not strip, normalize, or “learn” HTML from the delivered page. If Here.now unexpectedly rewrites author-authored metadata, report the mismatch using the existing uncertain/reconcile behavior; investigate it as a separate observed provider change, rather than silently teaching the checker another policy.

### 3.3 Preserve the completed historical release

Do **not** regenerate, mutate, re-upload, or rewrite the frozen artifact, checksums, source pin, policy profile, receipt, or canonical status of `JOB0154 / PUB0189 / APR0166 / ART0084-R01`. Its distinct `here-now-og/v2` manifest-bound policy remains available for inspecting/reconciling that historical release if needed.

The current Ops path is explicitly pinned to the recovered `JOB0154` and its policy/location. A new approved JOB must be able to reach the **normal** renderer and exact-readback path without inheriting that legacy pin. At implementation time, make the smallest existing-runtime routing/configuration change needed for new jobs; do not weaken the historical exact-JOB recovery path or build a generic policy registry.

### 3.4 Keep existing service ownership

- Confluence owns HTML head construction and the release artifact.
- Pressroom retains manuscript, approval, JOB, and publication state. No Pressroom DB/schema or approval-flow redesign.
- Here.now remains a publishing destination; Nor remains the canonical reader-facing base.
- HereNowRemote MCP is useful for owner-side inspection or independent site editing, **not** a substitute for a Confluence/Pressroom release. Do not use direct MCP writes to repair or mutate the same site while a canonical Confluence JOB owns the publication manifest.

## 4. Implementation slices

1. Adjust only the Confluence renderer's head and existing render call sites to pass description/type/route/canonical-base metadata. Keep the new helper small and local unless responsibility growth warrants a separate file.
2. Update renderer fixture(s) and focused metadata tests. Existing content/body, links, and layout should otherwise remain unchanged.
3. Keep new-job readback on the already implemented raw-exact default and adapt the minimal runtime selection so the old `JOB0154` policy applies only to its own recovery path.
4. Verify one newly built artifact end to end in an isolated or otherwise explicitly scoped non-destructive release test, including a settled remote readback after the interval in which provider insertion was previously observed. Then enable normal future JOBs through the existing release path.

This is an implementation sequence, not four new approval gates. Normal reversible code and test choices remain with the implementer; any live publication must use its existing authorized workflow.

## 5. Verification: capabilities versus examples

**Required product behavior**

- Head fields are authored before checksums are frozen, are deterministic and escaped, and match the page's title/type/canonical route.
- Both origins deliver the new HTML artifact byte-for-byte as expected; non-HTML bytes and the manifest remain exact.
- Current robots/noindex/noarchive behavior, unavailable sitemap, unknown-route behavior, and withdraw route checks remain unchanged.
- The old `JOB0154` remains published and its verified historical artifact/policy/receipt are unmodified.
- New approved publish/withdraw JOBs can use their own newly built artifact without inheriting `JOB0154`'s manifest-bound OG policy.

**Useful focused examples** (not an extra product-level checklist): home, browse, writers, one article with excerpt, one article without excerpt; quote/ampersand escaping; two-origin exact readback; reject a single modified HTML byte; stable snapshots before and after provider settling. Run existing relevant tests and record actual results in a separate changelog/receipt.

## 6. Exclusions and next stage

No UI redesign, new database, new approval layer, image pipeline, SEO-indexing change, cross-provider HTML normalization, direct HNR-powered canonical republish, or retroactive repair of completed JOBs.

Stage B (withdraw of the synthetic article) is **not** implemented by this design document. After the new ordinary release path is implemented and verified, Stage B uses its own approved withdrawal, newly frozen artifact and existing removed-path/404 verification. It must not borrow `JOB0154`'s old manifest/policy as authority.

## 7. Implementation reference

Current Confluence baseline: `CreamyCappuccino/Mizuki-Confluence`, main `be6c7043f489d9c1f21c4e6dc469bde55604e029` (checked 2026-10-18).

Design basis: Shared MN26 “Development — Design Principles” (minimal normal flow, proportional protections, distinguish product needs from test examples, no inherited approval proliferation); Shared MN19 “Development — Code Principles” (small responsibility boundaries and a short spec before complex changes).

No open product question blocks this design. The only uncertain external behavior is whether Here.now continues to leave author-authored OG metadata untouched; the limited probe supports it, and normal exact readback is the concrete check.
