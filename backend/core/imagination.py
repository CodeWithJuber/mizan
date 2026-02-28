"""
Taṣwīr — Imagination Engine
=============================

"He is Allah, the Creator, the Originator, the Fashioner (al-Muṣawwir)" — Quran 59:24

Implements Algorithm 5: TASWIR_IMAGINATION_ENGINE

Mental simulation with predictive coding and hierarchical scene generation.

Predictive coding update rule:
  μ_l(t+1) = μ_l(t) + κ_l[ε_l(t) - ε_{l+1}(t)]

  where:
  - μ_l = mean prediction at layer l
  - ε_l = prediction error at layer l
  - κ_l = learning rate at layer l
  - ε_{l+1} = top-down prediction from layer above

Counterfactual reasoning follows Pearl's 3-step procedure:
  1. Abduction: infer latent state from observations
  2. Action: apply counterfactual intervention
  3. Prediction: propagate through causal model
"""

import logging
import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("mizan.imagination")

# Predictive coding parameters
KAPPA = [0.3, 0.2, 0.1, 0.05]  # learning rates per layer (coarse → fine)
N_LAYERS = 4

# Emotional tagging thresholds
EMOTIONAL_VALENCE_THRESHOLD = 0.3

# Scene generation resolution levels
RESOLUTION_COARSE = "coarse"
RESOLUTION_MEDIUM = "medium"
RESOLUTION_FINE = "fine"


class ImaginationMode(Enum):
    PROSPECTIVE = "prospective"     # Forward simulation: what will happen?
    RETROSPECTIVE = "retrospective" # Backward: what led to this?
    COUNTERFACTUAL = "counterfactual"  # What if? (Pearl Rung 3)
    CREATIVE = "creative"           # Novel scene construction


@dataclass
class SceneFragment:
    """A memory fragment used to construct imagined scenes."""
    content: str
    source: str          # "episodic", "semantic", "sensory"
    salience: float
    emotional_tag: float  # -1.0 (negative) to +1.0 (positive)


@dataclass
class HierarchicalScene:
    """Multi-resolution mental scene."""
    coarse: str          # High-level gist: "a meeting goes wrong"
    medium: str          # Mid-level: actors, setting, actions
    fine: str            # Fine-grained: specific details, dialogue
    emotional_valence: float
    confidence: float
    prediction_errors: list[float]  # ε per layer


@dataclass
class MentalSimulation:
    """Result of running a mental simulation forward."""
    scenario: str
    steps: list[str]
    predicted_outcome: str
    emotional_trajectory: list[float]  # valence at each step
    confidence: float
    surprisal: float    # -log P(outcome): how unexpected?


@dataclass
class CounterfactualResult:
    """Pearl Rung 3 counterfactual analysis."""
    original_observation: str
    intervention: str
    counterfactual_world: str
    probability_shift: float   # ΔP(outcome) under intervention
    abduced_state: dict        # latent variables inferred


@dataclass
class ImaginationResult:
    mode: ImaginationMode
    scene: HierarchicalScene
    simulation: MentalSimulation | None
    counterfactual: CounterfactualResult | None
    predictive_states: list[float]   # μ_l per layer
    total_surprise: float


