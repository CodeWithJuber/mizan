# Validation at the recorded research snapshot

- New application lifecycle/failure tests: 23 passed.
- New application Ruff lint: passed.
- Existing backend/tests Ruff lint: passed.
- Existing repository tests: 557 passed, 8 skipped, 2 dependency deprecation warnings.
- Full `make check`: failed at mypy before its test stage, with `backend/_version.py: Source file found twice under different module names: _version and backend._version`. Backend source was not modified by this research addition. The test stage was run independently as reported above.
- Four-variant evaluation: 96 episodes, 24 finite hand-authored scenarios.
- Repeat: 96/96 semantic outcomes matched; timing and UUID-dependent audit fields excluded.
- Separate-process CLI smoke: init, propose, approve, execute, replay, inspect; recovery reported true, replay reported already_final, audit valid.
- Hostlelo staging deployment: not performed.
- Live model call: not performed.
- Submission: not performed.
