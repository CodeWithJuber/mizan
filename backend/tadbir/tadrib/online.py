"""The online learner (needs torch; imported only where a model learns).

Fast weights learn one lesson at a time: ``steps`` AdamW steps on a batch of
the lesson, ``seeds`` lines replayed from the reader's seeds and the rest
recent lessons (reservoir sampling, Vitter's algorithm R; seed lines while
fewer exist), at a constant learning rate, with an elastic pull toward the
slow (gated) weights (EWC, Kirkpatrick et al. 2017):

    L(θ) = CE(batch; θ) + (λ/2) · Σ_i F_i (θ_i − θ_slow,i)²

F is the slow weights' diagonal Fisher, normalised to mean 1, or 1 for every
parameter until a night has estimated it. Everything random in a lesson is
seeded by the lesson's digest, so a model rebuilt from the same lessons in
the same order is the same, bit for bit.
"""

from __future__ import annotations

import copy
import json
import os
import random
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import torch
from torch.nn import functional as F

from ..ruh_reader import net


@dataclass(frozen=True)
class Setting:
    steps: int = 3  # AdamW steps per lesson
    lr: float = 3e-4
    anchor: float = 1.0  # λ
    batch: int = 16
    seeds: int = 4  # seed lines in every batch
    recent: int = 512  # lessons kept for replay
    micro: int = 4  # rows per forward pass; gradients accumulate (same step, less memory)

    def to_dict(self) -> dict:
        return asdict(self)


Encoded = tuple[list[int], int]


def _seed(digest: str) -> int:
    return int(digest[:15], 16)


def _trim() -> None:
    """Give the freed activation memory back to the system (glibc keeps it
    otherwise, and a long-lived server would hold its high-water mark)."""
    try:
        import ctypes

        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


class Online:
    """The fast copy of a slow model and how it learns."""

    def __init__(
        self,
        slow: net.Reader,
        setting: Setting,
        seed_lines: Sequence[tuple[str, int]],
        fisher: dict[str, torch.Tensor] | None = None,
    ):
        self.slow = slow.eval()
        for parameter in self.slow.parameters():
            parameter.requires_grad_(False)
        self.setting = setting
        context = slow.config.context
        self.seed_lines: list[Encoded] = [
            (net.encode(text, context), slot) for text, slot in seed_lines if text
        ]
        if not self.seed_lines:
            raise ValueError("the online learner needs seed lines to replay")
        self.fisher = fisher
        self.reset()

    def reset(self) -> None:
        """Start again from the slow weights: no lesson learned."""
        self.fast = copy.deepcopy(self.slow)
        for parameter in self.fast.parameters():
            parameter.requires_grad_(True)
        self.fast.eval()
        self.anchor = {name: p.detach().clone() for name, p in self.slow.named_parameters()}
        self.optimizer = torch.optim.AdamW(
            self.fast.parameters(), lr=self.setting.lr, betas=(0.9, 0.95), weight_decay=0.0
        )
        self.recent: list[Encoded] = []
        self.seen = 0
        self.learned: list[str] = []

    def _penalty(self) -> torch.Tensor:
        total = torch.zeros(())
        for name, parameter in self.fast.named_parameters():
            moved = (parameter - self.anchor[name]) ** 2
            if self.fisher is not None and name in self.fisher:
                moved = moved * self.fisher[name]
            total = total + moved.sum()
        return total

    def learn(self, own: str, slot: int, digest: str) -> float:
        """Take the lesson's steps; the mean training loss."""
        setting = self.setting
        rng = random.Random(_seed(digest))
        torch.manual_seed(_seed(digest))
        lesson = (net.encode(own, self.fast.config.context), slot)
        losses = []
        self.fast.train()
        for _ in range(setting.steps):
            pieces = [lesson]
            pieces += [
                self.seed_lines[rng.randrange(len(self.seed_lines))] for _ in range(setting.seeds)
            ]
            room = setting.batch - len(pieces)
            recent = rng.sample(self.recent, min(room, len(self.recent)))
            pieces += recent
            pieces += [
                self.seed_lines[rng.randrange(len(self.seed_lines))]
                for _ in range(room - len(recent))
            ]
            self.optimizer.zero_grad(set_to_none=True)
            # The mean over every target of the batch, accumulated over
            # micro-batches: the same gradient, a quarter of the activations.
            tokens = sum(len(targets) for targets, _slot in pieces)
            total = 0.0
            for begin in range(0, len(pieces), max(1, setting.micro)):
                inputs, labels, mask = net.batch(pieces[begin : begin + max(1, setting.micro)])
                logits, _ = self.fast(inputs)
                part = F.cross_entropy(logits[mask], labels[mask], reduction="sum") / tokens
                part.backward()
                total += float(part.detach())
            losses.append(total)
            if setting.anchor > 0:
                (setting.anchor / 2 * self._penalty()).backward()
            torch.nn.utils.clip_grad_norm_(self.fast.parameters(), 1.0)
            self.optimizer.step()
        self.fast.eval()
        self.seen += 1
        if len(self.recent) < setting.recent:
            self.recent.append(lesson)
        else:
            index = rng.randrange(self.seen)
            if index < setting.recent:
                self.recent[index] = lesson
        self.learned.append(digest)
        _trim()
        return sum(losses) / len(losses)

    def replay(self, lessons: Sequence[tuple[str, int, str]]) -> None:
        """Rebuild: start from the slow weights and learn these lessons in order."""
        self.reset()
        for own, slot, digest in lessons:
            self.learn(own, slot, digest)

    def serving_copy(self) -> net.Reader:
        """A copy of the fast weights for the reader that serves messages."""
        served: net.Reader = copy.deepcopy(self.fast)
        served.eval()
        for parameter in served.parameters():
            parameter.requires_grad_(False)
        return served


