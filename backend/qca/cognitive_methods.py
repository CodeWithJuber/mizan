"""
Quranic Cognitive Methods (مناهج القرآنية المعرفية)
=====================================================

Five classical Islamic reasoning methods mapped to AI cognitive strategies:

1. Tafakkur (تفكر) — Deep reflective thinking / analytical reasoning
2. Tadabbur (تدبر) — Contemplation of meaning / contextual understanding
3. Istidlal (استدلال) — Logical deduction / formal reasoning
4. Qiyas (قياس) — Analogical reasoning / pattern matching
5. Ijma (إجماع) — Consensus building / ensemble reasoning

Each method corresponds to a different problem-solving strategy.
The QCA engine routes queries to the most appropriate method.
"""

import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("mizan.cognitive_methods")


class CognitiveMethod(Enum):
    """The five Quranic cognitive methods."""
    TAFAKKUR = "tafakkur"      # Deep analytical thinking
    TADABBUR = "tadabbur"      # Contextual contemplation
    ISTIDLAL = "istidlal"      # Logical deduction
    QIYAS = "qiyas"            # Analogical reasoning
    IJMA = "ijma"              # Consensus / ensemble


@dataclass
class CognitiveResult:
    """Result from applying a cognitive method."""
    method: CognitiveMethod
    conclusion: str
    confidence: float          # 0.0 - 1.0
    reasoning_chain: List[str] = field(default_factory=list)
    processing_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "method": self.method.value,
            "conclusion": self.conclusion,
            "confidence": round(self.confidence, 3),
            "reasoning_steps": len(self.reasoning_chain),
            "processing_time_ms": round(self.processing_time_ms, 1),
        }


class TafakkurEngine:
    """
    Tafakkur (تفكر) — Deep Reflective Thinking
    "Indeed, in the creation of the heavens and the earth...
     are signs for those who think (yatafakkarun)." — Quran 3:190

    Breaks complex problems into components, analyzes each deeply,
    then synthesizes a comprehensive understanding.
    """

    def process(self, query: str, context: Optional[Dict] = None) -> CognitiveResult:
        start = time.time()
        context = context or {}

        # Step 1: Decompose the query
        components = self._decompose(query)

        # Step 2: Analyze each component
        analyses = [self._analyze_component(c, context) for c in components]

        # Step 3: Synthesize
        conclusion = self._synthesize(analyses)

        chain = [f"Decomposed into {len(components)} components"]
        chain.extend(f"Analyzed: {c}" for c in components)
        chain.append("Synthesized comprehensive understanding")

        elapsed = (time.time() - start) * 1000
        return CognitiveResult(
            method=CognitiveMethod.TAFAKKUR,
            conclusion=conclusion,
            confidence=min(0.95, 0.6 + 0.1 * len(components)),
            reasoning_chain=chain,
            processing_time_ms=elapsed,
        )

    def _decompose(self, query: str) -> List[str]:
        """Break query into logical components."""
        # Split on sentence boundaries and conjunctions
        parts = []
        for sep in ["?", ".", " and ", " or ", " but "]:
            if sep in query:
                parts.extend(p.strip() for p in query.split(sep) if p.strip())
                return parts[:5]  # Cap at 5 components
        return [query]

    def _analyze_component(self, component: str, context: Dict) -> str:
        """Analyze a single component through keyword extraction and structure detection."""
        words = component.lower().split()
        # Identify question type
        q_type = "statement"
        for w in words[:3]:
            if w in ("what", "how", "why", "when", "where", "who", "which"):
                q_type = w
                break

        # Extract key nouns (non-stopword, longer words)
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "to", "of",
                     "in", "on", "at", "for", "with", "and", "or", "but", "not", "it"}
        key_terms = [w for w in words if w not in stopwords and len(w) > 3][:5]

        # Check context for relevant facts
        facts = context.get("facts", [])
        relevant_facts = [f for f in facts if any(t in f.lower() for t in key_terms)]

        analysis = f"[{q_type}] Key concepts: {', '.join(key_terms) or 'general'}"
        if relevant_facts:
            analysis += f" | Relevant context: {relevant_facts[0][:80]}"
        return analysis

    def _synthesize(self, analyses: List[str]) -> str:
        """Synthesize multiple component analyses into a unified understanding."""
        if not analyses:
            return "No components to synthesize"

        # Collect all key concepts across analyses
        all_concepts = []
        for analysis in analyses:
            if "Key concepts:" in analysis:
                concepts_part = analysis.split("Key concepts:")[1].split("|")[0].strip()
                all_concepts.extend(c.strip() for c in concepts_part.split(",") if c.strip() and c.strip() != "general")

        # Deduplicate while preserving order
        seen = set()
        unique_concepts = []
        for c in all_concepts:
            if c not in seen:
                seen.add(c)
                unique_concepts.append(c)

        if unique_concepts:
            return f"Integrated understanding spanning {len(analyses)} aspects: {', '.join(unique_concepts[:8])}"
        return f"Synthesized {len(analyses)} components into unified analysis"


