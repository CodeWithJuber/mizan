"""
TDD tests for the research integration layer (WP1a).

These tests are written FIRST (Red phase). They will fail until the modules
backend/research/{paths,schemas,results_loader,findings}.py are implemented.
"""

import sys
from pathlib import Path

import pytest

# conftest.py already inserts backend/ into sys.path


# ---------------------------------------------------------------------------
# test_paths_resolve
# ---------------------------------------------------------------------------


def test_paths_resolve():
    """DATASETS_DIR, RESULTS_DIR, FIGURES_DIR, and FONT_PATH must exist on disk."""
    from research.paths import DATASETS_DIR, FIGURES_DIR, FONT_PATH, RESULTS_DIR

    assert DATASETS_DIR.exists(), f"DATASETS_DIR missing: {DATASETS_DIR}"
    assert RESULTS_DIR.exists(), f"RESULTS_DIR missing: {RESULTS_DIR}"
    assert FIGURES_DIR.exists(), f"FIGURES_DIR missing: {FIGURES_DIR}"
    assert FONT_PATH.exists(), f"FONT_PATH missing: {FONT_PATH}"


# ---------------------------------------------------------------------------
# test_all_result_jsons_load
# ---------------------------------------------------------------------------


def test_all_result_jsons_load():
    """Every name returned by list_results() must load without error."""
    from research.results_loader import list_results, load_result

    names = list_results()
    assert len(names) > 0, "list_results() returned an empty list"

    for name in names:
        result = load_result(name)
        assert isinstance(result, dict), f"load_result({name!r}) did not return a dict"


# ---------------------------------------------------------------------------
# test_load_result_rejects_traversal
# ---------------------------------------------------------------------------


def test_load_result_rejects_traversal():
    """load_result must reject path-traversal names and unknown files."""
    from research.results_loader import load_result

    with pytest.raises((KeyError, FileNotFoundError, ValueError)):
        load_result("../secrets")

    with pytest.raises((KeyError, FileNotFoundError, ValueError)):
        load_result("nonexistent_result_xyz")


# ---------------------------------------------------------------------------
# test_registry_labels_valid
# ---------------------------------------------------------------------------


def test_registry_labels_valid():
    """Every Finding in the registry must carry a valid EpistemicLabel."""
    from research.findings import get_registry
    from research.schemas import EpistemicLabel

    allowed = {"Established", "Inference", "Conjecture", "Open"}
    for finding in get_registry():
        assert finding.epistemic_label in allowed, (
            f"Finding {finding.id!r} has invalid label {finding.epistemic_label!r}"
        )


# ---------------------------------------------------------------------------
# test_registry_files_exist
# ---------------------------------------------------------------------------


def test_registry_files_exist():
    """Non-None results_file entries and all figures must exist on disk."""
    from research.findings import get_registry
    from research.paths import FIGURES_DIR, RESULTS_DIR

    for finding in get_registry():
        if finding.results_file is not None:
            path = RESULTS_DIR / f"{finding.results_file}.json"
            assert path.exists(), (
                f"Finding {finding.id!r}: results_file {finding.results_file!r} not found at {path}"
            )
        for fig in finding.figures:
            fig_path = FIGURES_DIR / fig
            assert fig_path.exists(), (
                f"Finding {finding.id!r}: figure {fig!r} not found at {fig_path}"
            )


# ---------------------------------------------------------------------------
# test_known_numbers
# ---------------------------------------------------------------------------


def test_known_numbers():
    """The meccan_medinan finding must carry the documented key numbers."""
    from research.findings import get_registry

    registry = {f.id: f for f in get_registry()}
    assert "meccan_medinan" in registry, "meccan_medinan finding is missing"

    finding = registry["meccan_medinan"]
    assert finding.key_numbers["auc_vocab"] == pytest.approx(0.816, abs=1e-6)
    assert finding.key_numbers["auc_robust"] == pytest.approx(0.967, abs=1e-6)


# ---------------------------------------------------------------------------
# test_no_heavy_imports
# ---------------------------------------------------------------------------


def test_no_heavy_imports():
    """
    Guard the stdlib-only constraint: verify module source files contain no
    imports of pandas / numpy / sklearn / scipy / matplotlib / networkx.
    """
    import research.findings
    import research.paths
    import research.results_loader
    import research.schemas

    heavy = {"pandas", "numpy", "sklearn", "scipy", "matplotlib", "networkx"}
    modules_to_check = [
        research.paths,
        research.schemas,
        research.results_loader,
        research.findings,
    ]

    for mod in modules_to_check:
        source_path = Path(mod.__file__)
        source_text = source_path.read_text(encoding="utf-8")
        for lib in heavy:
            # Check for import patterns
            assert f"import {lib}" not in source_text, (
                f"Heavy dependency {lib!r} found in {source_path.name}"
            )
            assert f"from {lib}" not in source_text, (
                f"Heavy dependency {lib!r} found in {source_path.name}"
            )
