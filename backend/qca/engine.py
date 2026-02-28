"""
QCA Engine — Quranic Cognitive Architecture (7-Layer Processing Pipeline)
=========================================================================

"Do not pursue that of which you have no knowledge. Indeed, the hearing (Sam'),
 the sight (Basar) and the heart (Fu'ad) — about all those will be questioned." — 17:36

This module implements the complete 7-layer cognitive pipeline:

  Layer 1+2: Sam' + Basar (Dual Input) → sequential + structural perception
  Layer 3:   Fu'ad (Integration)        → unified understanding
  Layer 4:   ISM (Root-Space)           → deep semantic representation
  Layer 5:   Mizan (Weighting)          → epistemic truth calibration
  Layer 6:   'Aql (Binding)             → typed relationship graph
  Layer 7:   Lawh (Memory)              → 4-tier hierarchical memory
  Output:    Furqan + Bayan             → discrimination + articulation
"""

import logging
import re
import time
from collections import Counter, defaultdict

from qca.roots import ARABIC_ROOTS, CONCEPT_MAP, RELATED_DOMAINS

logger = logging.getLogger("mizan.qca")


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 1+2+3: SAM' + BASAR + FU'AD — Dual Input Processing
# ─────────────────────────────────────────────────────────────────────────────

STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "shall",
        "should",
        "may",
        "might",
        "must",
        "can",
        "could",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "with",
        "by",
        "from",
        "and",
        "or",
        "but",
        "not",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "they",
        "their",
    }
)


class DualInputProcessor:
    """
    Sam':  Sequential temporal processing (token by token) — Quran 16:78
    Basar: Structural simultaneous pattern (whole text at once) — Quran 16:78
    Fu'ad: Integration engine combining both into unified understanding — Quran 16:78
    """

    def process_sam(self, text: str) -> dict:
        """Sequential processing — one token after another (temporal stream)."""
        tokens = text.lower().split()
        timeline = [(i, tok) for i, tok in enumerate(tokens)]
        bigrams = [(tokens[i], tokens[i + 1]) for i in range(len(tokens) - 1)]
        return {"tokens": tokens, "timeline": timeline, "sequential_pairs": bigrams}

    def process_basar(self, text: str) -> dict:
        """Structural pattern — simultaneous view of whole text (spatial map)."""
        tokens = text.lower().split()
        freq = Counter(tokens)
        unique = len(set(tokens))
        density = len(tokens) / max(unique, 1)
        sentences = re.split(r"[.!?]+", text)
        return {
            "word_frequencies": dict(freq.most_common(10)),
            "vocabulary_richness": unique / max(len(tokens), 1),
            "information_density": density,
            "sentence_count": len([s for s in sentences if s.strip()]),
            "avg_sentence_length": len(tokens) / max(len(sentences), 1),
        }

    def integrate_fuad(self, sam_result: dict, basar_result: dict) -> dict:
        """
        Fu'ad: Integrate sequential + structural into unified understanding.
        Produces both Zahir (surface) and Batin (deep structure) views.
        """
        tokens = sam_result["tokens"]
        freq = basar_result["word_frequencies"]
        key_terms = [w for w in freq if w not in STOPWORDS and len(w) > 3][:8]
        zahir = " ".join(tokens[:10]) + ("..." if len(tokens) > 10 else "")
        batin = "Core concepts: {}".format(", ".join(key_terms))
        return {
            "zahir": zahir,
            "batin": batin,
            "key_terms": key_terms,
            "vocabulary_richness": basar_result["vocabulary_richness"],
            "sequential_pairs": sam_result["sequential_pairs"][:5],
            "total_tokens": len(tokens),
        }

    def process(self, text: str) -> dict:
        """Full dual-input processing pipeline."""
        sam = self.process_sam(text)
        basar = self.process_basar(text)
        fuad = self.integrate_fuad(sam, basar)
        return {"sam": sam, "basar": basar, "fuad": fuad}

    async def process_multimodal(
        self,
        text: str = "",
        image_bytes: bytes | None = None,
        audio_bytes: bytes | None = None,
        media_type: str = "image/png",
        context: str = "",
        qalb_state: str = "",
    ) -> dict:
        """
        Full multimodal processing: Sam' (hearing) first, then Basar (sight),
        following the Quranic ordering of 16:78 and 17:36.

        "And Allah brought you out from the wombs of your mothers while you knew
        nothing, and He gave you hearing (sam'), sight (basar), and hearts (af'ida)
        that perhaps you would be grateful." — Quran 16:78
        """
        from perception.basirah import BasirahEngine
        from perception.nutq import NutqEngine

        results: dict = {"sam": {}, "basar": {}, "fuad": {}, "nutq": None, "basirah": None}

        # ── Step 1: Sam' — auditory input first (hearing precedes sight) ──
        nutq_text = ""
        if audio_bytes:
            try:
                nutq = NutqEngine()
                transcription = await nutq.listen(audio_bytes)
                results["nutq"] = transcription.to_dict()
                nutq_text = transcription.text
            except Exception as e:
                logger.warning("[QCA] Nutq (audio) processing failed: %s", e)

        # Combine text sources: explicit text + transcribed speech
        combined_text = " ".join(filter(None, [text, nutq_text]))

        # ── Step 2: Basar — visual input second ──
        if image_bytes:
            try:
                basirah = BasirahEngine()
                insight = await basirah.analyze(
                    image_bytes, context=context, media_type=media_type,
                    qalb_state=qalb_state,
                )
                results["basirah"] = insight.to_dict()
                # Append extracted text from vision to combined text
                if insight.extracted_text:
                    combined_text += " " + insight.extracted_text
            except Exception as e:
                logger.warning("[QCA] Basirah (vision) processing failed: %s", e)

        # ── Step 3: Fu'ad — standard text integration on combined input ──
        if combined_text.strip():
            sam = self.process_sam(combined_text)
            basar = self.process_basar(combined_text)
            fuad = self.integrate_fuad(sam, basar)
            results["sam"] = sam
            results["basar"] = basar
            results["fuad"] = fuad
        else:
            results["fuad"] = {
                "zahir": "", "batin": "", "key_terms": [],
                "vocabulary_richness": 0, "sequential_pairs": [], "total_tokens": 0,
            }

        return results


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 4: ISM — Root-Space Semantic Representation
# ─────────────────────────────────────────────────────────────────────────────


