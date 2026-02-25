"""
Raqib Security Scanner (رَقِيب — The Watcher)
================================================

"Not a word does he utter but there is a watcher (Raqib) ready" — Quran 50:18
"And He is the All-Hearing, the All-Seeing (Basir)" — Quran 42:11

Comprehensive security scanning inspired by the Quranic concept of Raqib:
- Code vulnerability scanning (OWASP Top 10)
- Dependency audit (known CVEs)
- Secret detection (leaked credentials)
- Configuration security review
- Container image scanning
- Compliance reporting

Every action has a Raqib watching — our scanner watches over code integrity.
"""

import uuid
import json
import os
import re
import logging
import subprocess
from datetime import datetime
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field

from ..base import SkillBase, SkillManifest

logger = logging.getLogger("mizan.raqib")


@dataclass
class SecurityFinding:
    """A security finding — like an observation from the Raqib"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    severity: str = "info"      # critical, high, medium, low, info
    category: str = ""          # secret_leak, vulnerability, misconfiguration, dependency
    title: str = ""
    description: str = ""
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    code_snippet: Optional[str] = None
    recommendation: str = ""
    cwe_id: Optional[str] = None
    cvss_score: Optional[float] = None

    def to_dict(self) -> Dict:
        d = {
            "id": self.id, "severity": self.severity,
            "category": self.category, "title": self.title,
            "description": self.description,
            "recommendation": self.recommendation,
        }
        if self.file_path:
            d["file_path"] = self.file_path
        if self.line_number is not None:
            d["line_number"] = self.line_number
        if self.code_snippet:
            d["code_snippet"] = self.code_snippet
        if self.cwe_id:
            d["cwe_id"] = self.cwe_id
        if self.cvss_score is not None:
            d["cvss_score"] = self.cvss_score
        return d


@dataclass
class ScanReport:
    """Complete scan report — Shahid (witness) testimony"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    scan_type: str = ""
    target: str = ""
    findings: List[SecurityFinding] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None
    summary: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "scan_type": self.scan_type,
            "target": self.target,
            "findings": [f.to_dict() for f in self.findings],
            "finding_count": len(self.findings),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "summary": self.summary,
        }


# === SECRET PATTERNS — Things that should NEVER be in code ===
SECRET_PATTERNS = [
    (r'(?i)(?:api[_-]?key|apikey)\s*[:=]\s*["\']([a-zA-Z0-9_\-]{20,})["\']', "API Key", "high"),
    (r'(?i)(?:secret[_-]?key|secretkey)\s*[:=]\s*["\']([a-zA-Z0-9_\-]{20,})["\']', "Secret Key", "critical"),
    (r'(?i)(?:password|passwd|pwd)\s*[:=]\s*["\']([^\'"]{8,})["\']', "Password", "critical"),
    (r'(?i)(?:token)\s*[:=]\s*["\']([a-zA-Z0-9_\-\.]{20,})["\']', "Token", "high"),
    (r'sk-[a-zA-Z0-9]{48,}', "OpenAI API Key", "critical"),
    (r'sk-ant-[a-zA-Z0-9\-]{80,}', "Anthropic API Key", "critical"),
    (r'ghp_[a-zA-Z0-9]{36}', "GitHub Personal Access Token", "critical"),
    (r'gho_[a-zA-Z0-9]{36}', "GitHub OAuth Token", "critical"),
    (r'glpat-[a-zA-Z0-9\-]{20,}', "GitLab Token", "critical"),
    (r'AKIA[0-9A-Z]{16}', "AWS Access Key", "critical"),
    (r'(?i)aws[_-]?secret[_-]?access[_-]?key\s*[:=]\s*["\']([^\'"]{20,})["\']', "AWS Secret Key", "critical"),
    (r'xox[bpoas]-[a-zA-Z0-9\-]{10,}', "Slack Token", "high"),
    (r'-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----', "Private Key", "critical"),
    (r'(?i)(?:mysql|postgres|mongodb)://[^:]+:[^@]+@', "Database URL with credentials", "critical"),
    (r'(?i)bearer\s+[a-zA-Z0-9_\-\.]{20,}', "Bearer Token", "high"),
    (r'(?i)basic\s+[a-zA-Z0-9+/=]{20,}', "Basic Auth Credentials", "high"),
]

