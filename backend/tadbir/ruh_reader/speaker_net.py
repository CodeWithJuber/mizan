"""The Ruh speaker's network and training loop (needs torch and numpy).

Imported only to train, score or generate, as ``net`` is for the reader. The
network is the reader's family, grown: the same pre-norm ``net.Block``
(RMSNorm, rotary positions, SwiGLU, causal attention), the output layer tied
to the token embedding, and a KV cache for decoding. What differs is the
vocabulary (``speaker.CONFIGS``: the byte-level BPE of the pilot, or the
reader's bytes) and the size.

**Training** reads windows of ``context + 1`` tokens from the shards
(``speaker.write_shards``), each window's start drawn uniformly over every
token of every training shard by a generator seeded with (seed, step,
micro-batch). The data a step sees is therefore a function of the step alone,
and a run resumed from a checkpoint continues exactly where it stopped: the
test checks that 2 + 2 steps give the same weights as 4. AdamW (β = 0.9,
0.95; no decay on the embedding and the norms), the learning rate warmed up
and then a cosine to ``min_lr`` of its peak by the last step or the end of the
time given, whichever comes first, so a run the clock ends still anneals (as
``net.train`` does). bfloat16 autocast on CUDA, gradients clipped to 1.

**Checkpoints** (``checkpoints/step-NNNNNNNN/``: weights, optimizer, state)
carry a ``manifest.json`` with each file's SHA-256, are written to a temporary
folder and renamed whole, and ``latest.json`` (the checkpoint's path and its
manifest's SHA-256) is replaced last. Resuming reads the newest checkpoint
whose files match their SHA-256 and whose run key (the configuration, the plan
and the shards' SHA-256) is this run's; another run's checkpoint is never
continued. ``final/`` holds the weights, the tokenizer, the held-out report and
their SHA-256 manifest: what comes back from the pod.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import shutil
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from . import net, speaker


@dataclass(frozen=True)
class Config:
    vocab: int
    d_model: int
    layers: int
    heads: int
    d_ff: int
    context: int
    dropout: float = 0.0
    codec: str = "bytes"

    @classmethod
    def of(cls, values: dict) -> Config:
        names = {item.name for item in fields(cls)}
        return cls(**{key: value for key, value in values.items() if key in names})

    def blocks(self) -> net.Config:
        return net.Config(
            d_model=self.d_model,
            layers=self.layers,
            heads=self.heads,
            d_ff=self.d_ff,
            context=self.context,
            dropout=self.dropout,
        )

    def to_dict(self) -> dict:
        return asdict(self)


class Speaker(nn.Module):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        inner = config.blocks()
        self.embed = nn.Embedding(config.vocab, config.d_model)
        self.blocks = nn.ModuleList(net.Block(inner) for _ in range(config.layers))
        self.norm = net.RMSNorm(config.d_model)
        cos, sin = net._rotary(config.d_model // config.heads, config.context + 1)
        self.register_buffer("cos", cos, persistent=False)
        self.register_buffer("sin", sin, persistent=False)
        nn.init.normal_(self.embed.weight, std=0.02)
        for block in self.blocks:
            for layer in (block.qkv, block.gate, block.up):
                nn.init.normal_(layer.weight, std=0.02)
            for layer in (block.out, block.down):  # residual branches scaled by depth
                nn.init.normal_(layer.weight, std=0.02 / math.sqrt(2 * config.layers))

    def parameters_count(self) -> int:
        return sum(p.numel() for p in self.parameters())

    def forward(
        self,
        tokens: torch.Tensor,
        cache: list[tuple[torch.Tensor, torch.Tensor]] | None = None,
    ) -> tuple[torch.Tensor, list[tuple[torch.Tensor, torch.Tensor]]]:
        """Next-token logits for each position; with ``cache`` the tokens
        continue the cached prefix."""
        start = cache[0][0].shape[2] if cache else 0
        length = tokens.shape[1]
        cos = self.cos[start : start + length]
        sin = self.sin[start : start + length]
        x = self.embed(tokens)
        kept = []
        for index, block in enumerate(self.blocks):
            x, kv = block(x, cos, sin, cache[index] if cache else None)
            kept.append(kv)
        return F.linear(self.norm(x), self.embed.weight), kept


def flops_per_token(config: Config, parameters: int) -> float:
    """Training FLOPs per token: 6N for the weights (the tied output layer
    counted once, as a matmul it is) and 6·L·T·d for attention over the
    context (Kaplan et al. 2020, with T the full context)."""
    return 6.0 * parameters + 6.0 * config.layers * config.context * config.d_model


# ── the data ─────────────────────────────────────────────────────────────


class Windows:
    """Windows of ``context + 1`` tokens drawn uniformly over the shards."""

    def __init__(self, shards: Path, items: Sequence[dict], context: int):
        self.context = context
        self.arrays = [
            np.memmap(shards / item["file"], dtype="<u2", mode="r")
            for item in items
            if item["tokens"] > context + 1
        ]
        if not self.arrays:
            raise ValueError("no training shard is longer than the context")
        self.starts = np.array([len(array) - context for array in self.arrays], dtype=np.int64)
        self.ends = np.cumsum(self.starts)

    def batch(self, seed: int, step: int, micro: int, size: int) -> torch.Tensor:
        rng = np.random.default_rng([seed, step, micro])
        picks = rng.integers(0, int(self.ends[-1]), size=size)
        shard = np.searchsorted(self.ends, picks, side="right")
        offset = picks - (self.ends[shard] - self.starts[shard])
        rows = np.stack(
            [
                self.arrays[s][o : o + self.context + 1]
                for s, o in zip(shard.tolist(), offset.tolist(), strict=True)
            ]
        )
        return torch.from_numpy(rows.astype(np.int64))


# ── checkpoints ──────────────────────────────────────────────────────────


def _plain(model: nn.Module) -> nn.Module:
    return getattr(model, "_orig_mod", model)  # a compiled model's own module


def _sha256(path: Path) -> str:
    return speaker._sha256(path)


def run_key(manifest: dict, config: Config, plan: dict) -> str:
    """What a checkpoint must share to be continued: configuration, plan
    (whether it is compiled aside) and the training shards' SHA-256."""
    body = {
        "config": config.to_dict(),
        "plan": {key: value for key, value in plan.items() if key != "compile"},
        "shards": sorted(item["sha256"] for item in manifest["train"]),
        "codec": manifest["codec"],
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def _manifest(folder: Path, names: Sequence[str]) -> dict:
    return {
        name: {"sha256": _sha256(folder / name), "bytes": (folder / name).stat().st_size}
        for name in names
    }


def _replace_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=1), encoding="utf-8")
    temporary.replace(path)