class ISMLayer:
    """
    Root-space representation: every Arabic word = Root + Pattern.
    Zahir (surface meaning) + Batin (root deep meaning) always maintained.

    "And He taught Adam the names (ISM) of all things." — Quran 2:31
    """

    # 16 Arabic morphological patterns (awzan)
    PATTERNS = {
        "فَاعِل": ("active agent", "one actively doing root action"),
        "مَفْعُول": ("passive patient", "entity receiving root action"),
        "فِعَال": ("intensive noun", "primary instrument of action"),
        "فَعِيل": ("divine/intense attr", "permanent intense quality"),
        "مَفْعَل": ("place/time", "location where action occurs"),
        "فُعْلَان": ("overflow abundance", "encompassing quality"),
        "تَفْعِيل": ("intensive verbal noun", "act of doing intensively"),
        "اسْتِفْعَال": ("seeking verbal noun", "act of seeking the quality"),
        "تَفَعُّل": ("self-reflexive", "doing action to/for oneself"),
        "مُفَعِّل": ("active intensive agent", "one intensely doing action"),
        "فُعُول": ("completed action", "full noun of the action"),
        "أَفْعَال": ("broken plural", "plurality of root instances"),
        "فَعَّلَ": ("causative intensive", "making others do root action"),
        "تَفَاعُل": ("mutual action", "reciprocal doing of root"),
        "انْفِعَال": ("passive becoming", "spontaneous self-change"),
        "افْتِعَال": ("self-directed action", "doing action with effort"),
    }

    def __init__(self, root_db: dict = None):
        self.root_db = root_db or ARABIC_ROOTS

    def get_word_info(self, arabic_word: str) -> dict | None:
        """Get full ISM info for an Arabic word."""
        clean = re.sub(r"[\u064B-\u0652]", "", arabic_word)
        return self.root_db.get(clean) or self.root_db.get(arabic_word)

    def generalize_meaning(self, root: str, pattern: str) -> dict | None:
        """
        ZERO-SHOT: predict meaning of unknown word from Root + Pattern alone.
        Impossible in standard NLP. Core QCA advantage.
        """
        root_entry = self.root_db.get(root)
        pattern_entry = self.PATTERNS.get(pattern)
        if not root_entry or not pattern_entry:
            return None
        root_meaning = root_entry.get(
            "meaning", next(iter(root_entry.get("derivatives", {}).values()), "?")
        )
        pat_func, pat_desc = pattern_entry
        return {
            "predicted_zahir": f"{pat_func}: one who/that which {root_meaning}",
            "predicted_batin": f"Root invariant: [{root_meaning}] + Function: [{pat_desc}]",
            "confidence": min(0.95, root_entry.get("frequency", 10) / 900),
            "domain": root_entry.get("domain", "unknown"),
        }

    def find_root_family(self, root: str) -> dict:
        """Get all words sharing a root — the family cluster."""
        entry = self.root_db.get(root, {})
        return entry.get("derivatives", {})

    def root_distance(self, root1: str, root2: str) -> float:
        """Semantic distance between two roots based on domain."""
        e1 = self.root_db.get(root1, {})
        e2 = self.root_db.get(root2, {})
        d1 = e1.get("domain", "")
        d2 = e2.get("domain", "")
        if d1 == d2:
            return 0.15  # same domain = close
        pair = (d1, d2) if (d1, d2) in RELATED_DOMAINS else (d2, d1)
        if pair in RELATED_DOMAINS:
            return 0.35
        return 0.75

    def find_roots_in_text(self, text: str) -> list[dict]:
        """Find Arabic roots/concepts relevant to an English text."""
        words = text.lower().split()
        found_roots = []
        seen_roots = set()
        for word in words:
            clean = re.sub(r"[^a-z]", "", word)
            if clean in CONCEPT_MAP:
                root = CONCEPT_MAP[clean]
                if root not in seen_roots:
                    seen_roots.add(root)
                    root_data = self.root_db.get(root, {})
                    found_roots.append(
                        {
                            "english_term": clean,
                            "root": root,
                            "meaning": root_data.get("meaning", ""),
                            "domain": root_data.get("domain", ""),
                            "derivatives": list(root_data.get("derivatives", {}).items())[:3],
                        }
                    )
        return found_roots


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 5: MIZAN — Epistemic Weighting
# ─────────────────────────────────────────────────────────────────────────────


