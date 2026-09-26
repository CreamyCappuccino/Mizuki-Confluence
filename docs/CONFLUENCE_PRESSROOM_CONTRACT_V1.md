# Confluence × Pressroom — Phase 1 contract v1

Status: **design-aligned Phase 1 baseline; offline fixture checks implemented; provider/rehearsal wiring pending**.
Date: 2026-09-26. Frontend baseline: `CONFLUENCE_VISUAL_V02.md`.

## 1. Scope and ownership

The first milestone is one synthetic article through a Confluence staging
destination, including revision, retry/recovery, and withdrawal. It is not
permission to publish real manuscripts or change the running Pressroom/AIL.

Pressroom remains the editorial authority: manuscripts, immutable revisions,
authors/provenance, taxonomy, PUB attempts, APR approvals, JOBs, and bindings.
Confluence owns its provider, payload/projection version, routes, static
presentation, destination delivery, and readback. Dependency direction is
`confluence -> pressroom`, never the reverse. Do not copy the AIL backend or
make a display JSON file a second editable manuscript database.

This commit implements the **contract + fixture review gate only**. It does not
implement or claim the PUB/APR/JOB vertical slice described in section 7.

## 2. Sources actually checked

Pinned GitHub source snapshots (not proof of the currently deployed runtime):

- `CreamyCappuccino/CodexMizuki-Pressroom@5b278d825b383a074b8a24b0f8ccce85ab480f1b`
  - `README.md`, `src/pressroom/destinations/contracts.py`
  - `src/pressroom/domain/{manuscripts,publications,authors,responses}.py`
  - `src/pressroom/persistence/publication_models.py`
  - `src/pressroom/services/{publication_ledger_service,publication_recovery}.py`
- `CreamyCappuccino/CodexMizuki-AI-InnerLife@a0e807a72308b904091ab29266b3e205f5ba6c9a`
  - `src/ai_inner_life/pressroom/public_projection_payload.py`
- Confluence visual baseline: `4782188be55ac6600d0514a0371f9306f185749b`.

The Pressroom maintainer's review supplied the corrections reflected here.
Before live integration, confirm these shapes against the maintainer's **local**
checkout. The checked `ResponseRecord` has no `parent_response_ref`, and the
checked AIL tree has no `public_author.py`; these may be newer local work.
Neither absence blocks the Phase 1 text-article fixture.

## 3. Adapter and identity contract

Proposed registration: key `confluence`, adapter kind `confluence-static`,
`publication_mode=durable_release`, pipeline key `confluence-staging-v1`,
preview/publish/unpublish enabled, `external_side_effect=true`, two-step approval
required. The approved destination configuration also pins the site-wide discovery
policy: `external_discovery=discouraged`, HTML robots hint
`noindex, nofollow, noarchive`, and sitemap generation disabled. This site policy
is separate from article visibility; it discourages external discovery without
turning published Confluence entries into per-article unlisted content.

Use an isolated rehearsal DB/registry for staging, not a second `confluence`
binding in the running production registry. Staging transport, private output
location, and provider composition must be agreed before enabling this
registration; no default production endpoint is installed. Freeze and verify
the destination base/pipeline/site-policy identity so a staging approval cannot
be retargeted to production by changing configuration.

Implement the existing `RecoverableDestinationAdapter`, including `prepare`,
`publish_dispatch`, `unpublish_dispatch`, and `lookup_dispatch`. The Confluence
provider resolves Pressroom internal manuscript/revision UUIDs for
`PreparedPublication`; they do not belong in the public payload.

Stable projection identity is `(destination_key, manuscript_ref)`.
`PUB` identifies an attempt, not a binding. `binding_id` is internal ledger
identity and is not a required `PublicationDispatch` input. Use the existing
`dispatch.idempotency_key`, not a newly invented JOB key.

Proposed Phase 1 route:
`{configured_site_base}/{locale}/articles/{lowercase_manuscript_ref}.html`.
`destination_ref = "confluence:" + manuscript_ref`. No title-derived slug.
An edit keeps its route; a new language edition has its own ART. A locale/route
change is a migration decision, not something dispatch silently rewrites.
The site base is trusted provider configuration, checked against the candidate.

## 4. Prepared payload — not a publication result

`payload_snapshot` is Confluence-owned JSON with an explicit allowlist.
The fixture in `tests/fixtures/confluence/publication_v1.json` is the exact
proposed example. It is **not** a serialized whole `ManuscriptSnapshot` or
`PublicationDispatch`.

