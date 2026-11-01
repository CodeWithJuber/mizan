"""Exercise transcript ingestion against the current SDK's typed response."""

import threading

import pytest

from knowledge.ingest import extract_youtube

youtube = pytest.importorskip("youtube_transcript_api")
transcripts = pytest.importorskip("youtube_transcript_api._transcripts")


@pytest.mark.asyncio
async def test_typed_transcript_fetch_preserves_text_without_blocking_loop(monkeypatch):
    loop_thread = threading.get_ident()
    worker_threads = []

    def fetch(_client, video_id):
        worker_threads.append(threading.get_ident())
        assert video_id == "dQw4w9WgXcQ"
        return transcripts.FetchedTranscript(
            snippets=[
                transcripts.FetchedTranscriptSnippet(text="العلم", start=0, duration=1),
                transcripts.FetchedTranscriptSnippet(text="is knowledge", start=1, duration=2),
            ],
            video_id=video_id,
            language="Arabic",
            language_code="ar",
            is_generated=False,
        )

    monkeypatch.setattr(youtube.YouTubeTranscriptApi, "fetch", fetch)
    result = await extract_youtube("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result["content"] == "العلم is knowledge"
    assert result["segment_count"] == 2
    assert result["char_count"] == len(result["content"])
    assert result["video_id"] == "dQw4w9WgXcQ"
    assert len(worker_threads) == 1
    assert worker_threads[0] != loop_thread


@pytest.mark.asyncio
async def test_transcript_sdk_failure_returns_structured_error(monkeypatch):
    def fetch(_client, _video_id):
        raise RuntimeError("Captions unavailable")

    monkeypatch.setattr(youtube.YouTubeTranscriptApi, "fetch", fetch)
    result = await extract_youtube("https://youtu.be/dQw4w9WgXcQ")

    assert result["error"] == "Failed to get transcript: Captions unavailable"
    assert result["source_type"] == "youtube"
    assert result["video_id"] == "dQw4w9WgXcQ"
