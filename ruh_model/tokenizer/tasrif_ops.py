"""
Tasrif (morphophonemic transformation) operators from Q28 research.

Models 15 phonological processes in connected Arabic speech using 6D
articulatory feature vectors. Feature dimensions:

  [0] place      - place of articulation (0=glottal, 1=velar/uvular, ..., ~palatal)
  [1] manner     - manner of articulation (0=stop, 0.5=fricative, 1=approximant)
  [2] voicing    - voiced (1.0) vs voiceless (0.0)
  [3] nasality   - nasal resonance (0.0=oral, 1.0=nasal)
  [4] emphasis   - pharyngealization/velarization (0.0=plain, 1.0=emphatic)
  [5] length     - segment duration/weight (0.0=short, 1.0=long)
"""

import numpy as np
from numpy import ndarray
from functools import reduce


_CLAMP_MIN = 0.0
_CLAMP_MAX = 1.0


def _clamp(features: ndarray) -> ndarray:
    return np.clip(features, _CLAMP_MIN, _CLAMP_MAX)


def idgham(features: ndarray, target: ndarray | None = None) -> ndarray:
    """Assimilation: adopts place of the following sound."""
    # Without a following sound context, shift place forward by a fixed step
    result = features.copy()
    result[0] = min(features[0] + 0.15, _CLAMP_MAX)
    return _clamp(result)


def iqlab(features: ndarray) -> ndarray:
    """Substitution: nasal replaces target before labial consonants."""
    result = features.copy()
    result[3] = 1.0          # full nasality
    result[0] = 0.2          # labial-ish place
    result[1] = 0.0          # stop manner (nasal stop)
    return _clamp(result)


def ikhfa(features: ndarray) -> ndarray:
    """Concealment: partial nasalization before certain consonants."""
    result = features.copy()
    result[3] = features[3] + 0.5   # raise nasality partway
    result[1] = features[1] * 0.6   # reduce manner toward stop
    return _clamp(result)


def tafkhim(features: ndarray) -> ndarray:
    """Velarization: spread emphasis feature to neighbouring sounds."""
    result = features.copy()
    result[4] = 1.0           # full emphasis
    result[0] = features[0] * 0.8   # pull place slightly posterior
    return _clamp(result)


def tarqiq(features: ndarray) -> ndarray:
    """Thinning: remove emphasis, restoring plain articulation."""
    result = features.copy()
    result[4] = 0.0           # strip emphasis
    result[0] = min(features[0] + 0.1, _CLAMP_MAX)  # anterior shift
    return _clamp(result)


def qalb(features: ndarray) -> ndarray:
    """Metathesis: swap place [0] and manner [1] features."""
    result = features.copy()
    result[0], result[1] = features[1], features[0]
    return _clamp(result)


def ibdal(features: ndarray) -> ndarray:
    """Replacement: one sound category replaces another via place jump."""
    result = features.copy()
    result[0] = 1.0 - features[0]   # mirror place of articulation
    return _clamp(result)


def hazf(features: ndarray) -> ndarray:
    """Deletion / elision: zero out all features."""
    return np.zeros_like(features)


def ziadah(features: ndarray) -> ndarray:
    """Addition / epenthesis: strengthen all features uniformly."""
    result = features.copy()
    result = features + 0.2
    return _clamp(result)


def madd(features: ndarray) -> ndarray:
    """Extension: set length feature to maximum."""
    result = features.copy()
    result[5] = 1.0
    return _clamp(result)


def hamzah(features: ndarray) -> ndarray:
    """Glottalization: shift place toward glottal (0.0)."""
    result = features.copy()
    result[0] = features[0] * 0.3   # compress toward glottal end
    result[2] = 0.0                 # glottal stop is voiceless
    result[1] = 0.0                 # stop manner
    return _clamp(result)


def tashdid(features: ndarray) -> ndarray:
    """Gemination: double intensity by amplifying all features."""
    result = features * 2.0
    return _clamp(result)


def sukun(features: ndarray) -> ndarray:
    """Quiescence: reduce manner toward stop (saakin = no vowel)."""
    result = features.copy()
    result[1] = features[1] * 0.3   # manner collapses toward stop
    result[5] = features[5] * 0.5   # shorten length
    return _clamp(result)


def tanwin(features: ndarray) -> ndarray:
    """Nunation: add nasality feature (as if followed by /n/)."""
    result = features.copy()
    result[3] = min(features[3] + 0.4, _CLAMP_MAX)
    return _clamp(result)


def imaalah(features: ndarray) -> ndarray:
    """Inclination: shift place toward palatal region."""
    result = features.copy()
    result[0] = min(features[0] + 0.35, _CLAMP_MAX)   # anterior/palatal shift
    return _clamp(result)


_OPERATORS: dict[str, callable] = {
    "idgham": idgham,
    "iqlab": iqlab,
    "ikhfa": ikhfa,
    "tafkhim": tafkhim,
    "tarqiq": tarqiq,
    "qalb": qalb,
    "ibdal": ibdal,
    "hazf": hazf,
    "ziadah": ziadah,
    "madd": madd,
    "hamzah": hamzah,
    "tashdid": tashdid,
    "sukun": sukun,
    "tanwin": tanwin,
    "imaalah": imaalah,
}


class TasrifEngine:
    """Applies named Tasrif operators to articulatory feature vectors."""

    def __init__(self) -> None:
        self._operators: dict[str, callable] = dict(_OPERATORS)

    def get_operator_names(self) -> list[str]:
        return list(self._operators.keys())

    def apply(self, op_name: str, features: ndarray) -> ndarray:
        """Apply a single named operator to a 6D feature vector."""
        if features.shape != (6,):
            raise ValueError(f"Expected shape (6,), got {features.shape}")
        operator = self._operators.get(op_name)
        if operator is None:
            raise KeyError(f"Unknown Tasrif operator: '{op_name}'. "
                           f"Valid operators: {self.get_operator_names()}")
        return operator(features)

    def apply_sequence(self, ops: list[str], features: ndarray) -> ndarray:
        """Apply a sequence of operators left-to-right."""
        return reduce(lambda feat, op: self.apply(op, feat), ops, features)
