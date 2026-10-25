"""Shared token boundaries and lookup keys; never a root/lemma guesser."""

import unicodedata


def lookup_key(text: str) -> str:
    """Normalize marks/tatweel for lookup only, retaining radical distinctions."""
    return "".join(
        ch
        for ch in unicodedata.normalize("NFKC", text)
        if not unicodedata.category(ch).startswith("M") and ch != "ـ"
    )


def arabic_tokens(text: str, limit: int = 5) -> list[str]:
    """Distinct Arabic letter/mark sequences, without digits or punctuation.

    Keep original diacritics for the frozen WSD feature extractor. A token is
    an observed surface form, not an inferred morphological lemma.
    """
    if limit <= 0:
        return []
    tokens: list[str] = []
    current = ""
    for ch in text + " ":
        if "ARABIC" in unicodedata.name(ch, "") and unicodedata.category(ch)[0] in "LM":
            current += ch
        else:
            if current and any(unicodedata.category(c).startswith("L") for c in current):
                if current not in tokens:
                    tokens.append(current)
                    if len(tokens) >= limit:
                        return tokens
            current = ""
    return tokens
