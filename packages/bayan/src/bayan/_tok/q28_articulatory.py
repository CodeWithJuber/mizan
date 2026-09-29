"""
Q28 Articulatory Basis (أساس المخارج)
========================================

Implements the Q28 Complete Representation Theorem: the 28 Arabic letters
form a complete articulatory basis for ALL human speech sounds.

Each phoneme is a 6D vector: [place, manner, voicing, emphasis, nasality, length]

"And He taught Adam the names of all things." -- Quran 2:31
"""

from __future__ import annotations

import numpy as np
from numpy import ndarray

# ---------------------------------------------------------------------------
# Feature dimension constants
# ---------------------------------------------------------------------------

# Place of articulation (glottal→bilabial)
PLACE_GLOTTAL = 0.0
PLACE_PHARYNGEAL = 0.1
PLACE_UVULAR = 0.25
PLACE_VELAR = 0.4
PLACE_PALATAL = 0.55
PLACE_ALVEOLAR = 0.7
PLACE_DENTAL = 0.8
PLACE_LABIODENTAL = 0.9
PLACE_BILABIAL = 1.0

# Manner of articulation
MANNER_STOP = 0.0
MANNER_FRICATIVE = 0.33
MANNER_NASAL = 0.5
MANNER_LATERAL = 0.67
MANNER_TRILL = 0.83
MANNER_APPROXIMANT = 1.0

# Binary features
VOICELESS = 0.0
VOICED = 1.0
PLAIN = 0.0
EMPHATIC = 1.0
ORAL = 0.0
NASAL_FEAT = 1.0
SHORT = 0.0
LONG = 1.0

# ---------------------------------------------------------------------------
# 28 Arabic phonemes: letter → (IPA, [place, manner, voicing, emphasis, nasality, length])
# ---------------------------------------------------------------------------

