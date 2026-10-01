"""Sparse MoE equivalence, mixed-precision safety and pod lifecycle regression."""

import copy

import pytest
import torch
from torch import nn

from ruh_model.config import RuhConfig
from ruh_model.layers.shura_moe import ShuraMoE
from ruh_model.model import RuhModel
from ruh_model.train_sequence import run_training


def dense_reference(layer, x):
    probabilities = layer.gate(x).softmax(dim=-1)
    values, indices = probabilities.topk(layer.top_k, dim=-1)
    weights = values / values.sum(dim=-1, keepdim=True)
    output = torch.zeros_like(x)
    for slot in range(layer.top_k):
        for index, expert in enumerate(layer.experts):
            mask = indices[:, :, slot] == index
            if mask.any():
                output = output + expert(x * mask.unsqueeze(-1).float()) * (
                    weights[:, :, slot] * mask.float()
                ).unsqueeze(-1)
    return output


def test_sparse_moe_matches_dense_outputs_and_all_gradients():
    torch.manual_seed(82)
    config = RuhConfig(d_model=32, d_root=8, d_pattern=4, n_heads=4, dropout=0)
    sparse = ShuraMoE(config)
    dense = copy.deepcopy(sparse)
    sparse_x = torch.randn(2, 7, 32, requires_grad=True)
    dense_x = sparse_x.detach().clone().requires_grad_()
    actual, expected = sparse(sparse_x), dense_reference(dense, dense_x)
    torch.testing.assert_close(actual, expected, atol=1e-6, rtol=1e-5)
    gradient = torch.randn_like(actual)
    actual.backward(gradient)
    expected.backward(gradient)
    torch.testing.assert_close(sparse_x.grad, dense_x.grad, atol=1e-6, rtol=1e-5)
    for sparse_parameter, dense_parameter in zip(
        sparse.parameters(), dense.parameters(), strict=True
    ):
        torch.testing.assert_close(
            sparse_parameter.grad, dense_parameter.grad, atol=2e-6, rtol=1e-5
        )


def test_sparse_moe_dispatches_only_selected_tokens_once_per_expert():
    class CountingExpert(nn.Module):
        def __init__(self):
            super().__init__()
            self.tokens = 0
            self.calls = 0

        def forward(self, x):
            self.tokens += x.shape[0]
            self.calls += 1
            return x

    layer = ShuraMoE(RuhConfig(d_model=16, d_root=4, d_pattern=4, n_heads=4))
    experts = nn.ModuleList([CountingExpert() for _ in range(4)])
    layer.experts = experts
    layer(torch.randn(2, 9, 16))
    assert sum(expert.tokens for expert in experts) == 2 * 9 * 2
    assert all(expert.calls <= 1 for expert in experts)


def test_bf16_autocast_full_moe_forward_and_backward_are_finite():
    config = RuhConfig(
        d_model=32,
        d_root=8,
        d_pattern=4,
        n_heads=4,
        n_layers=3,
        n_roots=318,
        max_seq_len=32,
        tokenizer_version=2,
        dropout=0,
    )
    model = RuhModel(config)
    with torch.autocast("cpu", dtype=torch.bfloat16):
        result = model(torch.randint(62, 318, (2, 24)), torch.zeros(2, 24, dtype=torch.long))
        loss = result["logits"].float().square().mean() + result["moe_aux_loss"]
    assert torch.isfinite(loss)
    loss.backward()
    assert all(
        torch.isfinite(parameter.grad).all()
        for parameter in model.parameters()
        if parameter.grad is not None
    )


def test_cuda_bf16_request_refused_on_cpu_before_training(tmp_path):
    with pytest.raises(ValueError, match="BF16 training requires"):
        run_training(
            [], tmp_path / "output", config=RuhConfig(tokenizer_version=2), precision="bfloat16"
        )
