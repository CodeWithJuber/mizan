"""
Shūrā Council — Multi-Agent Consultation Architecture
======================================================

"And those who conduct their affairs by shūrā (mutual consultation)
 among themselves" — Quran 42:38

"And consult them in the matter" — Quran 3:159

Implements the SHURA_COUNCIL_MEETING algorithm:
1. Agenda setting (Qalb broadcasts problem)
2. Independent analysis (parallel, NO groupthink)
3. Proposal presentation (round-robin)
4. Cross-examination (agents challenge each other)
5. Integration (Lubb synthesis)
6. Dissent recording (Lawwāma function)
7. Knowledge sharing (post-meeting learning)

Also implements AGENT_KNOWLEDGE_SHARING for continuous inter-agent learning.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("mizan.shura")


class ProposalStatus(Enum):
    PENDING = "pending"
    PRESENTED = "presented"
    CHALLENGED = "challenged"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass
class AgentProposal:
    """A single agent's proposal in a Shūrā meeting."""
    agent_id: str
    agent_name: str
    expertise_domain: str
    solution: str
    reasoning: str
    confidence: float
    evidence: list[str]
    score: float = 0.0
    weaknesses: list[str] = field(default_factory=list)
    status: ProposalStatus = ProposalStatus.PENDING


@dataclass
class Challenge:
    """A challenge from one agent to another's proposal."""
    challenger_id: str
    target_proposal_agent: str
    critique: str
    severity: float     # 0.0 - 1.0
    valid: bool = True


@dataclass
class Rebuttal:
    """A defense against a challenge."""
    defender_id: str
    challenge_critique: str
    defense: str
    strength: float    # 0.0 - 1.0
    valid: bool = True


@dataclass
class DissentRecord:
    """Records disagreement for future reference."""
    agent_id: str
    agent_name: str
    alternative_proposal: str
    reasoning: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class MeetingResult:
    """Full result of a Shūrā council meeting."""
    meeting_id: str
    problem: str
    decision: str
    decision_source: str    # "synthesis" or agent_name
    confidence: float
    proposals: list[AgentProposal]
    dissent_records: list[DissentRecord]
    knowledge_shared: int
    meeting_duration_ms: float


@dataclass
class KnowledgePackage:
    """Packaged knowledge for sharing between agents."""
    source_agent: str
    target_agent: str
    content: str
    domain: str
    relevance: float
    timestamp: float = field(default_factory=time.time)