def fisher(
    model: net.Reader,
    lines: Sequence[tuple[str, int]],
    batches: int = 32,
    size: int = 16,
    seed: int = 0,
) -> dict[str, torch.Tensor]:
    """The diagonal empirical Fisher of ``model`` on ``lines`` (squared
    gradients of the batch loss, averaged), scaled to mean 1 over all
    parameters, so λ means the same whatever the model's size."""
    rng = random.Random(seed)
    encoded = [(net.encode(text, model.config.context), slot) for text, slot in lines if text]
    if not encoded:
        return {}
    work = copy.deepcopy(model).train()
    torch.manual_seed(seed)
    totals = {name: torch.zeros_like(p) for name, p in work.named_parameters()}
    for _ in range(batches):
        pieces = [encoded[rng.randrange(len(encoded))] for _ in range(size)]
        inputs, labels, mask = net.batch(pieces)
        logits, _ = work(inputs)
        loss = F.cross_entropy(logits[mask], labels[mask])
        work.zero_grad(set_to_none=True)
        loss.backward()
        for name, parameter in work.named_parameters():
            if parameter.grad is not None:
                totals[name] += parameter.grad.detach() ** 2
    count = sum(t.numel() for t in totals.values())
    mean = float(sum(t.sum() for t in totals.values())) / max(1, count)
    if mean <= 0:
        return {}
    return {name: t / mean for name, t in totals.items()}


def save_fisher(values: dict[str, torch.Tensor], path: Path, slow: str) -> None:
    temporary = path.with_suffix(".tmp")
    torch.save({"slow": slow, "fisher": values}, temporary)
    temporary.replace(path)


def load_fisher(path: Path, slow: str) -> dict[str, torch.Tensor] | None:
    """The Fisher estimated for this slow version, or None."""
    try:
        saved = torch.load(path, map_location="cpu", weights_only=True)
    except (OSError, RuntimeError, ValueError):
        return None
    if not isinstance(saved, dict) or saved.get("slow") != slow:
        return None
    return saved.get("fisher") or None


def save_fast(online: Online, weights: Path, described: Path, info: dict) -> None:
    """The fast copy and what it learned, each written whole (temporary file,
    then rename), so a restart reads either the old pair or the new one."""
    net.save(online.fast, weights)
    temporary = described.with_suffix(".tmp")
    temporary.write_text(json.dumps(info), encoding="utf-8")
    os.replace(temporary, described)
