# Agent Skills (SKILL.md)

MIZAN reads skills in the open Agent Skills format
([agentskills.io](https://agentskills.io/specification)). A skill is a folder
containing a `SKILL.md` file, plus optional `scripts/`, `references/` and
`assets/`:

```markdown
---
name: web-app-builder
description: Build and preview a small web app. Use when the user asks for a site, page or UI.
license: MIT            # optional
allowed-tools: workspace_write workspace_run   # optional, informational
---
Step-by-step instructions the agent follows once the skill is active…
```

The rules for `name`:

- lowercase letters, digits and single hyphens, up to 64 characters
- it should match the folder name

`description` is required and can be up to 1024 characters.

Validation is lenient, as in other clients:

- Cosmetic problems become diagnostics shown in the UI.
- A skill with no description, or with unreadable frontmatter, is skipped.

## Where skills come from

Sources, highest precedence first, for a name clash:

1. **Project** (highest): `.agents/skills/<name>/` or `.claude/skills/<name>/`
   inside the chat's bound coding project. Turn this off with
   `MIZAN_PROJECT_SKILLS=false`.
2. **User**: installed or written by you. Stored in
   `$MIZAN_DATA_DIR/agent_skills/<user>/`.
3. **Bundled** (lowest): `backend/agent_skills/library/`.
   - `web-app-builder`
   - `python-project`
   - `quran-hadith-sources`: exact surah:ayah citations and graded hadith
     references

## How the agent uses them (progressive disclosure)

1. The catalog (names and descriptions) lives in the description of the
   `activate_skill` tool. The tool window shows that tool only when the request
   matches, so ordinary chats stay small.
2. `activate_skill(name)` returns the body wrapped in `<skill_content>`, with a
   list of the skill's files. The UI shows a **skill** event.
3. `read_skill_file(name, path)` reads one of those files. The path must stay
   inside the skill folder; each file is limited to 256 KB.
4. Activated skills stay active for later turns of the same chat. Context
   compaction never folds them away.

Typing `/skill-name your request` activates a skill directly.

## Installing

Open **Skills → Agent Skills (SKILL.md)**, or use the API:

| Route (`/api/agent-skills`) | Purpose |
|---|---|
| `GET /` | all skills with scope, enabled flag and diagnostics |
| `GET /{name}`, `GET /{name}/file?path=` | read a skill or one of its files |
| `POST /install` `{url}` | install from GitHub: a repo, or a `tree/<ref>/<path>` folder URL |
| `POST /upload` | install from a `.zip` or `.tar.gz` |
| `POST /` `{name, description, body}` | write a skill in the UI |
| `POST /{name}/enabled` `{enabled}` | switch a skill on or off for you |
| `DELETE /{name}` | remove a user skill |

Archive limits:

- The download is at most 30 MB.
- A skill is at most 5 MB and 200 files.
- A single file is at most 1 MB.
- An install adds at most 25 skills.
- Only regular files are extracted. Links, devices and paths that leave the
  folder are rejected.

Skill scripts are instructions for the agent. Running them still goes through
the workspace runner and the chat's approval mode.
