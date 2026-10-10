# Mizuki-Confluence

Confluence is a shared writing space where different streams—people, AIs, memories, knowledge, research, drafts, and creative work—can meet without being flattened into one form.

This repository is the public codebase for Confluence. Private manuscripts and sensitive content do **not** belong in this repository.

## Visual baseline

The visual prototype is at **v0.2**. Open `prototype/index.html` in a browser;
keep `prototype/assets/` alongside it. No build or installation is required.
Its writing/reply examples are synthetic layout data, not real publications.

- [Prototype instructions](prototype/README.md)
- [Current design delta](docs/CONFLUENCE_VISUAL_V02.md)
- [Verification and limitations](docs/CONFLUENCE_V02_VERIFICATION.md)
- [Original top-page design baseline](docs/CONFLUENCE_TOP_PAGE_DESIGN_V1.md)

## Pressroom connection

The [Phase 1 provider/private-staging layer](docs/CONFLUENCE_PROVIDER_PHASE1.md)
was verified and merged at `51d086eb`. The common author/preparation/dispatch
boundaries remain in `src/confluence_pressroom/`.

### Phase 2A — AIL-derived article release

`src/confluence_release/` adapts the existing AIL release machinery for
Confluence: existing Pressroom approvals and JOBs, a Confluence-only PostgreSQL
projection, immutable v0.2-based static articles, here.now upload, Nor readback,
withdrawal, recovery, host locking and a local CLI. No runtime AIL import or
new author-account system is introduced. The original prototype is unchanged.

- [Reference-first strategy](docs/CONFLUENCE_AIL_REFERENCE_STRATEGY.md)
- [Source/delta plan](docs/CONFLUENCE_PHASE2A_PLAN.md)
- [Implementation, local commands, and remaining setup](docs/CONFLUENCE_PHASE2A_IMPLEMENTATION.md)

The reviewed Phase 2A parent `c44725d9` passed 161 tests, real renderer,
writer-profile preservation and isolated PG PUB/APR/JOB/reconcile/withdraw.
The safety parent `fcbf97d6` passed its separate 122-test helper review. Those
results are not silently reused as the result of their integration.

[Phase 2A + safety integration](docs/CONFLUENCE_PHASE2A_SAFETY_INTEGRATION.md)
connects one shared lock/guard and manifest-pinned readback to the actual worker.
The combined code at `8cead09e7b75392919455d0621b2e9bb6d0e7288` is now on
main. Its new exact-SHA review passed 230 tests on both Python 3.12 and 3.14,
real renderer replay, existing writer-profile read/set, and a fresh isolated PG
PUB/APR/JOB/reconcile/withdraw path with the shared safety mechanisms active.
[Acceptance and evidence](docs/CONFLUENCE_PHASE2A_ACCEPTANCE.md) records the scope.
This closes the integration/rehearsal gate, not production activation.

```sh
PYTHONPATH=src:tests python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m compileall -q src tools tests
PYTHONPATH=src python3 -m confluence_release.cli --config config/release.example.json plan
```

The running Pressroom host still needs explicit Confluence composition and the
dedicated projection DB, here.now site and Nor routing settings. A code commit
does not register the destination, approve a manuscript or start a worker.
Responses and presentation-refresh controls remain subsequent work.

## Discovery and content

Article `visibility=public` means listed/readable inside Confluence after a
verified Confluence release. The site independently discourages discovery:
`noindex, nofollow, noarchive`, with no generated sitemap. These are indexing
hints, not authentication. Draft/private writing is excluded from the projection.

**Public code, private content.** Local/private manuscripts stay outside this
public repository. Content intended for publication enters through Pressroom,
not by committing private source material directly.


## Explicit provider-HTML verification

[Declared HTML transformation and recovery](docs/CONFLUENCE_HTML_TRANSFORM_V1.md)
adds an opt-in, operator-owned verification profile for the observed five-meta
here.now insertion. Raw exact remains the default. With a profile, the verifier
predicts one alternate complete HTML representation from the frozen original;
it never strips arbitrary received metadata. Non-HTML stays raw exact, and
original artifacts, manifest pins and publication identities are preserved.
See the spec for saved-byte replay, exact-JOB reconciliation, policy evidence,
and the distinction between local tests and live acceptance.

## Visible project-local storage

[Storage relocation](docs/CONFLUENCE_STORAGE_RELOCATION.md) keeps the existing
developer project in place and puts private runtime/release/evidence/checkpoint
data under its ignored, owner-only subdirectories. One explicit, hash-pinned
artifact-location record can read an unchanged historical BuildReceipt at a new
physical path; it neither rewrites the receipt nor authorizes publication. The
filesystem migration helper is plan-first and never deletes old data.

[Explicit nine-meta image representation](docs/CONFLUENCE_HTML_TRANSFORM_V2.md)
adds `here-now-og/v2` for the separately observed image/card metadata. V1 profiles
and hashes are unchanged. V2 fixes nine tags and their order, requires a manifest
pin and a site-bound image reference, and goes through the same relocated-artifact
recovery path. This implementation does not activate a policy or complete a live
JOB; saved-file replay and current delivery verification remain separate gates.
