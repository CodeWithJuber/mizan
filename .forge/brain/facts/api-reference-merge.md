# api-reference-merge

When two PRs both change api/main.py, the one merged second merges main in and regenerates docs/api-reference.md and docs/openapi.json with scripts/api_reference.py; never hand-merge them.
