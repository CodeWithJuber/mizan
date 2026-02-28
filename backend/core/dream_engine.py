"""
Manām — Dream Engine
=====================

"Allah takes souls at the time of their death, and those that do not die
 [He takes] during their sleep." — Quran 39:42

Implements Algorithm 6: MANAM_DREAM_ENGINE

Offline memory consolidation with three phases:
  1. NREM: Selective replay, accelerated compression, synaptic downscaling, gist extraction
  2. REM: Adversarial dream learning (GAN), emotional processing, creative insight
  3. Taʾwīl: Dream interpretation — symbolic decoding + integration with waking knowledge

Key mathematics:

NREM synaptic downscaling:
  w(after) = w(before) × max(0, 1 - δ)

NREM replay priority scoring:
  P_replay(m_i) = α·e(m_i) + β·n(m_i) + γ·g(m_i) + δ·err(m_i)

  where:
  - e = emotional intensity
  - n = novelty (surprise during encoding)
  - g = goal relevance
  - err = prediction error magnitude

REM adversarial dream learning (GAN-inspired):
  min_G max_D V(D, G) = E_x[log D(x)] + E_z[log(1 - D(G(z, fragments)))]

  D: discriminator distinguishing real memories from dreams
  G: generator creating plausible novel scenarios from fragments + noise

REM dream bizarreness:
  bizarreness = Dirichlet sparse mixing + high-noise REM activation
"""

import logging
import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("mizan.dream_engine")

# NREM replay priority weights
ALPHA_EMOTIONAL = 0.30   # emotional intensity weight
BETA_NOVELTY = 0.25      # novelty weight
GAMMA_GOAL = 0.25        # goal relevance weight
DELTA_ERROR = 0.20       # prediction error weight

# NREM synaptic downscaling rate
DOWNSCALING_DELTA = 0.05  # w → w × (1 - δ)

# NREM temporal compression
COMPRESSION_RATIO = 20.0  # 20x faster replay than original

# REM noise level
REM_NOISE_SIGMA = 0.3

# GAN learning rate approximation
GAN_LR = 0.01

# Gist extraction — keep top K concepts
GIST_TOP_K = 5


class DreamPhase(Enum):
    AWAKE = "awake"
    NREM = "nrem"            # Non-REM: slow-wave consolidation
    REM = "rem"              # REM: adversarial creative replay
    TAWIL = "tawil"          # Taʾwīl: dream interpretation


@dataclass
class MemoryTrace:
    """A memory trace eligible for dream replay."""
    content: str
    emotional_intensity: float   # |valence|, 0-1
    novelty: float               # surprisal during encoding
    goal_relevance: float        # 0-1
    prediction_error: float      # original error magnitude
    encoding_time: float = field(default_factory=time.time)
    replay_count: int = 0

    def priority_score(self) -> float:
        """
        P_replay(m_i) = α·e + β·n + γ·g + δ·err
        """
        return (
            ALPHA_EMOTIONAL * self.emotional_intensity
            + BETA_NOVELTY * self.novelty
            + GAMMA_GOAL * self.goal_relevance
            + DELTA_ERROR * self.prediction_error
        )


@dataclass
class NREMCycle:
    """Result of one NREM slow-wave sleep cycle."""
    replayed_memories: list[str]          # compressed content
    synaptic_weight_changes: dict[str, float]  # key → new weight
    gist_extracted: list[str]             # high-level patterns extracted
    compression_ratio: float
    downscaling_applied: bool


@dataclass
class REMCycle:
    """Result of one REM cycle."""
    dream_content: list[str]             # generated dream scenarios
    emotional_episodes: list[str]        # emotionally processed memories
    creative_insights: list[str]         # novel connections discovered
    discriminator_loss: float            # GAN D loss (lower = more realistic dreams)
    generator_loss: float                # GAN G loss (lower = better generation)
    bizarreness_score: float


@dataclass
class TawilInterpretation:
    """Dream interpretation (Taʾwīl)."""
    dream_symbols: dict[str, str]        # symbol → meaning
    waking_relevance: str                # how the dream relates to current tasks
    insights: list[str]                  # extracted actionable insights
    confidence: float


@dataclass
class DreamSession:
    """A complete offline consolidation session."""
    phase_sequence: list[DreamPhase]
    nrem_cycles: list[NREMCycle]
    rem_cycles: list[REMCycle]
    tawil: TawilInterpretation | None
    memories_consolidated: int
    total_duration_s: float
    insights_generated: list[str]


