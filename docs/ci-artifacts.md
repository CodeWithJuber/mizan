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
- **Kept between runs, so free caching:** setup-python's interpreters and setup-node's Node, the pip and npm caches, Docker images. A Python job therefore makes a fresh virtual environment in `$RUNNER_TEMP` after setup-python ("Fresh Python environment"), so it sees only what it installs, as on a new machine.
- **No GPU.** `ruh-training.yml` runs only CPU checks; real training runs on Kaggle or RunPod.

## What a run checks

Each change gets its heavy jobs once, on `main` after the merge. Agents push a pull request many times, so its runs stay quick. `scripts/ci/plan.py`, in the first job of `ci.yml`, decides what a run checks (`tests/test_ci_plan.py` pins its rules).

| | Pull request (every push to it) | Push to `main` (a merge) | Weekly, and **Run workflow** |
| --- | --- | --- | --- |
| Typecheck (`mypy`, frontend `tsc`) | yes | yes | yes |
| Unit tests | the ones its change reaches | all | all, on Python 3.11 to 3.14 |
| Heavy jobs | no | the ones the merge reaches | all |

- **Unit tests a pull request runs.** Python: the test files it changes, the test files whose imports reach a changed module (transitively, read from the source), and the test files that name a changed file. `ruh`, `bayan` and the own-research invariants run when the change reaches their tests. Vitest runs `--changed` against `main`, and every spec when the frontend's package or build configuration changes; `npm run test:utils` runs when the frontend changes. Every Python test runs when the change touches shared code (`tests/conftest.py` and what it imports, `backend/core/`, the settings, the providers, `api/main.py`, `agents/base.py`), data under `backend/`, configuration, dependencies or a workflow, deletes a module, or changes a module no test reaches. Most backend modules are imported by what `conftest.py` imports, so a backend change usually runs them all.
- **Heavy jobs** are the Docker build, the package build, the frontend build with its size budget, and `coding-workspace.yml`. On `main` the plan compares the merge with the last commit a full run of `ci.yml` passed on `main` (so a heavy job that failed on one merge runs again on the next, before Deploy Production can follow a passing run) and runs the ones whose inputs changed: the images' `COPY` lines and build contexts, the wheel's packages, `frontend/`. A change to `ci.yml` or `scripts/ci/`, a path outside every known place, or a push with no passed commit to compare with runs them all. They wait for the quick jobs, so a cheap failure stops them. The frontend's heavy steps run after that job's own checks, which spares a second `npm ci`.
- **Production images** are built on every push to `main`, as before: Deploy Production sends them. The provenance preflight runs with them.
- **The same files.** The first job also asks [`skip-duplicate-actions`](https://github.com/fkirc/skip-duplicate-actions) (open source, pinned to a commit) whether an earlier run of this workflow has passed with the files of this run, as one Git tree. The plan trusts that pass only from a full run: a push to `main`, the weekly run or a run by hand. A pull request's run checks only part, so its pass never counts. When one does count, the checking jobs are skipped and the push goes straight to `production-images`. If the action fails, everything runs: a missing answer is not a pass. Only the latest 100 runs of CI are looked at.
- **To check a branch in full before merging:** `gh workflow run ci.yml --ref <branch>`, which also lets the merge skip to the production images when the branch was up to date with `main`. Start it by hand before a release too: it tests all four Pythons.
- **No second pull request workflow.** `pr-check.yml` ran lint, the tests and the frontend build that `ci.yml` already ran. On a pull request `ci.yml`'s jobs carry its names (`Test`, `Frontend Build`) for a branch protection rule; a job the plan skips counts as passed. There is no `Lint` job any more (Not in CI); this repository's plan cannot require checks anyway (branch protection answers HTTP 403).
- **A new job** reads its line from the plan: a quick check gets `if: needs.billing.outputs.verified != 'true'` (or its own plan output), a heavy one `needs:` the quick jobs and `if: ${{ !cancelled() && !failure() && needs.billing.outputs.<job> == 'true' }}`, with its inputs added to `HEAVY` in `scripts/ci/plan.py`.

What this gives up: the heavy jobs' failures show up on `main` after the merge, not on the pull request, and a failure there holds the deploy back until a fix is merged; a test the import graph misses (an import by a computed name) is caught on `main`; coverage is uploaded only from runs of the whole suite; a break that only an older or newer Python shows is found by the weekly run; and a pass is about the files, so a dependency that changed after it is also found by the weekly run.

## Not in CI

CI runs on a small server (4 shared vCPU, 8 GB) with one runner for this repository, so since 26 November 2026 no workflow lints or starts a browser. The test files and configs stay; run them yourself before a change that needs them:

- **Python lint:** `ruff check backend/ nlp/ tests/` and `ruff format --check backend/ nlp/ tests/`, with ruff from pyproject's `[dev]` range. The pre-commit hooks (`make setup` installs them) run ruff on each commit; `make check` runs `make lint`.
- **Frontend lint:** `cd frontend && npm run lint` (oxlint with its warning cap, then the colour ratchet).
- **Frontend browser tests:** `cd frontend && npx playwright install chromium && npm run e2e` (desktop and phone, against `e2e/mock-server.mjs`).
- **Shahid's browser sandbox:** build the image and run its self-test with production's hardening:

  ```bash
  bash scripts/build_workspace_image.sh workspace-browser mizan-workspace-browser:v1 --load
  docker run --rm --network none --read-only --cap-drop ALL \
    --security-opt no-new-privileges --user 65534:65534 --shm-size 256m \
    --tmpfs /tmp:rw,nosuid,nodev,size=256m,mode=1777 --env HOME=/tmp \
    mizan-workspace-browser:v1 python3 -I /browse_selftest.py
  ```

CI still builds the browser sandbox's image on every push to `main` (`production-images`): Deploy Production sends it to the workspace runner. Nothing starts a browser in it before it ships, and a lint finding reaches `main` unless someone runs the commands above. `tests/test_ci_plan.py` fails when a workflow runs ruff, oxlint, Playwright or `browse_selftest.py` again.

## Where the output is

A job keeps its files with `scripts/ci/keep-results.sh NAME [--optional] [--base DIR] PATH...`. They go to

```
$CI_RESULTS_DIR/<run id>-<attempt>/<NAME>/
```

on the server's disk, private to this repository and pruned after 14 days. The job summary prints that directory and each file's SHA-256. The path is the same inside the runner and on the server, so an operator copies it with `scp` as printed, then checks it with `sha256sum`.

| NAME | Written by | When |
| --- | --- | --- |
| `dist` | `ci.yml`, Build package | a push to `main` that changed the package, the weekly run and a run by hand (see What a run checks): the wheel and sdist |
| `research-import-public-key`, `research-import-receipt` | the research-import operations | when they run |

Two jobs of one run hand files over through `$CI_RESULTS_DIR/<run id>-<attempt>/handoff/<name>`; none does so today. The production images are not files: CI builds them into the runner's Docker and Deploy Production sends them to the server ([deployment.md](deployment.md)).

## Earlier output

Output from before the move stays where it was on the compute server: the direct uploads under `/srv/github-actions-direct/` (packages 90 days, browser reports 7 days, research keys 1 day, receipts 7 days) and the migrated GitHub artifacts under `/srv/github-actions-archive/CodeWithJuber/mizan`, each with a `metadata.json`.

The old operation branches `ops/research-key-20261025` and `ops/research-import-20261025` still contain their own workflow copies with GitHub artifact uploads and GitHub-hosted runners. They are dormant: key preparation runs only on a push to its exact branch, and the import only on a dispatch to its exact branch. Bring a branch up to date with `main` before using it again; do not push the key-preparation branch only to update it, because that runs key preparation.
