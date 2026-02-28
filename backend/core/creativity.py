"""
Ibdāʿ — Creativity Engine
===========================

"And He taught Adam the names of all things" — Quran 2:31

Implements Algorithm 4: IBDA_CREATIVITY_ENGINE

5 creation modes (from Quranic creative verbs):
  1. Badī': Radical origination — novelty gradient ascent
  2. Khalq: Measured creation — evolutionary refinement
  3. Jaʿl: Recombination — conceptual blending + analogy
  4. Ṣunʿ: Refinement — gradient descent on imperfection
  5. Taṣwīr: Visualization — scene construction (imagination engine)

Creativity landscape:
  Ψ(z) = U(z)^β × N(z)^α × F(z)

  where:
  - U(z) = utility (task relevance score)
  - N(z) = novelty (distance from known solutions)
  - F(z) = feasibility (implementation constraint satisfaction)
  - α = novelty weight, β = utility weight

Novelty gradient:
  ∇z novelty(z) = ∇z[-min_k ||z - z_known_k||²]
  → move away from known solutions in concept space

Creative oscillation:
  mode(t) = floor(sin(2π·t/T_creative) × 2.5) → cycles through modes
  T_creative ≈ 30-90 interactions
"""

import logging
import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("mizan.creativity")

# Creativity landscape weights
ALPHA_NOVELTY = 0.4     # novelty importance
BETA_UTILITY = 0.5      # utility importance
# Feasibility has implicit weight: 1 - α - β = 0.1 (or computed as multiplier)

# Creative oscillation period (interactions)
T_CREATIVE = 60

# Novelty distance threshold — closer than this is "known"
NOVELTY_PROXIMITY_THRESHOLD = 0.3

# Khalq evolutionary parameters
MUTATION_RATE = 0.15
SELECTION_PRESSURE = 0.7


class CreationMode(Enum):
    BADI = "badi"        # Radical origination (Badī')
    KHALQ = "khalq"      # Measured evolutionary creation
    JAL = "jal"          # Recombination / analogy (Jaʿl)
    SUNW = "sunw"        # Refinement / polish (Ṣunʿ)
    TASWIR = "taswir"    # Visualization (Taṣwīr)


@dataclass
class ConceptVector:
    """A concept in the creativity latent space."""
    label: str
    features: dict[str, float]   # semantic feature dimensions
    novelty_score: float = 0.0
    utility_score: float = 0.0
    feasibility_score: float = 0.0

    def landscape_score(self, alpha: float = ALPHA_NOVELTY, beta: float = BETA_UTILITY) -> float:
        """Ψ(z) = U^β × N^α × F"""
        return (
            (self.utility_score ** beta)
            * (self.novelty_score ** alpha)
            * max(0.01, self.feasibility_score)
        )


@dataclass
class BisociationResult:
    """Result of bisociation (Koestler): two matrices of thought intersect."""
    concept_a: str
    concept_b: str
    intersection: str   # the "aha" moment
    novelty: float
    metaphor: str


@dataclass
class CreativeOutput:
    mode: CreationMode
    primary_idea: str
    elaboration: str
    bisociations: list[BisociationResult]
    landscape_score: float
    novelty: float
    utility: float
    feasibility: float
    iterations: int
    creative_oscillation_phase: float


