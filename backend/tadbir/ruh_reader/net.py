"""The reader's network: a small byte-level causal transformer (needs torch).

Imported only by the functions of ``tadbir.ruh_reader`` that train or score,
so nothing at import time of MIZAN needs torch.

Tokens: the 256 byte values, an end-of-message token, and one token per
language slot. A message in language ``l`` is the sequence
``[lang_l] b_1 … b_n [end]``; the model predicts every byte and the end, so

    log P(x | l) = Σ_{t=1..n+1} log p(y_t | lang_l, y_<t)

is the log-probability of the whole message under language ``l``. Every
language is scored in one batched forward pass (one row per language).

Architecture: pre-norm blocks with RMSNorm, rotary positions (RoPE) on queries
and keys, SwiGLU feed-forward, causal attention, and the output layer tied to
the token embedding. Decoding keeps each layer's keys and values (KV cache), so
one more byte costs one position, not the whole prefix.
"""

from __future__ import annotations

import math
import random
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F

BYTES = 256
END = 256
SLOTS = 16  # language tokens: the shipped languages and those Ta'lim may add
VOCAB = BYTES + 1 + SLOTS


def lang_token(slot: int) -> int:
    return BYTES + 1 + slot


@dataclass(frozen=True)
class Config:
    d_model: int = 256
    layers: int = 4
    heads: int = 4
    d_ff: int = 768
    context: int = 192  # bytes read of one message (the language token is extra)
    dropout: float = 0.1

    def to_dict(self) -> dict:
        return asdict(self)


class RMSNorm(nn.Module):
    def __init__(self, size: int, eps: float = 1e-6):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(size))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps) * self.weight


def _rotary(head: int, length: int) -> tuple[torch.Tensor, torch.Tensor]:
    inverse = 1.0 / (10000 ** (torch.arange(0, head, 2, dtype=torch.float32) / head))
    angles = torch.outer(torch.arange(length, dtype=torch.float32), inverse)
    return torch.cos(angles), torch.sin(angles)


def _rotate(x: torch.Tensor, cos: torch.Tensor, sin: torch.Tensor) -> torch.Tensor:
    """RoPE on (batch, heads, positions, head) with the positions' cos/sin."""
    even, odd = x[..., 0::2], x[..., 1::2]
    turned = torch.stack((even * cos - odd * sin, even * sin + odd * cos), dim=-1)
    return turned.flatten(-2)


class Block(nn.Module):
    def __init__(self, config: Config):
        super().__init__()
        self.heads = config.heads
        self.head = config.d_model // config.heads
        self.norm1 = RMSNorm(config.d_model)
        self.qkv = nn.Linear(config.d_model, 3 * config.d_model, bias=False)
        self.out = nn.Linear(config.d_model, config.d_model, bias=False)
        self.norm2 = RMSNorm(config.d_model)
        self.gate = nn.Linear(config.d_model, config.d_ff, bias=False)
        self.up = nn.Linear(config.d_model, config.d_ff, bias=False)
        self.down = nn.Linear(config.d_ff, config.d_model, bias=False)
        self.drop = nn.Dropout(config.dropout)

    def forward(
        self,
        x: torch.Tensor,
        cos: torch.Tensor,
        sin: torch.Tensor,
        cache: tuple[torch.Tensor, torch.Tensor] | None = None,
        padding: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, tuple[torch.Tensor, torch.Tensor]]:
        batch, length, width = x.shape
        q, k, v = self.qkv(self.norm1(x)).split(width, dim=-1)
        q, k, v = (t.view(batch, length, self.heads, self.head).transpose(1, 2) for t in (q, k, v))
        q, k = _rotate(q, cos, sin), _rotate(k, cos, sin)
        if cache is not None:
            k = torch.cat((cache[0], k), dim=2)
            v = torch.cat((cache[1], v), dim=2)
        if cache is None and padding is None:
            attended = F.scaled_dot_product_attention(
                q, k, v, is_causal=True, dropout_p=self.drop.p if self.training else 0.0
            )
        else:
            past = k.shape[2] - length
            allowed = torch.ones(length, k.shape[2], dtype=torch.bool, device=x.device).tril(past)
            mask = allowed[None, None]
            if padding is not None:  # keys that are padding are never read
                mask = mask & ~padding[:, None, None, :]
            attended = F.scaled_dot_product_attention(
                q, k, v, attn_mask=mask, dropout_p=self.drop.p if self.training else 0.0
            )
        x = x + self.drop(self.out(attended.transpose(1, 2).reshape(batch, length, width)))
        h = self.norm2(x)
        x = x + self.drop(self.down(F.silu(self.gate(h)) * self.up(h)))
        return x, (k, v)


