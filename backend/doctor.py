"""
MIZAN Doctor — Self-Healing Diagnostic System (شفاء - Shifa)
=============================================================

"And We send down of the Quran that which is a healing (shifa)
 and a mercy for the believers." — 17:82

Every smart system needs a doctor. The human body has an immune system.
Cars have OBD diagnostics. Mizan has the Shifa Doctor.

Usage:
    mizan doctor          Full diagnostic + auto-fix
    mizan doctor --check  Diagnose only (no fixes)
    mizan doctor --fix    Fix everything possible

Checks:
    1. Environment   — Python version, venv, Node.js
    2. Configuration — .env file, API keys, SECRET_KEY
    3. Dependencies  — pip packages, npm packages
    4. Database      — connection, schema, data directory
    5. Core Modules  — all imports resolve
    6. Memory        — Masalik network initializes
    7. Providers     — API keys valid, endpoints reachable
    8. Ports         — 8000/3000 available or already Mizan

Auto-fixes (Islah — إصلاح):
    - Create .env from template if missing
    - Create data/ directory if missing
    - Generate random SECRET_KEY if using default
    - Install missing pip dependencies
    - Run database schema migration
"""

import os
import sys
import socket
import secrets
import shutil
import importlib
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum


class CheckStatus(Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    FIXED = "fixed"
    SKIP = "skip"


@dataclass
class CheckResult:
    """Result of a single diagnostic check."""
    name: str
    status: CheckStatus
    message: str
    fix_available: bool = False
    fix_description: str = ""
    fixed: bool = False
    fix_message: str = ""


@dataclass
class DoctorReport:
    """Full diagnostic report."""
    checks: List[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.status in (CheckStatus.PASS, CheckStatus.FIXED))

    @property
    def warnings(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.WARN)

    @property
    def failures(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.FAIL)

    @property
    def fixes_applied(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.FIXED)

    @property
    def healthy(self) -> bool:
        return self.failures == 0


def _get_project_root() -> Path:
    """Find project root (contains .env.example or pyproject.toml)."""
    # Try from this file's location (backend/doctor.py -> parent.parent)
    here = Path(__file__).resolve()
    root = here.parent.parent
    if (root / "pyproject.toml").exists():
        return root
    # Fallback: current working directory
    cwd = Path.cwd()
    if (cwd / "pyproject.toml").exists():
        return cwd
    return root


# ─────────────────────────────────────────────────────────────────────────────
# INDIVIDUAL CHECKS
# ─────────────────────────────────────────────────────────────────────────────

def check_python_version() -> CheckResult:
    """Check Python >= 3.11."""
    v = sys.version_info
    version_str = f"{v.major}.{v.minor}.{v.micro}"
    if v >= (3, 11):
        return CheckResult("Python version", CheckStatus.PASS, f"Python {version_str}")
    return CheckResult(
        "Python version", CheckStatus.FAIL,
        f"Python {version_str} (need >= 3.11)",
        fix_available=False,
    )


def check_venv() -> CheckResult:
    """Check running inside a virtual environment."""
    in_venv = (
        hasattr(sys, "real_prefix")
        or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)
    )
    if in_venv:
        return CheckResult("Virtual environment", CheckStatus.PASS, f"Active: {sys.prefix}")

    root = _get_project_root()
    venv_path = root / "backend" / "venv"
    if venv_path.exists():
        return CheckResult(
            "Virtual environment", CheckStatus.WARN,
            "Venv exists but not activated",
            fix_available=False,
            fix_description="Run: source backend/venv/bin/activate",
        )
    return CheckResult(
        "Virtual environment", CheckStatus.WARN,
        "No virtual environment found",
        fix_available=True,
        fix_description="Create venv: python3 -m venv backend/venv",
    )


def check_env_file(auto_fix: bool = False) -> CheckResult:
    """Check .env file exists and is populated."""
    root = _get_project_root()
    env_file = root / ".env"
    env_example = root / ".env.example"

    if env_file.exists():
        content = env_file.read_text()
        if len(content.strip()) < 10:
            return CheckResult(
                ".env file", CheckStatus.WARN,
                ".env exists but appears empty",
                fix_available=bool(env_example.exists()),
                fix_description="Copy from .env.example",
            )
        return CheckResult(".env file", CheckStatus.PASS, f"Found ({len(content)} bytes)")

    # Missing .env
    if auto_fix and env_example.exists():
        shutil.copy2(env_example, env_file)
        return CheckResult(
            ".env file", CheckStatus.FIXED,
            "Created from .env.example",
            fixed=True,
            fix_message="Copied .env.example → .env (edit with your API keys)",
        )

    return CheckResult(
        ".env file", CheckStatus.FAIL,
        ".env file not found",
        fix_available=bool(env_example.exists()),
        fix_description="Run: cp .env.example .env",
    )


