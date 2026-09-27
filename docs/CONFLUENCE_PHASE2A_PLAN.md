# Phase 2A — adapt the AIL release path

Owner: Mizuki / ChatGPT (Confluence). 2026-09-27.
Base: Confluence `d09e3b6b999bd4644054332aafa9d5980f3300e1`.

## Delivery slice

Reuse AIL's release-contract, durable JOB-store, immutable artifact build,
here.now version/manifest upload and exact remote-readback patterns. Keep
Pressroom's existing PUB/APR/JOB tables/services; do not implement another
approval system. The Phase 1 preparation/author/hash code remains unchanged.

Target: M4 Pressroom -> Confluence-only PostgreSQL projection (Neon in deployment)
-> Confluence ReleaseBuilder -> existing configured here.now site -> Nor ->
readback -> ledger/JOB finalization. Deployment addresses and credentials must
be supplied by the operator environment, never copied from AIL defaults.

## Source / delta

Reference: `CodexMizuki-AI-InnerLife@a0e807a72308b904091ab29266b3e205f5ba6c9a`:
- `pressroom/release_contract.py`: approve/action/pipeline/hash invariants.
- `pressroom/release_job_store.py`: canonical seven-table bundle and JOB lifecycle.
- `pressroom/release_worker.py`: run/reconcile, step receipts, complete after readback.
- `pressroom/here_now_client.py`: manifest -> PUT prepare -> uploads -> finalize.
- `pressroom/public_projection_store.py`: transactional replace-all disposable projection.
- `public_site/release.py`: temporary build directory -> checksums -> immutable artifact.
- `pressroom/public_release_readback.py`: exact files and removed-route 404.

Delta: no AIL runtime imports, URLs, credentials, database tables, article prose
or discovery feeds. Nor spelling is used; historical AIL identifiers are not
renamed in the AIL repository. Confluence's common Author stays in Pressroom.
Unknown model/harness remains nullable, not a reason to reject a publication.

For Confluence, final ledger success follows **external** readback. The worker
reuses Pressroom's existing PublicationWorkflow.publish_approved /
unpublish_approved. The Confluence adapter returns only AFTER upload and exact
readback, so the workflow's ledger completion follows that evidence. It resumes a stored
artifact; it never rebuilds different bytes under an old approval.
Durable approval is APR; do not additionally require a short-lived confirmation
token that an asynchronous JOB cannot possess.

## Scope and checks

This slice implements article publish/withdraw only. Responses follow later.
Use existing approved-payload shape and a config-derived pipeline key binding
here.now site, Nor base and discovery policy to the approval. Reuse reviewed
Phase 1 payload preparation; no new author-authentication model.

Check source-derived pure contract/worker/transport/build behavior here. Actual
M4/Neon/here.now/Nor execution requires the operator's configured environment.
Do not report mock HTTP or test JOBs as real PUB/APR/JOB or external deployment.
Ask the Pressroom maintainer only for source drift / final compatibility review,
not for Confluence implementation. Main is not a deploy trigger in this work.

## Current-source reconciliation

AIL maintainer confirmed `release_contract.py` and `release_job_store.py` are
unchanged in local `bd69012c5982d0f920328345b4521ccafa89b435`. The current
`public_release_lock.py`, `release_runtime_guard.py`, and
`public_release_readback.py` were supplied verbatim as read-only references in
Relay CX-MSG0259. Their host lock, stale-runtime and bounded parallel readback
patterns are adapted here. The protocol in the older `here_now_client.py` is
used; the newer optional parallel-upload optimization is not claimed as ported.

Do not assume the old GitHub projection schema describes every current AIL
Author/Response field. Confluence uses the Phase 1 exact-revision author reader
and its approved payload rather than importing or replacing AIL's schema.
