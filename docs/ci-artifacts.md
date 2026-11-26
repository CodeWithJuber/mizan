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
- **No GPU.** No workflow installs torch or trains; real training runs on Kaggle or RunPod, and the model and training tests run by hand (Not in CI).

## What a run checks

Agents push a pull request many times, so its runs stay quick. `scripts/ci/plan.py`, in the first job of `ci.yml`, decides what a run checks (`tests/test_ci_plan.py` pins its rules).

| | Pull request (every push to it) | Push to `main` (a merge) | Weekly, and **Run workflow** |
| --- | --- | --- | --- |
| Typecheck (`mypy`, frontend `tsc`) | yes | yes | yes |
| Unit tests (pytest, `bayan`, Vitest, `test:utils`) | the ones its change reaches | all | all, pytest on Python 3.11 to 3.14 |
| Provenance preflight | no | yes | yes |
| Production images | no | yes, after every check passes | no |

- **Unit tests a pull request runs.** Python: the test files it changes, the test files whose imports reach a changed module (transitively, read from the source), and the test files that name a changed file. `bayan` runs when the change reaches its tests or the tokenizer it vendors. The model and training tests (`NOT_IN_CI` in `scripts/ci/plan.py`) are never selected, and the whole-suite run leaves out the learning-cycle files. Vitest runs `--changed` against `main`, and every spec when the frontend's package or build configuration changes; `npm run test:utils` runs when the frontend changes. Every Python test runs when the change touches shared code (`tests/conftest.py` and what it imports, `backend/core/`, the settings, the providers, `api/main.py`, `agents/base.py`), data under `backend/`, configuration, dependencies or a workflow, deletes a module, or changes a module no test reaches. Most backend modules are imported by what `conftest.py` imports, so a backend change usually runs them all.
- **Production images** are built on every push to `main`, as before: Deploy Production sends them (the backend, the frontend and the workspace runtime, runner and browser images). They are the only images and builds CI makes. The job waits for every check of the run, so a failed check holds the deploy back, and it checks the backend image's runtime dependencies (CPU-only torch, pinned pip and setuptools, the owned learning cycle) before keeping it. The frontend image runs `npm run build` itself. The provenance preflight runs with them.
- **`coding-workspace.yml`** (two images and real sandboxes, the coding workspace's security boundary) runs on `main` after a merge that changed its paths, and by hand; never on a pull request.
- **The same files.** The first job also asks [`skip-duplicate-actions`](https://github.com/fkirc/skip-duplicate-actions) (open source, pinned to a commit) whether an earlier run of this workflow has passed with the files of this run, as one Git tree. The plan trusts that pass only from a full run: a push to `main`, the weekly run or a run by hand. A pull request's run checks only part, so its pass never counts. When one does count, the checking jobs are skipped and the push goes straight to `production-images`. If the action fails, everything runs: a missing answer is not a pass. Only the latest 100 runs of CI are looked at.
- **To check a branch in full before merging:** `gh workflow run ci.yml --ref <branch>`, which also lets the merge skip to the production images when the branch was up to date with `main`. Start it by hand before a release too: it tests all four Pythons.
- **No second pull request workflow.** `pr-check.yml` ran lint, the tests and the frontend build that `ci.yml` already ran. On a pull request `ci.yml`'s jobs carry its names (`Test`, `Frontend Build`) for a branch protection rule; a job the plan skips counts as passed. There is no `Lint` job any more (Not in CI); this repository's plan cannot require checks anyway (branch protection answers HTTP 403).
- **A new job** reads its line from the plan: a check gets `if: needs.billing.outputs.verified != 'true'` (or its own plan output) and goes into `production-images`' `needs:`. Keep it light (Not in CI).

What this gives up: a failure on `main` holds the deploy back until a fix is merged; a test the import graph misses (an import by a computed name) is caught on `main`; coverage is uploaded only from runs of the whole suite; a break that only an older or newer Python shows is found by the weekly run; and a pass is about the files, so a dependency that changed after it is also found by the weekly run.

## Not in CI

CI runs on a small server (4 shared vCPU, 8 GB) with one runner for this repository, so since 26 November 2026 no workflow lints, starts a browser, installs torch to test or train a model, or builds anything a deploy does not ship. The test files and configs stay; run them yourself before a change that needs them:

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

- **Frontend build and size budget:** `cd frontend && npm run build && npm run size` (`.size-limit.json`). The production frontend image builds the bundle but does not check its size.
- **Python package:** `python -m build` (`build>=1.6.1,<2`). `release.yml` builds and checks it at each release tag.
- **Ruh model and training checks** (what `ruh-training.yml` and the `ruh` job ran): `pip install --index-url https://download.pytorch.org/whl/cpu "torch==2.14.1+cpu"`, `pip install -e ".[dev,nlp,knowledge]" datasets`, then `PYTHONPATH=backend:. pytest ruh_model/tests/ -q`. The Kaggle notebooks' code cells are checked with `python3 -c 'import json, pathlib; [compile("".join(c["source"]), str(n), "exec") for n in pathlib.Path("notebooks/kaggle").rglob("*.ipynb") for c in json.loads(n.read_text())["cells"] if c["cell_type"] == "code"]'`.
- **Owned-model research invariants and learning cycle** (what the `own-research` job ran): with CPU torch as above, `pip install -e ".[dev]" jsonschema "numpy>=2.5.3,<3"`, then `pytest tests/test_mizan_owned*.py tests/test_owned_checkpoint_activation.py tests/test_owned_learning_cycle.py tests/test_owned_learning_service.py research/own_model/tests -q`. CI's `test` job still runs `tests/test_mizan_owned*.py` without torch; the three learning-cycle files run only here.
- **Images outside a deploy:** `docker build -f docker/Dockerfile.backend.prod .` and `docker build -f docker/Dockerfile.frontend.prod ./frontend`; `production-images` builds the same files on every push to `main`.

CI still builds the browser sandbox's image on every push to `main` (`production-images`): Deploy Production sends it to the workspace runner. Nothing starts a browser in it before it ships, a lint finding reaches `main` unless someone runs the commands above, a bundle over its size budget is not caught, a package that no longer builds is found at the next release, and a model, tokenizer or learning-cycle break is found only by someone running the commands above (the production image's runtime check still imports torch, the Bayan tokenizer and the learning cycle). `tests/test_ci_plan.py` fails when a workflow runs ruff, oxlint, Playwright or `browse_selftest.py` again, pip-installs torch, runs `ruh_model/tests`, `research/own_model/tests` or the learning-cycle files, or when a CI job other than `production-images` builds an image, the package or the frontend bundle.

## Where the output is

A job keeps its files with `scripts/ci/keep-results.sh NAME [--optional] [--base DIR] PATH...`. They go to

```
$CI_RESULTS_DIR/<run id>-<attempt>/<NAME>/
```

on the server's disk, private to this repository and pruned after 14 days. The job summary prints that directory and each file's SHA-256. The path is the same inside the runner and on the server, so an operator copies it with `scp` as printed, then checks it with `sha256sum`.

| NAME | Written by | When |
| --- | --- | --- |
| `research-import-public-key`, `research-import-receipt` | the research-import operations | when they run |

Two jobs of one run hand files over through `$CI_RESULTS_DIR/<run id>-<attempt>/handoff/<name>`; none does so today. The production images are not files: CI builds them into the runner's Docker and Deploy Production sends them to the server ([deployment.md](deployment.md)).

## Earlier output

Output from before the move stays where it was on the compute server: the direct uploads under `/srv/github-actions-direct/` (packages 90 days, browser reports 7 days, research keys 1 day, receipts 7 days) and the migrated GitHub artifacts under `/srv/github-actions-archive/CodeWithJuber/mizan`, each with a `metadata.json`.

The old operation branches `ops/research-key-20261025` and `ops/research-import-20261025` still contain their own workflow copies with GitHub artifact uploads and GitHub-hosted runners. They are dormant: key preparation runs only on a push to its exact branch, and the import only on a dispatch to its exact branch. Bring a branch up to date with `main` before using it again; do not push the key-preparation branch only to update it, because that runs key preparation.