class Reader(nn.Module):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.embed = nn.Embedding(VOCAB, config.d_model)
        self.blocks = nn.ModuleList(Block(config) for _ in range(config.layers))
        self.norm = RMSNorm(config.d_model)
        self.drop = nn.Dropout(config.dropout)
        cos, sin = _rotary(config.d_model // config.heads, config.context + 2)
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
        padding: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, list[tuple[torch.Tensor, torch.Tensor]]]:
        """Next-token logits for each position; with ``cache`` the tokens
        continue the cached prefix. ``padding`` (batch, positions) marks keys
        that are padding."""
        start = cache[0][0].shape[2] if cache else 0
        length = tokens.shape[1]
        cos = self.cos[start : start + length]
        sin = self.sin[start : start + length]
        x = self.drop(self.embed(tokens))
        kept = []
        for index, block in enumerate(self.blocks):
            x, kv = block(x, cos, sin, cache[index] if cache else None, padding)
            kept.append(kv)
        x = self.norm(x)
        return F.linear(x, self.embed.weight), kept


# ── encoding ────────────────────────────────────────────────────────────


def encode(text: str, context: int) -> list[int]:
    """The message's bytes (at most ``context``), then the end token when it fits."""
    data = list(text.encode("utf-8"))
    return data[:context] if len(data) >= context else [*data, END]


