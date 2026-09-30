# Declared here.now HTML transformation and frozen-artifact recovery

Owner: Mizuki / ChatGPT. Date: 2026-10-01.
Baseline: `06e2dade56543d2f0d2c0eeb6a94901b9a799849`.
Status: implemented and locally verified; exact-SHA local review and live recovery pending.

## Evidence and decision

RLY3031 (ERM000268 / CX-MSG0297) reports that JOB0154 uploaded the approved
ART0084-R01 artifact once. Both origins serve it, but PUB0189 is `publishing`
and JOB0154 is UNKNOWN because delivered HTML differs from its frozen bytes.
The reported difference is exactly five OG/Twitter meta elements immediately
before `</head>`; `og:url` varies with the requested origin/path. Styles match.
This is an observed site behavior, not a promise that all here.now HTML behaves
this way. The public API docs do not specify this exact injection serialization.

Do NOT strip arbitrary meta tags or normalize the received document. Instead,
compute a second expected representation from the independently verified local
original and an explicitly authorized, immutable site profile. Accept remote
bytes only if they equal the original or this single predicted representation.
Preserve the original manifest, private BuildReceipt, PUB/APR/JOB identities,
content/pipeline hashes, and provider version. Do not fix UNKNOWN by rebuilding,
reuploading, rewriting ledger rows, or changing the site's metadata.

## Trust and profile boundary

Raw exact is the default. An optional `here-now-og/v1` profile specifies both
normalized HTTPS delivery bases, the literal title and description, and exact
ASCII whitespace surrounding/separating the five tags. Type is fixed `website`;
Twitter card is fixed `summary`. URL is constructed from the configured origin
and the requested artifact-relative path, NEVER from remote meta or headers.
All other metadata, attributes, ordering, byte changes and locations are rejected.

The profile is operator-authorized configuration, not content from the remote
site or a replacement for the approved artifact. It is loaded once from an
owner-owned 0600 regular file, frozen in memory, and SHA-256 recorded in the
readback receipt. An optional `expected_manifest_sha256` pins a recovery profile
to one specific original manifest. A base mismatch fails before worker construction; a manifest-pin mismatch
fails during preparation, before provider lookup/upload or HTTP readback. No profile is auto-created, auto-learned or auto-enabled.

This explicitly revises the transport verification policy; it is NOT a claim
that delivered HTML is byte-identical to the upload. It does not alter the
approved article/target. The policy hash and separate raw versus transformed
file digests must remain visible in private operational evidence.

## Deterministic comparison

1. Run all existing local inventory, manifest-pin, file-size and discovery checks.
2. With a profile, validate its two bases and optional manifest pin against the
   current request. Hold the verified original HTML bytes, not mutable paths.
3. Only HTML files with one actual head/closing-head pair, no existing OG/Twitter
   meta, and an unambiguous literal lowercase `</head>` can use the alternate
   representation. Non-HTML files and the checksum manifest stay raw exact.
4. Render exactly the five fixed tags with escaped profile values and exact URL,
   insert them before the actual closing head without changing any other byte,
   and compare the full received bytes. No received HTML is reserialized.
5. Preserve both-origin, removed/unknown-route 404, noindex/no-sitemap, bounded
   no-redirect HTTP, runtime guards, lock, and finalization ordering.
6. Evidence names the comparison mode honestly, including per-HTML original and
   delivered SHA-256 and profile hash. Failure stays UNKNOWN/reconcile.

Profile formatting must be taken from independently saved evidence and reviewed
before activation. A JSON example is illustrative, not the live site's receipt.

## Wiring and recovery

The safety verifier and release bridge take an optional profile. The normal
worker factory receives it through an explicit keyword. The CLI accepts
`--html-policy FILE` for plan, exact-JOB run, and reconcile; it is not an implicit
fallback and is not used by retry or schema initialization.

Before live recovery, the Pressroom reviewer/M4 operator must independently
replay the saved original and both saved remote files, validate the current
JOB/PUB/provider version and manifest, and activate the reviewed code pin through
the established Ops entry. Updating the executing code pin must not rewrite the
old artifact's source_commit or change its hashes. Keep the real runtime guard.