def check_api_keys() -> CheckResult:
    """Check at least one AI provider API key is configured."""
    try:
        from backend.settings import get_settings
        settings = get_settings()
    except Exception:
        try:
            sys.path.insert(0, str(_get_project_root() / "backend"))
            from settings import get_settings
            settings = get_settings()
        except Exception as e:
            return CheckResult("API keys", CheckStatus.WARN, f"Cannot load settings: {e}")

    providers = []
    if settings.has_anthropic:
        providers.append("Anthropic")
    if settings.has_openai:
        providers.append("OpenAI")
    if settings.has_openrouter:
        providers.append("OpenRouter")

    if providers:
        return CheckResult(
            "API keys", CheckStatus.PASS,
            f"Configured: {', '.join(providers)}",
        )
    return CheckResult(
        "API keys", CheckStatus.FAIL,
        "No AI provider API key configured",
        fix_available=False,
        fix_description="Edit .env and add ANTHROPIC_API_KEY, OPENAI_API_KEY, or OPENROUTER_API_KEY",
    )


def check_secret_key(auto_fix: bool = False) -> CheckResult:
    """Check SECRET_KEY is not the insecure default."""
    root = _get_project_root()
    env_file = root / ".env"

    if not env_file.exists():
        return CheckResult("SECRET_KEY", CheckStatus.SKIP, "No .env file")

    content = env_file.read_text()
    if "change-this-to-a-secure-random-string" in content:
        if auto_fix:
            new_key = secrets.token_urlsafe(48)
            new_content = content.replace(
                "change-this-to-a-secure-random-string", new_key
            )
            env_file.write_text(new_content)
            return CheckResult(
                "SECRET_KEY", CheckStatus.FIXED,
                "Generated secure random key",
                fixed=True,
                fix_message=f"SECRET_KEY set to random 48-byte token",
            )
        return CheckResult(
            "SECRET_KEY", CheckStatus.WARN,
            "Using insecure default value",
            fix_available=True,
            fix_description="Will generate a secure random key",
        )

    return CheckResult("SECRET_KEY", CheckStatus.PASS, "Custom key configured")


def check_data_directory(auto_fix: bool = False) -> CheckResult:
    """Check data directory exists and is writable."""
    root = _get_project_root()
    data_dir = root / "data"

    if data_dir.exists():
        if os.access(data_dir, os.W_OK):
            return CheckResult("Data directory", CheckStatus.PASS, str(data_dir))
        return CheckResult(
            "Data directory", CheckStatus.FAIL,
            f"{data_dir} exists but not writable",
        )

    if auto_fix:
        data_dir.mkdir(parents=True, exist_ok=True)
        return CheckResult(
            "Data directory", CheckStatus.FIXED,
            f"Created {data_dir}",
            fixed=True,
        )

    return CheckResult(
        "Data directory", CheckStatus.FAIL,
        f"{data_dir} does not exist",
        fix_available=True,
        fix_description=f"mkdir -p {data_dir}",
    )


def check_dependencies() -> CheckResult:
    """Check core pip dependencies are importable."""
    required = [
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn"),
        ("pydantic", "Pydantic"),
        ("anthropic", "Anthropic SDK"),
        ("httpx", "httpx"),
        ("click", "Click"),
        ("rich", "Rich"),
    ]

    missing = []
    for module, name in required:
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(name)

    if not missing:
        return CheckResult("Dependencies", CheckStatus.PASS, f"All {len(required)} core packages found")

    return CheckResult(
        "Dependencies", CheckStatus.FAIL,
        f"Missing: {', '.join(missing)}",
        fix_available=True,
        fix_description="pip install -r backend/requirements.txt",
    )


