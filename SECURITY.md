# Security policy

## Reporting a vulnerability

Please report a vulnerability privately, through GitHub: open the repository's **Security** tab and choose **Report a vulnerability** (GitHub's private vulnerability reporting). Only you and the maintainers see the report, and it becomes a draft security advisory where the fix is discussed.

Do not open a public issue, pull request or discussion for it, and do not include it in a commit message.

A useful report says:

- what an attacker can do, and what they need first (an account, an administrator, a network position);
- the steps to reproduce it, or a proof of concept, against a version or commit of this repository;
- the parts concerned (a route, a tool, a workflow, a file).

Never include real users' data, someone else's credentials, or your own API keys. If a report needs a secret to reproduce, describe it and the maintainer will ask for what is needed.

## What happens next

The maintainer acknowledges the report in the advisory, confirms or rejects it, and agrees a disclosure date with you. A confirmed vulnerability is fixed on `main` and in a release, and the advisory is published with credit to you unless you ask not to be named.

## Supported versions

Security fixes go to the `main` branch and the latest release. Older releases do not get fixes.

## Scope

In scope: the code in this repository (the backend, the frontend, the workspace runner and sandboxes, the scripts and the GitHub Actions workflows). The security boundaries MIZAN means to keep are described in [docs/amanah.md](docs/amanah.md) (outside text is data), [docs/hudud.md](docs/hudud.md) (what a program may touch), [docs/coding-workspaces.md](docs/coding-workspaces.md) and [docs/shahid.md](docs/shahid.md) (the sandboxes), and [docs/sakk.md](docs/sakk.md) (receipts).

Out of scope: vulnerabilities in a dependency that MIZAN does not make exploitable (report them upstream), a deployment's own configuration, and denial of service by sheer volume. Do not test against a deployment you do not run yourself.
