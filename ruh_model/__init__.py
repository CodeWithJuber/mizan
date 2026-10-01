"""Ruh Model -- Arabic-native language model built on triconsonantal root morphology."""

__version__ = "0.1.0"

from typing import TYPE_CHECKING

from ruh_model.config import RuhConfig

if TYPE_CHECKING:
    from ruh_model.model import RuhModel

__all__ = ["RuhConfig", "RuhModel"]


def __getattr__(name: str):
    # Tokenization and root analysis do not require the optional Torch runtime.
    # Preserve the public model import while loading it only when requested.
    if name == "RuhModel":
        from ruh_model.model import RuhModel

        return RuhModel
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
