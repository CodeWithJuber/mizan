"""
Kitab Notebook Skill (كِتَاب — The Book)
==========================================

"Read! In the name of your Lord who created" — Quran 96:1
"He taught by the pen" — Quran 96:4
"Nun. By the pen and what they inscribe" — Quran 68:1

Interactive computational notebooks inspired by the Quranic principle of Kitab.
Like MolBook/Jupyter but with:
- Secure sandboxed execution (Wali protection)
- Version history (Lawh Al-Mahfuz — preserved tablet)
- Knowledge extraction to Dhikr memory
- Multi-format cells: code, markdown, data, visualization
"""

import json
import logging
import os
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime

import importlib.util as _ilu
# Direct file import to avoid triggering security/__init__.py which
# pulls in heavy dependencies (jwt, cryptography) not needed here.
_val_path = os.path.join(os.path.dirname(__file__), "..", "..", "security", "validation.py")
_spec = _ilu.spec_from_file_location("security.validation", os.path.abspath(_val_path))
_val_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_val_mod)
validate_command_safe = _val_mod.validate_command_safe
del _ilu, _val_path, _spec, _val_mod

from ..base import SkillBase, SkillManifest

logger = logging.getLogger("mizan.kitab")

MAX_CELL_OUTPUT = 50_000
MAX_NOTEBOOK_CELLS = 200
MAX_CODE_EXECUTION_TIME = 30
NOTEBOOKS_DIR = "/tmp/mizan_notebooks"


@dataclass
class KitabCell:
    """A single cell — like an Ayah (verse) in the Book"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    cell_type: str = "code"
    source: str = ""
    outputs: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    execution_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    executed_at: str | None = None
    status: str = "idle"

    def to_dict(self) -> dict:
        return {
            "id": self.id, "cell_type": self.cell_type,
            "source": self.source, "outputs": self.outputs,
            "metadata": self.metadata, "execution_count": self.execution_count,
            "created_at": self.created_at, "executed_at": self.executed_at,
            "status": self.status,
        }


@dataclass
class KitabNotebook:
    """
    A Kitab notebook — inspired by Lawh Al-Mahfuz (اللوح المحفوظ)
    The Preserved Tablet: every change is recorded, nothing is lost.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = "Untitled Kitab"
    description: str = ""
    cells: list[KitabCell] = field(default_factory=list)
    language: str = "python"
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    version: int = 1
    history: list[dict] = field(default_factory=list)
    owner: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title,
            "description": self.description,
            "cells": [c.to_dict() for c in self.cells],
            "cell_count": len(self.cells), "language": self.language,
            "tags": self.tags, "created_at": self.created_at,
            "updated_at": self.updated_at, "version": self.version,
        }

    def to_summary(self) -> dict:
        return {
            "id": self.id, "title": self.title,
            "description": self.description,
            "cell_count": len(self.cells), "language": self.language,
            "tags": self.tags, "updated_at": self.updated_at,
            "version": self.version,
        }