# Each row: [place, manner, voicing, emphasis, nasality, length]
_Q28_PHONEMES: list[tuple[str, str, list[float]]] = [
    # letter, IPA, feature vector
    ("ا", "ʔ",  [PLACE_GLOTTAL,      MANNER_STOP,        VOICELESS, PLAIN,   ORAL,       SHORT]),
    ("ب", "b",  [PLACE_BILABIAL,     MANNER_STOP,        VOICED,    PLAIN,   ORAL,       SHORT]),
    ("ت", "t",  [PLACE_DENTAL,       MANNER_STOP,        VOICELESS, PLAIN,   ORAL,       SHORT]),
    ("ث", "θ",  [PLACE_DENTAL,       MANNER_FRICATIVE,   VOICELESS, PLAIN,   ORAL,       SHORT]),
    ("ج", "dʒ", [PLACE_PALATAL,      MANNER_STOP,        VOICED,    PLAIN,   ORAL,       SHORT]),
    ("ح", "ħ",  [PLACE_PHARYNGEAL,   MANNER_FRICATIVE,   VOICELESS, PLAIN,   ORAL,       SHORT]),
    ("خ", "x",  [PLACE_UVULAR,       MANNER_FRICATIVE,   VOICELESS, PLAIN,   ORAL,       SHORT]),
    ("د", "d",  [PLACE_DENTAL,       MANNER_STOP,        VOICED,    PLAIN,   ORAL,       SHORT]),
    ("ذ", "ð",  [PLACE_DENTAL,       MANNER_FRICATIVE,   VOICED,    PLAIN,   ORAL,       SHORT]),
    ("ر", "r",  [PLACE_ALVEOLAR,     MANNER_TRILL,       VOICED,    PLAIN,   ORAL,       SHORT]),
    ("ز", "z",  [PLACE_ALVEOLAR,     MANNER_FRICATIVE,   VOICED,    PLAIN,   ORAL,       SHORT]),
    ("س", "s",  [PLACE_ALVEOLAR,     MANNER_FRICATIVE,   VOICELESS, PLAIN,   ORAL,       SHORT]),
    ("ش", "ʃ",  [PLACE_PALATAL,      MANNER_FRICATIVE,   VOICELESS, PLAIN,   ORAL,       SHORT]),
    ("ص", "sˤ", [PLACE_ALVEOLAR,     MANNER_FRICATIVE,   VOICELESS, EMPHATIC, ORAL,      SHORT]),
    ("ض", "dˤ", [PLACE_DENTAL,       MANNER_STOP,        VOICED,    EMPHATIC, ORAL,      SHORT]),
    ("ط", "tˤ", [PLACE_DENTAL,       MANNER_STOP,        VOICELESS, EMPHATIC, ORAL,      SHORT]),
    ("ظ", "ðˤ", [PLACE_DENTAL,       MANNER_FRICATIVE,   VOICED,    EMPHATIC, ORAL,      SHORT]),
    ("ع", "ʕ",  [PLACE_PHARYNGEAL,   MANNER_FRICATIVE,   VOICED,    PLAIN,   ORAL,       SHORT]),
    ("غ", "ɣ",  [PLACE_UVULAR,       MANNER_FRICATIVE,   VOICED,    PLAIN,   ORAL,       SHORT]),
    ("ف", "f",  [PLACE_LABIODENTAL,  MANNER_FRICATIVE,   VOICELESS, PLAIN,   ORAL,       SHORT]),
    ("ق", "q",  [PLACE_UVULAR,       MANNER_STOP,        VOICELESS, PLAIN,   ORAL,       SHORT]),
    ("ك", "k",  [PLACE_VELAR,        MANNER_STOP,        VOICELESS, PLAIN,   ORAL,       SHORT]),
    ("ل", "l",  [PLACE_ALVEOLAR,     MANNER_LATERAL,     VOICED,    PLAIN,   ORAL,       SHORT]),
    ("م", "m",  [PLACE_BILABIAL,     MANNER_NASAL,       VOICED,    PLAIN,   NASAL_FEAT, SHORT]),
    ("ن", "n",  [PLACE_ALVEOLAR,     MANNER_NASAL,       VOICED,    PLAIN,   NASAL_FEAT, SHORT]),
    ("ه", "h",  [PLACE_GLOTTAL,      MANNER_FRICATIVE,   VOICELESS, PLAIN,   ORAL,       SHORT]),
    ("و", "w",  [PLACE_BILABIAL,     MANNER_APPROXIMANT, VOICED,    PLAIN,   ORAL,       SHORT]),
    ("ي", "j",  [PLACE_PALATAL,      MANNER_APPROXIMANT, VOICED,    PLAIN,   ORAL,       SHORT]),
]

# ---------------------------------------------------------------------------
# Extended IPA → Q28 mapping (covers English and other common IPA symbols)
# Maps IPA → index into _Q28_PHONEMES basis (nearest Arabic phoneme)
# ---------------------------------------------------------------------------