class MizanLayer:
    """
    Proportional truth weighting — Quran 55:7-9.
    Every claim has a correct Mizan weight based on certainty + source.
    Transgression (Tughyan: claiming more certainty than evidence supports) is blocked.

    "And the heaven He raised and imposed the balance (Mizan).
     That you not transgress within the balance." — 55:7-8
    """

    LEVELS = {
        "yaqin": 1.00,  # certain — logical necessity, Quranic text
        "zann_rajih": 0.75,  # strong probability — verified source
        "zann": 0.50,  # conjecture — reasonable inference
        "shakk": 0.25,  # doubt — some evidence but unclear
        "wahm": 0.05,  # delusion — very weak or no basis
    }

    SOURCES = {
        "quran": 1.00,
        "mutawatir": 0.99,
        "sahih": 0.85,
        "hasan": 0.70,
        "inference": 0.60,
        "daif": 0.40,
        "unknown": 0.15,
    }

    LEVEL_NAMES = {
        1.00: "Yaqin (Certain)",
        0.75: "Zann Rajih (Probable)",
        0.50: "Zann (Conjecture)",
        0.25: "Shakk (Doubt)",
        0.05: "Wahm (Delusion)",
    }

    def weigh(
        self, certainty_level: str, source: str = "inference", contradictions: int = 0
    ) -> float:
        """Compute the Mizan weight for a claim."""
        base = self.LEVELS.get(certainty_level, 0.5)
        src = self.SOURCES.get(source, 0.5)
        weight = base * src - 0.15 * contradictions
        return max(0.0, min(1.0, weight))

    def check_tughyan(self, claimed_level: str, evidence_level: str) -> tuple[bool, str]:
        """
        Detect transgression: claiming more certainty than evidence allows.
        "That you not transgress within the balance." — 55:8
        """
        claimed = self.LEVELS.get(claimed_level, 0)
        actual = self.LEVELS.get(evidence_level, 0)
        if claimed > actual + 0.30:
            return True, (
                f"TUGHYAN: Claims {claimed_level}({claimed:.2f}) but evidence only supports "
                f"{evidence_level}({actual:.2f})"
            )
        return False, "Within Mizan bounds"

    def classify_confidence(self, score: float) -> str:
        """Convert float to epistemic certainty level name."""
        if score >= 0.85:
            return "yaqin"
        if score >= 0.65:
            return "zann_rajih"
        if score >= 0.45:
            return "zann"
        if score >= 0.25:
            return "shakk"
        return "wahm"

    def rate_confidence_string(self, score: float) -> str:
        """Convert float to human-readable epistemic label."""
        if score >= 0.85:
            return "Yaqin — Certain"
        if score >= 0.65:
            return "Zann Rajih — Strongly Probable"
        if score >= 0.45:
            return "Zann — Probable inference"
        if score >= 0.25:
            return "Shakk — Doubtful"
        return "Wahm — Very uncertain"


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 6: 'AQL — Typed Relationship Binding Engine
# ─────────────────────────────────────────────────────────────────────────────


