"""Unplug the keys: the demo path must fail, never fall back to canned output."""

from successor.agent import reader as rd
from successor.flow import lookup_stream


async def test_no_cmc_key_means_error_and_no_verdict(monkeypatch):
    monkeypatch.delenv("CMC_API_KEY", raising=False)
    monkeypatch.setattr("successor.cmc.LOCAL_KEY_FILE", rd.Path("/nonexistent"))
    events = [e async for e in lookup_stream("CPOOL", 1, guard_credits=False)]
    assert events[-1]["type"] == "error" and not any(e["type"] == "verdict" for e in events)


async def test_no_llm_key_on_a_cold_notice_is_not_verifiable(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setattr(rd, "LOCAL_ENV_FILE", rd.Path("/nonexistent"))
    s = rd.ReaderSession("n", "X", None)
    try:
        await s.propose()
        raise AssertionError("expected ReaderError")
    except rd.ReaderError as exc:
        assert "DASHSCOPE_API_KEY" in str(exc)
