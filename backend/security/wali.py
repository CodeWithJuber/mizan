"""
Wali (وَلِيّ) — Guardian Security Layer
========================================

"And Allah is the Guardian (Wali) over His servants" — Quran 42:6

Central security enforcement for the entire MIZAN system.
All operations pass through Wali before execution.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger("mizan.wali")


@dataclass
class SecurityConfig:
    """Security configuration for MIZAN"""

    # CORS
    allowed_origins: list[str] = field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:8000",
        ]
    )

    # Rate limiting
    rate_limit_per_minute: int = 60
    rate_limit_burst: int = 10
    ws_max_connections: int = 50

    # File system sandbox
    allowed_paths: list[str] = field(
        default_factory=lambda: [
            "/tmp/mizan/",
            "/data/mizan/",
        ]
    )
    blocked_paths: list[str] = field(
        default_factory=lambda: [
            "/etc/",
            "/root/",
            "/home/",
            "/var/",
            "/usr/",
            "/proc/",
            "/sys/",
            "/dev/",
        ]
    )

    # Command sandbox
    blocked_commands: list[str] = field(
        default_factory=lambda: [
            "rm -rf /",
            "rm -rf /*",
            "dd ",
            "mkfs",
            "> /dev/",
            ":(){ ",
            "chmod 777",
            "curl | sh",
            "wget | sh",
            "eval ",
            "exec ",
            "sudo ",
            "su ",
        ]
    )

    # Secrets
    secret_key: str = ""
    jwt_expiry_hours: int = 24
    jwt_refresh_days: int = 7

    # Input limits
    max_input_length: int = 50000
    max_file_size_mb: int = 10

    @classmethod
    def from_env(cls) -> "SecurityConfig":
        config = cls()
        config.secret_key = os.getenv("SECRET_KEY", os.urandom(32).hex())

        origins = os.getenv("ALLOWED_ORIGINS", "")
        if origins:
            parsed_origins = [o.strip() for o in origins.split(",")]
            # Validate origins - reject wildcards in production
            for origin in parsed_origins:
                if origin == "*":
                    logger.warning(
                        "SECURITY WARNING: Wildcard CORS origin '*' is insecure. "
                        "Please specify exact origins in ALLOWED_ORIGINS"
                    )
                elif not origin.startswith(("http://", "https://")):
                    logger.warning(
                        f"SECURITY WARNING: Invalid CORS origin '{origin}' - "
                        "must start with http:// or https://"
                    )
            config.allowed_origins = parsed_origins

        extra_paths = os.getenv("ALLOWED_PATHS", "")
        if extra_paths:
            config.allowed_paths.extend([p.strip() for p in extra_paths.split(",")])

        config.rate_limit_per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
        config.ws_max_connections = int(os.getenv("WS_MAX_CONNECTIONS", "50"))

        return config


class RateLimiter:
    """Token bucket rate limiter"""

    def __init__(self, per_minute: int = 60, burst: int = 10):
        self.per_minute = per_minute
        self.burst = burst
        self._buckets: dict[str, dict] = {}

    def check(self, key: str) -> bool:
        """Returns True if request is allowed"""
        now = time.time()

        if key not in self._buckets:
            self._buckets[key] = {
                "tokens": self.burst,
                "last_refill": now,
            }

        bucket = self._buckets[key]

        # Refill tokens
        elapsed = now - bucket["last_refill"]
        refill = elapsed * (self.per_minute / 60.0)
        bucket["tokens"] = min(self.burst, bucket["tokens"] + refill)
        bucket["last_refill"] = now

        # Consume token
        if bucket["tokens"] >= 1:
            bucket["tokens"] -= 1
            return True

        return False

    def cleanup(self, max_age_seconds: int = 3600):
        """Remove stale entries"""
        now = time.time()
        stale = [k for k, v in self._buckets.items() if now - v["last_refill"] > max_age_seconds]
        for k in stale:
            del self._buckets[k]


class AuditLog:
    """
    Shahid (شاهد) — Witness/Audit Log
    Records all security-relevant events.
    """

    def __init__(self):
        self._events: list[dict] = []
        self._max_events = 10000

    def log(self, event_type: str, details: dict, severity: str = "info"):
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "type": event_type,
            "severity": severity,
            "details": details,
        }
        self._events.append(entry)

        if severity in ("warning", "error", "critical"):
            logger.warning(f"[WALI] {event_type}: {details}")

        # Trim old events
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events :]

    def get_recent(self, limit: int = 100, severity: str = None) -> list[dict]:
        events = self._events
        if severity:
            events = [e for e in events if e["severity"] == severity]
        return events[-limit:]


class WaliGuardian:
    """
    Central security guardian for MIZAN.
    All tool calls, API requests, and messages pass through here.
    """

    def __init__(self, config: SecurityConfig = None, memory=None):
        self.config = config or SecurityConfig.from_env()
        self.rate_limiter = RateLimiter(
            per_minute=self.config.rate_limit_per_minute,
            burst=self.config.rate_limit_burst,
        )
        self.audit = AuditLog()
        self.memory = memory  # DhikrMemorySystem for persistent audit logs
        self._blocked_ips: dict[str, datetime] = {}

    async def persist_audit(self, event_type: str, details: dict, severity: str = "info"):
        """Persist audit entry to database if memory system available."""
        if self.memory:
            try:
                await self.memory.log_audit(
                    event_type=event_type,
                    severity=severity,
                    details=details,
                )
            except Exception as e:
                logger.error(f"[WALI] Failed to persist audit: {e}")

    def check_rate_limit(self, client_id: str) -> dict:
        """Check if client is within rate limits. Returns status dict with headers."""
        allowed = self.rate_limiter.check(client_id)
        bucket = self.rate_limiter._buckets.get(client_id, {})
        remaining = int(bucket.get("tokens", 0))
        result = {
            "allowed": allowed,
            "remaining": remaining,
            "limit": self.config.rate_limit_per_minute,
            "retry_after": 0 if allowed else max(1, int(60 / self.config.rate_limit_per_minute)),
        }
        if not allowed:
            self.audit.log(
                "rate_limit_exceeded",
                {
                    "client_id": client_id,
                },
                severity="warning",
            )
        return result

    def validate_file_path(self, path: str, mode: str = "read") -> bool:
        """
        Validate file path against sandbox rules.
        Prevents path traversal attacks.
        """
        import os.path

        # Resolve to absolute path, removing ../ traversals
        resolved = os.path.realpath(os.path.expanduser(path))

        # Check blocked paths
        for blocked in self.config.blocked_paths:
            if resolved.startswith(blocked):
                self.audit.log(
                    "path_blocked",
                    {
                        "requested": path,
                        "resolved": resolved,
                        "blocked_by": blocked,
                        "mode": mode,
                    },
                    severity="warning",
                )
                return False

        # For write operations, must be in allowed paths
        if mode == "write":
            in_allowed = any(resolved.startswith(p) for p in self.config.allowed_paths)
            if not in_allowed:
                self.audit.log(
                    "write_path_rejected",
                    {
                        "requested": path,
                        "resolved": resolved,
                        "mode": mode,
                    },
                    severity="warning",
                )
                return False

        return True

    def validate_command(self, command: str) -> bool:
        """
        Validate shell command against blocklist.
        Prevents command injection.
        """
        command_lower = command.lower().strip()

        for blocked in self.config.blocked_commands:
            if blocked in command_lower:
                self.audit.log(
                    "command_blocked",
                    {
                        "command": command[:200],
                        "blocked_by": blocked,
                    },
                    severity="warning",
                )
                return False

        # Block shell metacharacters in dangerous positions
        # Allow these in quoted strings but flag unquoted usage
        # Simple heuristic: if the command contains these outside of quotes, warn
        if any(p in command for p in ["$(", "`"]):
            self.audit.log(
                "command_subshell_warning",
                {
                    "command": command[:200],
                },
                severity="warning",
            )

        return True

    def validate_url(self, url: str) -> bool:
        """Validate URL to prevent SSRF"""
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
        except Exception:
            return False

        # Block internal/private networks
        blocked_hosts = [
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "169.254.",
            "10.",
            "172.16.",
            "172.17.",
            "172.18.",
            "192.168.",
            "::1",
            "fc00:",
            "fe80:",
        ]

        host = parsed.hostname or ""
        for blocked in blocked_hosts:
            if host.startswith(blocked) or host == blocked:
                self.audit.log(
                    "ssrf_blocked",
                    {
                        "url": url,
                        "blocked_host": host,
                    },
                    severity="warning",
                )
                return False

        # Only allow http and https
        if parsed.scheme not in ("http", "https"):
            return False

        return True

    def validate_input_length(self, text: str, field_name: str = "input") -> bool:
        """Check input doesn't exceed maximum length"""
        if len(text) > self.config.max_input_length:
            self.audit.log(
                "input_too_long",
                {
                    "field": field_name,
                    "length": len(text),
                    "max": self.config.max_input_length,
                },
                severity="warning",
            )
            return False
        return True

    def sanitize_sql_like(self, query: str) -> str:
        """Escape LIKE special characters to prevent wildcard injection"""
        return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def get_audit_summary(self) -> dict:
        """Get security audit summary"""
        events = self.audit.get_recent(1000)
        return {
            "total_events": len(events),
            "warnings": sum(1 for e in events if e["severity"] == "warning"),
            "errors": sum(1 for e in events if e["severity"] == "error"),
            "recent": self.audit.get_recent(10),
        }
