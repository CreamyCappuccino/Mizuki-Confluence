# RLY2890 correction pass — verification and restart point

Date: 2026-09-27
Reviewed base: `8edc0c61bef31a9252b36a03ecb371e421a6ea36`
Scope: four reported integration blockers; no UI redesign or production write.

## Corrections

1. Exact-revision authors are loaded by `canonical_reader.py` from the inspected
   `AuthorIdentityRepository.list_many` API, using `manuscript_profile` in the
   same transaction. Empty standalone snapshot authors no longer erase real
   authorship. The public allowlist retains author_ref, persona_name, harness,
   model, role, provenance_source; internal fields are not serialized.
2. `dispatch_validation.py` checks canonical JSON SHA-256 before side effects,
   with the Pressroom encoding (UTF-8, ensure_ascii=False, allow_nan=False,
   sorted keys, compact separators). Action/destination/ART/revision/UUID/route
   guards apply to publish, unpublish and lookup. No post-approval rewriting.
   Existing operation receipts are checked when present; their absence alone
   does not prevent artifact-based recovery.
3. `staging_readback.py` compares index.html, search.json and browse.html
   independently against deterministic output from remaining private projection
   state. Withdrawn detail must be absent. Shared categories/tags stay present
   with their correct reduced counts, not blanket text deletion.
4. Detail readback compares the entire expected artifact, including header,
   byline, body and trailing markup, with actual UTF-8 bytes. It rejects the
   extra-paragraph attack even when the approved body and all markers remain.

## Evidence produced in the ChatGPT container

- Baseline unchanged 8edc0c61 files: 54 tests PASS.
- Added counterexamples ran before the patch and failed against that baseline,
  reproducing authors/hash failures, stale independent surfaces and appended
  article content. These were not inferred only from an external report.
- Final suite: 79 tests PASS (19 contract + 35 existing provider + 25 regressions).
- Python: 3.13.5.
- compileall: PASS.
- Stored input/output renderer byte-integrity verifier: PASS.
- Existing loopback-only HTTP detail 200 / withdrawal 404 test: PASS.
- No production DB, registry, manuscript lookup or external delivery was used.

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m compileall -q src tools tests
python3 tests/fixtures/confluence/renderer/verify_fixture.py
```

`tests/adapter_test_support.py` provides explicit API-shaped doubles. This
exercises Confluence adapter code, not the local Pressroom installation or its
DB. Authors API source was inspected from the connected Pressroom repository;
actual local-checkout equivalence is deliberately a separate reviewer gate.
The real renderer output fixture is preserved byte-for-byte, not rewritten.

## Exact-SHA Pressroom-side recheck requested

Run the new SHA in local Pressroom b5ce8d9 with the original pinned converter.
Repeat renderer `--rerender`, import/signature checks and the isolated PG smoke.
Explicitly reproduce each RLY2890 counterexample on this new SHA:

- DB authors retained on the exact revision, with public-safe model/harness;
- wrong approved hash rejected before any staging file changes;
- restore index alone, search alone, browse alone, and detail alone after
  withdrawal: each must fail readback (include shared-taxonomy counts);
- append an extra paragraph while preserving the approved body/markers: fail.

Main remains held. The previous SHA's normal PG smoke PASS is not transferred
here. A future fresh integration PASS is not a claim that APR/JOB orchestration,
production access control or public delivery has been completed.
