"""
QCA Answer Engine — Full 7-Layer Question Answering Pipeline
=============================================================

Routes every question through the complete QCA cognitive pipeline:
  Sam' + Basar -> Fu'ad -> ISM -> Mizan -> 'Aql -> Lawh -> Furqan/Bayan

Integrates with MIZAN's existing AqlEngine for multi-turn reasoning
and DhikrMemorySystem for persistent storage.

"Say, are those who know equal to those who do not know?" — Quran 39:9
"""

import logging
import re
import time

from qca.engine import (
    AqlLayer,
    FurqanBayan,
    ISMLayer,
    LawhMemory,
    MizanLayer,
    QCAEngine,
)

logger = logging.getLogger("mizan.qca.answer")


class QCAAnswerEngine:
    """
    Full QCA pipeline for answering questions about any input.
    Routes each question through all 7 layers, maintains session memory,
    and integrates with MIZAN's existing reasoning infrastructure.

    Usage:
        engine = QCAAnswerEngine()
        engine.load_paragraph("Your text here")
        result = engine.answer("What does this discuss?")
    """

    def __init__(self, qca: QCAEngine = None):
        self.qca = qca or QCAEngine()
        self.current_paragraph = ""
        self.paragraph_analysis = {}
        self.session_memory: list[dict] = []

    @property
    def lawh(self) -> LawhMemory:
        return self.qca.lawh

    @property
    def mizan(self) -> MizanLayer:
        return self.qca.mizan

    @property
    def aql(self) -> AqlLayer:
        return self.qca.aql

    @property
    def ism(self) -> ISMLayer:
        return self.qca.ism

    @property
    def furqan(self) -> FurqanBayan:
        return self.qca.furqan

    def load_paragraph(self, text: str) -> dict:
        """Process a paragraph through all QCA input layers."""
        self.current_paragraph = text
        analysis = self.qca.process_input(text)
        self.paragraph_analysis = {
            "perception": analysis["perception"],
            "fuad": analysis["perception"]["fuad"],
            "roots": analysis["roots_identified"],
            "sentences": re.split(r"[.!?]+", text),
            "word_count": len(text.split()),
        }
        return analysis["perception"]["fuad"]

    def answer(self, question: str, paragraph: str = None) -> dict:
        """
        Full QCA pipeline answer to a question. All 7 layers invoked.

        Pipeline:
        1. Sam' + Basar + Fu'ad: Parse question and find relevant context
        2. ISM: Map English concepts to Arabic roots
        3. Lawh: Search memory tiers for relevant knowledge
        4. 'Aql: Trace causal chains through binding graph
        5. Mizan: Compute overall epistemic confidence
        6. Furqan/Bayan: Validate and articulate response
        """
        if paragraph:
            self.load_paragraph(paragraph)

        if not self.current_paragraph:
            return {"error": "No paragraph loaded. Please provide a paragraph first."}

        answer_parts = []
        confidence_scores = []
        sources = []

        # ── FU'AD ANALYSIS ──────────────────────────────────
        fuad = self.paragraph_analysis.get("fuad", {})
        key_terms = fuad.get("key_terms", [])
        sentences = self.paragraph_analysis.get("sentences", [self.current_paragraph])

        # ── LAYER 1+2+3: Find relevant sentences in paragraph ──
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
        else:
            answer_parts.append("The paragraph discusses: {}.".format(", ".join(key_terms[:5])))
            confidence_scores.append(0.5)
            sources.append("fuad_inference")

        # ── LAYER 4: ISM — Arabic root concepts ─────────────
        combined = question + " " + self.current_paragraph
        roots_found = self.ism.find_roots_in_text(combined)
        if roots_found:
            root_insights = []
            for r in roots_found[:3]:
                if r["meaning"]:
                    insight = "[{}] '{}' carries the deep meaning: \"{}\"".format(
                        r["root"], r["english_term"], r["meaning"][:60]
                    )
                    root_insights.append(insight)
            if root_insights:
                answer_parts.append("QCA Root Analysis: " + " | ".join(root_insights))
                confidence_scores.append(0.9)
                sources.append("ism_root_analysis")

        # ── LAYER 7: LAWH — Check memory tiers ──────────────
        memory_results = self.lawh.search(question, top_k=3, tiers=[1, 2])
        quran_refs_used = []
        for score, key, entry in memory_results:
            if score >= 2 and entry.get("content"):
                if key.startswith("Q"):
                    ref_text = 'Quran {}: "{}"'.format(key[1:], entry["content"][:80])
                    if entry.get("arabic"):
                        ref_text += " | Arabic: {}".format(entry["arabic"][:40])
                    quran_refs_used.append(ref_text)
                    sources.append("lawh_tier{}".format(entry["tier"]))
        if quran_refs_used:
            answer_parts.append("Quranic references: " + " | ".join(quran_refs_used[:2]))
            confidence_scores.append(0.95)

        # ── LAYER 6: 'AQL BINDING TRACE ──────────────────────
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

        # ── LAYER 5: MIZAN — Compute overall confidence ─────
        if confidence_scores:
            overall_confidence = sum(confidence_scores) / len(confidence_scores)
        else:
            overall_confidence = 0.5

        furqan_report = self.furqan.validate_and_express(
            " ".join(answer_parts[:2]),
            overall_confidence,
            source=sources[0] if sources else "inference",
        )

        # ── STORE IN TIER 3 MEMORY ──────────────────────────
        session_entry = {
            "question": question,
            "confidence": overall_confidence,
            "sources": sources,
            "timestamp": time.time(),
        }
        self.session_memory.append(session_entry)
        self.lawh.store(
            f"SESSION_Q{len(self.session_memory)}",
            question + " -> " + (answer_parts[0] if answer_parts else "no answer"),
            certainty=overall_confidence,
            source="session",
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

    def batch_answer(self, questions: list[str], paragraph: str = None) -> list[dict]:
        """Answer multiple questions about the same paragraph."""
        if paragraph:
            self.load_paragraph(paragraph)
        return [self.answer(q) for q in questions]

    def get_session_summary(self) -> dict:
        """Get a summary of the current session's Q&A history."""
        if not self.session_memory:
            return {"questions_asked": 0, "avg_confidence": 0}
        avg_conf = sum(e["confidence"] for e in self.session_memory) / len(self.session_memory)
        return {
            "questions_asked": len(self.session_memory),
            "avg_confidence": avg_conf,
            "epistemic_label": self.mizan.rate_confidence_string(avg_conf),
            "sources_used": list(set(s for e in self.session_memory for s in e.get("sources", []))),
            "lawh_stats": self.lawh.stats(),
        }

    def reset_session(self):
        """Clear session memory (Tier 3) but preserve axioms and verified knowledge."""
        self.current_paragraph = ""
        self.paragraph_analysis = {}
        self.session_memory.clear()
        self.lawh.tiers[3].clear()
