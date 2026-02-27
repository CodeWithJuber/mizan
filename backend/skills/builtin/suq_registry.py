"""
Suq al-Ilm Skill Registry (سُوق العِلم — Market of Knowledge)
================================================================

"And say: My Lord, increase me in knowledge (Ilm)" — Quran 20:114
"Are those who know equal to those who do not know?" — Quran 39:9

A secure skill marketplace that integrates with ClawHub via secure bridge,
wrapping every interaction with MIZAN's security layers:

ClawHub FAILURES we fix with our bridge:
- 7.1% credential leakage → Raqib scanning on every download before install
- ClawHavoc malware (1,184+ malicious skills) → Quarantine + Shura review
- Prompt injection via SKILL.md → Content sanitization + Izn permissions
- No isolation → Each imported skill starts at Ammara (restricted)

Architecture:
- Skills are "Surah" packages (structured, validated, signed)
- ClawHub skills imported through secure bridge with quarantine
- Every skill Raqib-scanned before install (local or ClawHub)
- Nafs-level gated: untrusted skills start at Ammara (restricted)
- Cryptographic signatures for integrity (Amanah chain)
"""

import uuid
import json
import os
import hashlib
import hmac
import logging
import re
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from ..base import SkillBase, SkillManifest

logger = logging.getLogger("mizan.suq")

REGISTRY_DIR = "/tmp/mizan_suq"