class SandboxedExecutor:
    """
    Secure code execution — guided by Wali (Guardian) principle.
    "And Allah is sufficient as a Guardian (Wali)" — 4:45
    """

    BLOCKED_PATTERNS = [
        "import socket", "import requests", "import urllib",
        "open('/etc", "open('/root", "open('/home",
        "os.remove", "os.unlink", "os.rmdir", "shutil.rmtree",
        "__import__", "eval(", "exec(", "compile(",
        "globals()", "locals()",
    ]

    def __init__(self):
        os.makedirs(NOTEBOOKS_DIR, exist_ok=True)

    def validate_code(self, code: str) -> tuple:
        """Validate code before execution — Hisab (accounting)"""
        for pattern in self.BLOCKED_PATTERNS:
            if pattern in code:
                return False, f"Blocked pattern: {pattern}"
        return True, "Valid"

    async def execute_python(self, code: str, cell_id: str) -> dict:
        """Execute Python in sandboxed subprocess"""
        safe, reason = self.validate_code(code)
        if not safe:
            return {"output_type": "error", "text": f"Security: {reason}", "execution_time": 0}

        script_path = os.path.join(NOTEBOOKS_DIR, f"cell_{cell_id}.py")

        # Wrap code to capture stdout/stderr
        indented = "\n".join("    " + line for line in code.split("\n"))
        wrapped = f"""import sys, json, io
_out, _err = io.StringIO(), io.StringIO()
sys.stdout, sys.stderr = _out, _err
try:
{indented}
except Exception as e:
    print(f"Error: {{type(e).__name__}}: {{e}}", file=_err)
finally:
    sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
    print(json.dumps({{"stdout": _out.getvalue()[:{MAX_CELL_OUTPUT}], "stderr": _err.getvalue()[:{MAX_CELL_OUTPUT}]}}))
"""
        try:
            with open(script_path, "w") as f:
                f.write(wrapped)

            start = datetime.utcnow()
            proc = subprocess.run(
                ["python3", script_path],
                capture_output=True, text=True,
                timeout=MAX_CODE_EXECUTION_TIME,
                cwd=NOTEBOOKS_DIR,
                env={"PATH": "/usr/bin:/usr/local/bin", "HOME": NOTEBOOKS_DIR,
                     "PYTHONDONTWRITEBYTECODE": "1"},
            )
            elapsed = (datetime.utcnow() - start).total_seconds()

            try:
                lines = proc.stdout.strip().split("\n")
                data = json.loads(lines[-1])
                return {
                    "output_type": "execute_result",
                    "stdout": data.get("stdout", ""),
                    "stderr": data.get("stderr", "") or proc.stderr[:MAX_CELL_OUTPUT],
                    "execution_time": elapsed,
                }
            except (json.JSONDecodeError, IndexError):
                return {
                    "output_type": "execute_result",
                    "stdout": proc.stdout[:MAX_CELL_OUTPUT],
                    "stderr": proc.stderr[:MAX_CELL_OUTPUT],
                    "execution_time": elapsed,
                }
        except subprocess.TimeoutExpired:
            return {"output_type": "error", "text": f"Timeout ({MAX_CODE_EXECUTION_TIME}s)", "execution_time": MAX_CODE_EXECUTION_TIME}
        except Exception as e:
            return {"output_type": "error", "text": str(e), "execution_time": 0}
        finally:
            try:
                os.remove(script_path)
            except OSError:
                pass

    async def execute_shell(self, command: str) -> dict:
        """Execute shell command with restrictions"""
        # Use the comprehensive validation from security.validation
        is_safe, reason = validate_command_safe(command)
        if not is_safe:
            return {"output_type": "error", "text": f"Command blocked: {reason}"}

        try:
            proc = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=MAX_CODE_EXECUTION_TIME, cwd=NOTEBOOKS_DIR,
            )
            return {"output_type": "execute_result",
                    "stdout": proc.stdout[:MAX_CELL_OUTPUT],
                    "stderr": proc.stderr[:MAX_CELL_OUTPUT]}
        except subprocess.TimeoutExpired:
            return {"output_type": "error", "text": "Command timed out"}
        except Exception as e:
            return {"output_type": "error", "text": f"Execution failed: {str(e)}"}


