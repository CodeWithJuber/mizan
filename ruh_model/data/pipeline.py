"""Bounded, reproducible streaming corpus preparation and tokenized batching.

Defaults are verified full Quran text and pinned Arabic Wikipedia. Custom
religious sources require explicit permission and provenance. No dataset scripts
execute, and audio-reciter duplication is not additional text supervision.
"""

from __future__ import annotations

import json
import os
import random
import tempfile
import warnings
from collections.abc import Iterable, Iterator
from pathlib import Path

from ruh_model.data.collator import RuhCollator
from ruh_model.tokenizer.bayan import BayanTokenizer
from ruh_model.tokenizer.conversation import serialize_messages

DEFAULT_SOURCES = {
    "quran": {
        "kind": "verified_quran",
        "path": "Tanzil/Uthmani-Hafs",
        "revision": "6523a9ad3b73bb7e8cb3a9cdf0ea774b8bab3123",
        "lang": "ar",
        "column": "text",
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
            raise ValueError(
                f"Configure corpus sources for: {', '.join(absent)}. "
                "Hadith has no automatic source; explicitly supply licensed, attributed "
                "sources through RUH_DATA_SOURCES. See docs/quranic_training_paths.md."
            )
        for domain in ("quran", "hadith"):
            if not self.ratios.get(domain):
                continue
            if tokenizer.version != 2:
                raise ValueError("Religious text training requires the lossless Bayan V2 tokenizer")
            spec = self.sources[domain]
            if (
                domain == "quran"
                and isinstance(spec, dict)
                and spec.get("kind") == "verified_quran"
            ):
                continue
            required = {"license", "attribution", "revision", "training_permission"}
            if (
                not isinstance(spec, dict)
                or not required <= spec.keys()
                or any(not spec[key] for key in required)
                or spec["training_permission"] is not True
            ):
                raise ValueError(
                    f"Custom {domain} requires explicit training permission, licence, attribution and revision"
                )
            if domain == "quran" and (not spec.get("edition") or not spec.get("verse_columns")):
                raise ValueError(
                    "Custom Quran requires its exact edition and surah/ayah verse_columns"
                )
            warnings.warn(
                f"Explicit custom {domain} source selected: {spec['attribution']}; "
                "source terms and provenance apply. Complete verse coverage and "
                "Hadith authenticity are not inferred from sample counts.",
                UserWarning,
                stacklevel=2,
            )
        self.loader = loader

    def _rows(self, domain: str) -> Iterable[dict]:
        spec = self.sources[domain]
        if not isinstance(spec, dict):
            return spec
        if domain == "quran" and spec.get("kind") == "verified_quran":
            return self._verified_quran_rows()
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

    @staticmethod
    def _verified_quran_rows():
        from ruh_model.data.quranic import SOURCES, compare_editions, fetch_sources, read_verses

        cache = Path(
            os.getenv("RUH_QURAN_CACHE", str(Path(tempfile.gettempdir()) / "ruh-verified-quran"))
        )
        snapshots = fetch_sources(cache)
        primary = read_verses(snapshots["tanzil"])
        secondary = read_verses(snapshots["qpc_hafs"])
        comparison = compare_editions(primary, secondary)
        if {row["verse_id"] for row in comparison["differences"]} != {
            "2:72",
            "15:7",
            "27:20",
            "36:22",
        }:
            raise ValueError("Unexpected Quran edition comparison; review before training")
        for identity, text in primary.items():
            yield {
                "text": text,
                "verse_id": identity,
                "source_provenance": dict(
                    SOURCES["tanzil"],
                    source_verse_coverage=6236,
                    edition="Tanzil Uthmani Hafs; exact pinned bytes",
                    text_modified=False,
                ),
            }

    def _parquet_rows(self, spec: dict, column: str):
        # ParquetFile with synchronous decoding avoids background Arrow scanners
        # surviving an early corpus limit and aborting the Python interpreter.
        import pyarrow.parquet as parquet
        from huggingface_hub import HfApi, HfFileSystem

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
                    columns = [column, *spec.get("verse_columns", [])]
                    for batch in reader.iter_batches(
                        batch_size=64, columns=columns, use_threads=False
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
        quran_seen: dict[str, str] = {}
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
                provenance = row.get("source_provenance")
                identity = row.get("verse_id")
                if domain == "quran":
                    from ruh_model.data.quranic import CHAPTER_LENGTHS, digest

                    if not identity:
                        columns = spec.get("verse_columns")
                        if not isinstance(columns, list) or len(columns) != 2:
                            raise ValueError("Custom Quran requires two surah/ayah verse columns")
                        s, v = row[columns[0]], row[columns[1]]
                        if (
                            type(s) is not int
                            or type(v) is not int
                            or not 1 <= s <= 114
                            or not 1 <= v <= CHAPTER_LENGTHS[s - 1]
                        ):
                            raise ValueError("Invalid Quran surah/ayah identifier")
                        identity = f"{s}:{v}"
                    try:
                        s, v = map(int, identity.split(":"))
                    except (ValueError, AttributeError, TypeError) as error:
                        raise ValueError("Invalid Quran verse identifier") from error
                    if (
                        identity != f"{s}:{v}"
                        or not 1 <= s <= 114
                        or not 1 <= v <= CHAPTER_LENGTHS[s - 1]
                    ):
                        raise ValueError("Invalid Quran verse identifier")
                    text_hash = digest(text.encode())
                    if identity in quran_seen:
                        if quran_seen[identity] != text_hash:
                            raise ValueError(f"Conflicting Quran texts for verse {identity}")
                        continue  # Reciter duplication is not additional text supervision.
                    quran_seen[identity] = text_hash
                if domain in {"quran", "hadith"} and provenance is None:
                    provenance = {
                        key: spec[key]
                        for key in ("path", "revision", "license", "attribution", "edition")
                        if key in spec
                    }
                if len(text) > 1_000_000:
                    if domain in {"quran", "hadith"}:
                        raise ValueError(
                            "Religious source record exceeds the supported size; text is never rewritten"
                        )
                    text = text[:1_000_000]
                count += 1
                result = {
                    "text": text,
                    "domain": domain,
                    "paraphrase": row.get("paraphrase"),
                    "lang": spec.get("lang", "unknown")
                    if isinstance(spec, dict)
                    else row.get("lang", "unknown"),
                }
                if identity:
                    result["verse_id"] = identity
                if provenance:
                    result["source_provenance"] = provenance
                yield result
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
            if row["domain"] in {"quran", "hadith"}:
                from ruh_model.data.sequence import tokenize_record

                samples = tokenize_record(row, self.tokenizer, self.max_seq_len)
            else:
                tokens = self.tokenizer.encode(row["text"])[: self.max_seq_len]
                sample = {"root_ids": [r for r, p in tokens], "pattern_ids": [p for r, p in tokens]}
                if row.get("paraphrase"):
                    paired = self.tokenizer.encode(row["paraphrase"])[: self.max_seq_len]
                    sample["paraphrase_root_ids"] = [r for r, p in paired]
                    sample["paraphrase_pattern_ids"] = [p for r, p in paired]
                samples = iter([sample])
            for sample in samples:
                batch.append(sample)
                if len(batch) == batch_size:
                    yield collator(batch)
                    batch = []
        if batch:
            yield collator(batch)
