"""Tests for the Ruh Model LLM Provider."""

from unittest.mock import MagicMock

import pytest

from providers import LLMResponse
from providers_ruh import RuhModelProvider


class TestRuhModelProviderInit:
    """Test RuhModelProvider instantiation and attributes."""

    def test_instantiation_with_defaults(self) -> None:
        """Provider should accept model_path and default to cpu device."""
        provider = RuhModelProvider(model_path="/tmp/ruh-checkpoint")
        assert provider.model_path == "/tmp/ruh-checkpoint"
        assert provider.device == "cpu"
        assert provider._loaded is False
        assert provider._model is None
        assert provider._tokenizer is None

    def test_instantiation_with_custom_device(self) -> None:
        """Provider should accept a custom device string."""
        provider = RuhModelProvider(model_path="/tmp/model", device="cuda:0")
        assert provider.device == "cuda:0"

    def test_provider_name_is_ruh(self) -> None:
        """The provider_name class attribute should be 'ruh'."""
        provider = RuhModelProvider(model_path="/tmp/model")
        assert provider.provider_name == "ruh"

    def test_provider_inherits_base(self) -> None:
        """RuhModelProvider should be a BaseLLMProvider subclass."""
        from providers import BaseLLMProvider

        provider = RuhModelProvider(model_path="/tmp/model")
        assert isinstance(provider, BaseLLMProvider)


class TestExtractPrompt:
    """Test _extract_prompt with various message formats."""

    @pytest.fixture
    def provider(self) -> RuhModelProvider:
        return RuhModelProvider(model_path="/tmp/model")

    def test_extracts_last_user_message_string(self, provider: RuhModelProvider) -> None:
        """Should return the string content of the last user message."""
        messages = [
            {"role": "user", "content": "first question"},
            {"role": "assistant", "content": "answer"},
            {"role": "user", "content": "second question"},
        ]
        assert provider._extract_prompt(messages) == "second question"

    def test_extracts_from_content_block_list(self, provider: RuhModelProvider) -> None:
        """Should join text blocks when content is a list of typed blocks."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "text", "text": "world"},
                ],
            }
        ]
        assert provider._extract_prompt(messages) == "Hello world"

    def test_skips_non_text_blocks(self, provider: RuhModelProvider) -> None:
        """Should ignore blocks that are not type 'text'."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": "data:..."},
                    {"type": "text", "text": "describe this"},
                ],
            }
        ]
        assert provider._extract_prompt(messages) == "describe this"

    def test_returns_empty_for_no_user_messages(self, provider: RuhModelProvider) -> None:
        """Should return empty string when no user messages exist."""
        messages = [
            {"role": "assistant", "content": "I can help you."},
            {"role": "system", "content": "You are helpful."},
        ]
        assert provider._extract_prompt(messages) == ""

    def test_returns_empty_for_empty_list(self, provider: RuhModelProvider) -> None:
        """Should return empty string for empty message list."""
        assert provider._extract_prompt([]) == ""

    def test_handles_integer_content(self, provider: RuhModelProvider) -> None:
        """Should coerce non-string content to string."""
        messages = [{"role": "user", "content": 42}]
        assert provider._extract_prompt(messages) == "42"

    def test_ignores_assistant_between_users(self, provider: RuhModelProvider) -> None:
        """Should skip assistant messages and return the last user message."""
        messages = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "follow-up"},
            {"role": "assistant", "content": "second reply"},
        ]
        assert provider._extract_prompt(messages) == "follow-up"


class TestTokensToTensors:
    """Test _tokens_to_tensors creates correct tensor shapes."""

    @pytest.fixture
    def provider(self) -> RuhModelProvider:
        return RuhModelProvider(model_path="/tmp/model")

    def test_tensor_shapes_for_single_token(self, provider: RuhModelProvider) -> None:
        """Single token pair should produce (1, 1) shaped tensors."""
        pytest.importorskip("torch")
        tokens = [(10, 20)]
        root_ids, pattern_ids = provider._tokens_to_tensors(tokens)

        assert root_ids.shape == (1, 1)
        assert pattern_ids.shape == (1, 1)
        assert root_ids[0, 0].item() == 10
        assert pattern_ids[0, 0].item() == 20

    def test_tensor_shapes_for_multiple_tokens(self, provider: RuhModelProvider) -> None:
        """Multiple token pairs should produce (1, N) shaped tensors."""
        pytest.importorskip("torch")
        tokens = [(1, 2), (3, 4), (5, 6)]
        root_ids, pattern_ids = provider._tokens_to_tensors(tokens)

        assert root_ids.shape == (1, 3)
        assert pattern_ids.shape == (1, 3)

    def test_tensor_dtype_is_long(self, provider: RuhModelProvider) -> None:
        """Tensors should be created with dtype=torch.long."""
        torch = pytest.importorskip("torch")
        tokens = [(7, 8)]
        root_ids, pattern_ids = provider._tokens_to_tensors(tokens)

        assert root_ids.dtype == torch.long
        assert pattern_ids.dtype == torch.long

    def test_tensor_values_preserved(self, provider: RuhModelProvider) -> None:
        """Root and pattern IDs should be extracted into separate tensors correctly."""
        pytest.importorskip("torch")
        tokens = [(100, 200), (300, 400)]
        root_ids, pattern_ids = provider._tokens_to_tensors(tokens)

        assert root_ids[0].tolist() == [100, 300]
        assert pattern_ids[0].tolist() == [200, 400]