_IPA_TO_Q28_INDEX: dict[str, int] = {
    # Core Arabic phonemes (direct mapping by IPA)
    "ʔ":  0,   # alif
    "b":  1,   # ba
    "t":  2,   # ta
    "θ":  3,   # tha
    "dʒ": 4,   # jim
    "ħ":  5,   # ha
    "x":  6,   # kha
    "d":  7,   # dal
    "ð":  8,   # dhal
    "r":  9,   # ra
    "z":  10,  # zay
    "s":  11,  # sin
    "ʃ":  12,  # shin
    "sˤ": 13,  # sad
    "dˤ": 14,  # dad
    "tˤ": 15,  # ta'
    "ðˤ": 16,  # dha'
    "ʕ":  17,  # ayn
    "ɣ":  18,  # ghayn
    "f":  19,  # fa
    "q":  20,  # qaf
    "k":  21,  # kaf
    "l":  22,  # lam
    "m":  23,  # mim
    "n":  24,  # nun
    "h":  25,  # ha
    "w":  26,  # waw
    "j":  27,  # ya
    # English consonants mapped to nearest Arabic basis
    "p":  1,   # bilabial stop voiceless → nearest is ب (b), place/manner match
    "v":  19,  # labiodental fricative voiced → nearest is ف (f)
    "g":  21,  # velar stop voiced → nearest is ك (k) by place
    "ŋ":  24,  # velar nasal → nearest is ن (n) by nasality/manner
    "tʃ": 4,   # affricate → nearest is ج (jim) dʒ
    "ʒ":  12,  # palatal fricative voiced → nearest is ش (shin)
    "ʍ":  26,  # voiceless labial-velar → nearest is و (waw)
    "ɹ":  9,   # English r (approximant) → nearest is ر (ra)
    "ɾ":  9,   # tap → nearest is ر (ra)
    "ʁ":  18,  # uvular fricative voiced → nearest is غ (ghayn)
    "χ":  6,   # uvular fricative voiceless → nearest is خ (kha)
    "ʀ":  9,   # uvular trill → nearest is ر (ra) by trill manner
    "β":  1,   # bilabial fricative voiced → nearest is ب (ba)
    "ɸ":  19,  # bilabial fricative voiceless → nearest is ف (fa)
    "ç":  12,  # palatal fricative voiceless → nearest is ش (shin)
    "ɬ":  22,  # lateral fricative → nearest is ل (lam)
    "ʙ":  1,   # bilabial trill → nearest is ب (ba)
    "ɴ":  24,  # uvular nasal → nearest is ن (nun) by nasality
    "ɱ":  23,  # labiodental nasal → nearest is م (mim) by nasality
    "ʋ":  26,  # labiodental approximant → nearest is و (waw)
    "ɥ":  27,  # labial-palatal approximant → nearest is ي (ya)
    # Vowels: map by place of articulation to the nearest glide/approximant
    "a":  0,   # open central → alif (vowel bearer)
    "ɑ":  0,   # open back → alif
    "æ":  0,   # near-open front → alif
    "e":  27,  # close-mid front → ya (palatal coloring)
    "ɛ":  27,  # open-mid front → ya
    "i":  27,  # close front → ya
    "ɪ":  27,  # near-close front → ya
    "o":  26,  # close-mid back → waw (labial/back coloring)
    "ɔ":  26,  # open-mid back → waw
    "u":  26,  # close back → waw
    "ʊ":  26,  # near-close back → waw
    "ə":  0,   # schwa → alif (neutral)
    "ʌ":  0,   # open-mid back unrounded → alif
    "ɜ":  27,  # open-mid central → ya
    "ɐ":  0,   # near-open central → alif
    "y":  27,  # close front rounded → ya
    "ø":  27,  # close-mid front rounded → ya
}

