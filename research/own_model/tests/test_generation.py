"""Decoder syntax and cache invariants, not learned conversational examples."""
from unittest.mock import patch

import pytest
import torch

from mizan_reply.generation import UTF8State, generate
from mizan_reply.model import ASSISTANT_ID, ModelConfig, MizanReplyModel


def model_fixture():
    torch.manual_seed(51)
    return MizanReplyModel(ModelConfig(dim=8, layers=4, max_seq_len=30, root_dim=4, root_mode="ordered"))


def scripted_energy(tokens, index):
    scores = torch.full((1, 257), 10.0)
    scores[0, tokens[index]] = -10
    return scores


def test_utf8_scalar_boundaries_and_forbidden_sequences():
    for text in ["\x00\x7f", "é", "علم", "தமிழ்", "🧪", "\u0800", "\ud7ff", "\ue000", "\U0010ffff"]:
        raw = text.encode("utf-8")
        state = UTF8State()
        for i, byte in enumerate(raw):
            assert state.allowed(len(raw) - i)[byte]
            state.consume(byte)
        assert state.remaining == 0
        assert state.allowed(1)[256]
    for invalid in [[0x80], [0xC0], [0xC1], [0xF5], [0xE0, 0x9F], [0xED, 0xA0], [0xF0, 0x8F], [0xF4, 0x90]]:
        state = UTF8State()
        with pytest.raises(ValueError):
            for byte in invalid:
                state.consume(byte)


def test_eos_forbidden_inside_multibyte_and_budget_lookahead():
    state = UTF8State()
    assert not state.allowed(1)[0xC2]
    assert not state.allowed(2)[0xE0]
    assert not state.allowed(3)[0xF0]
    state.consume(0xD8)
    assert not state.allowed(1)[256]
    with pytest.raises(ValueError, match="continuation"):
        state.consume(256)
    state.consume(0xB9)
    assert state.allowed(1)[256]


def test_generator_unicode_eos_source_only_roots_and_mode_restore():
    model = model_fixture()
    model.train()
    prompt = torch.tensor([257, 120, ASSISTANT_ID])
    source_roots = torch.tensor([[0, 0, 0, 0], [1, 2, 3, 0], [0, 0, 0, 0]])
    expected_text = "ع🧪"
    tokens = list(expected_text.encode("utf-8")) + [256]
    stepped = []
    def fake_prefill(ids, roots):
        assert torch.equal(roots, source_roots[None])
        assert not model.training
        return scripted_energy(tokens, 0), model.new_cache()
    def fake_step(ids, cache, roots=None):
        assert roots is None  # No oracle roots for the generated answer.
        stepped.append(int(ids[0]))
        return scripted_energy(tokens, len(stepped))
    with patch.object(model, "prefill", side_effect=fake_prefill), patch.object(model, "step", side_effect=fake_step):
        result = generate(model, prompt, source_roots, max_new_tokens=len(tokens))
    assert model.training
    assert result.text == expected_text
    assert result.token_ids == tokens
    assert result.eos and result.stop_reason == "eos"
    assert stepped == tokens[:-1]


def test_greedy_ties_choose_lowest_valid_id_and_do_not_mutate_weights():
    model = model_fixture().eval()
    prompt = torch.tensor([257, ASSISTANT_ID])
    old_weights = {k: v.clone() for k, v in model.state_dict().items()}
    with patch.object(model, "prefill", return_value=(torch.zeros(1, 257), model.new_cache())):
        result = generate(model, prompt, max_new_tokens=1)
    assert result.token_ids == [0]
    assert result.text == "\x00" and not result.eos
    assert not model.training
    assert all(torch.equal(old_weights[k], v) for k, v in model.state_dict().items())


def test_real_untrained_generator_deterministic_valid_utf8_no_semantic_claim():
    model = model_fixture()
    prompt = torch.tensor([257, 120, ASSISTANT_ID])
    first = generate(model, prompt, max_new_tokens=12)
    second = generate(model, prompt, max_new_tokens=12)
    assert first == second
    assert first.text.encode("utf-8") == bytes(t for t in first.token_ids if t != 256)
    assert model.training
    assert first.generated_tokens == len(first.token_ids)


def test_token_budget_never_returns_partial_unicode():
    model = model_fixture()
    scores = torch.full((1, 257), 10.0)
    scores[0, 0xF0] = -20  # Four-byte lead cannot fit in a one-token budget.
    scores[0, ord("x")] = -10
    with patch.object(model, "prefill", return_value=(scores, model.new_cache())):
        result = generate(model, torch.tensor([257, ASSISTANT_ID]), max_new_tokens=1)
    assert result.text == "x" and result.stop_reason == "token_limit"


def test_generation_exact_context_boundary_and_invalid_requests():
    model = model_fixture()
    prompt = torch.tensor([257] + [120] * 28 + [ASSISTANT_ID])
    generate(model, prompt, max_new_tokens=1)  # Predict once from a full prefix.
    with pytest.raises(ValueError, match="context"):
        generate(model, prompt, max_new_tokens=2)
    with pytest.raises(ValueError, match="ASSISTANT"):
        generate(model, torch.tensor([257, 120]), max_new_tokens=1)
    with pytest.raises(ValueError, match="positive"):
        generate(model, torch.tensor([257, ASSISTANT_ID]), max_new_tokens=0)
    with pytest.raises(ValueError, match="exactly one"):
        generate(model, torch.tensor([[257, ASSISTANT_ID], [257, ASSISTANT_ID]]), max_new_tokens=1)


def test_generation_nonfinite_scores_abort_and_restore_training():
    model = model_fixture()
    scores = torch.zeros(1, 257)
    scores[0, 0] = float("nan")
    with patch.object(model, "prefill", return_value=(scores, model.new_cache())):
        with pytest.raises(ValueError, match="finite"):
            generate(model, torch.tensor([257, ASSISTANT_ID]), max_new_tokens=1)
    assert model.training