def save_checkpoint(
    out: Path, model: nn.Module, optimizer: torch.optim.Optimizer, state: dict, keep: int = 2
) -> Path:
    folder = out / "checkpoints"
    name = f"step-{state['step']:08d}"
    temporary = folder / f"{name}.tmp"
    shutil.rmtree(temporary, ignore_errors=True)
    temporary.mkdir(parents=True)
    torch.save(_plain(model).state_dict(), temporary / "model.pt")
    torch.save(optimizer.state_dict(), temporary / "optimizer.pt")
    (temporary / "state.json").write_text(json.dumps(state, indent=1), encoding="utf-8")
    files = _manifest(temporary, ("model.pt", "optimizer.pt", "state.json"))
    (temporary / "manifest.json").write_text(
        json.dumps({"step": state["step"], "files": files}, indent=1), encoding="utf-8"
    )
    final = folder / name
    shutil.rmtree(final, ignore_errors=True)
    temporary.rename(final)
    _replace_json(
        out / "latest.json",
        {"path": f"checkpoints/{name}", "manifest_sha256": _sha256(final / "manifest.json")},
    )
    kept = sorted(path for path in folder.glob("step-*") if not path.name.endswith(".tmp"))
    for old in kept[:-keep]:
        if old != final:
            shutil.rmtree(old, ignore_errors=True)
    return final


