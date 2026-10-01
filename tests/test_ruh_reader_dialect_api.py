"""Tests for the Ruh reader + dialect API routers (beta).

Covers ``backend/api/ruh_reader.py`` (``GET /v1/reader/lookup``,
``POST /v1/reader/build``) and ``backend/api/ruh_dialect.py``
(``POST /v1/normalize``) via FastAPI's TestClient.

Torch-free: the routers load ``ruh_model`` submodules by file path
(``backend/api/_ruh_loader.py``), never triggering
``ruh_model/__init__.py``'s torch import, so these tests run in CI's
``[dev,nlp]`` environment.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.ruh_dialect import router as dialect_router
from api.ruh_reader import router as reader_router


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = FastAPI()
    app.include_router(reader_router)
    app.include_router(dialect_router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def reader_db(monkeypatch: pytest.MonkeyPatch, tmp_path) -> str:  # type: ignore[no-untyped-def]
    db = str(tmp_path / "reader.sqlite")
    monkeypatch.setenv("RUH_READER_DB", db)
    return db


class TestNormalizeEndpoint:
    def test_egyptian(self, client: TestClient) -> None:
        resp = client.post("/v1/normalize", json={"word": "مايعرفش", "dialect_hint": "egyptian"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["root"] == "عرف"
        assert body["dialect"] == "egyptian"
        assert body["foreign"] is False
        assert body["needs_review"] is False
        assert body["beta"] is True

    def test_levantine(self, client: TestClient) -> None:
        resp = client.post("/v1/normalize", json={"word": "عميكتب", "dialect_hint": "levantine"})
        assert resp.json()["root"] == "كتب"

    def test_gulf(self, client: TestClient) -> None:
        resp = client.post("/v1/normalize", json={"word": "مايعرف", "dialect_hint": "gulf"})
        assert resp.json()["root"] == "عرف"

    def test_maghrebi_foreign_bucket(self, client: TestClient) -> None:
        resp = client.post("/v1/normalize", json={"word": "طوموبيل", "dialect_hint": "maghrebi"})
        body = resp.json()
        assert body["foreign"] is True
        assert body["root"] is None

    def test_auto_detect(self, client: TestClient) -> None:
        resp = client.post("/v1/normalize", json={"word": "كايكتب"})
        body = resp.json()
        assert body["dialect"] == "maghrebi"
        assert body["root"] == "كتب"

    def test_invalid_hint_rejected(self, client: TestClient) -> None:
        resp = client.post("/v1/normalize", json={"word": "بيكتب", "dialect_hint": "klingon"})
        assert resp.status_code == 422

    def test_beta_note_present(self, client: TestClient) -> None:
        resp = client.post("/v1/normalize", json={"word": "بيكتب"})
        assert "UNVERIFIED" in resp.json()["note"]


class TestReaderEndpoints:
    def test_build_then_lookup(self, client: TestClient, reader_db: str) -> None:
        build = client.post("/v1/reader/build", json={"ref_id": "1:1", "text": "العلم نور"})
        assert build.status_code == 200
        assert build.json()["words"] == 2
        assert build.json()["beta"] is True

        lookup = client.get("/v1/reader/lookup", params={"ref": "1:1", "word": 0})
        assert lookup.status_code == 200
        body = lookup.json()
        assert body["annotation"] is not None
        assert body["annotation"]["surface"] == "العلم"
        assert body["annotation"]["word_index"] == 0
        # No sense inventory wired: senses must stay pending, never guessed.
        assert body["annotation"]["sense_id"] is None
        assert body["annotation"]["sense_pending"] is True
        assert "scholar-eval pending" in body["note"]

    def test_lookup_missing_returns_null(self, client: TestClient, reader_db: str) -> None:
        resp = client.get("/v1/reader/lookup", params={"ref": "9:9", "word": 0})
        assert resp.status_code == 200
        assert resp.json()["annotation"] is None

    def test_build_rejects_oversize(self, client: TestClient, reader_db: str) -> None:
        big_text = " ".join(["العلم"] * 5001)
        resp = client.post("/v1/reader/build", json={"ref_id": "x", "text": big_text})
        assert resp.status_code == 413
