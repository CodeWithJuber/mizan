"""Agent Skills — folders of SKILL.md instructions in the open format other agents share.

Bundled skills ship with MIZAN, users install or write their own, and a coding
project may carry project skills under ``.agents/skills/`` or ``.claude/skills/``.
The model sees each skill's name and description, loads the full instructions
with ``activate_skill`` when a task matches, and reads bundled files on demand.
"""
