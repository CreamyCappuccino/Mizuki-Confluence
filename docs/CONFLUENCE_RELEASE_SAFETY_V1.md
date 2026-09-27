# Confluence release safety transplant — v1

Status: helper parent `fcbf97d6` passed complete-checkout review (RLY2924 /
ERM000233), including 122 tests on Python 3.12/3.14. The evidence below preserves
the original implementation-pass boundary. Current worker wiring is tracked in
`CONFLUENCE_PHASE2A_SAFETY_INTEGRATION.md`.
Date: 2026-09-27. Base: d09e3b6b999bd4644054332aafa9d5980f3300e1.

## Scope and source

Adapt the three exact AIL local sources delivered through ERM000231/CX-MSG0260
(replay of CX-MSG0259 / RLY2914–2916). Source commit:
`bd69012c5982d0f920328345b4521ccafa89b435`.

| Source under src/ai_inner_life/pressroom/ | Git blob |
| --- | --- |
| public_release_lock.py | 43f6e170130c099da5a5b162aea7cb85f23a7513 |
| release_runtime_guard.py | 0ce6135e1043de460bd8233a8e8b1fd2f685a61b |
| public_release_readback.py | b2e657ad31ed6a7063611f25f66a338bb2acd2e6 |

All three received byte sequences matched Git's blob hash formula before
adaptation. No AIL runtime import, source-repository push or live-runtime change.
The mirror release_worker was read for stage order only; it is not substituted
for the local bd69012 worker source or treated as current-runtime proof.

## Reuse and explicit deltas

- Lock: retain AIL's nonblocking flock structure; change only the busy message.
  One common site release root must be used by every public mutator on this host.
  This is advisory host-local locking, not a distributed/multi-host lock.
- Runtime guard: retain AIL's capture/assert_current and whole-HEAD-change restart
  rule. Watch Confluence source, prototype, tools, pyproject and uv.lock. Ignored
  files and external editable dependencies are not attested; dependency pinning
  remains separate. A dirty/source-changed process must not claim new work.
- Readback: retain complete-file SHA-256 comparison, at most six parallel GETs,
  two explicit delivery bases, unknown-route and removed-route 404 checks.
  Confluence adds a manifest digest supplied by the trusted build receipt,
  path/duplicate/symlink/file-set validation, bounded no-redirect GET transport,
  and explicit noindex/no-sitemap checks.
- The private manifest pin is not Pressroom's PUB payload hash. The builder and
  release snapshot must preserve the association between the approved payload,
  generated files, their manifest, destination bases and pipeline identity.
- No embedded AIL host, slug, credential or endpoint. HTTPS is required except
  an explicit loopback-only HTTP option for tests. Base-path prefixes are kept.
- Every HTML artifact must contain noindex, nofollow, noarchive in head metadata.
  Owned robots cannot advertise a sitemap; sitemap files are not accepted.
  Both configured bases must return 404 for sitemap.xml and each removed route.
  This is discovery suppression, not authentication or secrecy.
- AIL's first-host robots exception is available only as the explicit
  `here_now_robots=host-owned-open` compatibility option. The default is exact.
  It never relaxes HTML noindex or the second base's checksum. It is source-derived
  behavior, not a claim about the current here.now service; live verification is
  still needed before activation. Keep the AIL `nol_base` argument name for Nor.

## Code map

- public_release_lock.py: site-level host lock, always released on exit.
- release_runtime_guard.py: Git source/dirty-runtime checks.
- release_checksums.py: pinned local artifact and discovery-policy validation.
- release_http.py: bounded GET-only transport; redirects fail exact readback,
  transport/HTTP 5xx errors remain unavailable, never proof of withdrawal.
- public_release_readback.py: exact two-base files + manifest + removed routes.
- release_execution.py: thin synchronous stage-order safety envelope.

`run_guarded_release` checks runtime, takes the site lock, checks again, then
runs claim -> build -> deliver -> readback -> finalize, checking runtime before
each stage. The lock covers the entire operation through finalization. Busy or
stale workers do not claim; exceptions never become success or automatic retry.
Post-delivery errors propagate for the caller's existing recovery policy.

This is not a new JOB store, approval engine, daemon or retry subsystem. The
caller supplies the real Pressroom-backed operations. Tests supply explicit
boundary doubles; they do not create APR/JOB records. The previous Phase 1
provider, static staging implementation and v0.2 UI are unchanged.

## Verification performed and remaining

The ChatGPT sandbox executed 43 new tests successfully plus compileall:
16 lock/runtime/order tests, 20 artifact/readback tests, 7 loopback-HTTP tests.
Real subprocess contention, temporary Git repositories and a real loopback HTTP
server were used. No real external origins, production DB or deployment commands.

```sh
python3 -m unittest discover -s tests -p 'test_release_*.py' -v
python3 -m compileall -q src/confluence_pressroom tests
```

The sandbox was a partial namespace checkout; the existing package/79 tests were
not rerun there. Its working files later became unavailable before the complete
upload, so the same code/test text was preserved with GitHub tree writes. A fresh
complete-checkout run on the final exact SHA is required before merge; expected
selection is existing 79 + new 43 = 122 tests, not yet a claimed combined PASS.

Negative cases cover body append, independent index/search/browse/detail
corruption, stale sitemap, missing/noindex/conflicting metadata, manifest/body
co-tamper, invalid paths, extra files, symlinks, missing removed-route 404,
redirects/timeouts, stale runtime, and no finalization after failed readback.
The builder must still provide prior release paths: readback cannot enumerate
all arbitrary remote URLs to discover unknown stale files.

## Next composition boundary

Connect these hooks to the exact AIL-derived Confluence worker, canonical
Pressroom JOB claim/finalize/recovery, and a Confluence ReleaseBuilder. Pin
configuration at approval; run that full chain in isolation. Production registry,
Neon projection, here.now/Nor activation and real publication are not enabled
by this review branch. Do not turn a helper-suite PASS into a full pipeline PASS.
