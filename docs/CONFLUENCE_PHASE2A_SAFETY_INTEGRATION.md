# Phase 2A + release safety integration

2026-09-27. Owner: Mizuki / ChatGPT. Status: safety wiring implemented; complete-checkout tests pass locally; final exact-SHA real-Pressroom review pending.

## Parents and evidence

- Phase 2A: c44725d9dd962cf04d490fa4e227c5ce65623edd; RLY2926 / ERM000234: 161 tests and real isolated PG PUB/APR/JOB/reconcile/withdraw PASS.
- Safety: fcbf97d6dc8ec9614d2d8f75cca96eba10a6cb95; RLY2924 / ERM000233: 122 tests (79 shared + 43 safety) and helper smoke PASS.
- Their common base is d09e3b6b999bd4644054332aafa9d5980f3300e1. Preserve both parents and their original verification boundaries.

## Integration decisions

A file union is not enough. Use one host lock and one runtime guard implementation, exposing compatibility imports from confluence_release. Extend guard input coverage to both source packages, prototype and tools. Keep one lock around JOB claim through canonical ledger and JOB completion; do not nest the helper's synchronous wrapper around the existing worker.

Use the Phase 2A private BuildReceipt.checksums['checksums.sha256'] as the trusted manifest pin for the safety verifier. Preserve the existing whole-inventory check as well. Default external reads must use the bounded, no-redirect GET transport. Explicit injected test transports remain test-only. Preserve two delivery bases, removal checks, noindex and sitemap absence; do not silently enable the AIL host-owned robots exception.

Check runtime before projection/build, external effects, readback, return to canonical ledger finalization, and JOB completion. Failure after possible delivery stays unknown/reconcile; never rebuild or re-upload to hide uncertain outcomes.

## Acceptance

Run full combined discovery (expected baseline 161 + 43 = 204; confirm actual count) plus new wiring regressions. Run stored fixture integrity and compileall. A final exact SHA still needs the pinned Pressroom real renderer, host writer-profile preservation and fresh isolated PG owner probe. The probe must exercise the integrated safety path, not replacement fake safety functions. Hosting alone remains in-memory.

Main, production, dedicated hosting configuration, AIL and Pressroom sources are unchanged. No live credentials are read and no deployment is attempted. Dedicated here.now/Nor/projection setup remains UNKNOWN.

## Wiring actually implemented

- `confluence_release.release_lock` and `runtime_guard` re-export the same
  implementations/classes as the safety package. The shared runtime input list
  covers both source packages, prototype, tools and dependency files.
- `ReleaseJobStore.site_lock` already spans worker claim, canonical workflow,
  recovery and JOB completion. It now reaches the shared lock. The generic
  `run_guarded_release` helper remains usable by synchronous callers but is NOT
  nested around the JOB worker, avoiding double-acquisition and a parallel
  approval/retry implementation.
- `artifacts.verify_local_artifact` keeps exact private receipt inventory and
  adds the safety manifest/discovery checks. The trusted pin is the existing
  `BuildReceipt.checksums['checksums.sha256']`, preserved in private JOB receipts.
  No new approval object, manifest re-sealing, or public-JSON authority is added.
- `confluence_release.readback` bridges that same receipt to
  `confluence_pressroom.public_release_readback`. Default GETs use the existing
  bounded no-redirect transport. Explicit urllib-shaped test openers are adapted
  to the bounded response API; normal runtime cannot fall back to bare urlopen.
  HTTP is accepted only via explicit loopback test opt-in. Two distinct bases
  are mandatory. Unknown-route, removed-route and sitemap absence are checked
  on BOTH bases. The host-owned robots exception remains disabled here.
- Guard checks cover preparation, projection/build, possible external mutation,
  readback, return to canonical workflow/recovery finalization, and JOB completion.
  A post-delivery stale runtime cannot complete the JOB. Existing unknown/reconcile
  handling retains the exact artifact and never repairs by re-uploading.
- The existing owner PG probe now captures the shared real Git runtime guard,
  passes it to bridge AND worker, and records that source commit in its build.
  It still uses the supplied isolated PG and only in-memory hosting. The probe
  does not call production or create/drop the caller's DB.

## Verification at this integration checkpoint

The branch's initial union plus alias commit `2b553dac` passed 204 tests in
GitHub Actions run `36309095355`. Its exact public source archive was used to
create the full ChatGPT working copy, rather than reconstructing partial files.
The archive ZIP matched its reported SHA-256 before extraction.

After wiring, the full source tree passed **230 tests** on Python 3.13.5:
204 inherited cases + 26 new wiring regressions in
`test_integrated_readback.py` and `test_integrated_runtime.py`.
`compileall` and stored renderer byte integrity also passed. Real temporary Git
repositories, shared flock and loopback HTTP are exercised. Hosting/JOB ports
in focused tests are explicit doubles; this is NOT a new real-Pressroom/PG or
external-deployment result.

Existing test adaptations are limited to the stricter seams: bounded `.read(size)`
on the explicit HTTP double; two independent loopback mounts with explicit HTTP
opt-in; and inducing a runtime change AFTER preparation in the old upload guard
case (preparation itself is now guarded). No old test is removed or skipped.

```sh
PYTHONPATH=src:tests PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m compileall -q src tools tests
python3 tests/fixtures/confluence/renderer/verify_fixture.py
```

A branch-scoped GitHub Actions workflow repeats the complete offline checks and
stores source/test evidence. It uses no repository write permissions, credentials,
production services or deployment commands. No automatic main/release trigger
is enabled by that workflow.

## Final review and remaining boundary

Review the final commit of this integration branch, not either parent. Run the
230 tests plus actual renderer replay in local Pressroom `b5ce8d9`, preserve
writer_profiles in the test host, and run the owner PG probe UNCHANGED in a
fresh dedicated empty loopback DB and private temp root. Confirm the integrated
readback and real guard are reached during PUB -> APR -> JOB -> lost-reply
reconcile (upload count remains one) -> withdrawal. A Git archive is adequate
for offline tests but this PG probe's real guard requires an actual clean Git
checkout. Never disable that guard to make the probe run.

Separate authorizations/setups still remain: dedicated hosting/projection/runtime
configuration, live here.now/Nor delivery and readback, production registry,
actual manuscripts, Responses, and presentation-refresh controls. None is
implied by a source merge or helper/unit-suite PASS.