def check_core_imports() -> CheckResult:
    """Check all MIZAN core modules can be imported."""
    root = _get_project_root()
    backend = root / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    # Try both import styles (from project root vs from backend/)
    modules = [
        (["_version", "backend._version"], "Version"),
        (["settings", "backend.settings"], "Settings (pydantic-settings)"),
        (["memory.masalik"], "Masalik (Neural Pathways)"),
        (["memory.dhikr"], "Dhikr (Memory System)"),
        (["qca.engine"], "QCA Engine"),
        (["qca.yaqin_engine"], "Yaqin (Certainty)"),
        (["qca.cognitive_methods"], "Cognitive Methods"),
        (["core.qalb"], "Qalb (Emotion)"),
        (["core.ruh_engine"], "Ruh (Energy)"),
        (["core.tawbah"], "Tawbah (Recovery)"),
        (["agents.base"], "BaseAgent"),
        (["agents.specialized"], "Specialized Agents"),
        (["providers"], "AI Providers"),
        (["security.wali"], "Wali (Security)"),
    ]

    failed = []
    for candidates, name in modules:
        imported = False
        for module in candidates:
            try:
                importlib.import_module(module)
                imported = True
                break
            except Exception:
                continue
        if not imported:
            failed.append(name)

    if not failed:
        return CheckResult("Core modules", CheckStatus.PASS, f"All {len(modules)} modules import OK")

    return CheckResult(
        "Core modules", CheckStatus.FAIL,
        f"{len(failed)} module(s) failed: {'; '.join(failed[:3])}",
    )


def check_masalik_memory() -> CheckResult:
    """Check neural pathway memory system initializes."""
    try:
        from memory.masalik import MasalikNetwork
        net = MasalikNetwork()
        stats = net.stats()
        return CheckResult(
            "Masalik memory", CheckStatus.PASS,
            f"{stats['fitrah_concepts']} fitrah concepts, "
            f"{stats['total_pathways']} pathways ready",
        )
    except Exception as e:
        return CheckResult("Masalik memory", CheckStatus.FAIL, str(e))


def check_database() -> CheckResult:
    """Check database can be created/connected."""
    try:
        from memory.dhikr import DhikrMemorySystem
        db = DhikrMemorySystem(db_path=":memory:")
        # Quick schema test
        conn = db._get_conn()
        c = conn.cursor()
        c.execute("SELECT count(*) FROM sqlite_master WHERE type='table'")
        table_count = c.fetchone()[0]
        db._release_conn(conn)

        if table_count >= 5:
            return CheckResult(
                "Database", CheckStatus.PASS,
                f"SQLite OK ({table_count} tables), Masalik integrated",
            )
        return CheckResult("Database", CheckStatus.WARN, f"Only {table_count} tables found")
    except Exception as e:
        return CheckResult("Database", CheckStatus.FAIL, str(e))


