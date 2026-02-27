"""
MIZAN Authentication (Amanah - أَمَانَة — Trust)
==================================================

"Indeed, Allah commands you to render trusts (Amanah) to whom they are due" — Quran 4:58

JWT-based authentication with role-based access control.
"""

import os
import time
import uuid
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass

import jwt
from passlib.context import CryptContext


# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Roles hierarchy
ROLES = {
    "admin": 100,
    "user": 50,
    "agent": 30,
    "viewer": 10,
    "guest": 0,
}


@dataclass
class TokenPayload:
    """Decoded JWT token data"""
    user_id: str
    username: str
    roles: List[str]
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
    roles: List[str]
    created_at: str
    api_keys: List[str]
    enabled: bool = True


class MizanAuth:
    """
    Authentication and authorization system.
    Supports JWT tokens, API keys, and WebSocket auth.
    """

    def __init__(self, secret_key: str, expiry_hours: int = 24):
        self.secret_key = secret_key or os.urandom(32).hex()
        self.expiry_hours = expiry_hours
        self.algorithm = "HS256"

        # In-memory user store (later: move to DhikrMemorySystem)
        self._users: Dict[str, UserRecord] = {}
        self._revoked_tokens: set = set()
        self._api_keys: Dict[str, str] = {}  # api_key -> user_id

        # Create default admin if no users exist
        self._ensure_default_admin()

    def _ensure_default_admin(self):
        """Create default admin user from environment"""
        admin_user = os.getenv("MIZAN_ADMIN_USER", "admin")
        admin_pass = os.getenv("MIZAN_ADMIN_PASS", "")

        if admin_pass and admin_user not in {u.username for u in self._users.values()}:
            self.create_user(admin_user, admin_pass, roles=["admin"])

    def create_user(self, username: str, password: str,
                    roles: List[str] = None) -> UserRecord:
        """Create a new user"""
        user_id = str(uuid.uuid4())
        user = UserRecord(
            id=user_id,
            username=username,
            password_hash=pwd_context.hash(password),
            roles=roles or ["user"],
            created_at=datetime.now(timezone.utc).isoformat(),
            api_keys=[],
        )
        self._users[user_id] = user
        return user

    def authenticate(self, username: str, password: str) -> Optional[UserRecord]:
        """Authenticate user with username and password"""
        for user in self._users.values():
            if user.username == username and user.enabled:
                if pwd_context.verify(password, user.password_hash):
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

    def verify_token(self, token: str) -> Optional[TokenPayload]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(
                token, self.secret_key,
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

    def create_api_key(self, user_id: str) -> Optional[str]:
        """Create an API key for a user"""
        if user_id not in self._users:
            return None

        key = f"mzn_{uuid.uuid4().hex}"
        self._api_keys[key] = user_id
        self._users[user_id].api_keys.append(key)
        return key

    def verify_api_key(self, key: str) -> Optional[TokenPayload]:
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

    def extract_token(self, authorization: str = None,
                      api_key: str = None) -> Optional[TokenPayload]:
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

    def get_user(self, user_id: str) -> Optional[UserRecord]:
        return self._users.get(user_id)

    def list_users(self) -> List[Dict]:
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
