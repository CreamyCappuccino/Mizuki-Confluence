# RLY2923 — Phase 2A host/probe correction

Date: 2026-09-27. Implementation owner: Mizuki / ChatGPT.
Base: `a235b796fe32f8838eb79c4b1fa1ea9617060dbf`.
Status: correction closed at `c44725d9` by RLY2926 / ERM000234.
161 tests, real renderer, real writer_profiles read/set and the unpatched owner
PG probe passed. The verification paragraphs below describe the earlier
correction pass; current two-branch integration is tracked in
`CONFLUENCE_PHASE2A_SAFETY_INTEGRATION.md`.

## Evidence and scope

The Pressroom reviewer ran the base SHA in the local `b5ce8d9` environment
(ERM000232 / CX-MSG0261 / RLY2923). Its 151 tests and real renderer byte replay
passed, but the supplied PG probe stopped at manuscript creation. The real
PUB/APR/JOB chain was NOT REACHED. Separately, adding Confluence to the host
core dropped the configured writer-profile service. Those are the two defects
addressed here; passing unit tests is not a replacement for that integration.

## Changes

- `tests/phase2_pg_probe.py` constructs its draft request in
  `_synthetic_create_request()`, called by the same guarded `run_probe` path.
  `persona_key=confluence-phase2a-probe` is explicit when author_ref is omitted.
  It is synthetic probe data, not a new production identity. `model=None`, the
  existing persona_name/harness, draft action and JSON receipt remain unchanged.
  Manuscript/publication/approval/JOB references must still come from real
  returned receipts; no ART/AUT/PUB/APR/JOB identifier is guessed or reserved.
- `src/confluence_release/runtime_composition.py` accepts `writer_profiles`
  and passes the exact object to `PressroomToolCore`. Callers must supply their
  existing configured service, just as they supply responses, approvals,
  editorial_state and system. None means that the host has no configured profile
  service. No silent compatibility fallback discards a supplied service.
- Existing gateways, destinations and services are reused, not recreated.
  This change does not install a new core into a running host or mutate a
  production registry. It does not change public author-field policy.

Example host-factory addition, using the already constructed host service:

```python
core = create_pressroom_core(
    session_factory,
    config=config,
    manuscripts=manuscripts,
    approvals=approvals,
    existing_destinations=existing_destinations,
    responses=responses,
    editorial_state=editorial_state,
    system=system,
    writer_profiles=writer_profiles,
)
```

## Verification performed in this correction

- Ten new `test_phase2_host_regressions.py` tests pass on Python 3.13.5.
  They execute the real composition function and real probe request builder
  with explicit constructor/input boundary doubles, not a Pressroom DB.
- Each defect was independently reintroduced: omitting writer-profile
  forwarding caused four failures; setting persona_key to None caused one.
  The corrected sources were restored and all ten tests passed again.
- `compileall` passed for the two edited files and the new tests.
- The two retrieved base files matched their Git blob hashes before editing.
  Only these source/test changes and this checkpoint are included.

```sh
python3 -m unittest discover -s tests -p 'test_phase2_host_regressions.py' -v
python3 -m compileall -q src/confluence_release/runtime_composition.py tests/phase2_pg_probe.py tests/test_phase2_host_regressions.py
```

The complete inherited 151-test suite, actual renderer replay, real host
writer_profiles read/set operations, and isolated PG chain have NOT been rerun
by this correction in the ChatGPT container. The complete-checkout target is
151 existing + 10 new = 161 tests; that total is not a claimed PASS.

## Next exact-SHA review

Use the committed SHA containing this note, not the previous base. In the
pinned local Pressroom/converter environment, run the full suite and renderer
replay, then preserve the real writer_profiles service in host composition and
check read/set behavior in an isolated test host. Run the supplied PG probe
unchanged in a fresh empty dedicated loopback database and private output root.
It must get past create, use returned refs for PUB/APR/JOB, recover the simulated
lost reply without re-upload, and withdraw with body/listing removal.

The dedicated Confluence hosting configuration remains UNKNOWN, not confirmed
absent or ready. No production DB, registry, runtime, here.now or Nor setting is
changed here. Main is not moved. The separate release-safety branch is untouched.
