"""
Single source of truth for on-disk locations used by the research package.

All paths are derived from the location of this file so the package is
relocatable.  No heavy dependencies — stdlib pathlib only.
"""

from pathlib import Path

# Package root: backend/research/
PACKAGE_DIR: Path = Path(__file__).parent

# Corpus data
DATASETS_DIR: Path = PACKAGE_DIR / "datasets"
RAW_DIR: Path = DATASETS_DIR / "raw"

# Experiment outputs
RESULTS_DIR: Path = PACKAGE_DIR / "results"

# Scratch space (may not exist yet)
OUTPUT_DIR: Path = PACKAGE_DIR / "output"

# SQLite database (created on first use)
DB_PATH: Path = PACKAGE_DIR / "research.db"

# Arabic font bundled with the raw data
FONT_PATH: Path = RAW_DIR / "arabic_font.ttf"

# Figures live two levels up from backend/research/ → repo-root/docs/research/figures
# PACKAGE_DIR.parent = backend/
# PACKAGE_DIR.parent.parent = repo root
FIGURES_DIR: Path = PACKAGE_DIR.parent.parent / "docs" / "research" / "figures"

# CSV encoding: files carry a UTF-8 BOM produced by Excel/pandas
CSV_ENCODING: str = "utf-8-sig"

# Canonical SHA-256 of the corpus CSV for integrity checks
CORPUS_SHA256: str = "742bfac59941b2cb09736d5b7aae694af50792261fb8450cbf6afafcc340645f"


def result_path(name: str) -> Path:
    """Return the absolute path for a named result JSON file."""
    return RESULTS_DIR / f"{name}.json"


def figure_path(name: str) -> Path:
    """Return the absolute path for a named figure file."""
    return FIGURES_DIR / name