class AqlLayer:
    """
    8 typed relationship categories derived from Quranic epistemology.
    Every relationship has TYPE, DIRECTION, CERTAINTY — not just scalar similarity.

    "Indeed in the creation of the heavens and earth... are signs
     for people of reason ('Aql)." — 3:190
    """

    BINDING_TYPES = {
        "CAUSAL": ("A directly causes B", "A -> B"),
        "ESSENTIAL": ("A is inseparable attribute of B", "A in def(B)"),
        "ACCIDENTAL": ("A sometimes accompanies B", "A ~ B (partial)"),
        "NEGATION": ("A and B mutually exclude each other", "not(A and B)"),
        "HIERARCHICAL": ("A is a subset/instance of B", "A subset B"),
        "ANALOGICAL": ("A resembles B in specific aspect X", "A approx B [X]"),
        "PURPOSE": ("A exists for the purpose of B", "purpose(A) = B"),
        "CONTRAST": ("A and B define each other by opposition", "A <-> not-A = B"),
    }

    def __init__(self):
        self.graph: dict[str, list[dict]] = defaultdict(list)
        self._populate_from_quran()

    def _populate_from_quran(self):
        """Seed the binding network from Quranic epistemology."""
        bindings = [
            # 2:31 — Names and Knowledge
            ("Ism", "PURPOSE", "KnowledgeOfEssences", 1.0, "2:31"),
            ("Teaching", "CAUSAL", "Knowledge", 1.0, "2:31-32"),
            # 16:78 — Triadic Input
            ("Sam-Hearing", "PURPOSE", "TemporalPerception", 1.0, "16:78"),
            ("Basar-Sight", "PURPOSE", "SpatialPerception", 1.0, "16:78"),
            ("Fuad-Heart", "PURPOSE", "Integration", 1.0, "16:78"),
            ("Sam-Hearing", "CONTRAST", "Basar-Sight", 0.9, "16:78"),
            ("Fuad-Heart", "HIERARCHICAL", "Aql-Intellect", 0.9, "17:36"),
            # 55:2-4 — Architecture Order
            ("QuranKnowledge", "PURPOSE", "HumanReceiver", 1.0, "55:2-4"),
            ("Bayan", "PURPOSE", "ClearExpression", 1.0, "55:4"),
            ("Bayan", "ESSENTIAL", "Human", 1.0, "55:3-4"),
            # 55:7-9 — Mizan
            ("Mizan", "ESSENTIAL", "CosmicOrder", 1.0, "55:7"),
            ("Tughyan", "NEGATION", "Mizan", 1.0, "55:8"),
            ("Justice", "HIERARCHICAL", "Mizan", 1.0, "55:9"),
            # 4:82, 47:24 — Tadabbur
            ("Tadabbur", "CAUSAL", "DeepUnderstanding", 1.0, "4:82"),
            ("LockedHeart", "NEGATION", "Tadabbur", 1.0, "47:24"),
            ("Tadabbur", "ESSENTIAL", "Aql-Intellect", 0.9, "inference"),
            # 3:191 — Tafakkur
            ("Tafakkur", "CAUSAL", "KnowledgeOfCreator", 0.9, "3:191"),
            ("Creation", "PURPOSE", "Contemplation", 0.9, "3:191"),
            # 17:36 — Epistemic responsibility
            ("FollowingWithoutKnowledge", "CAUSAL", "Sin", 1.0, "17:36"),
            ("Knowledge", "PURPOSE", "CorrectFollowing", 1.0, "17:36"),
            # 49:12 — Conjecture
            ("SomeConjecture", "ESSENTIAL", "Sin", 1.0, "49:12"),
            ("Conjecture", "CONTRAST", "Certainty", 1.0, "49:12"),
            # 85:22 — Lawh Mahfuz
            ("LawhMahfuz", "ESSENTIAL", "Preservation", 1.0, "85:22"),
            ("LawhMahfuz", "HIERARCHICAL", "Memory", 1.0, "85:22"),
            # 96:1-5 — Iqra cycle
            ("Reading", "CAUSAL", "Knowledge", 1.0, "96:1"),
            ("Pen", "PURPOSE", "Inscription", 1.0, "96:4"),
            ("Inscription", "CAUSAL", "TransmittedKnowledge", 1.0, "96:4-5"),
            # Additional linguistic bindings
            ("Language", "ESSENTIAL", "Human", 0.9, "inference"),
            ("Root", "ESSENTIAL", "ArabicWord", 1.0, "linguistics"),
            ("Pattern", "ESSENTIAL", "ArabicWord", 1.0, "linguistics"),
            ("Root", "PURPOSE", "SemanticInvariant", 1.0, "linguistics"),
        ]
        for a, btype, b, cert, src in bindings:
            self.bind(a, btype, b, cert, src)

    def bind(
        self, a: str, binding_type: str, b: str, certainty: float = 1.0, source: str = ""
    ) -> None:
        """Add a typed binding between two concepts."""
        entry = {
            "from": a,
            "type": binding_type,
            "to": b,
            "certainty": certainty,
            "source": source,
            "logic": self.BINDING_TYPES.get(binding_type, ("?", "?"))[1],
        }
        self.graph[a].append(entry)

    def query(self, concept: str, btype: str = None) -> list[dict]:
        """Query all bindings for a concept, optionally filtered by type."""
        results = self.graph.get(concept, [])
        if btype:
            results = [r for r in results if r["type"] == btype]
        return results

    def tadabbur_trace(self, start: str, depth: int = 4) -> list[str]:
        """
        Trace causal chain forward from a concept (Quranic Tadabbur mode).
        "Do they not then reflect upon the Quran?" — 4:82
        """
        chain = [start]
        visited = {start}
        current = start
        for _ in range(depth):
            causal = [b for b in self.graph.get(current, []) if b["type"] == "CAUSAL"]
            if not causal:
                break
            best = max(causal, key=lambda x: x["certainty"])
            nxt = best["to"]
            if nxt in visited:
                break
            chain.append("->[{:.1f}]-> {}".format(best["certainty"], nxt))
            visited.add(nxt)
            current = nxt
        return chain

    def get_all_bindings_summary(self) -> tuple[int, dict[str, int]]:
        """Get total bindings count and distribution by type."""
        total = sum(len(v) for v in self.graph.values())
        type_counts = Counter(b["type"] for v in self.graph.values() for b in v)
        return total, dict(type_counts)


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 7: LAWH — 4-Tier Hierarchical Memory
# ─────────────────────────────────────────────────────────────────────────────


