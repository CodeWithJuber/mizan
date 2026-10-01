"""
MIZAN Authentication (Amanah - أَمَانَة — Trust)
==================================================

"Indeed, Allah commands you to render trusts (Amanah) to whom they are due" — Quran 4:58

JWT-based authentication with role-based access control.

Users are persisted to a JSON store under the data directory
(``MIZAN_DATA_DIR``, default ``/data/mizan``) so accounts survive
backend restarts. Writes are atomic (temp file + rename) and guarded
by a lock; a missing or unreadable store degrades to in-memory only.
"""

import json
import logging
import os
import tempfile
import threading
import time
import uuid
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import bcrypt
import jwt

logger = logging.getLogger(__name__)

# Default persistent data directory (matches the Wali sandbox allow-list).
DEFAULT_DATA_DIR = "/data/mizan"
USERS_FILENAME = "users.json"


def hash_password(password: str) -> str:
    """Hash a password with bcrypt.

    bcrypt hard-errors on inputs longer than 72 bytes (v5+); we truncate
    explicitly and document it instead of relying on silent truncation.
    Output is standard $2b$ format, compatible with hashes made by passlib.
    """
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a $2b$ hash (same 72-byte rule as hashing)."""
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# Roles hierarchy
ROLES = {
    "admin": 100,
    "user": 50,
    "agent": 30,
    "viewer": 10,
    "guest": 0,
}


# Request-scoped principal roles, bound by require_auth (or the WebSocket
# handshake) for the lifetime of the request task. Default is empty:
# fail closed - code running outside an authenticated request (background
# jobs, tests, imports) holds no privileges.
_request_roles: ContextVar[tuple] = ContextVar("mizan_request_roles", default=())


def set_request_roles(roles) -> None:
    """Bind the current request principal's roles. Call once per request."""
    _request_roles.set(tuple(roles or ()))


def request_has_role(role: str) -> bool:
    """True if the current request principal holds `role` (admin implies all)."""
    roles = _request_roles.get()
    return role in roles or "admin" in roles


_request_user: ContextVar[str | None] = ContextVar("mizan_request_user", default=None)


def bind_principal(user):
    return (_request_user.set(user.user_id), _request_roles.set(tuple(user.roles)))


def reset_principal(tokens):
    _request_user.reset(tokens[0])
    _request_roles.reset(tokens[1])


def current_user_id() -> str | None:
    return _request_user.get()


@dataclass
class TokenPayload:
    """Decoded JWT token data"""

    user_id: str
    username: str
    roles: list[str]
    exp: float
    iat: float
    jti: str  # Token ID for revocation

    @property
    def is_expired(self) -> bool:
        return time.time() > self.exp

    def has_role(self, role: str) -> bool:
        if "admin" in self.roles:
            return True
        return role in self.roles

    def has_min_role(self, min_role: str) -> bool:
        """Check if user has at least the specified role level"""
        min_level = ROLES.get(min_role, 0)
        return any(ROLES.get(r, 0) >= min_level for r in self.roles)


@dataclass
class UserRecord:
    """User stored in memory/database"""

    id: str
    username: str
    password_hash: str
    roles: list[str]
    created_at: str
    api_keys: list[str]
    enabled: bool = True


