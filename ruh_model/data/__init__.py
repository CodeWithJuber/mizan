"""ruh_model.data — training-data package.

Implements the training-data modules used by ``ruh_model.train``:
``collator`` (batch padding + next-token labels), ``dataset`` (JSONL
tokenization), and ``generator`` (seed-data generation from ARABIC_ROOTS).
``scripture`` holds the rule that scripture is never a training target.

The Torch-backed classes load on first use, so the Torch-free modules
(``scripture``, ``sequence``, ``quranic``, ``pipeline``) import without Torch.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ruh_model.data.collator import RuhCollator
    from ruh_model.data.dataset import RuhDataset
    from ruh_model.data.generator import SeedDataGenerator

__all__ = ["RuhCollator", "RuhDataset", "SeedDataGenerator"]


def __getattr__(name: str):
    if name == "RuhCollator":
        from ruh_model.data.collator import RuhCollator

        return RuhCollator
    if name == "RuhDataset":
        from ruh_model.data.dataset import RuhDataset

        return RuhDataset
    if name == "SeedDataGenerator":
        from ruh_model.data.generator import SeedDataGenerator

        return SeedDataGenerator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
