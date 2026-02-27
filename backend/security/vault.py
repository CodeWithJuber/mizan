"""
Vault (خزنة) — Encrypted Secret Storage
=========================================

"And with Him are the keys of the unseen" — Quran 6:59

Encrypts sensitive configuration (API keys, tokens) at rest.
Addresses OpenClaw's critical weakness: plaintext credential storage.
"""

import json
import logging
import os

logger = logging.getLogger("mizan.vault")

# Use Fernet symmetric encryption (from cryptography library)
try:
    from cryptography.fernet import Fernet, InvalidToken

    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
    logger.warning("[VAULT] cryptography library not installed. Secrets stored in plaintext.")


class SecretVault:
    """
    Encrypted secret storage for MIZAN.
    Uses Fernet (AES-128-CBC) for symmetric encryption.
    Falls back to plaintext if cryptography is not available.
    """

    def __init__(self, vault_path: str = None, key_path: str = None):
        self.vault_path = vault_path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), ".vault.json"
        )
        self.key_path = key_path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), ".vault.key"
        )
        self._fernet: object | None = None
        self._secrets: dict = {}
        self._init_vault()

    def _init_vault(self):
        """Initialize encryption key and load existing secrets."""
        if not HAS_CRYPTO:
            self._load_plaintext()
            return

        # Load or generate encryption key
        if os.path.exists(self.key_path):
            with open(self.key_path, "rb") as f:
                key = f.read().strip()
        else:
            key = Fernet.generate_key()
            # Create key file with restrictive permissions
            fd = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(key)
            logger.info("[VAULT] Generated new encryption key")

        self._fernet = Fernet(key)

        # Load existing vault
        if os.path.exists(self.vault_path):
            try:
                with open(self.vault_path) as f:
                    encrypted_data = json.load(f)
                for name, enc_value in encrypted_data.items():
                    try:
                        decrypted = self._fernet.decrypt(enc_value.encode()).decode()
                        self._secrets[name] = decrypted
                    except InvalidToken:
                        logger.error(f"[VAULT] Failed to decrypt secret: {name}")
            except (OSError, json.JSONDecodeError) as e:
                logger.error(f"[VAULT] Failed to load vault: {e}")

    def _load_plaintext(self):
        """Fallback: load secrets from plaintext file."""
        if os.path.exists(self.vault_path):
            try:
                with open(self.vault_path) as f:
                    self._secrets = json.load(f)
            except (OSError, json.JSONDecodeError):
                self._secrets = {}

    def _save(self):
        """Save secrets to vault file."""
        if self._fernet:
            encrypted_data = {}
            for name, value in self._secrets.items():
                encrypted_data[name] = self._fernet.encrypt(value.encode()).decode()
            with open(self.vault_path, "w") as f:
                json.dump(encrypted_data, f, indent=2)
        else:
            with open(self.vault_path, "w") as f:
                json.dump(self._secrets, f, indent=2)

    def store(self, name: str, value: str) -> bool:
        """Store a secret securely."""
        self._secrets[name] = value
        self._save()
        logger.info(f"[VAULT] Stored secret: {name}")
        return True

    def retrieve(self, name: str) -> str | None:
        """Retrieve a secret by name."""
        return self._secrets.get(name)

    def delete(self, name: str) -> bool:
        """Delete a secret."""
        if name in self._secrets:
            del self._secrets[name]
            self._save()
            logger.info(f"[VAULT] Deleted secret: {name}")
            return True
        return False

    def list_names(self) -> list:
        """List secret names (not values)."""
        return list(self._secrets.keys())

    def has(self, name: str) -> bool:
        """Check if a secret exists."""
        return name in self._secrets

    def get_or_env(self, name: str, env_var: str = None) -> str | None:
        """
        Get secret from vault, falling back to environment variable.
        This is the recommended way to retrieve API keys.
        """
        value = self.retrieve(name)
        if value:
            return value
        env_key = env_var or name.upper().replace(".", "_")
        return os.getenv(env_key)

    @property
    def is_encrypted(self) -> bool:
        """Whether the vault uses encryption."""
        return self._fernet is not None

    def get_status(self) -> dict:
        """Get vault status for the settings API."""
        return {
            "encrypted": self.is_encrypted,
            "secrets_count": len(self._secrets),
            "secret_names": self.list_names(),
            "vault_path": self.vault_path,
            "has_crypto": HAS_CRYPTO,
        }
