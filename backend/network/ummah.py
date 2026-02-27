"""
Ummah (أمة) — Federated Instance Network
==========================================

"You are the best nation (Ummah) produced for mankind." — Quran 3:110

P2P knowledge sharing between MIZAN instances with privacy-preserving
federated learning. Each instance retains sovereignty while benefiting
from collective wisdom.

Architecture:
  - Each MIZAN instance = node in the Ummah
  - Nodes discover each other via Salam handshake protocol
  - Knowledge shared via Risalah (message) protocol
  - Privacy preserved: only aggregated insights shared, never raw data
  - Trust built through NafsTrustLevel — higher trust = more sharing
  - Consensus via Shura voting on disputed knowledge
"""

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("mizan.ummah")


class NodeStatus(Enum):
    ACTIVE = "active"
    IDLE = "idle"
    SYNCING = "syncing"
    OFFLINE = "offline"
    UNTRUSTED = "untrusted"


class SharingLevel(Enum):
    """How much knowledge a node shares — tied to trust."""

    NONE = "none"  # No sharing (untrusted / Ammara)
    METADATA = "metadata"  # Share only topic labels, no content
    SUMMARY = "summary"  # Share summarized/aggregated insights
    FULL = "full"  # Share full knowledge entries (high trust)


@dataclass
class UmmahNode:
    """A single MIZAN instance in the federation."""

    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    address: str = ""  # host:port
    public_key: str = ""
    status: NodeStatus = NodeStatus.IDLE
    nafs_level: int = 1
    sharing_level: SharingLevel = SharingLevel.METADATA
    trust_score: float = 0.0
    last_seen: float = field(default_factory=time.time)
    joined_at: float = field(default_factory=time.time)
    knowledge_count: int = 0
    sync_count: int = 0
    failed_syncs: int = 0

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "address": self.address,
            "status": self.status.value,
            "nafs_level": self.nafs_level,
            "sharing_level": self.sharing_level.value,
            "trust_score": round(self.trust_score, 3),
            "last_seen": self.last_seen,
            "knowledge_count": self.knowledge_count,
            "sync_count": self.sync_count,
        }


@dataclass
class KnowledgeShard:
    """
    A shareable piece of knowledge — privacy-preserving representation.
    Never shares raw user data; only derived insights and patterns.
    """

    shard_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    topic: str = ""
    summary: str = ""
    domain: str = ""
    confidence: float = 0.5
    source_node: str = ""
    timestamp: float = field(default_factory=time.time)
    hash_fingerprint: str = ""  # For deduplication
    yaqin_level: str = "ilm"  # ilm / ayn / haqq
    verification_count: int = 0

    def compute_hash(self) -> str:
        content = f"{self.topic}:{self.summary}:{self.domain}"
        self.hash_fingerprint = hashlib.sha256(content.encode()).hexdigest()[:16]
        return self.hash_fingerprint

    def to_dict(self) -> dict:
        return {
            "shard_id": self.shard_id,
            "topic": self.topic,
            "summary": self.summary,
            "domain": self.domain,
            "confidence": self.confidence,
            "source_node": self.source_node,
            "yaqin_level": self.yaqin_level,
            "verification_count": self.verification_count,
            "hash": self.hash_fingerprint,
        }


