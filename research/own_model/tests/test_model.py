"""Machine invariants only. Fixtures are not a language/meaning benchmark."""
import math

import pytest
import torch
import torch.nn.functional as F

from mizan_reply.model import (
    ASSISTANT_ID, INPUT_VOCAB_SIZE, ModelConfig, MizanReplyModel,
    RADICALS, RadicalComposer, margin_loss,
)


def small_model(mode="none", **kwargs):
    torch.manual_seed(37)
    return MizanReplyModel(ModelConfig(dim=12, layers=4, max_seq_len=30, root_dim=5, root_mode=mode, **kwargs))


def content_fixture():
    ids = torch.tensor([[257, 120, 121, 122, ASSISTANT_ID, 80, 81, 82]], dtype=torch.int64)
    roots = torch.zeros((1, ids.shape[1], 4), dtype=torch.int64)
    roots[0, 2] = torch.tensor([2, 3, 4, 0])
    roots[0, 3] = torch.tensor([4, 3, 2, 5])
    return ids, roots


def test_config_roundtrip_and_receptive_field():
    cfg = ModelConfig()
    assert cfg.receptive_field == 4095
    assert ModelConfig.from_dict(cfg.to_dict()) == cfg
    with pytest.raises(ValueError, match="unknown"):
        ModelConfig.from_dict({"softmax": True})
    with pytest.raises(ValueError, match="receptive field"):
        ModelConfig(layers=2, max_seq_len=8)


@pytest.mark.parametrize("kwargs", [
    {"dim": True}, {"dim": 1}, {"layers": 0}, {"layers": 31}, {"kernel_size": 1},
    {"max_seq_len": -1}, {"root_dim": 0}, {"root_mode": "magic"},
    {"margin": 0}, {"margin": True}, {"margin": float("nan")},
])
def test_bad_config_rejected(kwargs):
    with pytest.raises(ValueError):
        ModelConfig(**kwargs)


def test_fixed_bits_injective_no_unknown_byte():
    model = small_model()
    assert model.input_bits.shape == (INPUT_VOCAB_SIZE, 9)
    assert torch.unique(model.input_bits, dim=0).shape[0] == INPUT_VOCAB_SIZE
    assert set(model.input_bits.unique().tolist()) == {-1.0, 1.0}
    assert "input_bits" not in dict(model.named_parameters())
    # Every UTF-8 byte is representable without a language-specific vocabulary.
    ids = torch.tensor([list("علم 🧪 தமிழ்".encode("utf-8"))])
    model(ids)


@pytest.mark.parametrize("mode", ["none", "ordered", "bag"])
def test_causality_future_token_and_root_cannot_change_past(mode):
    model = small_model(mode).eval()
    ids, roots = content_fixture()
    original = model(ids, roots)
    future = ids.clone()
    future[:, 5:] = torch.tensor([200, 201, 202])
    other_roots = roots.clone()
    other_roots[0, 6] = torch.tensor([7, 8, 9, 0])
    changed = model(future, other_roots)
    torch.testing.assert_close(original[:, :5], changed[:, :5], atol=0, rtol=0)


def test_channel_normalization_and_padding_independence():
    model = small_model("ordered").eval()
    ids, roots = content_fixture()
    solo = model(ids[:, :4], roots[:, :4])
    padded = model(F.pad(ids[:, :4], (0, 4), value=0), F.pad(roots[:, :4], (0, 0, 0, 4)))
    # Different batch mates and padding must not alter a shorter example's past.
    batched_ids = torch.cat([ids, torch.flip(ids, [1])], dim=0)
    batched_roots = torch.cat([roots, torch.zeros_like(roots)], dim=0)
    batched = model(batched_ids, batched_roots)
    torch.testing.assert_close(solo, padded[:, :4], atol=1e-6, rtol=1e-6)
    torch.testing.assert_close(solo, batched[:1, :4], atol=1e-6, rtol=1e-6)


def test_manual_causal_kernel_matches_dilated_conv1d():
    model = small_model()
    hidden = torch.randn(2, 13, 12)
    for block in model.blocks:
        norm = block.norm(hidden)
        expected = F.conv1d(
            F.pad(norm.transpose(1, 2), (block.history_size, 0)),
            block.conv.weight, block.conv.bias, dilation=block.dilation,
        ).transpose(1, 2)
        torch.testing.assert_close(block._causal_affine(norm), expected, atol=1e-6, rtol=1e-6)


@pytest.mark.parametrize("mode", ["none", "ordered", "bag"])
def test_cached_all_steps_and_prefill_equal_full_prefix(mode):
    model = small_model(mode).eval()
    ids, roots = content_fixture()
    cache = model.new_cache(1)
    for i in range(ids.shape[1]):
        got = model.step(ids[:, i], cache, roots[:, i])
        expected = model(ids[:, :i + 1], roots[:, :i + 1])[:, -1]
        torch.testing.assert_close(got, expected, atol=1e-6, rtol=1e-6)
    # Exercise wrapped ring buffers and a prefill longer than small-layer history.
    got, cache = model.prefill(ids[:, :5], roots[:, :5])
    torch.testing.assert_close(got, model(ids[:, :5], roots[:, :5])[:, -1], atol=1e-6, rtol=1e-6)
    for i in range(5, ids.shape[1]):
        got = model.step(ids[:, i], cache, roots[:, i])
        torch.testing.assert_close(got, model(ids[:, :i + 1], roots[:, :i + 1])[:, -1], atol=1e-6, rtol=1e-6)