def batch(
    pieces: Sequence[tuple[list[int], int]],
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Inputs, targets and a mask of real targets, for (targets, slot) pairs:
    each row is ``[lang] y_1 … y_{m-1}`` predicting ``y_1 … y_m``."""
    width = max(len(targets) for targets, _slot in pieces)
    inputs = torch.full((len(pieces), width), END, dtype=torch.long)
    labels = torch.full((len(pieces), width), END, dtype=torch.long)
    mask = torch.zeros((len(pieces), width), dtype=torch.bool)
    for row, (targets, slot) in enumerate(pieces):
        m = len(targets)
        inputs[row, 0] = lang_token(slot)
        if m > 1:
            inputs[row, 1:m] = torch.tensor(targets[:-1], dtype=torch.long)
        labels[row, :m] = torch.tensor(targets, dtype=torch.long)
        mask[row, :m] = True
    return inputs, labels, mask


def _token_logprobs(model: nn.Module, inputs, labels, mask) -> torch.Tensor:
    logits, _ = model(inputs)
    picked = torch.log_softmax(logits.float(), dim=-1).gather(-1, labels[..., None])[..., 0]
    return picked * mask


@torch.no_grad()
def score(
    model: nn.Module,
    texts: Sequence[str],
    slots: Sequence[int],
    rows_per_pass: int = 320,
    ends: bool = False,
) -> tuple[list[list[float]], list[int]]:
    """log P(text | language) in nats for every text and every slot, and the
    number of predicted tokens of each text. Each text's languages are rows of
    one batched forward pass. Without ``ends`` the end token is not scored:
    the bytes are read as they came (a message may be cut short, and where a
    training sentence ends says more about the corpus than the language)."""
    model.eval()
    context = model.config.context if hasattr(model, "config") else Config().context
    encoded = [encode(text, context) for text in texts]
    if not ends:
        encoded = [item[:-1] if item and item[-1] == END else item for item in encoded]
    order = sorted((i for i in range(len(texts)) if encoded[i]), key=lambda i: len(encoded[i]))
    found: list[list[float]] = [[0.0] * len(slots) for _ in texts]
    per_pass = max(1, rows_per_pass // max(1, len(slots)))
    for begin in range(0, len(order), per_pass):
        chosen = order[begin : begin + per_pass]
        pieces = [(encoded[i], slot) for i in chosen for slot in slots]
        inputs, labels, mask = batch(pieces)
        totals = _token_logprobs(model, inputs, labels, mask).sum(-1).tolist()
        for position, i in enumerate(chosen):
            found[i] = totals[position * len(slots) : (position + 1) * len(slots)]
    return found, [len(item) for item in encoded]


@torch.no_grad()
def generate(model: nn.Module, slot: int, prompt: str, new: int) -> bytes:
    """Greedy continuation of ``prompt`` in language ``slot``, decoded with the
    KV cache (each new byte runs one position through the model)."""
    model.eval()
    tokens = [lang_token(slot), *prompt.encode("utf-8")]
    logits, cache = model(torch.tensor([tokens]))
    made: list[int] = []
    for _ in range(new):
        following = int(logits[0, -1, : END + 1].argmax())
        if following == END or len(tokens) + len(made) >= model.config.context + 1:
            break
        made.append(following)
        logits, cache = model(torch.tensor([[following]]), cache)
    return bytes(made)


# ── training ────────────────────────────────────────────────────────────


@dataclass
class Plan:
    seconds: float  # wall-clock budget
    epochs: float  # passes over the training lines, at most
    batch: int = 32
    lr: float = 2e-3
    weight_decay: float = 0.1
    warmup: int = 60
    replay: float = 0.0  # share of each batch drawn from ``replay_lines``
    seed: int = 0
    threads: int = 2


def _lines_for(lines: Sequence[tuple[str, int]], context: int) -> list[tuple[list[int], int]]:
    return [(encode(text, context), slot) for text, slot in lines if text]


def bits_per_byte(model: nn.Module, lines: Sequence[tuple[str, int]]) -> tuple[float, int, float]:
    """Total nats, predicted tokens and bits per token of ``lines`` under their
    own language."""
    total, tokens = 0.0, 0
    model.eval()
    encoded = sorted(_lines_for(lines, model.config.context), key=lambda item: len(item[0]))
    with torch.no_grad():
        for begin in range(0, len(encoded), 64):
            inputs, labels, mask = batch(encoded[begin : begin + 64])
            total -= float(_token_logprobs(model, inputs, labels, mask).sum())
            tokens += int(mask.sum())
    return total, tokens, total / max(1, tokens) / math.log(2)


def train(
    model: Reader,
    lines: Sequence[tuple[str, int]],
    plan: Plan,
    dev: Sequence[tuple[str, int]] = (),
    replay_lines: Sequence[tuple[str, int]] = (),
    stop: Callable[[], bool] = lambda: False,
    loss_hook: Callable[[torch.Tensor, torch.Tensor], None] | None = None,
) -> dict:
    """Train on (text, slot) lines within the plan's budget; keep the weights
    that read ``dev`` best (checked once per pass over the lines). With
    ``replay``, that share of every batch is a sample of ``replay_lines``.
    ``loss_hook`` sees the targets and mask of every batch that reaches the loss."""
    torch.manual_seed(plan.seed)
    torch.set_num_threads(plan.threads)
    rng = random.Random(plan.seed)
    context = model.config.context
    new = _lines_for(lines, context)
    old = _lines_for(replay_lines, context) if plan.replay > 0 else []
    if not new:
        return {"steps": 0, "seconds": 0.0, "tokens": 0, "stopped": "nothing to learn"}
    from_new = max(1, round(plan.batch * (1 - plan.replay))) if old else plan.batch
    per_epoch = math.ceil(len(new) / from_new)
    total_steps = max(1, math.ceil(per_epoch * plan.epochs))
    decay: list[nn.Parameter] = []
    keep: list[nn.Parameter] = []
    for name, parameter in model.named_parameters():
        (decay if parameter.dim() >= 2 and "embed" not in name else keep).append(parameter)
    optimizer = torch.optim.AdamW(
        [{"params": decay, "weight_decay": plan.weight_decay}, {"params": keep, "weight_decay": 0}],
        lr=plan.lr,
        betas=(0.9, 0.95),
    )

    def rate(step: int) -> float:
        if step < plan.warmup:
            return (step + 1) / plan.warmup
        progress = (step - plan.warmup) / max(1, total_steps - plan.warmup)
        return 0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * min(1.0, progress)))

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, rate)
    began = time.monotonic()
    best: tuple[float, dict] | None = None
    history: list[dict] = []
    step, ran, tokens, stopped = 0, 0, 0, "budget"

    def checkpoint() -> None:
        nonlocal best
        if not dev:
            return
        _nats, _count, bpb = bits_per_byte(model, dev)
        history.append({"step": step, "dev_bpb": round(bpb, 5)})
        if best is None or bpb < best[0]:
            best = (bpb, {k: v.detach().clone() for k, v in model.state_dict().items()})
        model.train()

    model.train()
    while step < total_steps:
        order = list(range(len(new)))
        rng.shuffle(order)
        # Lines of like length together, so a batch is mostly bytes, not padding.
        chunks = [order[i : i + from_new * 8] for i in range(0, len(order), from_new * 8)]
        batches = []
        for chunk in chunks:
            chunk.sort(key=lambda i: len(new[i][0]))
            batches += [chunk[i : i + from_new] for i in range(0, len(chunk), from_new)]
        rng.shuffle(batches)
        for chosen in batches:
            if step >= total_steps:
                break
            if stop() or time.monotonic() - began > plan.seconds:
                stopped = "stopped" if stop() else "time"
                step = total_steps
                break
            pieces = [new[i] for i in chosen]
            if old:
                pieces += [old[rng.randrange(len(old))] for _ in range(plan.batch - from_new)]
            inputs, labels, mask = batch(pieces)
            if loss_hook is not None:
                loss_hook(labels, mask)
            logits, _ = model(inputs)
            loss = F.cross_entropy(logits[mask], labels[mask])
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            step += 1
            ran += 1
            tokens += int(mask.sum())
        checkpoint()
    if best is not None:
        model.load_state_dict(best[1])
    model.eval()
    return {
        "steps": ran,
        "seconds": round(time.monotonic() - began, 2),
        "tokens": tokens,
        "stopped": stopped,
        "dev_bpb": round(best[0], 5) if best else None,
        "history": history,
    }


# ── saving, loading, int8 ───────────────────────────────────────────────


def save(model: Reader, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    torch.save({"config": model.config.to_dict(), "state": model.state_dict()}, temporary)
    temporary.replace(path)


def load(path: Path) -> Reader:
    saved = torch.load(path, map_location="cpu", weights_only=True)
    model = Reader(Config(**saved["config"]))
    model.load_state_dict(saved["state"])
    model.eval()
    return model


def quantized(model: Reader) -> nn.Module:
    """int8 dynamic quantisation of every linear layer (the tied output layer
    and the embedding stay fp32)."""
    import warnings

    with warnings.catch_warnings():  # torch marks the eager API for a move to torchao
        warnings.simplefilter("ignore")
        from torch.ao.quantization import quantize_dynamic

        small = quantize_dynamic(model, {nn.Linear}, dtype=torch.qint8)
    small.config = model.config  # type: ignore[assignment]
    return small


def latency(model: nn.Module, slots: Sequence[int], size: int = 100, repeats: int = 30) -> dict:
    """Milliseconds to score one ``size``-byte message under every language
    (one batched forward pass), on 2 threads: median and 90th percentile."""
    torch.set_num_threads(2)
    text = ("abc def ghi " * size)[:size]
    for _ in range(3):
        score(model, [text], slots)
    timings = []
    for _ in range(repeats):
        began = time.perf_counter()
        score(model, [text], slots)
        timings.append((time.perf_counter() - began) * 1000)
    timings.sort()
    return {
        "median_ms": round(timings[len(timings) // 2], 2),
        "p90_ms": round(timings[int(len(timings) * 0.9)], 2),
    }
