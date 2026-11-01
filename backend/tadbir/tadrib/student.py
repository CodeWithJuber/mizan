"""MIZAN's own student of a Lisan task (Tadrib phase 2, docs/tadrib.md).

The student is the reader's network (``ruh_reader.net.Reader``: bytes, RoPE,
SwiGLU, tied embeddings, KV-cached decoding) with a longer context, started
from the reader's weights. A lesson (``plans.target``) is the sequence

    [TASK] message bytes [SEP] answer bytes [END]

and only the answer and its end are learned: L = −Σ_{t ≥ SEP} log p(y_t | y_<t).
It learns each lesson in a few AdamW steps with recent lessons replayed
(reservoir sampling), everything seeded by the lesson's digest, so a student
rebuilt from the same lessons in the same order is the same, bit for bit.
"""

from __future__ import annotations

import copy
import random
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace

import torch
from torch.nn import functional as F

from ..ruh_reader import net

TASK = net.lang_token(net.SLOTS - 1)  # the task: plan_steps
SEP = net.lang_token(net.SLOTS - 2)  # the answer begins
MAX_INPUT = 320  # bytes of the message the student reads
MAX_OUTPUT = 200  # bytes of answer it may write


# ── the student ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Setting:
    steps: int = 2  # AdamW steps per lesson
    lr: float = 1e-3
    replay: int = 7  # recent lessons in every batch with the new one
    recent: int = 4096  # lessons kept for replay
    micro: int = 4  # rows per forward pass; gradients accumulate
    context: int = 544  # positions: the task, the message, SEP, the answer, END

    def to_dict(self) -> dict:
        return asdict(self)


Encoded = tuple[list[int], int]  # tokens and the index of the first answer token


def encode(message: str, answer: str | None = None) -> Encoded:
    tokens = [TASK, *message.encode("utf-8")[:MAX_INPUT], SEP]
    start = len(tokens)
    if answer is not None:
        tokens += [*answer.encode("utf-8")[:MAX_OUTPUT], net.END]
    return tokens, start


def _seed(digest: str) -> int:
    return int(digest[:15], 16)


def _batch(pieces: Sequence[Encoded]) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Inputs, targets and a mask of the answer's targets."""
    width = max(len(tokens) for tokens, _start in pieces) - 1
    inputs = torch.full((len(pieces), width), net.END, dtype=torch.long)
    labels = torch.full((len(pieces), width), net.END, dtype=torch.long)
    mask = torch.zeros((len(pieces), width), dtype=torch.bool)
    for row, (tokens, start) in enumerate(pieces):
        n = len(tokens) - 1
        inputs[row, :n] = torch.tensor(tokens[:-1], dtype=torch.long)
        labels[row, :n] = torch.tensor(tokens[1:], dtype=torch.long)
        mask[row, start - 1 : n] = True
    return inputs, labels, mask


class Student:
    """A student network, how it learns, and what it learned (in order)."""

    def __init__(self, base: net.Reader, setting: Setting | None = None):
        self.setting = setting or Setting()
        config = replace(base.config, context=self.setting.context, dropout=0.0)
        self.initial = net.Reader(config)
        self.initial.load_state_dict(base.state_dict())
        self.reset()

    def reset(self) -> None:
        self.model = copy.deepcopy(self.initial)
        self.optimizer = torch.optim.AdamW(
            self.model.parameters(), lr=self.setting.lr, betas=(0.9, 0.98), weight_decay=0.0
        )
        self.recent: list[Encoded] = []
        self.seen = 0
        self.learned: list[str] = []

    def learn(self, message: str, answer: str, digest: str) -> float:
        setting = self.setting
        rng = random.Random(_seed(digest))
        torch.manual_seed(_seed(digest))
        lesson = encode(message, answer)
        losses = []
        self.model.train()
        for _ in range(setting.steps):
            pieces = [lesson, *rng.sample(self.recent, min(setting.replay, len(self.recent)))]
            self.optimizer.zero_grad(set_to_none=True)
            targets = sum(len(tokens) - start for tokens, start in pieces)
            total = 0.0
            for begin in range(0, len(pieces), max(1, setting.micro)):
                inputs, labels, mask = _batch(pieces[begin : begin + max(1, setting.micro)])
                logits, _ = self.model(inputs)
                part = F.cross_entropy(logits[mask], labels[mask], reduction="sum") / targets
                part.backward()
                total += float(part.detach())
            losses.append(total)
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
            self.optimizer.step()
        self.model.eval()
        self.seen += 1
        if len(self.recent) < setting.recent:
            self.recent.append(lesson)
        else:
            index = rng.randrange(self.seen)
            if index < setting.recent:
                self.recent[index] = lesson
        self.learned.append(digest)
        return sum(losses) / len(losses)

    @torch.no_grad()
    def answer(self, message: str) -> tuple[str | None, float]:
        """The student's answer (greedy, KV-cached) and the mean log-probability
        of its tokens; None when it does not end within ``MAX_OUTPUT`` bytes."""
        self.model.eval()
        tokens, _start = encode(message)
        logits, cache = self.model(torch.tensor([tokens]))
        made: list[int] = []
        logps: list[float] = []
        for _ in range(MAX_OUTPUT + 1):
            row = torch.log_softmax(logits[0, -1, : net.END + 1].float(), dim=-1)
            following = int(row.argmax())
            logps.append(float(row[following]))
            if following == net.END:
                break
            made.append(following)
            logits, cache = self.model(torch.tensor([[following]]), cache)
        else:
            return None, sum(logps) / len(logps)
        return bytes(made).decode("utf-8", errors="replace"), sum(logps) / len(logps)

    def rebuild(self, lessons: Sequence[tuple[str, str, str]]) -> None:
        """Start again from the initial weights and learn these lessons in order."""
        self.reset()
        for message, answer, digest in lessons:
            self.learn(message, answer, digest)


def same_weights(first: torch.nn.Module, second: torch.nn.Module) -> bool:
    one, two = first.state_dict(), second.state_dict()
    return one.keys() == two.keys() and all(torch.equal(one[k], two[k]) for k in one)
