# Bayan PyPI Release Checklist

Release prep lives in `packages/bayan/`. **Do not publish from a dirty tree.**
Publish is an external action: it needs a JEV decision AND the user's PyPI
API token (see "Credentials" below).

## 0. Blocking decisions (resolve before publish)

- [ ] **Distribution name:** the bare `bayan` name is TAKEN on PyPI by an
  unrelated project (a weblog scraper, v1.0.0, no author contact). The
  package is prepared as **`bayan-tokenizer`** (verified available, 2026-09-29)
  with import name `bayan` (`pip install bayan-tokenizer` → `import bayan`).
  Alternatives if the user wants the bare name: `ruh-bayan`, or contact the
  `bayan` owner for a transfer (low odds — no contact listed).
- [ ] **License:** the monorepo is Apache-2.0; the Bayan package ships
  **MIT** per the product decision ("Bayan tokenizer, free + MIT"). Confirm
  the user is fine with the package being MIT while the repo stays Apache-2.0.
- [ ] **Version:** first release is `0.1.0`. Semver after that:
  `0.x.y` while in beta (breaking API changes bump `x`), `1.0.0` when the
  public API is frozen.

## 1. Pre-publish verification (every release)

From the repo root:

```bash
# 1. Re-vendor from upstream sources (fails loudly on drift)
python packages/bayan/scripts/sync_vendor.py

# 2. Lint the vendored package with its own config
cd packages/bayan
ruff check src/ tests/ scripts/
ruff format --check src/ tests/ scripts/

# 3. Build + validate
python -m build
twine check dist/*

# 4. Fresh-venv install test (no torch, no numpy in the venv)
python -m venv /tmp/bayan-venv && source /tmp/bayan-venv/bin/activate
pip install dist/bayan_tokenizer-*.whl
pip install pytest && python -m pytest tests/ -q
python - <<'EOF'
from bayan import BayanTokenizer
tok = BayanTokenizer()
print(tok.tokenize("الكتاب"))
assert [t["surface"] for t in tok.tokenize("العلم نور")] == ["العلم", "نور"]
print("round-trip OK")
EOF
deactivate
```

All four steps must be green. `twine check` must report no warnings —
a warning is a release blocker, not a suggestion.

## 2. Credentials (user-side)

- Publishing needs a **PyPI API token** (scoped to the `bayan-tokenizer`
  project). The user creates it at <https://pypi.org/manage/account/token/>.
- The token is used **once, transiently**, via `twine upload` or
  `~/.pypirc` — it is never pasted in chat, never committed, never stored
  in the repo. Prefer a trusted-publisher (OIDC) setup on the GitHub repo
  for future releases so no long-lived token exists at all.
- First upload is best done from **TestPyPI** (`twine upload --repository
  testpypi dist/*`), then install from TestPyPI in a fresh venv and re-run
  the smoke test before the real upload.

## 3. Publish commands (run only after JEV + user approval)

```bash
cd packages/bayan
python -m build && twine check dist/*
twine upload --repository testpypi dist/*   # verify first
# fresh venv: pip install -i https://test.pypi.org/simple/ bayan-tokenizer
twine upload dist/*                          # real release
git tag bayan-v0.1.0 && git push origin bayan-v0.1.0
```

## 4. Post-publish

- [ ] `pip install bayan-tokenizer` in a clean venv works; quickstart from
  the package README runs.
- [ ] GitHub Release created for the tag with the changelog entry.
- [ ] Mizan docs site links the package (`pip install bayan-tokenizer`).
- [ ] Announce only AFTER install-verified — never announce an uninstalled
  upload (lā taqfu: no claim without verification).

## 5. Known honest limits (ship in the README, never remove silently)

- Rule-based analyzer; NOT benchmarked vs CAMeL/Farasa.
- Unknown English → `<ENG:bucket>` placeholders, never invented roots.
- `with_model()` is an explicit stub (`NotAvailableError`).
- Fertility 1.0 is by construction, not a quality claim.