# === VULNERABILITY PATTERNS (OWASP Top 10) ===
VULN_PATTERNS = {
    "python": [
        (r'eval\s*\(', "Dangerous eval() usage", "CWE-95", "high",
         "Use ast.literal_eval() for safe evaluation or avoid eval entirely"),
        (r'exec\s*\(', "Dangerous exec() usage", "CWE-95", "high",
         "Avoid exec(). Use subprocess with argument lists instead"),
        (r'os\.system\s*\(', "OS command injection risk", "CWE-78", "high",
         "Use subprocess.run() with argument lists instead of os.system()"),
        (r'subprocess\.\w+\([^)]*shell\s*=\s*True', "Shell injection risk", "CWE-78", "high",
         "Use subprocess with shell=False and argument lists"),
        (r'pickle\.loads?\s*\(', "Insecure deserialization", "CWE-502", "high",
         "Use json or other safe serialization formats"),
        (r'yaml\.load\s*\([^)]*(?!Loader)', "Unsafe YAML loading", "CWE-502", "medium",
         "Use yaml.safe_load() instead of yaml.load()"),
        (r'\.format\s*\(.*\)|f["\'].*\{.*\}', "Potential format string injection in SQL", "CWE-89", "info",
         "Use parameterized queries for database operations"),
        (r'cursor\.execute\s*\([^)]*%\s', "SQL injection via string formatting", "CWE-89", "critical",
         "Use parameterized queries: cursor.execute('SELECT ? WHERE ?', (val1, val2))"),
        (r'cursor\.execute\s*\([^)]*\.format\s*\(', "SQL injection via .format()", "CWE-89", "critical",
         "Use parameterized queries instead of string formatting"),
        (r'cursor\.execute\s*\(f["\']', "SQL injection via f-string", "CWE-89", "critical",
         "Use parameterized queries instead of f-strings in SQL"),
        (r'allow_origins\s*=\s*\[\s*["\']?\*["\']?\s*\]', "CORS wildcard origin", "CWE-942", "medium",
         "Specify explicit allowed origins instead of wildcard"),
        (r'verify\s*=\s*False', "SSL verification disabled", "CWE-295", "medium",
         "Enable SSL verification in production"),
        (r'debug\s*=\s*True', "Debug mode enabled", "CWE-489", "low",
         "Disable debug mode in production"),
        (r'SECRET_KEY\s*=\s*["\'][^"\']{1,20}["\']', "Weak secret key", "CWE-330", "medium",
         "Use a strong random secret key (32+ characters)"),
        (r'hashlib\.md5\s*\(', "Weak hashing (MD5)", "CWE-328", "medium",
         "Use SHA-256 or stronger hashing algorithms"),
        (r'hashlib\.sha1\s*\(', "Weak hashing (SHA-1)", "CWE-328", "low",
         "Use SHA-256 or stronger hashing algorithms"),
    ],
    "javascript": [
        (r'eval\s*\(', "Dangerous eval()", "CWE-95", "high",
         "Use JSON.parse() or Function constructor safely"),
        (r'innerHTML\s*=', "XSS via innerHTML", "CWE-79", "high",
         "Use textContent or sanitize HTML before insertion"),
        (r'document\.write\s*\(', "XSS via document.write", "CWE-79", "high",
         "Use DOM manipulation methods instead"),
        (r'dangerouslySetInnerHTML', "XSS risk in React", "CWE-79", "medium",
         "Sanitize HTML content with DOMPurify before using"),
        (r'window\.location\s*=.*\+', "Open redirect risk", "CWE-601", "medium",
         "Validate redirect URLs against an allowlist"),
        (r'\.query\s*\([^)]*\+|\.query\s*\(`', "SQL injection in Node.js", "CWE-89", "high",
         "Use parameterized queries or an ORM"),
        (r'cors\(\s*\)', "CORS with no restrictions", "CWE-942", "medium",
         "Configure specific origin restrictions"),
    ],
}