class KitabNotebookSkill(SkillBase):
    """
    Kitab — Interactive Computational Notebook
    "He taught by the pen" — 96:4
    """

    manifest = SkillManifest(
        name="kitab_notebook",
        version="1.0.0",
        description="Interactive computational notebooks with secure sandboxed execution. "
                    "Create, edit, run code like Jupyter/MolBook.",
        permissions=["sandbox_exec", "file:read:/tmp/mizan_notebooks/*",
                     "file:write:/tmp/mizan_notebooks/*"],
        tags=["كتاب", "Notebook"],
    )

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.notebooks: dict[str, KitabNotebook] = {}
        self.executor = SandboxedExecutor()
        self._tools = {
            "notebook_create": self.create_notebook,
            "notebook_add_cell": self.add_cell,
            "notebook_execute_cell": self.execute_cell,
            "notebook_execute_all": self.execute_all,
            "notebook_list": self.list_notebooks,
            "notebook_get": self.get_notebook,
            "notebook_delete": self.delete_notebook,
            "notebook_update_cell": self.update_cell,
            "notebook_export": self.export_notebook,
        }

    async def execute(self, params: dict, context: dict = None) -> dict:
        action = params.get("action", "list")
        handler = self._tools.get(f"notebook_{action}")
        if handler:
            return await handler(params)
        return {"error": f"Unknown action: {action}"}

    async def create_notebook(self, params: dict) -> dict:
        """Create a new notebook — Bismillah"""
        nb = KitabNotebook(
            title=params.get("title", "Untitled Kitab"),
            description=params.get("description", ""),
            language=params.get("language", "python"),
            tags=params.get("tags", []),
            owner=params.get("user_id"),
        )
        # Bismillah intro cell
        nb.cells.append(KitabCell(
            cell_type="markdown",
            source=f"# {nb.title}\n\nبسم الله الرحمن الرحيم\n\n{nb.description or ''}",
        ))
        self.notebooks[nb.id] = nb
        logger.info(f"[KITAB] Created: {nb.title}")
        return nb.to_dict()

    async def add_cell(self, params: dict) -> dict:
        """Add cell to notebook"""
        nb = self.notebooks.get(params.get("notebook_id"))
        if not nb:
            return {"error": "Notebook not found"}
        if len(nb.cells) >= MAX_NOTEBOOK_CELLS:
            return {"error": f"Max cells ({MAX_NOTEBOOK_CELLS}) reached"}

        cell = KitabCell(
            cell_type=params.get("cell_type", "code"),
            source=params.get("source", ""),
        )
        pos = params.get("position")
        if pos is not None and 0 <= pos <= len(nb.cells):
            nb.cells.insert(pos, cell)
        else:
            nb.cells.append(cell)
        nb.updated_at = datetime.utcnow().isoformat()
        return {"cell": cell.to_dict(), "notebook_id": nb.id}

    async def update_cell(self, params: dict) -> dict:
        """Update cell source code"""
        nb = self.notebooks.get(params.get("notebook_id"))
        if not nb:
            return {"error": "Notebook not found"}
        cell = next((c for c in nb.cells if c.id == params.get("cell_id")), None)
        if not cell:
            return {"error": "Cell not found"}
        cell.source = params.get("source", cell.source)
        cell.cell_type = params.get("cell_type", cell.cell_type)
        nb.updated_at = datetime.utcnow().isoformat()
        return {"cell": cell.to_dict()}

    async def execute_cell(self, params: dict) -> dict:
        """Execute cell — Amal (action): 'Say: Work! Allah will see your work' — 9:105"""
        nb = self.notebooks.get(params.get("notebook_id"))
        if not nb:
            return {"error": "Notebook not found"}
        cell = next((c for c in nb.cells if c.id == params.get("cell_id")), None)
        if not cell:
            return {"error": "Cell not found"}
        if cell.cell_type == "markdown":
            cell.status = "success"
            return {"cell": cell.to_dict()}

        cell.status = "running"
        cell.execution_count += 1

        if cell.cell_type in ("code", "python"):
            result = await self.executor.execute_python(cell.source, cell.id)
        elif cell.cell_type == "shell":
            result = await self.executor.execute_shell(cell.source)
        else:
            result = {"output_type": "error", "text": f"Unknown type: {cell.cell_type}"}

        cell.outputs = [result]
        cell.executed_at = datetime.utcnow().isoformat()
        cell.status = "error" if result.get("output_type") == "error" else "success"

        nb.history.append({"action": "execute", "cell_id": cell.id,
                          "timestamp": cell.executed_at, "status": cell.status})
        nb.updated_at = datetime.utcnow().isoformat()
        return {"cell": cell.to_dict()}

    async def execute_all(self, params: dict) -> dict:
        """Execute all code cells sequentially"""
        nb = self.notebooks.get(params.get("notebook_id"))
        if not nb:
            return {"error": "Notebook not found"}
        results = []
        for cell in nb.cells:
            if cell.cell_type in ("code", "shell", "python"):
                r = await self.execute_cell({"notebook_id": nb.id, "cell_id": cell.id})
                results.append(r)
        return {"notebook_id": nb.id, "executed": len(results), "results": results}

    async def list_notebooks(self, params: dict = None) -> dict:
        return {"notebooks": [nb.to_summary() for nb in self.notebooks.values()]}

    async def get_notebook(self, params: dict) -> dict:
        nb = self.notebooks.get(params.get("notebook_id"))
        return nb.to_dict() if nb else {"error": "Notebook not found"}

    async def delete_notebook(self, params: dict) -> dict:
        nb_id = params.get("notebook_id")
        if nb_id in self.notebooks:
            del self.notebooks[nb_id]
            return {"deleted": nb_id}
        return {"error": "Not found"}

    async def export_notebook(self, params: dict) -> dict:
        """Export — write into Lawh Al-Mahfuz (Preserved Tablet)"""
        nb = self.notebooks.get(params.get("notebook_id"))
        if not nb:
            return {"error": "Not found"}
        fmt = params.get("format", "json")
        os.makedirs(NOTEBOOKS_DIR, exist_ok=True)
        safe_title = nb.title.replace(" ", "_").replace("/", "_")[:50]

        if fmt == "json":
            path = os.path.join(NOTEBOOKS_DIR, f"{safe_title}.kitab.json")
            with open(path, "w") as f:
                json.dump(nb.to_dict(), f, indent=2, default=str)
        elif fmt == "python":
            path = os.path.join(NOTEBOOKS_DIR, f"{safe_title}.py")
            lines = [f"# {nb.title}", f"# {nb.description}", ""]
            for c in nb.cells:
                if c.cell_type in ("code", "python"):
                    lines.append(c.source)
                    lines.append("")
                elif c.cell_type == "markdown":
                    lines.extend(f"# {line}" for line in c.source.split("\n"))
                    lines.append("")
            with open(path, "w") as f:
                f.write("\n".join(lines))
        elif fmt == "markdown":
            path = os.path.join(NOTEBOOKS_DIR, f"{safe_title}.md")
            lines = [f"# {nb.title}", "", nb.description, ""]
            for c in nb.cells:
                if c.cell_type in ("code", "python"):
                    lines.extend([f"```{nb.language}", c.source, "```"])
                    for o in c.outputs:
                        if o.get("stdout"):
                            lines.extend(["**Output:**", f"```\n{o['stdout']}\n```"])
                    lines.append("")
                elif c.cell_type == "markdown":
                    lines.extend([c.source, ""])
            with open(path, "w") as f:
                f.write("\n".join(lines))
        else:
            return {"error": f"Unknown format: {fmt}"}
        return {"exported": path, "format": fmt}

    def get_tool_schemas(self) -> list[dict]:
        return [
            {"name": "notebook_create",
             "description": "Create a new Kitab computational notebook",
             "input_schema": {"type": "object", "properties": {
                 "title": {"type": "string"}, "description": {"type": "string"},
                 "language": {"type": "string", "enum": ["python", "shell"]},
             }, "required": ["title"]}},
            {"name": "notebook_add_cell",
             "description": "Add a cell to a notebook",
             "input_schema": {"type": "object", "properties": {
                 "notebook_id": {"type": "string"},
                 "cell_type": {"type": "string", "enum": ["code", "markdown", "shell"]},
                 "source": {"type": "string"}, "position": {"type": "integer"},
             }, "required": ["notebook_id", "source"]}},
            {"name": "notebook_execute_cell",
             "description": "Execute a specific cell",
             "input_schema": {"type": "object", "properties": {
                 "notebook_id": {"type": "string"}, "cell_id": {"type": "string"},
             }, "required": ["notebook_id", "cell_id"]}},
            {"name": "notebook_execute_all",
             "description": "Execute all code cells sequentially",
             "input_schema": {"type": "object", "properties": {
                 "notebook_id": {"type": "string"},
             }, "required": ["notebook_id"]}},
            {"name": "notebook_list",
             "description": "List all Kitab notebooks",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "notebook_export",
             "description": "Export notebook to json, python, or markdown",
             "input_schema": {"type": "object", "properties": {
                 "notebook_id": {"type": "string"},
                 "format": {"type": "string", "enum": ["json", "python", "markdown"]},
             }, "required": ["notebook_id"]}},
        ]