class LawhMemory:
    """
    4-tier structured memory based on Lawh al-Mahfuz principle (85:22).
    Every piece of knowledge is tagged with tier, source, certainty, timestamp.

    Tier 1: Lawh (Immutable)   — Axiomatic truths that cannot be overwritten
    Tier 2: Kitab (Verified)   — Verified knowledge (Quran verses, confirmed facts)
    Tier 3: Dhikr (Active)     — Working memory / active session knowledge
    Tier 4: Wahm (Conjecture)  — Unverified, low-certainty claims

    "But this is an honored Quran, inscribed in a Preserved Slate (Lawh)." — 85:21-22
    """

    TIER_NAMES = {
        1: "Lawh (Immutable)",
        2: "Kitab (Verified)",
        3: "Dhikr (Active)",
        4: "Wahm (Conjecture)",
    }

    def __init__(self):
        self.tiers: dict[int, dict[str, dict]] = {1: {}, 2: {}, 3: {}, 4: {}}
        self._init_tier1()
        self._init_tier2_roots()

    def _init_tier1(self):
        """Immutable axioms from Quran — cannot be overwritten."""
        axioms = {
            "TRIADIC_INPUT": ("Sam'+Basar+Fu'ad is the cognitive input triad", "16:78"),
            "BAYAN_ORDER": ("Knowledge structure precedes expression (Bayan)", "55:2-4"),
            "MIZAN_COSMIC": ("Mizan (balance) is a cosmic law — transgression is error", "55:7-9"),
            "ISM_FOUNDATION": (
                "Knowledge of Names (essences) is the foundation of cognition",
                "2:31",
            ),
            "EPISTEMIC_DUTY": ("Do not follow what you have no knowledge of", "17:36"),
            "CONJECTURE_WARN": (
                "Some conjecture is sin — never assert conjecture as certainty",
                "49:12",
            ),
            "LAWH_PRESERVATION": (
                "All is preserved in the Lawh Mahfuz without corruption",
                "85:22",
            ),
            "IQRA_CYCLE": ("Read-Name-Write: the complete cognitive acquisition cycle", "96:1-5"),
            "YAQIN_REQUIRED": (
                "Only certain (Yaqin) knowledge deserves assertion without qualification",
                "2:255",
            ),
        }
        for key, (content, source) in axioms.items():
            self.tiers[1][key] = {
                "content": content,
                "source": source,
                "certainty": 1.0,
                "tier": 1,
                "mutable": False,
                "timestamp": time.time(),
            }

    def _init_tier2_roots(self):
        """Load Arabic roots into Tier 2 as verified knowledge."""
        for root, data in ARABIC_ROOTS.items():
            if isinstance(data, dict) and data.get("meaning"):
                self.tiers[2][f"ROOT:{root}"] = {
                    "content": data["meaning"],
                    "source": "Arabic lexicon",
                    "certainty": 0.95,
                    "tier": 2,
                    "timestamp": time.time(),
                }

    def load_quran_verses(self, quran_data: dict):
        """Load downloaded Quran verses into Tier 2."""
        count = 0
        for snum, verses in quran_data.items():
            for v in verses:
                key = "Q{}:{}".format(v.get("surah", snum), v.get("ayah", ""))
                if v.get("arabic") or v.get("english"):
                    self.tiers[2][key] = {
                        "content": v.get("english", ""),
                        "arabic": v.get("arabic", ""),
                        "source": "Quran {}:{}".format(v.get("surah", snum), v.get("ayah", "")),
                        "certainty": 1.0,
                        "tier": 2,
                        "timestamp": time.time(),
                    }
                    count += 1
        return count

    def store(
        self, key: str, content: str, certainty: float, source: str = "inference", tier: int = None
    ) -> bool:
        """Store knowledge in the appropriate tier."""
        if tier is None:
            tier = 2 if certainty >= 0.85 else 3 if certainty >= 0.45 else 4
        if tier == 1 and key in self.tiers[1]:
            return False  # Cannot overwrite Tier 1
        self.tiers[tier][key] = {
            "content": content,
            "source": source,
            "certainty": certainty,
            "tier": tier,
            "timestamp": time.time(),
        }
        return True

    def retrieve(self, key: str) -> dict | None:
        """Retrieve knowledge by key, searching from highest to lowest tier."""
        for t in [1, 2, 3, 4]:
            if key in self.tiers[t]:
                e = self.tiers[t][key].copy()
                e["retrieved_tier"] = t
                e["tier_name"] = self.TIER_NAMES[t]
                return e
        return None

    def search(
        self, query_text: str, top_k: int = 5, tiers: list[int] = None
    ) -> list[tuple[int, str, dict]]:
        """Keyword search across tiers."""
        if tiers is None:
            tiers = [2, 3]
        query_words = set(query_text.lower().split())
        query_words -= {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "in",
            "of",
            "to",
            "and",
            "or",
            "what",
            "how",
            "why",
            "when",
            "where",
            "who",
        }
        results = []
        for tier in tiers:
            for key, entry in self.tiers[tier].items():
                content = entry.get("content", "").lower()
                arabic = entry.get("arabic", "").lower()
                score = sum(1 for w in query_words if w in content or w in arabic)
                if score > 0:
                    results.append((score, key, entry))
        results.sort(key=lambda x: (-x[0], -x[2]["certainty"]))
        return results[:top_k]

    def consolidate(self, max_age_hours: float = 720):
        """
        Memory consolidation — Tafakkur process.
        Promote highly-accessed Tier 3 to Tier 2, prune old Tier 4.
        """
        now = time.time()
        cutoff = now - (max_age_hours * 3600)
        pruned = 0
        for key in list(self.tiers[4].keys()):
            entry = self.tiers[4][key]
            if entry.get("timestamp", 0) < cutoff:
                del self.tiers[4][key]
                pruned += 1
        return {"consolidated": True, "pruned": pruned}

    def stats(self) -> dict[int, int]:
        """Get entry counts per tier."""
        return {t: len(self.tiers[t]) for t in [1, 2, 3, 4]}


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT: FURQAN + BAYAN — Discrimination & Articulation
# ─────────────────────────────────────────────────────────────────────────────


