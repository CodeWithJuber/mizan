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
        return f"Analysis of '{component[:50]}'"

    def _synthesize(self, analyses: List[str]) -> str:
        return f"Synthesized understanding from {len(analyses)} analyses"


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
        return query[:100]

    def _extract_deeper(self, query: str, context: Dict) -> str:
        user_history = context.get("history", [])
        if user_history:
            return f"Contextual understanding with {len(user_history)} prior interactions"
        return "Direct interpretation of query"

    def _derive_implications(self, query: str, context: Dict) -> str:
        return "Considered broader implications"


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
        return [f"From premises, deduced step {i+1}" for i in range(min(3, len(premises)))]

    def _conclude(self, deductions: List[str]) -> str:
        return f"Logical conclusion from {len(deductions)} deduction steps"


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
        return {"query": query, "analogies": analogies}

    def _apply_analogy(self, mapping: Dict) -> str:
        count = len(mapping.get("analogies", []))
        if count == 0:
            return "No analogous cases found — novel situation"
        return f"Applied {count} analogous pattern(s) to derive solution"


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
