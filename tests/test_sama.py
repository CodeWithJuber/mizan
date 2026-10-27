"""Sama': short voice messages heard on MIZAN's own server, within limits."""

import json
from types import SimpleNamespace

import httpx
import pytest

from gateway.store import BabStore
from gateway.telegram import TelegramBot
from perception import sama


@pytest.fixture
def store(tmp_path):
    return BabStore(str(tmp_path / "bab.db"))


class FakeModel:
    """Whisper's two calls, recorded: which language, then the words."""

    def __init__(self, probs, text="As-salamu alaykum"):
        self.probs = probs
        self.text = text
        self.calls: list[dict] = []

    def detect_language(self, audio, vad_filter):
        top = max(self.probs, key=lambda item: item[1])
        return top[0], top[1], list(self.probs)

    def transcribe(self, audio, **options):
        self.calls.append(options)
        info = SimpleNamespace(language=options["language"], duration=len(audio) / 16_000)
        return iter([SimpleNamespace(text=f" {self.text} ")]), info


@pytest.fixture
def heard_by(monkeypatch):
    def install(model, seconds=4.0):
        import numpy as np

        monkeypatch.setattr(sama, "available", lambda: True)
        monkeypatch.setattr(sama, "_load", lambda: model)
        monkeypatch.setattr(
            sama, "_decode", lambda audio: np.zeros(int(seconds * 16_000), dtype=np.float32)
        )
        return model

    return install


@pytest.mark.parametrize(
    "audio,mime,message",
    [
        (b"x", "video/mp4", "voice recording"),
        (b"x", "text/plain", "voice recording"),
        (b"", "audio/webm", "empty"),
        (b"x" * (sama.MAX_BYTES + 1), "audio/webm", "over 2 MB"),
    ],
    ids=["video", "text", "empty", "too-large"],  # a 2 MB value must not become a test name
)
def test_only_short_recordings_are_taken(audio, mime, message):
    with pytest.raises(sama.HearingError, match=message):
        sama.check(audio, mime)
    sama.check(b"x", "audio/webm;codecs=opus")  # the browser's own type with codec


def test_a_flat_prior_lets_the_audio_decide():
    probs = [("en", 0.2), ("hi", 0.45), ("ur", 0.35)]
    assert sama.spoken_language(probs, []) == "hi"


def test_the_chats_language_tips_a_borderline_recording():
    # Hindi and Urdu sound alike; the audio leans to Hindi, the chat is in Urdu script.
    probs = [("en", 0.02), ("hi", 0.50), ("ur", 0.48)]
    earlier = ["آج عصر کب ہے؟", "مجھے نماز کا وقت بتائیں", "شکریہ، اب فجر کا وقت؟"]
    assert sama.spoken_language(probs, earlier) == "ur"


def test_clear_audio_is_not_overruled_by_the_chat():
    probs = [("en", 0.97), ("hi", 0.02), ("ur", 0.01)]
    earlier = ["Mujhe namaz ka waqt batao", "aaj Asr kab hai", "shukriya"]
    assert sama.spoken_language(probs, earlier) == "en"


def test_the_users_words_are_context_only_in_the_language_spoken():
    earlier = ["Mujhe namaz ka waqt batao", "aaj Asr kab hai"]
    assert sama._prompt("hi", earlier).endswith("aaj Asr kab hai")
    assert sama._prompt("en", ["What is the time of Asr today?"]) is not None
    assert sama._prompt("ar", earlier) is None  # an Arabic recording in a Hinglish chat
    assert sama._prompt("hi", []) is None


async def test_a_recording_is_heard_and_counted_against_the_day(store, heard_by):
    model = heard_by(FakeModel([("en", 0.1), ("ar", 0.9)]), seconds=4.0)
    heard = await sama.hear(b"opus", "audio/webm", owner="alice", store=store)
    assert heard.text == "As-salamu alaykum" and heard.language == "ar"
    assert model.calls[0]["language"] == "ar" and model.calls[0]["vad_filter"] is True
    assert sama.used_today(store, "alice") == pytest.approx(4.0)
    assert sama.used_today(store, "bob") == 0


async def test_the_daily_allowance_stops_non_admins_only(store, heard_by, monkeypatch):
    heard_by(FakeModel([("en", 1.0)]), seconds=4.0)
    monkeypatch.setenv("MIZAN_STT_DAILY_SECONDS", "5")
    await sama.hear(b"opus", "audio/webm", owner="alice", store=store)
    await sama.hear(b"opus", "audio/webm", owner="alice", store=store)  # 4 s left: allowed
    with pytest.raises(sama.HearingError, match="allowance"):
        await sama.hear(b"opus", "audio/webm", owner="alice", store=store)
    await sama.hear(b"opus", "audio/webm", owner="alice", store=store, limited=False)


async def test_nothing_is_heard_when_voice_is_off(store, monkeypatch):
    monkeypatch.setenv("MIZAN_STT", "off")
    assert sama.available() is False
    with pytest.raises(sama.HearingError, match="not installed"):
        await sama.hear(b"opus", "audio/webm", owner="alice", store=store)


def test_a_long_recording_stops_decoding_at_the_limit(tmp_path, monkeypatch):
    av = pytest.importorskip("av")
    import numpy as np

    path = tmp_path / "long.ogg"
    with av.open(str(path), "w") as container:
        stream = container.add_stream("libopus", rate=48_000)
        stream.layout = "mono"
        frames = int(48_000 * 3)
        frame = av.AudioFrame.from_ndarray(
            np.zeros((1, frames), dtype=np.int16), format="s16", layout="mono"
        )
        frame.rate = 48_000
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    assert len(sama._decode(path.read_bytes())) == pytest.approx(3 * 16_000, rel=0.05)
    monkeypatch.setattr(sama, "MAX_SECONDS", 1.0)
    with pytest.raises(sama.HearingError, match="over 90 seconds"):
        sama._decode(path.read_bytes())
    with pytest.raises(sama.HearingError, match="could not be read"):
        sama._decode(b"not audio at all")


