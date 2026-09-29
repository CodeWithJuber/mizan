"""ruh_model.data — training-data package (STUB).

This package is intentionally minimal: the training-data modules referenced
by ``ruh_model.train`` (``collator``, ``dataset``, ``generator``) are not
implemented in this repository yet. Importing them raises an informative
error instead of failing with a bare ``ModuleNotFoundError``.

Real-data training currently goes through ``ruh_model/train_full.py``
(HuggingFace datasets path). This stub exists so the package layout is
honest about what is and is not here.
"""

__all__ = []


def __getattr__(name: str):
    raise ImportError(
        f"ruh_model.data.{name} is not implemented yet — "
        "the training-data modules (collator, dataset, generator) are stubs. "
        "Use ruh_model/train_full.py for the HuggingFace-datasets training path."
    )
