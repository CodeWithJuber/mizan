# Full research import operations

This is a bounded first import of the already verified consolidated research archive. It preserves all archive files and the original ZIP, builds the existing local source index, and verifies source retrieval as the real backend user. It does not execute archive code, authorize training data, train weights, or establish independent model readiness.

| Source identity | Verified value |
|---|---|
| Library filename | `Mizan-Full-Architecture-Integration-2026-10-24(4).zip` |
| ZIP bytes | `241577161` |
| SHA256 | `0fda16988214d7949592d018b9edab5157d6e7a0b437d74f1d155d164e6531f6` |
| Archive members / indexed UTF-8 text files | `21486` / `7665` |

The older approximately 77 MB archive with a similar filename and SHA prefix `d3d9` is a different version and is not accepted here.

The production first import completed on October 25, 2026; its receipt is kept
with the deployment records, not in this repository. This procedure does not
replace or reimport that active collection.

## Sequence and authority

1. Complete the application deployment and any separately reviewed backend recreation first. These workflows never recreate containers or change configuration. If `MIZAN_RESEARCH_DIR` is ephemeral, stop and separately fix deployment configuration; the importer cannot override it.
2. Publish the reviewed key-preparation slice to exact branch `ops/research-key-20261025`. Its workflow uses the existing pinned SSH host and existing production deployment lock. It reports only the configured research path, matching persistent mount, backend image/container identity, effective UID/GID and path permissions. All existing research targets, including dangling or unrelated symlinks, are refused.
3. Save the single `key_ready` public JSON line, or the complete public JSONL artifact. Prepare a fresh Library download URL immediately before encryption. The URL must be a read-only signed HTTPS URL from the reviewed exact host `sdmntprcentralus.oaiusercontent.com`, with at most a one-hour validity window and at least 60 seconds remaining. If the service changes the host, review the allowlist explicitly; do not edit signed query parameters.
4. Run `python3 scripts/encrypt_research_url.py --public-key PUBLIC.jsonl --output ENCRYPTED.json`, supplying the URL only through a private stdin stream from the materialization result. Never put the URL in a shell command, argument, environment variable, clipboard log, Git file, workflow input, or Actions log. The helper emits only an encrypted CMS envelope and nonsensitive receipt.
5. Place only the encrypted envelope at `deploy/research-transfer.encrypted.json` on exact operations branch `ops/research-import-20261025`, together with the reviewed scripts/workflow. Keep this one-use envelope separate from reusable implementation commits. The workflow copies only code and ciphertext to a private `/run` directory over pinned SSH, then invokes the receiver under the shared `mizan-production` concurrency group and production host lock.

Key preparation may be run early for a safe preflight. Any key bound to the earlier container must be discarded. Only a fresh key prepared after the final backend recreation is valid for import.

## Receiver bounds and proof

The server keeps RSA-3072 private material in root-only `/run/mizan-research-transfer/<random-id>` with 0600 files. A one-hour deletion timer is scheduled before generating private material, and reboot clears `/run`. Each attempted import consumes its key, including failed authentication. The envelope requires CMS AuthEnvelopedData, AES-256-GCM, RSA-OAEP-SHA256 and MGF1-SHA256; authenticated fields bind the key, target inventory, archive hash/size and expiry. Plaintext is parsed only after successful GCM authentication.

The URL exists only in receiver memory. The download follows no redirects, sends no authorization header, checks the exact byte count and pinned SHA before archive parsing, and uses bounded time/space. There must be at least 2 GB free in the research volume, plus temporary download space on the host. Backend user identity, image/container, path, mount and permissions must exactly match key preparation both before and after download.

The existing trusted `mizan_owned.research.import_bundle` executes in the running backend as its configured user. It rejects traversal, duplicate entries, symlinks, mismatched hashes and excessive extraction sizes. No code from the ZIP is imported or run. A unique backend-owned release beside the configured research target contains the full extraction, original `BUNDLE.source.zip`, `IMPORT.json`, `FULL_IMPORT.json`, and the FTS index. The importer verifies 21,486 members, 7,665 index rows, SQLite integrity, and actual source-attributed search. The final absent research path is created atomically as a relative symlink to that complete release; symlink creation refuses concurrent or pre-existing data.

The Actions receipt contains the pin, byte/count proof, release/target paths, actual backend UID/GID, `fts_search_verified: true`, and `training_gold: false`. It includes no source excerpts or signed URL. Application research status/search should then observe the same configured collection without restarting the backend.

## Cleanup, failure and retry

Ordinary failure removes the downloaded temporary file and private key. The receiver defers handled TERM/HUP/INT during the backend operation, retaining the production lock until the backend returns its actual outcome. It supplies an absolute operation deadline 840 seconds from launch; the backend checks it at entry and immediately before activation and caps its independent alarm to the remaining interval. A delayed Docker start therefore cannot activate beyond the host's 900-second lock window. Cancellation checks the recorded PID, process start time and exact request identity, then signals a stable Linux pidfd at most once. Missing process metadata is an unknown outcome until a terminal receipt exists; unresolved early Docker failures retain the lock through the launch window. Trusted helper source is cached in memory so SSH upload cleanup cannot remove the reconciliation code. The aggregate network phase has a separate 600-second alarm, including response headers. The workflow allows 40 minutes so cancellation/reconciliation is not cut off by its usual time budget.

Backend failure removes its private staging and newly created release, and removes only its own newly activated link if post-activation verification fails. Existing data is never replaced. No prior deployment or provider settings change. If Docker is unavailable and the remote result cannot be observed, the receiver reports `outcome_unknown`, preserves backend evidence, and performs no automatic retry, deletion or adoption. Read-only reconciliation of the exact target and operation must precede any further import or deployment; this workflow does not install a deployment-block marker.

An unused key expires automatically after one hour. A used or failed key cannot be retried: prepare a fresh key and fresh signed URL. If activation succeeded but the workflow disconnected before recording the receipt, inspect the actual configured target and its receipts before retrying; the first-import guard will refuse to replace it. A separate private `.mizan-research-operation-<id>.json` terminal receipt remains beside the target for reconciliation. For recovery, record the exact managed release and verify its `FULL_IMPORT.json` before any separately authorized change. Forced termination such as host power loss or SIGKILL can leave a private staging/release directory; inspect the exact recorded random ID and verify that the directory is inactive before removing it. Do not bulk-delete research directories. Completed and handled operations leave the configured target absent or pointing at the verified release. After power loss or SIGKILL, recheck the original archive hash, receipts, index integrity and source retrieval before declaring readiness; the importer does not fsync every extracted source file.

Future upgrades or replacement of existing research collections require an explicit adoption/upgrade design. This first-import flow intentionally refuses those operations.