# ── Telegram voice notes ────────────────────────────────────────────────


class FakeTelegram:
    def __init__(self, audio=b"OggS voice"):
        self.calls: list[tuple[str, dict]] = []
        self.audio = audio
        self.downloads = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if "/file/bot" in request.url.path:
            self.downloads += 1
            return httpx.Response(200, content=self.audio)
        method = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content or b"{}")
        self.calls.append((method, body))
        result = {"getFile": {"file_path": "voice/file_7.oga"}}.get(method, True)
        return httpx.Response(200, json={"ok": True, "result": result})

    def sent(self) -> list[str]:
        return [body["text"] for method, body in self.calls if method == "sendMessage"]


def voice_note(**voice):
    return {
        "message": {
            "message_id": 1,
            "chat": {"id": 42, "type": "private"},
            "from": {"id": 42, "is_bot": False},
            "voice": {"file_id": "v1", "duration": 3, "mime_type": "audio/ogg", **voice},
        }
    }


def make_bot(store, fake, turns, heard):
    async def run_turn(owner, session, text):
        turns.append((owner, text))
        return "Wa alaykum as-salam", []

    async def decide(owner, held_id, decision):
        return ""

    async def hear(owner, session, audio, mime):
        heard.append((owner, audio, mime))
        return "Asr kab hai?"

    bot = TelegramBot(
        "test-token", store, run_turn, decide, transport=httpx.MockTransport(fake), hear=hear
    )
    store.redeem(store.new_code("owner-1", "telegram"), "telegram", "42", "42")
    return bot


async def test_a_voice_note_is_heard_then_answered(store):
    fake, turns, heard = FakeTelegram(), [], []
    bot = make_bot(store, fake, turns, heard)
    await bot.handle(voice_note())
    assert heard == [("owner-1", b"OggS voice", "audio/ogg")]
    assert fake.sent()[0] == "Heard: Asr kab hai?"
    assert turns == [("owner-1", "Asr kab hai?")] and fake.sent()[-1] == "Wa alaykum as-salam"


async def test_a_long_voice_note_is_refused_before_download(store):
    fake, turns, heard = FakeTelegram(), [], []
    bot = make_bot(store, fake, turns, heard)
    await bot.handle(voice_note(duration=600))
    await bot.handle(voice_note(file_size=50 * 1024 * 1024))
    assert fake.downloads == 0 and heard == [] and turns == []
    assert "over 90 seconds" in fake.sent()[0] and "over 2 MB" in fake.sent()[1]


async def test_a_download_bigger_than_announced_is_cut_off(store):
    fake, turns, heard = FakeTelegram(audio=b"x" * (3 * 1024 * 1024)), [], []
    bot = make_bot(store, fake, turns, heard)
    await bot.handle(voice_note(file_size=1000))
    assert heard == [] and turns == [] and "over 2 MB" in fake.sent()[-1]


async def test_a_forwarded_voice_note_is_data_not_a_request(store):
    fake, turns, heard = FakeTelegram(), [], []
    bot = make_bot(store, fake, turns, heard)
    update = voice_note()
    update["message"]["forward_origin"] = {"type": "user"}
    await bot.handle(update)
    assert turns[0][1] == "Forwarded message:\n```\nAsr kab hai?\n```"


# ── the route ───────────────────────────────────────────────────────────


def test_voice_routes(tmp_path, monkeypatch, heard_by):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("MIZAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "chat.db"))
    monkeypatch.setenv("MIZAN_OWNED_DB", str(tmp_path / "owned.sqlite3"))
    monkeypatch.setenv("MIZAN_STT_DAILY_SECONDS", "6")
    import api.main as main
    from gateway import store as bab_store
    from security.auth import MizanAuth

    bab_store._STORES.clear()
    auth = MizanAuth("voice-test-signing-key-" * 4, data_dir=str(tmp_path / "users"))
    alice = auth.create_user("alice", "test-password", roles=["user"])
    monkeypatch.setattr(main, "auth", auth)
    client = TestClient(main.app)
    headers = {"Authorization": "Bearer " + auth.create_token(alice)}

    monkeypatch.setattr(sama, "available", lambda: False)
    assert client.get("/api/voice", headers=headers).json()["available"] is False
    off = client.post(
        "/api/voice/transcribe", files={"file": ("a.webm", b"opus", "audio/webm")}, headers=headers
    )
    assert off.status_code == 503

    heard_by(FakeModel([("en", 1.0)], text="What time is Asr?"), seconds=4.0)
    status = client.get("/api/voice", headers=headers).json()
    assert status == {
        "available": True,
        "seconds_left": 6,
        "max_seconds": 90.0,
        "max_bytes": 2097152,
    }
    wrong = client.post(
        "/api/voice/transcribe", files={"file": ("a.txt", b"hi", "text/plain")}, headers=headers
    )
    assert wrong.status_code == 400
    ok = client.post(
        "/api/voice/transcribe", files={"file": ("a.webm", b"opus", "audio/webm")}, headers=headers
    )
    assert ok.json() == {
        "text": "What time is Asr?",
        "language": "en",
        "seconds": 4.0,
        "seconds_left": 2,
    }
    client.post(
        "/api/voice/transcribe", files={"file": ("a.webm", b"opus", "audio/webm")}, headers=headers
    )
    spent = client.post(
        "/api/voice/transcribe", files={"file": ("a.webm", b"opus", "audio/webm")}, headers=headers
    )
    assert spent.status_code == 429 and "allowance" in spent.json()["detail"]
