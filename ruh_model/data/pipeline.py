"""Bounded, reproducible streaming corpus preparation and tokenized batching.

Default sources are pinned public parquet corpora. Custom domain sources can be
supplied as a mapping or RUH_DATA_SOURCES JSON file. No dataset scripts execute.
"""

from __future__ import annotations

import json
import os
import random
from pathlib import Path
from collections.abc import Iterable, Iterator

from ruh_model.data.collator import RuhCollator
from ruh_model.tokenizer.bayan import BayanTokenizer
from ruh_model.tokenizer.conversation import serialize_messages

DEFAULT_SOURCES = {
    "quran": {
        "path": "Buraaq/quran-md-ayahs",
        "revision": "669e9c4b78716d4558cebab98e1072564801fbb0",
        "lang": "ar",
        "column": "ayah_ar",
        "files": ["data/train-00000-of-00071.parquet"],
    },
    "hadith": {
        "path": "arbml/Hadith",
        "revision": "44ebe1a07005ee6afd1b0fa316522b18e05a3be1",
        "lang": "ar",
        "column": "Text",
    },
    "arabic_wiki": {
        "path": "wikimedia/wikipedia",
        "name": "20231101.ar",
        "revision": "b04c8d1ceb2f5cd4588862100d08de323dccfbaa",
        "lang": "ar",
    },
}


class RealDataPipeline:
    def __init__(
        self,
        tokenizer: BayanTokenizer,
        max_seq_len: int,
        mixing_ratios: dict[str, float] | None = None,
        *,
        sources: dict | None = None,
        seed: int = 42,
        loader=None,
    ):
        if max_seq_len < 2:
            raise ValueError("max_seq_len must permit a next-token target")
        self.tokenizer, self.max_seq_len, self.seed = tokenizer, max_seq_len, seed
        if sources is None and os.getenv("RUH_DATA_SOURCES"):
            sources = json.loads(Path(os.environ["RUH_DATA_SOURCES"]).read_text())
        self.sources = sources if sources is not None else DEFAULT_SOURCES
        self.ratios = mixing_ratios or {domain: 1.0 for domain in self.sources}
        if any(weight < 0 for weight in self.ratios.values()) or not any(self.ratios.values()):
            raise ValueError("Mixing ratios must be nonnegative with positive total")
        absent = [
            domain
            for domain, weight in self.ratios.items()
            if weight and domain not in self.sources
        ]
        if absent:
            raise ValueError(f"Configure corpus sources for: {', '.join(absent)}")
        self.loader = loader

    def _rows(self, domain: str) -> Iterable[dict]:
        spec = self.sources[domain]
        if not isinstance(spec, dict):
            return spec
        column = spec.get("column", "text")
        if self.loader is not None:
            return self.loader(
                spec["path"],
                name=spec.get("name"),
                split=spec.get("split", "train"),
                revision=spec["revision"],
                streaming=True,
            )
        return self._parquet_rows(spec, column)

    def _parquet_rows(self, spec: dict, column: str):
        # ParquetFile with synchronous decoding avoids background Arrow scanners
        # surviving an early corpus limit and aborting the Python interpreter.
        from huggingface_hub import HfApi, HfFileSystem
        import pyarrow.parquet as parquet

        filesystem = HfFileSystem()
        files = spec.get("files")
        if files is None:
            files = HfApi().list_repo_files(
                spec["path"], revision=spec["revision"], repo_type="dataset"
            )
            prefix = spec.get("name", "")
            files = [
                file
                for file in files
                if file.endswith(".parquet")
                and (not prefix or file.startswith(prefix + "/"))
                and Path(file).name.startswith(spec.get("split", "train") + "-")
            ]
        if not files:
            raise ValueError("Corpus has no parquet files; configure a supported source")
        for filename in files:
            path = f"datasets/{spec['path']}@{spec['revision']}/{filename}"
            with filesystem.open(path, "rb") as handle:
                reader = parquet.ParquetFile(handle, pre_buffer=False)
                try:
                    for batch in reader.iter_batches(
                        batch_size=64, columns=[column], use_threads=False
                    ):
                        yield from batch.to_pylist()
                finally:
                    reader.close()

    def stream(self, max_samples: int) -> Iterator[dict]:
        if max_samples < 0:
            raise ValueError("max_samples must be nonnegative")
        rng = random.Random(self.seed)
        streams = {
            domain: iter(self._rows(domain)) for domain, weight in self.ratios.items() if weight > 0
        }
        count = 0
        try:
            while streams and count < max_samples:
                domain = rng.choices(list(streams), weights=[self.ratios[d] for d in streams])[0]
                try:
                    row = next(streams[domain])
                except StopIteration:
                    del streams[domain]
                    continue
                spec = self.sources[domain]
                column = spec.get("column", "text") if isinstance(spec, dict) else "text"
                text = row.get(column, "")
                if row.get("messages"):
                    text = serialize_messages(row["messages"], assistant_prefix=False)
                if not isinstance(text, str) or not text.strip():
                    continue
                if len(text) > 1_000_000:
                    text = text[:1_000_000]
                count += 1
                yield {
                    "text": text,
                    "domain": domain,
                    "paraphrase": row.get("paraphrase"),
                    "lang": spec.get("lang", "unknown")
                    if isinstance(spec, dict)
                    else row.get("lang", "unknown"),
                }
        finally:
            for stream in streams.values():
                close = getattr(stream, "close", None)
                if close:
                    close()
            streams.clear()
        if max_samples and not count:
            raise ValueError("No nonempty text records found; check corpus column mappings")

    def get_dataloader(self, max_samples: int, batch_size: int, shuffle: bool = True):
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        collator = RuhCollator()
        batch = []
        for row in self.stream(max_samples):
            tokens = self.tokenizer.encode(row["text"])[: self.max_seq_len]
            sample = {"root_ids": [r for r, p in tokens], "pattern_ids": [p for r, p in tokens]}
            if row.get("paraphrase"):
                paired = self.tokenizer.encode(row["paraphrase"])[: self.max_seq_len]
                sample["paraphrase_root_ids"] = [r for r, p in paired]
                sample["paraphrase_pattern_ids"] = [p for r, p in paired]
            batch.append(sample)
            if len(batch) == batch_size:
                yield collator(batch)
                batch = []
        if batch:
            yield collator(batch)
