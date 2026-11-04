"""
Pydantic v2 data models for the research integration layer.

These models import ONLY stdlib + pydantic.  No pandas/numpy/scipy/sklearn/
matplotlib/networkx — those heavy deps belong to pipeline scripts only.

EpistemicLabel encodes the Mizan principle: structure describes, transmission
legislates.  The four labels reflect epistemic status, not importance; null
results (is_null=True) are first-class findings, not errors or failures.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

# ── Epistemic Label ──────────────────────────────────────────────────────────

EpistemicLabel = Literal["Established", "Inference", "Conjecture", "Open"]


# ── Permissive envelope for heterogeneous result JSONs ────────────────────────


class ResultEnvelope(BaseModel):
    """
    Loose wrapper around any experiment result JSON.

    The 17 result files have heterogeneous structures, so we use extra="allow"
    to validate loosely rather than writing a per-file strict model.  Consumers
    can access arbitrary fields via model.model_extra or model.__dict__.
    """

    model_config = ConfigDict(extra="allow")


# ── Curated finding ───────────────────────────────────────────────────────────


class Finding(BaseModel):
    """A single curated research finding with epistemic metadata."""

    id: str
    title: str
    epistemic_label: EpistemicLabel
    is_null: bool = False
    summary: str
    key_numbers: dict[str, str | float | int]
    results_file: str | None = None
    figures: list[str]
    related_routes: list[str] = []


# ── Corpus data-shape models ──────────────────────────────────────────────────
# Used later by corpus loader and API endpoints.  All fields are Optional with
# defaults so partial rows validate without errors.


class WordRecord(BaseModel):
    """One row of quran_words.csv.  44 columns; BOM stripped before parsing."""

    model_config = ConfigDict(extra="ignore")

    # Integer fields
    gidx: int | None = None
    sura: int | None = None
    aya: int | None = None
    n_seg: int | None = None
    n_letters: int | None = None
    freq_form: int | None = None
    freq_norm: int | None = None
    freq_lemma: int | None = None
    freq_root: int | None = None

    # Float fields
    energy_info_norm: float | None = None
    energy_info_lemma: float | None = None
    energy_info_root: float | None = None
    root_degree: float | None = None
    root_wdegree: float | None = None
    root_clustering: float | None = None
    root_eigcent: float | None = None
    root_pagerank: float | None = None
    abjad_form: float | None = None
    abjad_root: float | None = None

    # String fields
    loc: str | None = None
    word: str | None = None
    form: str | None = None
    translit: str | None = None
    word_en: str | None = None
    skeleton: str | None = None
    norm: str | None = None
    root: str | None = None
    root_translit: str | None = None
    root_en: str | None = None
    root_en_here: str | None = None
    lemma: str | None = None
    pos: str | None = None
    prev_form: str | None = None
    prev_en: str | None = None
    prev_root: str | None = None
    prev_pos: str | None = None
    next_form: str | None = None
    next_en: str | None = None
    next_root: str | None = None
    next_pos: str | None = None
    crosses_verse_prev: str | None = None
    crosses_verse_next: str | None = None
    collocate_roots: str | None = None
    collocate_en: str | None = None


class RootSummary(BaseModel):
    """One row of roots_summary.csv.  14 columns."""

    model_config = ConfigDict(extra="ignore")

    root: str | None = None
    translit: str | None = None
    buckwalter: str | None = None
    meaning_en: str | None = None
    top_glosses_en: str | None = None
    abjad: float | None = None
    freq: int | None = None
    info: float | None = None
    n_letters: int | None = None
    degree: float | None = None
    wdegree: float | None = None
    clustering: float | None = None
    eigcent: float | None = None
    pagerank: float | None = None


class WajhOccurrence(BaseModel):
    """One row of wajh_*_tagged.csv.  Columns: verse,sura,aya,word,prev,nxt,face,confidence,basis."""

    model_config = ConfigDict(extra="ignore")

    verse: str | None = None
    sura: int | None = None
    aya: int | None = None
    word: str | None = None
    prev: str | None = None
    nxt: str | None = None
    face: str | None = None
    confidence: float | None = None
    basis: str | None = None
