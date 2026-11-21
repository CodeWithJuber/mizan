# CI on the self-hosted runner, and where its output is

Every job of every workflow in `.github/workflows/` runs on the owner's self-hosted runner, `runs-on: [self-hosted, linux, x64, mizan]`, written literally. GitHub bills nothing for it: self-hosted runners are free, and job logs and job summaries are not billed storage.

## What may not be added

These are billed for a private repository, or could send a job to something that is:

- a GitHub-hosted runner (`ubuntu-latest`, `ubuntu-24.04`, …), or a `runs-on` with an expression, a variable or a runner group;
- artifacts: `actions/upload-artifact`, `actions/download-artifact`, `actions/upload-pages-artifact`, `actions/deploy-pages`;
- GitHub Pages (a paid feature on a private repository);
- caches: `actions/cache`, a `cache:` input on a setup action, `package-manager-cache` other than `false`, Docker's `type=gha` cache;
- GitHub Packages: `*.pkg.github.com`, logging in or pushing to `ghcr.io` (pulling public images is fine);
- CodeQL (`github/codeql-action`);
- a reusable workflow from another repository.

`scripts/ci/no-github-billing.sh` fails on each of them and prints `FILE:LINE: why`. It is the first job of `ci.yml` (every other job waits for it), the first step of `make check` (`make no-github-billing` alone), and a pre-commit hook on `.github/*.yml`. `docker/build-push-action` would also upload a build record as an artifact unless `DOCKER_BUILD_RECORD_UPLOAD=false`; the workflows build with plain `docker build` instead.

## The runner

It is GitHub's own runner image (Ubuntu 24.04, `python3` 3.12, Docker CLI with buildx and compose, `git`, `curl`, `jq`, `sshpass`, `shellcheck`, Playwright's Chromium libraries), in a container on the owner's server. It does not have the rest of GitHub's `ubuntu-24.04` image, such as Node, the `gh` CLI or extra Python versions, so the workflows set them up with `actions/setup-python` and `actions/setup-node` (`package-manager-cache: false`) and call GitHub's API with `curl` and `jq`.

- **One job at a time.** Jobs that ran side by side on GitHub run one after another.
- **Docker** talks to the runner's own Docker-in-Docker daemon. `services:` and `container:` do not work there; use `docker run` steps. Images and the build cache stay between runs.
- **Kept between runs, so free caching:** setup-python's interpreters and setup-node's Node, the pip and npm caches, Playwright's browsers, Docker images. A Python job therefore makes a fresh virtual environment in `$RUNNER_TEMP` after setup-python ("Fresh Python environment"), so it sees only what it installs, as on a new machine.
- **No GPU.** `ruh-training.yml` runs only CPU checks; real training runs on Kaggle or RunPod.

## Where the output is

A job keeps its files with `scripts/ci/keep-results.sh NAME [--optional] [--base DIR] PATH...`. They go to

```
$CI_RESULTS_DIR/<run id>-<attempt>/<NAME>/
```

on the server's disk, private to this repository and pruned after 14 days. The job summary prints that directory and each file's SHA-256. The path is the same inside the runner and on the server, so an operator copies it with `scp` as printed, then checks it with `sha256sum`.

| NAME | Written by | When |
| --- | --- | --- |
| `dist` | `ci.yml`, Build package | every run: the wheel and sdist |
| `playwright-report` | `ci.yml`, frontend | when the browser tests fail |
| `research-import-public-key`, `research-import-receipt` | the research-import operations | when they run |

Two jobs of one run hand files over through `$CI_RESULTS_DIR/<run id>-<attempt>/handoff/<name>`; none does so today. The production images are not files: CI builds them into the runner's Docker and Deploy Production sends them to the server ([deployment.md](deployment.md)).

## Earlier output

Output from before the move stays where it was on the compute server: the direct uploads under `/srv/github-actions-direct/` (packages 90 days, browser reports 7 days, research keys 1 day, receipts 7 days) and the migrated GitHub artifacts under `/srv/github-actions-archive/CodeWithJuber/mizan`, each with a `metadata.json`.

The old operation branches `ops/research-key-20261025` and `ops/research-import-20261025` still contain their own workflow copies with GitHub artifact uploads and GitHub-hosted runners. They are dormant: key preparation runs only on a push to its exact branch, and the import only on a dispatch to its exact branch. Bring a branch up to date with `main` before using it again; do not push the key-preparation branch only to update it, because that runs key preparation.
