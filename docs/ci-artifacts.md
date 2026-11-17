# Retrieve CI output from compute

The CI package build and failed browser-test report upload their ZIPs directly to the compute server. Research-import jobs store their public key or receipt through the same service. Each job summary records the private SSH path, original SHA-256, byte count and expiry after the server has verified and persisted the bytes.

The uploader authenticates with a short-lived GitHub OIDC token. Server policy limits it to the repository, workflow and output type. Storage is immutable within each run, attempt and output slot. The service grants write access only to that output.

An operator with SSH access can copy the recorded file using SCP. Verify the downloaded file with `sha256sum artifact.zip`, compare it with the digest in the job summary, and unpack it to retrieve the distribution or report.

Package distributions remain for 90 days and browser reports for seven days. Research public keys remain for one day and import receipts for seven days. Historical migrated output keeps its existing retention.

GitHub withholds OIDC access from fork-origin and Dependabot pull requests under the default read-only permission policy. Their checks still run and emit console results, and the upload step reports that downloadable output is unavailable. The workflow does not request extra fork permissions.

The original migration copies remain under `/srv/github-actions-archive/CodeWithJuber/mizan`. Their adjacent `metadata.json` records GitHub's original artifact name, run ID, artifact ID, size and digest.
