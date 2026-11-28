"""Sakk (صَكّ, a written deed): a tamper-evident record of what MIZAN did for each person.

Every action MIZAN takes or holds is written as a receipt in its owner's chain:
the tool, the outcome, keyed digests of what went in and what came out, and
the hash of the receipt before it. A receipt's hash is SHA-256 over its RFC
8785 canonical JSON, so changing, removing or reordering any receipt breaks
every hash after it, and ``verify`` names where.

No content is kept. Parameters and results are recorded only as HMAC-SHA256
under a key of the owner's own, sealed with the data key: the owner, who can
export the key, can show a receipt matches what they hold; nobody else can
test a guess against it. The short display line ("bash · held") sits outside
the hashed fields.

Once a day MIZAN signs, with an Ed25519 key of its own, the Merkle root of
every chain's latest receipt (RFC 6962 leaf and node hashing). The roots and
the public key are public, and any owner can prove their chain is in a signed
root, so a history cannot be rewritten later without the signature showing it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import rfc8785

logger = logging.getLogger("mizan.sakk")

GENESIS = "0" * 64
VERSION = 1


def canonical(value: Any) -> bytes:
    """RFC 8785 JSON. A value it cannot hold (bytes, NaN, an integer past 2^53, an
    object) is canonicalized as its sorted JSON text instead."""
    try:
        return bytes(rfc8785.dumps(value))
    except (ValueError, TypeError):  # rfc8785.CanonicalizationError is a ValueError
        return bytes(rfc8785.dumps(json.dumps(value, default=str, sort_keys=True)))


def digest(body: dict) -> str:
    return hashlib.sha256(canonical(body)).hexdigest()


def outcome(result: Any) -> str:
    """What became of an action, read from its result."""
    if isinstance(result, dict):
        if result.get("held_for_approval"):
            return "held"
        if result.get("declined"):
            return "declined"
        if result.get("error"):
            return "error"
    return "done"


# ── Merkle tree (RFC 6962 hashing) ───────────────────────────────────────


def _leaf(data: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + data).digest()


def _node(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def merkle_root(leaves: list[bytes]) -> bytes:
    if not leaves:
        return hashlib.sha256(b"").digest()
    level = [_leaf(item) for item in leaves]
    while len(level) > 1:
        level = [
            _node(level[i], level[i + 1]) if i + 1 < len(level) else level[i]
            for i in range(0, len(level), 2)
        ]
    return level[0]


def merkle_proof(leaves: list[bytes], index: int) -> list[tuple[str, str]]:
    """The sibling hashes from leaf ``index`` up, each with its side."""
    level = [_leaf(item) for item in leaves]
    path: list[tuple[str, str]] = []
    while len(level) > 1:
        sibling = index ^ 1
        if sibling < len(level):
            path.append(("left" if sibling < index else "right", level[sibling].hex()))
        level = [
            _node(level[i], level[i + 1]) if i + 1 < len(level) else level[i]
            for i in range(0, len(level), 2)
        ]
        index //= 2
    return path


def proof_root(data: bytes, path: list[tuple[str, str]] | list[list[str]]) -> str:
    current = _leaf(data)
    for side, other in path:
        sibling = bytes.fromhex(other)
        current = _node(sibling, current) if side == "left" else _node(current, sibling)
    return current.hex()


def head_leaf(owner: str, seq: int, head: str) -> bytes:
    """One chain's latest receipt as a leaf; the owner appears only as a digest."""
    return canonical(
        {"owner": hashlib.sha256(owner.encode()).hexdigest(), "seq": seq, "head": head}
    )


def root_message(day: str, root: str, leaves: int) -> bytes:
    return canonical({"v": VERSION, "day": day, "root": root, "leaves": leaves})


# ── the store ────────────────────────────────────────────────────────────