| Field | Source / rule |
| --- | --- |
| `schema_version` | Confluence constant `confluence.publication.v1` |
| `destination_key` | `confluence` |
| `manuscript_ref`, `revision_ref`, `revision_no` | Exact selected ART / ART-R / integer; verify consistency |
| `edition_ref`, `locale` | Snapshot; EDN may be null, initially `ja` or `en` |
| `destination_ref`, `destination_url` | Confluence routing, frozen before preview approval |
| `title` | Selected revision's plain text |
| `excerpt` | Nullable snapshot text; null/missing content renders as an empty preview line, not generated prose |
| `rendered_html`, `renderer_version` | Prepared publication HTML and its renderer version; no frontend Markdown conversion |
| `author_label` | Nullable public display label |
| `authors` | Public-safe attribution list described below; may be empty |
| `category_paths` | Nested arrays of path components; retain hierarchy; may be `[]` |
| `tags` | String array; may be `[]` |
| `published_on` | Explicit, frozen Confluence display date, `YYYY-MM-DD` |
| `content_updated_at` | Exact revision's content update time, offset ISO8601 or null |
| `visibility` | Phase 1 article listing/access intent: `public` only; readable without authentication and included in Confluence's own index/search/category/tag/reply surfaces once the Confluence binding is verified published. External discovery is controlled separately by destination site policy. |

All keys are present, including nullable ones. Unknown fields require a contract
change. No raw Markdown, actor, session reference, source path, binding UUID,
credentials, arbitrary metadata, or cross-destination `is_published` is copied.

Each `authors[]` item has exactly `author_ref`, `persona_name`, `harness`, `model`,
`role`, `provenance_source`, selected from the revision's attributions. Preserve
known provenance, use null for unknown harness/model, and never substitute the
publishing actor for the author. A future provider must apply the public-field
policy before constructing this list. Row UI shows only the display author/date;
harness/model are not additional row columns.

Taxonomy names are the existing wire representation, not stable IDs. Do not hash
display names into permanent identity or discard parent categories. Any future
UUID mapping is an explicit extension. If excerpt is absent upstream, map to null.
`author_label` null falls back to public persona names; an empty author set stays
unattributed rather than inventing a writer.

### Dates and hashes

For first publication, require a Confluence-specific `published_on` in the
provider's destination metadata. Do not silently inherit AIL publication dates.
On revision/republish, reuse the previously approved display date unless a new
explicit date is approved. This is an editorial display date, **not** a claim of
the time at which a new Confluence publication succeeded.

Actual Confluence `first_published_at` / `last_published_at` come from its own
successful ledger history and stay in private receipt/ledger evidence during
Phase 1. They are **not** required by the initial static build or delivery
readback, because they are only authoritative after successful destination
readback and ledger finalization. If a later public metadata schema exposes them,
that requires an explicit re-projection step rather than a circular requirement
on the first publish. Neither replaces `content_updated_at`.
Display timezone is a site setting, initially `Asia/Taipei`; timestamps retain
their offsets. Scheduling / `publishable_at` is not part of Phase 1.

Freeze the payload at PUB. Hash with Pressroom's encoding:
UTF-8 JSON, `ensure_ascii=False`, `allow_nan=False`, `sort_keys=True`,
`separators=(",", ":")`, then SHA-256. Dispatch verifies the approved hash and
exact revision. Never insert the current clock, re-render Markdown, or silently
sanitize/rewrite HTML after approval to make dispatch "work".

### HTML and asset boundary

The provider sanitizes and resolves content **before** PUB, under a versioned
policy. Candidate HTML is a balanced fragment using ordinary prose, headings,
lists, quotes, code, and tables. No scripts, handlers, inline styles, forms,
iframes, SVG/MathML, embedded executable objects, or arbitrary attributes.

Phase 1 supports absolute HTTPS links without credentials and validated local
`#cf-...` fragments. Relative links must be resolved/validated by the provider
before preview; unresolved links fail preparation. Embedded images are deferred
until an explicit asset resolver exists. This is a Phase 1 scope limit, not a
permanent ban on article images and not a requirement for post thumbnails.

`tools/contract_html_policy.py` is an offline fixture checker, **not** the
production sanitizer or a proof of comprehensive browser/XSS safety.
The production sanitizer and prepared output must be reviewed in the live
provider integration; unsupported markup must fail closed rather than silently
changing an already-approved payload.

## 5. State and visibility authority

| Observed condition | Confluence treatment |
| --- | --- |
| Draft, preview, APR, queued/running JOB | Not evidence of publication; keep candidate private |
| `never_published` binding | No publicly readable entry |
| `published` binding with matching revision and successful Confluence evidence | Eligible for current projection |
| `unpublished` binding | Remove from index/search/detail; old URL must not expose the body |
| Delivery result unknown | Reconcile exact dispatch; do not blindly publish again |

`visibility=public` is the Phase 1 **Confluence-internal listing/access intent**,
not a claim that publication has already succeeded and not permission to promote
the site externally. Once the Confluence binding is verified `published`, the
entry is readable without authentication and is eligible for Confluence's own
top/index, search, category, tag, archive, and reply-related surfaces.

