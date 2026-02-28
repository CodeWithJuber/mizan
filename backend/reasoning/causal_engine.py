"""
Causal Engine (عِلَّة) — Pearl's Causal Ladder
================================================

"Does the human think that We will not assemble his bones?
 Yes. [We are] Able [even] to proportion his fingertips." — Quran 75:3-4

Implements Judea Pearl's three rungs of causal reasoning:
  Rung 1 — Observation     (مشاهدة): P(Y|X)          — "What is?"
  Rung 2 — Intervention    (تدخل):   P(Y|do(X))       — "What if I do X?"
  Rung 3 — Counterfactual  (تفكر):   P(Y_x|X', Y')    — "What if I had done X?"

Higher rungs enable deeper understanding of causality —
not just correlation, but actual cause-effect relationships.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("mizan.causal")


class CausalRung(Enum):
    OBSERVATION = 1       # Association — seeing patterns
    INTERVENTION = 2      # Doing — what happens when I act
    COUNTERFACTUAL = 3    # Imagining — what would have been


@dataclass
class CausalNode:
    """A variable in the causal graph."""
    name: str
    value: float = 0.5          # Normalised probability (0-1)
    is_observed: bool = False


@dataclass
class CausalEdge:
    """A directed causal link: source → target with strength."""
    source: str
    target: str
    strength: float = 0.5       # Causal strength (0-1)


@dataclass
class CausalModel:
    """A structural causal model (SCM) built from observations."""
    nodes: dict[str, CausalNode] = field(default_factory=dict)
    edges: list[CausalEdge] = field(default_factory=list)

    def parents_of(self, node_name: str) -> list[str]:
        return [e.source for e in self.edges if e.target == node_name]

    def children_of(self, node_name: str) -> list[str]:
        return [e.target for e in self.edges if e.source == node_name]


@dataclass
class ObservationResult:
    """Rung 1 result: observed associations."""
    rung: CausalRung = CausalRung.OBSERVATION
    associations: dict[str, float] = field(default_factory=dict)
    model: CausalModel = field(default_factory=CausalModel)
    summary: str = ""


@dataclass
class InterventionResult:
    """Rung 2 result: effect of doing action."""
    rung: CausalRung = CausalRung.INTERVENTION
    action: str = ""
    predicted_effects: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.5
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "rung": self.rung.value,
            "action": self.action,
            "predicted_effects": self.predicted_effects,
            "confidence": round(self.confidence, 3),
            "summary": self.summary,
        }


@dataclass
class CounterfactualResult:
    """Rung 3 result: what would have happened."""
    rung: CausalRung = CausalRung.COUNTERFACTUAL
    factual: str = ""
    alternative: str = ""
    counterfactual_outcome: str = ""
    probability: float = 0.5
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "rung": self.rung.value,
            "factual": self.factual,
            "alternative": self.alternative,
            "counterfactual_outcome": self.counterfactual_outcome,
            "probability": round(self.probability, 3),
            "summary": self.summary,
        }


def _detect_causal_rung(text: str) -> CausalRung:
    """
    Detect which causal rung a question requires from its phrasing.
    Rung 3 indicators take priority, then Rung 2, else Rung 1.
    """
    lower = text.lower()
    rung3_signals = [
        "what if i had", "what would have", "if only", "had i",
        "would have been", "could have", "should have",
    ]
    rung2_signals = [
        "what if i", "what happens if", "what would happen",
        "if i do", "if i delete", "if i change", "if i run",
        "what if we", "what if you",
    ]
    if any(s in lower for s in rung3_signals):
        return CausalRung.COUNTERFACTUAL
    if any(s in lower for s in rung2_signals):
        return CausalRung.INTERVENTION
    return CausalRung.OBSERVATION


class CausalEngine:
    """
    Implements Pearl's three-rung causal ladder for agent reasoning.

    Usage:
        engine = CausalEngine()
        model = engine.observe({"database_size": 0.8, "response_time": 0.9})
        result = engine.intervene(model, "delete the database")
        # → InterventionResult(predicted_effects={"response_time": 0.1, ...})
    """

    def observe(self, data: dict[str, float]) -> ObservationResult:
        """
        Rung 1: Build a causal model from observed co-occurrences.
        Data is a dict of {variable_name: probability/value 0-1}.

        Uses correlation as a proxy for causal links (acknowledging the
        correlation ≠ causation limitation — this is Rung 1, not Rung 2).
        """
        model = CausalModel()
        keys = list(data.keys())

        # Create nodes
        for k, v in data.items():
            model.nodes[k] = CausalNode(name=k, value=float(v), is_observed=True)

        # Create edges based on co-occurrence / correlation heuristics
        # High-value nodes tend to "cause" downstream effects
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                va, vb = data[a], data[b]
                # If both are high, assume possible causal relationship
                if abs(va - vb) < 0.3:
                    strength = min(va, vb)
                    if strength > 0.3:
                        model.edges.append(CausalEdge(source=a, target=b, strength=strength))

        associations = {k: round(v, 3) for k, v in data.items()}
        summary = f"Observed {len(keys)} variables, identified {len(model.edges)} potential causal links."

        logger.debug("[CAUSAL] Rung 1: %s", summary)
        return ObservationResult(
            associations=associations,
            model=model,
            summary=summary,
        )

    def intervene(self, model: CausalModel, action: str) -> InterventionResult:
        """
        Rung 2: do-calculus — predict effect of an intervention.

        Simulates "cutting" incoming edges to the action node (Pearl's do-operator)
        and propagating the change downstream through the causal graph.

        action: natural language description of the intervention
        """
        action_lower = action.lower()

        # Map common actions to their variable effects
        # Format: {trigger_word: {variable: delta}}
        _action_effects: dict[str, dict[str, float]] = {
            "delete": {"data_availability": -0.9, "storage_usage": -0.8, "system_stability": -0.3},
            "restart": {"memory_usage": -0.5, "cpu_load": -0.3, "uptime": -0.7},
            "scale": {"throughput": 0.6, "cost": 0.5, "latency": -0.3},
            "cache": {"response_time": -0.4, "memory_usage": 0.3, "throughput": 0.4},
            "remove": {"resource_availability": -0.6, "dependency_count": -0.3},
            "add": {"capability": 0.5, "complexity": 0.3},
            "disable": {"availability": -0.7, "security_risk": -0.2},
            "enable": {"availability": 0.6, "attack_surface": 0.2},
        }

        predicted_effects: dict[str, float] = {}
        matched_action = None

        for trigger, effects in _action_effects.items():
            if trigger in action_lower:
                matched_action = trigger
                # Apply direct effects
                for var, delta in effects.items():
                    predicted_effects[var] = max(0.0, min(1.0, 0.5 + delta))
                # Propagate to downstream nodes in model
                for node_name in model.nodes:
                    for trigger_var in effects:
                        if trigger_var in node_name or node_name in trigger_var:
                            children = model.children_of(node_name)
                            for child in children:
                                if child not in predicted_effects:
                                    edge = next(
                                        (e for e in model.edges
                                         if e.source == node_name and e.target == child),
                                        None
                                    )
                                    if edge:
                                        propagated = effects[trigger_var] * edge.strength * 0.7
                                        predicted_effects[child] = max(
                                            0.0, min(1.0, model.nodes[child].value + propagated)
                                        )
                break

        if not matched_action:
            predicted_effects = {"uncertainty": 0.7}

        confidence = 0.6 if matched_action else 0.3
        summary = (
            f"do({action}): predicts effects on {len(predicted_effects)} variables. "
            f"Confidence: {'moderate' if confidence >= 0.5 else 'low'} "
            f"(Rung 2 do-calculus)."
        )

        logger.debug("[CAUSAL] Rung 2: action='%s' effects=%s", action[:60], predicted_effects)
        return InterventionResult(
            action=action,
            predicted_effects={k: round(v, 3) for k, v in predicted_effects.items()},
            confidence=confidence,
            summary=summary,
        )

    def counterfactual(
        self,
        model: CausalModel,
        factual: str,
        alternative: str,
    ) -> CounterfactualResult:
        """
        Rung 3: Counterfactual reasoning — what would have happened
        under an alternative course of action.

        Uses abduction (infer hidden state from observed outcome),
        then predicts what the outcome would have been under the alternative.
        """
        # Step 1: Abduction — infer hidden exogenous factors from factual outcome
        # (Simplified: use causal model to estimate prior state)
        factual_result = self.intervene(model, factual)
        alt_result = self.intervene(model, alternative)

        # Step 2: Prediction — compare outcomes
        factual_effects = factual_result.predicted_effects
        alt_effects = alt_result.predicted_effects

        # Compute what would have differed
        diffs: dict[str, float] = {}
        all_vars = set(factual_effects) | set(alt_effects)
        for var in all_vars:
            fa = factual_effects.get(var, 0.5)
            aa = alt_effects.get(var, 0.5)
            if abs(fa - aa) > 0.05:
                diffs[var] = round(aa - fa, 3)

        if diffs:
            changes = ", ".join(
                f"{var}: {'+' if d >= 0 else ''}{d:.2f}"
                for var, d in sorted(diffs.items(), key=lambda x: -abs(x[1]))[:5]
            )
            counterfactual_outcome = f"If '{alternative}' instead of '{factual}': {changes}"
            probability = alt_result.confidence * 0.8  # Counterfactuals are less certain
        else:
            counterfactual_outcome = (
                f"No significant difference between '{factual}' and '{alternative}'."
            )
            probability = 0.5

        summary = (
            f"Counterfactual (Rung 3): {counterfactual_outcome}. "
            f"Probability estimate: {probability:.0%}."
        )

        logger.debug("[CAUSAL] Rung 3: factual='%s' alt='%s' prob=%.2f",
                     factual[:40], alternative[:40], probability)
        return CounterfactualResult(
            factual=factual,
            alternative=alternative,
            counterfactual_outcome=counterfactual_outcome,
            probability=round(probability, 3),
            summary=summary,
        )

    def analyze_query(self, query: str, data: dict[str, float] = None) -> dict:
        """
        Auto-detect the required causal rung and run the appropriate analysis.
        Entry point for agent tool use.
        """
        rung = _detect_causal_rung(query)
        data = data or {}
        model = self.observe(data) if data else ObservationResult(model=CausalModel())

        if rung == CausalRung.OBSERVATION:
            return {
                "rung": 1,
                "type": "observation",
                "result": model.summary,
                "associations": model.associations,
            }
        elif rung == CausalRung.INTERVENTION:
            result = self.intervene(model.model, query)
            return {
                "rung": 2,
                "type": "intervention",
                "result": result.summary,
                **result.to_dict(),
            }
        else:
            # Counterfactual: parse factual vs alternative from query
            parts = query.lower().split("instead of")
            alt = parts[0].strip() if parts else query
            factual = parts[1].strip() if len(parts) > 1 else "current state"
            result = self.counterfactual(model.model, factual, alt)
            return {
                "rung": 3,
                "type": "counterfactual",
                "result": result.summary,
                **result.to_dict(),
            }
