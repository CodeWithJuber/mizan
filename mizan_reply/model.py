"""An untrained, causal byte-energy model with optional radical composition.

No softmax, pretrained weights, retrieval, or conversational templates are used.
Lower output energies are preferred; these scores are not truth or confidence.
The implementation deliberately makes its finite receptive field explicit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import math
from typing import Any

import torch
from torch import Tensor, nn
import torch.nn.functional as F

EOS_ID = 256
BOS_ID = 257
USER_ID = 258
ASSISTANT_ID = 259
SYSTEM_ID = 260
EVIDENCE_ID = 261
END_ID = 262
INPUT_VOCAB_SIZE = 263
OUTPUT_VOCAB_SIZE = 257
RADICALS = "ءبتثجحخدذرزسشصضطظعغفقكلمنهوي"


@dataclass(frozen=True)
class ModelConfig:
    dim: int = 128
    layers: int = 11
    kernel_size: int = 3
    max_seq_len: int = 2048
    root_dim: int = 12
    root_mode: str = "none"
    margin: float = 1.0

    def __post_init__(self) -> None:
        for name in ("dim", "layers", "kernel_size", "max_seq_len", "root_dim"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.dim < 2:
            raise ValueError("dim must be >= 2; single-channel LayerNorm erases the input")
        if self.kernel_size < 2:
            raise ValueError("kernel_size must be >= 2 for temporal composition")
        if self.layers > 30:
            raise ValueError("layers must be <= 30; reject impractical dilation values")
        if self.root_mode not in ("none", "ordered", "bag"):
            raise ValueError("root_mode must be none, ordered, or bag")
        if isinstance(self.margin, bool) or not isinstance(self.margin, (int, float)):
            raise ValueError("margin must be a finite positive number")
        if not math.isfinite(self.margin) or self.margin <= 0:
            raise ValueError("margin must be a finite positive number")
        if self.max_seq_len > self.receptive_field:
            raise ValueError(
                f"max_seq_len {self.max_seq_len} exceeds receptive field "
                f"{self.receptive_field}; increase layers or reduce the explicit budget"
            )

    @property
    def receptive_field(self) -> int:
        return 1 + (self.kernel_size - 1) * ((1 << self.layers) - 1)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ModelConfig":
        if not isinstance(value, dict):
            raise ValueError("model config must be a dictionary")
        unknown = set(value) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"unknown config fields: {sorted(unknown)}")
        return cls(**value)


@dataclass
class LayerCache:
    # A circular buffer of *normalized inputs* to this layer, [B, history, D].
    values: Tensor
    next_index: int = 0


@dataclass
class ModelCache:
    layers: list[LayerCache]
    position: int
    batch_size: int
    owner_id: int
    state_signature: tuple[Any, ...]
    inference_state: tuple[Tensor, ...]


class RadicalComposer(nn.Module):
    """Learned symbol operators; their coordinates have no intrinsic semantics."""

    def __init__(self, dim: int, mode: str) -> None:
        super().__init__()
        self.mode = mode
        self.A = nn.Parameter(torch.eye(dim).repeat(len(RADICALS), 1, 1))
        self.b = nn.Parameter(torch.empty(len(RADICALS), dim))
        with torch.no_grad():
            self.A.add_(0.02 * torch.randn_like(self.A))
            self.b.normal_(mean=0.0, std=0.02)
        # Fixed and nonzero: no trainable initial-state escape from composition.
        h0 = torch.linspace(-0.5, 0.5, dim) if dim > 1 else torch.tensor([0.5])
        self.register_buffer("h0", h0)

    def forward(self, roots: Tensor) -> Tensor:
        present = roots.ne(0)
        base = self.h0.expand(*roots.shape[:-1], -1)
        # Zero IDs index row zero internally, then are masked. Keeping this path
        # connected gives DDP a zero gradient (not an unused parameter) on batches
        # containing no roots, including all-ignore dummy batches.
        ids = (roots - 1).clamp_min(0)
        if self.mode == "ordered":
            state = base
            for j in range(4):
                matrix = self.A[ids[..., j]]
                bias = self.b[ids[..., j]]
                candidate = torch.tanh(torch.matmul(matrix, state.unsqueeze(-1)).squeeze(-1) + bias)
                state = torch.where(present[..., j, None], candidate, state)
        else:
            matrix = self.A[ids]
            bias = self.b[ids]
            candidate = torch.tanh(torch.matmul(matrix, base[..., None, :, None]).squeeze(-1) + bias)
            count = present.sum(-1, keepdim=True).clamp_min(1)
            state = (candidate * present[..., None]).sum(-2) / count
        return state * present.any(-1, keepdim=True)


class CausalBlock(nn.Module):
    def __init__(self, dim: int, kernel_size: int, dilation: int, scale: float) -> None:
        super().__init__()
        self.norm = nn.LayerNorm(dim)
        self.conv = nn.Conv1d(dim, 2 * dim, kernel_size, dilation=dilation)
        self.out = nn.Linear(dim, dim)
        self.dilation = dilation
        self.scale = scale
        # Start gates inside the linear region rather than mostly closed.
        with torch.no_grad():
            self.conv.bias[dim:].fill_(0.5)

    @property
    def history_size(self) -> int:
        return self.dilation * (self.conv.kernel_size[0] - 1)

    def _causal_affine(self, normalized: Tensor) -> Tensor:
        """Equivalent to left-padded dilated Conv1d without huge padding tensors.

        Each kernel contribution is a batched matrix multiply over all valid
        sequence positions. Large dilations beyond this prefix contribute zero.
        """
        steps = normalized.shape[1]
        output = self.conv.bias.view(1, 1, -1).expand(normalized.shape[0], steps, -1)
        width = self.conv.kernel_size[0]
        for j in range(width):
            delay = (width - 1 - j) * self.dilation
            if delay < steps:
                projected = F.linear(normalized[:, : steps - delay], self.conv.weight[:, :, j])
                output = output + F.pad(projected, (0, 0, delay, 0))
        return output

    def _residual(self, original: Tensor, affine: Tensor) -> Tensor:
        content, gate = affine.chunk(2, dim=-1)
        return original + self.scale * self.out(torch.tanh(content) * gate.clamp(0.0, 1.0))

    def forward(self, hidden: Tensor) -> tuple[Tensor, Tensor]:
        normalized = self.norm(hidden)  # Last/channel axis only; no time mixing.
        return self._residual(hidden, self._causal_affine(normalized)), normalized

    def step(self, hidden: Tensor, cache: LayerCache, position: int) -> Tensor:
        normalized = self.norm(hidden)
        width = self.conv.kernel_size[0]
        affine = self.conv.bias.expand(hidden.shape[0], -1)
        for j in range(width):
            delay = (width - 1 - j) * self.dilation
            if delay == 0:
                value = normalized
            elif delay <= position:
                index = (cache.next_index - delay) % cache.values.shape[1]
                value = cache.values[:, index]
            else:
                continue
            affine = affine + F.linear(value, self.conv.weight[:, :, j])
        # Read history before overwriting the oldest element.
        cache.values[:, cache.next_index].copy_(normalized)
        cache.next_index = (cache.next_index + 1) % cache.values.shape[1]
        return self._residual(hidden, affine)


class MizanReplyModel(nn.Module):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        if not isinstance(config, ModelConfig):
            raise TypeError("config must be ModelConfig")
        self.config = config
        ids = torch.arange(INPUT_VOCAB_SIZE, dtype=torch.int64)[:, None]
        bits = ((ids >> torch.arange(9)) & 1).float().mul(2).sub(1)
        self.register_buffer("input_bits", bits, persistent=False)
        self.input_projection = nn.Linear(9, config.dim)
        if config.root_mode != "none":
            self.root_composer: RadicalComposer | None = RadicalComposer(config.root_dim, config.root_mode)
            self.root_projection: nn.Linear | None = nn.Linear(config.root_dim, config.dim, bias=False)
        else:
            self.root_composer = None
            self.root_projection = None
        self.blocks = nn.ModuleList([
            CausalBlock(config.dim, config.kernel_size, 1 << i, 1 / math.sqrt(config.layers))
            for i in range(config.layers)
        ])
        self.output_norm = nn.LayerNorm(config.dim)
        self.output_projection = nn.Linear(config.dim, OUTPUT_VOCAB_SIZE)

    @property
    def device(self) -> torch.device:
        return self.input_projection.weight.device

    def _validate(self, input_ids: Tensor, roots: Tensor | None) -> Tensor:
        if not isinstance(input_ids, Tensor) or input_ids.dtype != torch.int64 or input_ids.ndim != 2:
            raise ValueError("input_ids must be an int64 [batch, time] tensor")
        if input_ids.shape[0] < 1 or not 1 <= input_ids.shape[1] <= self.config.max_seq_len:
            raise ValueError(f"input length must be 1..{self.config.max_seq_len}; no truncation is performed")
        if input_ids.device != self.device:
            raise ValueError("input_ids and model must use the same device")
        if bool(((input_ids < 0) | (input_ids >= INPUT_VOCAB_SIZE)).any()):
            raise ValueError("input id outside 0..262")
        if roots is None:
            return torch.zeros((*input_ids.shape, 4), dtype=torch.int64, device=input_ids.device)
        if not isinstance(roots, Tensor) or roots.dtype != torch.int64 or roots.shape != (*input_ids.shape, 4):
            raise ValueError("roots must be an int64 [batch, time, 4] tensor")
        if roots.device != input_ids.device:
            raise ValueError("roots and input_ids must use the same device")
        if bool(((roots < 0) | (roots > len(RADICALS))).any()):
            raise ValueError("root IDs must be 0 padding or canonical radical IDs 1..28")
        present = roots.ne(0)
        counts = present.sum(-1)
        if bool(((counts != 0) & (counts != 3) & (counts != 4)).any()):
            raise ValueError("roots must contain exactly 3 or 4 radicals, or be entirely absent")
        if bool((present[..., 1:] & ~present[..., :-1]).any()):
            raise ValueError("root padding must be contiguous on the right")
        if bool((present.any(-1) & (input_ids > 255)).any()):
            raise ValueError("roots may annotate content bytes, never structural tokens")
        return roots

    def _features(self, input_ids: Tensor, roots: Tensor) -> Tensor:
        hidden = self.input_projection(self.input_bits[input_ids])
        if self.root_composer is not None:
            hidden = hidden + self.root_projection(self.root_composer(roots))
        return hidden

    def forward(self, input_ids: Tensor, roots: Tensor | None = None) -> Tensor:
        valid_roots = self._validate(input_ids, roots)
        hidden = self._features(input_ids, valid_roots)
        for block in self.blocks:
            hidden, _ = block(hidden)
        return self.output_projection(self.output_norm(hidden))

    def new_cache(self, batch_size: int = 1) -> ModelCache:
        if type(batch_size) is not int or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        dtype = self.input_projection.weight.dtype
        layers = [LayerCache(torch.zeros(
            batch_size, min(block.history_size, self.config.max_seq_len), self.config.dim,
            dtype=dtype, device=self.device,
        )) for block in self.blocks]
        return ModelCache(layers, position=0, batch_size=batch_size, owner_id=id(self),
                          state_signature=self._cache_signature(),
                          inference_state=tuple(tensor.detach().clone() for tensor in
                                                (*self.parameters(), *self.buffers())
                                                if tensor.is_inference()))

    def _cache_signature(self) -> tuple[Any, ...]:
        """Track normal tensor updates/replacement and the numerical execution mode.

        Caches cannot survive optimizer steps, load_state_dict, dtype/device
        conversion or a change of autocast mode. As with autograd, bypassing
        version counters with unsupported .data mutation is not supported.
        """
        state = tuple((name, id(tensor), None if tensor.is_inference() else tensor._version,
                       tensor.device, tensor.dtype, tuple(tensor.shape))
                      for name, tensor in (*self.named_parameters(), *self.named_buffers()))
        autocast = torch.is_autocast_enabled(self.device.type)
        return (self.config, state, autocast,
                torch.get_autocast_dtype(self.device.type) if autocast else None)

    def _validate_cache(self, cache: ModelCache) -> None:
        if not isinstance(cache, ModelCache) or cache.owner_id != id(self):
            raise ValueError("cache must have been created by this exact model instance")
        if cache.state_signature != self._cache_signature():
            raise ValueError("stale cache: model tensors or autocast mode changed; prefill again")
        # Models constructed inside inference_mode have no version counters.
        # Only that unusual case needs value snapshots instead of cheap versions.
        inference_tensors = tuple(tensor for tensor in (*self.parameters(), *self.buffers())
                                  if tensor.is_inference())
        if (len(cache.inference_state) != len(inference_tensors)
                or any(not torch.equal(tensor, snapshot) for tensor, snapshot in
                       zip(inference_tensors, cache.inference_state))):
            raise ValueError("stale cache: inference model tensors changed; prefill again")
        if type(cache.position) is not int or not 0 <= cache.position <= self.config.max_seq_len:
            raise ValueError("cache position must be within the configured context budget")
        if type(cache.batch_size) is not int or cache.batch_size < 1:
            raise ValueError("cache batch_size must be a positive integer")
        if not isinstance(cache.layers, list) or len(cache.layers) != len(self.blocks):
            raise ValueError("cache must contain exactly one buffer per model layer")
        for block, layer_cache in zip(self.blocks, cache.layers):
            history = min(block.history_size, self.config.max_seq_len)
            if (not isinstance(layer_cache, LayerCache) or not isinstance(layer_cache.values, Tensor)
                    or layer_cache.values.shape != (cache.batch_size, history, self.config.dim)
                    or layer_cache.values.dtype != self.input_projection.weight.dtype
                    or layer_cache.values.device != self.device):
                raise ValueError("cache layer buffer has an invalid shape, dtype or device")
            if type(layer_cache.next_index) is not int or not 0 <= layer_cache.next_index < history:
                raise ValueError("cache layer index is outside its circular buffer")

    @torch.no_grad()
    def prefill(self, input_ids: Tensor, roots: Tensor | None = None) -> tuple[Tensor, ModelCache]:
        if self.training:
            raise RuntimeError("prefill/step caches are inference-only; call model.eval()")
        valid_roots = self._validate(input_ids, roots)
        hidden = self._features(input_ids, valid_roots)
        cache = self.new_cache(input_ids.shape[0])
        for block, layer_cache in zip(self.blocks, cache.layers):
            hidden, normalized = block(hidden)
            take = min(normalized.shape[1], layer_cache.values.shape[1])
            layer_cache.values[:, -take:].copy_(normalized[:, -take:])
        cache.position = input_ids.shape[1]
        energies = self.output_projection(self.output_norm(hidden[:, -1]))
        return energies, cache

    @torch.no_grad()
    def step(self, input_ids: Tensor, cache: ModelCache, roots: Tensor | None = None) -> Tensor:
        if self.training:
            raise RuntimeError("prefill/step caches are inference-only; call model.eval()")
        self._validate_cache(cache)
        if cache.position >= self.config.max_seq_len:
            raise ValueError("context budget exhausted; cache is never silently cropped or reset")
        if not isinstance(input_ids, Tensor) or input_ids.ndim != 1 or input_ids.shape[0] != cache.batch_size:
            raise ValueError("step input_ids must have shape [cache batch]")
        if roots is not None and (not isinstance(roots, Tensor) or roots.shape != (cache.batch_size, 4)):
            raise ValueError("step roots must have shape [cache batch, 4]")
        expanded_roots = None if roots is None else roots[:, None]
        valid_roots = self._validate(input_ids[:, None], expanded_roots)
        hidden = self._features(input_ids[:, None], valid_roots)[:, 0]
        for block, layer_cache in zip(self.blocks, cache.layers):
            hidden = block.step(hidden, layer_cache, cache.position)
        cache.position += 1
        return self.output_projection(self.output_norm(hidden))


def margin_loss(
    energies: Tensor,
    targets: Tensor,
    ignore_index: int = -100,
    reduction: str = "mean",
    margin: float = 1.0,
) -> Tensor:
    """Hinge on the hardest wrong next byte/EOS; not a likelihood loss.

    Each supervised position contributes max(0, margin + E_gold - min E_wrong).
    A byte-exact target is still just a supplied target, not proof of truth.
    """
    if not isinstance(energies, Tensor) or not energies.is_floating_point() or energies.ndim != 3:
        raise ValueError("energies must be a floating [batch, time, 257] tensor")
    if energies.shape[-1] != OUTPUT_VOCAB_SIZE:
        raise ValueError("energies must have 257 output classes")
    if not isinstance(targets, Tensor) or targets.dtype != torch.int64 or targets.shape != energies.shape[:-1]:
        raise ValueError("targets must be an int64 [batch, time] tensor")
    if targets.device != energies.device:
        raise ValueError("targets and energies must use the same device")
    if type(ignore_index) is not int or 0 <= ignore_index < OUTPUT_VOCAB_SIZE:
        raise ValueError("ignore_index must be an integer outside output classes")
    if reduction not in ("mean", "sum"):
        raise ValueError("reduction must be mean or sum")
    if isinstance(margin, bool) or not isinstance(margin, (int, float)) or not math.isfinite(margin) or margin <= 0:
        raise ValueError("margin must be finite and positive")
    valid = targets.ne(ignore_index)
    if bool((valid & ((targets < 0) | (targets >= OUTPUT_VOCAB_SIZE))).any()):
        raise ValueError("target id outside 0..256")
    if not bool(torch.isfinite(energies).all()):
        raise ValueError("energies contain NaN or infinity")
    if not bool(valid.any()):
        # Zero each finite entry before reduction: sum()*0 can overflow to NaN.
        return (energies * 0.0).sum()
    # Low-precision input energies should not force low-precision subtraction
    # or reduction. The cast remains differentiable back to the model output.
    chosen = energies[valid]
    if chosen.dtype in (torch.float16, torch.bfloat16):
        chosen = chosen.float()
    gold = targets[valid, None]
    gold_energy = chosen.gather(-1, gold).squeeze(-1)
    wrong_energy = chosen.scatter(-1, gold, float("inf")).amin(-1)
    # Subtract first so a common large energy offset does not erase the margin.
    losses = ((gold_energy - wrong_energy) + margin).clamp_min(0.0)
    result = losses.sum() if reduction == "sum" else losses.mean()
    if not bool(torch.isfinite(result)):
        raise ValueError("hinge loss overflow; reduce the energy scale or use a wider dtype")
    return result