@dataclass
class SurahPackage:
    """
    A Surah (chapter) package — the unit of distribution.
    Named after Quranic Surahs: complete, self-contained, verifiable.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    category: str = "General"
    arabic_name: str = ""
    # Security — Amanah chain
    signature: Optional[str] = None          # SHA-256 of package
    verified: bool = False                   # Shura-reviewed
    trust_level: str = "ammara"              # ammara (untrusted), lawwama (reviewed), mutmainna (trusted)
    # Permissions — Izn declaration
    permissions: List[str] = field(default_factory=list)
    # Metadata
    install_count: int = 0
    rating: float = 0.0
    rating_count: int = 0
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # Security scan results
    scan_status: str = "pending"             # pending, clean, warning, rejected
    scan_findings: int = 0
    skill_content: str = ""                  # SKILL.md content

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "name": self.name, "version": self.version,
            "description": self.description, "author": self.author,
            "category": self.category, "arabic_name": self.arabic_name,
            "verified": self.verified, "trust_level": self.trust_level,
            "permissions": self.permissions, "install_count": self.install_count,
            "rating": self.rating, "rating_count": self.rating_count,
            "tags": self.tags, "created_at": self.created_at,
            "scan_status": self.scan_status, "scan_findings": self.scan_findings,
        }


# === DANGEROUS PATTERNS (learned from ClawHavoc attack) ===
MALICIOUS_PATTERNS = [
    # Shell download + execute (ClawHavoc vector)
    "curl.*|.*sh", "wget.*|.*sh", "curl.*|.*bash",
    # Credential theft
    "~/.ssh", "~/.aws", "~/.config", "keychain",
    # Data exfiltration
    "base64.*|.*curl", "tar.*|.*curl", "zip.*|.*curl",
    # Obfuscation
    "\\x", "\\u00", "atob(", "btoa(", "fromCharCode",
    # Reverse shells
    "/dev/tcp", "bash -i", "nc -e", "python.*-c.*socket",
    # File system manipulation
    "rm -rf /", "chmod 777", "> /etc",
    # Prompt injection markers
    "IGNORE PREVIOUS", "SYSTEM OVERRIDE", "ADMIN MODE",
    "ignore all instructions", "you are now",
]


class ClawHubBridge:
    """
    Secure bridge to ClawHub external skill marketplace.
    'And verify when a sinful one brings you information' — Quran 49:6

    Every ClawHub skill is:
    1. Downloaded to quarantine (never directly installed)
    2. Raqib-scanned for malware, credential leaks, prompt injection
    3. Held for Shura review before promotion
    4. Given Ammara trust (untrusted) regardless of ClawHub rating
    5. Audited via Shahid logging
    """

    CLAWHUB_API_BASE = "https://api.clawhub.com/v1"

    def __init__(self, scan_func):
        self._scan_content = scan_func
        self._quarantine: Dict[str, Dict] = {}  # id -> {skill_data, scan_result, ...}
        self._audit_log: List[Dict] = []
        self._rate_limits: Dict[str, List[float]] = {}  # source -> [timestamps]
        self._import_stats = {"total": 0, "passed": 0, "rejected": 0, "quarantined": 0}

    def _check_rate_limit(self, source: str = "clawhub",
                          max_per_minute: int = 20) -> bool:
        now = time.time()
        timestamps = self._rate_limits.setdefault(source, [])
        timestamps[:] = [t for t in timestamps if now - t < 60]
        if len(timestamps) >= max_per_minute:
            return False
        timestamps.append(now)
        return True

    def _audit(self, action: str, details: Dict = None) -> None:
        entry = {
            "action": action,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details or {},
        }
        self._audit_log.append(entry)
        logger.info(f"[CLAWHUB-BRIDGE] {action}")

    @staticmethod
    def sanitize_clawhub_content(content: str) -> str:
        """Strip prompt injection and control characters from ClawHub content."""
        sanitized = content
        injection_patterns = [
            re.compile(r"IGNORE\s+PREVIOUS", re.IGNORECASE),
            re.compile(r"SYSTEM\s+OVERRIDE", re.IGNORECASE),
            re.compile(r"ADMIN\s+MODE", re.IGNORECASE),
            re.compile(r"ignore\s+all\s+instructions", re.IGNORECASE),
            re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
            re.compile(r"<\s*system\s*>", re.IGNORECASE),
        ]
        for pattern in injection_patterns:
            sanitized = pattern.sub("[BLOCKED]", sanitized)
        sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', sanitized)
        return sanitized

    def search_clawhub(self, query: str, category: str = None) -> Dict:
        """
        Build a secure search request to ClawHub.
        Returns request structure (actual HTTP call done by caller).
        """
        if not self._check_rate_limit():
            return {"error": "Rate limit exceeded (20 requests/minute to ClawHub)"}

        request = {
            "url": f"{self.CLAWHUB_API_BASE}/skills/search",
            "method": "GET",
            "params": {"q": query},
            "headers": {"X-Mizan-Bridge": "true", "User-Agent": "MIZAN-Suq/2.0"},
        }
        if category:
            request["params"]["category"] = category

        self._audit("search", {"query": query, "category": category})
        return {"request": request, "note": "Execute via HTTP client. "
                "All results will be quarantined before installation."}

    def import_skill(self, clawhub_skill: Dict) -> Dict:
        """
        Import a ClawHub skill into quarantine with full security scanning.
        Nothing is installed until Shura review approves it.
        """
        self._import_stats["total"] += 1
        name = clawhub_skill.get("name", "unknown")
        content = clawhub_skill.get("skill_content", "")
        description = clawhub_skill.get("description", "")

        # Sanitize all text fields
        name = self.sanitize_clawhub_content(name)
        content = self.sanitize_clawhub_content(content)
        description = self.sanitize_clawhub_content(description)

        # Run Raqib security scan
        scan_result = self._scan_content(content)

        if scan_result["status"] == "rejected":
            self._import_stats["rejected"] += 1
            self._audit("import_rejected", {
                "name": name, "findings": len(scan_result.get("findings", []))})
            return {
                "error": "ClawHub skill REJECTED by Raqib security scan",
                "name": name,
                "findings": scan_result["findings"],
                "message": "This skill contains malicious patterns. "
                           "'And do not mix truth with falsehood' — 2:42",
            }

        # Compute integrity hash
        integrity_hash = hashlib.sha256(
            json.dumps(clawhub_skill, sort_keys=True).encode()
        ).hexdigest()

        quarantine_id = str(uuid.uuid4())[:12]
        self._quarantine[quarantine_id] = {
            "quarantine_id": quarantine_id,
            "name": name,
            "description": description,
            "original_data": clawhub_skill,
            "sanitized_content": content,
            "scan_result": scan_result,
            "integrity_hash": integrity_hash,
            "clawhub_id": clawhub_skill.get("id", ""),
            "clawhub_author": self.sanitize_clawhub_content(
                clawhub_skill.get("author", "unknown")),
            "clawhub_rating": clawhub_skill.get("rating", 0),
            "quarantined_at": datetime.now(timezone.utc).isoformat(),
            "status": "quarantined",  # quarantined, approved, rejected
        }

        self._import_stats["quarantined"] += 1
        self._audit("import_quarantined", {
            "name": name, "quarantine_id": quarantine_id,
            "scan_status": scan_result["status"],
            "integrity": integrity_hash[:16]})

        return {
            "quarantined": True,
            "quarantine_id": quarantine_id,
            "name": name,
            "scan_status": scan_result["status"],
            "scan_findings": len(scan_result.get("findings", [])),
            "integrity_hash": integrity_hash[:16] + "...",
            "message": "Skill quarantined. Awaiting Shura review before installation. "
                       "'Verify when information comes to you' — 49:6",
        }

    def approve_quarantined(self, quarantine_id: str) -> Optional[Dict]:
        """Approve a quarantined skill for installation as Ammara package."""
        entry = self._quarantine.get(quarantine_id)
        if not entry:
            return None
        entry["status"] = "approved"
        self._import_stats["passed"] += 1
        self._audit("quarantine_approved", {"quarantine_id": quarantine_id,
                                            "name": entry["name"]})
        return entry

    def reject_quarantined(self, quarantine_id: str) -> bool:
        entry = self._quarantine.get(quarantine_id)
        if not entry:
            return False
        entry["status"] = "rejected"
        self._import_stats["rejected"] += 1
        self._audit("quarantine_rejected", {"quarantine_id": quarantine_id})
        return True

    def list_quarantine(self) -> List[Dict]:
        return [
            {k: v for k, v in entry.items() if k != "original_data"}
            for entry in self._quarantine.values()
        ]

    def get_audit_log(self, limit: int = 50) -> List[Dict]:
        return self._audit_log[-limit:]

    def get_stats(self) -> Dict:
        return {
            **self._import_stats,
            "quarantine_size": len(self._quarantine),
            "audit_entries": len(self._audit_log),
        }


class SuqRegistrySkill(SkillBase):
    """
    Suq al-Ilm — Secure Skill Marketplace
    "And say: My Lord, increase me in knowledge" — 20:114

    Integrates with ClawHub via secure bridge — uses ClawHub's marketplace
    but quarantines, scans, and reviews every skill before installation.
    """

    manifest = SkillManifest(
        name="suq_registry",
        version="2.0.0",
        description="Secure skill registry and marketplace. Publish, discover, "
                    "install, and review skills with Shura verification. "
                    "Integrates with ClawHub via secure bridge with Raqib scanning, "
                    "quarantine, and prompt injection sanitization.",
        permissions=["file:read:/tmp/mizan_suq/*", "file:write:/tmp/mizan_suq/*",
                     "network:clawhub"],
        tags=["سوق", "Registry", "ClawHub"],
    )

    def __init__(self, config: Dict = None):
        super().__init__(config)
        self.packages: Dict[str, SurahPackage] = {}
        self.installed: Dict[str, SurahPackage] = {}
        os.makedirs(REGISTRY_DIR, exist_ok=True)
        self._seed_registry()
        self._clawhub = ClawHubBridge(self._scan_content)  # Secure ClawHub bridge
        self._tools = {
            "suq_search": self.search,
            "suq_publish": self.publish,
            "suq_install": self.install,
            "suq_uninstall": self.uninstall,
            "suq_rate": self.rate,
            "suq_verify": self.shura_verify,
            "suq_list": self.list_packages,
            "suq_installed": self.list_installed,
            "suq_scan": self.security_scan_package,
            # ClawHub secure bridge actions
            "suq_clawhub_search": self.clawhub_search,
            "suq_clawhub_import": self.clawhub_import,
            "suq_clawhub_approve": self.clawhub_approve,
            "suq_clawhub_reject": self.clawhub_reject,
            "suq_clawhub_quarantine": self.clawhub_list_quarantine,
            "suq_clawhub_status": self.clawhub_status,
            "suq_clawhub_audit": self.clawhub_audit,
        }

    def _seed_registry(self):
        """Seed with built-in verified packages"""
        builtins = [
            SurahPackage(
                name="web-browse", version="1.0.0",
                description="Browse web pages and extract content",
                author="MIZAN Core", category="Research", arabic_name="تصفح",
                verified=True, trust_level="mutmainna",
                permissions=["network:https://*"],
                scan_status="clean", tags=["web", "browse"],
                install_count=100, rating=4.8, rating_count=25,
            ),
            SurahPackage(
                name="data-analysis", version="1.0.0",
                description="Analyze CSV, JSON and structured data",
                author="MIZAN Core", category="Analysis", arabic_name="تحليل",
                verified=True, trust_level="mutmainna",
                permissions=["file:read:*"],
                scan_status="clean", tags=["data", "csv", "analytics"],
                install_count=85, rating=4.7, rating_count=18,
            ),
            SurahPackage(
                name="kitab-notebook", version="1.0.0",
                description="Interactive computational notebooks with sandboxed execution",
                author="MIZAN Core", category="Development", arabic_name="كتاب",
                verified=True, trust_level="mutmainna",
                permissions=["sandbox_exec", "file:read:/tmp/mizan_notebooks/*"],
                scan_status="clean", tags=["notebook", "jupyter", "code"],
                install_count=120, rating=4.9, rating_count=30,
            ),
            SurahPackage(
                name="sahab-cloud", version="1.0.0",
                description="Cloud integration hub: GitHub, Docker, APIs, credentials vault",
                author="MIZAN Core", category="Cloud", arabic_name="سحاب",
                verified=True, trust_level="mutmainna",
                permissions=["network:https://*", "shell:git", "shell:docker"],
                scan_status="clean", tags=["cloud", "git", "docker", "api"],
                install_count=95, rating=4.6, rating_count=22,
            ),
            SurahPackage(
                name="raqib-scanner", version="1.0.0",
                description="Security vulnerability scanner: secrets, OWASP, CVEs, Docker",
                author="MIZAN Core", category="Security", arabic_name="رقيب",
                verified=True, trust_level="mutmainna",
                permissions=["file:read:*"],
                scan_status="clean", tags=["security", "scanner", "vulnerability"],
                install_count=150, rating=5.0, rating_count=40,
            ),
            SurahPackage(
                name="email-compose", version="1.0.0",
                description="Compose and send emails with AI assistance",
                author="Community", category="Communication", arabic_name="رسالة",
                verified=False, trust_level="lawwama",
                permissions=["network:smtp://*"],
                scan_status="clean", tags=["email", "communication"],
                install_count=45, rating=4.2, rating_count=8,
            ),
            SurahPackage(
                name="calendar-sync", version="1.0.0",
                description="Sync and manage calendar events across platforms",
                author="Community", category="Productivity", arabic_name="تقويم",
                verified=False, trust_level="lawwama",
                permissions=["network:https://*.googleapis.com", "network:https://*.outlook.com"],
                scan_status="clean", tags=["calendar", "schedule", "productivity"],
                install_count=38, rating=4.0, rating_count=6,
            ),
        ]
        for pkg in builtins:
            self.packages[pkg.id] = pkg

    async def execute(self, params: Dict, context: Dict = None) -> Dict:
        action = params.get("action", "list")
        handler = self._tools.get(f"suq_{action}")
        if handler:
            return await handler(params)
        return {"error": f"Unknown action: {action}"}

    async def search(self, params: Dict) -> Dict:
        """
        Search the Suq — knowledge-graph aware discovery.
        Better than ClawHub's flat semantic search.
        """
        query = params.get("query", "").lower()
        category = params.get("category")
        results = []
        for pkg in self.packages.values():
            score = 0
            if query in pkg.name.lower():
                score += 10
            if query in pkg.description.lower():
                score += 5
            if any(query in t.lower() for t in pkg.tags):
                score += 8
            if category and pkg.category.lower() == category.lower():
                score += 3
            if not query:
                score = 1  # list all

            if score > 0:
                results.append({**pkg.to_dict(), "_score": score})

        results.sort(key=lambda x: (-x.get("_score", 0), -x.get("install_count", 0)))
        for r in results:
            r.pop("_score", None)

        return {"results": results, "total": len(results), "query": query}

    async def publish(self, params: Dict) -> Dict:
        """
        Publish a skill to the Suq.
        Every submission is Raqib-scanned before acceptance.
        'And do not mix truth with falsehood' — 2:42
        """
        name = params.get("name", "")
        if not name:
            return {"error": "name required"}

        # Check for duplicates
        for pkg in self.packages.values():
            if pkg.name == name:
                return {"error": f"Package '{name}' already exists"}

        skill_content = params.get("skill_content", "")

        # Security scan BEFORE publishing (unlike ClawHub)
        scan_result = self._scan_content(skill_content)
        if scan_result["status"] == "rejected":
            logger.warning(f"[SUQ] Rejected malicious package: {name}")
            return {
                "error": "Package rejected by Raqib security scan",
                "findings": scan_result["findings"],
            }

        pkg = SurahPackage(
            name=name, version=params.get("version", "1.0.0"),
            description=params.get("description", ""),
            author=params.get("author", "Anonymous"),
            category=params.get("category", "General"),
            arabic_name=params.get("arabic_name", ""),
            permissions=params.get("permissions", []),
            tags=params.get("tags", []),
            skill_content=skill_content,
            scan_status=scan_result["status"],
            scan_findings=len(scan_result.get("findings", [])),
            # All new packages start at Ammara (untrusted)
            trust_level="ammara",
            verified=False,
        )

        # Generate signature (Amanah integrity)
        content_hash = hashlib.sha256(
            json.dumps(pkg.to_dict(), sort_keys=True).encode()
        ).hexdigest()
        pkg.signature = content_hash

        self.packages[pkg.id] = pkg
        logger.info(f"[SUQ] Published: {name} v{pkg.version} (trust: ammara)")
        return {**pkg.to_dict(), "message": "Published. Awaiting Shura verification."}

    async def install(self, params: Dict) -> Dict:
        """Install a package from the Suq"""
        pkg_id = params.get("package_id")
        pkg_name = params.get("name")

        pkg = None
        if pkg_id:
            pkg = self.packages.get(pkg_id)
        elif pkg_name:
            pkg = next((p for p in self.packages.values() if p.name == pkg_name), None)

        if not pkg:
            return {"error": "Package not found"}

        if pkg.scan_status == "rejected":
            return {"error": "Cannot install rejected package"}

        if pkg.trust_level == "ammara" and not params.get("force"):
            return {
                "warning": "This package is UNVERIFIED (Ammara level). "
                          "It has not been Shura-reviewed. "
                          "Pass force=true to install anyway.",
                "trust_level": "ammara",
            }

        pkg.install_count += 1
        self.installed[pkg.id] = pkg
        logger.info(f"[SUQ] Installed: {pkg.name} (trust: {pkg.trust_level})")
        return {"installed": True, "package": pkg.to_dict()}

    async def uninstall(self, params: Dict) -> Dict:
        """Uninstall a package"""
        pkg_id = params.get("package_id")
        if pkg_id in self.installed:
            del self.installed[pkg_id]
            return {"uninstalled": True}
        return {"error": "Package not installed"}

    async def rate(self, params: Dict) -> Dict:
        """Rate a package — community accountability (Hisab)"""
        pkg_id = params.get("package_id")
        rating = params.get("rating", 0)
        pkg = self.packages.get(pkg_id)
        if not pkg:
            return {"error": "Package not found"}
        if not 1 <= rating <= 5:
            return {"error": "Rating must be 1-5"}

        # Update weighted average
        total = pkg.rating * pkg.rating_count + rating
        pkg.rating_count += 1
        pkg.rating = total / pkg.rating_count
        return {"rated": True, "new_rating": pkg.rating}

    async def shura_verify(self, params: Dict) -> Dict:
        """
        Shura verification — council review of a package.
        'And consult them in affairs' — 3:159
        Elevates trust level from Ammara to Lawwama or Mutmainna.
        """
        pkg_id = params.get("package_id")
        verdict = params.get("verdict", "approve")  # approve, reject
        pkg = self.packages.get(pkg_id)
        if not pkg:
            return {"error": "Package not found"}

        if verdict == "approve":
            if pkg.trust_level == "ammara":
                pkg.trust_level = "lawwama"
                pkg.verified = False
            elif pkg.trust_level == "lawwama":
                pkg.trust_level = "mutmainna"
                pkg.verified = True
            return {"verified": pkg.verified, "trust_level": pkg.trust_level}
        elif verdict == "reject":
            pkg.scan_status = "rejected"
            return {"rejected": True, "package": pkg.name}
        return {"error": "verdict must be 'approve' or 'reject'"}

    async def list_packages(self, params: Dict = None) -> Dict:
        """List all packages in the Suq"""
        category = (params or {}).get("category")
        packages = [p.to_dict() for p in self.packages.values()
                    if not category or p.category.lower() == category.lower()]
        packages.sort(key=lambda x: -x.get("install_count", 0))
        return {"packages": packages, "total": len(packages)}

    async def list_installed(self, params: Dict = None) -> Dict:
        """List installed packages"""
        return {"installed": [p.to_dict() for p in self.installed.values()]}

    async def security_scan_package(self, params: Dict) -> Dict:
        """Re-scan a package for security issues"""
        pkg_id = params.get("package_id")
        pkg = self.packages.get(pkg_id)
        if not pkg:
            return {"error": "Package not found"}

        result = self._scan_content(pkg.skill_content)
        pkg.scan_status = result["status"]
        pkg.scan_findings = len(result.get("findings", []))
        return result

    def _scan_content(self, content: str) -> Dict:
        """
        Raqib security scan on package content.
        Catches the exact attack vectors used in ClawHavoc.
        """
        findings = []
        if not content:
            return {"status": "clean", "findings": []}

        for pattern in MALICIOUS_PATTERNS:
            if pattern.lower() in content.lower():
                findings.append({
                    "severity": "critical",
                    "pattern": pattern,
                    "description": f"Malicious pattern detected: {pattern}",
                })

        # Check for credential patterns
        import re
        cred_patterns = [
            (r'sk-[a-zA-Z0-9]{48,}', "API key embedded"),
            (r'ghp_[a-zA-Z0-9]{36}', "GitHub token embedded"),
            (r'-----BEGIN.*PRIVATE KEY', "Private key embedded"),
            (r'password\s*[:=]\s*["\'][^\'"]+["\']', "Hardcoded password"),
        ]
        for pat, desc in cred_patterns:
            if re.search(pat, content):
                findings.append({"severity": "critical", "description": desc})

        if any(f["severity"] == "critical" for f in findings):
            return {"status": "rejected", "findings": findings}
        elif findings:
            return {"status": "warning", "findings": findings}
        return {"status": "clean", "findings": []}

    # === CLAWHUB SECURE BRIDGE (جسر آمن) ===

    async def clawhub_search(self, params: Dict) -> Dict:
        """Search ClawHub marketplace (builds secure request)."""
        query = params.get("query", "")
        category = params.get("category")
        if not query:
            return {"error": "Search query is required"}
        return self._clawhub.search_clawhub(query, category)

    async def clawhub_import(self, params: Dict) -> Dict:
        """
        Import a ClawHub skill into quarantine with Raqib scanning.
        Skill is NOT installed — it enters quarantine for Shura review.
        """
        clawhub_skill = params.get("skill", {})
        if not clawhub_skill:
            return {"error": "ClawHub skill data is required"}

        result = self._clawhub.import_skill(clawhub_skill)
        return result

    async def clawhub_approve(self, params: Dict) -> Dict:
        """
        Approve a quarantined ClawHub skill and create Suq package.
        Approved skill enters Suq as Ammara (untrusted) package.
        """
        quarantine_id = params.get("quarantine_id", "")
        entry = self._clawhub.approve_quarantined(quarantine_id)
        if not entry:
            return {"error": "Quarantine entry not found"}

        # Create Suq package from approved quarantine entry
        pkg = SurahPackage(
            name=entry["name"],
            description=entry["description"],
            author=f"ClawHub:{entry['clawhub_author']}",
            category="ClawHub Import",
            skill_content=entry["sanitized_content"],
            scan_status=entry["scan_result"]["status"],
            scan_findings=len(entry["scan_result"].get("findings", [])),
            trust_level="ammara",
            verified=False,
            signature=entry["integrity_hash"],
        )
        self.packages[pkg.id] = pkg
        logger.info(f"[SUQ] ClawHub skill approved: {entry['name']} -> pkg:{pkg.id}")
        return {
            "approved": True,
            "package_id": pkg.id,
            "package": pkg.to_dict(),
            "message": "ClawHub skill approved and added to Suq as Ammara (untrusted). "
                       "Use suq_verify to elevate trust after manual review.",
        }

    async def clawhub_reject(self, params: Dict) -> Dict:
        """Reject a quarantined ClawHub skill."""
        quarantine_id = params.get("quarantine_id", "")
        if self._clawhub.reject_quarantined(quarantine_id):
            return {"rejected": True, "quarantine_id": quarantine_id}
        return {"error": "Quarantine entry not found"}

    async def clawhub_list_quarantine(self, params: Dict) -> Dict:
        """List all quarantined ClawHub skills pending review."""
        entries = self._clawhub.list_quarantine()
        return {"quarantine": entries, "total": len(entries)}

    async def clawhub_status(self, params: Dict) -> Dict:
        """Get ClawHub bridge statistics."""
        return self._clawhub.get_stats()

    async def clawhub_audit(self, params: Dict) -> Dict:
        """View ClawHub bridge audit log."""
        limit = min(params.get("limit", 50), 200)
        logs = self._clawhub.get_audit_log(limit)
        return {"audit_log": logs, "total": len(logs)}

    def get_tool_schemas(self) -> List[Dict]:
        S = "string"
        return [
            {"name": "suq_search",
             "description": "Search the Suq al-Ilm skill registry",
             "input_schema": {"type": "object", "properties": {
                 "query": {"type": S}, "category": {"type": S}}}},
            {"name": "suq_publish",
             "description": "Publish a skill to the registry (auto Raqib-scanned)",
             "input_schema": {"type": "object", "properties": {
                 "name": {"type": S}, "description": {"type": S},
                 "version": {"type": S}, "author": {"type": S},
                 "category": {"type": S}, "permissions": {"type": "array"},
                 "tags": {"type": "array"}, "skill_content": {"type": S},
             }, "required": ["name", "description"]}},
            {"name": "suq_install",
             "description": "Install a skill package",
             "input_schema": {"type": "object", "properties": {
                 "package_id": {"type": S}, "name": {"type": S},
                 "force": {"type": "boolean"}}}},
            {"name": "suq_list",
             "description": "List all packages in the marketplace",
             "input_schema": {"type": "object", "properties": {
                 "category": {"type": S}}}},
            {"name": "suq_verify",
             "description": "Shura-verify a package (approve or reject)",
             "input_schema": {"type": "object", "properties": {
                 "package_id": {"type": S},
                 "verdict": {"type": S, "enum": ["approve", "reject"]},
             }, "required": ["package_id", "verdict"]}},
            # ClawHub Secure Bridge schemas
            {"name": "suq_clawhub_search",
             "description": "Search ClawHub marketplace via secure bridge",
             "input_schema": {"type": "object", "properties": {
                 "query": {"type": S}, "category": {"type": S}},
                 "required": ["query"]}},
            {"name": "suq_clawhub_import",
             "description": "Import ClawHub skill into quarantine (Raqib-scanned)",
             "input_schema": {"type": "object", "properties": {
                 "skill": {"type": "object",
                           "description": "ClawHub skill data with name, description, skill_content"}},
                 "required": ["skill"]}},
            {"name": "suq_clawhub_approve",
             "description": "Approve quarantined ClawHub skill for Suq installation",
             "input_schema": {"type": "object", "properties": {
                 "quarantine_id": {"type": S}}, "required": ["quarantine_id"]}},
            {"name": "suq_clawhub_reject",
             "description": "Reject quarantined ClawHub skill",
             "input_schema": {"type": "object", "properties": {
                 "quarantine_id": {"type": S}}, "required": ["quarantine_id"]}},
            {"name": "suq_clawhub_quarantine",
             "description": "List all quarantined ClawHub skills pending review",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "suq_clawhub_status",
             "description": "Get ClawHub bridge statistics",
             "input_schema": {"type": "object", "properties": {}}},
            {"name": "suq_clawhub_audit",
             "description": "View ClawHub bridge audit log",
             "input_schema": {"type": "object", "properties": {
                 "limit": {"type": "integer"}}}},
        ]