def test_cache_batched_parity_and_context_limit():
    model = small_model("ordered").eval()
    ids = torch.randint(0, 256, (2, 30))
    roots = torch.zeros((2, 30, 4), dtype=torch.int64)
    roots[0, 2] = torch.tensor([1, 3, 5, 0])
    roots[1, 20] = torch.tensor([5, 3, 1, 7])
    got, cache = model.prefill(ids[:, :20], roots[:, :20])
    for i in range(20, 30):
        got = model.step(ids[:, i], cache, roots[:, i])
    torch.testing.assert_close(got, model(ids, roots)[:, -1], atol=2e-6, rtol=2e-6)
    with pytest.raises(ValueError, match="budget"):
        model.step(ids[:, 0], cache)
    with pytest.raises(ValueError, match="no truncation"):
        model(torch.zeros(1, 31, dtype=torch.int64))


def test_cache_owner_and_inference_only():
    model = small_model()
    with pytest.raises(RuntimeError, match="inference-only"):
        model.prefill(torch.tensor([[1]]))
    model.eval()
    other = small_model().eval()
    with pytest.raises(ValueError, match="exact model"):
        model.step(torch.tensor([1]), other.new_cache())


def test_order_is_representable_and_bag_is_permutation_invariant():
    ordered = RadicalComposer(3, "ordered")
    with torch.no_grad():
        ordered.A.copy_(torch.eye(3).repeat(28, 1, 1))
        ordered.b.zero_()
        ordered.A[0] = torch.tensor([[1., .5, 0.], [0., 1., 0.], [0., 0., 1.]])
        ordered.A[1] = torch.tensor([[1., 0., 0.], [.5, 1., 0.], [0., 0., 1.]])
        ordered.b[2] = torch.tensor([.2, -.1, .3])
    roots = torch.tensor([[1, 2, 3, 0], [3, 2, 1, 0]])
    values = ordered(roots)
    assert (values[0] - values[1]).abs().max() > 1e-3
    bag = RadicalComposer(3, "bag")
    bag.load_state_dict(ordered.state_dict())
    torch.testing.assert_close(bag(roots)[0], bag(roots)[1], atol=1e-7, rtol=1e-7)
    assert torch.equal(ordered(torch.zeros(1, 4, dtype=torch.int64)), torch.zeros(1, 3))
    # This verifies expressive capability, not Arabic semantic usefulness.


@pytest.mark.parametrize("mode", ["none", "ordered", "bag"])
@pytest.mark.parametrize("rooted", [False, True])
def test_hinge_backward_all_parameters_connected_even_rootless(mode, rooted):
    model = small_model(mode)
    ids, roots = content_fixture()
    energies = model(ids, roots if rooted else None)
    labels = torch.full(ids.shape, -100, dtype=torch.int64)
    labels[0, 4:7] = ids[0, 5:8]
    labels[0, 7] = 256
    loss = margin_loss(energies, labels, reduction="sum", margin=model.config.margin)
    loss.backward()
    assert math.isfinite(float(loss.detach()))
    assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters())
    assert model.output_projection.weight.grad.abs().sum() > 0
    if mode == "none":
        assert not any("root_" in n for n, _ in model.named_parameters())


@pytest.mark.parametrize("mode", ["none", "ordered", "bag"])
def test_all_ignore_loss_remains_ddp_connected(mode):
    model = small_model(mode)
    ids = torch.tensor([[257, 259]])
    loss = margin_loss(model(ids), torch.full_like(ids, -100))
    assert loss.item() == 0
    loss.backward()
    assert all(p.grad is not None for p in model.parameters())
    assert all(torch.count_nonzero(p.grad) == 0 for p in model.parameters())


def test_loss_hardest_wrong_direction_reduction_and_mask():
    e = torch.full((1, 3, 257), 4.0)
    e[0, 0, 5], e[0, 0, 7] = 1, 0
    e[0, 1, 5], e[0, 1, 7] = -2, 0
    e.requires_grad_()
    targets = torch.tensor([[5, 5, -100]])
    assert margin_loss(e, targets, reduction="sum").item() == 2
    assert margin_loss(e, targets, reduction="mean").item() == 1
    margin_loss(e, targets, reduction="sum").backward()
    assert e.grad[0, 0, 5] == 1  # Gradient descent lowers gold energy.
    assert e.grad[0, 0, 7] == -1  # Gradient descent raises closest wrong energy.
    assert torch.count_nonzero(e.grad[0, 2]) == 0


@pytest.mark.parametrize("bad", [-1, 263])
def test_invalid_token_rejected(bad):
    with pytest.raises(ValueError, match="outside"):
        small_model()(torch.tensor([[bad]]))


@pytest.mark.parametrize("root", [[1, 0, 2, 3], [1, 2, 0, 0], [1, 2, 29, 0], [-1, 2, 3, 0]])
def test_invalid_roots_rejected_even_no_root_control(root):
    with pytest.raises(ValueError):
        small_model("none")(torch.tensor([[120]]), torch.tensor([[root]]))


def test_structural_root_and_malformed_shapes_rejected():
    model = small_model("ordered")
    with pytest.raises(ValueError, match="structural"):
        model(torch.tensor([[ASSISTANT_ID]]), torch.tensor([[[1, 2, 3, 0]]]))
    with pytest.raises(ValueError, match="int64"):
        model(torch.ones(1, 2))
    with pytest.raises(ValueError, match="roots"):
        model(torch.tensor([[120]]), torch.zeros(1, 1, 3, dtype=torch.int64))
    assert len(RADICALS) == 28 and "ا" not in RADICALS


def test_loss_rejects_out_of_range_labels_and_nonfinite_values():
    e = torch.zeros(1, 1, 257)
    with pytest.raises(ValueError, match="outside"):
        margin_loss(e, torch.tensor([[257]]))
    e[0, 0, 0] = float("nan")
    with pytest.raises(ValueError, match="NaN"):
        margin_loss(e, torch.tensor([[0]]))
