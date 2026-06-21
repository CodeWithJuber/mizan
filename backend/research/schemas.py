"""
Pydantic v2 data models for the research integration layer.

These models import ONLY stdlib + pydantic.  No pandas/numpy/scipy/sklearn/
matplotlib/networkx — those heavy deps belong to pipeline scripts only.

EpistemicLabel encodes the Mizan principle: structure describes, transmission
legislates.  The four labels reflect epistemic status, not importance; null
results (is_null=True) are first-class findings, not errors or failures.
"""

from typing import Literal, Optional

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
    results_file: Optional[str] = None
    figures: list[str]
    related_routes: list[str] = []


# ── Corpus data-shape models ──────────────────────────────────────────────────
# Used later by corpus loader and API endpoints.  All fields are Optional with
# defaults so partial rows validate without errors.


class WordRecord(BaseModel):
    """One row of quran_words.csv.  44 columns; BOM stripped before parsing."""

    model_config = ConfigDict(extra="ignore")

    # Integer fields
    gidx: Optional[int] = None
    sura: Optional[int] = None
    aya: Optional[int] = None
    n_seg: Optional[int] = None
    n_letters: Optional[int] = None
    freq_form: Optional[int] = None
    freq_norm: Optional[int] = None
    freq_lemma: Optional[int] = None
    freq_root: Optional[int] = None

    # Float fields
    energy_info_norm: Optional[float] = None
    energy_info_lemma: Optional[float] = None
    energy_info_root: Optional[float] = None
    root_degree: Optional[float] = None
    root_wdegree: Optional[float] = None
    root_clustering: Optional[float] = None
    root_eigcent: Optional[float] = None
    root_pagerank: Optional[float] = None
    abjad_form: Optional[float] = None
    abjad_root: Optional[float] = None

    # String fields
    loc: Optional[str] = None
    word: Optional[str] = None
    form: Optional[str] = None
    translit: Optional[str] = None
    word_en: Optional[str] = None
    skeleton: Optional[str] = None
    norm: Optional[str] = None
    root: Optional[str] = None
    root_translit: Optional[str] = None
    root_en: Optional[str] = None
    root_en_here: Optional[str] = None
    lemma: Optional[str] = None
    pos: Optional[str] = None
    prev_form: Optional[str] = None
    prev_en: Optional[str] = None
    prev_root: Optional[str] = None
    prev_pos: Optional[str] = None
    next_form: Optional[str] = None
    next_en: Optional[str] = None
    next_root: Optional[str] = None
    next_pos: Optional[str] = None
    crosses_verse_prev: Optional[str] = None
    crosses_verse_next: Optional[str] = None
    collocate_roots: Optional[str] = None
    collocate_en: Optional[str] = None


class RootSummary(BaseModel):
    """One row of roots_summary.csv.  14 columns."""

    model_config = ConfigDict(extra="ignore")

    root: Optional[str] = None
    translit: Optional[str] = None
    buckwalter: Optional[str] = None
    meaning_en: Optional[str] = None
    top_glosses_en: Optional[str] = None
    abjad: Optional[float] = None
    freq: Optional[int] = None
    info: Optional[float] = None
    n_letters: Optional[int] = None
    degree: Optional[float] = None
    wdegree: Optional[float] = None
    clustering: Optional[float] = None
    eigcent: Optional[float] = None
    pagerank: Optional[float] = None


class WajhOccurrence(BaseModel):
    """One row of wajh_*_tagged.csv.  Columns: verse,sura,aya,word,prev,nxt,face,confidence,basis."""

    model_config = ConfigDict(extra="ignore")

    verse: Optional[str] = None
    sura: Optional[int] = None
    aya: Optional[int] = None
    word: Optional[str] = None
    prev: Optional[str] = None
    nxt: Optional[str] = None
    face: Optional[str] = None
    confidence: Optional[float] = None
    basis: Optional[str] = None
