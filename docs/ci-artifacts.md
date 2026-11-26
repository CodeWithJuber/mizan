# CI on GitHub-hosted runners

Every job of every workflow in `.github/workflows/` runs on a standard GitHub-hosted runner, `runs-on: ubuntu-24.04`, written literally. Standard hosted runners are free for a public repository.

## The rules for a public repository

`scripts/ci/public-repo-guard.sh` fails on each of these and prints `FILE:LINE: why`. It is the first step of `ci.yml` (every other job waits for it), the first step of `make check` (`make public-repo-guard` alone), and a pre-commit hook on `.github/*.yml`. `tests/test_public_repo_guard.py` pins it.

- **A standard GitHub-hosted runner only.** A self-hosted runner would run any fork's pull request on the machine it lives on. A larger runner is billed, and a label list, a runner group, an expression or a variable could pick either.
- **No pull request code with secrets.** A workflow started by `pull_request_target` runs with this repository's token and secrets, so it never checks out code and never names the pull request's head.
- **Every action pinned to a full commit SHA**, with its version in a comment (`uses: actions/checkout@<sha> # v7.0.1`). A tag can be moved. Dependabot (`.github/dependabot.yml`) proposes updates weekly and keeps the pins.

The tests also pin that every workflow has `permissions: contents: read` at the top (a job asks for more only where it needs it), that every checkout sets `persist-credentials: false`, and that the workflows which reach production never run on a pull request, wait for the `production` environment and connect with a key.

**Job logs are public.** Nothing a job prints may identify the production server or hold user data. Secrets are masked by GitHub; the operations workflows keep their reports on the server (Operations, below).

## What a run checks

Agents push a pull request many times, so its runs stay quick. `scripts/ci/plan.py`, in the first job of `ci.yml`, decides what a run checks (`tests/test_ci_plan.py` pins its rules).

| | Pull request (every push to it) | Push to `main` (a merge) | Weekly, and **Run workflow** |
| --- | --- | --- | --- |
| Typecheck (`mypy`, frontend `tsc`) | yes | yes | yes |
| Unit tests (pytest, `bayan`, Vitest, `test:utils`) | the ones its change reaches | all | all, pytest on Python 3.11 to 3.14 |
| Lint (`ruff check`, `ruff format --check`, `npm run lint`: oxlint and the colour ratchet) | no | yes | yes |
| Provenance preflight | no | yes | yes |
| Frontend build, size budget, Playwright e2e (desktop and phone, mocked API) | no | yes | yes |
| Docker images, the runner's import check, Shahid's browser self-test | no | yes, after every check passes | yes |
| Model and training tests (`ruh_model/tests`, `research/own_model/tests`, the learning-cycle tests; CPU torch) | no | no | yes |

- **Unit tests a pull request runs.** Python: the test files it changes, the test files whose imports reach a changed module (transitively, read from the source), and the test files that name a changed file. `bayan` runs when the change reaches its tests or the tokenizer it vendors. The model and training tests (`TRAINING_TESTS` in `scripts/ci/plan.py`) are never selected, and the whole-suite run leaves out the learning-cycle files, which the weekly `own-research` job runs. Vitest runs `--changed` against `main`, and every spec when the frontend's package or build configuration changes; `npm run test:utils` runs when the frontend changes. Every Python test runs when the change touches shared code (`tests/conftest.py` and what it imports, `backend/core/`, the settings, the providers, `api/main.py`, `agents/base.py`), data under `backend/`, configuration, dependencies or a workflow, deletes a module, or changes a module no test reaches. Most backend modules are imported by what `conftest.py` imports, so a backend change usually runs them all.
- **The images** (`images` job): the production backend and frontend images, and the workspace runtime, runner and browser images, built as a check. The job waits for every check of the run, so a failed check holds the deploy back. It checks the backend image's runtime dependencies (CPU-only torch, pinned pip and setuptools, the owned learning cycle), that the runner image imports without Docker access, and runs Shahid's browser self-test and the egress proxy's public mode with production's hardening. Nothing is pushed: Deploy Production builds the commit's images itself ([deployment.md](deployment.md)).
- **`coding-workspace.yml`** (two images and real sandboxes, the coding workspace's security boundary) runs on `main` after a merge that changed its paths, and by hand; never on a pull request.
- **`security.yml`**: dependency review on pull requests (fails on a new dependency with a high or critical advisory) gitleaks on pull requests and pushes to `main` (`.gitleaks.toml` lists the files whose digests and fixtures look like keys), and `reuse lint` (every file has a copyright and a licence in `REUSE.toml`, and every licence its text in `LICENSES/`). **`scorecard.yml`**: OpenSSF Scorecard on pushes to `main` and weekly, published to the code scanning page.
- **The same files.** The first job also asks [`skip-duplicate-actions`](https://github.com/fkirc/skip-duplicate-actions) (pinned to a commit) whether an earlier run of this workflow has passed with the files of this run, as one Git tree. The plan trusts that pass only from a full run: a push to `main`, the weekly run or a run by hand. A pull request's run checks only part, so its pass never counts. When one does count, the checking jobs are skipped and Deploy Production follows the green run. If the action fails, everything runs: a missing answer is not a pass. Only the latest 100 runs of CI are looked at.
- **To check a branch in full before merging:** `gh workflow run ci.yml --ref <branch>`. Start it by hand before a release too: it tests all four Pythons and the training tests.
- **No second pull request workflow.** On a pull request `ci.yml`'s jobs carry the names a branch protection rule may require (`Test`, `Frontend Build`); a job the plan skipped counts as passed.
- **A new job** reads its line from the plan: a check gets `if: needs.plan.outputs.verified != 'true'` (or its own plan output) and goes into the `images` job's `needs:`.

What this gives up: a pull request is not linted and its browser tests and images are not built until it merges, so a lint finding or a broken image holds the deploy back until a fix is merged; a test the import graph misses (an import by a computed name) is caught on `main`; coverage is uploaded only from runs of the whole suite; a break that only an older or newer Python, or the model and training tests, shows is found by the weekly run; and a pass is about the files, so a dependency that changed after it is also found by the weekly run. To lint before merging, run `make lint` and `cd frontend && npm run lint`, or let the pre-commit hooks do it.

## Where the output is

Job logs and summaries, in the repository's Actions tab: public. A failed Playwright run keeps its report as the `playwright-report` artifact for 7 days. Coverage goes to Codecov. Nothing else is kept as an artifact.

## Operations

Deploy Production, Auto Release and the dated `ops/*` operations (`chat-stream-diagnostics.yml`, `research-import*.yml`, `workspace-runner-*.yml`) reach the production server. They run on a hosted runner in the `production` environment, so a required reviewer approves each run and only those jobs see the environment's secrets: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY` (a private key for that user, nothing else), `DEPLOY_KNOWN_HOSTS` (the server's pinned host key line) and `DEPLOY_PUBLIC_URL` (the site's `https://` origin). The key and host key are written to the job's private temporary directory and removed at its end; `StrictHostKeyChecking=yes` and `BatchMode=yes` refuse an unknown host or a password prompt.

The operations are completed, kept as a record, and run only on a push to (or a dispatch of) their exact dated branch. Their reports (diagnostics, the research import's public key and receipt) are written root-only to `/var/lib/mizan-deploy/reports/<name>-<run id>-<attempt>.json[l]` on the server; the log shows only that path and its SHA-256, and an operator copies the file with `scp`. Bring an operation branch up to date with `main` before using it again; do not push the key-preparation branch only to update it, because that runs key preparation.
