"""The agent loop with a scripted model: tool routing, budgets, repairs. No network."""

import json

import pytest

from successor.agent import reader as rd


def _field(v=None, q=None, src="notice"):
    return {"value": v, "evidence_quote": q, "source": src}


def proposal(**over):
    base = {
        "event_type": "token_swap",
        **{n: _field() for n in rd.FIELD_NAMES},
        "links_to_follow": [],
        "unstated": [],
    }
    base.update(over)
    return base


def msg(*calls, content=None):
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}}
            for i, (n, a) in enumerate(calls)
        ]
        or None,
    }


def scripted(*messages):
    seen = []

    async def chat(cfg, body, timeout):
        seen.append(body)
        return 200, {"choices": [{"message": messages[len(seen) - 1]}], "usage": {}}, 5

    return chat, seen


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test")
    rd._daily.clear()


async def _fetch(url):
    return {
        "url": url,
        "final_url": url,
        "host": "fetch.ai",
        "text": "1 $AGIX to 0.433350 $ASI",
        "sha256": "x",
        "fetched_at": "2026-11-22T00:00:00Z",
        "latency_ms": 1,
    }


async def test_follow_link_then_submit_in_two_calls():
    chat, seen = scripted(
        msg(("follow_link", {"url": "https://fetch.ai/a"}), ("follow_link", {"url": "https://fetch.ai/b"})),
        msg(
            (
                "submit_proposal",
                proposal(ratio_new_per_old=_field(0.43335, "1 $AGIX to 0.433350 $ASI", "announcement")),
            )
        ),
    )
    s = rd.ReaderSession("notice https://fetch.ai/a https://fetch.ai/b", "AGIX", _fetch, chat=chat)
    p = await s.propose()
    assert p["ratio_new_per_old"]["value"] == 0.43335
    assert len(s.calls) == 2 and len(s.fetches) == 2
    assert "0.433350" in s.announcement_text


async def test_schema_invalid_gets_one_format_repair_then_fails():
    chat, _ = scripted(
        msg(("submit_proposal", {"event_type": "bogus"})), msg(("submit_proposal", {"event_type": "bogus"}))
    )
    s = rd.ReaderSession("n", "X", _fetch, chat=chat)
    with pytest.raises(rd.ReaderError, match="schema validation twice"):
        await s.propose()
    assert len(s.calls) == 2


async def test_array_of_one_object_is_unwrapped():
    chat, _ = scripted(msg(("submit_proposal", [proposal()])))
    s = rd.ReaderSession("n", "X", _fetch, chat=chat)
    assert (await s.propose())["event_type"] == "token_swap"


async def test_identity_repair_is_one_more_proposal_within_three_calls():
    chat, seen = scripted(
        msg(("submit_proposal", proposal(successor_symbol=_field("ASI", "the $ASI")))),
        msg(("submit_proposal", proposal(successor_symbol=_field("FET", "$FET")))),
    )
    s = rd.ReaderSession("n", "X", _fetch, chat=chat)
    await s.propose()
    p2 = await s.repair("ASI collides with 3 CMC ids")
    assert p2["successor_symbol"]["value"] == "FET" and len(s.proposals) == 2
    tool_msgs = [m for m in seen[1]["messages"] if m["role"] == "tool"]
    assert "could not verify the successor" in tool_msgs[-1]["content"]


async def test_three_call_budget_is_hard():
    chat, _ = scripted(*[msg(("follow_link", {"url": "https://fetch.ai/a"}))] * 4)
    s = rd.ReaderSession("https://fetch.ai/a", "X", _fetch, chat=chat)
    with pytest.raises(rd.ReaderError, match="3-call budget"):
        await s.propose()
    assert len(s.calls) == 3 and len(s.fetches) == 2  # link budget 2, third refused


async def test_daily_cap(monkeypatch):
    monkeypatch.setenv("LLM_DAILY_CAP", "0")
    chat, _ = scripted(msg(("submit_proposal", proposal())))
    with pytest.raises(rd.ReaderError, match="agent budget for today"):
        await rd.ReaderSession("n", "X", _fetch, chat=chat).propose()