class TadabburEngine:
    """
    Tadabbur (تدبر) — Contextual Contemplation
    "Do they not contemplate (yatadabbarun) the Quran?" — Quran 4:82

    Focuses on understanding the deeper meaning and context behind queries.
    Considers historical context, user intent, and broader implications.
    """

    def process(self, query: str, context: Optional[Dict] = None) -> CognitiveResult:
        start = time.time()
        context = context or {}

        # Step 1: Surface meaning
        surface = self._extract_surface(query)

        # Step 2: Deeper meaning
        deeper = self._extract_deeper(query, context)

        # Step 3: Broader implications
        implications = self._derive_implications(query, context)

        chain = [
            f"Surface meaning: {surface}",
            f"Deeper intent: {deeper}",
            f"Implications: {implications}",
        ]

        elapsed = (time.time() - start) * 1000
        return CognitiveResult(
            method=CognitiveMethod.TADABBUR,
            conclusion=f"Contemplated meaning: {deeper}",
            confidence=0.75,
            reasoning_chain=chain,
            processing_time_ms=elapsed,
        )

    def _extract_surface(self, query: str) -> str:
        """Extract the literal, surface-level meaning of the query."""
        # Identify the main action/request
        words = query.lower().split()
        if not words:
            return query[:100]

        # Detect query intent from first meaningful word
        intent_words = {"what": "definition", "how": "method", "why": "causation",
                       "when": "timing", "where": "location", "who": "agent",
                       "can": "capability", "should": "recommendation",
                       "is": "verification", "does": "confirmation"}
        intent = "request"
        for w in words[:3]:
            if w in intent_words:
                intent = intent_words[w]
                break

        return f"Surface intent ({intent}): {query[:100]}"

    def _extract_deeper(self, query: str, context: Dict) -> str:
        """Extract the deeper contextual meaning considering conversation history."""
        user_history = context.get("history", [])
        facts = context.get("facts", [])

        parts = []
        if user_history:
            # Detect conversation trajectory
            recent_topics = []
            for h in user_history[-3:]:
                content = h.get("content", "")[:100].lower()
                key_words = [w for w in content.split() if len(w) > 4][:3]
                recent_topics.extend(key_words)
            if recent_topics:
                parts.append(f"Conversation trajectory: {', '.join(set(recent_topics)[:5])}")

        if facts:
            parts.append(f"Known facts: {'; '.join(f[:60] for f in facts[:3])}")

        # Detect implicit needs from query structure
        q_lower = query.lower()
        if any(w in q_lower for w in ["help", "stuck", "can't", "unable", "failing"]):
            parts.append("Implicit need: troubleshooting/unblocking")
        elif any(w in q_lower for w in ["best", "recommend", "should", "optimal"]):
            parts.append("Implicit need: guidance/recommendation")
        elif any(w in q_lower for w in ["understand", "explain", "clarify"]):
            parts.append("Implicit need: deeper comprehension")

        return " | ".join(parts) if parts else f"Direct query without additional context"

    def _derive_implications(self, query: str, context: Dict) -> str:
        """Derive broader implications and follow-up considerations."""
        implications = []
        q_lower = query.lower()

        # Technical implications
        if any(w in q_lower for w in ["change", "modify", "update", "refactor", "add"]):
            implications.append("May require testing after changes")
        if any(w in q_lower for w in ["delete", "remove", "drop"]):
            implications.append("Destructive action — verify intent and backup state")
        if any(w in q_lower for w in ["deploy", "release", "publish"]):
            implications.append("Affects production — requires careful validation")
        if any(w in q_lower for w in ["security", "auth", "password", "token"]):
            implications.append("Security-sensitive — handle with extra care")

        # Knowledge implications
        if any(w in q_lower for w in ["learn", "understand", "study"]):
            implications.append("Knowledge-building — consider providing references")

        return "; ".join(implications) if implications else "Standard implications — proceed normally"