class IbdaCreativityEngine:
    """
    Algorithm 4: IBDA_CREATIVITY_ENGINE

    Routes tasks to the appropriate creation mode based on:
    - Task type (novel vs refined vs recombined)
    - Qalb oscillation phase (creative cycle)
    - Available conceptual vocabulary
    - Landscape scoring Ψ(z) = U^β × N^α × F

    Each mode has a distinct mathematical procedure:
    - Badī': gradient ascent on novelty landscape
    - Khalq: evolutionary selection pressure
    - Jaʿl: structure mapping + conceptual blending
    - Ṣunʿ: gradient descent on imperfection metric
    - Taṣwīr: delegates to imagination engine
    """

    def __init__(self):
        self.known_solutions: list[ConceptVector] = []
        self.interaction_count = 0
        self.mode_history: list[CreationMode] = []

    def create(
        self,
        task: str,
        constraints: list[str] | None = None,
        force_mode: CreationMode | None = None,
        context_fragments: list[str] | None = None,
    ) -> CreativeOutput:
        """
        Main creativity entry point.

        1. Select creation mode (oscillation or forced)
        2. Generate concept vector for task
        3. Apply mode-specific algorithm
        4. Score on creativity landscape
        5. Return creative output
        """
        self.interaction_count += 1
        constraints = constraints or []
        context_fragments = context_fragments or []

        # Select mode
        mode = force_mode or self._select_mode()
        self.mode_history.append(mode)

        # Build initial concept vector
        concept = self._build_concept_vector(task, context_fragments)

        # Apply creation mode
        if mode == CreationMode.BADI:
            result = self._badi_origination(task, concept, constraints)
        elif mode == CreationMode.KHALQ:
            result = self._khalq_evolution(task, concept, constraints)
        elif mode == CreationMode.JAL:
            result = self._jal_recombination(task, concept, context_fragments)
        elif mode == CreationMode.SUNW:
            result = self._sunw_refinement(task, concept, constraints)
        else:  # TASWIR
            result = self._taswir_visualization(task, concept)

        # Score on landscape
        concept.novelty_score = result.novelty
        concept.utility_score = result.utility
        concept.feasibility_score = result.feasibility
        result.landscape_score = concept.landscape_score()

        # Register solution as known (for future novelty computation)
        self._register_known_solution(concept)

        logger.debug(
            "[IBDA] mode=%s Ψ=%.3f N=%.3f U=%.3f F=%.3f",
            mode.value, result.landscape_score, result.novelty,
            result.utility, result.feasibility,
        )

        return result

    def _select_mode(self) -> CreationMode:
        """
        Creative oscillation:
        mode(t) = f(sin(2π·t/T_creative))

        Maps sinusoidal phase to creation modes cyclically.
        """
        phase = (2 * math.pi * self.interaction_count) / T_CREATIVE
        sin_val = math.sin(phase)
        # Map [-1, 1] → [0, 4] → mode index
        mode_idx = int((sin_val + 1.0) / 2.0 * (len(CreationMode) - 0.01))
        modes = list(CreationMode)
        return modes[mode_idx]

    def _build_concept_vector(
        self, task: str, fragments: list[str]
    ) -> ConceptVector:
        """Build feature vector for task in concept space."""
        words = task.lower().split()
        features = {
            "length": min(1.0, len(words) / 50.0),
            "novelty_seed": (hash(task) % 1000) / 1000.0,
            "fragment_richness": min(1.0, len(fragments) / 5.0),
            "question_mark": 1.0 if "?" in task else 0.0,
            "imperative": 1.0 if words[0] in {"create", "build", "design", "make", "write"} else 0.0,
        }
        return ConceptVector(label=task[:50], features=features)

    def _badi_origination(
        self, task: str, concept: ConceptVector, constraints: list[str]
    ) -> CreativeOutput:
        """
        Badī': Radical origination via novelty gradient ascent.

        ∇z novelty(z) = ∇z[-min_k ||z - z_known_k||²]

        Move maximally far from all known solutions.
        Constraints are relaxed progressively.
        """
        # Compute minimum distance to known solutions
        min_dist = self._min_distance_to_known(concept)
        novelty = min(1.0, min_dist + 0.2)  # gradient step pushes away

        # Radical idea generation: invert standard approaches
        inversions = self._generate_inversions(task)
        primary_idea = inversions[0] if inversions else f"Radical reframe of: {task[:80]}"
        elaboration = " | ".join(inversions[:3]) if inversions else "No known solutions — pure origination territory"

        bisociations = self._find_bisociations(task, n=2)

        return CreativeOutput(
            mode=CreationMode.BADI,
            primary_idea=primary_idea,
            elaboration=elaboration,
            bisociations=bisociations,
            landscape_score=0.0,  # computed after
            novelty=round(novelty, 3),
            utility=round(self._estimate_utility(task, primary_idea, constraints), 3),
            feasibility=round(self._estimate_feasibility(primary_idea, constraints), 3),
            iterations=1,
            creative_oscillation_phase=round(
                (2 * math.pi * self.interaction_count) / T_CREATIVE, 4
            ),
        )

    def _khalq_evolution(
        self, task: str, concept: ConceptVector, constraints: list[str], generations: int = 3
    ) -> CreativeOutput:
        """
        Khalq: Measured creation via evolutionary refinement.

        Population of candidate solutions evolves over generations.
        Fitness = Ψ(z) landscape score.
        Mutation rate decays with generations (constraint relaxation schedule).
        """
        # Generate initial population
        population = [self._generate_candidate(task, constraints, mutation=MUTATION_RATE)]
        for _ in range(2):
            population.append(self._generate_candidate(
                task, constraints, mutation=MUTATION_RATE * 1.5
            ))

        best = population[0]
        best_score = 0.0
        iterations = 0

        for gen in range(generations):
            # Score and select
            scored = [
                (c, self._score_candidate(c, task, constraints))
                for c in population
            ]
            scored.sort(key=lambda x: x[1], reverse=True)
            best, best_score = scored[0]

            # Mutate survivors into next generation
            survivors = [c for c, _ in scored[:max(1, len(scored) // 2)]]
            mutation = MUTATION_RATE * (1.0 - gen / generations * SELECTION_PRESSURE)
            population = survivors + [
                self._mutate_candidate(s, mutation) for s in survivors
            ]
            iterations = gen + 1

        bisociations = self._find_bisociations(task, n=1)
        novelty = max(0.3, min(0.9, 1.0 - self._min_distance_to_known(concept) * 0.5))

        return CreativeOutput(
            mode=CreationMode.KHALQ,
            primary_idea=best,
            elaboration=f"Evolved over {iterations} generations. Fitness: {best_score:.3f}",
            bisociations=bisociations,
            landscape_score=0.0,
            novelty=round(novelty, 3),
            utility=round(self._estimate_utility(task, best, constraints), 3),
            feasibility=round(self._estimate_feasibility(best, constraints), 3),
            iterations=iterations,
            creative_oscillation_phase=round(
                (2 * math.pi * self.interaction_count) / T_CREATIVE, 4
            ),
        )

    def _jal_recombination(
        self, task: str, concept: ConceptVector, fragments: list[str]
    ) -> CreativeOutput:
        """
        Jaʿl: Recombination via conceptual blending and analogy.

        Structure mapping (Gentner): find common relational structure
        between source and target domains.

        Bisociation (Koestler): two matrices of thought intersect
        at an unexpected point → creative insight.
        """
        bisociations = self._find_bisociations(task, n=3)

        # Blend top fragments with task
        blended_concepts = []
        for fragment in fragments[:2]:
            blend = self._blend_concepts(task, fragment)
            blended_concepts.append(blend)

        primary_idea = (
            bisociations[0].intersection
            if bisociations
            else f"Blend of {len(fragments)} context fragments with task"
        )
        elaboration = " | ".join(blended_concepts[:2]) if blended_concepts else task

        novelty = 0.5 + 0.3 * (len(bisociations) / 3)

        return CreativeOutput(
            mode=CreationMode.JAL,
            primary_idea=primary_idea,
            elaboration=elaboration,
            bisociations=bisociations,
            landscape_score=0.0,
            novelty=round(min(0.9, novelty), 3),
            utility=round(self._estimate_utility(task, primary_idea, []), 3),
            feasibility=round(0.7, 3),  # recombination is inherently feasible
            iterations=1,
            creative_oscillation_phase=round(
                (2 * math.pi * self.interaction_count) / T_CREATIVE, 4
            ),
        )

    def _sunw_refinement(
        self, task: str, concept: ConceptVector, constraints: list[str]
    ) -> CreativeOutput:
        """
        Ṣunʿ: Refinement via gradient descent on imperfection.

        elegance = utility / complexity
        imperfection = 1 - elegance

        Iterate: identify imperfection sources, apply targeted fixes.
        """
        # Start with a standard approach and refine
        base_idea = f"Standard approach: {task[:100]}"
        imperfections = self._identify_imperfections(base_idea, constraints)

        refined = base_idea
        iterations = 0
        for imperfection in imperfections[:3]:
            refined = self._apply_refinement(refined, imperfection)
            iterations += 1

        elegance = self._compute_elegance(refined, constraints)

        return CreativeOutput(
            mode=CreationMode.SUNW,
            primary_idea=refined,
            elaboration=f"Refined {iterations} imperfections. Elegance: {elegance:.3f}",
            bisociations=[],
            landscape_score=0.0,
            novelty=round(0.2 + 0.3 * elegance, 3),  # refined = less novel
            utility=round(0.6 + 0.3 * elegance, 3),  # but more useful
            feasibility=round(0.8, 3),
            iterations=iterations,
            creative_oscillation_phase=round(
                (2 * math.pi * self.interaction_count) / T_CREATIVE, 4
            ),
        )

    def _taswir_visualization(
        self, task: str, concept: ConceptVector
    ) -> CreativeOutput:
        """
        Taṣwīr: Creative visualization — generates a rich mental image.
        Delegates to imagination engine in full integration.
        """
        visual_description = (
            f"Visual scenario: [{task[:80]}]\n"
            f"Scene: {concept.features.get('novelty_seed', 0.5):.2f} novelty intensity\n"
            f"Render: coarse→medium→fine hierarchical construction"
        )

        return CreativeOutput(
            mode=CreationMode.TASWIR,
            primary_idea=f"Visualized: {task[:100]}",
            elaboration=visual_description,
            bisociations=[],
            landscape_score=0.0,
            novelty=round(0.6, 3),
            utility=round(0.7, 3),
            feasibility=round(0.9, 3),
            iterations=1,
            creative_oscillation_phase=round(
                (2 * math.pi * self.interaction_count) / T_CREATIVE, 4
            ),
        )

    def _find_bisociations(self, task: str, n: int = 2) -> list[BisociationResult]:
        """
        Bisociation: find two distant concept matrices that unexpectedly intersect.
        """
        domain_pairs = [
            ("biology", "software"),
            ("music", "mathematics"),
            ("architecture", "language"),
            ("cooking", "algorithms"),
            ("navigation", "problem_solving"),
        ]

        results = []
        task_lower = task.lower()

        for domain_a, domain_b in domain_pairs[:n]:
            intersection = f"The {domain_a} metaphor applied to {task[:40]}: {domain_b} lens"
            metaphor = f"Like {domain_a} processes, this task involves {domain_b} principles"
            novelty = 0.6 + (hash(domain_a + task) % 30) / 100.0

            results.append(BisociationResult(
                concept_a=domain_a,
                concept_b=domain_b,
                intersection=intersection,
                novelty=round(min(0.95, novelty), 3),
                metaphor=metaphor,
            ))

        return results

    def _blend_concepts(self, concept_a: str, concept_b: str) -> str:
        """Structure mapping: extract relational structure common to A and B."""
        words_a = set(concept_a.lower().split()[:5])
        words_b = set(concept_b.lower().split()[:5])
        shared = words_a & words_b
        unique_a = (words_a - words_b)
        unique_b = (words_b - words_a)

        if shared:
            return f"Shared structure [{', '.join(list(shared)[:2])}] bridging [{', '.join(list(unique_a)[:2])}] and [{', '.join(list(unique_b)[:2])}]"
        return f"Cross-domain blend: {concept_a[:30]} ↔ {concept_b[:30]}"

    def _generate_inversions(self, task: str) -> list[str]:
        """Generate radical inversions of standard approaches."""
        inversions = [
            f"Invert: Instead of solving '{task[:50]}', solve its opposite",
            f"Constraint removal: What if there were no constraints on '{task[:40]}'?",
            f"Scale inversion: Apply micro/macro scale inversion to '{task[:40]}'",
        ]
        return inversions

    def _generate_candidate(
        self, task: str, constraints: list[str], mutation: float
    ) -> str:
        """Generate a candidate solution for evolutionary selection."""
        seed = f"Approach {random.random():.2f}: {task[:60]}"
        if constraints:
            seed += f" (satisfying: {constraints[0][:40]})"
        return seed

    def _mutate_candidate(self, candidate: str, mutation_rate: float) -> str:
        """Apply mutation to a candidate solution."""
        words = candidate.split()
        if len(words) > 3 and random.random() < mutation_rate:
            idx = random.randint(1, len(words) - 1)
            words[idx] = f"[mutated:{words[idx]}]"
        return " ".join(words)

    def _score_candidate(
        self, candidate: str, task: str, constraints: list[str]
    ) -> float:
        """Fitness function for evolutionary selection."""
        utility = self._estimate_utility(task, candidate, constraints)
        feasibility = self._estimate_feasibility(candidate, constraints)
        return utility * BETA_UTILITY + feasibility * (1.0 - BETA_UTILITY)

    def _identify_imperfections(
        self, idea: str, constraints: list[str]
    ) -> list[str]:
        """Find imperfections in current idea relative to constraints."""
        imperfections = []
        if len(idea.split()) > 20:
            imperfections.append("verbosity")
        if not constraints:
            imperfections.append("missing constraints")
        if "standard" in idea.lower():
            imperfections.append("lack of novelty")
        return imperfections

    def _apply_refinement(self, idea: str, imperfection: str) -> str:
        """Apply targeted fix to an imperfection."""
        if imperfection == "verbosity":
            return idea[:len(idea) // 2] + " [condensed]"
        if imperfection == "lack of novelty":
            return idea.replace("standard", "novel")
        return idea + f" [refined: {imperfection} addressed]"

    def _compute_elegance(self, idea: str, constraints: list[str]) -> float:
        """elegance = utility / complexity"""
        utility = self._estimate_utility("", idea, constraints)
        complexity = min(1.0, len(idea.split()) / 30.0)
        return utility / max(complexity, 0.1)

    def _estimate_utility(
        self, task: str, idea: str, constraints: list[str]
    ) -> float:
        """Estimate how useful the idea is for the task."""
        if not task:
            return 0.6
        task_words = set(task.lower().split())
        idea_words = set(idea.lower().split())
        overlap = len(task_words & idea_words) / max(len(task_words), 1)
        constraint_penalty = 0.1 * max(0, len(constraints) - len(idea_words & set(" ".join(constraints).lower().split())))
        return max(0.1, min(0.95, 0.4 + 0.5 * overlap - constraint_penalty))

    def _estimate_feasibility(self, idea: str, constraints: list[str]) -> float:
        """Estimate how feasible the idea is to implement."""
        base = 0.6
        if len(idea.split()) > 50:
            base -= 0.1  # complex ideas are harder
        if constraints:
            base -= 0.05 * len(constraints)  # more constraints = harder
        return max(0.2, min(0.95, base))

    def _min_distance_to_known(self, concept: ConceptVector) -> float:
        """
        min_k ||z - z_known_k||²
        Approximated by novelty_seed distance in feature space.
        """
        if not self.known_solutions:
            return 1.0  # maximum distance — all is novel
        seed = concept.features.get("novelty_seed", 0.5)
        distances = [
            abs(seed - k.features.get("novelty_seed", 0.5))
            for k in self.known_solutions
        ]
        return min(distances)

    def _register_known_solution(self, concept: ConceptVector) -> None:
        self.known_solutions.append(concept)
        if len(self.known_solutions) > 100:
            self.known_solutions.pop(0)

    def to_dict(self) -> dict:
        mode_counts = {}
        for m in self.mode_history:
            mode_counts[m.value] = mode_counts.get(m.value, 0) + 1
        return {
            "interaction_count": self.interaction_count,
            "known_solutions": len(self.known_solutions),
            "mode_history_counts": mode_counts,
            "current_oscillation_phase": round(
                (2 * math.pi * self.interaction_count) / T_CREATIVE, 4
            ),
        }