# Simple English word → approximate IPA (fallback when epitran is absent)
_ENGLISH_APPROX_IPA: dict[str, str] = {
    # Common English words with approximate IPA transcriptions
    "the": "ðə",
    "and": "ænd",
    "that": "ðæt",
    "this": "ðɪs",
    "with": "wɪθ",
    "from": "frɒm",
    "have": "hæv",
    "not": "nɒt",
    "but": "bʌt",
    "for": "fɔr",
    "are": "ɑr",
    "was": "wɒz",
    "all": "ɔl",
    "been": "biːn",
    "said": "sɛd",
    "has": "hæz",
    "can": "kæn",
    "will": "wɪl",
    "one": "wʌn",
    "their": "ðɛr",
    "time": "taɪm",
    "day": "deɪ",
    "love": "lʌv",
    "life": "laɪf",
    "heart": "hɑrt",
    "mind": "maɪnd",
    "soul": "soʊl",
    "light": "laɪt",
    "truth": "truːθ",
    "peace": "piːs",
    "mercy": "mɜrsi",
    "grace": "ɡreɪs",
    "path": "pæθ",
    "way": "weɪ",
    "guide": "ɡaɪd",
    "know": "noʊ",
    "see": "siː",
    "hear": "hɪr",
    "speak": "spiːk",
    "say": "seɪ",
    "word": "wɜrd",
    "name": "neɪm",
    "god": "ɡɒd",
    "lord": "lɔrd",
    "man": "mæn",
    "world": "wɜrld",
    "good": "ɡʊd",
    "great": "ɡreɪt",
    "first": "fɜrst",
    "last": "læst",
    "new": "njuː",
    "old": "oʊld",
    "long": "lɒŋ",
    "high": "haɪ",
    "place": "pleɪs",
    "people": "piːpəl",
    "right": "raɪt",
    "come": "kʌm",
    "give": "ɡɪv",
    "take": "teɪk",
    "make": "meɪk",
    "work": "wɜrk",
    "think": "θɪŋk",
    "look": "lʊk",
    "turn": "tɜrn",
    "start": "stɑrt",
    "leave": "liːv",
    "call": "kɔl",
    "show": "ʃoʊ",
    "try": "traɪ",
    "ask": "æsk",
    "need": "niːd",
    "feel": "fiːl",
    "become": "bɪˈkʌm",
    "move": "muːv",
    "live": "lɪv",
    "run": "rʌn",
    "write": "raɪt",
    "read": "riːd",
    "walk": "wɔk",
    "stand": "stænd",
    "grow": "ɡroʊ",
    "open": "oʊpən",
    "follow": "fɒloʊ",
    "remember": "rɪˈmɛmbər",
    "believe": "bɪˈliːv",
    "receive": "rɪˈsiːv",
    "serve": "sɜrv",
    "seek": "siːk",
    "return": "rɪˈtɜrn",
    "learn": "lɜrn",
    "teach": "tiːtʃ",
    "worship": "ˈwɜrʃɪp",
    "pray": "preɪ",
    "fast": "fæst",
    "give": "ɡɪv",
    "help": "hɛlp",
    "protect": "prəˈtɛkt",
    "create": "kriˈeɪt",
    "build": "bɪld",
    "destroy": "dɪˈstrɔɪ",
    "save": "seɪv",
    "forgive": "fərˈɡɪv",
    "judge": "dʒʌdʒ",
    "command": "kəˈmænd",
    "obey": "oˈbeɪ",
}

# Known Arabic root articulatory signatures (averaged Q28 vector per root)
# Format: root_string → representative word (IPA approximation)
_ROOT_IPA_SIGNATURES: dict[str, str] = {
    "ك-ت-ب": "ktb",   # write
    "ع-ل-م": "ʕlm",   # know/science
    "ر-ح-م": "rħm",   # mercy
    "ح-م-د": "ħmd",   # praise
    "س-ل-م": "slm",   # peace/submission
    "ق-ر-أ": "qrʔ",   # read/recite
    "ع-ب-د": "ʕbd",   # worship/serve
    "ح-ي-ي": "ħjj",   # live/greet
    "و-ج-د": "wdʒd",  # exist/find
    "ن-ز-ل": "nzl",   # descend/reveal
    "ه-د-ي": "hdj",   # guide
    "ح-ق-ق": "ħqq",   # truth/realize
    "ص-ب-ر": "sˤbr",  # patience
    "ج-ه-د": "dʒhd",  # strive
    "ف-ت-ح": "ftħ",   # open/victory
    "ذ-ك-ر": "ðkr",   # remember/mention
    "خ-ل-ق": "xlq",   # create
    "ن-و-ر": "nwr",   # light
    "ع-ر-ف": "ʕrf",   # know/recognize
    "ق-ل-ب": "qlb",   # heart/turn
    "ر-ز-ق": "rzq",   # provision
    "ش-ك-ر": "ʃkr",   # gratitude
    "ت-و-ب": "twb",   # repent/return
    "ف-ك-ر": "fkr",   # think/reflect
    "أ-م-ن": "ʔmn",   # faith/security
    "ع-ل-و": "ʕlw",   # high/exalted
    "ب-ر-ك": "brk",   # blessing
    "ر-ب-ب": "rbb",   # lord/nurture
}