# === DEPENDENCY VULNERABILITY DATABASE (sample) ===
KNOWN_VULN_DEPS = {
    "python": {
        "flask": {"below": "2.3.0", "cve": "CVE-2023-30861", "severity": "high",
                  "desc": "Cookie parsing vulnerability"},
        "django": {"below": "4.2.0", "cve": "CVE-2023-31047", "severity": "high",
                   "desc": "Multiple file upload bypass"},
        "requests": {"below": "2.31.0", "cve": "CVE-2023-32681", "severity": "medium",
                     "desc": "Proxy-Authorization header leak"},
        "pyyaml": {"below": "6.0", "cve": "CVE-2020-14343", "severity": "critical",
                   "desc": "Arbitrary code execution via yaml.load()"},
        "pillow": {"below": "10.0.0", "cve": "CVE-2023-44271", "severity": "high",
                   "desc": "Denial of service via large images"},
        "cryptography": {"below": "41.0.0", "cve": "CVE-2023-38325", "severity": "medium",
                        "desc": "Certificate validation bypass"},
        "urllib3": {"below": "2.0.7", "cve": "CVE-2023-45803", "severity": "medium",
                   "desc": "Request body leaked on redirect"},
    },
    "javascript": {
        "lodash": {"below": "4.17.21", "cve": "CVE-2021-23337", "severity": "high",
                   "desc": "Prototype pollution"},
        "express": {"below": "4.18.2", "cve": "CVE-2022-24999", "severity": "high",
                    "desc": "Open redirect vulnerability"},
        "jsonwebtoken": {"below": "9.0.0", "cve": "CVE-2022-23529", "severity": "critical",
                        "desc": "Token verification bypass"},
    },
}

# === CONFIG SECURITY CHECKS ===
CONFIG_CHECKS = [
    {"file": ".env", "pattern": r'(?i)(password|secret|key|token)\s*=\s*\S+',
     "title": ".env file with secrets", "severity": "high",
     "recommendation": "Ensure .env is in .gitignore and not committed"},
    {"file": ".gitignore", "check_missing": True,
     "title": "Missing .gitignore", "severity": "medium",
     "recommendation": "Add .gitignore to prevent accidental commits of secrets"},
    {"file": "docker-compose.yml", "pattern": r'(?i)password:\s*\S+',
     "title": "Hardcoded password in docker-compose", "severity": "high",
     "recommendation": "Use environment variables or Docker secrets"},
    {"file": "Dockerfile", "pattern": r'(?i)(?:ENV|ARG)\s+(?:.*PASSWORD|.*SECRET|.*KEY)=',
     "title": "Secrets in Dockerfile", "severity": "high",
     "recommendation": "Use Docker secrets or build args that aren't persisted"},
]


