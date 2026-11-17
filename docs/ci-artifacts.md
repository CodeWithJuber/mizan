# Retrieve CI output from compute

After each CI run, **Move CI outputs to compute** transfers its package distribution and any failed browser-test report through the pinned SSH connection. Its job summary lists each file, byte count, server path and SHA-256. A GitHub artifact stays available until the server independently reads back the persisted bytes and confirms the original digest. A failed archive job can be re-run.

On the compute host the layout is:

```text
/srv/github-actions-archive/CodeWithJuber/mizan/ci/<name>/<ci-run-id>/<artifact-id>/artifact.zip
```

An operator with SSH access can copy that file using SCP. The adjacent `metadata.json` records GitHub's original name, run ID, artifact ID, size and digest. Verify the copy with `sha256sum artifact.zip` and unpack it to retrieve the distribution or Playwright report.

The server keeps `dist` for 90 days and `playwright-report` for seven days. A daily systemd cleanup applies those limits. The relay reads the two allowlisted outputs as opaque files. It runs trusted default-branch code and never executes a PR archive.
