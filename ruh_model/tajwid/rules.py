"""Tajwīd rules engine — text-based analysis for Ḥafṣ ʿan ʿĀṣim.

Pure stdlib (no torch): safe to load by file path in minimal installs.

Scope (honest):
- Input: Arabic text WITH diacritics (tashkīl). Rules that need vowels/sukūn
  only fire where the marks are present. Undiacritized text returns
  ``status: "needs_diacritics"`` — the engine never guesses vowels.
- Default qirāʾah: Ḥafṣ ʿan ʿĀṣim min ṭarīq ash-Shāṭibiyyah. Where a rule
  differs in Warsh (or has jawāz al-wajhayn), the annotation carries a
  ``qiraat_note``; Warsh-specific VALUES are not computed (lā taqfu — no
  invented rulings).
- This is a *text* rules engine, not the ASR "Tajwīd Buddy" of
  ``scaffold.py`` (that bridge is still unproven and untouched).

Rule sources: al-Muqaddimah al-Jazariyyah (Ibn al-Jazarī),
Tuḥfat al-Aṭfāl (al-Jamzūrī), ash-Shāṭibiyyah (ash-Shāṭibī) — cited per
rule at topic level.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "RULES",
    "QIRAAT_DEFAULT",
    "analyze_text",
    "get_rule_catalog",
    "strip_diacritics",
]

QIRAAT_DEFAULT = "hafs"

# ---------------------------------------------------------------------------
# Unicode constants
# ---------------------------------------------------------------------------

# Diacritics (combining marks)
FATHATAN = "ً"  # U+064B
DAMMATAN = "ٌ"  # U+064C
KASRATAN = "ٍ"  # U+064D
FATHA = "َ"  # U+064E
DAMMA = "ُ"  # U+064F
KASRA = "ِ"  # U+0650
SHADDA = "ّ"  # U+0651
SUKUN = "ْ"  # U+0652
MADDAH = "ٓ"  # U+0653
SUP_ALEF = "ٰ"  # U+0670 superscript alef (alif khanjariyyah)
ALEF_WASLA = "ٱ"  # U+0671
TATWEEL = "ـ"  # U+0640

TANWIN_MARKS = {FATHATAN, DAMMATAN, KASRATAN}
HARAKAH_MARKS = {FATHA, DAMMA, KASRA}

MARK_NAMES = {
    FATHATAN: "tanwin_fath",
    DAMMATAN: "tanwin_damm",
    KASRATAN: "tanwin_kasr",
    FATHA: "fatha",
    DAMMA: "damma",
    KASRA: "kasra",
    SHADDA: "shadda",
    SUKUN: "sukun",
    MADDAH: "maddah",
    SUP_ALEF: "sup_alef",
}

# Hamzah carriers → canonical hamzah for rule matching
HAMZAH_FORMS = {"أ": "ء", "إ": "ء", "ؤ": "ء", "ئ": "ء", "ء": "ء"}
# U+0622 ALEF WITH MADDAH ABOVE expands to hamzah + madd-alif
ALEF_MADDAH = "آ"

# ---------------------------------------------------------------------------
# Classical letter sets
# ---------------------------------------------------------------------------

# Ḥurūf al-ḥalq (throat letters) — iẓhār
HALQ = {"ء", "ه", "ع", "ح", "غ", "خ"}
# Ḥurūf al-idghām bi-ghunnah (yanmū)
IDGHAM_GHUNNAH = {"ي", "ن", "م", "و"}
IDGHAM_GHUNNAH_KAMIL = {"ن", "م"}  # complete assimilation
# Ḥurūf al-idghām bi-ghayr ghunnah
IDGHAM_NO_GHUNNAH = {"ل", "ر"}
# Iqlāb
IQLAB = {"ب"}
# Ḥurūf al-ikhfāʾ (15)
IKHFA = {"ت", "ث", "ج", "د", "ذ", "ز", "س", "ش", "ص", "ض", "ط", "ظ", "ف", "ق", "ك"}
# Ḥurūf al-qalqalah (qaṭb jad)
QALQALAH = {"ق", "ط", "ب", "ج", "د"}
# Ḥurūf al-istiʿlāʾ (khaṣṣa ḍaghṭin qiẓ) — always mufakhkham
ISTILA = {"خ", "ص", "ض", "غ", "ط", "ق", "ظ"}
# Solar / lunar letters for lām at-taʿrīf
SUN = {"ت", "ث", "د", "ذ", "ر", "ز", "س", "ش", "ص", "ض", "ط", "ظ", "ل", "ن"}
MOON = {"ء", "ب", "ج", "ح", "خ", "ع", "غ", "ف", "ق", "ك", "م", "ه", "و", "ي"}
# The four words of iẓhār muṭlaq (nūn + yāʾ/wāw inside one word → no idghām)
IZHAR_MUTLAQ_WORDS = {"دنيا", "بنيان", "صنوان", "قنوان"}
# Sakt pairs in Ḥafṣ (bare-letter form): (word1, word2)
SAKT_PAIRS = {
    ("من", "راق"),  # 75:27 — blocks idghām nūn→rāʾ
    ("بل", "ران"),  # 83:14 — blocks assimilation lām→rāʾ
    ("عوجا", "قيم"),  # 18:1-2 — blocks ikhfāʾ of tanwīn
    ("ماليه", "هلك"),  # 69:28-29 — blocks idghām mithlayn
}
# Muqaṭṭaʿāt openings (bare form)
MUQATTAAT = {
    "الم",
    "المر",
    "المص",
    "الر",
    "كهيعص",
    "طه",
    "طسم",
    "طس",
    "يس",
    "ص",
    "حم",
    "عسق",
    "ق",
    "ن",
}
# Ḥarfī madd breakdown: 6-count (naqṣ ʿasalukum), 2-count (ḥayy ṭāhir), ʿayn jawāz
HARFI_SIX = {"ن", "ق", "ص", "ل", "م", "س", "ك"}
HARFI_TWO = {"ح", "ي", "ط", "ه", "ر"}
# yarmalūn minus nūn/mīm — nāqiṣ ghunnah
IDGHAM_GHUNNAH_NAQIS = {"ي", "و"}

_JAZ = "al-Muqaddimah al-Jazariyyah (Ibn al-Jazarī)"
_TUHFA = "Tuḥfat al-Aṭfāl (al-Jamzūrī)"
_SHAT = "ash-Shāṭibiyyah (ash-Shāṭibī)"


@dataclass
class Rule:
    """One tajwīd rule in the catalog."""

    rule_id: str
    name_ar: str
    name_en: str
    category: str
    description: str
    counts: str | None = None
    sources: tuple[str, ...] = ()
    qiraat_notes: tuple[str, ...] = ()


RULES: dict[str, Rule] = {}


def _r(rule_id, name_ar, name_en, category, description, counts=None, sources=(), qiraat_notes=()):
    RULES[rule_id] = Rule(
        rule_id,
        name_ar,
        name_en,
        category,
        description,
        counts,
        tuple(sources),
        tuple(qiraat_notes),
    )


# -- Nūn sākinah & tanwīn ----------------------------------------------------
_r(
    "nun_izhar",
    "الإظهار",
    "Iẓhār",
    "nun_sakinah",
    "Nūn sākinah/tanwīn before a throat letter (ء ه ع ح غ خ): pronounced clearly, no ghunnah.",
    sources=[f"{_JAZ}, bāb aḥkām an-nūn as-sākinah wa-t-tanwīn", _TUHFA],
)
_r(
    "nun_idgham_ghunnah",
    "الإدغام بغنة",
    "Idghām bi-ghunnah",
    "nun_sakinah",
    "Nūn sākinah/tanwīn before ي ن م و (across a word boundary): "
    "merged with ghunnah. Kāmil (complete) with ن م; nāqiṣ (ghunnah remains) with ي و.",
    sources=[f"{_JAZ}, bāb aḥkām an-nūn as-sākinah wa-t-tanwīn", _TUHFA],
)
_r(
    "nun_idgham_no_ghunnah",
    "الإدغام بغير غنة",
    "Idghām bi-ghayr ghunnah",
    "nun_sakinah",
    "Nūn sākinah/tanwīn before ل ر: merged with no ghunnah.",
    sources=[f"{_JAZ}, bāb aḥkām an-nūn as-sākinah wa-t-tanwīn", _TUHFA],
)
_r(
    "nun_iqlab",
    "الإقلاب",
    "Iqlāb",
    "nun_sakinah",
    "Nūn sākinah/tanwīn before ب: converted to a concealed mīm with ghunnah.",
    sources=[f"{_JAZ}, bāb aḥkām an-nūn as-sākinah wa-t-tanwīn", _TUHFA],
)
_r(
    "nun_ikhfa",
    "الإخفاء",
    "Ikhfāʾ",
    "nun_sakinah",
    "Nūn sākinah/tanwīn before the 15 ikhfāʾ letters "
    "(ت ث ج د ذ ز س ش ص ض ط ظ ف ق ك): concealed with ghunnah — mufakhkhamah "
    "before istiʿlāʾ letters, muraqqaqah otherwise.",
    sources=[f"{_JAZ}, bāb aḥkām an-nūn as-sākinah wa-t-tanwīn", _TUHFA],
)
_r(
    "nun_izhar_mutlaq",
    "الإظهار المطلق",
    "Iẓhār muṭlaq",
    "nun_sakinah",
    "Nūn sākinah before ي/و INSIDE one word (الدنيا، بنيان، "
    "صنوان، قنوان): pronounced clearly — idghām is blocked to preserve meaning.",
    sources=[f"{_JAZ}, bāb aḥkām an-nūn as-sākinah wa-t-tanwīn"],
)
# -- Ghunnah -----------------------------------------------------------------
_r(
    "ghunnah_mushaddad",
    "الغنة",
    "Ghunnah (mushaddad)",
    "ghunnah",
    "Nūn/mīm mushaddadah (نّ / مّ): ghunnah, 2 counts — akmal (fullest).",
    "2",
    sources=[f"{_JAZ}, bāb aḥkām an-nūn wa-l-mīm al-mushaddadatayn"],
)
# -- Mīm sākinah --------------------------------------------------------------
_r(
    "mim_ikhfa",
    "الإخفاء الشفوي",
    "Ikhfāʾ shafawī",
    "mim_sakinah",
    "Mīm sākinah before ب: concealed with ghunnah.",
    sources=[f"{_JAZ}, bāb aḥkām al-mīm as-sākinah", _TUHFA],
)
_r(
    "mim_idgham",
    "إدغام المثلين الصغير",
    "Idghām mithlayn ṣaghīr",
    "mim_sakinah",
    "Mīm sākinah before م: merged with ghunnah.",
    sources=[f"{_JAZ}, bāb aḥkām al-mīm as-sākinah", _TUHFA],
)
_r(
    "mim_izhar",
    "الإظهار الشفوي",
    "Iẓhār shafawī",
    "mim_sakinah",
    "Mīm sākinah before any other letter: pronounced clearly. "
    "Extra care before و and ف (similar makhraj).",
    sources=[f"{_JAZ}, bāb aḥkām al-mīm as-sākinah", _TUHFA],
)
# -- Madd --------------------------------------------------------------------
_r(
    "madd_tabi",
    "المد الطبيعي",
    "Madd ṭabīʿī",
    "madd",
    "Natural elongation, 2 counts: alif after fatḥah, wāw sākinah after "
    "ḍammah, yāʾ sākinah after kasrah — with no hamzah or sukūn after it.",
    "2",
    sources=[f"{_JAZ}, bāb al-madd wa-l-qaṣr", _TUHFA, _SHAT],
)
_r(
    "madd_muttasil",
    "المد المتصل",
    "Madd muttaṣil",
    "madd",
    "Madd letter followed by hamzah in the SAME word: 4–5 counts (ṭūl).",
    "4-5",
    sources=[f"{_JAZ}, bāb al-madd wa-l-qaṣr", _SHAT],
    qiraat_notes=["Warsh: 6 (ishbāʿ) via most ṭuruq; Ḥafṣ: 4–5."],
)
_r(
    "madd_munfasil",
    "المد المنفصل",
    "Madd munfaṣil",
    "madd",
    "Madd letter at end of a word, hamzah (qaṭʿ) at the start of the "
    "next word: 4–5 counts (ṭūl) in Ḥafṣ.",
    "4-5",
    sources=[f"{_JAZ}, bāb al-madd wa-l-qaṣr", _SHAT],
    qiraat_notes=["Warsh: 6 (ishbāʿ) via most ṭuruq; Ḥafṣ: 4–5 (ṭūl)."],
)
_r(
    "madd_badal",
    "مد البدل",
    "Madd badal",
    "madd",
    "Hamzah followed by a madd letter (e.g. آمَنُوا): 2 counts in Ḥafṣ.",
    "2",
    sources=[f"{_JAZ}, bāb al-madd wa-l-qaṣr"],
    qiraat_notes=["Warsh: 2/4/6 (qaṣr/tawassuṭ/ṭūl); Ḥafṣ: 2 (qaṣr)."],
)
_r(
    "madd_lazim_kalimi",
    "المد اللازم الكلمي",
    "Madd lāzim kalimī",
    "madd",
    "Madd letter followed by a permanent sukūn in a word (shaddah → "
    "muthaqqal, e.g. الضَّالِّين; sukūn → mukhaffaf, e.g. آلْآنَ): 6 counts.",
    "6",
    sources=[f"{_JAZ}, bāb al-madd wa-l-qaṣr", _SHAT],
)
_r(
    "madd_lazim_harfi",
    "المد اللازم الحرفي",
    "Madd lāzim ḥarfī",
    "madd",
    "In the muqaṭṭaʿāt openings: letters of نقص عسلكم → 6 counts; "
    "ʿayn → 4 or 6 (jawāz); letters of حي طهر → 2 counts (ṭabīʿī ḥarfī); "
    "alif → no madd.",
    "6",
    sources=[f"{_JAZ}, bāb al-madd wa-l-qaṣr", _SHAT],
)
_r(
    "madd_arid",
    "المد العارض للسكون",
    "Madd ʿāriḍ li-s-sukūn",
    "madd",
    "Madd letter followed by a letter made sākin by stopping (waqf): "
    "2, 4 or 6 counts. Annotated at word-final madd+consonant positions — "
    "applies on waqf; in waṣl it is ṭabīʿī.",
    "2/4/6",
    sources=[f"{_JAZ}, bāb al-madd wa-l-qaṣr"],
)
_r(
    "madd_lin",
    "مد اللين",
    "Madd līn",
    "madd",
    "Wāw/yāʾ sākinah preceded by fatḥah, followed by a letter made "
    "sākin by stopping: 2, 4 or 6 counts on waqf (no madd in waṣl).",
    "2/4/6",
    sources=[f"{_JAZ}, bāb al-madd wa-l-qaṣr"],
)
_r(
    "madd_silah_sughra",
    "مد الصلة الصغرى",
    "Madd ṣilah ṣughrā",
    "madd",
    "Hāʾ al-ḍamīr (ـهُ/ـهِ) preceded by a vowelled letter: lengthened "
    "2 counts. Blocked in يَرْضَهُ (39:7, istiṯnāʾ). Verse-specific exception "
    "not applied by the engine: فِيهِ مُهَانًا (25:69) takes ṣilah despite the "
    "sākin — needs verse context.",
    "2",
    sources=[f"{_JAZ}, bāb al-madd wa-l-qaṣr", _SHAT],
)
_r(
    "madd_silah_kubra",
    "مد الصلة الكبرى",
    "Madd ṣilah kubrā",
    "madd",
    "Hāʾ al-ḍamīr followed by hamzah (qaṭʿ): 4–5 counts, like munfaṣil.",
    "4-5",
    sources=[f"{_JAZ}, bāb al-madd wa-l-qaṣr", _SHAT],
)
_r(
    "madd_iwad",
    "مد العوض",
    "Madd ʿiwaḍ",
    "madd",
    "Tanwīn fatḥah on a word-final alif (e.g. رِزْقًا): on waqf the "
    "tanwīn becomes a madd alif, 2 counts (no madd in waṣl).",
    "2",
    sources=[f"{_JAZ}, bāb al-madd wa-l-qaṣr"],
)
# -- Qalqalah -----------------------------------------------------------------
_r(
    "qalqalah_sughra",
    "القلقلة الصغرى",
    "Qalqalah ṣughrā",
    "qalqalah",
    "Qaṭb-jad letter (ق ط ب ج د) with sukūn mid-word: light echo.",
    sources=[f"{_JAZ}, bāb ṣifāt al-ḥurūf"],
)
_r(
    "qalqalah_kubra",
    "القلقلة الكبرى",
    "Qalqalah kubrā",
    "qalqalah",
    "Qaṭb-jad letter at a stop (waqf): stronger echo. Annotated at "
    "word-final qalqalah letters — applies on waqf.",
    sources=[f"{_JAZ}, bāb ṣifāt al-ḥurūf"],
)
# -- Tafkhīm / tarqīq ----------------------------------------------------------
_r(
    "ra_tafkhim",
    "تفخيم الراء",
    "Tafkhīm ar-rāʾ",
    "tafkheem_tarqeeq",
    "Rāʾ is heavy: with fatḥah/ḍammah; sākinah after "
    "fatḥah/ḍammah; after an ʿāriḍ kasrah (hamzat waṣl); or sākinah after a "
    "lāzim kasrah but followed by an istiʿlāʾ letter in the same word.",
    sources=[f"{_JAZ}, bāb aḥkām ar-rāʾ", _SHAT],
)
_r(
    "ra_tarqeeq",
    "ترقيق الراء",
    "Tarqīq ar-rāʾ",
    "tafkheem_tarqeeq",
    "Rāʾ is light: with kasrah; sākinah after a lāzim kasrah; or sākinah after yāʾ sākinah.",
    sources=[f"{_JAZ}, bāb aḥkām ar-rāʾ", _SHAT],
    qiraat_notes=[
        "Warsh raqqaqa ar-rāʾ more broadly (e.g. after kasrah "
        "lāzimah even before istiʿlāʾ in some positions)."
    ],
)
_r(
    "ra_jawaz",
    "جواز الوجهين في الراء",
    "Jawāz al-wajhayn (rāʾ)",
    "tafkheem_tarqeeq",
    "Both tafkhīm and tarqīq allowed: فِرْقٍ (tarqīq "
    "preferred), مِصْرَ on waqf (tafkhīm preferred), الْقِطْرِ on waqf "
    "(tarqīq preferred).",
    sources=[f"{_JAZ}, bāb aḥkām ar-rāʾ"],
)
_r(
    "lam_jalalah_tafkhim",
    "تفخيم لام الجلالة",
    "Tafkhīm lām al-jalālah",
    "tafkheem_tarqeeq",
    "Lām of الله is heavy after fatḥah/ḍammah (or at start).",
    sources=[f"{_JAZ}, bāb al-lāmāt"],
)
_r(
    "lam_jalalah_tarqeeq",
    "ترقيق لام الجلالة",
    "Tarqīq lām al-jalālah",
    "tafkheem_tarqeeq",
    "Lām of الله is light after kasrah.",
    sources=[f"{_JAZ}, bāb al-lāmāt"],
)
_r(
    "tafkheem_istila",
    "تفخيم حروف الاستعلاء",
    "Tafkhīm of istiʿlāʾ letters",
    "tafkheem_tarqeeq",
    "خص ضغط قظ are always heavy (with ṣād/ḍād/ṭāʾ/ẓāʾ "
    "heaviest); qāf/ghayn/khāʾ slightly lighter when makṣūr.",
    sources=[f"{_JAZ}, bāb ṣifāt al-ḥurūf"],
)
# -- Lām at-taʿrīf / hamzah -----------------------------------------------------
_r(
    "lam_shamsi",
    "اللام الشمسية",
    "Idghām shamsī",
    "lam_hamzah",
    "Lām of ال before a solar letter (ت ث د ذ ر ز س ش ص ض ط ظ ل ن): "
    "assimilated, the solar letter is doubled.",
    sources=[f"{_JAZ}, bāb al-lāmāt"],
)
_r(
    "lam_qamari",
    "اللام القمرية",
    "Iẓhār qamarī",
    "lam_hamzah",
    "Lām of ال before a lunar letter (ابغ حجك وخف عقيمه): pronounced clearly.",
    sources=[f"{_JAZ}, bāb al-lāmāt"],
)
_r(
    "hamzat_wasl",
    "همزة الوصل",
    "Hamzat al-waṣl",
    "lam_hamzah",
    "Word-initial bare alif (ٱ/ا): pronounced at ibtidāʾ, dropped in connection (waṣl).",
    sources=[f"{_JAZ}, bāb al-waqf wa-l-ibtidāʾ"],
    qiraat_notes=["Warsh differs in hamzah treatment (naql/ibdāl/tas-hīl) — not analyzed here."],
)
# -- Sakt ----------------------------------------------------------------------
_r(
    "sakt",
    "السكت",
    "Sakt",
    "sakt",
    "A brief pause without breath at the four Ḥafṣ places "
    "(مَنْ رَاقٍ، بَلْ رَانَ، عِوَجًا قَيِّمًا، مَالِيَهْ هَلَكَ) — it blocks the "
    "idghām/ikhfāʾ that would otherwise apply.",
    sources=[f"{_SHAT}, Ḥafṣ ʿan ʿĀṣim min ṭarīq ash-Shāṭibiyyah"],
    qiraat_notes=["Ḥafṣ-specific (Shaṭibiyyah ṭarīq); Warsh reads these with waṣl (no sakt)."],
)

# ---------------------------------------------------------------------------
# Token model
# ---------------------------------------------------------------------------


@dataclass
class Unit:
    """One base letter with its combining marks."""

    index: int  # char offset in the original text
    base: str  # canonical base (hamzah carriers → ء)
    raw: str  # original character
    marks: frozenset  # e.g. frozenset({"fatha", "shadda"})
    word: int  # word index
    tail: int = 0  # number of combining-mark chars after this char


@dataclass
class Annotation:
    rule_id: str
    start: int  # char offset (inclusive)
    end: int  # char offset (exclusive)
    span: str  # original text slice
    detail: str
    qiraat_note: str | None = None

    def to_dict(self, text: str) -> dict:
        rule = RULES[self.rule_id]
        return {
            "rule_id": rule.rule_id,
            "rule_name_ar": rule.name_ar,
            "rule_name_en": rule.name_en,
            "category": rule.category,
            "start": self.start,
            "end": self.end,
            "span": text[self.start : self.end],
            "detail": self.detail,
            "counts": rule.counts,
            "sources": list(rule.sources),
            "qiraat_note": self.qiraat_note
            or (rule.qiraat_notes[0] if rule.qiraat_notes else None),
        }


def strip_diacritics(text: str) -> str:
    """Remove combining marks and tatweel (for bare-letter matching)."""
    return "".join(ch for ch in text if ch not in MARK_NAMES and ch != TATWEEL)


def _tokenize(text: str) -> tuple[list[Unit], list[tuple[int, int]]]:
    """Split text into letter units; group into words.

    Returns (units, words) where words are (first_unit_idx, one_past_last)
    index ranges into units. One original char may yield two units
    (آ → hamzah + madd-alif), both sharing the char index.
    """
    units: list[Unit] = []
    words: list[tuple[int, int]] = []
    word_idx = -1
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            if word_idx >= 0 and words and words[-1][1] != len(units):
                s, _ = words[-1]
                words[-1] = (s, len(units))
            word_idx = -1
            i += 1
            continue
        if ch == TATWEEL:
            i += 1
            continue
        if word_idx < 0:
            word_idx = len(words)
            words.append((len(units), len(units)))
        # collect combining marks following this base char
        marks: set[str] = set()
        j = i + 1
        while j < n and text[j] in MARK_NAMES:
            marks.add(MARK_NAMES[text[j]])
            j += 1
        if ch in MARK_NAMES:
            # stray mark (no base) — skip
            i = j
            continue
        if ch == ALEF_MADDAH:
            # آ → hamzah + alif (madd)
            units.append(Unit(i, "ء", ch, frozenset(), word_idx, j - i - 1))
            units.append(Unit(i, "ا", ch, frozenset({"maddah"}), word_idx, j - i - 1))
        elif ch == ALEF_WASLA:
            units.append(Unit(i, "ا", ch, frozenset(marks) | {"wasla"}, word_idx, j - i - 1))
        elif ch in HAMZAH_FORMS:
            units.append(Unit(i, HAMZAH_FORMS[ch], ch, frozenset(marks), word_idx, j - i - 1))
        else:
            units.append(Unit(i, ch, ch, frozenset(marks), word_idx, j - i - 1))
        i = j
    if words and words[-1][1] != len(units):
        s, _ = words[-1]
        words[-1] = (s, len(units))
    return units, words


def _is_tanwin(u: Unit) -> bool:
    return bool({"tanwin_fath", "tanwin_damm", "tanwin_kasr"} & u.marks)


def _vowel(u: Unit) -> str | None:
    """The ḥarakah on a unit (tanwīn counts as its vowel)."""
    for m in ("fatha", "damma", "kasra"):
        if m in u.marks:
            return m
    if "tanwin_fath" in u.marks:
        return "fatha"
    if "tanwin_damm" in u.marks:
        return "damma"
    if "tanwin_kasr" in u.marks:
        return "kasra"
    return None


def _next_letter(units: list[Unit], i: int) -> Unit | None:
    return units[i + 1] if i + 1 < len(units) else None


def _prev_letter(units: list[Unit], i: int) -> Unit | None:
    return units[i - 1] if i - 1 >= 0 else None


def _vowel_before(units: list[Unit], i: int) -> str | None:
    """Walk back over sākin letters to find the governing ḥarakah."""
    j = i - 1
    while j >= 0 and units[j].word == units[i].word:
        v = _vowel(units[j])
        if v:
            return v
        if "sukun" not in units[j].marks and units[j].base not in ("و", "ي", "ا"):
            return None
        j -= 1
    return None


def _span_of(a: int, b: int, units: list[Unit]) -> tuple[int, int]:
    """Char offsets covering units[a..b] inclusive (with their mark chars)."""
    return units[a].index, units[b].index + 1 + units[b].tail


def _next_sound_index(units: list[Unit], words: list[tuple[int, int]], i: int) -> int | None:
    """Index of the next letter unit, skipping a word-final ʿiwaḍ alif.

    In رِزْقًا غَفُورٌ the tanwīn sits on ق while the bare alif is just the
    ʿiwaḍ carrier — the nūn-rule trigger is the next word's غ.
    """
    j = i + 1
    while j < len(units):
        u = units[j]
        w = words[u.word]
        if u.base in {"ا", "ى"} and not u.marks and j == w[1] - 1 and j > w[0]:
            p = units[j - 1]
            if p.word == u.word and "tanwin_fath" in p.marks:
                j += 1
                continue
        return j
    return None


# ---------------------------------------------------------------------------
# Scanners
# ---------------------------------------------------------------------------


class _Scan:
    def __init__(self, text: str, units: list[Unit], words: list[tuple[int, int]]):
        self.text = text
        self.units = units
        self.words = words
        self.anns: list[Annotation] = []
        self.sakt_blocks: set[int] = set()  # word idx i → sakt between i and i+1
        self.muqattaat_words: set[int] = set()

    # -- helpers ------------------------------------------------------------
    def add(self, rule_id: str, a: int, b: int, detail: str, qiraat_note: str | None = None):
        s, e = _span_of(a, b, self.units)
        self.anns.append(Annotation(rule_id, s, e, "", detail, qiraat_note))

    def word_start_hamzah_qat(self, wi: int) -> bool:
        """Next word starts with hamzat qaṭʿ (أ/إ/ء — not bare ا)."""
        if wi + 1 >= len(self.words):
            return None
        w = self.words[wi + 1]
        first = self.units[w[0]]
        return first.base == "ء" and first.raw != "ا"

    def sakt_between(self, ui: int, vi: int) -> bool:
        u, v = self.units[ui], self.units[vi]
        return u.word != v.word and u.word in self.sakt_blocks

    # -- sakt ---------------------------------------------------------------
    def scan_sakt(self):
        def norm(bare: str) -> str:
            # strip the ʿiwaḍ alif for pair matching (قَيِّمًا → قيم)
            return bare.rstrip("اى")

        bare = [norm("".join(u.base for u in self.units[w[0] : w[1]])) for w in self.words]
        pairs = {(a.rstrip("اى"), b.rstrip("اى")) for a, b in SAKT_PAIRS}
        for i in range(len(bare) - 1):
            if (bare[i], bare[i + 1]) in pairs:
                self.sakt_blocks.add(i)
                w = self.words[i]
                self.add(
                    "sakt",
                    w[0],
                    w[1] - 1,
                    f"sakt at end of «{self.text[self.units[w[0]].index : self.units[w[1] - 1].index + 1]}»: "
                    "brief pause without breath; blocks the idghām/ikhfāʾ that "
                    "would otherwise apply across this boundary (Ḥafṣ).",
                )

    # -- nūn sākinah / tanwīn ------------------------------------------------
    def scan_nun(self, i: int):
        u = self.units[i]
        triggered = (u.base == "ن" and "sukun" in u.marks) or _is_tanwin(u)
        if not triggered:
            return
        vi = _next_sound_index(self.units, self.words, i)
        if vi is None or self.sakt_between(i, vi):
            return
        v = self.units[vi]
        b = v.base
        trig = "nūn sākinah" if u.base == "ن" else "tanwīn"
        if b in HALQ:
            self.add(
                "nun_izhar", i, vi, f"{trig} + {v.raw} (throat letter) → iẓhār: clear, no ghunnah."
            )
        elif b in IDGHAM_GHUNNAH:
            if u.word == v.word and u.base == "ن":
                self.add(
                    "nun_izhar_mutlaq",
                    i,
                    vi,
                    f"{trig} + {v.raw} inside one word → iẓhār muṭlaq "
                    "(idghām blocked to preserve meaning).",
                )
            else:
                kamil = (
                    "kāmil (complete assimilation)"
                    if b in IDGHAM_GHUNNAH_KAMIL
                    else "nāqiṣ (ghunnah remains on ي/و)"
                )
                self.add(
                    "nun_idgham_ghunnah", i, vi, f"{trig} + {v.raw} → idghām bi-ghunnah, {kamil}."
                )
        elif b in IDGHAM_NO_GHUNNAH:
            self.add("nun_idgham_no_ghunnah", i, vi, f"{trig} + {v.raw} → idghām bi-ghayr ghunnah.")
        elif b in IQLAB:
            self.add(
                "nun_iqlab", i, vi, f"{trig} + {v.raw} → iqlāb: concealed as mīm with ghunnah."
            )
        elif b in IKHFA:
            taf = "mufakhkhamah (before istiʿlāʾ)" if b in ISTILA else "muraqqaqah"
            self.add("nun_ikhfa", i, vi, f"{trig} + {v.raw} → ikhfāʾ with ghunnah {taf}.")

    # -- mīm sākinah ----------------------------------------------------------
    def scan_mim(self, i: int):
        u = self.units[i]
        if not (u.base == "م" and "sukun" in u.marks):
            return
        vi = _next_sound_index(self.units, self.words, i)
        if vi is None or self.sakt_between(i, vi):
            return
        v = self.units[vi]
        b = v.base
        if b == "ب":
            self.add("mim_ikhfa", i, vi, f"mīm sākinah + {v.raw} → ikhfāʾ shafawī with ghunnah.")
        elif b == "م":
            self.add(
                "mim_idgham", i, vi, f"mīm sākinah + {v.raw} → idghām mithlayn ṣaghīr with ghunnah."
            )
        else:
            extra = " — extra care before و/ف (close makhraj)." if b in {"و", "ف"} else ""
            self.add("mim_izhar", i, vi, f"mīm sākinah + {v.raw} → iẓhār shafawī (clear).{extra}")

    # -- ghunnah ---------------------------------------------------------------
    def scan_ghunnah(self, i: int):
        u = self.units[i]
        if u.base in {"ن", "م"} and "shadda" in u.marks:
            self.add("ghunnah_mushaddad", i, i, f"{u.raw} mushaddadah → ghunnah, 2 counts (akmal).")

    # -- qalqalah ---------------------------------------------------------------
    def scan_qalqalah(self, i: int, word_end: bool, phrase_end: bool):
        u = self.units[i]
        if u.base not in QALQALAH:
            return
        if word_end and phrase_end:
            # waqf assumed at end of input
            self.add("qalqalah_kubra", i, i, f"{u.raw} at end of phrase → qalqalah kubrā on waqf.")
        elif "sukun" in u.marks:
            where = "at word end (waṣl)" if word_end else "mid-word"
            self.add("qalqalah_sughra", i, i, f"{u.raw} sākinah {where} → qalqalah ṣughrā.")

    # -- rāʾ ---------------------------------------------------------------------
    def _ra_sakinah_ruling(self, i: int, wi: int) -> tuple[str, str] | None:
        """Ruling for a sākin rāʾ (or rāʾ made sākin by waqf)."""
        u = self.units[i]
        w = self.words[wi]
        bare = "".join(x.base for x in self.units[w[0] : w[1]])
        word_end = i == w[1] - 1
        if word_end and bare in {"مصر", "القطر"}:
            pref = ("tafkhīm preferred", "tarqīq preferred")[bare != "مصر"]
            return ("ra_jawaz", f"{bare}: rāʾ at waqf → both allowed on waqf, {pref}.")
        if bare == "فرق":
            nxt = _next_letter(self.units, i)
            if nxt is not None and nxt.base == "ق" and _vowel(nxt) == "kasra":
                return (
                    "ra_jawaz",
                    "فِرْقٍ: rāʾ sākinah after lāzim kasrah before makṣūr "
                    "qāf → both allowed, tarqīq preferred.",
                )
        p = _prev_letter(self.units, i)
        if p is None or p.word != u.word:
            return None
        pv = _vowel(p)
        if pv in ("fatha", "damma"):
            return ("ra_tafkhim", f"rāʾ sākinah after {pv} → mufakhkhamah.")
        if pv == "kasra":
            if p.base == "ا" and p.index == self.units[w[0]].index and p.raw in {"ا", "ٱ"}:
                return (
                    "ra_tafkhim",
                    "rāʾ sākinah after ʿāriḍ kasrah (hamzat waṣl) → mufakhkhamah.",
                )
            nxt = _next_letter(self.units, i)
            if (
                nxt is not None
                and nxt.word == u.word
                and nxt.base in ISTILA
                and _vowel(nxt) != "kasra"
            ):
                return (
                    "ra_tafkhim",
                    "rāʾ sākinah after lāzim kasrah but followed by "
                    f"istiʿlāʾ letter {nxt.raw} in the same word → "
                    "mufakhkhamah.",
                )
            return ("ra_tarqeeq", "rāʾ sākinah after lāzim kasrah → muraqqaqah.")
        if "sukun" in p.marks:
            if p.base == "ي":
                return ("ra_tarqeeq", "rāʾ sākinah after yāʾ sākinah → muraqqaqah.")
            gv = _vowel_before(self.units, i)
            if gv in ("fatha", "damma"):
                return (
                    "ra_tafkhim",
                    "rāʾ sākinah; governing vowel before the sākin "
                    f"cluster is {gv} → mufakhkhamah.",
                )
            if gv == "kasra":
                return (
                    "ra_tarqeeq",
                    "rāʾ sākinah; governing vowel before the sākin cluster is kasrah → muraqqaqah.",
                )
        return None

    def scan_ra(self, i: int, wi: int):
        u = self.units[i]
        if u.base != "ر":
            return
        w = self.words[wi]
        word_end = i == w[1] - 1
        v = _vowel(u)
        if v in ("fatha", "damma", "kasra"):
            rule = "ra_tafkhim" if v != "kasra" else "ra_tarqeeq"
            how = "mufakhkhamah" if v != "kasra" else "muraqqaqah"
            detail = f"rāʾ with {v} → {how} (in waṣl)."
            if word_end:
                wr = self._ra_sakinah_ruling(i, wi)
                if wr is not None:
                    wr_rule = RULES[wr[0]]
                    detail += f" On waqf: {wr_rule.name_en.lower()} — {wr[1]}"
            self.add(rule, i, i, detail)
            return
        if "sukun" not in u.marks:
            return  # unvocalized — cannot judge (lā taqfu)
        r = self._ra_sakinah_ruling(i, wi)
        if r is not None:
            self.add(r[0], i, i, r[1])

    # -- lām al-jalālah -----------------------------------------------------------
    def scan_lam_jalalah(self, wi: int):
        w = self.words[wi]
        us = self.units[w[0] : w[1]]
        bases = [x.base for x in us]
        for j in range(len(bases) - 3):
            if bases[j : j + 4] == ["ا", "ل", "ل", "ه"]:
                a = w[0] + j
                # governing vowel: prefix letter, else previous word's last vowel
                gv = _vowel(us[j - 1]) if j > 0 else None
                if gv is None and wi > 0:
                    pw = self.words[wi - 1]
                    gv = _vowel(self.units[pw[1] - 1])
                if gv == "kasra":
                    self.add(
                        "lam_jalalah_tarqeeq", a, a + 3, "lām al-jalālah after kasrah → muraqqaqah."
                    )
                else:
                    self.add(
                        "lam_jalalah_tafkhim",
                        a,
                        a + 3,
                        f"lām al-jalālah after {gv or 'start'} → mufakhkhamah.",
                    )
                return

    # -- lām at-taʿrīf ---------------------------------------------------------------
    def scan_lam_tarif(self, wi: int) -> bool:
        """Apply the ال (lām at-taʿrīf) rule. Returns True if it fired."""
        w = self.words[wi]
        us = self.units[w[0] : w[1]]
        if len(us) < 3 or us[0].base != "ا" or us[0].raw not in {"ا", "ٱ"}:
            return False
        if us[1].base != "ل":
            return False
        b = us[2].base
        if b in SUN:
            self.add(
                "lam_shamsi",
                w[0],
                w[0] + 1,
                f"ال + {us[2].raw} (solar) → idghām shamsī: lām assimilated, solar letter doubled.",
            )
            return True
        if b in MOON:
            self.add(
                "lam_qamari", w[0], w[0] + 1, f"ال + {us[2].raw} (lunar) → iẓhār qamarī: lām clear."
            )
            return True
        return False

    # -- hamzat al-waṣl ------------------------------------------------------------
    def scan_hamzat_wasl(self, wi: int):
        w = self.words[wi]
        u = self.units[w[0]]
        if u.base == "ا" and u.raw in {"ا", "ٱ"}:
            self.add(
                "hamzat_wasl", w[0], w[0], "hamzat al-waṣl: pronounced at ibtidāʾ, dropped in waṣl."
            )

    # -- madd -----------------------------------------------------------------------
    def _is_wasl_alif(self, i: int, s: int) -> bool:
        """True if the alif at i is hamzat waṣl of ال (not a madd carrier).

        Covers word-initial ال and ال after detachable prefixes
        (وَ/فَ/بِ/كَ/لِ), e.g. وَاللَّهُ. The alif must be followed by lām;
        a stem alif before lām (قَالَ) keeps its madd.
        """
        u = self.units[i]
        if u.base != "ا":
            return False
        n = _next_letter(self.units, i)
        if n is None or n.word != u.word or n.base != "ل":
            return False
        if i == s:
            return True
        j = i - 1
        while (
            j >= s
            and self.units[j].base in {"و", "ف", "ب", "ك", "ل"}
            and _vowel(self.units[j]) is not None
        ):
            j -= 1
        return j < s

    def _madd_carrier(self, i: int):
        """Classify unit i as a madd carrier or None.

        Returns (kind, prev_vowel) where kind is 'alif' | 'waw' | 'ya' | 'lin' | 'sup'.
        Badal (hamzah + madd) is handled as a pre-check in scan_madd_word.
        Word-initial bare alif is hamzat waṣl — never a madd carrier.
        """
        u = self.units[i]
        if "sup_alef" in u.marks:
            return ("sup", None)
        p = _prev_letter(self.units, i)
        if p is None or p.word != u.word:
            return None  # word-initial: hamzat waṣl / hamzah, not madd
        pv = _vowel(p)
        if u.base == "ا" and "wasla" not in u.marks:
            if pv == "fatha":
                return ("alif", pv)
            return None
        if u.base == "ى" and pv == "fatha":
            return ("alif", pv)
        if u.base == "و" and ("sukun" in u.marks or not u.marks):
            if pv == "damma":
                # bare wāw after ḍammah (unmarked madd, e.g. يَقُولُ) counts
                return ("waw", pv)
            if pv == "fatha" and "sukun" in u.marks:
                return ("lin", pv)
            return None
        if u.base == "ي" and ("sukun" in u.marks or not u.marks):
            if pv == "kasra":
                # bare yāʾ after kasrah (unmarked madd, e.g. نَسْتَعِينُ) counts
                return ("ya", pv)
            if pv == "fatha" and "sukun" in u.marks:
                return ("lin", pv)
            return None
        return None

    def _badal_at(self, i: int) -> bool:
        """True if unit i is a madd letter right after a hamzah (madd badal).

        The hamzah may carry no explicit vowel in digital text (e.g. آ),
        so this does not require the ṭabīʿī conditions.
        """
        u = self.units[i]
        p = _prev_letter(self.units, i)
        if p is None or p.word != u.word or p.base != "ء":
            return False
        if u.base == "ا" and "wasla" not in u.marks:
            return True
        if u.base in {"و", "ي"} and ("sukun" in u.marks or _vowel(u) is None):
            return True
        return False

    def scan_madd_word(self, wi: int):
        if wi in self.muqattaat_words:
            return
        w = self.words[wi]
        s, e = w
        for i in range(s, e):
            u = self.units[i]
            if u.base == "ا" and self._is_wasl_alif(i, s):
                continue  # hamzat waṣl of ال — never a madd carrier
            # madd ʿiwaḍ: word-final bare alif after tanwīn fatḥah (waqf only)
            # e.g. رِزْقًا (tanwīn sits on the qāf, alif is the carrier)
            if i == e - 1 and u.base in {"ا", "ى"} and not u.marks:
                p0 = _prev_letter(self.units, i)
                if p0 is not None and p0.word == u.word and "tanwin_fath" in p0.marks:
                    self.add(
                        "madd_iwad",
                        i,
                        i,
                        "tanwīn + word-final alif → madd ʿiwaḍ, 2 counts "
                        "on waqf (no madd in waṣl).",
                    )
                    continue
            is_badal = self._badal_at(i)
            mc = self._madd_carrier(i)
            if not is_badal and mc is None:
                continue
            kind = mc[0] if mc else "alif"
            n = _next_letter(self.units, i)

            def _same(x, _u=u):
                return x is not None and x.word == _u.word

            # 1. lāzim kalimī — madd + permanent sukūn (wins over badal, e.g. آلْآنَ)
            if _same(n) and "shadda" in n.marks:
                self.add(
                    "madd_lazim_kalimi",
                    i,
                    i,
                    f"madd + {n.raw} mushaddad → lāzim kalimī muthaqqal, 6 counts.",
                )
                continue
            if _same(n) and "sukun" in n.marks and n.base != "ء":
                self.add(
                    "madd_lazim_kalimi",
                    i,
                    i,
                    f"madd + {n.raw} sākin → lāzim kalimī mukhaffaf, 6 counts.",
                )
                continue
            # 2. badal — hamzah + madd
            if is_badal:
                self.add(
                    "madd_badal",
                    i - 1,
                    i,
                    "hamzah + madd → badal, 2 counts (Ḥafṣ).",
                    qiraat_note="Warsh: 2/4/6 (qaṣr/tawassuṭ/ṭūl); Ḥafṣ: 2.",
                )
                continue
            if kind == "sup":
                self.add("madd_tabi", i, i, "alif khanjariyyah (ٰ) → madd ṭabīʿī, 2 counts.")
                continue
            # 3. muttaṣil — madd + hamzah, same word
            if _same(n) and n.base == "ء":
                self.add(
                    "madd_muttasil", i, i + 1, "madd + hamzah in one word → muttaṣil, 4–5 counts."
                )
                continue
            # 4. word-final positions
            if i == e - 1:
                if kind == "lin":
                    continue  # līn needs a following letter; nothing to lengthen
                if self.word_start_hamzah_qat(wi):
                    self.add(
                        "madd_munfasil",
                        i,
                        i,
                        "word-final madd + hamzah (qaṭʿ) next word → munfaṣil, 4–5 counts (Ḥafṣ).",
                        qiraat_note="Warsh: 6 (ishbāʿ) via most ṭuruq; Ḥafṣ: 4–5.",
                    )
                else:
                    self.add("madd_tabi", i, i, "madd ṭabīʿī, 2 counts.")
                continue
            if i == e - 2:
                if kind == "lin":
                    self.add(
                        "madd_lin",
                        i,
                        i,
                        "līn letter + word-final consonant → madd līn "
                        "2/4/6 on waqf (no madd in waṣl).",
                    )
                elif kind in ("alif", "waw", "ya"):
                    self.add(
                        "madd_arid",
                        i,
                        i,
                        "madd + word-final letter → ʿāriḍ li-s-sukūn "
                        "2/4/6 on waqf (ṭabīʿī in waṣl).",
                    )
                continue
            # 5. plain ṭabīʿī
            if kind in ("alif", "waw", "ya"):
                self.add("madd_tabi", i, i, "madd ṭabīʿī, 2 counts.")

    # -- ṣilah ------------------------------------------------------------------------
    def scan_silah(self, wi: int):
        w = self.words[wi]
        u = self.units[w[1] - 1]
        if u.base != "ه" or _vowel(u) not in ("damma", "kasra"):
            return
        bare = "".join(x.base for x in self.units[w[0] : w[1]])
        if "الله" in bare:
            return  # the hāʾ of الله is not hāʾ al-ḍamīr
        if bare == "يرضه":
            return  # istiṯnāʾ (39:7) — no ṣilah in Ḥafṣ
        p = _prev_letter(self.units, w[1] - 1)
        mutaharrik = (
            p is not None and p.word == u.word and _vowel(p) is not None and "sukun" not in p.marks
        )
        if not mutaharrik:
            # e.g. فِيهِ (sākin before): no ṣilah. The single exception
            # فِيهِ مُهَانًا (25:69) needs verse context — not guessed here.
            return
        if self.word_start_hamzah_qat(wi):
            self.add(
                "madd_silah_kubra",
                w[1] - 1,
                w[1] - 1,
                "hāʾ al-ḍamīr + hamzah → ṣilah kubrā, 4–5 counts.",
                qiraat_note="Warsh: 6 (like munfaṣil).",
            )
        else:
            self.add(
                "madd_silah_sughra",
                w[1] - 1,
                w[1] - 1,
                "hāʾ al-ḍamīr after mutaḥarrik → ṣilah ṣughrā, 2 counts.",
            )

    # -- muqaṭṭaʿāt ----------------------------------------------------------------------
    def scan_muqattaat(self, wi: int):
        w = self.words[wi]
        bare = "".join(x.base for x in self.units[w[0] : w[1]])
        if bare not in MUQATTAAT:
            return
        self.muqattaat_words.add(wi)
        for k in range(w[0], w[1]):
            u = self.units[k]
            if u.base in HARFI_SIX:
                if u.base == "ع":
                    self.add(
                        "madd_lazim_harfi",
                        k,
                        k,
                        "ʿayn in muqaṭṭaʿāt → lāzim ḥarfī, 4 or 6 (jawāz).",
                    )
                else:
                    self.add(
                        "madd_lazim_harfi",
                        k,
                        k,
                        f"{u.raw} in muqaṭṭaʿāt (نقص عسلكم) → lāzim ḥarfī, 6 counts.",
                    )
            elif u.base in HARFI_TWO:
                self.add(
                    "madd_tabi", k, k, f"{u.raw} in muqaṭṭaʿāt (حي طهر) → ṭabīʿī ḥarfī, 2 counts."
                )

    # -- istiʿlāʾ tafkhīm ------------------------------------------------------------------
    def scan_istila(self, i: int):
        u = self.units[i]
        if u.base in ISTILA:
            self.add("tafkheem_istila", i, i, f"{u.raw} (istiʿlāʾ) → always mufakhkham.")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_text(text: str, qiraat: str = QIRAAT_DEFAULT) -> dict:
    """Analyze Arabic text for tajwīd rules (Ḥafṣ ʿan ʿĀṣim).

    Returns a JSON-serializable dict with ``status``, ``annotations``,
    ``rules_applied`` and ``diacritic_coverage``.
    """
    units, words = _tokenize(text)
    result: dict = {
        "status": "ok",
        "qiraat": qiraat,
        "annotations": [],
        "rules_applied": [],
        "diacritic_coverage": 0.0,
        "note": None,
    }
    if not units:
        result["note"] = "Empty input."
        return result
    coverage = sum(1 for u in units if u.marks) / len(units)
    result["diacritic_coverage"] = round(coverage, 3)
    letter_only = coverage == 0

    sc = _Scan(text, units, words)
    sc.scan_sakt()
    for wi, _w in enumerate(words):
        sc.scan_muqattaat(wi)
    if letter_only:
        # No tashkīl: only letter-shape rules can run (no vowel guessing).
        for wi, _w in enumerate(words):
            if wi not in sc.muqattaat_words:
                sc.scan_lam_tarif(wi)
                sc.scan_hamzat_wasl(wi)  # ال's alif is hamzat waṣl too
        anns = sorted(sc.anns, key=lambda a: (a.start, -(a.end - a.start)))
        result["annotations"] = [a.to_dict(text) for a in anns]
        result["rules_applied"] = sorted({a.rule_id for a in anns})
        result["status"] = "partial"
        result["note"] = (
            "No diacritics detected: only letter-shape rules ran "
            "(muqaṭṭaʿāt, sakt places, hamzat al-waṣl, lām shamsiyyah/qamariyyah). "
            "Add tashkīl for the full analysis — the engine does not guess vowels."
        )
        return result

    for wi, w in enumerate(words):
        s, e = w
        if wi not in sc.muqattaat_words:
            sc.scan_lam_tarif(wi)
            sc.scan_hamzat_wasl(wi)  # ال's alif is hamzat waṣl too
            sc.scan_lam_jalalah(wi)
            sc.scan_madd_word(wi)
            sc.scan_silah(wi)
        for i in range(s, e):
            sc.scan_nun(i)
            sc.scan_mim(i)
            sc.scan_ghunnah(i)
            sc.scan_istila(i)
            sc.scan_qalqalah(i, word_end=(i == e - 1), phrase_end=(wi == len(words) - 1))
            sc.scan_ra(i, wi)

    anns = sorted(sc.anns, key=lambda a: (a.start, -(a.end - a.start)))
    result["annotations"] = [a.to_dict(text) for a in anns]
    result["rules_applied"] = sorted({a.rule_id for a in anns})
    if qiraat != QIRAAT_DEFAULT:
        result["note"] = (
            f"qiraat={qiraat!r}: only Ḥafṣ values are computed; "
            "qirāʾāt differences are flagged in qiraat_note fields, "
            "Warsh-specific values are not implemented."
        )
    return result


def get_rule_catalog() -> list[dict]:
    """The full rule catalog (for GET /v1/tajwid/rules)."""
    return [
        {
            "rule_id": r.rule_id,
            "name_ar": r.name_ar,
            "name_en": r.name_en,
            "category": r.category,
            "description": r.description,
            "counts": r.counts,
            "sources": list(r.sources),
            "qiraat_notes": list(r.qiraat_notes),
        }
        for r in RULES.values()
    ]