class TaswirImaginationEngine:
    """
    Algorithm 5: TASWIR_IMAGINATION_ENGINE

    Constructs imagined scenes from memory fragments, runs forward
    mental simulations, and performs counterfactual reasoning.

    Architecture:
    - Hippocampal recombination: assembles fragments from memory
    - Hierarchical predictive coding: coarse → medium → fine rendering
    - Qalb emotional tagging: attaches valence to each simulation step
    - Counterfactual module: abduction → action → prediction (Pearl 3)
    """

    def __init__(self):
        # Predictive coding state: mean predictions per layer
        self.mu: list[float] = [0.0] * N_LAYERS
        self.memory_fragments: list[SceneFragment] = []
        self._simulation_count = 0

    def imagine(
        self,
        prompt: str,
        mode: ImaginationMode = ImaginationMode.PROSPECTIVE,
        memory_fragments: list[dict] | None = None,
        counterfactual_intervention: str | None = None,
    ) -> ImaginationResult:
        """
        Main entry point for imagination.

        Steps:
        1. Hippocampal recombination (assemble scene fragments)
        2. Hierarchical scene generation (coarse → fine)
        3. Predictive coding update
        4. Forward mental simulation
        5. Emotional tagging via Qalb
        6. Counterfactual reasoning (if mode == COUNTERFACTUAL)
        """
        self._simulation_count += 1

        # Step 1: Recombine memory fragments
        fragments = self._recombine_fragments(prompt, memory_fragments or [])

        # Step 2: Hierarchical scene generation
        scene = self._generate_hierarchical_scene(prompt, fragments)

        # Step 3: Predictive coding update
        prediction_errors = self._compute_prediction_errors(scene)
        self._update_predictions(prediction_errors)

        # Step 4: Forward mental simulation
        simulation = None
        if mode in (ImaginationMode.PROSPECTIVE, ImaginationMode.CREATIVE):
            simulation = self._run_forward_simulation(prompt, scene)

        # Step 5: Counterfactual
        counterfactual = None
        if mode == ImaginationMode.COUNTERFACTUAL and counterfactual_intervention:
            counterfactual = self._counterfactual_reasoning(
                prompt, counterfactual_intervention, scene
            )

        total_surprise = sum(abs(e) for e in prediction_errors)

        logger.debug(
            "[TASWIR] mode=%s fragments=%d surprise=%.3f",
            mode.value, len(fragments), total_surprise,
        )

        return ImaginationResult(
            mode=mode,
            scene=scene,
            simulation=simulation,
            counterfactual=counterfactual,
            predictive_states=list(self.mu),
            total_surprise=round(total_surprise, 4),
        )

    def _recombine_fragments(
        self, prompt: str, raw_fragments: list[dict]
    ) -> list[SceneFragment]:
        """
        Hippocampal recombination: select and blend memory fragments
        relevant to the prompt.

        Salience = cosine_sim(fragment, prompt) × emotional_weight
        (Approximated by keyword overlap here.)
        """
        prompt_words = set(prompt.lower().split())
        fragments = []

        for raw in raw_fragments:
            content = raw.get("content", "")
            content_words = set(content.lower().split())
            overlap = len(prompt_words & content_words) / max(len(prompt_words), 1)
            emotional_tag = raw.get("emotional_tag", 0.0)
            salience = overlap * 0.7 + abs(emotional_tag) * 0.3

            fragments.append(SceneFragment(
                content=content,
                source=raw.get("source", "semantic"),
                salience=salience,
                emotional_tag=emotional_tag,
            ))

        # Sort by salience, keep top fragments
        fragments.sort(key=lambda f: f.salience, reverse=True)
        top = fragments[:5]

        # Add synthetic fragment from prompt itself
        top.append(SceneFragment(
            content=prompt,
            source="episodic",
            salience=1.0,
            emotional_tag=self._estimate_valence(prompt),
        ))

        return top

    def _generate_hierarchical_scene(
        self, prompt: str, fragments: list[SceneFragment]
    ) -> HierarchicalScene:
        """
        Build 3-resolution mental scene via hierarchical predictive coding.

        Coarse level: high-level gist (layer 4 — most abstract)
        Medium level: actors and actions (layer 2-3)
        Fine level: specific details (layer 1 — most concrete)
        """
        # Coarse: extract gist from dominant fragment
        dominant = max(fragments, key=lambda f: f.salience) if fragments else None
        coarse = self._extract_gist(prompt, dominant)

        # Medium: identify actors and setting
        medium = self._extract_actors_and_setting(prompt, fragments)

        # Fine: construct specific details
        fine = self._construct_fine_details(prompt, fragments)

        # Emotional valence: weighted average across fragments
        if fragments:
            total_salience = sum(f.salience for f in fragments)
            emotional_valence = sum(
                f.emotional_tag * f.salience for f in fragments
            ) / max(total_salience, 0.01)
        else:
            emotional_valence = 0.0

        # Confidence: based on fragment coverage
        coverage = len(fragments) / max(1, len(fragments) + 2)
        confidence = 0.3 + 0.7 * coverage

        return HierarchicalScene(
            coarse=coarse,
            medium=medium,
            fine=fine,
            emotional_valence=round(emotional_valence, 3),
            confidence=round(confidence, 3),
            prediction_errors=[],
        )

    def _compute_prediction_errors(
        self, scene: HierarchicalScene
    ) -> list[float]:
        """
        Prediction error at each layer:
        ε_l(t) = observation_l - μ_l(t)

        Layers: [fine, medium, coarse, abstract]
        """
        # Map scene to activation signals (0-1)
        observations = [
            self._text_to_activation(scene.fine),
            self._text_to_activation(scene.medium),
            self._text_to_activation(scene.coarse),
            scene.confidence,  # abstract layer = overall confidence
        ]
        errors = [obs - mu for obs, mu in zip(observations, self.mu)]
        scene.prediction_errors = errors
        return errors

    def _update_predictions(self, errors: list[float]) -> None:
        """
        μ_l(t+1) = μ_l(t) + κ_l[ε_l(t) - ε_{l+1}(t)]

        Top-down correction: each layer's prediction is adjusted
        by the difference between its own error and the layer above.
        """
        for l in range(N_LAYERS):
            own_error = errors[l]
            upper_error = errors[l + 1] if l + 1 < N_LAYERS else 0.0
            self.mu[l] = max(0.0, min(1.0,
                self.mu[l] + KAPPA[l] * (own_error - upper_error)
            ))

    def _run_forward_simulation(
        self, prompt: str, scene: HierarchicalScene
    ) -> MentalSimulation:
        """
        Run mental simulation forward in time from the imagined scene.

        Uses scene as initial state; generates causal step sequence.
        """
        steps = []
        emotional_trajectory = [scene.emotional_valence]
        current_valence = scene.emotional_valence

        # Generate up to 4 simulation steps
        sim_templates = [
            f"Initial state: {scene.coarse}",
            f"Development: {scene.medium}",
            f"Key action: {self._extract_action(prompt)}",
            f"Consequence: outcome follows from action",
        ]
        for template in sim_templates:
            steps.append(template)
            # Emotional drift: move 10% toward neutral per step
            current_valence = current_valence * 0.9
            emotional_trajectory.append(round(current_valence, 3))

        predicted_outcome = (
            f"Outcome {'positive' if scene.emotional_valence > 0 else 'challenging'}: "
            f"{scene.fine[:100]}"
        )

        # Surprisal: -log P(outcome) approximated by (1 - confidence)
        surprisal = -math.log(max(scene.confidence, 0.01))

        return MentalSimulation(
            scenario=prompt[:200],
            steps=steps,
            predicted_outcome=predicted_outcome,
            emotional_trajectory=emotional_trajectory,
            confidence=scene.confidence,
            surprisal=round(surprisal, 4),
        )

    def _counterfactual_reasoning(
        self,
        observation: str,
        intervention: str,
        scene: HierarchicalScene,
    ) -> CounterfactualResult:
        """
        Pearl's 3-step counterfactual procedure:
        1. Abduction: infer latent state U from (observation, scene)
        2. Action: apply intervention (modify causal model)
        3. Prediction: propagate modified model → counterfactual world

        ΔP = P(Y|do(X=x')) - P(Y|X=x)
        """
        # Step 1: Abduction — infer latent state
        abduced_state = {
            "world_model": scene.coarse,
            "confidence": scene.confidence,
            "emotional_context": scene.emotional_valence,
            "inferred_causes": self._infer_causes(observation),
        }

        # Step 2: Action — apply counterfactual intervention
        # Estimate how much the intervention changes the causal structure
        intervention_strength = min(1.0, len(intervention.split()) / 20.0)
        probability_shift = intervention_strength * (1.0 - scene.confidence)

        # Step 3: Prediction — generate counterfactual world
        original_valence = scene.emotional_valence
        counterfactual_valence = original_valence + probability_shift * (
            1.0 - abs(original_valence)
        )
        counterfactual_world = (
            f"Under intervention '{intervention[:80]}': "
            f"The world differs from '{scene.coarse[:80]}' with "
            f"P(outcome) shift of {probability_shift:.2%}. "
            f"New emotional trajectory: {counterfactual_valence:.3f}"
        )

        return CounterfactualResult(
            original_observation=observation[:200],
            intervention=intervention[:200],
            counterfactual_world=counterfactual_world,
            probability_shift=round(probability_shift, 4),
            abduced_state=abduced_state,
        )

    def _extract_gist(self, prompt: str, dominant: SceneFragment | None) -> str:
        words = prompt.split()[:6]
        gist_seed = " ".join(words)
        if dominant:
            return f"{gist_seed} → {dominant.content[:60]}"
        return f"Imagined scenario: {gist_seed}"

    def _extract_actors_and_setting(
        self, prompt: str, fragments: list[SceneFragment]
    ) -> str:
        context = " | ".join(f.content[:40] for f in fragments[:2])
        return f"Setting: {prompt[:60]} | Context: {context}"

    def _construct_fine_details(
        self, prompt: str, fragments: list[SceneFragment]
    ) -> str:
        details = " ".join(f.content[:30] for f in fragments[:3])
        return f"Details: {details[:200]}"

    def _extract_action(self, prompt: str) -> str:
        action_verbs = ["create", "delete", "build", "fix", "analyze", "send", "run"]
        for verb in action_verbs:
            if verb in prompt.lower():
                return f"{verb} [primary action]"
        return "proceed with task"

    def _infer_causes(self, observation: str) -> list[str]:
        """Simplified abduction: extract likely causal factors from observation."""
        words = observation.split()
        return [w for w in words if len(w) > 5][:3]

    @staticmethod
    def _estimate_valence(text: str) -> float:
        positive = {"help", "good", "create", "success", "improve", "benefit"}
        negative = {"error", "fail", "harm", "delete", "wrong", "danger"}
        words = set(text.lower().split())
        pos = len(words & positive)
        neg = len(words & negative)
        total = pos + neg
        if total == 0:
            return 0.0
        return (pos - neg) / total

    @staticmethod
    def _text_to_activation(text: str) -> float:
        """Map text richness to a 0-1 activation signal."""
        return min(1.0, len(text.split()) / 30.0)

    def to_dict(self) -> dict:
        return {
            "predictive_states": [round(m, 4) for m in self.mu],
            "fragment_count": len(self.memory_fragments),
            "simulation_count": self._simulation_count,
            "n_layers": N_LAYERS,
        }
