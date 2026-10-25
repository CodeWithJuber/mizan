"""Adversarial numerical checks; fixtures are not a language benchmark."""
from copy import deepcopy
from unittest.mock import patch

import pytest
import torch
import torch.nn.functional as F

from mizan_reply.data import encode_prompt, encode_record
from mizan_reply.generation import generate
from mizan_reply.model import (
    ASSISTANT_ID, ModelConfig, MizanReplyModel, margin_loss,
)


def tiny(mode="ordered", dtype=torch.float32, kernel=3):
    torch.manual_seed(812)
    length = 1 + (kernel - 1) * 15
    return MizanReplyModel(ModelConfig(dim=7, layers=4, kernel_size=kernel,
                          max_seq_len=length, root_dim=3, root_mode=mode)).to(dtype).eval()


@pytest.mark.parametrize("dtype,offset", [(torch.float16, 60000.), (torch.bfloat16, 1e20),
                                         (torch.float32, 1e20), (torch.float64, 1e100)])
def test_large_common_energy_offset_preserves_margin(dtype, offset):
    energies = torch.full((1, 1, 257), offset, dtype=dtype, requires_grad=True)
    loss = margin_loss(energies, torch.tensor([[2]]), margin=1.25)
    assert loss.item() == 1.25
    loss.backward()
    assert energies.grad[0, 0, 2].item() == 1.
    assert torch.isfinite(energies.grad).all()


@pytest.mark.parametrize("dtype", [torch.float16, torch.bfloat16, torch.float32, torch.float64])
def test_all_ignore_at_dtype_limit_is_zero_with_zero_gradient(dtype):
    energies = torch.full((2, 3, 257), torch.finfo(dtype).max, dtype=dtype, requires_grad=True)
    loss = margin_loss(energies, torch.full((2, 3), -100, dtype=torch.long))
    assert loss.item() == 0.
    loss.backward()
    assert torch.count_nonzero(energies.grad) == 0


def test_low_precision_loss_uses_wider_reduction_and_true_overflow_fails_closed():
    energies = torch.full((1, 2, 257), -60000., dtype=torch.float16, requires_grad=True)
    with torch.no_grad():
        energies[:, :, 3] = 60000.
    loss = margin_loss(energies, torch.tensor([[3, 3]]), reduction="sum")
    assert loss.item() == 240002.
    loss.backward()
    assert torch.isfinite(energies.grad).all()
    energies = torch.full((1, 1, 257), -torch.finfo(torch.float32).max)
    energies[0, 0, 3] = torch.finfo(torch.float32).max
    with pytest.raises(ValueError, match="overflow"):
        margin_loss(energies, torch.tensor([[3]]))


@pytest.mark.parametrize("change", ["inplace", "replacement", "load", "dtype", "buffer"])
def test_cache_rejects_stale_state_before_mutating(change):
    model = tiny()
    ids = torch.tensor([[4, 11, 192]])
    _, cache = model.prefill(ids)
    old_position = cache.position
    old_values = [layer.values.clone() for layer in cache.layers]
    with torch.no_grad():
        if change == "inplace":
            model.input_projection.weight.add_(0.5)
        elif change == "replacement":
            model.input_projection.weight = torch.nn.Parameter(model.input_projection.weight.clone())
        elif change == "load":
            model.load_state_dict(deepcopy(model.state_dict()))
        elif change == "dtype":
            model.double()
        else:
            model.root_composer.h0.add_(0.25)
    with pytest.raises(ValueError, match="stale"):
        model.step(torch.tensor([5]), cache)
    assert cache.position == old_position
    assert all(torch.equal(layer.values, old) for layer, old in zip(cache.layers, old_values))


def test_cache_rejects_autocast_mode_change():
    model = tiny()
    with torch.autocast("cpu", dtype=torch.bfloat16):
        _, cache = model.prefill(torch.tensor([[4, 5]]))
    with pytest.raises(ValueError, match="stale"):
        model.step(torch.tensor([6]), cache)


def test_model_constructed_in_inference_mode_can_cache_and_detect_updates():
    with torch.inference_mode():
        model = tiny()
        ids = torch.tensor([[4, 5, 6]])
        _, cache = model.prefill(ids[:, :2])
        last = model.step(ids[:, 2], cache)
        torch.testing.assert_close(last, model(ids)[:, -1], atol=3e-6, rtol=3e-6)
        model.root_composer.h0.add_(0.25)
        with pytest.raises(ValueError, match="stale"):
            model.step(torch.tensor([7]), cache)


@pytest.mark.parametrize("corruption", ["missing", "extra", "shape", "dtype", "index", "position", "batch"])
def test_malformed_cache_rejected_without_partial_step(corruption):
    model = tiny()
    _, cache = model.prefill(torch.tensor([[1, 2]]))
    if corruption == "missing":
        cache.layers.pop()
    elif corruption == "extra":
        cache.layers.append(cache.layers[0])
    elif corruption == "shape":
        cache.layers[-1].values = cache.layers[-1].values[:, :-1]
    elif corruption == "dtype":
        cache.layers[-1].values = cache.layers[-1].values.double()
    elif corruption == "index":
        cache.layers[-1].next_index = -1
    elif corruption == "position":
        cache.position = -1
    else:
        cache.batch_size = True
    old_position = cache.position
    old = cache.layers[0].values.clone()
    with pytest.raises(ValueError, match="cache"):
        model.step(torch.tensor([5]), cache)
    assert cache.position == old_position
    assert torch.equal(cache.layers[0].values, old)


