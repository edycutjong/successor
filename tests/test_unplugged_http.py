"""Unplug the keys at the HTTP layer: /api/lookup must answer an error, never a canned verdict."""

import pytest
from fastapi.testclient import TestClient

from api.index import app
from successor.agent import reader as rd


@pytest.fixture
def unplugged(monkeypatch):
    monkeypatch.delenv("CMC_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setattr("successor.cmc.LOCAL_KEY_FILE", rd.Path("/nonexistent"))
    monkeypatch.setattr(rd, "LOCAL_ENV_FILE", rd.Path("/nonexistent"))


def test_lookup_without_keys_is_an_error_not_a_verdict(unplugged):
    r = TestClient(app).get("/api/lookup", params={"q": "CPOOL"}, headers={"Accept": "application/json"})
    body = r.json()
    assert r.status_code >= 400
    assert body["type"] == "error" and "verdict" not in body


def test_streamed_lookup_without_keys_never_emits_a_verdict(unplugged):
    r = TestClient(app).get("/api/lookup", params={"q": "CPOOL"})
    assert '"type": "verdict"' not in r.text
