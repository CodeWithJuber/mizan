"""
Curated registry of research findings from the Mizan Quran computational-
linguistics study.

Each Finding carries an EpistemicLabel that encodes the Mizan principle:
*structure describes, transmission legislates*.  The label reflects the
epistemic status of the claim — how well-evidenced it is — NOT its
theological or literary importance.

Null results (is_null=True) are first-class findings.  A null result means
the study ran a rigorous test and found no effect; that is a positive
scientific contribution, not a failure or omission.

Labels:
  Established  — multiple independent converging tests, effect robust
  Inference    — solid evidence but depends on modelling choices / register
  Conjecture   — plausible framing, not yet tested quantitatively
  Open         — question posed, evidence ambiguous or missing

Imports: stdlib + pydantic only.  No pandas/numpy/scipy/sklearn/
matplotlib/networkx.
"""

from functools import lru_cache

from research.schemas import EpistemicLabel, Finding


@lru_cache(maxsize=1)
def get_registry() -> tuple[Finding, ...]:
    """Return the immutable curated registry of research findings."""
    return (
        Finding(
            id="meccan_medinan",
            title="Meccan vs Medinan predictable from vocabulary",
            epistemic_label="Established",
            is_null=False,
            summary=(
                "A vocabulary-based classifier achieves AUC 0.816 on a balanced "
                "Meccan/Medinan split; a robust re-run on tighter labels reaches "
                "AUC 0.967.  Permutation p-value 0.002 confirms the result is not "
                "a chance artefact."
            ),
            key_numbers={"auc_vocab": 0.816, "perm_p": 0.002, "auc_robust": 0.967},
            results_file="meccan_medinan_results",
            figures=["meccan_medinan.png", "auc_explainer.png"],
        ),
        Finding(
            id="compositional_meaning",
            title="Meaning is ~43% structural (root + wazn)",
            epistemic_label="Established",
            is_null=False,
            summary=(
                "Root identity alone explains 38.3% of variance in distributed "
                "meaning representations (R²=0.383); adding morphological pattern "
                "(wazn) raises this to 43.0% (R²=0.430), a Δ of 4.7 pp."
            ),
            key_numbers={"r2_root": 0.383, "r2_root_wazn": 0.430, "delta_wazn": 0.047},
            results_file="compositional",
            figures=["compositional.png"],
        ),
        Finding(
            id="context_null",
            title="Same-verse neighbour-root context adds nothing (this setup)",
            epistemic_label="Established",
            is_null=True,
            summary=(
                "Adding same-verse neighbour-root context to the compositional "
                "model changes R² by −0.008 — a null result under this experimental "
                "setup.  Context may matter in other configurations."
            ),
            key_numbers={"delta_context": -0.008},
            results_file="compositional",
            figures=["compositional.png"],
        ),
        Finding(
            id="generative_grid",
            title="Root x wazn is a sparse generative grid",
            epistemic_label="Established",
            is_null=False,
            summary=(
                "The Quran lexicon spans 1456 roots × 565 morphological patterns "
                "(wuzun), filling only 0.45% of possible root–pattern slots.  "
                "The top 20% of patterns account for 47% of attested words."
            ),
            key_numbers={
                "roots": 1456,
                "patterns": 565,
                "fill_pct": 0.45,
                "top20_pct": 47,
            },
            results_file="algebra_phase1",
            figures=["algebra_phase1.png"],
        ),
        Finding(
            id="sound_meaning_mantel",
            title="Sound to lexical meaning, global test: NULL",
            epistemic_label="Established",
            is_null=True,
            summary=(
                "A Mantel test of the correlation between phonological distance "
                "and semantic distance across all Quran roots returns r=0.010, "
                "p=0.512 — a clear null result at the global level."
            ),
            key_numbers={"mantel_r": 0.010, "p": 0.512},
            results_file="letter_math",
            figures=["letter_math.png"],
        ),
        Finding(
            id="sound_meaning_pockets",
            title="Sound to lexical meaning, local test: NULL",
            epistemic_label="Established",
            is_null=True,
            summary=(
                "A local pocket-hunt (FWER-controlled at 0.05) finds 0 surviving "
                "sound–meaning clusters.  The strongest candidate has z=4.23 but "
                "corrected p=0.247 after multiple-comparison correction."
            ),
            key_numbers={
                "survivors": 0,
                "fwer": 0.05,
                "strongest_z": 4.23,
                "corrected_p": 0.247,
            },
            results_file="pocket_hunt",
            figures=["pocket_hunt.png"],
        ),
        Finding(
            id="wajh_detector",
            title="Context disambiguates polysemous words (rule-based, hand-validated)",
            epistemic_label="Established",
            is_null=False,
            summary=(
                "A rule-based wajh (semantic face) detector achieves 96% accuracy "
                "on dīn and 100% on ummah, validated against hand-labelled "
                "occurrences.  Demonstrates that immediate verse context is "
                "sufficient for disambiguation."
            ),
            key_numbers={"deen_acc": 0.96, "ummah_acc": 1.0},
            results_file="wajh_detector",
            figures=["wajh_detector.png", "nazair_deen.png"],
        ),
        Finding(
            id="six_laws",
            title="Quran is a linguistically normal corpus",
            epistemic_label="Established",
            is_null=False,
            summary=(
                "Six standard corpus linguistics laws (Zipf, Heaps, Brevity, etc.) "
                "were tested; 4 of 6 hold, 2 are rejected.  The Quran behaves as a "
                "normal natural-language corpus under standard metrics."
            ),
            key_numbers={"laws_total": 6, "laws_rejected": 2},
            results_file="laws_results",
            figures=["analysis_laws.png", "zipf.png"],
        ),
        Finding(
            id="root_embeddings",
            title=(
                "Root embeddings recover semantic fields "
                "(light/fire collapse at root, separate at lemma)"
            ),
            epistemic_label="Established",
            is_null=False,
            summary=(
                "SVD embeddings (k=50) trained on Quran co-occurrence recover "
                "interpretable semantic fields.  Roots for light and fire cluster "
                "together at the root level but separate correctly at the lemma "
                "level — validating the root-as-semantic-attractor hypothesis."
            ),
            key_numbers={"svd_k": 50},
            results_file="embeddings_results",
            figures=["embeddings_map.png", "lemma_embeddings_map.png", "top_roots.png"],
        ),
        Finding(
            id="surah_order",
            title="Sura ordering has mild positive content-structure",
            epistemic_label="Established",
            is_null=False,
            summary=(
                "Mantel tests show a mild positive correlation between sura "
                "content similarity and both mushaf order (r=0.308) and "
                "chronological order (r=0.303).  The ordering is non-random "
                "but not strongly determined by content alone."
            ),
            key_numbers={"mantel_mushaf": 0.308, "mantel_chrono": 0.303},
            results_file="surah_order",
            figures=["surah_order.png"],
        ),
        Finding(
            id="register_baselines",
            title="Frequency exponents are register- and unit-dependent",
            epistemic_label="Inference",
            is_null=False,
            summary=(
                "Baseline frequency-rank exponents vary across registers (Quran, "
                "Hadith, poetry, Tabari) and across units (forms, lemmas, roots).  "
                "Any comparison must control for both register and unit definition."
            ),
            key_numbers={},
            results_file="baselines_multi",
            figures=["baselines_multi.png", "baseline_sizematched.png"],
        ),
        Finding(
            id="letter_features",
            title="28-letter articulatory feature space (Jakobson binary oppositions)",
            epistemic_label="Established",
            is_null=False,
            summary=(
                "Arabic's 28 letters are described by 15 binary Jakobson-style "
                "articulatory features, spanning place, manner, and voicing "
                "dimensions.  This feature space is the foundation for all "
                "sound–meaning and phonological distance analyses."
            ),
            key_numbers={"features_per_letter": 15},
            results_file="letter_math",
            figures=["letter_math.png"],
        ),
        Finding(
            id="grand_vision",
            title=(
                "Primordial-Arabic / letters-carry-meaning / "
                "reality-in-pairs (the original intuition)"
            ),
            epistemic_label="Conjecture",
            is_null=False,
            summary=(
                "The founding intuition of the Mizan project: that Quranic Arabic "
                "encodes meaning at the level of individual letters; that root "
                "families form a generative 'primordial' system; that reality is "
                "structured in complementary pairs (azwāj).  These ideas motivate "
                "the study but are not yet quantitatively tested."
            ),
            key_numbers={},
            results_file=None,
            figures=["system_architecture.png"],
        ),
    )
