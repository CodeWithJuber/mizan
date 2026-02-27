"""
Input Validation (Tazkiyah - تَزْكِيَة — Purification)
========================================================

"He has succeeded who purifies (Tazkiyah) it" — Quran 91:9

Purifies all input before it enters the system.
Prevents injection attacks, path traversal, and overflow.
"""

import os
import re
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
    """Check if resolved path is within allowed directories"""
    resolved = sanitize_path(path)
    return any(resolved.startswith(os.path.realpath(d)) for d in allowed_dirs)


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

    # Block private/internal networks
    private_prefixes = [
        "localhost",
        "127.",
        "0.0.0.0",
        "10.",
        "172.16.",
        "172.17.",
        "172.18.",
        "172.19.",
        "172.20.",
        "172.21.",
        "172.22.",
        "172.23.",
        "172.24.",
        "172.25.",
        "172.26.",
        "172.27.",
        "172.28.",
        "172.29.",
        "172.30.",
        "172.31.",
        "192.168.",
        "169.254.",
        "[::1]",
    ]

    for prefix in private_prefixes:
        if hostname.startswith(prefix) or hostname == prefix.rstrip("."):
            return False, f"Blocked private/internal host: {hostname}"

    # Block metadata endpoints (cloud SSRF)
    if hostname in ("metadata.google.internal", "169.254.169.254"):
        return False, "Blocked cloud metadata endpoint"

    return True, "OK"


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