def verified(folder: Path) -> dict | None:
    """The checkpoint's state when every file matches its SHA-256."""
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        for name, item in manifest["files"].items():
            if _sha256(folder / name) != item["sha256"]:
                return None
        return dict(json.loads((folder / "state.json").read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError):
        return None


def resume(
    out: Path,
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
    key: str,
    device: str,
    log: Callable[[str], None] = print,
) -> dict | None:
    """Load the newest whole checkpoint of this run (``latest.json`` first,
    then the others, newest first); None when there is none."""
    candidates: list[Path] = []
    try:
        pointer = json.loads((out / "latest.json").read_text(encoding="utf-8"))
        candidates.append(out / pointer["path"])
    except (OSError, ValueError, KeyError):
        pass
    candidates += sorted(
        (p for p in (out / "checkpoints").glob("step-*") if not p.name.endswith(".tmp")),
        reverse=True,
    )
    for folder in dict.fromkeys(candidates):
        state = verified(folder)
        if state is None:
            log(f"speaker: {folder.name} does not match its SHA-256; not resumed")
            continue
        if state.get("key") != key:
            log(f"speaker: {folder.name} belongs to another run; not resumed")
            continue
        model.load_state_dict(torch.load(folder / "model.pt", map_location=device))
        optimizer.load_state_dict(torch.load(folder / "optimizer.pt", map_location=device))
        log(f"speaker: resumed from {folder.name}")
        return state
    return None


# ── evaluation ───────────────────────────────────────────────────────────


def _special_table(codec: Any, vocab: int, device: str) -> torch.Tensor:
    table = torch.zeros(vocab, dtype=torch.bool, device=device)
    for token in range(vocab):
        if codec.special(token):
            table[token] = True
    return table


@torch.no_grad()
def held_out_bpb(
    model: nn.Module, shards: Path, manifest: dict, device: str = "cpu", rows: int = 16
) -> dict[str, dict]:
    """Bits per byte of each language's held-out documents: the nats of
    predicting their text tokens (not the language and end tokens, which are
    structure), over the UTF-8 bytes of their text. The stream is read in
    windows of the context, each from its own start."""
    model.eval()
    config: Config = _plain(model).config  # type: ignore[assignment]
    codec = speaker.codec_of(shards, manifest["codec"])
    special = _special_table(codec, config.vocab, device)
    found: dict[str, dict] = {}
    for item in manifest["held_out"]:
        stream = np.memmap(shards / item["file"], dtype="<u2", mode="r")
        width = config.context + 1
        starts = list(range(0, max(1, len(stream) - 1), config.context))
        nats, counted = 0.0, 0
        for begin in range(0, len(starts), rows):
            chunks = [
                np.asarray(stream[s : s + width], dtype=np.int64)
                for s in starts[begin : begin + rows]
                if len(stream) - s >= 2
            ]
            if not chunks:
                continue
            longest = max(len(chunk) for chunk in chunks)
            padded = np.full((len(chunks), longest), codec.end, dtype=np.int64)
            real = np.zeros((len(chunks), longest - 1), dtype=bool)
            for row, chunk in enumerate(chunks):
                padded[row, : len(chunk)] = chunk
                real[row, : len(chunk) - 1] = True
            tokens = torch.from_numpy(padded).to(device)
            inputs, targets = tokens[:, :-1], tokens[:, 1:]
            logits, _ = model(inputs)
            picked = torch.log_softmax(logits.float(), -1).gather(-1, targets[..., None])[..., 0]
            mask = torch.from_numpy(real).to(device) & ~special[targets]
            nats -= float((picked * mask).sum())
            counted += int(mask.sum())
        found[item["language"]] = {
            "bpb": round(nats / max(1, item["bytes"]) / math.log(2), 4),
            "tokens": counted,
            "bytes": item["bytes"],
            "bytes_per_token": round(item["bytes"] / max(1, counted), 3),
        }
    model.train()
    return found


@torch.no_grad()
def score(
    model: nn.Module, codec: Any, texts: Sequence[str], slots: Sequence[int]
) -> tuple[list[list[float]], list[int]]:
    """log P(text | language) in nats for each text under each slot's language
    token (its tokens, not the end), and each text's UTF-8 bytes: what the
    reader's posterior reads (``ruh_reader.reader_log_posterior``, n in bytes)."""
    model.eval()
    context = _plain(model).config.context  # type: ignore[union-attr]
    found: list[list[float]] = []
    for ids in codec.encode(list(texts)):
        ids = ids[:context]
        if not ids:
            found.append([0.0] * len(slots))
            continue
        rows = torch.tensor([[codec.lang(slot), *ids[:-1]] for slot in slots])
        targets = torch.tensor([ids] * len(slots))
        logits, _ = model(rows)
        picked = torch.log_softmax(logits.float(), -1).gather(-1, targets[..., None])[..., 0]
        found.append(picked.sum(-1).tolist())
    return found, [len(text.encode("utf-8")) for text in texts]


def score_reads(
    model: nn.Module, codec: Any, reads: Sequence[Any], languages: Sequence[str], using: Any = None
) -> None:
    """Fill each ``ruh_reader.Read`` with the speaker's log P(x | l): the
    message's own words as written (``lughah.own_words``; the reader reads them
    lower-cased, the speaker learned text as people write it), n in their bytes."""
    from .. import lughah

    slots = [speaker.LANGUAGES.index(code) for code in languages]
    own = [lughah.own_words(read.text, using) if read.own else "" for read in reads]
    found, sizes = score(model, codec, own, slots)
    for read, likelihoods, size in zip(reads, found, sizes, strict=True):
        if read.own:
            read.lm, read.tokens = likelihoods, size


def gate_on_validation(
    model: nn.Module,
    codec: Any,
    rows: Sequence[tuple[str, str, str, str]],
    languages: Sequence[str],
    using: Any = None,
    test: int = 1,
) -> dict:
    """The reader's gate with the speaker in the reader's place (E2 of
    ``docs/ruh-speaker.md``): v1.1's validation rows (text, label, group,
    half), read by ``using`` (the held-out Lughah); κ, γ and b fitted on the
    calibration half with ñ the median bytes there; the gate run on the gate
    half as the speaker's ``test``-th test (e-value k(k+1)/α)."""
    from .. import ruh_reader
    from .corpus import HALVES

    halves: dict[str, list[Any]] = {}
    for name in HALVES:
        chosen = [row for row in rows if row[3] == name and row[1] in languages]
        reads = ruh_reader.read_with_lughah(
            [(text, label) for text, label, _group, _half in chosen], languages, using, ()
        )
        for read, row in zip(reads, chosen, strict=True):
            read.group = row[2]  # a MASSIVE request in every language is one group
        score_reads(model, codec, reads, languages, using)
        halves[name] = reads
    sizes = sorted(read.tokens for read in halves["calibration"] if read.own)
    fit = ruh_reader.fit_on(halves["calibration"], float(sizes[len(sizes) // 2] if sizes else 1))
    gated = halves["gate"]
    arms = ruh_reader.arms(gated, fit)
    verdict = ruh_reader.gate(
        [r.truth for r in gated], [r.group for r in gated], arms["lughah"], arms["combined"], test
    )
    return {
        "test": test,
        "fit": fit.to_dict(),
        "gate": verdict,
        "adopted": bool(verdict["adopted"]) and fit.b > 0,
        "gate_bpb": ruh_reader.bits_per_byte(gated, languages),
        "sizes": {name: len(reads) for name, reads in halves.items()},
    }


@torch.no_grad()
def generate(model: nn.Module, codec: Any, slot: int, prompt: str, new: int) -> str:
    """Greedy continuation of ``prompt`` in language ``slot``, decoded with
    the KV cache (each new token runs one position through the model)."""
    model.eval()
    context = _plain(model).config.context  # type: ignore[union-attr]
    tokens = [codec.lang(slot), *codec.encode([prompt])[0]]
    logits, cache = model(torch.tensor([tokens]))
    made: list[int] = []
    for _ in range(new):
        following = int(logits[0, -1].argmax())
        if following == codec.end or len(tokens) + len(made) >= context:
            break
        made.append(following)
        logits, cache = model(torch.tensor([[following]]), cache)
    return str(codec.decode(made))


# ── training ─────────────────────────────────────────────────────────────


def learning_rate(plan: dict, step: int, total: int, clock: float) -> float:
    """Warm-up, then a cosine to ``min_lr`` of the peak by the last step or
    the end of the time (``clock``: the share of it used), whichever is first."""
    peak, warmup, low = float(plan["lr"]), int(plan["warmup"]), float(plan["min_lr"])
    if step < warmup:
        return peak * (step + 1) / warmup
    progress = max((step - warmup) / max(1, total - warmup), clock)
    return peak * (low + (1 - low) * 0.5 * (1 + math.cos(math.pi * min(1.0, progress))))


def _optimizer(model: nn.Module, plan: dict, device: str) -> torch.optim.Optimizer:
    decay: list[nn.Parameter] = []
    keep: list[nn.Parameter] = []
    for name, parameter in model.named_parameters():
        (decay if parameter.dim() >= 2 and "embed" not in name else keep).append(parameter)
    return torch.optim.AdamW(
        [
            {"params": decay, "weight_decay": plan["weight_decay"]},
            {"params": keep, "weight_decay": 0.0},
        ],
        lr=plan["lr"],
        betas=(0.9, 0.95),
        fused=device == "cuda",
    )


def save_final(out: Path, model: nn.Module, shards: Path, manifest: dict, report: dict) -> dict:
    """``final/``: the weights with their configuration, the tokenizer (when
    there is one), the report, and the SHA-256 of each."""
    folder = out / "final"
    folder.mkdir(parents=True, exist_ok=True)
    plain = _plain(model)
    torch.save(
        {
            "config": plain.config.to_dict(),  # type: ignore[operator]
            "codec": manifest["codec"],
            "languages": manifest["languages"],
            "state": plain.state_dict(),
        },
        folder / "model.pt",
    )
    names = ["model.pt", "report.json"]
    if manifest["codec"]["kind"] == "bpe":
        shutil.copyfile(shards / "tokenizer.json", folder / "tokenizer.json")
        names.append("tokenizer.json")
    (folder / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    files = _manifest(folder, names)
    (folder / "manifest.json").write_text(json.dumps({"files": files}, indent=1), encoding="utf-8")
    return files


def load_final(folder: Path) -> tuple[Speaker, Any]:
    """The speaker and its codec from ``final/``, after every file matches
    its SHA-256."""
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    for name, item in manifest["files"].items():
        if _sha256(folder / name) != item["sha256"]:
            raise speaker.Mismatch(f"{name} does not match its SHA-256")
    saved = torch.load(folder / "model.pt", map_location="cpu", weights_only=True)
    model = Speaker(Config.of(saved["config"]))
    model.load_state_dict(saved["state"])
    model.eval()
    codec = speaker.codec_of(folder, saved["codec"])
    return model, codec


def default_device() -> str:
    """CUDA, then Apple silicon's GPU (Metal, ``mps``), then the CPU."""
    if torch.cuda.is_available():
        return "cuda"
    metal = getattr(torch.backends, "mps", None)
    if metal is not None and metal.is_available():
        return "mps"
    return "cpu"


def _backward_step(
    runner: nn.Module,
    windows: Windows,
    plan: dict,
    step: int,
    rows: int,
    vocab: int,
    device: str,
    autocast: contextlib.AbstractContextManager,
) -> float:
    """Back-propagate one step's micro-batches, ``rows`` windows a pass. The
    windows are the step's own and each part's mean loss is weighted by its
    share of the micro-batch, so the gradient is the one-pass gradient up to
    the order of float sums. Returns the last micro-batch's mean loss."""
    batch, accumulate = plan["batch"], plan["accumulate"]
    seen: list[torch.Tensor] = []
    for micro in range(accumulate):
        seen = []
        for part in windows.batch(plan["seed"], step, micro, batch).split(rows):
            tokens = part.to(device)
            with autocast:
                logits, _ = runner(tokens[:, :-1])
            loss = F.cross_entropy(logits.float().reshape(-1, vocab), tokens[:, 1:].reshape(-1))
            (loss * (len(part) / batch) / accumulate).backward()
            seen.append(loss.detach() * len(part))
    return float(torch.stack(seen).sum() / batch)


def train(
    shards: Path,
    out: Path,
    config: dict,
    plan: dict,
    *,
    seconds: float = math.inf,
    steps: int | None = None,
    stop: Callable[[], bool] = lambda: False,
    device: str | None = None,
    rows: int | None = None,
    log: Callable[[str], None] = print,
) -> dict:
    """Train on the shards for the plan's tokens, within ``seconds`` of this
    call (and at most ``steps`` more steps), resuming this run's newest whole
    checkpoint in ``out``. A checkpoint is written every
    ``checkpoint_seconds`` and when the call ends; ``final/`` is written each
    time it ends. ``rows`` (a divisor of the plan's batch; default all of it)
    is how many windows one forward pass holds: memory only, not the run.
    Returns the report."""
    rows = rows or plan["batch"]
    if rows < 1 or plan["batch"] % rows:
        raise ValueError(f"rows must divide the plan's batch of {plan['batch']}, not {rows}")
    manifest = speaker.verify_shards(shards)
    model_config = Config.of(config)
    device = device or default_device()
    torch.manual_seed(plan["seed"])
    model = Speaker(model_config).to(device)
    optimizer = _optimizer(model, plan, device)
    key = run_key(manifest, model_config, plan)
    out.mkdir(parents=True, exist_ok=True)
    state = resume(out, model, optimizer, key, device, log) or {
        "step": 0,
        "tokens": 0,
        "elapsed": 0.0,
        "key": key,
        "history": [],
        "calls": 0,
    }
    state["calls"] += 1
    before = float(state["elapsed"])
    budget = before + seconds
    per_step = plan["batch"] * plan["accumulate"] * model_config.context
    total = max(1, math.ceil(plan["tokens"] / per_step))
    windows = Windows(shards, manifest["train"], model_config.context)
    runner: nn.Module = model
    if plan.get("compile") and device == "cuda":
        runner = torch.compile(model)  # type: ignore[assignment]
    autocast = (
        torch.autocast("cuda", dtype=torch.bfloat16)
        if device == "cuda"
        else contextlib.nullcontext()
    )
    began = time.monotonic()
    saved_at = began
    ran, ended, last_loss = 0, "done", float("nan")
    model.train()
    while state["step"] < total:
        now = time.monotonic()
        if stop():
            ended = "stopped"
            break
        if before + (now - began) >= budget:
            ended = "time"
            break
        if steps is not None and ran >= steps:
            ended = "steps"
            break
        clock = (before + now - began) / budget if math.isfinite(budget) else 0.0
        rate = learning_rate(plan, state["step"], total, clock)
        for group in optimizer.param_groups:
            group["lr"] = rate
        last_loss = _backward_step(
            runner, windows, plan, state["step"], rows, model_config.vocab, device, autocast
        )
        torch.nn.utils.clip_grad_norm_(model.parameters(), plan["clip"])
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)
        state["step"] += 1
        state["tokens"] += per_step
        ran += 1
        if plan["evaluate_every"] and state["step"] % plan["evaluate_every"] == 0:
            found = held_out_bpb(model, shards, manifest, device)
            state["history"].append(
                {
                    "step": state["step"],
                    "loss": round(last_loss, 4),
                    **{label: item["bpb"] for label, item in found.items()},
                }
            )
            log(f"speaker: step {state['step']} {json.dumps(state['history'][-1])}")
        if time.monotonic() - saved_at >= plan["checkpoint_seconds"]:
            state["elapsed"] = before + time.monotonic() - began
            save_checkpoint(out, model, optimizer, state)
            saved_at = time.monotonic()
    state["elapsed"] = before + time.monotonic() - began
    save_checkpoint(out, model, optimizer, state)
    parameters = model.parameters_count()
    report = {
        "ended": ended,
        "step": state["step"],
        "steps_planned": total,
        "tokens": state["tokens"],
        "parameters": parameters,
        "flops": flops_per_token(model_config, parameters) * state["tokens"],
        "seconds": round(state["elapsed"], 1),
        "calls": state["calls"],
        "device": device,
        "torch": torch.__version__,
        "loss": round(last_loss, 4) if ran else None,
        "held_out": held_out_bpb(model, shards, manifest, device),
        "shards_manifest_sha256": _sha256(shards / "shards.json"),
        "history": state["history"],
    }
    report["final"] = save_final(out, model, shards, manifest, report)
    log(f"speaker: {ended} at step {state['step']} of {total}")
    return report
