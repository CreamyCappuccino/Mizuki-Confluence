# Declared nine-meta image representation (here-now-og/v2)

Owner: Mizuki / ChatGPT. Date: 2026-10-10.
Base source: 3580a8cb3856d56fd6df25e1031e2fd2dc785b05.
Status: design and offline implementation; no production policy activation.

## Evidence, uncertainty, and scope

The formal Pressroom reply RLY3104 (ERM000282 / CX-MSG0311) reports:
- Same provider version and 21-file manifest as the earlier five-meta capture.
- Four HTML surfaces times two origins have nine inserted meta elements.
- The existing title, description, origin/path-specific URL, and website type
  are preserved. There are eight inter-tag LF bytes and no prefix/suffix bytes.
- Image metadata adds og:image, og:image:width=1280, og:image:height=720, and
  twitter:image. Both image values are the site's here.now-generated JPEG URL.
- twitter:card changes from summary to summary_large_image.
- Each remote HTML is 277 bytes longer than the old five-tag prediction.
- Outside the inserted block the original bytes match; all 34 non-HTML reads
  match. Unknown-route/sitemap checks were not reached in that failed preflight.

The follow-up CX-MSG0337 / ERM000308 confirms the exact name order by reading
observed-blocks.json: title, description, url, type, image, width, height,
twitter:image, twitter:card. All eight captured pages share that one order.
V2 fixes it in code; there is no configurable order, optional tag, or permutation
search. Test bodies remain synthetic, not saved production HTML.

The provider's public docs describe generated display name/description after
finalize, but do not specify this nine-meta serialization or prove its cause.
Do not infer an asynchronous image-generation mechanism from the metadata change.
Do not change provider metadata to make a verification test pass.

## Versioned, immutable policy

V1 class, JSON field set, defaults, five-tag serialization and canonical hash
are preserved. Existing v1 profiles do not start accepting image metadata.
Raw exact remains the default when no policy is supplied. Even with a v2 profile,
an original byte-exact HTML response is accepted and honestly recorded as raw-exact.
A v2 profile predicts ONE alternate representation, not both v1 and v2 blocks.

V2 is an explicit subtype of the existing policy with:
- format exactly here-now-og/v2;
- the same HTTPS bases, title/description, and non-null original manifest pin;
- image_url exactly https://here.now/og/<configured-site-slug>.jpg;
- explicit integer image_width and image_height (not booleans or numeric strings);
- the single confirmed nine-name order, fixed in code (no tag_order profile field);
- block_prefix='', tag_separator='\n', block_suffix='' (the reported form).

The supported names are og:title, og:description, og:url, og:type, og:image,
og:image:width, og:image:height, twitter:image, twitter:card. Website type and
summary_large_image are fixed, twitter:image equals image_url. No extra tag,
attribute, remote-supplied field or alternate serialization is accepted.

The nine-name sequence is a fixed tuple tied to the v2 format. Received HTML
cannot change it. A different order requires a reviewed implementation change,
not runtime permutation search. The image URL is independently bound to the configured site;
the reader never fetches that JPEG or treats its pixels as attested. Only its
literal reference in the HTML is checked. The generated image is not a file in
the original release manifest and its content digest is not proven by this policy.

## Unchanged safety and relocation behavior

Predict full remote bytes from independently hash-checked original HTML and the
immutable owner policy. Never strip, parse-and-reserialize, or learn from remote
HTML. Preserve the real head boundary, one eligible head, and rejection of existing
author-owned OG/Twitter metadata for transformed comparisons.

The loader keeps owner0600, regular/non-symlink, size bound, duplicate/unknown
field rejection, and load-once semantics. It selects a policy type only by the
explicit format. V1 rejects v2 fields; v2 rejects missing/invalid required values.

The real worker/factory/delivery/readback interfaces already accept the v1 base
class, so v2 passes through the same path without replacing any transport, guard,
lock, canonical store, or claim logic. Manifest/base checks still precede provider
lookup. Non-HTML and checksums.sha256 stay raw-exact; all origins, file inventory,
noindex/no-sitemap, removed/unknown 404, and bounded no-redirect reads remain.

ArtifactLocation from the storage migration remains independent. Read the same
JOB's relocated physical files while preserving the stored original absolute path,
source commit, PUB/APR/payload and static_build hashes. No old-path fallback,
symlink, rebuild, projection replacement, upload or ledger edit is a repair.

## Activation gate and local cooperation

Implementation and offline tests are the ChatGPT owner's work. The Pressroom
session supplies only saved local evidence / local-only final verification.
No general local implementation lane is created.

Before an executing source/policy update:
1. Read the saved observed-blocks.json and all original/remote byte pairs under
   the existing project's evidence/ directory. Confirm all nine names, values,
   exact fixed order, whitespace, position and the recorded body hashes.
2. Make a separate reviewed v2 profile pinned to the original manifest; do not
   overwrite the preserved v1 profile or the artifact-location record.
3. Replay the saved eight HTML pairs with independent original receipt hashes,
   using tools/replay_here_now_html.py or the whole-artifact verifier. Check the
   old five-tag profile still rejects them. Do not count synthetic pairs as this.
4. Capture new executing source/policy hashes and align existing Ops + AIL host
   pins together. Preserve the relocated source and artifact paths; do not move
   anything back into ~/.local. Existing configuration files stay where they are.
5. A fresh live read-only check must still establish that the declared profile
   matches current delivery. Any further representation change stays UNKNOWN.
6. Only then use the authorized same-JOB, same-artifact reconciliation entry.
   Recovery must not upload/build/reproject. Withdrawal is a subsequent, separately
   approved JOB with its own manifest-bound profile and normal new artifact.

This code change alone is neither a production update nor a recovery PASS.

## Verification checkpoint

The complete baseline tree was reconstructed from the saved 3c source archive
plus connector-fetched 3580 files. Its Git tree matched the remote
733561c5284ea01509c5c389ee3f30a18fcc2002 exactly before changes; all 319 baseline
tests passed. After the v2 change, all 364 tests (319 + 45) pass on Python 3.13.5,
plus compileall and stored renderer-byte integrity.

New tests cover v1 schema/hash preservation, exact nine-name serialization,
site-bound image reference, type/size/format/manifest validation, loader
permissions/load-once behavior, all eight synthetic HTML responses and raw-exact
non-HTML, modified order/attributes/URL/values/whitespace/body, per-byte XOR1
mutants of synthetic pairs, no auto-fallback to five tags, snapshot-race rejection,
404/sitemap rules, new-manifest withdrawal separation, and combined relocated
same-JOB recovery with no old files, no rebuild/upload/projection replacement.
The existing replay CLI accepts an explicit v2 profile without rewriting evidence.

Four independent safeguard-removal mutations were detected: removing image-site
binding, removing manifest-scope checking, bypassing the full-HTML comparison, and
omitting an image tag from the predicted block. Sources were restored and all
364 tests rerun successfully. These are cloud/offline tests with real local files,
Git/locks/guards and explicit provider/JOB boundary doubles, not a live PG run or
saved-production full-byte replay. No production settings, old profile, artifact,
receipt, JOB, site metadata, or main ref were modified by this checkpoint.