class UmmahNetwork:
    """
    The Ummah — federated network of MIZAN instances.

    Protocol phases:
      1. Salam (سلام) — Discovery handshake
      2. Bayah (بيعة) — Pledge of trust/mutual agreement
      3. Risalah (رسالة) — Knowledge message exchange
      4. Shura (شورى) — Consensus on disputed knowledge
      5. Hisab (حساب) — Periodic trust accounting

    Privacy guarantees:
      - Raw user data never leaves the instance
      - Only aggregated insights (KnowledgeShards) are shared
      - Differential privacy noise can be added to sensitive metrics
      - Nodes can revoke sharing at any time
    """

    # Trust score needed for each sharing level
    TRUST_THRESHOLDS = {
        SharingLevel.NONE: 0.0,
        SharingLevel.METADATA: 0.2,
        SharingLevel.SUMMARY: 0.5,
        SharingLevel.FULL: 0.8,
    }

    def __init__(self, instance_id: str = None, instance_name: str = "MIZAN"):
        self.instance_id = instance_id or str(uuid.uuid4())
        self.instance_name = instance_name
        self.nodes: dict[str, UmmahNode] = {}
        self.knowledge_pool: dict[str, KnowledgeShard] = {}
        self.pending_syncs: list[dict] = []
        self.sync_history: list[dict] = []
        self._running = False

    # ─── Salam: Discovery ───

    async def salam_handshake(self, remote_address: str, remote_info: dict) -> UmmahNode | None:
        """
        Salam (سلام) — Peace greeting / discovery handshake.
        Exchange basic info to establish connection.
        """
        node_id = remote_info.get("node_id", str(uuid.uuid4()))

        if node_id in self.nodes:
            # Update existing node
            node = self.nodes[node_id]
            node.last_seen = time.time()
            node.status = NodeStatus.ACTIVE
            logger.info(f"[SALAM] Reconnected with node: {node.name}")
            return node

        node = UmmahNode(
            node_id=node_id,
            name=remote_info.get("name", f"Node-{node_id[:8]}"),
            address=remote_address,
            public_key=remote_info.get("public_key", ""),
            status=NodeStatus.ACTIVE,
            nafs_level=remote_info.get("nafs_level", 1),
            sharing_level=SharingLevel.METADATA,  # Start with metadata only
            trust_score=0.1,  # Minimal initial trust
        )

        self.nodes[node_id] = node
        logger.info(f"[SALAM] New node joined Ummah: {node.name} ({remote_address})")
        return node

    # ─── Bayah: Trust Building ───

    def update_trust(self, node_id: str, interaction_success: bool) -> float:
        """
        Bayah (بيعة) — Update trust score based on interaction quality.
        Successful syncs increase trust; failures decrease it.
        """
        node = self.nodes.get(node_id)
        if not node:
            return 0.0

        if interaction_success:
            node.trust_score = min(1.0, node.trust_score + 0.05)
            node.sync_count += 1
        else:
            node.trust_score = max(0.0, node.trust_score - 0.10)
            node.failed_syncs += 1

        # Update sharing level based on trust
        for level in reversed(list(SharingLevel)):
            threshold = self.TRUST_THRESHOLDS[level]
            if node.trust_score >= threshold:
                node.sharing_level = level
                break

        return node.trust_score

    # ─── Risalah: Knowledge Exchange ───

    async def share_knowledge(self, node_id: str, shards: list[KnowledgeShard]) -> dict:
        """
        Risalah (رسالة) — Share knowledge with a specific node.
        Respects the node's sharing level permissions.
        """
        node = self.nodes.get(node_id)
        if not node:
            return {"error": "Node not found", "shared": 0}

        if node.status == NodeStatus.OFFLINE:
            return {"error": "Node offline", "shared": 0}

        shared_count = 0
        for shard in shards:
            shard.compute_hash()

            # Apply sharing level filter
            if node.sharing_level == SharingLevel.NONE:
                continue
            elif node.sharing_level == SharingLevel.METADATA:
                # Strip content, only share topic + domain
                filtered = KnowledgeShard(
                    topic=shard.topic,
                    domain=shard.domain,
                    confidence=shard.confidence,
                    source_node=self.instance_id,
                )
                filtered.compute_hash()
                self.knowledge_pool[filtered.hash_fingerprint] = filtered
            elif node.sharing_level == SharingLevel.SUMMARY:
                # Share summary but not full details
                filtered = KnowledgeShard(
                    topic=shard.topic,
                    summary=shard.summary[:200],
                    domain=shard.domain,
                    confidence=shard.confidence,
                    source_node=self.instance_id,
                    yaqin_level=shard.yaqin_level,
                )
                filtered.compute_hash()
                self.knowledge_pool[filtered.hash_fingerprint] = filtered
            else:
                # Full sharing
                shard.source_node = self.instance_id
                self.knowledge_pool[shard.hash_fingerprint] = shard

            shared_count += 1

        self.update_trust(node_id, True)

        self.sync_history.append(
            {
                "node_id": node_id,
                "direction": "outbound",
                "shards_shared": shared_count,
                "timestamp": time.time(),
            }
        )

        logger.info(f"[RISALAH] Shared {shared_count} shards with {node.name}")
        return {"shared": shared_count, "node": node_id}

    async def receive_knowledge(self, source_node_id: str, shards: list[dict]) -> dict:
        """Receive knowledge shards from another node."""
        node = self.nodes.get(source_node_id)
        if not node:
            return {"error": "Unknown source node", "received": 0}

        received = 0
        for shard_data in shards:
            shard = KnowledgeShard(
                topic=shard_data.get("topic", ""),
                summary=shard_data.get("summary", ""),
                domain=shard_data.get("domain", ""),
                confidence=shard_data.get("confidence", 0.5),
                source_node=source_node_id,
                yaqin_level=shard_data.get("yaqin_level", "ilm"),
            )
            shard.compute_hash()

            # Deduplication: skip if we already have this
            if shard.hash_fingerprint in self.knowledge_pool:
                existing = self.knowledge_pool[shard.hash_fingerprint]
                existing.verification_count += 1  # Cross-verification
                continue

            self.knowledge_pool[shard.hash_fingerprint] = shard
            received += 1

        self.update_trust(source_node_id, True)
        node.knowledge_count += received

        self.sync_history.append(
            {
                "node_id": source_node_id,
                "direction": "inbound",
                "shards_received": received,
                "timestamp": time.time(),
            }
        )

        logger.info(f"[RISALAH] Received {received} shards from {node.name}")
        return {"received": received, "source": source_node_id}

    # ─── Shura: Consensus ───

    async def shura_verify(self, shard_id: str) -> dict:
        """
        Shura (شورى) — Request consensus on a disputed knowledge shard.
        Multiple nodes vote on validity.
        """
        shard = self.knowledge_pool.get(shard_id)
        if not shard:
            return {"error": "Shard not found"}

        # Collect votes from active, trusted nodes
        votes_for = 0
        votes_against = 0
        voters = 0

        for _node_id, node in self.nodes.items():
            if node.status != NodeStatus.ACTIVE:
                continue
            if node.trust_score < 0.3:
                continue

            # Weighted vote based on trust
            vote_weight = node.trust_score
            # Simulate: nodes with higher nafs_level more likely to verify
            if node.nafs_level >= 3:
                votes_for += vote_weight
            else:
                votes_against += vote_weight * 0.3
            voters += 1

        total_votes = votes_for + votes_against
        if total_votes > 0:
            consensus_score = votes_for / total_votes
        else:
            consensus_score = 0.5

        # Update shard confidence based on consensus
        if consensus_score > 0.7:
            shard.confidence = min(1.0, shard.confidence + 0.1)
            shard.verification_count += 1
            if shard.verification_count >= 3:
                shard.yaqin_level = "ayn"  # Witnessed by multiple nodes
            if shard.verification_count >= 10:
                shard.yaqin_level = "haqq"  # Proven through consensus

        return {
            "shard_id": shard_id,
            "consensus_score": round(consensus_score, 3),
            "voters": voters,
            "verified": consensus_score > 0.7,
            "new_yaqin": shard.yaqin_level,
        }

    # ─── Hisab: Periodic Accounting ───

    async def hisab_audit(self) -> dict:
        """
        Hisab (حساب) — Periodic trust accounting.
        Reviews all nodes, demotes inactive ones, prunes stale knowledge.
        """
        now = time.time()
        demoted = 0
        pruned_nodes = 0
        pruned_shards = 0

        # Check node health
        for node_id, node in list(self.nodes.items()):
            age = now - node.last_seen
            if age > 86400:  # 24 hours
                node.status = NodeStatus.OFFLINE
                node.trust_score = max(0.0, node.trust_score - 0.05)
                demoted += 1
            if age > 604800:  # 7 days inactive
                del self.nodes[node_id]
                pruned_nodes += 1

        # Prune low-confidence unverified shards
        for hash_key, shard in list(self.knowledge_pool.items()):
            age = now - shard.timestamp
            if age > 2592000 and shard.confidence < 0.3:  # 30 days + low conf
                del self.knowledge_pool[hash_key]
                pruned_shards += 1

        logger.info(
            f"[HISAB] Audit: {demoted} demoted, "
            f"{pruned_nodes} nodes pruned, {pruned_shards} shards pruned"
        )

        return {
            "demoted": demoted,
            "pruned_nodes": pruned_nodes,
            "pruned_shards": pruned_shards,
            "active_nodes": sum(1 for n in self.nodes.values() if n.status == NodeStatus.ACTIVE),
            "total_knowledge": len(self.knowledge_pool),
        }

    # ─── Network Status ───

    def get_status(self) -> dict:
        """Get full Ummah network status."""
        return {
            "instance_id": self.instance_id,
            "instance_name": self.instance_name,
            "nodes": {
                "total": len(self.nodes),
                "active": sum(1 for n in self.nodes.values() if n.status == NodeStatus.ACTIVE),
                "offline": sum(1 for n in self.nodes.values() if n.status == NodeStatus.OFFLINE),
            },
            "knowledge_pool": {
                "total_shards": len(self.knowledge_pool),
                "verified": sum(
                    1 for s in self.knowledge_pool.values() if s.verification_count > 0
                ),
                "by_yaqin": {
                    "ilm": sum(1 for s in self.knowledge_pool.values() if s.yaqin_level == "ilm"),
                    "ayn": sum(1 for s in self.knowledge_pool.values() if s.yaqin_level == "ayn"),
                    "haqq": sum(1 for s in self.knowledge_pool.values() if s.yaqin_level == "haqq"),
                },
            },
            "sync_history_count": len(self.sync_history),
        }

    def list_nodes(self) -> list[dict]:
        """List all known nodes."""
        return [node.to_dict() for node in self.nodes.values()]

    def search_knowledge(self, query: str, top_k: int = 10) -> list[dict]:
        """Search federated knowledge pool."""
        query_words = set(query.lower().split())
        results = []

        for shard in self.knowledge_pool.values():
            text = f"{shard.topic} {shard.summary} {shard.domain}".lower()
            score = sum(1 for w in query_words if w in text)
            if score > 0:
                results.append((score * shard.confidence, shard))

        results.sort(key=lambda x: -x[0])
        return [s.to_dict() for _, s in results[:top_k]]