@pytest.mark.parametrize("mode", ["none", "ordered", "bag"])
@pytest.mark.parametrize("kernel", [2, 3, 4])
@pytest.mark.parametrize("dtype,atol", [(torch.float64, 2e-12), (torch.float32, 3e-6),
                                       (torch.float16, 0.004), (torch.bfloat16, 0.03)])
def test_cached_full_parity_across_ring_boundaries(mode, kernel, dtype, atol):
    model = tiny(mode, dtype, kernel)
    length = model.config.max_seq_len
    ids = torch.randint(0, 256, (3, length))
    roots = torch.zeros((3, length, 4), dtype=torch.long)
    roots[0, ::3] = torch.tensor([1, 28, 7, 0])
    roots[1, 1::4] = torch.tensor([4, 3, 27, 14])
    with torch.no_grad():
        full = model(ids, roots)
        for prefix in sorted({0, 1, kernel - 1, length // 2, length - 1, length}):
            if prefix:
                last, cache = model.prefill(ids[:, :prefix], roots[:, :prefix])
                torch.testing.assert_close(last, full[:, prefix - 1], atol=atol, rtol=atol)
            else:
                cache = model.new_cache(3)
            for step in range(prefix, length):
                last = model.step(ids[:, step], cache, roots[:, step])
                torch.testing.assert_close(last, full[:, step], atol=atol, rtol=atol)
            with pytest.raises(ValueError, match="budget"):
                model.step(ids[:, 0], cache)


def test_large_dilations_do_not_allocate_the_theoretical_history():
    model = MizanReplyModel(ModelConfig(dim=2, layers=30, max_seq_len=3)).eval()
    ids = torch.tensor([[0, 128, 255]])
    last, cache = model.prefill(ids[:, :1])
    assert all(layer.values.shape[1] <= 3 for layer in cache.layers)
    for i in range(1, 3):
        last = model.step(ids[:, i], cache)
    torch.testing.assert_close(last, model(ids)[:, -1], atol=3e-6, rtol=3e-6)


def test_causal_kernel_forward_and_backward_match_independent_conv():
    model = tiny(dtype=torch.float64, kernel=4)
    for block in model.blocks:
        values = torch.randn(2, 19, 7, dtype=torch.float64, requires_grad=True)
        actual = block._causal_affine(values)
        reference = F.conv1d(F.pad(values.transpose(1, 2), (block.history_size, 0)),
                             block.conv.weight, block.conv.bias,
                             dilation=block.dilation).transpose(1, 2)
        torch.testing.assert_close(actual, reference, atol=1e-12, rtol=1e-12)
        upstream = torch.randn_like(actual)
        inputs = (values, block.conv.weight, block.conv.bias)
        actual_grad = torch.autograd.grad((actual * upstream).sum(), inputs)
        reference_grad = torch.autograd.grad((reference * upstream).sum(), inputs)
        for got, expected in zip(actual_grad, reference_grad):
            torch.testing.assert_close(got, expected, atol=1e-11, rtol=1e-11)


def test_target_boundary_matches_free_running_prefix_without_target_leakage():
    record = {
        "schema_version": "mizan.reply.v1", "id": "dv-alignment", "split": "train",
        "group_id": "dv-alignment-group", "language": "und", "task": "dialogue",
        "messages": [{"role": "user", "content": "x"}], "evidence": [],
        "target": {"text": "é🧪", "citations": [], "answer_status": "answer"},
        "provenance": {"origin": "human_original", "source_ids": ["dv-fixture-source"],
                       "rights": "Technical tensor fixture only; not a semantic corpus",
                       "author_ids": ["dv-author"], "reviewer_ids": ["dv-reviewer"],
                       "review_status": "accepted"},
    }
    model = tiny(dtype=torch.float64)
    prompt = encode_prompt(record["messages"], [], max_seq_len=model.config.max_seq_len)
    encoded = encode_record(record, model.config.max_seq_len)
    p = len(prompt["input_ids"])
    raw = list(record["target"]["text"].encode("utf8"))
    assert encoded["targets"][:p - 1].tolist() == [-100] * (p - 1)
    assert encoded["targets"][p - 1:].tolist() == raw + [256]
    assert torch.count_nonzero(encoded["roots"][p:]) == 0
    full = model(encoded["input_ids"][None], encoded["roots"][None])
    last, cache = model.prefill(prompt["input_ids"][None], prompt["roots"][None])
    torch.testing.assert_close(last, full[:, p - 1], atol=1e-12, rtol=1e-12)
    for i, token in enumerate(raw):
        last = model.step(torch.tensor([token]), cache, roots=None)
        torch.testing.assert_close(last, full[:, p + i], atol=1e-12, rtol=1e-12)
        changed = encoded["input_ids"].clone()
        changed[p + i:] = (changed[p + i:] + 117) % 256
        other = model(changed[None], encoded["roots"][None])
        torch.testing.assert_close(full[:, :p + i], other[:, :p + i], atol=0, rtol=0)


@pytest.mark.parametrize("fail", [False, True])
def test_generation_restores_mixed_module_modes_even_on_failure(fail):
    model = tiny().train()
    model.blocks[0].eval()
    before = [module.training for module in model.modules()]
    energies = torch.zeros(1, 257)
    if fail:
        energies[0, 0] = float("nan")
    with patch.object(model, "prefill", return_value=(energies, model.new_cache())):
        if fail:
            with pytest.raises(ValueError, match="finite"):
                generate(model, torch.tensor([257, ASSISTANT_ID]), max_new_tokens=1)
        else:
            generate(model, torch.tensor([257, ASSISTANT_ID]), max_new_tokens=1)
    assert [module.training for module in model.modules()] == before
