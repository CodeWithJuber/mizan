#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Session start for coding agents working on MIZAN: keep ForgeKit's CLI on PATH at npm's
# latest release, so the hooks in .claude/settings.json (forge hooks run ...) and the
# forge-cortex MCP server in .mcp.json work. The cloud environment's setup script installs
# it before the session starts; this covers a machine that has not, and upgrades one that
# is behind. It never fails the session: without network or npm the guards are only skipped.
# FORGE_HOOKS=0 turns it off; FORGE_AUTO_UPDATE=0 keeps the installed version.
set -u

[ "${FORGE_HOOKS:-1}" = "0" ] && exit 0
command -v npm >/dev/null 2>&1 || exit 0

pkg="@codewithjuber/forgekit"
installed=""
if command -v forge >/dev/null 2>&1; then
  installed="$(forge --version 2>/dev/null | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
fi

if [ -z "$installed" ] || [ "${FORGE_AUTO_UPDATE:-1}" != "0" ]; then
  latest="$(timeout 15 npm view "$pkg" version 2>/dev/null || true)"
  if [ -z "$installed" ] || { [ -n "$latest" ] && [ "$latest" != "$installed" ]; }; then
    timeout 120 npm install -g --silent --no-fund --no-audit "$pkg@${latest:-latest}" >/dev/null 2>&1 || true
    now="$(forge --version 2>/dev/null | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
    [ -n "$now" ] && [ "$now" != "$installed" ] && echo "ForgeKit ${installed:-not installed} -> $now"
  fi
fi
exit 0
