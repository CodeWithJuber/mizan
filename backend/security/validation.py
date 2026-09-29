"""
Input Validation (Tazkiyah - تَزْكِيَة — Purification)
========================================================

"He has succeeded who purifies (Tazkiyah) it" — Quran 91:9

Purifies all input before it enters the system.
Prevents injection attacks, path traversal, and overflow.
"""

import ipaddress
import os
import re
from pathlib import Path
from urllib.parse import urlparse

# === Path Validation ===


def sanitize_path(path: str) -> str:
    """
    Resolve and sanitize a file path.
    Removes traversal attacks (../) and symbolic link tricks.
    """
    # Expand user home and resolve relative paths
    resolved = os.path.realpath(os.path.expanduser(path))

    # Remove null bytes (null byte injection)
    resolved = resolved.replace("\x00", "")

    return resolved


def validate_path_in_sandbox(path: str, allowed_dirs: list) -> bool:
    """
    Check if resolved path is within allowed directories.

    Uses proper path containment (not str.startswith): a sibling such as
    /tmp/mizan-evil/x must NOT pass for an allowed dir /tmp/mizan.
    """
    resolved = Path(sanitize_path(path))
    for d in allowed_dirs:
        try:
            if resolved.is_relative_to(Path(os.path.realpath(d))):
                return True
        except (ValueError, OSError):
            continue
    return False


# === Command Validation ===


def sanitize_command(command: str) -> str:
    """
    Basic command sanitization.
    Strips dangerous patterns while keeping the command functional.
    """
    # Remove null bytes
    command = command.replace("\x00", "")

    # Truncate extremely long commands
    if len(command) > 10000:
        command = command[:10000]

    return command.strip()


def validate_command_safe(command: str) -> tuple:
    """
    Validate a shell command for safety.
    Returns (is_safe: bool, reason: str).
    """
    if not command or not command.strip():
        return False, "Empty command"

    cmd_lower = command.lower().strip()

    # Critical: block destructive patterns
    destructive_patterns = [
        r"rm\s+(-\w+\s+)?/",  # rm -rf /
        r">\s*/dev/",  # > /dev/sda
        r"dd\s+.*of=/dev/",  # dd of=/dev/
        r"mkfs\.",  # mkfs.ext4
        r":\(\)\{",  # fork bomb
        r"chmod\s+777\s+/",  # chmod 777 /
        r"curl.*\|\s*(ba)?sh",  # curl | sh
        r"wget.*\|\s*(ba)?sh",  # wget | sh
        r"sudo\s",  # sudo
        r"\bsu\s+",  # su
        r"shutdown\b",  # shutdown
        r"reboot\b",  # reboot
        r"init\s+[06]",  # init 0/6
        r"kill\s+-9\s+1\b",  # kill init
        r"echo\s+.*>\s*/etc/",  # write to /etc
    ]

    for pattern in destructive_patterns:
        if re.search(pattern, cmd_lower):
            return False, "Blocked: matches destructive pattern"

    return True, "OK"


# === SQL Validation ===


def escape_sql_like(query: str) -> str:
    """Escape special LIKE characters to prevent wildcard injection"""
    return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# === URL Validation ===


