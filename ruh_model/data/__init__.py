"""ruh_model.data — training-data package.

Implements the training-data modules used by ``ruh_model.train``:
``collator`` (batch padding + next-token labels), ``dataset`` (JSONL
tokenization), and ``generator`` (seed-data generation from ARABIC_ROOTS).
"""

from ruh_model.data.collator import RuhCollator
from ruh_model.data.dataset import RuhDataset
from ruh_model.data.generator import SeedDataGenerator

__all__ = ["RuhCollator", "RuhDataset", "SeedDataGenerator"]