class RaqibScannerSkill(SkillBase):
    """
    Raqib — Comprehensive Security Scanner
    "Not a word does he utter but there is a watcher (Raqib) ready" — 50:18
    """

    manifest = SkillManifest(
        name="raqib_scanner",
        version="1.0.0",
        description="Security scanner: vulnerability detection, secret scanning, "
                    "dependency audit, OWASP Top 10 checks, compliance reporting.",
        permissions=["file:read:*", "shell:pip", "shell:npm"],
        tags=["رقيب", "Security"],
    )

    def __init__(self, config: Dict = None):
        super().__init__(config)
        self.scan_history: List[ScanReport] = []
        self._tools = {
            "security_scan_full": self.full_scan,
            "security_scan_secrets": self.scan_secrets,
            "security_scan_code": self.scan_code_vulnerabilities,
            "security_scan_deps": self.scan_dependencies,
            "security_scan_config": self.scan_configuration,
            "security_scan_docker": self.scan_docker,
            "security_report": self.get_report,
            "security_history": self.get_history,
        }

    async def execute(self, params: Dict, context: Dict = None) -> Dict:
        action = params.get("action", "full")
        handler = self._tools.get(f"security_scan_{action}") or self._tools.get(f"security_{action}")
        if handler:
            return await handler(params)
        return {"error": f"Unknown action: {action}"}

    async def full_scan(self, params: Dict) -> Dict:
        """
        Full security scan — like the complete Raqib watch.
        Runs all scanners in sequence for comprehensive coverage.
        """
        target = params.get("path", ".")
        report = ScanReport(scan_type="full", target=target)

        # 1. Secret scanning
        secret_results = await self.scan_secrets({"path": target})
        report.findings.extend([
            SecurityFinding(**f) if isinstance(f, dict) else f
            for f in secret_results.get("findings", [])
        ])

        # 2. Code vulnerability scanning
        code_results = await self.scan_code_vulnerabilities({"path": target})
        report.findings.extend([
            SecurityFinding(**f) if isinstance(f, dict) else f
            for f in code_results.get("findings", [])
        ])

        # 3. Dependency audit
        dep_results = await self.scan_dependencies({"path": target})
        report.findings.extend([
            SecurityFinding(**f) if isinstance(f, dict) else f
            for f in dep_results.get("findings", [])
        ])

        # 4. Configuration check
        config_results = await self.scan_configuration({"path": target})
        report.findings.extend([
            SecurityFinding(**f) if isinstance(f, dict) else f
            for f in config_results.get("findings", [])
        ])

        report.completed_at = datetime.utcnow().isoformat()

        # Summary — Hisab (accounting)
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for f in report.findings:
            sev = f.severity if isinstance(f, SecurityFinding) else f.get("severity", "info")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        report.summary = {
            "total_findings": len(report.findings),
            "by_severity": severity_counts,
            "risk_score": self._calculate_risk_score(severity_counts),
            "verdict": self._verdict(severity_counts),
        }

        self.scan_history.append(report)
        return report.to_dict()

    async def scan_secrets(self, params: Dict) -> Dict:
        """Scan for leaked secrets — 'And conceal your secret counsel' (58:9)"""
        target = params.get("path", ".")
        findings = []
        files_scanned = 0

        for root, dirs, files in os.walk(target):
            # Skip hidden dirs, node_modules, __pycache__, .git
            dirs[:] = [d for d in dirs if not d.startswith(".")
                       and d not in ("node_modules", "__pycache__", "venv", ".venv")]

            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                if ext in (".pyc", ".pyo", ".so", ".o", ".a", ".class",
                           ".jpg", ".png", ".gif", ".ico", ".woff", ".ttf",
                           ".zip", ".tar", ".gz", ".db", ".sqlite"):
                    continue

                filepath = os.path.join(root, filename)
                try:
                    with open(filepath, "r", errors="ignore") as f:
                        content = f.read(100_000)  # Max 100KB per file
                    files_scanned += 1

                    for line_num, line in enumerate(content.split("\n"), 1):
                        for pattern, name, severity in SECRET_PATTERNS:
                            if re.search(pattern, line):
                                # Mask the actual secret
                                masked = re.sub(
                                    r'(["\'])[^\'"]{8,}(["\'])',
                                    r'\1****REDACTED****\2', line.strip()
                                )
                                findings.append(SecurityFinding(
                                    severity=severity,
                                    category="secret_leak",
                                    title=f"{name} detected",
                                    description=f"Potential {name} found in {filepath}",
                                    file_path=filepath,
                                    line_number=line_num,
                                    code_snippet=masked[:200],
                                    recommendation=f"Remove {name} from code. Use environment variables or a secret manager.",
                                    cwe_id="CWE-798",
                                ).to_dict())
                                break  # One finding per line

                except (IOError, UnicodeDecodeError):
                    continue

        return {"findings": findings, "files_scanned": files_scanned,
                "scan_type": "secrets"}

    async def scan_code_vulnerabilities(self, params: Dict) -> Dict:
        """Scan code for vulnerabilities — OWASP Top 10"""
        target = params.get("path", ".")
        language = params.get("language")
        findings = []
        files_scanned = 0

        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if not d.startswith(".")
                       and d not in ("node_modules", "__pycache__", "venv", ".venv")]

            for filename in files:
                filepath = os.path.join(root, filename)
                ext = os.path.splitext(filename)[1].lower()

                lang = None
                if ext == ".py":
                    lang = "python"
                elif ext in (".js", ".jsx", ".ts", ".tsx"):
                    lang = "javascript"

                if not lang or (language and lang != language):
                    continue

                patterns = VULN_PATTERNS.get(lang, [])
                if not patterns:
                    continue

                try:
                    with open(filepath, "r", errors="ignore") as f:
                        content = f.read(200_000)
                    files_scanned += 1

                    for line_num, line in enumerate(content.split("\n"), 1):
                        for pattern, title, cwe, severity, recommendation in patterns:
                            if re.search(pattern, line):
                                findings.append(SecurityFinding(
                                    severity=severity,
                                    category="vulnerability",
                                    title=title,
                                    description=f"{title} in {filepath}:{line_num}",
                                    file_path=filepath,
                                    line_number=line_num,
                                    code_snippet=line.strip()[:200],
                                    recommendation=recommendation,
                                    cwe_id=cwe,
                                ).to_dict())
                except (IOError, UnicodeDecodeError):
                    continue

        return {"findings": findings, "files_scanned": files_scanned,
                "scan_type": "code_vulnerabilities"}

    async def scan_dependencies(self, params: Dict) -> Dict:
        """Audit dependencies — check for known CVEs"""
        target = params.get("path", ".")
        findings = []

        # Python: requirements.txt
        req_path = os.path.join(target, "requirements.txt")
        if os.path.exists(req_path):
            try:
                with open(req_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        parts = re.split(r'[=<>!~]', line)
                        pkg_name = parts[0].strip().lower()
                        version_match = re.search(r'[=<>!~]+(.+)', line)
                        version = version_match.group(1).strip() if version_match else None

                        vuln = KNOWN_VULN_DEPS.get("python", {}).get(pkg_name)
                        if vuln and version:
                            findings.append(SecurityFinding(
                                severity=vuln["severity"],
                                category="dependency",
                                title=f"Vulnerable dependency: {pkg_name} {version}",
                                description=f"{vuln['desc']} ({vuln['cve']})",
                                file_path=req_path,
                                recommendation=f"Upgrade {pkg_name} to version >= {vuln['below']}",
                                cwe_id="CWE-1104",
                            ).to_dict())
            except IOError:
                pass

        # JavaScript: package.json
        pkg_path = os.path.join(target, "package.json")
        if os.path.exists(pkg_path):
            try:
                with open(pkg_path, "r") as f:
                    pkg = json.load(f)
                all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                for dep_name, dep_version in all_deps.items():
                    vuln = KNOWN_VULN_DEPS.get("javascript", {}).get(dep_name)
                    if vuln:
                        findings.append(SecurityFinding(
                            severity=vuln["severity"],
                            category="dependency",
                            title=f"Vulnerable dependency: {dep_name} {dep_version}",
                            description=f"{vuln['desc']} ({vuln['cve']})",
                            file_path=pkg_path,
                            recommendation=f"Upgrade {dep_name} to version >= {vuln['below']}",
                            cwe_id="CWE-1104",
                        ).to_dict())
            except (IOError, json.JSONDecodeError):
                pass

        # Also try pip audit if available
        try:
            proc = subprocess.run(
                ["pip", "audit", "--format=json"],
                capture_output=True, text=True, timeout=60, cwd=target,
            )
            if proc.returncode == 0:
                audit = json.loads(proc.stdout)
                for vuln in audit.get("vulnerabilities", []):
                    findings.append(SecurityFinding(
                        severity="high",
                        category="dependency",
                        title=f"pip audit: {vuln.get('name')} {vuln.get('version')}",
                        description=vuln.get("description", ""),
                        recommendation=f"Upgrade to {vuln.get('fix_version', 'latest')}",
                    ).to_dict())
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            pass

        return {"findings": findings, "scan_type": "dependencies"}

    async def scan_configuration(self, params: Dict) -> Dict:
        """Scan configuration files for security issues"""
        target = params.get("path", ".")
        findings = []

        for check in CONFIG_CHECKS:
            filepath = os.path.join(target, check["file"])

            if check.get("check_missing"):
                if not os.path.exists(filepath):
                    findings.append(SecurityFinding(
                        severity=check["severity"],
                        category="misconfiguration",
                        title=check["title"],
                        description=f"Missing {check['file']}",
                        file_path=filepath,
                        recommendation=check["recommendation"],
                    ).to_dict())
                continue

            if os.path.exists(filepath):
                try:
                    with open(filepath, "r") as f:
                        content = f.read()
                    if re.search(check["pattern"], content):
                        findings.append(SecurityFinding(
                            severity=check["severity"],
                            category="misconfiguration",
                            title=check["title"],
                            file_path=filepath,
                            recommendation=check["recommendation"],
                        ).to_dict())
                except IOError:
                    pass

        # Check if .env is in .gitignore
        gitignore_path = os.path.join(target, ".gitignore")
        env_path = os.path.join(target, ".env")
        if os.path.exists(env_path) and os.path.exists(gitignore_path):
            try:
                with open(gitignore_path, "r") as f:
                    if ".env" not in f.read():
                        findings.append(SecurityFinding(
                            severity="high",
                            category="misconfiguration",
                            title=".env file not in .gitignore",
                            file_path=gitignore_path,
                            recommendation="Add .env to .gitignore to prevent secret leakage",
                        ).to_dict())
            except IOError:
                pass

        return {"findings": findings, "scan_type": "configuration"}

    async def scan_docker(self, params: Dict) -> Dict:
        """Scan Dockerfile for security issues"""
        target = params.get("path", ".")
        findings = []

        dockerfile = os.path.join(target, "Dockerfile")
        if not os.path.exists(dockerfile):
            return {"findings": [], "scan_type": "docker", "message": "No Dockerfile found"}

        try:
            with open(dockerfile, "r") as f:
                content = f.read()
                lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("FROM") and ":latest" in stripped:
                    findings.append(SecurityFinding(
                        severity="medium", category="docker",
                        title="Using :latest tag",
                        description="Pin image versions for reproducible builds",
                        file_path=dockerfile, line_number=i,
                        recommendation="Use specific version tags (e.g., python:3.11-slim)",
                    ).to_dict())
                elif stripped.startswith("RUN") and "curl" in stripped and "|" in stripped and "sh" in stripped:
                    findings.append(SecurityFinding(
                        severity="high", category="docker",
                        title="Piping curl to shell",
                        description="Download scripts and execute separately after verification",
                        file_path=dockerfile, line_number=i,
                        recommendation="Download, verify checksum, then execute",
                    ).to_dict())
                elif re.match(r'^\s*USER\s+root', stripped):
                    findings.append(SecurityFinding(
                        severity="medium", category="docker",
                        title="Running as root",
                        description="Container should run as non-root user",
                        file_path=dockerfile, line_number=i,
                        recommendation="Add USER nonroot after installation steps",
                    ).to_dict())
                elif re.search(r'COPY\s+\.\s', stripped) or re.search(r'ADD\s+\.\s', stripped):
                    findings.append(SecurityFinding(
                        severity="low", category="docker",
                        title="Copying entire context",
                        description="May include unnecessary or sensitive files",
                        file_path=dockerfile, line_number=i,
                        recommendation="Use .dockerignore and copy only needed files",
                    ).to_dict())

        except IOError:
            pass

        return {"findings": findings, "scan_type": "docker"}

    async def get_report(self, params: Dict) -> Dict:
        """Get a scan report by ID"""
        report_id = params.get("report_id")
        for report in self.scan_history:
            if report.id == report_id:
                return report.to_dict()
        return {"error": "Report not found"}

    async def get_history(self, params: Dict = None) -> Dict:
        """Get scan history"""
        return {"scans": [
            {"id": r.id, "scan_type": r.scan_type, "target": r.target,
             "finding_count": len(r.findings),
             "summary": r.summary, "completed_at": r.completed_at}
            for r in self.scan_history
        ]}

    def _calculate_risk_score(self, severity_counts: Dict) -> float:
        """Calculate risk score 0-100 based on findings"""
        weights = {"critical": 25, "high": 15, "medium": 5, "low": 1, "info": 0}
        score = sum(count * weights.get(sev, 0)
                    for sev, count in severity_counts.items())
        return min(100.0, score)

    def _verdict(self, severity_counts: Dict) -> str:
        """Quranic-inspired security verdict"""
        if severity_counts.get("critical", 0) > 0:
            return "FASAD (فَسَاد) — Corruption found. Critical fixes needed."
        if severity_counts.get("high", 0) > 0:
            return "MUNKAR (مُنكَر) — Evil detected. High-priority remediation required."
        if severity_counts.get("medium", 0) > 0:
            return "TAWBAH (تَوْبَة) — Repentance needed. Medium issues to address."
        if severity_counts.get("low", 0) > 0:
            return "IHSAN (إحسان) — Near excellence. Minor improvements possible."
        return "TAYYIB (طَيِّب) — Pure and good. No significant issues found."

    def get_tool_schemas(self) -> List[Dict]:
        return [
            {"name": "security_scan_full",
             "description": "Run comprehensive security scan (secrets, code, deps, config)",
             "input_schema": {"type": "object", "properties": {
                 "path": {"type": "string", "description": "Directory to scan"},
             }}},
            {"name": "security_scan_secrets",
             "description": "Scan for leaked secrets, API keys, passwords",
             "input_schema": {"type": "object", "properties": {
                 "path": {"type": "string"},
             }}},
            {"name": "security_scan_code",
             "description": "Scan code for OWASP Top 10 vulnerabilities",
             "input_schema": {"type": "object", "properties": {
                 "path": {"type": "string"},
                 "language": {"type": "string", "enum": ["python", "javascript"]},
             }}},
            {"name": "security_scan_deps",
             "description": "Audit dependencies for known CVEs",
             "input_schema": {"type": "object", "properties": {
                 "path": {"type": "string"},
             }}},
            {"name": "security_scan_config",
             "description": "Check configuration files for security misconfigurations",
             "input_schema": {"type": "object", "properties": {
                 "path": {"type": "string"},
             }}},
            {"name": "security_scan_docker",
             "description": "Scan Dockerfile for security issues",
             "input_schema": {"type": "object", "properties": {
                 "path": {"type": "string"},
             }}},
            {"name": "security_history",
             "description": "Get scan history",
             "input_schema": {"type": "object", "properties": {}}},
        ]