def validate_url(url: str) -> tuple:
    """
    Validate URL for safety (SSRF prevention).
    Returns (is_safe: bool, reason: str).
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL"

    # Must have scheme and host
    if not parsed.scheme or not parsed.hostname:
        return False, "Missing scheme or hostname"

    # Only allow http/https
    if parsed.scheme not in ("http", "https"):
        return False, f"Blocked scheme: {parsed.scheme}"

    hostname = parsed.hostname.lower()

    # Resolve the host to an IP when it is an IP literal in any notation:
    # dotted decimal, integer decimal (http://2130706433/ = 127.0.0.1),
    # hex (http://0x7f000001/) or octal. urlparse keeps brackets off IPv6,
    # so strip them defensively.
    ip = _hostname_to_ip(hostname)
    if ip is not None:
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False, f"Blocked non-public IP: {hostname}"
        return True, "OK"

    # DNS name: block obvious local names. NOTE - DNS rebinding means a name
    # that resolves to a public IP now may resolve to a private IP later;
    # full protection requires re-checking the resolved IP at connection
    # time and on every redirect, or an egress allowlist.
    local_names = ("localhost",)
    if hostname in local_names or hostname.endswith((".localhost", ".local", ".internal")):
        return False, f"Blocked local hostname: {hostname}"

    # Block metadata endpoints (cloud SSRF)
    if hostname in ("metadata.google.internal", "metadata.google.com"):
        return False, "Blocked cloud metadata endpoint"

    return True, "OK"


def _hostname_to_ip(hostname: str):
    """
    Interpret a hostname as an IP address when it is an IP literal.

    Handles dotted notation, plain integers (decimal), 0x-hex and
    0-octal forms. Returns an ipaddress object or None for DNS names.
    """
    host = hostname.strip().strip("[]")
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    try:
        if host.lower().startswith("0x"):
            num = int(host, 16)
        elif host.isdigit():
            num = int(host, 10)
        elif len(host) > 1 and host.startswith("0") and all(c in "01234567" for c in host):
            num = int(host, 8)
        else:
            return None
        return ipaddress.ip_address(num)
    except ValueError:
        return None


# === Input Text Validation ===


def validate_text_input(text: str, max_length: int = 50000, field_name: str = "input") -> tuple:
    """
    Validate text input.
    Returns (is_valid: bool, reason: str, sanitized: str).
    """
    if text is None:
        return False, f"{field_name} is required", ""

    if not isinstance(text, str):
        return False, f"{field_name} must be a string", ""

    # Remove null bytes
    text = text.replace("\x00", "")

    if len(text) > max_length:
        return False, f"{field_name} exceeds maximum length ({max_length})", ""

    if len(text.strip()) == 0:
        return False, f"{field_name} cannot be empty", ""

    return True, "OK", text


# === Package Name Validation ===


def validate_package_name(package: str) -> tuple:
    """
    Validate package name for pip/npm install.
    Prevents malicious package injection.
    Returns (is_safe: bool, reason: str).
    """
    if not package or not package.strip():
        return False, "Empty package name"

    # Only allow alphanumeric, hyphens, underscores, dots, and version specifiers
    if not re.match(
        r"^[a-zA-Z0-9][\w\-\.]*(\[[\w,\-]+\])?(([<>=!~]+[\d\.\*]+)(,\s*([<>=!~]+[\d\.\*]+))*)?$",
        package,
    ):
        return False, "Invalid package name format"

    return True, "OK"


class InputValidator:
    """
    Unified input validator.
    Validates all types of input before processing.
    """

    def __init__(self, max_input_length: int = 50000):
        self.max_input_length = max_input_length

    def validate_task(self, task: str) -> tuple:
        return validate_text_input(task, self.max_input_length, "task")

    def validate_chat_message(self, content: str) -> tuple:
        return validate_text_input(content, self.max_input_length, "message")

    def validate_memory_query(self, query: str) -> tuple:
        return validate_text_input(query, 5000, "query")

    def validate_path(self, path: str, allowed_dirs: list = None) -> tuple:
        resolved = sanitize_path(path)
        if allowed_dirs and not validate_path_in_sandbox(path, allowed_dirs):
            return False, "Path outside allowed directories", resolved
        return True, "OK", resolved

    def validate_command(self, command: str) -> tuple:
        sanitized = sanitize_command(command)
        is_safe, reason = validate_command_safe(sanitized)
        return is_safe, reason, sanitized

    def validate_url(self, url: str) -> tuple:
        return validate_url(url)

    def validate_package(self, package: str) -> tuple:
        return validate_package_name(package)