class IstidlalEngine:
    """
    Istidlal (استدلال) — Logical Deduction
    "Say, 'Produce your proof (burhanakum)'" — Quran 2:111

    Applies formal logical reasoning: premises → deduction → conclusion.
    """

    def process(self, query: str, context: Optional[Dict] = None) -> CognitiveResult:
        start = time.time()
        context = context or {}

        # Step 1: Extract premises
        premises = self._extract_premises(query, context)

        # Step 2: Apply deduction rules
        deductions = self._deduce(premises)

        # Step 3: Reach conclusion
        conclusion = self._conclude(deductions)

        chain = [f"Premise: {p}" for p in premises]
        chain.extend(f"Deduction: {d}" for d in deductions)
        chain.append(f"Conclusion: {conclusion}")

        elapsed = (time.time() - start) * 1000
        return CognitiveResult(
            method=CognitiveMethod.ISTIDLAL,
            conclusion=conclusion,
            confidence=min(0.9, 0.5 + 0.15 * len(premises)),
            reasoning_chain=chain,
            processing_time_ms=elapsed,
        )

    def _extract_premises(self, query: str, context: Dict) -> List[str]:
        facts = context.get("facts", [])
        premises = list(facts[:5])
        premises.append(f"Query: {query[:80]}")
        return premises

    def _deduce(self, premises: List[str]) -> List[str]:
        """Apply logical deduction rules to premises."""
        deductions = []
        for i, premise in enumerate(premises):
            p_lower = premise.lower()

            # Modus ponens pattern: "if X then Y" + "X" -> "Y"
            if "if " in p_lower and " then " in p_lower:
                parts = p_lower.split(" then ", 1)
                condition = parts[0].replace("if ", "").strip()
                consequence = parts[1].strip()
                # Check if condition is asserted in other premises
                for other in premises:
                    if other != premise and condition in other.lower():
                        deductions.append(f"By modus ponens: {consequence}")
                        break

            # Transitivity: "A implies B" + "B implies C" -> "A implies C"
            if " implies " in p_lower or " leads to " in p_lower or " causes " in p_lower:
                separator = " implies " if " implies " in p_lower else " leads to " if " leads to " in p_lower else " causes "
                parts = p_lower.split(separator, 1)
                if len(parts) == 2:
                    deductions.append(f"Identified causal chain: {parts[0].strip()} -> {parts[1].strip()}")

            # Contradiction detection
            if any(neg in p_lower for neg in ["not ", "never ", "cannot ", "impossible"]):
                for other in premises:
                    # Simple contradiction: premise negates something another asserts
                    core = p_lower.replace("not ", "").replace("never ", "").replace("cannot ", "").strip()
                    if core in other.lower() and other != premise:
                        deductions.append(f"Contradiction detected between premises {i} and others")
                        break

        if not deductions:
            # Fallback: extract direct assertions
            for p in premises[:3]:
                if not p.startswith("Query:"):
                    deductions.append(f"Accepted premise: {p[:80]}")

        return deductions[:5]

    def _conclude(self, deductions: List[str]) -> str:
        """Derive a conclusion from deduction steps."""
        if not deductions:
            return "Insufficient premises for logical conclusion"

        # Check for contradictions
        has_contradiction = any("contradiction" in d.lower() for d in deductions)
        if has_contradiction:
            return f"Premises contain contradictions — conclusion uncertain ({len(deductions)} steps analyzed)"

        # Check for modus ponens results
        mp_results = [d for d in deductions if "modus ponens" in d.lower()]
        if mp_results:
            return f"Logical derivation: {mp_results[0].replace('By modus ponens: ', '')}"

        # Check for causal chains
        causal = [d for d in deductions if "causal chain" in d.lower()]
        if causal:
            return f"Established causal reasoning from {len(causal)} chain(s)"

        return f"Conclusion drawn from {len(deductions)} accepted premises"


