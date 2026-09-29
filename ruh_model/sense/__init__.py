"""Ruh sense inventory + disambiguation (torch-free subpackage).

Versioned sense inventory, provenance receipts, and a deterministic
context-overlap disambiguator. Everything here runs on the stdlib only —
no torch, no sklearn — so it works in minimal (``[dev, nlp]``) installs.

Public surface::

    from ruh_model.sense import (
        SenseEntry, SenseInventory, load_inventory_jsonl,
        ProvenanceSignal, build_receipt,
        disambiguate, Disambiguation,
    )

NOTE (torch-less environments): ``ruh_model/__init__.py`` imports torch via
``ruh_model.model``. Importing ``ruh_model.sense`` in an env without torch
fails at the *parent* package ``__init__``. The modules in this subpackage
therefore resolve each other through a guarded loader (normal import first,
file-path fallback) instead of plain top-level imports. Consumers in
torch-less envs should load these modules by file path with
``importlib.util.spec_from_file_location``.
"""

from ruh_model.sense.disambiguate import (
    DEFAULT_THRESHOLD,
    RELIGIOUS_THRESHOLD,
    Disambiguation,
    SenseAlternative,
    disambiguate,
)
from ruh_model.sense.inventory import (
    INVENTORY_VERSION,
    SenseEntry,
    SenseInventory,
    build_inventory,
    dump_inventory_jsonl,
    load_inventory_jsonl,
    normalize_sense_id,
)
from ruh_model.sense.provenance import (
    KNOWN_SIGNALS,
    ProvenanceSignal,
    build_receipt,
)

__all__ = [
    "DEFAULT_THRESHOLD",
    "INVENTORY_VERSION",
    "KNOWN_SIGNALS",
    "RELIGIOUS_THRESHOLD",
    "Disambiguation",
    "ProvenanceSignal",
    "SenseAlternative",
    "SenseEntry",
    "SenseInventory",
    "build_inventory",
    "build_receipt",
    "disambiguate",
    "dump_inventory_jsonl",
    "load_inventory_jsonl",
    "normalize_sense_id",
]
