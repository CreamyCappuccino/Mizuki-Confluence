# Project-local storage relocation

Owner: Mizuki / ChatGPT. Date: 2026-10-10. Baseline: `3c753eb7`.

## Requested boundary

Keep the existing local `projects/confluence` Git checkout where it is. Move
only the contents of the existing `.local/share/confluence` store into visible,
ignored subdirectories of that project. Do not create a second project home,
overwrite the developer checkout, move `.config`, Ops, Pressroom DBs or backups,
or change the here.now HTML policy. This is not publication/recovery authority.

| Old store entry | Under existing project |
| --- | --- |
| `source/` | `runtime/source/` (separate pinned production checkout) |
| `releases/` | `releases/` |
| `acceptance-*` | `evidence/<unchanged directory name>/` |
| `checkpoints/` | `checkpoints/` |

All four destinations are Git-ignored and private (0700 directory boundaries).
The caller checks external-sync exclusions too: Git ignore is not a sync policy.
The existing `.config/confluence` files remain there; only their path values and
Ops/AIL path guards change. No credential values are exported into the code repo.

## Frozen history, relocated bytes

The old private `static_build.output` is immutable historical evidence, not the
new file location. A separate owner-owned `confluence-artifact-location/v1`
record binds ONE exact JOB ref + UUID + pipeline, original absolute output,
new absolute output, canonical SHA-256 of the whole saved `static_build` JSON,
and its original checksum-manifest digest. It never substitutes checksums.

`ReleaseDelivery.prepare` accepts a relocated saved artifact only with this
explicit record. It creates an in-memory BuildReceipt with the new output,
rechecks all original hashes and inventory there, and leaves the saved receipt
unchanged. No symlinks, fallback to the old directory, receipt/DB rewriting,
rebuild, upload or JOB execution is involved in changing a storage location.
The new path must be exactly configured `release_root / JOB UUID` and have no
symlink ancestor. Normal workers without a location record retain the old strict
path check. The record is not globally enabled for other JOBs or new builds.

`--artifact-location` loads an owner0600 regular non-symlink JSON once; it is
available for `plan`, exact-JOB `run` and `reconcile`, not retry/init. The operator
wrapper must enforce the same exact JOB selection. Factory/bridge wiring carries
this immutable record explicitly. Successful future readback evidence includes
the relocation-record digest and old/new locations, without rewriting history.
The frozen content's source commit and the currently executing source commit
remain distinct. The unresolved nine-meta/five-meta mismatch remains blocked.

## Cutover order (local cooperation only after source tests)

1. Inspect current JOB/receipts/refs and process state. Take the original private
   receipt hash from the DB without changing it. Do not confuse a status report
   with a completed migration. Check project Git identity, ignored destinations,
   external-sync exclusions, and no pre-existing destination collision.
2. Quiesce all possible Confluence writers and the shared MCP host as needed.
   Use one migration operator. Never run old/new workers under different locks.
   Existing reader services and external AIL/site artifacts remain untouched.
3. Inventory source files (relative name, size, SHA-256, mode); verified-copy to
   the layout above. The supplied copy helper refuses links, unexpected entries,
   overwrites and changed source. Originals stay intact until cutover verifies.
4. Install reviewed source in `runtime/source` only, preserving the developer
   checkout. Update Ops SOURCE/RELEASE_ROOT and AIL host SOURCE + matching code
   pins together. Update `.config/confluence/release.json` project_root and
   release_root, and checkpoint/evidence references; do not move those configs.
   Store the one-JOB location record under project checkpoints (0600).
5. Load through the regular factory, verify relocated files against the unedited
   original receipt, and run non-writing plan/guard/host health. No JOB claim,
   reconcile or publication. Compare original receipt/manifest/JOB/PUB/APR and
   provider-independent state; preserve current HTML policy and its STOP.
6. After dependent references and health pass, the helper can archive the old
   root under project checkpoints with a same-filesystem rename. Revalidate
   source + new copies before this. It never deletes the original: the visible
   archive is explicitly rollback-only. Old `.local` path is no longer active.
   Log old/new mapping; historical receipt paths remain historical only.

Rollback before archive uses untouched old paths + recorded config/pin snapshots.
Rollback after archive requires restoring the archived root and all dependent
path/pin values as one quiesced operation. Do not resurrect old workers alone.
Do not remove this one-JOB locator while an old saved receipt may be read.

## Local tool

`tools/move_confluence_storage.py plan|copy|archive` is filesystem-only, with no
DB, service, Git write or networking calls. Use explicit absolute source/project
paths. Plan and copy require the existing Git root and ignored destinations.
`copy` needs its reviewed fingerprint and `--confirm-copy`; `archive` additionally
needs `--confirm-cutover`, the original copy receipt and an exact new archive
path under project checkpoints. It retains originals on failure. It is not the
host/config cutover coordinator; that tightly scoped operation remains local.