class QiyasEngine:
    """
    Qiyas (قياس) — Analogical Reasoning
    Classical Islamic method of deriving rulings by analogy.

    Finds similar patterns from known cases and applies them to new situations.
    """

    def __init__(self):
        self._pattern_bank: List[Dict] = []

    def add_pattern(self, pattern: str, outcome: str, category: str = "general"):
        """Register a known pattern for future analogical reasoning."""
        self._pattern_bank.append({
            "pattern": pattern,
            "outcome": outcome,
            "category": category,
            "added_at": time.time(),
        })

    def process(self, query: str, context: Optional[Dict] = None) -> CognitiveResult:
        start = time.time()
        context = context or {}

        # Step 1: Find analogous cases
        analogies = self._find_analogies(query)

        # Step 2: Map the analogy
        mapping = self._map_analogy(query, analogies)

        # Step 3: Apply to current case
        conclusion = self._apply_analogy(mapping)

        chain = [f"Found {len(analogies)} analogous cases"]
        for a in analogies[:3]:
            chain.append(f"Analogy: {a.get('pattern', '')[:50]}")
        chain.append(f"Applied analogy: {conclusion}")

        elapsed = (time.time() - start) * 1000
        return CognitiveResult(
            method=CognitiveMethod.QIYAS,
            conclusion=conclusion,
            confidence=min(0.85, 0.3 + 0.2 * len(analogies)),
            reasoning_chain=chain,
            processing_time_ms=elapsed,
        )

    def _find_analogies(self, query: str) -> List[Dict]:
        query_words = set(query.lower().split())
        scored = []
        for pattern in self._pattern_bank:
            pattern_words = set(pattern["pattern"].lower().split())
            overlap = len(query_words & pattern_words)
            if overlap > 0:
                scored.append((overlap, pattern))
        scored.sort(key=lambda x: -x[0])
        return [p for _, p in scored[:5]]

    def _map_analogy(self, query: str, analogies: List[Dict]) -> Dict:
        """Map analogous patterns to the current query, identifying shared structure."""
        if not analogies:
            return {"query": query, "analogies": [], "shared_aspects": [], "strength": 0.0}

        query_words = set(query.lower().split())
        shared_aspects = []
        total_overlap = 0

        for analogy in analogies:
            pattern_words = set(analogy["pattern"].lower().split())
            overlap = query_words & pattern_words
            if overlap:
                shared_aspects.append({
                    "pattern": analogy["pattern"][:60],
                    "outcome": analogy["outcome"][:60],
                    "shared_terms": list(overlap)[:5],
                    "category": analogy.get("category", "general"),
                })
                total_overlap += len(overlap)

        strength = min(1.0, total_overlap / max(len(query_words), 1))

        return {
            "query": query,
            "analogies": analogies,
            "shared_aspects": shared_aspects,
            "strength": round(strength, 3),
        }

    def _apply_analogy(self, mapping: Dict) -> str:
        """Apply the mapped analogy to derive a conclusion for the current query."""
        shared = mapping.get("shared_aspects", [])
        strength = mapping.get("strength", 0)

        if not shared:
            return "No analogous cases found — novel situation requiring first-principles reasoning"

        # Build conclusion from strongest analogies
        outcomes = [a["outcome"] for a in shared if a.get("outcome")]
        categories = list(set(a["category"] for a in shared))

        if strength > 0.5:
            qualifier = "Strong analogy"
        elif strength > 0.2:
            qualifier = "Moderate analogy"
        else:
            qualifier = "Weak analogy"

        conclusion = f"{qualifier} ({strength:.0%}) from {len(shared)} pattern(s)"
        if categories and categories[0] != "general":
            conclusion += f" in domain: {', '.join(categories[:3])}"
        if outcomes:
            conclusion += f". Prior outcome: {outcomes[0][:80]}"

        return conclusion


