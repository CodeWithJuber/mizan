# Wara' (ورع): the package check before an install

"Leave what gives you doubt for what does not give you doubt" (Tirmidhi 2518).

A language model that invents a package name is how a squatted name gets installed:
the name sounds right, someone registers it, and the install runs their code. Before a
command MIZAN runs installs a package from PyPI or npm, Wara' (`backend/security/wara.py`,
ported from ForgeKit's dep-gate) asks for evidence about each package and decides from it.

## What it reads

The tools that run a command line: `bash`, `workspace_run` (shell only, not Python or
JavaScript code), `workspace_sandbox` `serve`, the CodeAgent's `install_package`,
`run_tests`, `lint_code` and `git_operation` (their command lines as the tools compose
them). The parser (`wara.install_targets`, shlex, no shell is run) finds:

- `pip`, `pip3`, `python -m pip`, `uv pip install`, `uv add`;
- `npm install|i|add`, `pnpm add|install|i`, `yarn add`, `yarn global add`;
- through `&&`, `;`, `|`, new lines, `sudo`/`env` wrappers, `VAR=x` prefixes and
  `bash -c '…'`; redirections (`2>&1`, `> log`) are not arguments.

Versions are stripped (`pkg==1.2`, `pkg@^1`), npm scopes and aliases are read
(`@types/node`, `alias@npm:real`), PyPI names are PEP 503 normalised. Nothing is vetted
for a local path, a URL, a `git+` source, a tarball, GitHub shorthand, a name built from
a variable (`$PKG`) or `-r requirements.txt`.

A command that points the install at another index or registry (`-i`/`--index-url`,
`--extra-index-url`, `-f`/`--find-links`, `--registry`, or `PIP_INDEX_URL=`,
`PIP_EXTRA_INDEX_URL=`, `UV_INDEX_URL=`, `npm_config_registry=` set before it on the
same line, also by `export`) is allowed with a note: its names are not asked of the
public registry at all, since a miss there proves nothing and a private name stays
private.

## Evidence

1. The package's own registry: `https://pypi.org/pypi/<name>/json`,
   `https://registry.npmjs.org/<name>`. 200 is "exists" (with the first release's date
   and the number of versions), 404/410 is "does not exist", anything else is unknown.
   A packument over 4 MB (thousands of release files: an old package) is not read.
2. OSV (`POST https://api.osv.dev/v1/query`): a `MAL-` advisory is the OpenSSF
   malicious-packages feed. Only a name its registry has is sent to OSV, so a typo, an
   invented name or a private name is told to no one else.

When the registry answers but OSV does not, or its answer is too large to read (no age
or version count), the evidence is partial: the install is allowed with a note saying
what could not be checked, and the verdict is not remembered.
3. Its name against a bundled list of popular PyPI and npm packages: one slip
   (optimal string alignment, so a transposition is one) for names under nine letters,
   two for longer ones; names under four letters are close to too many to say anything.

## The verdict

| Decision | When | What happens |
|---|---|---|
| refuse | the registry does not have the name, or OSV lists it as malicious | the tool returns `{"error": "Wara': …", "wara": {…}}`; nothing runs |
| ask | the noisy-OR score is 0.5 or more | the person is asked, in every permission mode, `auto` included; held for the owner when no one is watching; refused when no one can be asked |
| allow | everything else | the command runs as before; a score of 0.25 or more, or a registry that could not be reached, is noted on the result (`result.wara.notes`) |

The score is score = 1 − ∏(1 − wₖ·sₖ) over the signals present: youth (w 0.9,
s = 2^(−days since the first release / 30)), a thin history (w 0.2, s = 1/versions) and a
name one slip from a popular one (w 0.4, s = 1). So a package first published under about
25 days ago asks on its own; a two-month-old package with a few versions asks when its
name is one slip from a popular one; an old package close to a popular name (`attr`,
`attrs`) is only noted. Missing evidence never refuses or asks: a registry that times out
(2.5 s) or cannot be reached allows the install with a note.

Verdicts are cached in the process for six hours per (ecosystem, name); a registry that
could not be reached, or partial evidence, is asked again next time (a package whose
registry answer is over 4 MB, such as `boto3`, is therefore downloaded up to 4 MB on each
install that names it). At most eight packages are probed per
command; more are noted as not checked.

## Settings

`MIZAN_WARA` = `on` (default) | `off`, in Settings → Developer → System settings
(Agents). Tests run with it off (`tests/conftest.py`); `tests/test_wara.py` turns it on
with recorded registry answers (`httpx.MockTransport`), so no test reaches a registry.

## Limits

- It reads the command line, not what a program does: Python code that calls
  `subprocess.run(["pip", "install", …])` is not vetted.
- A brand-new legitimate package asks once per six hours until it is about a month old.
- The popular list is small and fixed; a squat of a package outside it shows only
  through youth and a thin history.
- This is a check in front of the approvals, not a sandbox boundary: installs still run
  inside the user's isolated sandbox.