class MizanAuth:
    """
    Authentication and authorization system.
    Supports JWT tokens, API keys, and WebSocket auth.

    Users persist to ``<data_dir>/users.json`` (atomic writes). Pass
    ``data_dir=None`` to use ``$MIZAN_DATA_DIR`` or ``/data/mizan``.
    """

    def __init__(self, secret_key: str, expiry_hours: int = 24, data_dir: str | None = None):
        self.secret_key = secret_key or os.urandom(32).hex()
        self.expiry_hours = expiry_hours
        self.algorithm = "HS256"

        self.data_dir = Path(data_dir or (os.getenv("MIZAN_DATA_DIR") or DEFAULT_DATA_DIR))
        self._users_file = self.data_dir / USERS_FILENAME
        self._lock = threading.Lock()

        self._users: dict[str, UserRecord] = {}
        self._revoked_tokens: set = set()
        self._api_keys: dict[str, str] = {}  # api_key -> user_id

        # Load persisted users before the default-admin check so a
        # restarted server keeps its accounts.
        self._load_users()

        # Create default admin if no users exist
        self._ensure_default_admin()

    def _load_users(self) -> None:
        """Load users from the JSON store. Best-effort: never crash startup."""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning(
                "Cannot create data dir %s (%s); using in-memory user store",
                self.data_dir,
                exc,
            )
            return

        if not self._users_file.exists():
            return

        try:
            raw = json.loads(self._users_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning(
                "Cannot read user store %s (%s); starting with empty user store",
                self._users_file,
                exc,
            )
            return

        if not isinstance(raw, list):
            logger.warning(
                "User store %s is malformed; starting with empty user store",
                self._users_file,
            )
            return

        for item in raw:
            try:
                user = UserRecord(
                    id=str(item["id"]),
                    username=str(item["username"]),
                    password_hash=str(item["password_hash"]),
                    roles=list(item.get("roles") or ["user"]),
                    created_at=str(item.get("created_at") or ""),
                    api_keys=list(item.get("api_keys") or []),
                    enabled=bool(item.get("enabled", True)),
                )
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Skipping malformed user record: %s", exc)
                continue
            self._users[user.id] = user
            for key in user.api_keys:
                self._api_keys[key] = user.id

    def _save_users(self) -> None:
        """Persist all users atomically (temp file + rename). Best-effort."""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            payload = json.dumps([asdict(u) for u in self._users.values()], indent=2)
            fd, tmp_path = tempfile.mkstemp(dir=str(self.data_dir), prefix="users.", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                os.replace(tmp_path, self._users_file)
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except OSError as exc:
            logger.warning("Cannot persist users to %s (%s)", self._users_file, exc)

    def _ensure_default_admin(self):
        """Create default admin user from environment"""
        admin_user = os.getenv("MIZAN_ADMIN_USER", "admin")
        admin_pass = os.getenv("MIZAN_ADMIN_PASS", "")

        if admin_pass and admin_user not in {u.username for u in self._users.values()}:
            self.create_user(admin_user, admin_pass, roles=["admin"])

    def create_user(
        self, username: str, password: str, roles: list[str] | None = None
    ) -> UserRecord:
        """Create a new user"""
        user_id = str(uuid.uuid4())
        user = UserRecord(
            id=user_id,
            username=username,
            password_hash=hash_password(password),
            roles=roles or ["user"],
            created_at=datetime.now(UTC).isoformat(),
            api_keys=[],
        )
        with self._lock:
            self._users[user_id] = user
            self._save_users()
        return user

    def authenticate(self, username: str, password: str) -> UserRecord | None:
        """Authenticate user with username and password"""
        for user in self._users.values():
            if user.username == username and user.enabled:
                if verify_password(password, user.password_hash):
                    return user
        return None

    def create_token(self, user: UserRecord) -> str:
        """Create JWT token for authenticated user"""
        now = time.time()
        payload = {
            "user_id": user.id,
            "username": user.username,
            "roles": user.roles,
            "iat": now,
            "exp": now + (self.expiry_hours * 3600),
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> TokenPayload | None:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
            )

            # Check if revoked
            if payload.get("jti") in self._revoked_tokens:
                return None

            return TokenPayload(
                user_id=payload["user_id"],
                username=payload["username"],
                roles=payload["roles"],
                exp=payload["exp"],
                iat=payload["iat"],
                jti=payload["jti"],
            )
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def revoke_token(self, jti: str):
        """Revoke a specific token"""
        self._revoked_tokens.add(jti)

    def create_api_key(self, user_id: str) -> str | None:
        """Create an API key for a user"""
        with self._lock:
            if user_id not in self._users:
                return None

            key = f"mzn_{uuid.uuid4().hex}"
            self._api_keys[key] = user_id
            self._users[user_id].api_keys.append(key)
            self._save_users()
            return key

    def verify_api_key(self, key: str) -> TokenPayload | None:
        """Verify an API key and return a token payload"""
        user_id = self._api_keys.get(key)
        if not user_id or user_id not in self._users:
            return None

        user = self._users[user_id]
        if not user.enabled:
            return None

        return TokenPayload(
            user_id=user.id,
            username=user.username,
            roles=user.roles,
            exp=time.time() + 3600,  # API keys are always valid
            iat=time.time(),
            jti=f"apikey_{key[:8]}",
        )

    def extract_token(
        self, authorization: str | None = None, api_key: str | None = None
    ) -> TokenPayload | None:
        """
        Extract and verify token from various sources.
        Supports: Bearer token, API key, query param.
        """
        # Try Bearer token
        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:]
            return self.verify_token(token)

        # Try API key
        if api_key:
            return self.verify_api_key(api_key)

        return None

    def get_user(self, user_id: str) -> UserRecord | None:
        return self._users.get(user_id)

    def list_users(self) -> list[dict]:
        return [
            {
                "id": u.id,
                "username": u.username,
                "roles": u.roles,
                "created_at": u.created_at,
                "enabled": u.enabled,
            }
            for u in self._users.values()
        ]