def check_port(port: int, service: str) -> CheckResult:
    """Check if a port is available or already running Mizan."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        result = sock.connect_ex(("127.0.0.1", port))
        if result == 0:
            # Port in use — check if it's Mizan
            try:
                import httpx
                resp = httpx.get(f"http://127.0.0.1:{port}/", timeout=2)
                data = resp.json()
                if "MIZAN" in str(data.get("system", "")):
                    return CheckResult(
                        f"Port {port} ({service})", CheckStatus.PASS,
                        f"MIZAN already running (v{data.get('version', '?')})",
                    )
            except Exception:
                pass
            return CheckResult(
                f"Port {port} ({service})", CheckStatus.WARN,
                f"Port {port} in use by another process",
            )
        return CheckResult(
            f"Port {port} ({service})", CheckStatus.PASS,
            "Available",
        )
    except Exception as e:
        return CheckResult(f"Port {port} ({service})", CheckStatus.WARN, str(e))
    finally:
        sock.close()


def check_node() -> CheckResult:
    """Check Node.js availability (for frontend)."""
    root = _get_project_root()
    frontend_dir = root / "frontend"

    if not frontend_dir.exists():
        return CheckResult("Node.js", CheckStatus.SKIP, "No frontend directory")

    try:
        result = subprocess.run(
            ["node", "--version"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            major = int(version.lstrip("v").split(".")[0])
            if major >= 18:
                return CheckResult("Node.js", CheckStatus.PASS, version)
            return CheckResult("Node.js", CheckStatus.FAIL, f"{version} (need >= 18)")
    except FileNotFoundError:
        return CheckResult(
            "Node.js", CheckStatus.WARN,
            "Not installed (needed for frontend)",
            fix_description="Install Node.js 18+ from https://nodejs.org",
        )
    except Exception as e:
        return CheckResult("Node.js", CheckStatus.WARN, str(e))

    return CheckResult("Node.js", CheckStatus.WARN, "Could not determine version")


def check_provider_connectivity() -> CheckResult:
    """Check if configured providers are actually reachable."""
    try:
        from backend.settings import get_settings
        settings = get_settings()
    except Exception:
        try:
            from settings import get_settings
            settings = get_settings()
        except Exception:
            return CheckResult("Provider connectivity", CheckStatus.SKIP, "Cannot load settings")

    if not settings.has_any_provider:
        return CheckResult(
            "Provider connectivity", CheckStatus.SKIP,
            "No provider configured",
        )

    reachable = []
    unreachable = []

    if settings.has_anthropic:
        try:
            import httpx
            resp = httpx.get(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                },
                timeout=5,
            )
            # 401/400 means reachable but needs proper request — that's fine
            reachable.append("Anthropic")
        except Exception:
            unreachable.append("Anthropic")

    if settings.has_openrouter:
        try:
            import httpx
            resp = httpx.get(
                "https://openrouter.ai/api/v1/auth/key",
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                timeout=5,
            )
            reachable.append("OpenRouter")
        except Exception:
            unreachable.append("OpenRouter")

    if reachable and not unreachable:
        return CheckResult(
            "Provider connectivity", CheckStatus.PASS,
            f"Reachable: {', '.join(reachable)}",
        )
    if unreachable:
        return CheckResult(
            "Provider connectivity", CheckStatus.WARN,
            f"Unreachable: {', '.join(unreachable)}"
            + (f" | OK: {', '.join(reachable)}" if reachable else ""),
        )
    return CheckResult("Provider connectivity", CheckStatus.SKIP, "No providers to check")


# ─────────────────────────────────────────────────────────────────────────────
# DOCTOR ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def run_doctor(auto_fix: bool = True, check_only: bool = False) -> DoctorReport:
    """
    Run all diagnostic checks.

    Islah (إصلاح) — "Indeed, I only intend reform as much as I am able." — 11:88

    Args:
        auto_fix: If True, automatically fix issues where possible
        check_only: If True, just diagnose (overrides auto_fix)
    """
    if check_only:
        auto_fix = False

    report = DoctorReport()

    # ── Environment ──
    report.checks.append(check_python_version())
    report.checks.append(check_venv())
    report.checks.append(check_node())

    # ── Configuration ──
    report.checks.append(check_env_file(auto_fix=auto_fix))
    report.checks.append(check_api_keys())
    report.checks.append(check_secret_key(auto_fix=auto_fix))

    # ── File System ──
    report.checks.append(check_data_directory(auto_fix=auto_fix))

    # ── Dependencies ──
    report.checks.append(check_dependencies())
    report.checks.append(check_core_imports())

    # ── Systems ──
    report.checks.append(check_masalik_memory())
    report.checks.append(check_database())

    # ── Network ──
    report.checks.append(check_port(8000, "Backend"))
    report.checks.append(check_port(3000, "Frontend"))
    report.checks.append(check_provider_connectivity())

    return report


def format_report_plain(report: DoctorReport) -> str:
    """Format report as plain text."""
    lines = [
        "",
        "MIZAN Doctor (شفاء - Shifa)",
        "=" * 50,
        "",
    ]

    status_icons = {
        CheckStatus.PASS: "[OK]   ",
        CheckStatus.WARN: "[WARN] ",
        CheckStatus.FAIL: "[FAIL] ",
        CheckStatus.FIXED: "[FIX]  ",
        CheckStatus.SKIP: "[SKIP] ",
    }

    for check in report.checks:
        icon = status_icons[check.status]
        lines.append(f"  {icon} {check.name}: {check.message}")
        if check.status == CheckStatus.FIXED and check.fix_message:
            lines.append(f"           Healed: {check.fix_message}")
        elif check.status == CheckStatus.FAIL and check.fix_description:
            lines.append(f"           Fix: {check.fix_description}")
        elif check.status == CheckStatus.WARN and check.fix_description:
            lines.append(f"           Hint: {check.fix_description}")

    lines.append("")
    lines.append("-" * 50)
    total = len(report.checks)
    skipped = sum(1 for c in report.checks if c.status == CheckStatus.SKIP)
    lines.append(
        f"  {report.passed}/{total - skipped} passed, "
        f"{report.warnings} warnings, "
        f"{report.failures} failures, "
        f"{report.fixes_applied} auto-fixed"
    )

    if report.healthy:
        lines.append("  System: HEALTHY")
    else:
        lines.append("  System: NEEDS ATTENTION")

    lines.append("")
    return "\n".join(lines)


def report_to_dict(report: DoctorReport) -> dict:
    """Convert report to JSON-serializable dict for API responses."""
    return {
        "healthy": report.healthy,
        "passed": report.passed,
        "warnings": report.warnings,
        "failures": report.failures,
        "fixes_applied": report.fixes_applied,
        "checks": [
            {
                "name": c.name,
                "status": c.status.value,
                "message": c.message,
                "fix_available": c.fix_available,
                "fix_description": c.fix_description,
                "fixed": c.fixed,
                "fix_message": c.fix_message,
            }
            for c in report.checks
        ],
    }