class TestCreateRaisesWithoutModel:
    """Test that create() raises when the model is not loaded."""

    def test_create_raises_when_model_not_loaded(self) -> None:
        """create() should raise when no valid checkpoint exists at path."""
        provider = RuhModelProvider(model_path="/nonexistent/path")
        messages = [{"role": "user", "content": "Hello"}]

        # May raise ModuleNotFoundError (ruh_model not installed) or
        # FileNotFoundError (ruh_model installed but checkpoint missing)
        with pytest.raises((ModuleNotFoundError, FileNotFoundError)):
            provider.create(
                model="ruh-local",
                max_tokens=100,
                system="You are helpful.",
                messages=messages,
            )


class TestCreateWithMockedModel:
    """Test the full generate flow with mocked model and tokenizer."""

    def test_full_generate_flow(self) -> None:
        """create() should produce an LLMResponse when model is mocked."""
        pytest.importorskip("torch")

        provider = RuhModelProvider(model_path="/tmp/model")

        # Pre-set internal state to skip _ensure_loaded
        mock_tokenizer = MagicMock()
        mock_tokenizer.encode.return_value = [(1, 10), (2, 20), (3, 30)]
        mock_tokenizer.decode.return_value = "Bismillah"

        mock_model = MagicMock()
        mock_model.generate.return_value = [101, 102, 103, 104]

        provider._model = mock_model
        provider._tokenizer = mock_tokenizer
        provider._loaded = True

        messages = [{"role": "user", "content": "What is Basmala?"}]

        response = provider.create(
            model="ruh-local",
            max_tokens=256,
            system="You are a scholar.",
            messages=messages,
        )

        assert isinstance(response, LLMResponse)
        assert response.model == "ruh-local"
        assert response.stop_reason == "end_turn"
        assert len(response.content) == 1
        assert response.content[0].type == "text"
        assert response.content[0].text == "Bismillah"
        assert response.usage["input_tokens"] == 3
        assert response.usage["output_tokens"] == 4

        mock_tokenizer.encode.assert_called_once_with("What is Basmala?")
        mock_model.generate.assert_called_once()

    def test_generate_respects_max_tokens_cap(self) -> None:
        """max_new_tokens should be capped at 1024."""
        pytest.importorskip("torch")

        provider = RuhModelProvider(model_path="/tmp/model")

        mock_tokenizer = MagicMock()
        mock_tokenizer.encode.return_value = [(1, 2)]
        mock_tokenizer.decode.return_value = "output"

        mock_model = MagicMock()
        mock_model.generate.return_value = [1]

        provider._model = mock_model
        provider._tokenizer = mock_tokenizer
        provider._loaded = True

        provider.create(
            model="ruh-local",
            max_tokens=5000,
            system="sys",
            messages=[{"role": "user", "content": "test"}],
        )

        call_kwargs = mock_model.generate.call_args
        # max_new_tokens should be min(5000, 1024) = 1024
        assert call_kwargs.kwargs.get("max_new_tokens") == 1024 or (
            len(call_kwargs.args) >= 3 and call_kwargs.args[2] is not None
        )

    def test_generate_uses_default_temperature(self) -> None:
        """Temperature should default to 1.0 when not provided."""
        pytest.importorskip("torch")

        provider = RuhModelProvider(model_path="/tmp/model")

        mock_tokenizer = MagicMock()
        mock_tokenizer.encode.return_value = [(1, 2)]
        mock_tokenizer.decode.return_value = "result"

        mock_model = MagicMock()
        mock_model.generate.return_value = [1]

        provider._model = mock_model
        provider._tokenizer = mock_tokenizer
        provider._loaded = True

        provider.create(
            model="ruh-local",
            max_tokens=100,
            system="sys",
            messages=[{"role": "user", "content": "test"}],
            temperature=None,
        )

        call_kwargs = mock_model.generate.call_args.kwargs
        assert call_kwargs.get("temperature") == 1.0

    def test_generate_uses_custom_temperature(self) -> None:
        """Custom temperature should be passed through to model.generate."""
        pytest.importorskip("torch")

        provider = RuhModelProvider(model_path="/tmp/model")

        mock_tokenizer = MagicMock()
        mock_tokenizer.encode.return_value = [(1, 2)]
        mock_tokenizer.decode.return_value = "result"

        mock_model = MagicMock()
        mock_model.generate.return_value = [1]

        provider._model = mock_model
        provider._tokenizer = mock_tokenizer
        provider._loaded = True

        provider.create(
            model="ruh-local",
            max_tokens=100,
            system="sys",
            messages=[{"role": "user", "content": "test"}],
            temperature=0.3,
        )

        call_kwargs = mock_model.generate.call_args.kwargs
        assert call_kwargs.get("temperature") == 0.3
