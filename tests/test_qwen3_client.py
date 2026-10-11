"""Unit tests for the Qwen3 serverless client (HTTP fully mocked).

Covers: env config, feature flag, typed errors, retry/backoff behavior,
payload shape, SSE streaming, and the no-key-leak guarantee.
"""

import httpx
import pytest

from api.qwen3_client import (
    Qwen3Config,
    Qwen3Error,
    Qwen3RequestError,
    Qwen3ResponseError,
    Qwen3Unavailable,
    backoff_delay,
    chat_completions_url,
    extract_text,
    extract_usage,
    get_client,
    is_retryable_status,
    qwen3_enabled,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text if text else "{}"
        self.headers = {}

    def json(self):
        if self._json_data is None:
            raise ValueError("no json")
        return self._json_data


def ok_payload(text="hello", model="qwen3-0.6b-quran"):
    return {
        "id": "chatcmpl-1",
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
    }


class FakeAsyncClient:
    """Mimics the httpx.AsyncClient surface used by Qwen3Client."""

    behavior: list = []
    instances: list = []

    def __init__(self, *args, **kwargs):
        self.posts = []
        FakeAsyncClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        self.posts.append({"url": url, "headers": headers, "json": json})
        item = FakeAsyncClient.behavior.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def stream(self, method, url, headers=None, json=None):
        return FakeStream(FakeAsyncClient.behavior.pop(0))


class FakeStream:
    """Mimics the httpx streaming response surface used by generate_stream."""

    def __init__(self, spec):
        # spec: ("sse", [lines]) | ("raw", status, body) | ("error-status", status, body)
        self._spec = spec
        kind = spec[0]
        if kind == "sse":
            self.status_code = 200
            self.headers = {"content-type": "text/event-stream"}
            self._lines = spec[1]
            self._body = b""
        elif kind == "raw":
            self.status_code = spec[1]
            self.headers = {"content-type": "application/json"}
            self._lines = []
            self._body = spec[2]
        else:  # error-status
            self.status_code = spec[1]
            self.headers = {"content-type": "application/json"}
            self._lines = []
            self._body = spec[2]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def aread(self):
        return self._body

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class FakeSyncClient(FakeAsyncClient):
    """Sync variant mimicking httpx.Client."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, headers=None, json=None):
        self.posts.append({"url": url, "headers": headers, "json": json})
        item = FakeAsyncClient.behavior.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def qwen3_env(monkeypatch):
    monkeypatch.setenv("QWEN3_ENABLED", "1")
    monkeypatch.setenv("QWEN3_ENDPOINT_URL", "https://qwen3-test.runpod.net")
    monkeypatch.setenv("QWEN3_API_KEY", "test-key-123")
    monkeypatch.setenv("QWEN3_BACKOFF_BASE", "0")
    monkeypatch.delenv("QWEN3_MODEL", raising=False)
    monkeypatch.delenv("QWEN3_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("QWEN3_MAX_RETRIES", raising=False)


@pytest.fixture
def mock_async_http(monkeypatch):
    FakeAsyncClient.behavior = []
    FakeAsyncClient.instances = []
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    return FakeAsyncClient


@pytest.fixture
def mock_sync_http(monkeypatch):
    FakeAsyncClient.behavior = []
    FakeAsyncClient.instances = []
    monkeypatch.setattr(httpx, "Client", FakeSyncClient)
    return FakeAsyncClient


# ---------------------------------------------------------------------------
# Config / flag
# ---------------------------------------------------------------------------


class TestConfig:
    def test_disabled_by_default(self, monkeypatch):
        for var in (
            "QWEN3_ENABLED",
            "QWEN3_ENDPOINT_URL",
            "QWEN3_API_KEY",
        ):
            monkeypatch.delenv(var, raising=False)
        assert qwen3_enabled() is False
        cfg = Qwen3Config.from_env()
        assert cfg.enabled is False
        assert cfg.model == "qwen3-0.6b-quran"
        assert cfg.timeout_s == 60.0
        assert cfg.max_retries == 3

    def test_flag_truthy_values(self, monkeypatch, qwen3_env):
        for truthy in ("1", "true", "TRUE", "yes", "Yes"):
            monkeypatch.setenv("QWEN3_ENABLED", truthy)
            assert qwen3_enabled() is True, truthy
        for falsy in ("0", "false", "no", ""):
            monkeypatch.setenv("QWEN3_ENABLED", falsy)
            assert qwen3_enabled() is False, falsy

    def test_enabled_requires_url_and_key(self, monkeypatch, qwen3_env):
        monkeypatch.delenv("QWEN3_ENDPOINT_URL")
        assert qwen3_enabled() is False
        monkeypatch.setenv("QWEN3_ENDPOINT_URL", "https://x.example")
        monkeypatch.delenv("QWEN3_API_KEY")
        assert qwen3_enabled() is False

    def test_endpoint_host_never_leaks_key(self, qwen3_env):
        cfg = Qwen3Config.from_env()
        assert cfg.endpoint_host() == "qwen3-test.runpod.net"
        assert "test-key-123" not in cfg.endpoint_host()

    def test_chat_url(self, qwen3_env):
        cfg = Qwen3Config.from_env()
        assert chat_completions_url(cfg) == "https://qwen3-test.runpod.net/v1/chat/completions"

    def test_backoff_schedule(self):
        assert backoff_delay(0, 0.5) == pytest.approx(0.5)
        assert backoff_delay(1, 0.5) == pytest.approx(1.0)
        assert backoff_delay(2, 0.5) == pytest.approx(2.0)
        assert backoff_delay(10, 0.5) == pytest.approx(30.0)  # capped


# ---------------------------------------------------------------------------
# generate()
# ---------------------------------------------------------------------------


class TestGenerate:
    async def test_disabled_raises_typed_unavailable(self, monkeypatch):
        monkeypatch.delenv("QWEN3_ENABLED", raising=False)
        with pytest.raises(Qwen3Unavailable) as exc_info:
            await get_client().generate([{"role": "user", "content": "hi"}])
        assert exc_info.value.code == "qwen3_disabled"

    async def test_unconfigured_raises_typed_unavailable(self, monkeypatch):
        monkeypatch.setenv("QWEN3_ENABLED", "1")
        monkeypatch.delenv("QWEN3_ENDPOINT_URL", raising=False)
        with pytest.raises(Qwen3Unavailable) as exc_info:
            await get_client().generate([{"role": "user", "content": "hi"}])
        assert exc_info.value.code == "qwen3_not_configured"

    async def test_success_shape(self, qwen3_env, mock_async_http):
        FakeAsyncClient.behavior = [FakeResponse(200, ok_payload("salam"))]
        result = await get_client().generate(
            [{"role": "user", "content": "hi"}],
            system="sys",
            max_tokens=10,
            temperature=0.1,
        )
        assert result.text == "salam"
        assert result.model == "qwen3-0.6b-quran"
        assert result.usage["total_tokens"] == 7
        post = FakeAsyncClient.instances[0].posts[0]
        assert post["url"] == "https://qwen3-test.runpod.net/v1/chat/completions"
        assert post["headers"]["Authorization"] == "Bearer test-key-123"
        payload = post["json"]
        assert payload["messages"][0] == {"role": "system", "content": "sys"}
        assert payload["messages"][1] == {"role": "user", "content": "hi"}
        assert payload["max_tokens"] == 10
        assert payload["temperature"] == pytest.approx(0.1)
        assert payload["stream"] is False

    async def test_retry_then_success(self, qwen3_env, mock_async_http):
        FakeAsyncClient.behavior = [
            FakeResponse(500, None, "boom"),
            FakeResponse(200, ok_payload("recovered")),
        ]
        result = await get_client().generate([{"role": "user", "content": "hi"}])
        assert result.text == "recovered"
        total_posts = sum(len(i.posts) for i in FakeAsyncClient.instances)
        assert total_posts == 2

    async def test_exhausted_retries(self, qwen3_env, mock_async_http):
        FakeAsyncClient.behavior = [FakeResponse(500, None, "boom")] * 4
        with pytest.raises(Qwen3Unavailable) as exc_info:
            await get_client().generate([{"role": "user", "content": "hi"}])
        assert exc_info.value.code == "qwen3_exhausted"
        total_posts = sum(len(i.posts) for i in FakeAsyncClient.instances)
        assert total_posts == 4  # 1 + 3 retries

    async def test_no_retry_on_400(self, qwen3_env, mock_async_http):
        FakeAsyncClient.behavior = [FakeResponse(400, None, "bad request")]
        with pytest.raises(Qwen3RequestError) as exc_info:
            await get_client().generate([{"role": "user", "content": "hi"}])
        assert exc_info.value.code == "qwen3_rejected"
        total_posts = sum(len(i.posts) for i in FakeAsyncClient.instances)
        assert total_posts == 1

    async def test_auth_error_not_retryable(self, qwen3_env, mock_async_http):
        FakeAsyncClient.behavior = [FakeResponse(401, None, "unauthorized")]
        with pytest.raises(Qwen3RequestError) as exc_info:
            await get_client().generate([{"role": "user", "content": "hi"}])
        assert exc_info.value.code == "qwen3_auth"

    async def test_timeout_retries(self, qwen3_env, mock_async_http):
        FakeAsyncClient.behavior = [
            httpx.TimeoutException("timed out"),
            FakeResponse(200, ok_payload("late")),
        ]
        result = await get_client().generate([{"role": "user", "content": "hi"}])
        assert result.text == "late"

    async def test_connect_error_exhausts(self, qwen3_env, mock_async_http):
        FakeAsyncClient.behavior = [httpx.ConnectError("refused")] * 4
        with pytest.raises(Qwen3Unavailable) as exc_info:
            await get_client().generate([{"role": "user", "content": "hi"}])
        assert exc_info.value.code == "qwen3_exhausted"

    async def test_bad_payload(self, qwen3_env, mock_async_http):
        FakeAsyncClient.behavior = [FakeResponse(200, {"no": "choices"})]
        with pytest.raises(Qwen3ResponseError):
            await get_client().generate([{"role": "user", "content": "hi"}])

    def test_sync_generate(self, qwen3_env, mock_sync_http):
        FakeAsyncClient.behavior = [FakeResponse(200, ok_payload("sync-ok"))]
        result = get_client().generate_sync([{"role": "user", "content": "hi"}])
        assert result.text == "sync-ok"

    def test_sync_disabled(self, monkeypatch):
        monkeypatch.delenv("QWEN3_ENABLED", raising=False)
        with pytest.raises(Qwen3Unavailable):
            get_client().generate_sync([{"role": "user", "content": "hi"}])


# ---------------------------------------------------------------------------
# generate_stream()
# ---------------------------------------------------------------------------


class TestGenerateStream:
    async def test_sse_deltas(self, qwen3_env, mock_async_http):
        lines = [
            'data: {"choices": [{"delta": {"content": "Hello "}}]}',
            "",
            'data: {"choices": [{"delta": {"content": "world"}}]}',
            "data: [DONE]",
        ]
        FakeAsyncClient.behavior = [("sse", lines)]
        chunks = [
            c async for c in get_client().generate_stream([{"role": "user", "content": "hi"}])
        ]
        assert chunks == ["Hello ", "world"]

    async def test_non_sse_falls_back_to_single_call(self, qwen3_env, mock_async_http):
        FakeAsyncClient.behavior = [
            ("raw", 200, b'{"unexpected": "format"}'),
            FakeResponse(200, ok_payload("fallback-text")),
        ]
        chunks = [
            c async for c in get_client().generate_stream([{"role": "user", "content": "hi"}])
        ]
        assert chunks == ["fallback-text"]

    async def test_stream_disabled(self, monkeypatch):
        monkeypatch.delenv("QWEN3_ENABLED", raising=False)
        with pytest.raises(Qwen3Unavailable):
            [c async for c in get_client().generate_stream([{"role": "user", "content": "hi"}])]

    async def test_stream_error_status_raises(self, qwen3_env, mock_async_http):
        FakeAsyncClient.behavior = [("error-status", 500, b"err")] * 4
        with pytest.raises(Qwen3Unavailable):
            [c async for c in get_client().generate_stream([{"role": "user", "content": "hi"}])]


# ---------------------------------------------------------------------------
# health() / pure helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    async def test_health_without_probe_makes_no_http(self, qwen3_env, mock_async_http):
        report = await get_client().health(probe=False)
        assert report["enabled"] is True
        assert report["configured"] is True
        assert report["endpoint_host"] == "qwen3-test.runpod.net"
        assert "test-key-123" not in str(report)
        assert FakeAsyncClient.instances == []

    async def test_health_probe_failure(self, qwen3_env, mock_async_http):
        FakeAsyncClient.behavior = [FakeResponse(500, None, "down")] * 4
        report = await get_client().health(probe=True)
        assert report["reachable"] is False
        assert report["probe_error"]["code"] == "qwen3_exhausted"

    def test_extract_text_validates(self):
        assert extract_text(ok_payload("x")) == "x"
        with pytest.raises(Qwen3ResponseError):
            extract_text({})
        with pytest.raises(Qwen3ResponseError):
            extract_text({"choices": []})
        with pytest.raises(Qwen3ResponseError):
            extract_text({"choices": [{"message": {"content": 123}}]})

    def test_extract_usage_defaults(self):
        assert extract_usage(ok_payload())["total_tokens"] == 7
        assert extract_usage({}) == {}

    def test_retryable_status(self):
        assert is_retryable_status(429) is True
        assert is_retryable_status(500) is True
        assert is_retryable_status(503) is True
        assert is_retryable_status(400) is False
        assert is_retryable_status(401) is False
        assert is_retryable_status(200) is False

    def test_error_hierarchy(self):
        assert issubclass(Qwen3Unavailable, Qwen3Error)
        assert issubclass(Qwen3RequestError, Qwen3Error)
        assert issubclass(Qwen3ResponseError, Qwen3Error)
        err = Qwen3Unavailable("qwen3_disabled", "off")
        assert err.code == "qwen3_disabled"
        assert "[qwen3_disabled]" in str(err)
