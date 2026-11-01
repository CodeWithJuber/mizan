"""Ruh service layer — deterministic, torch-free orchestration facades.

NOTE (torch-free): ``ruh_model/__init__.py`` imports torch via ``ruh_model.model``.
In torch-less environments, import the modules in this package by file path
(``importlib.util.spec_from_file_location``) instead of ``import ruh_model.service``.
``analyze.py`` bootstraps stub parent packages so the tokenizer modules load
without executing the real ``__init__`` files. See ``analyze._bootstrap_torch_free``.
"""

__all__: list[str] = []