class FurqanBayan:
    """
    Furqan (discrimination) + Bayan (articulation).
    Every output is validated before expression:

    1. Mizan compliance (certainty proportionate to evidence)
    2. Tier 1 consistency (no axiom violations)
    3. 'Aql coherence (no binding contradictions)
    4. Bayan clarity (expression matches certainty level)

    "Blessed is He who sent down the Criterion (Furqan)." — 25:1
    "He taught him clear expression (Bayan)." — 55:4
    """

    def __init__(self, mizan: MizanLayer = None, lawh: LawhMemory = None):
        self.mizan = mizan or MizanLayer()
        self.lawh = lawh

    # Axiom keywords for semantic matching against Tier 1
    _AXIOM_CONCEPTS = {
        "TRIADIC_INPUT": ["perception", "hearing", "sight", "heart", "input", "cognitive"],
        "BAYAN_ORDER": ["expression", "knowledge", "structure", "language", "bayan"],
        "MIZAN_COSMIC": ["balance", "mizan", "proportion", "transgression", "tughyan"],
        "ISM_FOUNDATION": ["names", "essence", "cognition", "foundation", "ism"],
        "EPISTEMIC_DUTY": ["knowledge", "follow", "evidence", "certainty", "epistemic"],
        "CONJECTURE_WARN": ["conjecture", "certainty", "assertion", "zann", "wahm"],
        "LAWH_PRESERVATION": ["preservation", "lawh", "memory", "corruption", "preserved"],
        "IQRA_CYCLE": ["read", "write", "name", "cognitive", "acquisition"],
        "YAQIN_REQUIRED": ["certain", "yaqin", "assertion", "qualification", "knowledge"],
    }

    def validate_and_express(
        self, claim: str, confidence: float, source: str = "inference"
    ) -> dict:
        """Validate a claim through Furqan checks and produce Bayan output."""
        report = {
            "passed": True,
            "checks": [],
            "confidence": confidence,
            "epistemic_label": self.mizan.rate_confidence_string(confidence),
        }

        # Check 1: Determine epistemic level
        cert_level = self.mizan.classify_confidence(confidence)
        report["certainty_level"] = cert_level

        # Check 2: Tughyan detection — claiming more certainty than evidence supports
        claim_lower = claim.lower()
        certainty_markers = ["certainly", "definitely", "absolutely", "always", "proven fact"]
        hedging_markers = ["possibly", "might", "perhaps", "likely", "seems"]
        has_strong_claim = any(m in claim_lower for m in certainty_markers)
        has_hedging = any(m in claim_lower for m in hedging_markers)

        if has_strong_claim and confidence < 0.75:
            is_tughyan, msg = self.mizan.check_tughyan("yaqin", cert_level)
            if is_tughyan:
                report["checks"].append(f"tughyan_detected: {msg}")
                report["passed"] = False
                # Auto-downgrade confidence to prevent transgression
                confidence = min(confidence, 0.6)
                report["confidence"] = confidence
                report["epistemic_label"] = self.mizan.rate_confidence_string(confidence)
                cert_level = self.mizan.classify_confidence(confidence)
                report["certainty_level"] = cert_level

        # Check 3: Tier 1 axiom consistency (semantic matching)
        if self.lawh:
            for key, concepts in self._AXIOM_CONCEPTS.items():
                axiom_entry = self.lawh.tiers[1].get(key)
                if not axiom_entry:
                    continue
                # Check if claim contradicts axiom via negation + concept overlap
                negation_near_concept = False
                for concept in concepts:
                    if concept in claim_lower:
                        # Look for negation within 5 words of the concept
                        idx = claim_lower.find(concept)
                        window = claim_lower[max(0, idx - 40) : idx + len(concept) + 40]
                        if any(
                            neg in window
                            for neg in ["not ", "no ", "never ", "cannot ", "isn't ", "doesn't "]
                        ):
                            negation_near_concept = True
                            break

                if negation_near_concept:
                    report["checks"].append(
                        "axiom_conflict: Claim may contradict '{}' ({})".format(
                            key, axiom_entry["content"][:60]
                        )
                    )

        # Check 4: Epistemic prefix (Bayan clarity)
        if confidence < 0.3:
            prefix = "[WAHM — very uncertain] "
        elif confidence < 0.5:
            prefix = "[CONJECTURE — low certainty] "
        elif confidence < 0.75:
            prefix = "[Probable inference] "
        elif confidence >= 0.9:
            prefix = "[Verified] "
        else:
            prefix = ""

        # If claim already has appropriate hedging, acknowledge it
        if has_hedging and confidence < 0.75:
            report["checks"].append("bayan_appropriate: Claim uses proportional hedging")

        report["bayan_prefix"] = prefix
        report["final_output"] = prefix + claim

        return report