class IjmaEngine:
    """
    Ijma (إجماع) — Consensus / Ensemble Reasoning

    Runs multiple cognitive methods and builds consensus from their results.
    Similar to ensemble methods in ML — combines multiple perspectives.
    """

    def __init__(self):
        self.tafakkur = TafakkurEngine()
        self.tadabbur = TadabburEngine()
        self.istidlal = IstidlalEngine()
        self.qiyas = QiyasEngine()

    def process(self, query: str, context: Optional[Dict] = None,
                methods: Optional[List[CognitiveMethod]] = None) -> CognitiveResult:
        """
        Run multiple methods and build consensus.
        If methods is None, runs all four base methods.
        """
        start = time.time()
        context = context or {}
        methods = methods or [
            CognitiveMethod.TAFAKKUR,
            CognitiveMethod.TADABBUR,
            CognitiveMethod.ISTIDLAL,
            CognitiveMethod.QIYAS,
        ]

        results: List[CognitiveResult] = []
        engine_map = {
            CognitiveMethod.TAFAKKUR: self.tafakkur,
            CognitiveMethod.TADABBUR: self.tadabbur,
            CognitiveMethod.ISTIDLAL: self.istidlal,
            CognitiveMethod.QIYAS: self.qiyas,
        }

        for method in methods:
            engine = engine_map.get(method)
            if engine:
                results.append(engine.process(query, context))

        # Build consensus
        avg_confidence = sum(r.confidence for r in results) / max(len(results), 1)
        chain = [f"Consulted {len(results)} cognitive methods"]
        for r in results:
            chain.append(f"{r.method.value}: {r.conclusion[:60]} (conf={r.confidence:.2f})")
        chain.append(f"Consensus confidence: {avg_confidence:.2f}")

        elapsed = (time.time() - start) * 1000
        return CognitiveResult(
            method=CognitiveMethod.IJMA,
            conclusion=f"Consensus from {len(results)} methods",
            confidence=avg_confidence,
            reasoning_chain=chain,
            processing_time_ms=elapsed,
            metadata={"sub_results": [r.to_dict() for r in results]},
        )


def select_method(query: str, context: Optional[Dict] = None) -> CognitiveMethod:
    """
    Route a query to the most appropriate cognitive method.

    Heuristic routing based on query characteristics:
    - Analytical / multi-part → Tafakkur
    - Context-heavy / meaning → Tadabbur
    - Logic / proof → Istidlal
    - Comparison / similar → Qiyas
    - Complex / uncertain → Ijma (ensemble)
    """
    q = query.lower()

    # Logical / proof-based
    if any(w in q for w in ["prove", "deduce", "therefore", "logic", "if then", "implies"]):
        return CognitiveMethod.ISTIDLAL

    # Analogical
    if any(w in q for w in ["similar", "like", "compare", "analogy", "pattern"]):
        return CognitiveMethod.QIYAS

    # Context / meaning
    if any(w in q for w in ["meaning", "context", "why", "intent", "purpose", "understand"]):
        return CognitiveMethod.TADABBUR

    # Analytical / complex
    if any(w in q for w in ["analyze", "break down", "components", "detail", "explain"]):
        return CognitiveMethod.TAFAKKUR

    # Default: use ensemble for uncertain queries
    if len(q.split()) > 15 or "?" in q:
        return CognitiveMethod.IJMA

    return CognitiveMethod.TAFAKKUR