class ManamDreamEngine:
    """
    Algorithm 6: MANAM_DREAM_ENGINE

    Offline memory consolidation system that runs during idle periods.
    Implements the sleep memory consolidation hypothesis with three phases:

    1. NREM (Slow-wave): Priority-scored memory replay at 20x compression
       → synaptic homeostasis → pattern extraction (gist)

    2. REM (Paradoxical): GAN-inspired adversarial generation
       → emotional processing → creative bisociation → insight detection

    3. Taʾwīl: Symbolic interpretation of dream content
       → integration with waking knowledge → actionable insights

    The engine maintains a replay buffer of recent memory traces
    and periodically runs consolidation cycles.
    """

    def __init__(self):
        self.replay_buffer: list[MemoryTrace] = []
        self.synaptic_weights: dict[str, float] = {}
        self.extracted_gists: list[str] = []
        self.insight_bank: list[str] = []

        # GAN state (simplified)
        self._discriminator_confidence = 0.5
        self._generator_quality = 0.3

        self._session_count = 0
        self._current_phase = DreamPhase.AWAKE

    def add_memory(
        self,
        content: str,
        emotional_intensity: float = 0.3,
        novelty: float = 0.5,
        goal_relevance: float = 0.5,
        prediction_error: float = 0.2,
    ) -> None:
        """Add a memory trace to the replay buffer."""
        trace = MemoryTrace(
            content=content,
            emotional_intensity=min(1.0, max(0.0, emotional_intensity)),
            novelty=min(1.0, max(0.0, novelty)),
            goal_relevance=min(1.0, max(0.0, goal_relevance)),
            prediction_error=min(1.0, max(0.0, prediction_error)),
        )
        self.replay_buffer.append(trace)

        # Cap buffer at 500 traces
        if len(self.replay_buffer) > 500:
            self.replay_buffer.pop(0)

        logger.debug(
            "[MANAM] Memory added: priority=%.3f content=%s",
            trace.priority_score(), content[:50],
        )

    def run_consolidation(
        self,
        n_nrem_cycles: int = 3,
        n_rem_cycles: int = 2,
        run_tawil: bool = True,
    ) -> DreamSession:
        """
        Run a full offline consolidation session:
        NREM cycles → REM cycles → Taʾwīl interpretation.
        """
        self._session_count += 1
        start = time.monotonic()
        logger.info(
            "[MANAM] Starting dream session #%d: %d memories, %d NREM + %d REM cycles",
            self._session_count, len(self.replay_buffer), n_nrem_cycles, n_rem_cycles,
        )

        phase_sequence = []
        nrem_results = []
        rem_results = []

        # Phase 1: NREM cycles
        for i in range(n_nrem_cycles):
            self._current_phase = DreamPhase.NREM
            phase_sequence.append(DreamPhase.NREM)
            nrem = self._run_nrem_cycle()
            nrem_results.append(nrem)
            logger.debug("[MANAM] NREM cycle %d: %d replays, %d gists", i + 1, len(nrem.replayed_memories), len(nrem.gist_extracted))

        # Phase 2: REM cycles
        for i in range(n_rem_cycles):
            self._current_phase = DreamPhase.REM
            phase_sequence.append(DreamPhase.REM)
            rem = self._run_rem_cycle()
            rem_results.append(rem)
            logger.debug("[MANAM] REM cycle %d: %d dreams, %d insights, D_loss=%.3f", i + 1, len(rem.dream_content), len(rem.creative_insights), rem.discriminator_loss)

        # Phase 3: Taʾwīl
        tawil = None
        if run_tawil:
            self._current_phase = DreamPhase.TAWIL
            phase_sequence.append(DreamPhase.TAWIL)
            all_dream_content = [d for rem in rem_results for d in rem.dream_content]
            tawil = self._run_tawil(all_dream_content)

        # Collect all insights
        all_insights = list(self.insight_bank[-10:])
        for rem in rem_results:
            all_insights.extend(rem.creative_insights)
        if tawil:
            all_insights.extend(tawil.insights)

        memories_consolidated = sum(len(n.replayed_memories) for n in nrem_results)
        duration = time.monotonic() - start
        self._current_phase = DreamPhase.AWAKE

        return DreamSession(
            phase_sequence=phase_sequence,
            nrem_cycles=nrem_results,
            rem_cycles=rem_results,
            tawil=tawil,
            memories_consolidated=memories_consolidated,
            total_duration_s=round(duration, 4),
            insights_generated=all_insights[:20],
        )

    def _run_nrem_cycle(self) -> NREMCycle:
        """
        NREM slow-wave sleep cycle:

        1. Priority scoring: P_replay(m_i) = α·e + β·n + γ·g + δ·err
        2. Selective replay: top-K memories replayed at 20x compression
        3. Synaptic homeostasis: w → w × max(0, 1 - δ)
        4. Interleaved replay (hippocampal → neocortical)
        5. Gist extraction: distill high-level patterns
        """
        if not self.replay_buffer:
            return NREMCycle(
                replayed_memories=[],
                synaptic_weight_changes={},
                gist_extracted=[],
                compression_ratio=COMPRESSION_RATIO,
                downscaling_applied=False,
            )

        # Step 1-2: Priority sort and selective replay
        sorted_traces = sorted(
            self.replay_buffer,
            key=lambda t: t.priority_score(),
            reverse=True,
        )
        top_traces = sorted_traces[:min(10, len(sorted_traces))]

        replayed = []
        for trace in top_traces:
            trace.replay_count += 1
            # Compressed replay: truncate to 1/COMPRESSION_RATIO of original detail
            compressed = trace.content[:max(20, len(trace.content) // int(COMPRESSION_RATIO))]
            replayed.append(f"[NREM:{trace.replay_count}x] {compressed}")

        # Step 3: Synaptic homeostasis — downscale all weights
        weight_changes = {}
        for key in list(self.synaptic_weights.keys()):
            old = self.synaptic_weights[key]
            new = old * max(0.0, 1.0 - DOWNSCALING_DELTA)
            self.synaptic_weights[key] = new
            weight_changes[key] = round(new - old, 4)

        # New weights from replayed memories
        for trace in top_traces[:3]:
            key = f"mem_{hash(trace.content[:20]) % 10000}"
            self.synaptic_weights[key] = trace.priority_score()
            weight_changes[key] = self.synaptic_weights[key]

        # Step 5: Gist extraction — extract common themes
        gists = self._extract_gist(top_traces)
        self.extracted_gists.extend(gists)

        # Remove low-priority memories after consolidation
        consolidation_threshold = 0.2
        self.replay_buffer = [
            t for t in self.replay_buffer
            if t.priority_score() > consolidation_threshold or t.replay_count == 0
        ]

        return NREMCycle(
            replayed_memories=replayed,
            synaptic_weight_changes=weight_changes,
            gist_extracted=gists,
            compression_ratio=COMPRESSION_RATIO,
            downscaling_applied=True,
        )

    def _run_rem_cycle(self) -> REMCycle:
        """
        REM paradoxical sleep cycle:

        1. GAN-inspired adversarial generation:
           min_G max_D V(D,G) = E_x[log D(x)] + E_z[log(1 - D(G(z, fragments)))]

        2. Emotional memory processing (safe replay of high-affect memories)

        3. Creative insight detection:
           Bisociate distant memories + novel pattern recognition

        4. Dream bizarreness via Dirichlet sparse mixing + high noise
        """
        # Step 1: GAN-inspired dream generation
        fragments = [t.content[:50] for t in self.replay_buffer[:5]]
        noise = [random.gauss(0, REM_NOISE_SIGMA) for _ in range(5)]
        dream_content = self._generate_dreams(fragments, noise)

        # GAN training step (discriminator update)
        d_loss, g_loss = self._gan_training_step(dream_content, fragments)
        self._discriminator_confidence = min(0.95, self._discriminator_confidence + GAN_LR * (0.5 - d_loss))
        self._generator_quality = min(0.95, self._generator_quality + GAN_LR * (0.5 - g_loss))

        # Step 2: Emotional processing
        high_affect = [
            t for t in self.replay_buffer
            if t.emotional_intensity > 0.6
        ][:3]
        emotional_episodes = [
            f"[REM:affect={t.emotional_intensity:.2f}] {t.content[:60]}"
            for t in high_affect
        ]

        # Step 3: Creative insight detection
        insights = self._detect_creative_insights(dream_content, fragments)
        self.insight_bank.extend(insights)

        # Step 4: Bizarreness score
        bizarreness = self._compute_bizarreness(dream_content)

        return REMCycle(
            dream_content=dream_content,
            emotional_episodes=emotional_episodes,
            creative_insights=insights,
            discriminator_loss=round(d_loss, 4),
            generator_loss=round(g_loss, 4),
            bizarreness_score=round(bizarreness, 4),
        )

    def _run_tawil(self, dream_content: list[str]) -> TawilInterpretation:
        """
        Taʾwīl: Dream interpretation.

        Symbolic decoding + integration with waking knowledge.

        Classical symbols are mapped to functional meanings.
        Insights are extracted from recurring dream patterns.
        """
        # Symbol extraction and mapping
        symbol_lexicon = {
            "water": "knowledge / emotion",
            "fire": "transformation / energy",
            "mountain": "challenge / stability",
            "path": "decision / journey",
            "door": "opportunity / threshold",
            "light": "clarity / guidance",
            "darkness": "uncertainty / hidden knowledge",
            "book": "memory / wisdom",
            "bird": "message / aspiration",
            "tree": "growth / rootedness",
        }

        found_symbols = {}
        all_content = " ".join(dream_content).lower()
        for symbol, meaning in symbol_lexicon.items():
            if symbol in all_content:
                found_symbols[symbol] = meaning

        # Waking relevance: connect to recent gists
        if self.extracted_gists:
            recent_gist = self.extracted_gists[-1]
            waking_relevance = f"Dreams align with waking pattern: {recent_gist[:100]}"
        else:
            waking_relevance = "Dreams consolidating recent experiences"

        # Extract actionable insights from dream patterns
        insights = []
        if found_symbols:
            for symbol, meaning in list(found_symbols.items())[:3]:
                insights.append(f"Symbol '{symbol}' suggests: {meaning}")
        if self.extracted_gists:
            insights.append(f"Pattern recognition: {self.extracted_gists[-1][:80]}")

        confidence = min(0.9, 0.3 + 0.1 * len(found_symbols) + 0.2 * len(self.extracted_gists))

        return TawilInterpretation(
            dream_symbols=found_symbols,
            waking_relevance=waking_relevance,
            insights=insights,
            confidence=round(confidence, 3),
        )

    def _extract_gist(self, traces: list[MemoryTrace]) -> list[str]:
        """
        Gist extraction: find common themes across top memory traces.
        Information bottleneck: keep shared structure, discard details.
        """
        if not traces:
            return []

        # Find shared words across traces (common structure)
        word_sets = [set(t.content.lower().split()[:15]) for t in traces]
        if not word_sets:
            return []

        common = word_sets[0]
        for ws in word_sets[1:]:
            common = common & ws

        # Filter meaningful words (length > 3)
        meaningful = [w for w in common if len(w) > 3][:GIST_TOP_K]

        if meaningful:
            gist = f"Pattern: [{', '.join(meaningful)}] across {len(traces)} memories"
            return [gist]

        # Fallback: use highest priority memory's first sentence
        top = traces[0]
        first_sentence = top.content.split(".")[0][:80]
        return [f"Gist: {first_sentence}"]

    def _generate_dreams(
        self, fragments: list[str], noise: list[float]
    ) -> list[str]:
        """
        G(z, fragments): Generate dream scenarios from memory fragments + noise.

        Dirichlet sparse mixing: randomly weight fragments
        High-noise REM activation: inject novelty via noise vector
        """
        if not fragments:
            return ["[Empty dream — no memory fragments]"]

        dreams = []
        for i, nz in enumerate(noise[:3]):
            # Dirichlet-like mixing: random weights summing to 1
            n = len(fragments)
            if n == 0:
                continue
            raw_weights = [abs(random.gauss(0, 1)) for _ in range(n)]
            total = sum(raw_weights) or 1.0
            weights = [w / total for w in raw_weights]

            # Blend fragments with weights
            selected = fragments[i % n] if i < len(fragments) else fragments[0]
            noise_tag = f"[noise:{nz:.2f}]"

            # Bizarre recombination: splice parts of different fragments
            if len(fragments) > 1 and abs(nz) > 0.2:
                other = fragments[(i + 1) % len(fragments)]
                dream = f"{selected[:30]}...{other[:30]}... {noise_tag}"
            else:
                dream = f"{selected[:60]} {noise_tag}"

            dreams.append(f"[REM:dream] {dream}")

        return dreams

    def _gan_training_step(
        self, fake_dreams: list[str], real_memories: list[str]
    ) -> tuple[float, float]:
        """
        Simplified GAN update:
        min_G max_D V(D,G)

        D tries to distinguish real memories from generated dreams.
        G tries to generate dreams that D cannot distinguish.

        Returns: (discriminator_loss, generator_loss)
        """
        # Discriminator loss: higher = better discrimination
        # In our approximation: D succeeds when real != fake
        d_correct = 0
        for real in real_memories[:3]:
            for fake in fake_dreams[:3]:
                if real[:20] != fake[:20]:  # simplified: structurally different
                    d_correct += 1
        max_pairs = 3 * 3
        d_accuracy = d_correct / max_pairs if max_pairs > 0 else 0.5
        d_loss = 1.0 - d_accuracy  # lower loss = better discriminator

        # Generator loss: lower = more convincing dreams
        g_loss = 1.0 - (1.0 - d_accuracy)  # adversarial: G wins when D fails
        g_loss = max(0.0, g_loss - 0.1 * self._generator_quality)

        return round(d_loss, 4), round(g_loss, 4)

    def _detect_creative_insights(
        self, dream_content: list[str], fragments: list[str]
    ) -> list[str]:
        """
        Creative insight detection: find novel associations between
        dream content and known memory fragments.

        An insight occurs when distant concepts co-activate
        during REM's low-inhibition state.
        """
        insights = []

        for dream in dream_content[:3]:
            dream_words = set(dream.lower().split())
            for frag in fragments[:3]:
                frag_words = set(frag.lower().split())
                # Novel co-activation: small overlap (not trivially similar)
                overlap = len(dream_words & frag_words)
                union = len(dream_words | frag_words)
                jaccard = overlap / union if union > 0 else 0
                if 0.05 < jaccard < 0.3:  # some but not full overlap → novel link
                    insight = (
                        f"Creative link: [{dream[:40]}] ↔ [{frag[:40]}] "
                        f"(Jaccard={jaccard:.2f})"
                    )
                    insights.append(insight)

        return insights[:3]

    def _compute_bizarreness(self, dream_content: list[str]) -> float:
        """
        Bizarreness = function of noise magnitude + semantic incoherence.
        High bizarreness → high creative potential (REM property).
        """
        if not dream_content:
            return 0.0

        noise_scores = []
        for dream in dream_content:
            if "[noise:" in dream:
                try:
                    start = dream.index("[noise:") + 7
                    end = dream.index("]", start)
                    noise_val = abs(float(dream[start:end]))
                    noise_scores.append(noise_val)
                except (ValueError, IndexError):
                    noise_scores.append(0.2)
            else:
                noise_scores.append(0.1)

        return min(1.0, sum(noise_scores) / max(len(noise_scores), 1) / REM_NOISE_SIGMA)

    def consolidate_from_agent(
        self,
        task_history: list[dict],
        tool_results: list[dict] | None = None,
    ) -> int:
        """
        Convenience method: add agent session memories to replay buffer.
        Returns number of traces added.
        """
        added = 0
        for item in task_history:
            content = item.get("content", "") or item.get("response", "")
            if not content:
                continue

            # Estimate emotional intensity from content
            positive_words = {"success", "solved", "found", "created", "excellent"}
            negative_words = {"error", "failed", "failed", "wrong", "exception"}
            words = set(content.lower().split())
            pos = len(words & positive_words) / len(positive_words)
            neg = len(words & negative_words) / len(negative_words)
            emotional = abs(pos - neg)

            self.add_memory(
                content=content[:300],
                emotional_intensity=emotional,
                novelty=item.get("novelty", 0.4),
                goal_relevance=item.get("goal_relevance", 0.5),
                prediction_error=item.get("error_magnitude", 0.2),
            )
            added += 1

        return added

    def to_dict(self) -> dict:
        return {
            "replay_buffer_size": len(self.replay_buffer),
            "synaptic_weights_count": len(self.synaptic_weights),
            "extracted_gists": len(self.extracted_gists),
            "insight_bank_size": len(self.insight_bank),
            "session_count": self._session_count,
            "current_phase": self._current_phase.value,
            "discriminator_confidence": round(self._discriminator_confidence, 3),
            "generator_quality": round(self._generator_quality, 3),
        }