class Sakk:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._keys: dict[str, bytes] = {}
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS receipts (
                    owner TEXT NOT NULL, seq INTEGER NOT NULL, at TEXT NOT NULL,
                    kind TEXT NOT NULL, body TEXT NOT NULL, hash TEXT NOT NULL,
                    display TEXT NOT NULL DEFAULT '', PRIMARY KEY (owner, seq));
                CREATE TABLE IF NOT EXISTS keys (owner TEXT PRIMARY KEY, sealed TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS roots (
                    day TEXT PRIMARY KEY, root TEXT NOT NULL, leaves TEXT NOT NULL,
                    signature TEXT NOT NULL, at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS checkpoints (
                    at TEXT PRIMARY KEY, day TEXT NOT NULL, root TEXT NOT NULL,
                    leaves TEXT NOT NULL, signature TEXT NOT NULL);
                INSERT OR IGNORE INTO checkpoints SELECT at, day, root, leaves, signature
                    FROM roots;
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # ── keyed digests ────────────────────────────────────────────────────

    def _owner_key(self, owner: str) -> bytes:
        if owner in self._keys:
            return self._keys[owner]
        from connectors.secrets import seal, unseal

        with self._connect() as conn:
            row = conn.execute("SELECT sealed FROM keys WHERE owner = ?", (owner,)).fetchone()
            if row is not None:
                key = bytes.fromhex(str(unseal(row["sealed"])))
            else:
                key = secrets.token_bytes(32)
                conn.execute("INSERT INTO keys VALUES (?, ?)", (owner, seal(key.hex())))
        self._keys[owner] = key
        return key

    def mac(self, owner: str, value: Any) -> str:
        return hmac.new(self._owner_key(owner), canonical(value), hashlib.sha256).hexdigest()

    # ── writing ──────────────────────────────────────────────────────────

    def append(self, owner: str, kind: str, fields: dict, display: str = "") -> dict:
        owner = owner or "system"
        with self._lock, self._connect() as conn:
            last = conn.execute(
                "SELECT seq, hash FROM receipts WHERE owner = ? ORDER BY seq DESC LIMIT 1",
                (owner,),
            ).fetchone()
            seq = (last["seq"] + 1) if last else 1
            body = {
                "v": VERSION,
                "owner": owner,
                "seq": seq,
                "at": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "kind": kind,
                **fields,
                "prev": last["hash"] if last else GENESIS,
            }
            found = digest(body)
            conn.execute(
                "INSERT INTO receipts VALUES (?,?,?,?,?,?,?)",
                (owner, seq, body["at"], kind, json.dumps(body), found, display[:120]),
            )
        return {**body, "hash": found}

    def record_tool(self, owner: str, tool: str, params: Any, result: Any) -> dict | None:
        """A receipt for one tool call (returned, or None when it could not be
        written); never raises into the call it records."""
        try:
            owner = owner or "system"
            state = outcome(result)
            return self.append(
                owner,
                "tool",
                {
                    "tool": tool,
                    "outcome": state,
                    "params": self.mac(owner, params),
                    "result": self.mac(owner, result),
                },
                f"{tool} · {state}",
            )
        except Exception:  # noqa: BLE001 - a receipt failure must not undo an action
            logger.exception("[SAKK] receipt not written for %s", tool)
            return None

    def record(self, owner: str, kind: str, fields: dict, display: str = "") -> None:
        try:
            self.append(owner, kind, fields, display)
        except Exception:  # noqa: BLE001
            logger.exception("[SAKK] %s receipt not written", kind)

    # ── reading ──────────────────────────────────────────────────────────

    def receipts(self, owner: str, limit: int = 50, before: int | None = None) -> list[dict]:
        query = "SELECT * FROM receipts WHERE owner = ?"
        params: list[Any] = [owner]
        if before:
            query += " AND seq < ?"
            params.append(before)
        query += " ORDER BY seq DESC LIMIT ?"
        params.append(max(1, min(500, limit)))
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {**json.loads(row["body"]), "hash": row["hash"], "display": row["display"]}
            for row in rows
        ]

    def verify(self, owner: str) -> dict:
        """Recompute the owner's chain from the start; name the first receipt that fails."""
        expected_prev, expected_seq, count = GENESIS, 1, 0
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT seq, body, hash FROM receipts WHERE owner = ? ORDER BY seq", (owner,)
            ).fetchall()
        for row in rows:
            body = json.loads(row["body"])
            problem = (
                "missing or reordered receipt"
                if row["seq"] != expected_seq or body.get("seq") != expected_seq
                else "receipt belongs to another chain"
                if body.get("owner") != owner
                else "link to the previous receipt is broken"
                if body.get("prev") != expected_prev
                else "receipt was changed"
                if digest(body) != row["hash"]
                else ""
            )
            if problem:
                return {
                    "ok": False,
                    "receipts": len(rows),
                    "broken_at": expected_seq,
                    "problem": problem,
                }
            expected_prev, expected_seq, count = row["hash"], expected_seq + 1, count + 1
        return {"ok": True, "receipts": count, "head": expected_prev if count else None}

    def owners(self) -> list[str]:
        with self._connect() as conn:
            return [row[0] for row in conn.execute("SELECT DISTINCT owner FROM receipts")]

    def heads(self) -> list[tuple[str, int, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT owner, seq, hash FROM receipts r WHERE seq = "
                "(SELECT MAX(seq) FROM receipts WHERE owner = r.owner) ORDER BY owner"
            ).fetchall()
        return [(row["owner"], row["seq"], row["hash"]) for row in rows]

    # ── daily signed roots ───────────────────────────────────────────────

    def _signer(self) -> Any:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        from connectors.secrets import seal, unseal

        with self._connect() as conn:
            row = conn.execute("SELECT value FROM state WHERE key = 'signing_key'").fetchone()
            if row is not None:
                raw = bytes.fromhex(str(unseal(row["value"])))
                return Ed25519PrivateKey.from_private_bytes(raw)
            key = Ed25519PrivateKey.generate()
            raw = key.private_bytes(
                serialization.Encoding.Raw,
                serialization.PrivateFormat.Raw,
                serialization.NoEncryption(),
            )
            conn.execute("INSERT INTO state VALUES ('signing_key', ?)", (seal(raw.hex()),))
            return key

    def public_key(self) -> str:
        from cryptography.hazmat.primitives import serialization

        raw = (
            self._signer()
            .public_key()
            .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        )
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    def sign_day(self, day: str | None = None) -> dict:
        """Sign the Merkle root of every chain's latest receipt: at least once
        per UTC day, and again whenever a chain has moved since the last
        signed checkpoint, so the public root never lags the receipts."""
        day = day or datetime.now(UTC).date().isoformat()
        heads = self.heads()
        listed = json.dumps([[o, s, h] for o, s, h in heads])
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM checkpoints ORDER BY at DESC LIMIT 1").fetchone()
        if row is not None and row["day"] == day and row["leaves"] == listed:
            return self._root(row)
        leaves = [head_leaf(owner, seq, head) for owner, seq, head in heads]
        root = merkle_root(leaves).hex()
        signature = self._signer().sign(root_message(day, root, len(leaves)))
        record = (
            datetime.now(UTC).isoformat(timespec="microseconds"),
            day,
            root,
            listed,
            base64.urlsafe_b64encode(signature).decode().rstrip("="),
        )
        with self._lock, self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO checkpoints VALUES (?,?,?,?,?)", record)
            row = conn.execute("SELECT * FROM checkpoints WHERE at = ?", (record[0],)).fetchone()
        return self._root(row)

    @staticmethod
    def _root(row: sqlite3.Row) -> dict:
        return {
            "day": row["day"],
            "root": row["root"],
            "leaves": len(json.loads(row["leaves"])),
            "signature": row["signature"],
            "signed_at": row["at"],
        }

    def roots(self, limit: int = 30) -> list[dict]:
        """The signed checkpoints, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM checkpoints ORDER BY at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._root(row) for row in rows]

    def proof(self, owner: str) -> dict | None:
        """Where the owner's chain sits in the latest signed checkpoint."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM checkpoints ORDER BY at DESC LIMIT 1").fetchone()
        if row is None:
            return None
        heads = [tuple(item) for item in json.loads(row["leaves"])]
        leaves = [head_leaf(o, s, h) for o, s, h in heads]
        for index, (found, seq, head) in enumerate(heads):
            if found == owner:
                return {
                    **self._root(row),
                    "seq": seq,
                    "head": head,
                    "leaf": head_leaf(owner, seq, head).decode(),
                    "path": merkle_proof(leaves, index),
                }
        return {**self._root(row), "seq": None, "head": None, "leaf": None, "path": []}

    def export(self, owner: str) -> dict:
        """The owner's whole chain, their digest key, MIZAN's public key and their proof."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT body, hash FROM receipts WHERE owner = ? ORDER BY seq", (owner,)
            ).fetchall()
        return {
            "format": "mizan-sakk/1",
            "owner": owner,
            "receipts": [{"body": json.loads(r["body"]), "hash": r["hash"]} for r in rows],
            "digest_key": self._owner_key(owner).hex(),
            "public_key": self.public_key(),
            "proof": self.proof(owner),
        }


def verify_export(data: dict) -> dict:
    """Check an export with no access to MIZAN: chain, inclusion and signature."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    prev, problems = GENESIS, []
    receipts = data.get("receipts") or []
    for index, item in enumerate(receipts, start=1):
        body = item["body"]
        if body.get("seq") != index or body.get("prev") != prev or digest(body) != item["hash"]:
            problems.append(f"receipt {index} does not verify")
            break
        prev = item["hash"]
    proof = data.get("proof") or {}
    included = signed = None
    if proof.get("leaf"):
        included = proof_root(proof["leaf"].encode(), proof["path"]) == proof["root"]
        key = base64.urlsafe_b64decode(data["public_key"] + "=" * (-len(data["public_key"]) % 4))
        signature = base64.urlsafe_b64decode(
            proof["signature"] + "=" * (-len(proof["signature"]) % 4)
        )
        try:
            Ed25519PublicKey.from_public_bytes(key).verify(
                signature, root_message(proof["day"], proof["root"], proof["leaves"])
            )
            signed = True
        except InvalidSignature:
            signed = False
        if included and not any(r["hash"] == proof.get("head") for r in receipts):
            problems.append("the signed head is not in this chain")
    if included is False:
        problems.append("the chain is not in the signed root")
    if signed is False:
        problems.append("the root's signature does not verify")
    return {
        "ok": not problems,
        "receipts": len(receipts),
        "included": included,
        "signed": signed,
        "problems": problems,
    }


_STORES: dict[str, Sakk] = {}


def store() -> Sakk:
    path = str(Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan")) / "sakk.db")
    if path not in _STORES:
        _STORES[path] = Sakk(path)
    return _STORES[path]


def record_tool(owner: str, tool: str, params: Any, result: Any) -> dict | None:
    """Write a tool receipt and return it; an unwritable store is logged, never raised."""
    try:
        sakk = store()
    except Exception:  # noqa: BLE001 - e.g. a read-only data directory
        logger.warning("[SAKK] store unavailable; receipt for %s not written", tool)
        return None
    return sakk.record_tool(owner, tool, params, result)


def record(owner: str, kind: str, fields: dict, display: str = "") -> None:
    try:
        sakk = store()
    except Exception:  # noqa: BLE001
        logger.warning("[SAKK] store unavailable; %s receipt not written", kind)
        return
    sakk.record(owner, kind, fields, display)