def _cosine_similarity(vec_a: ndarray, vec_b: ndarray) -> float:
    """Compute cosine similarity between two 1D vectors."""
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))


def _ipa_string_to_chars(ipa: str) -> list[str]:
    """Split an IPA string into recognized phoneme tokens.

    Handles multi-character IPA symbols (e.g. 'dʒ', 'tʃ', 'sˤ').
    """
    multi_char = sorted(_IPA_TO_Q28_INDEX.keys(), key=len, reverse=True)
    result: list[str] = []
    idx = 0
    while idx < len(ipa):
        matched = False
        for symbol in multi_char:
            if ipa[idx:idx + len(symbol)] == symbol:
                result.append(symbol)
                idx += len(symbol)
                matched = True
                break
        if not matched:
            # Include single character even if unmapped — caller handles UNK
            result.append(ipa[idx])
            idx += 1
    return result


def _word_to_ipa_fallback(word: str) -> str:
    """Best-effort IPA approximation for English when epitran is absent."""
    lower = word.lower().strip()
    if lower in _ENGLISH_APPROX_IPA:
        return _ENGLISH_APPROX_IPA[lower]
    # Character-level naive mapping for unknown words
    char_map = {
        "a": "æ", "b": "b", "c": "k", "d": "d", "e": "ɛ",
        "f": "f", "g": "ɡ", "h": "h", "i": "ɪ", "j": "dʒ",
        "k": "k", "l": "l", "m": "m", "n": "n", "o": "ɒ",
        "p": "p", "q": "k", "r": "r", "s": "s", "t": "t",
        "u": "ʌ", "v": "v", "w": "w", "x": "ks", "y": "j",
        "z": "z",
    }
    return "".join(char_map.get(ch, ch) for ch in lower)


def _try_import_epitran() -> object | None:
    """Attempt to import epitran; return the module or None if absent."""
    try:
        import epitran  # type: ignore[import]
        return epitran
    except ImportError:
        return None