class ShuraCouncil:
    """
    SHURA_COUNCIL_MEETING algorithm implementation.

    Manages formal multi-agent deliberation sessions with:
    - Independent parallel analysis (prevents groupthink)
    - Cross-examination (stress-tests proposals)
    - Weighted synthesis (not majority vote — expertise-weighted)
    - Dissent recording (minority views preserved for future correction)
    - Post-meeting knowledge sharing (agents learn from each other)
    """

    def __init__(self):
        self.meeting_history: list[MeetingResult] = []
        self.dissent_archive: list[DissentRecord] = []
        self.knowledge_inbox: dict[str, list[KnowledgePackage]] = {}
        self.expertise_profiles: dict[str, dict[str, float]] = {}

    def convene(
        self,
        problem: str,
        agents: list[dict],
        context: dict | None = None,
    ) -> MeetingResult:
        """
        Run a full Shūrā council meeting.

        agents: list of {"id", "name", "expertise", "evaluate_fn" (optional)}

        Steps:
        1. Agenda broadcast
        2. Independent analysis (parallel)
        3. Proposal presentation
        4. Cross-examination
        5. Integration
        6. Dissent recording
        7. Knowledge sharing
        """
        meeting_id = str(uuid.uuid4())[:8]
        start = time.monotonic()

        # Step 1: Agenda setting
        logger.info("[SHURA] Meeting %s convened: %s", meeting_id, problem[:80])

        # Step 2: Independent analysis (each agent generates a proposal)
        proposals = []
        for agent in agents:
            proposal = self._generate_proposal(agent, problem, context)
            proposals.append(proposal)

        # Step 3: Proposal presentation (score by expertise relevance)
        proposals.sort(
            key=lambda p: self._expertise_relevance(p.expertise_domain, problem),
            reverse=True,
        )
        for proposal in proposals:
            proposal.status = ProposalStatus.PRESENTED

        # Step 4: Cross-examination
        self._cross_examine(proposals, problem)

        # Step 5: Integration — weighted scoring + synthesis attempt
        decision, decision_source, confidence = self._integrate(proposals, problem)

        # Step 6: Dissent recording
        dissent_records = []
        for proposal in proposals:
            if proposal.solution != decision:
                record = DissentRecord(
                    agent_id=proposal.agent_id,
                    agent_name=proposal.agent_name,
                    alternative_proposal=proposal.solution,
                    reasoning=proposal.reasoning,
                )
                dissent_records.append(record)
                self.dissent_archive.append(record)

        # Step 7: Knowledge sharing
        shared = self._share_knowledge(proposals, agents)

        elapsed_ms = (time.monotonic() - start) * 1000

        result = MeetingResult(
            meeting_id=meeting_id,
            problem=problem,
            decision=decision,
            decision_source=decision_source,
            confidence=confidence,
            proposals=proposals,
            dissent_records=dissent_records,
            knowledge_shared=shared,
            meeting_duration_ms=round(elapsed_ms, 2),
        )
        self.meeting_history.append(result)

        logger.info(
            "[SHURA] Meeting %s concluded: source=%s confidence=%.2f dissents=%d",
            meeting_id, decision_source, confidence, len(dissent_records),
        )
        return result

    def _generate_proposal(
        self, agent: dict, problem: str, context: dict | None
    ) -> AgentProposal:
        """
        Each agent independently analyzes the problem.
        In production, this calls the agent's LLM evaluate function.
        """
        agent_id = agent.get("id", "unknown")
        name = agent.get("name", "Agent")
        expertise = agent.get("expertise", "general")

        # Expertise-based confidence heuristic
        relevance = self._expertise_relevance(expertise, problem)
        confidence = 0.4 + 0.5 * relevance  # base + expertise boost

        # Generate proposal text (placeholder — LLM call in production)
        solution = (
            f"[{expertise.upper()} perspective] "
            f"Approach to '{problem[:60]}' "
            f"using {expertise} principles"
        )
        reasoning = (
            f"Based on {expertise} analysis: "
            f"relevance={relevance:.2f}, "
            f"confidence={confidence:.2f}"
        )
        evidence = [f"{expertise}_analysis", f"domain_knowledge_{expertise}"]

        return AgentProposal(
            agent_id=agent_id,
            agent_name=name,
            expertise_domain=expertise,
            solution=solution,
            reasoning=reasoning,
            confidence=round(confidence, 3),
            evidence=evidence,
            score=confidence * relevance,
        )

    def _cross_examine(self, proposals: list[AgentProposal], problem: str) -> None:
        """
        Agents challenge each other's proposals.
        Score adjustments: valid challenge reduces score, valid rebuttal partially recovers.
        """
        for i, proposal in enumerate(proposals):
            for j, challenger_source in enumerate(proposals):
                if i == j:
                    continue

                # Generate challenge based on expertise difference
                challenge = self._generate_challenge(
                    challenger_source, proposal, problem
                )
                if not challenge:
                    continue

                if challenge.valid:
                    proposal.score -= challenge.severity * 0.2
                    proposal.weaknesses.append(challenge.critique)

                    # Allow rebuttal
                    rebuttal = self._generate_rebuttal(proposal, challenge)
                    if rebuttal and rebuttal.valid:
                        proposal.score += rebuttal.strength * 0.1  # partial recovery

            proposal.status = ProposalStatus.CHALLENGED

    def _generate_challenge(
        self, challenger: AgentProposal, target: AgentProposal, problem: str
    ) -> Challenge | None:
        """Generate a challenge from one agent to another's proposal."""
        # Only challenge if domains differ (cross-domain critique is more valuable)
        if challenger.expertise_domain == target.expertise_domain:
            return None

        # Heuristic: challenge strength based on challenger's confidence
        severity = 0.2 + 0.3 * challenger.confidence

        # Identify potential weakness based on expertise gap
        critique = (
            f"{challenger.expertise_domain} perspective: "
            f"'{target.expertise_domain}' approach may miss "
            f"{challenger.expertise_domain}-specific considerations"
        )

        return Challenge(
            challenger_id=challenger.agent_id,
            target_proposal_agent=target.agent_id,
            critique=critique,
            severity=round(severity, 3),
            valid=severity > 0.3,  # only valid if substantive
        )

    def _generate_rebuttal(
        self, defender: AgentProposal, challenge: Challenge
    ) -> Rebuttal | None:
        """Defender responds to a challenge."""
        # Rebuttal strength proportional to evidence quality
        strength = min(0.8, 0.3 + 0.1 * len(defender.evidence))

        defense = (
            f"Rebuttal: {defender.expertise_domain} approach accounts for "
            f"the raised concern through {defender.evidence[0] if defender.evidence else 'general analysis'}"
        )

        return Rebuttal(
            defender_id=defender.agent_id,
            challenge_critique=challenge.critique,
            defense=defense,
            strength=round(strength, 3),
            valid=strength > 0.4,
        )

    def _integrate(
        self, proposals: list[AgentProposal], problem: str
    ) -> tuple[str, str, float]:
        """
        Integration: NOT majority vote — weighted by expertise and evidence quality.

        final_score = expertise_weight × confidence × evidence_quality × (1 - weaknesses)

        Attempt synthesis (combine best elements). If synthesis > best individual, use it.
        """
        if not proposals:
            return "No proposals generated", "none", 0.0

        # Score each proposal
        for proposal in proposals:
            expertise_weight = self._expertise_relevance(
                proposal.expertise_domain, problem
            )
            evidence_quality = min(1.0, 0.5 + 0.1 * len(proposal.evidence))
            weakness_penalty = min(0.5, 0.1 * len(proposal.weaknesses))

            proposal.score = (
                expertise_weight
                * proposal.confidence
                * evidence_quality
                * (1.0 - weakness_penalty)
            )

        # Best individual proposal
        best = max(proposals, key=lambda p: p.score)

        # Attempt synthesis: combine elements from top proposals
        top_proposals = sorted(proposals, key=lambda p: p.score, reverse=True)[:3]
        synthesis = self._synthesize(top_proposals, problem)
        synthesis_score = sum(p.score for p in top_proposals) / len(top_proposals) * 1.1

        if synthesis_score > best.score:
            confidence = min(0.95, synthesis_score)
            return synthesis, "synthesis", round(confidence, 3)
        else:
            best.status = ProposalStatus.ACCEPTED
            return best.solution, best.agent_name, round(best.score, 3)

    def _synthesize(self, proposals: list[AgentProposal], problem: str) -> str:
        """Combine best elements of multiple proposals into synthesis."""
        elements = []
        for proposal in proposals:
            key_element = proposal.solution.split("]")[-1].strip()[:80]
            if key_element:
                elements.append(f"[{proposal.expertise_domain}] {key_element}")
        return f"Synthesis for '{problem[:40]}': " + " + ".join(elements[:3])

    def _share_knowledge(
        self, proposals: list[AgentProposal], agents: list[dict]
    ) -> int:
        """Post-meeting knowledge sharing: each agent learns from others."""
        shared = 0
        for proposal in proposals:
            for agent in agents:
                target_id = agent.get("id", "")
                if target_id == proposal.agent_id:
                    continue  # don't share with self

                relevance = self._cross_domain_relevance(
                    proposal.expertise_domain,
                    agent.get("expertise", "general"),
                )
                if relevance > 0.3:
                    package = KnowledgePackage(
                        source_agent=proposal.agent_id,
                        target_agent=target_id,
                        content=proposal.reasoning[:200],
                        domain=proposal.expertise_domain,
                        relevance=relevance,
                    )
                    if target_id not in self.knowledge_inbox:
                        self.knowledge_inbox[target_id] = []
                    self.knowledge_inbox[target_id].append(package)
                    shared += 1

        return shared

    def get_inbox(self, agent_id: str) -> list[KnowledgePackage]:
        """Get pending knowledge packages for an agent."""
        return self.knowledge_inbox.pop(agent_id, [])

    def search_meeting_history(self, query: str, limit: int = 5) -> list[MeetingResult]:
        """Search past meetings by problem text."""
        query_words = set(query.lower().split())
        scored = []
        for meeting in self.meeting_history:
            problem_words = set(meeting.problem.lower().split())
            overlap = len(query_words & problem_words)
            if overlap > 0:
                scored.append((meeting, overlap))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [m for m, _ in scored[:limit]]

    def get_dissents_for(self, problem_query: str) -> list[DissentRecord]:
        """Find dissent records related to a query (may prove right later)."""
        results = []
        query_words = set(problem_query.lower().split())
        for record in self.dissent_archive:
            alt_words = set(record.alternative_proposal.lower().split())
            if len(query_words & alt_words) > 1:
                results.append(record)
        return results

    def update_expertise(self, agent_id: str, domain: str, score: float) -> None:
        """Track and update expertise profiles over time."""
        if agent_id not in self.expertise_profiles:
            self.expertise_profiles[agent_id] = {}
        # Exponential moving average
        alpha = 0.2
        current = self.expertise_profiles[agent_id].get(domain, 0.5)
        self.expertise_profiles[agent_id][domain] = (
            alpha * score + (1 - alpha) * current
        )

    def _expertise_relevance(self, expertise: str, problem: str) -> float:
        """How relevant is an expertise domain to the problem?"""
        # Simple keyword overlap heuristic
        expertise_words = set(expertise.lower().split("_"))
        problem_words = set(problem.lower().split())
        if not expertise_words:
            return 0.5
        overlap = len(expertise_words & problem_words)
        return min(1.0, 0.3 + 0.3 * overlap)

    def _cross_domain_relevance(self, domain_a: str, domain_b: str) -> float:
        """How relevant is knowledge from domain_a to domain_b?"""
        if domain_a == domain_b:
            return 0.9  # same domain = highly relevant
        # Cross-domain pairs that benefit each other
        synergies = {
            frozenset({"reasoning", "planning"}): 0.7,
            frozenset({"creativity", "reasoning"}): 0.6,
            frozenset({"memory", "reasoning"}): 0.7,
            frozenset({"language", "social"}): 0.6,
            frozenset({"perception", "creativity"}): 0.5,
        }
        pair = frozenset({domain_a.lower(), domain_b.lower()})
        return synergies.get(pair, 0.35)

    def measure_collective_intelligence(self) -> dict:
        """Measure collective IQ: total knowledge × diversity ÷ redundancy."""
        if not self.meeting_history:
            return {"collective_iq": 0, "meetings": 0}

        unique_domains = set()
        total_proposals = 0
        for meeting in self.meeting_history:
            for proposal in meeting.proposals:
                unique_domains.add(proposal.expertise_domain)
                total_proposals += 1

        diversity = len(unique_domains)
        # Estimate redundancy from repeated similar proposals
        redundancy = max(1, total_proposals - diversity * len(self.meeting_history))

        collective_iq = (total_proposals * diversity) / redundancy
        return {
            "collective_iq": round(collective_iq, 2),
            "meetings": len(self.meeting_history),
            "unique_domains": diversity,
            "total_proposals": total_proposals,
            "dissent_records": len(self.dissent_archive),
        }

    def to_dict(self) -> dict:
        return {
            "meetings_held": len(self.meeting_history),
            "dissents_archived": len(self.dissent_archive),
            "knowledge_inbox_agents": len(self.knowledge_inbox),
            "expertise_profiles": len(self.expertise_profiles),
        }