External discovery is a separate site-wide destination policy:
`external_discovery=discouraged`, `noindex, nofollow, noarchive`, and no generated
sitemap in Phase 1. These are crawler/discovery controls, not authentication or
secrecy guarantees; external links or noncompliant crawlers can still reveal a
URL. Draft/private writing is excluded from the public projection entirely.
A future per-article `unlisted` mode may mean direct-URL readable but omitted from
Confluence listings, but it is intentionally not implemented in Phase 1.

The candidate contains no premature `state=published`. AIL's binding and
snapshot-wide `is_published` never decide Confluence visibility.

Staging candidates/artifacts stay outside public Git and public feeds. Build
and delivery evidence precede Pressroom success finalization. Reconcile the
interval between external delivery and ledger commit; don't claim atomicity
across a remote site and the database.

## 6. Readback, recovery, and withdrawal

Key an operation by the existing idempotency key and verify its action, ART,
revision, destination and payload hash. Retrying the same operation must not
create another article or restamp its dates. A key with different input fails.
Serialize writes per binding and reject superseded work before activation.

Readback checks the delivered route and expected revision/payload **plus the
actual deployed artifact/body**, not merely an echoed success flag or copied
JSON marker. Generated manifest/file digests and route checks must agree with
the approved candidate. For a verified published `visibility=public` entry,
acceptance also requires positive presence in Confluence's own listing/search/
browse projection; draft/private/withdrawn entries require negative readback for
both body and listing surfaces. Site output must preserve the approved discovery
policy (`noindex, nofollow, noarchive`) and must not generate a sitemap in
Phase 1. Keep operational evidence private.

`lookup_dispatch` uses existing outcomes `succeeded`, `failed`, `unknown`.
An unavailable URL or a timeout alone is not definitive absence/failure.
For unknown delivery outcomes, reconcile before repeating the side effect.

Withdrawal removes the entry from every projection surface (including search,
archive/taxonomy and the old detail URL). A removed/tombstone page has no old
body. Verify those routes before marking the attempt successful. If withdrawal
readback is uncertain, keep the outcome unresolved; do not mark it complete.

## 7. Implementation order and acceptance gate

1. **Contract gate complete:** keep this spec, synthetic fixture, and offline
   validator aligned with the reviewed route/date/visibility/discovery policy.
2. Pin the actual local Pressroom dependency revision and Confluence provider
   composition; keep the local checkout identity distinct from deployed-runtime
   proof. Freeze staging storage/transport and the destination base/pipeline/site
   policy in the approved configuration.
3. Pass synthetic Markdown through the **real Pressroom renderer** and the
   Confluence provider's pre-PUB normalize/sanitize/link policy. If heading IDs
   or fragments change, update local links before the candidate is frozen. Hash
   this prepared renderer-derived HTML; the offline `HTMLParser` remains only a
   fixture checker, never the production sanitizer.
4. Connect isolated fixture/renderer-backed detail plus Confluence-internal
   listing/search/browse projection without replacing the v0.2 visual baseline
   or pretending its ten sample articles are production data. Verify site-level
   noindex policy and sitemap non-generation separately from article visibility.
5. Implement the Confluence provider, prepared payload, recoverable dispatch,
   versioned projection/static builder, and private staging readback.
6. In an isolated rehearsal environment, create/import one synthetic ART using
   real returned refs, then `preview/PUB -> APR -> JOB -> staging -> readback`.
   The first build/readback depends only on approved `published_on` and
   `content_updated_at`; actual successful ledger timestamps finalize afterward.
7. Exercise same-key retry, external-success/ledger-failure unknown recovery,
   one revision, stale work, and unpublish including the old route and every
   listing/search/browse surface. Inspect actual ledger outcomes.

The repository fixture uses syntactically shaped fake ART/AUT IDs solely for
offline checks. They are **not reserved IDs** and must never be looked up in a
live DB. The real rehearsal replaces them with refs returned by Pressroom and
gets its own exact approval; the fixture is not a ready-made authorized dispatch.

Phase 2 adds related writings and RSP replies. Keep `target_revision_ref`
explicit. Confirm the live `parent_response_ref` mapping before implementation.
Counts/latest-reply sorting use only Confluence-visible RSPs for the selected
revision; cross-revision display is a separate policy to agree. No PV/trending,
anonymous posting endpoint, or independent discussion forum is introduced.

## 8. Reproduce the offline checks

```sh
python3 tools/validate_confluence_contract.py tests/fixtures/confluence/publication_v1.json
python3 -m unittest discover -s tests -p 'test_confluence_contract.py' -v
```

These commands need only Python's standard library, no network, secrets,
Pressroom installation, or DB. Passing them does **not** prove registration,
approval, JOB execution, publish, withdrawal, readback, or browser rendering.
The fixture envelope is testing metadata; it is not the dispatch wire format.
