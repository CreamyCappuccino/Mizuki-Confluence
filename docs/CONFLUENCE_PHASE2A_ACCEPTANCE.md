# Phase 2A + safety — integrated rehearsal acceptance

Date: 2026-09-27. Implementation owner: Mizuki / ChatGPT.
Reviewed code: `8cead09e7b75392919455d0621b2e9bb6d0e7288`.
Verdict: **PASS within the integrated compatibility/rehearsal scope**.
No blocking issue was reported. This is not live deployment acceptance.

## Exact evidence, not inherited PASS

The Pressroom reviewer executed a clean checkout of this exact SHA, rather than
reusing either parent result. Formal result: ERM000238 / CX-MSG0267, reply dated
2026-09-27 17:37:20 +08:00.

- All 230 tests passed separately on Python 3.12.11 and 3.14.7. Compileall and
  actual renderer `verify_fixture.py --rerender` byte replay passed.
- Installed Pressroom `b5ce8d9422f0b90377145471bcb96f870e3e9263` was clean;
  runtime core, destination adapter and worker import/init/signatures matched.
- The existing writer_profiles service remained the same object. Composed-set /
  host-read and host-update / composed-read passed in the test DB.
- The owner PG probe ran UNMODIFIED against a fresh empty dedicated database and
  private temporary output: returned ART0001 -> PUB0001 -> APR0001 -> JOB0001 ->
  unknown_reconcile -> exact frozen-artifact reconciliation -> published ->
  withdrawal JOB0002 -> unpublished. Both JOBs completed. Reconcile did not
  re-upload (`upload_calls == 1` for the first release).
- Exact author projection count remained one. Withdrawal left the projection
  empty, removed the old article route and removed the target from index,
  search and browse. Canonical counts were one manuscript, two attempts, two JOBs.

The reviewer used `sys.setprofile` CALL observation only, without replacing the
functions, results or guards. During the owner probe the shared runtime guard
was observed 35 times with this source commit, and both the release readback
bridge and shared safety readback were observed twice. Six lock-generator call
events include generator resumes and are NOT six independent acquisitions.
The real guard was not disabled to make the test run.

Independent GitHub Actions run `36309789541`, job `108593385239`, checked out this
same SHA and passed all 230 offline tests, compileall and stored renderer-byte
integrity. That CI run did not execute the real Pressroom/PG environment.

## Evidence retention and repository readback

Reviewer evidence was saved in Worldline lab
`confluence-phase2a-8cead09e-s01a037e1d6-20260927` as run_review.py,
probe-results.json and report.md. Dump/archive timestamp: `20260927T093637Z`.
Only the dedicated synthetic database was dropped after evidence preservation.

Main was read as exact `8cead09e`; comparison against the reviewed code returned
identical (ahead zero, behind zero). No redundant ref update was performed.
The closeout commit adds documentation only; it does not change reviewed code.

The inherited Python 3.14 staging HTTP404 ResourceWarning was observed again;
its test still passed. It was not classified as a new integration blocker.

## What this does not authorize or prove

Hosting was the owner's MemoryHosting port. No real here.now/Nor URL or live
readback was used. Dedicated hosting/projection configuration remains UNKNOWN.
Production DB, running registry/runtime, AIL sources and real manuscripts were
not changed. Source merging does not register a destination or start a worker.

Next work is dedicated configuration, explicit production composition and a
separately authorized synthetic live acceptance. Responses and presentation
refresh remain subsequent functionality. Existing low-discovery requirements
(noindex/nofollow/noarchive, no sitemap) stay unchanged.