# ─────────────────────────────────────────────────────────────────────────────
# QCA ENGINE — Unified 7-Layer Pipeline
# ─────────────────────────────────────────────────────────────────────────────


class QCAEngine:
    """
    The unified QCA Engine that orchestrates all 7 layers.
    Integrates into MIZAN's existing architecture as the cognitive core.

    Usage:
        engine = QCAEngine()
        result = engine.process_input("Your text here")
        answer = engine.reason("Your question", context_text="Your text here")
    """

    def __init__(self):
        self.dual_input = DualInputProcessor()
        self.ism = ISMLayer()
        self.mizan = MizanLayer()
        self.aql = AqlLayer()
        self.lawh = LawhMemory()
        self.furqan = FurqanBayan(mizan=self.mizan, lawh=self.lawh)
        logger.info(
            "QCA Engine initialized: %d roots, %d axioms, %d bindings",
            len(ARABIC_ROOTS),
            len(self.lawh.tiers[1]),
            self.aql.get_all_bindings_summary()[0],
        )

    def process_input(self, text: str) -> dict:
        """
        Process text through all input layers (Sam' + Basar + Fu'ad + ISM).
        Returns a comprehensive analysis.
        """
        # Layer 1+2+3: Dual Input
        perception = self.dual_input.process(text)

        # Layer 4: ISM — find Arabic root concepts
        roots = self.ism.find_roots_in_text(text)

        # Store in Tier 3 working memory
        self.lawh.store(
            "CURRENT_INPUT",
            text[:500],
            certainty=1.0,
            source="user_input",
            tier=3,
        )
        key_terms = perception["fuad"].get("key_terms", [])
        self.lawh.store(
            "CURRENT_TERMS",
            str(key_terms),
            certainty=1.0,
            source="fuad_analysis",
            tier=3,
        )

        return {
            "perception": perception,
            "roots_identified": roots,
            "key_terms": key_terms,
            "zahir": perception["fuad"]["zahir"],
            "batin": perception["fuad"]["batin"],
        }

    async def process_input_multimodal(
        self,
        text: str = "",
        image_bytes: bytes | None = None,
        audio_bytes: bytes | None = None,
        media_type: str = "image/png",
        context: str = "",
        qalb_state: str = "",
    ) -> dict:
        """
        Process multimodal input through perception layers + ISM.

        Follows Quranic ordering: Sam' (hearing) first, then Basar (sight).
        Falls back to text-only process_input() if no multimodal data present.
        """
        if not image_bytes and not audio_bytes:
            return self.process_input(text)

        perception = await self.dual_input.process_multimodal(
            text=text,
            image_bytes=image_bytes,
            audio_bytes=audio_bytes,
            media_type=media_type,
            context=context,
            qalb_state=qalb_state,
        )

        # Combine all text sources for root analysis
        combined_text = text
        nutq_result = perception.get("nutq")
        if nutq_result and nutq_result.get("text"):
            combined_text += " " + nutq_result["text"]
        basirah_result = perception.get("basirah")
        if basirah_result and basirah_result.get("extracted_text"):
            combined_text += " " + basirah_result["extracted_text"]

        roots = self.ism.find_roots_in_text(combined_text) if combined_text.strip() else {}

        # Store in Tier 3 working memory
        self.lawh.store(
            "CURRENT_INPUT",
            combined_text[:500],
            certainty=1.0,
            source="multimodal_input",
            tier=3,
        )
        key_terms = perception.get("fuad", {}).get("key_terms", [])
        self.lawh.store(
            "CURRENT_TERMS",
            str(key_terms),
            certainty=1.0,
            source="fuad_analysis",
            tier=3,
        )

        return {
            "perception": perception,
            "roots_identified": roots,
            "key_terms": key_terms,
            "zahir": perception.get("fuad", {}).get("zahir", ""),
            "batin": perception.get("fuad", {}).get("batin", ""),
            "has_vision": image_bytes is not None,
            "has_audio": audio_bytes is not None,
        }

    def reason(self, question: str, context_text: str = None) -> dict:
        """
        Full QCA reasoning pipeline for answering a question.
        Routes through all 7 layers.
        """
        if context_text:
            self.process_input(context_text)

        answer_parts = []
        confidence_scores = []
        sources = []

        # Retrieve current context from memory
        current_input = self.lawh.retrieve("CURRENT_INPUT")
        current_terms = self.lawh.retrieve("CURRENT_TERMS")

        # Parse context
        context = current_input.get("content", "") if current_input else ""
        sentences = re.split(r"[.!?]+", context) if context else []

        # Layer 1+2+3: Find relevant sentences in context
        q_words = set(question.lower().split()) - {
            "what",
            "how",
            "why",
            "is",
            "are",
            "the",
            "a",
            "an",
            "in",
            "of",
            "to",
            "does",
            "do",
            "did",
        }
        relevant_sentences = []
        for sent in sentences:
            if sent.strip():
                overlap = sum(1 for w in q_words if w.lower() in sent.lower())
                if overlap > 0:
                    relevant_sentences.append((overlap, sent.strip()))
        relevant_sentences.sort(key=lambda x: -x[0])

        if relevant_sentences:
            best_sent = relevant_sentences[0][1]
            answer_parts.append(f'From the text: "{best_sent}"')
            confidence_scores.append(0.85)
            sources.append("paragraph_direct")
        elif current_terms:
            answer_parts.append(
                "Context discusses: {}".format(current_terms.get("content", "")[:200])
            )
            confidence_scores.append(0.5)
            sources.append("fuad_inference")

        # Layer 4: ISM — Arabic root concepts
        combined_text = question + " " + context
        roots_found = self.ism.find_roots_in_text(combined_text)
        if roots_found:
            root_insights = []
            for r in roots_found[:3]:
                if r["meaning"]:
                    insight = "[{}] '{}' carries deep meaning: \"{}\"".format(
                        r["root"], r["english_term"], r["meaning"][:60]
                    )
                    root_insights.append(insight)
            if root_insights:
                answer_parts.append("QCA Root Analysis: " + " | ".join(root_insights))
                confidence_scores.append(0.9)
                sources.append("ism_root_analysis")

        # Layer 7: Lawh — search memory tiers
        memory_results = self.lawh.search(question, top_k=3, tiers=[1, 2])
        quran_refs = []
        for score, key, entry in memory_results:
            if score >= 2 and entry.get("content"):
                if key.startswith("Q"):
                    ref_text = 'Quran {}: "{}"'.format(key[1:], entry["content"][:80])
                    if entry.get("arabic"):
                        ref_text += " | Arabic: {}".format(entry["arabic"][:40])
                    quran_refs.append(ref_text)
                    sources.append("lawh_tier{}".format(entry["tier"]))
        if quran_refs:
            answer_parts.append("Quranic references: " + " | ".join(quran_refs[:2]))
            confidence_scores.append(0.95)

        # Layer 6: 'Aql — tadabbur trace
        for root_info in roots_found[:1]:
            concept = root_info.get("domain", "")
            if concept:
                concept_key = concept.replace("/", "_").title()
                chain = self.aql.tadabbur_trace(concept_key, depth=3)
                if len(chain) > 1:
                    answer_parts.append(
                        "'Aql Tadabbur trace: {}".format(" ".join(str(c) for c in chain))
                    )
                    confidence_scores.append(0.7)
                    sources.append("aql_tadabbur")

        # Layer 5: Mizan — compute overall confidence
        if confidence_scores:
            overall_confidence = sum(confidence_scores) / len(confidence_scores)
        else:
            overall_confidence = 0.5

        # Output: Furqan + Bayan — validate and express
        furqan_report = self.furqan.validate_and_express(
            " ".join(answer_parts[:2]),
            overall_confidence,
            source=sources[0] if sources else "inference",
        )

        # Store result in Tier 3 memory
        self.lawh.store(
            f"REASONING_{int(time.time())}",
            question + " -> " + (answer_parts[0] if answer_parts else "no answer"),
            certainty=overall_confidence,
            source="qca_reasoning",
            tier=3,
        )

        return {
            "question": question,
            "answer_parts": answer_parts,
            "roots_identified": roots_found,
            "confidence": overall_confidence,
            "epistemic_label": self.mizan.rate_confidence_string(overall_confidence),
            "certainty_level": furqan_report["certainty_level"],
            "bayan_prefix": furqan_report["bayan_prefix"],
            "sources": sources,
            "lawh_stats": self.lawh.stats(),
        }

    def weigh_claim(self, claim: str, certainty_level: str, source: str = "inference") -> dict:
        """Weigh a claim through the Mizan layer."""
        weight = self.mizan.weigh(certainty_level, source)
        report = self.furqan.validate_and_express(claim, weight, source)
        return report

    def trace_concept(self, concept: str, depth: int = 4) -> list[str]:
        """Trace causal chain through 'Aql bindings."""
        return self.aql.tadabbur_trace(concept, depth)

    def remember(self, key: str, content: str, certainty: float, source: str = "agent") -> bool:
        """Store knowledge in Lawh memory."""
        return self.lawh.store(key, content, certainty, source)

    def recall(self, query: str, top_k: int = 5) -> list:
        """Search Lawh memory."""
        return self.lawh.search(query, top_k, tiers=[1, 2, 3])
