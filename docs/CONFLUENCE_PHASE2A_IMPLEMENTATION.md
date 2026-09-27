# Confluence Phase 2A — AIL-derived article release implementation

2026-09-27 · Implementation owner: **Mizuki / ChatGPT**.
Base: `d09e3b6b999bd4644054332aafa9d5980f3300e1`.
Status: code and focused local checks ready; actual local Pressroom/PG and
external deployment are **not** asserted by these checks.

## What is reused, not reinvented

See `CONFLUENCE_PHASE2A_PLAN.md` and `CONFLUENCE_AIL_REFERENCE_STRATEGY.md`.
AIL's release contract, JOB claim/receipts/retry/reconcile, transactional
projection rebuild, immutable artifact, here.now prepare/upload/finalize,
checksum readback, host lock and stale-worker patterns are adapted into
`src/confluence_release/`. There is no runtime import from `ai_inner_life`,
no new author account system and no parallel implementation of Pressroom
approval state. Existing Phase 1 preparation/author/hash modules are unchanged.

Reference identities:
- AIL GitHub `a0e807a72308b904091ab29266b3e205f5ba6c9a`.
- AIL local `bd69012c5982d0f920328345b4521ccafa89b435`: maintainer confirmed
  contract/job-store unchanged; supplied current lock/guard/readback verbatim
  in Relay `CX-MSG0259`. This was a read-only source request, not implementation.
- Expected integration dependency: Pressroom local
  `b5ce8d9422f0b90377145471bcb96f870e3e9263` and its existing converter environment.
  Do not try to install an unrelated PyPI package named Pressroom.

## Normal and recovery paths

Existing Pressroom `preview -> PUB -> APR -> approve -> JOB` is the input.
`runtime_composition.create_pressroom_core` accepts the host's existing gateway,
approval/read, editorial-state and system objects and adds only Confluence.
It does not start or mutate the running eight-tool MCP server.

Worker: host lock -> canonical JOB claim -> approved action/hash/config check
-> authoritative Confluence article snapshot plus approved change -> disposable
Confluence-only PostgreSQL projection -> immutable v0.2-based static artifact
-> here.now upload/finalize -> exact here.now **and Nor** file readback
-> existing `PublicationWorkflow` ledger completion -> JOB complete.

The adapter returns only after remote readback; it does not complete a local
pointer then pretend that external delivery succeeded. Failed/uncertain delivery
uses existing `PublicationRecoveryCoordinator`, observing the stored exact
artifact rather than rebuilding/re-uploading it. PUB terminal failures require
new preview/approval; only pre-dispatch JOB failure is retriable. No extra
short-lived confirmation token is added on top of durable APR approval.

The current single release-host lock must be shared by every future presentation
refresh. Outstanding Confluence unknown/processing JOBs prevent a new whole-site
release until reconciled. This is publication ordering, not author verification.

## Configuration and installation

`config/release.example.json` uses placeholder origins and local paths only.
Supply the dedicated Confluence here.now site and Nor mount; never use AIL's
site slug or replace its routes. `site_base` is the canonical Nor base. Static
artifact routes remain root-relative within the build, so the same bytes work
at here.now root and behind the Nor prefix.

Use the already-provisioned, pinned Pressroom environment. Add this checkout's
`src` to PYTHONPATH (or install this package there). Runtime needs SQLAlchemy,
psycopg, Pressroom and its existing renderer dependencies. No dependency install
or global service reconfiguration is implicit in these commands.

```sh
# Read configuration only; no credentials/DB/network.
PYTHONPATH=src python -m confluence_release.cli --config /private/release.json plan

# Explicit one-time Confluence projection setup. DSNs remain process-local.
# CONFLUENCE_PROJECTION_DATABASE_URL: dedicated projection target
PYTHONPATH=src python -m confluence_release.cli --config /private/release.json init-projection

# Also provide CONFLUENCE_PRESSROOM_DATABASE_URL in the trusted local process.
# Uses the existing owner-only ~/.herenow/credentials file; never print its key.
# JOBxxxx below means an ACTUAL returned approved Confluence JOB, not a fixture ID.
PYTHONPATH=src python -m confluence_release.cli --config /private/release.json run JOBxxxx
PYTHONPATH=src python -m confluence_release.cli --config /private/release.json reconcile JOBxxxx
```

`create_pressroom_core` is the host-composition seam. Existing Pressroom services
and OAuth transport are passed in, not rebuilt; the operator's deployed factory
must install that returned core explicitly. Neither a code import nor a GitHub
commit registers the destination, creates an APR, launches a daemon, provisions
Neon/Nor, or publishes content. `init-projection` changes only the explicitly
selected `confluence_public` schema, not Pressroom or AIL tables.

## Reader-facing output

The builder uses v0.2's shell/classes/assets, hero/closing scene and preferences
hooks. Rows, writers, hierarchy/category/tag/month navigation, search JSON,
article bodies and bylines come from approved projection data, never SAMPLES.
In-place expansion starts at six; no-JS readers still see all articles. Responses
are not wired in 2A and no invented reply count is displayed.

Every HTML page has `noindex, nofollow, noarchive`; no sitemap, public feed,
analytics or SEO campaign is added. These are discovery hints, not access
control. The host-reserved here.now robots behavior is not rewritten into a
false secrecy guarantee. Nor headers/routing remain explicit deployment setup.

## Checks actually executed in ChatGPT

- **72 new focused unittest cases PASS** on Python 3.13.5.
- `compileall` PASS.
- Actual local-loopback HTTP checksum/404 tests PASS (not external hosting).
- Chromium interaction smoke PASS: six-to-ten expansion, search, no matches,
  reset. Exact generated HTML, network blocked, tiny test assets: not full visual
  acceptance of the real CSS/photos and not a Safari claim.

```sh
PYTHONPATH=src:tests python -m unittest discover -s tests -p 'test_phase2_*.py' -v
python -m compileall -q src tools tests
PYTHONPATH=src:tests python tests/phase2_browser_smoke.py  # optional Playwright/Chromium
```

HTTP vendor behavior and JOB bridge steps use explicit doubles except for the
local HTTP smoke. The inherited **79 Phase 1 tests were not re-executed in this
container pass**; do not call the result a 151-test full integration PASS.
Actual PG, exact local Pressroom, renderer replay and PUB/APR/JOB need the pinned
runtime for verification. No production DB/registry, real manuscript or external
here.now/Nor endpoint was changed by this implementation pass.

## Concrete remaining work

Review this exact code against the installed Pressroom environment, including
actual APR -> JOB, publish/withdraw and recovery. Then configure the dedicated
projection DB, here.now site and Nor route and run the approved synthetic article.
The implementation remains here; the Pressroom colleague supplies compatibility
results and local operational evidence, not replacement Confluence code.

Known operational limit: if a process dies after private artifact rename but
before its JOB receipt is committed, no automatic overwrite is attempted. Inspect
that private orphan against a still-unclaimed PUB before cleanup/rebuild. An
active/uncertain PUB without its frozen-artifact receipt must recover evidence,
never invent a new artifact. Multi-host writers and presentation-refresh UI are
not implemented here; the current AIL-style host lock is single-host.