class Q28ArticulatoryBasis:
    """Maps all human speech to the 28-dimensional Arabic articulatory basis.

    The Q28 Complete Representation Theorem holds that the 28 Arabic letters,
    each associated with a specific point of articulation (makhraj), span the
    full phonemic space of human speech.
    """

    def __init__(self) -> None:
        self._letters: list[str] = [row[0] for row in _Q28_PHONEMES]
        self._ipa_symbols: list[str] = [row[1] for row in _Q28_PHONEMES]
        self._basis_matrix: ndarray = np.array(
            [row[2] for row in _Q28_PHONEMES], dtype=np.float64
        )  # shape: (28, 6)
        self._ipa_to_q28: dict[str, ndarray] = self._build_ipa_lookup()
        self._root_signatures: dict[str, ndarray] = self._build_root_signatures()

    def _build_ipa_lookup(self) -> dict[str, ndarray]:
        """Pre-compute IPA → Q28 vector dict for O(1) lookup."""
        lookup: dict[str, ndarray] = {}
        for ipa_symbol, basis_idx in _IPA_TO_Q28_INDEX.items():
            lookup[ipa_symbol] = self._basis_matrix[basis_idx].copy()
        return lookup

    def _build_root_signatures(self) -> dict[str, ndarray]:
        """Compute average Q28 vector for each known Arabic root."""
        signatures: dict[str, ndarray] = {}
        for root, ipa_approx in _ROOT_IPA_SIGNATURES.items():
            chars = _ipa_string_to_chars(ipa_approx)
            vectors = [self._ipa_to_q28[ch] for ch in chars if ch in self._ipa_to_q28]
            if vectors:
                signatures[root] = np.mean(vectors, axis=0)
        return signatures

    def ipa_to_q28(self, ipa_char: str) -> ndarray:
        """Map a single IPA character to its nearest Q28 coordinate (6D vector).

        Uses cosine similarity against the 28-basis matrix when the symbol
        is not in the direct lookup table.
        """
        if ipa_char in self._ipa_to_q28:
            return self._ipa_to_q28[ipa_char].copy()
        return self._nearest_by_cosine(ipa_char)

    def _nearest_by_cosine(self, ipa_char: str) -> ndarray:
        """Find nearest basis vector via cosine similarity for unknown IPA."""
        # Build a crude feature vector from character ordinal as fallback seed
        seed = np.array([ord(ipa_char) % 128 / 128.0] * 6, dtype=np.float64)
        best_idx = max(
            range(len(self._basis_matrix)),
            key=lambda i: _cosine_similarity(seed, self._basis_matrix[i]),
        )
        return self._basis_matrix[best_idx].copy()

    def text_to_q28(self, text: str, lang: str = "en") -> list[ndarray]:
        """Convert text to Q28 coordinates via IPA intermediate representation.

        Attempts to use epitran for accurate text→IPA conversion. Falls back
        to a built-in approximation table when epitran is not installed.

        Args:
            text: Input text to convert.
            lang: ISO 639-1 language code (default 'en' for English).

        Returns:
            List of 6D Q28 vectors, one per recognized phoneme.
        """
        ipa_string = self._text_to_ipa(text, lang)
        phonemes = _ipa_string_to_chars(ipa_string)
        return [self.ipa_to_q28(ph) for ph in phonemes if ph.strip()]

    def _text_to_ipa(self, text: str, lang: str) -> str:
        """Convert text to IPA using epitran or the fallback table."""
        epitran_mod = _try_import_epitran()
        if epitran_mod is not None:
            return self._epitran_convert(epitran_mod, text, lang)
        return self._fallback_ipa(text, lang)

    def _epitran_convert(self, epitran_mod: object, text: str, lang: str) -> str:
        """Use epitran library for accurate text→IPA conversion."""
        lang_codes: dict[str, str] = {
            "en": "eng-Latn",
            "ar": "ara-Arab",
            "fr": "fra-Latn",
            "de": "deu-Latn",
            "es": "spa-Latn",
            "tr": "tur-Latn",
            "fa": "fas-Arab",
            "ur": "urd-Arab",
        }
        epitran_lang = lang_codes.get(lang, f"{lang}-Latn")
        epi = epitran_mod.Epitran(epitran_lang)  # type: ignore[attr-defined]
        return epi.transliterate(text)

    def _fallback_ipa(self, text: str, lang: str) -> str:
        """Produce approximate IPA from text using built-in tables."""
        words = text.lower().split()
        return " ".join(_word_to_ipa_fallback(word) for word in words)

    def q28_to_root_hint(self, q28_coords: list[ndarray]) -> str:
        """Find the closest Arabic root by articulatory similarity.

        Averages the Q28 vectors for the word, then finds the root whose
        articulatory signature has the highest cosine similarity.

        Args:
            q28_coords: List of 6D Q28 vectors representing a word.

        Returns:
            The closest Arabic root string, or '<unknown>' if no match.
        """
        if not q28_coords or not self._root_signatures:
            return "<unknown>"
        word_vector = np.mean(q28_coords, axis=0)
        return max(
            self._root_signatures,
            key=lambda root: _cosine_similarity(word_vector, self._root_signatures[root]),
        )

    @property
    def basis_matrix(self) -> ndarray:
        """Return the 28×6 basis matrix (read-only copy)."""
        return self._basis_matrix.copy()

    @property
    def letters(self) -> list[str]:
        """Return the 28 Arabic letter symbols in order."""
        return list(self._letters)

    @property
    def ipa_symbols(self) -> list[str]:
        """Return the IPA symbol for each of the 28 Arabic letters."""
        return list(self._ipa_symbols)
