"""
Quaternary Encoding (تشفير رباعي) — DNA-Inspired Data Integrity
================================================================

"And We created you in pairs (azwaj)" — Quran 78:8
"Read in the name of your Lord who created — created man from a clinging substance" — Quran 96:1-2

Binary data encoded using a quaternary alphabet (A, C, G, T),
mirroring DNA's information storage:
- 2 bits → 1 quaternary symbol
- 3 symbols → 1 codon (6 bits → 64 possible codons)
- Codons map to semantic categories

Error detection inspired by biological error correction:
- Per-codon XOR parity symbol
- Hamming distance for corruption detection
- Quaternary checksums for integrity verification
"""

import hashlib

# ─── Quaternary Alphabet ──────────────────────────────────────────────────────
# Maps 2-bit pairs to nucleotide symbols (like DNA base pairs)
QUAT_MAP = {0b00: "A", 0b01: "C", 0b10: "G", 0b11: "T"}
QUAT_REVERSE = {"A": 0b00, "C": 0b01, "G": 0b10, "T": 0b11}
VALID_SYMBOLS = frozenset("ACGT")


# ─── Encoding / Decoding ─────────────────────────────────────────────────────


def bytes_to_quaternary(data: bytes) -> str:
    """Convert binary data to quaternary string (A/C/G/T).

    Each byte produces 4 quaternary symbols (2 bits per symbol).

    >>> bytes_to_quaternary(b'\\x00')
    'AAAA'
    >>> bytes_to_quaternary(b'\\xff')
    'TTTT'
    """
    result = []
    for byte in data:
        result.append(QUAT_MAP[(byte >> 6) & 0b11])
        result.append(QUAT_MAP[(byte >> 4) & 0b11])
        result.append(QUAT_MAP[(byte >> 2) & 0b11])
        result.append(QUAT_MAP[byte & 0b11])
    return "".join(result)


def quaternary_to_bytes(quat: str) -> bytes:
    """Convert quaternary string back to binary data.

    >>> quaternary_to_bytes('AAAA')
    b'\\x00'
    >>> quaternary_to_bytes('TTTT')
    b'\\xff'
    """
    # Validate input
    if not all(c in VALID_SYMBOLS for c in quat):
        raise ValueError("Invalid quaternary string: contains non-ACGT characters")

    # Pad to multiple of 4
    padded = quat
    while len(padded) % 4 != 0:
        padded += "A"

    result = bytearray()
    for i in range(0, len(padded), 4):
        byte = (
            (QUAT_REVERSE[padded[i]] << 6)
            | (QUAT_REVERSE[padded[i + 1]] << 4)
            | (QUAT_REVERSE[padded[i + 2]] << 2)
            | QUAT_REVERSE[padded[i + 3]]
        )
        result.append(byte)
    return bytes(result)


# ─── Codon Chunking ──────────────────────────────────────────────────────────
# 3 quaternary symbols = 1 codon (64 possible triplets → semantic categories)

CODON_CATEGORIES = [
    "data", "reference", "separator", "checksum", "metadata", "padding",
]


def _build_codon_table() -> dict[str, str]:
    """Build complete 64-codon to category mapping."""
    alphabet = "ACGT"
    table: dict[str, str] = {}
    idx = 0
    for a in alphabet:
        for b in alphabet:
            for c in alphabet:
                codon = a + b + c
                if codon == "AAA":
                    table[codon] = "start"
                elif codon == "TTT":
                    table[codon] = "stop"
                else:
                    table[codon] = CODON_CATEGORIES[idx % len(CODON_CATEGORIES)]
                    idx += 1
    return table


CODON_TABLE = _build_codon_table()


def to_codons(quat_string: str) -> list[str]:
    """Split quaternary string into triplet codons.

    >>> to_codons('ACGTAC')
    ['ACG', 'TAC']
    """
    # Pad to multiple of 3
    padded = quat_string
    while len(padded) % 3 != 0:
        padded += "A"
    return [padded[i : i + 3] for i in range(0, len(padded), 3)]


def classify_codons(codons: list[str]) -> list[tuple[str, str]]:
    """Classify each codon into its semantic category.

    >>> classify_codons(['AAA', 'TTT'])
    [('AAA', 'start'), ('TTT', 'stop')]
    """
    return [(codon, CODON_TABLE.get(codon, "data")) for codon in codons]


# ─── Error Detection (Parity) ────────────────────────────────────────────────


def compute_parity_symbol(codon: str) -> str:
    """Compute a parity symbol for a codon (XOR of three symbols).

    >>> compute_parity_symbol('ACG')
    'C'
    """
    if len(codon) != 3 or not all(c in VALID_SYMBOLS for c in codon):
        raise ValueError(f"Invalid codon: {codon!r}")
    values = [QUAT_REVERSE[c] for c in codon]
    parity = values[0] ^ values[1] ^ values[2]
    return QUAT_MAP[parity & 0b11]


def encode_with_parity(quat_string: str) -> str:
    """Encode quaternary string with per-codon parity symbols.

    Every 3 data symbols get 1 parity symbol appended (3+1=4 per block).
    """
    codons = to_codons(quat_string)
    result = []
    for codon in codons:
        parity = compute_parity_symbol(codon)
        result.append(codon + parity)
    return "".join(result)


def verify_and_correct(encoded: str) -> tuple[str, bool, int]:
    """Verify parity and detect errors.

    Returns (data_without_parity, is_valid, errors_detected).
    """
    blocks = [encoded[i : i + 4] for i in range(0, len(encoded), 4)]
    corrected_data = []
    errors = 0

    for block in blocks:
        if len(block) < 4:
            corrected_data.append(block[:3] if len(block) >= 3 else block)
            continue

        codon = block[:3]
        stored_parity = block[3]
        expected_parity = compute_parity_symbol(codon)

        if stored_parity == expected_parity:
            corrected_data.append(codon)
        else:
            errors += 1
            # Error detected — pass through data (correction requires
            # additional redundancy beyond single parity)
            corrected_data.append(codon)

    return "".join(corrected_data), errors == 0, errors


# ─── Checksums ────────────────────────────────────────────────────────────────


def quaternary_checksum(content: str) -> str:
    """Generate a quaternary checksum for text content.

    Takes SHA-256 of content, converts first 8 bytes to 32 quaternary symbols.

    >>> len(quaternary_checksum("hello"))
    32
    >>> all(c in 'ACGT' for c in quaternary_checksum("hello"))
    True
    """
    sha = hashlib.sha256(content.encode("utf-8")).digest()
    return bytes_to_quaternary(sha[:8])  # 8 bytes → 32 quaternary symbols


def hamming_distance(a: str, b: str) -> int:
    """Compute Hamming distance between two quaternary strings.

    Counts the number of symbol positions where the two strings differ.

    >>> hamming_distance('ACGT', 'ACGT')
    0
    >>> hamming_distance('ACGT', 'TCGA')
    4
    """
    return sum(1 for x, y in zip(a, b, strict=False) if x != y)


def verify_checksum(content: str, stored_checksum: str, tolerance: int = 0) -> bool:
    """Verify content against a stored quaternary checksum.

    Args:
        content: The text content to verify.
        stored_checksum: The quaternary checksum to verify against.
        tolerance: Maximum Hamming distance allowed (0 = exact match).

    Returns:
        True if the content matches within tolerance.
    """
    if not stored_checksum:
        return True  # No checksum to verify against
    actual = quaternary_checksum(content)
    dist = hamming_distance(actual, stored_checksum)
    return dist <= tolerance