Recover JOB0154 through same-artifact reconcile only. Confirm no PUT/POST upload,
no builder/projection replacement, unchanged manifest and content hash, and an
honest `public_readback` receipt before canonical/JOB completion. Only then create
a separately approved withdrawal JOB and verify old route and listing removal.
A manifest-pinned recovery profile must not be reused for the withdrawal's new
manifest; authorize its profile/receipt explicitly. No actual manuscripts.

Implementation ownership remains with ChatGPT; local reviewers provide evidence,
run tests, and perform authorized operational recovery, not unreviewed hot fixes.

## Local profile example (illustrative, NOT activated)

```json
{
  "format": "here-now-og/v1",
  "here_now_base": "https://synthetic-confluence.here.now",
  "nor_base": "https://nor.example.invalid/confluence",
  "title": "Confluence",
  "description": "Synthetic description.",
  "block_prefix": "",
  "tag_separator": "\n",
  "block_suffix": "",
  "expected_manifest_sha256": null
}
```

No whitespace is accepted by trial-and-error during verification. The profile
chooses one exact serialization, and its hash records that choice. For JOB0154,
use its saved title/description/serialization and original private manifest pin;
the illustrative strings above are not evidence. Missing evidence remains a
review blocker, not permission to expand the matching rules.

```sh
# Optional declared policy; without this flag the original raw-exact behavior stays.
PYTHONPATH=src python3 -m confluence_release.cli \
  --config /OWNER/release.json --html-policy /OWNER/html-policy.json plan
# Only after exact-SHA review, Ops pin/guard verification and recovery authorization:
PYTHONPATH=src python3 -m confluence_release.cli \
  --config /OWNER/release.json --html-policy /OWNER/html-policy.json reconcile JOB0154
```

Ops may instead pass the loaded immutable policy using
`create_release_worker(..., html_policy=load_html_policy(profile_path))`.
The existing host/API composition does not acquire a transformation profile or
new credentials. No global monkeypatch, readback replacement, or disabled guard
is required. The runtime's code pin changes; the old artifact's pin does not.

`tools/replay_here_now_html.py` compares a saved original/remote file pair offline
against a digest copied from the trusted original receipt. It performs no GETs,
DB operations, deploy or cleanup, and reports that its scope is file-pair replay,
not canonical publication or full-site acceptance.


## Saved-evidence checkpoint and tests

The follow-up evidence in ERM000274 / CX-MSG0303 independently fixes the
serialization for the blocked synthetic release: no block prefix or suffix,
four LF separators, the five tags in the order above, immediately before the
original closing head. The original head/body boundary is otherwise unchanged.
The four reported block lengths (two origins, index/detail) are 359, 364, 345,
and 350 bytes. Predicting these blocks from the explicit operator profile
matched all four independently reported SHA-256 values. This checks insertion
serialization only: the complete saved remote/original files have not been
replayed in the ChatGPT container. Writers/browse remote bytes were not retained
by the original test and remain a separate full-site verification requirement.
The title/description's origin in provider setup is not proven by these blocks;
the profile explicitly authorizes the observed literal values, not an inferred
metadata lookup. Live hostnames, receipt hashes and the recovery profile remain
in the private handoff rather than adding discovery links to this public repo.

At this checkpoint the full source tree passed 280 unittest cases on Python
3.13.5 (234 inherited + 46 new), compileall, and stored renderer-byte integrity.
Tests exercise default strict behavior, declared comparison, unapproved edits,
both origins and each surface, profile loading, source integrity and recovery
wiring. Temporary Git and the real shared runtime guard/lock are used; JOB,
provider and canonical-finalization ports in focused recovery tests are explicit
doubles. They are not proof of the actual PostgreSQL/PUB/APR workflow.

Three independent negative mutations were detected: disabling the whole-document
alternate comparison, removing manifest-pin checks, and removing all pre-provider
profile checks. Corrected sources were restored and the complete suite rerun.
Actual Pressroom rerendering, a clean-checkout local review, full saved-byte
replay, live all-surface GET-only validation and canonical JOB completion remain
required before calling this production recovery successful. No site, metadata,
artifact, original receipt, PUB/APR/JOB, production runtime or main is changed by
this implementation checkpoint.
