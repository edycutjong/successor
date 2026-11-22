from datetime import UTC, datetime

from successor.cmc import CmcResponse
from successor.flow import _assess, dropped_contracts
from successor.verify import sanity
from successor.verify.quotes import check_quotes


def _c3(**fields):
    prop = {k: {"value": v, "evidence_quote": v, "source": "notice"} for k, v in fields.items()}
    return check_quotes(prop, {"notice": " ".join(fields.values())})


def test_repair_resubmit_that_drops_a_quoted_contract_is_caught():
    p1 = _c3(old_contract="0xabc0000000000000000000000000000000000001", successor_symbol="NOPE")
    p2 = _c3(successor_symbol="FET")
    assert dropped_contracts(p1, p2) == ["old_contract"]
    p3 = _c3(old_contract="0xABC0000000000000000000000000000000000001", successor_symbol="FET")
    assert dropped_contracts(p1, p3) == [] and dropped_contracts(None, p2) == []


def _resp(status, body):
    return CmcResponse("/v2/cryptocurrency/market-pairs/latest", {}, status, body, 1, "t")


def test_pairs_outage_is_unknown_not_a_plan_fallback():
    row = {"quote": {"USD": {"price": 1.0, "volume_24h": 10}}}
    assert _assess(_resp(500, {"status": {"error_code": 500}}), row, []).state == "unknown"
    denied = _assess(_resp(403, {"status": {"error_code": 1006}}), row, [])
    assert denied.state == "alive" and denied.notes == ["spot pairs not checked: key plan"]


def test_missing_quote_row_trips_the_guard():
    now = datetime(2026, 11, 22, tzinfo=UTC)
    trips = sanity.check(legs=[{"label": "X", "requested_id": 1, "returned_id": None}], ratio=1, now=now)
    assert trips and "no quote row" in trips[0]
    stale = sanity.check(
        legs=[
            {
                "label": "X",
                "requested_id": 1,
                "returned_id": 1,
                "is_active": 1,
                "price": 1,
                "volume_24h": 1,
                "last_updated": "2026-11-19T00:00:00Z",
            }
        ],
        ratio=1e10,
        now=now,
    )
    assert len(stale) == 2


# --- a2a r03: lookup deadline, terminal event, credit probe ------------------------------------------------
def test_cmc_call_past_the_lookup_deadline_raises_before_any_request():
    import asyncio
    import time

    import httpx
    import pytest

    from successor.cmc import CmcClient

    c = CmcClient(key="k", deadline=time.monotonic() - 1)
    with pytest.raises(httpx.TimeoutException, match="deadline"):
        asyncio.run(c.get("/v1/key/info"))
    assert c._retry_fits(1.0) is False and CmcClient(key="k")._retry_fits(1e9) is True


def test_unexpected_exception_still_ends_the_stream_with_an_error_event():
    import asyncio

    from successor.cmc import CmcClient
    from successor.flow import lookup_stream

    class Boom(CmcClient):
        async def get(self, path, params=None, *, strict=False):
            raise KeyError("data")

    async def run():
        return [e async for e in lookup_stream("CPOOL", cmc=Boom(key="k"), guard_credits=False)]

    evs = asyncio.run(run())
    assert evs[-1]["type"] == "error" and evs[-1]["step"] == "internal" and "KeyError" in evs[-1]["error"]


def test_unknown_credit_balance_is_not_cached():
    import asyncio

    from successor import flow
    from successor.cmc import CmcClient

    class NoUsage(CmcClient):
        n = 0

        async def get(self, path, params=None, *, strict=False):
            NoUsage.n += 1
            self.calls.append(CmcResponse(path, {}, 500, {}, 0, "t"))
            return self.calls[-1]

    flow._credit_cache.clear()
    c = NoUsage(key="k")
    assert asyncio.run(flow._credits_ok(c)) == (True, None)
    asyncio.run(flow._credits_ok(c))
    assert NoUsage.n == 2 and "v" not in flow._credit_cache and c.calls == []


def test_naive_timestamp_does_not_crash_the_sanity_guard():
    now = datetime(2026, 11, 22, tzinfo=UTC)
    leg = {
        "label": "old",
        "requested_id": 1,
        "returned_id": 1,
        "is_active": 1,
        "price": 1.0,
        "volume_24h": 5,
        "last_updated": "2026-11-01T00:00:00",
    }
    assert any("48 h" in t for t in sanity.check(legs=[leg], ratio=None, now=now))


# --- a2a r04 ----------------------------------------------------------------------------------------------
def test_successor_name_must_appear_in_its_quote():
    from successor.verify.quotes import _value_in_quote

    assert _value_in_quote("successor_name", "Alpha", "migrates to Alpha (NEW) at 1:1")
    assert not _value_in_quote("successor_name", "Beta", "migrates to Alpha (NEW) at 1:1")


def test_continuity_needs_closes_on_both_sides_of_the_event_with_volume():
    from datetime import date as d

    from successor.verify.ratio import continuity_check

    day = d(2026, 11, 10)

    def closes(offsets, vol=5.0):
        return [
            {"date": str(d.fromordinal(day.toordinal() + o)), "price": 1.0, "volume_24h": vol}
            for o in offsets
        ]

    assert continuity_check(1, closes([-2, -1, 0, 1, 2]), day)[0] is True
    assert continuity_check(1, closes([0, 1, 2]), day)[0] is False  # nothing before the event
    assert continuity_check(1, closes([-2, -1, 0]), day)[0] is False  # nothing after it
    assert continuity_check(1, closes([-2, -1, 0, 1, 2], vol=0), day)[0] is False  # flat print, no trades


def test_priced_active_quote_needs_a_readable_present_timestamp():
    now = datetime(2026, 11, 22, tzinfo=UTC)
    base = {
        "label": "new",
        "requested_id": 2,
        "returned_id": 2,
        "is_active": 1,
        "price": 1.0,
        "volume_24h": 9,
    }
    for bad in (None, "bad", "2099-01-01T00:00:00Z"):
        assert sanity.check(legs=[{**base, "last_updated": bad}], ratio=None, now=now), bad
    assert sanity.check(legs=[{**base, "last_updated": "2026-11-21T23:00:00Z"}], ratio=None, now=now) == []


def test_label_only_swap_never_reaches_swap():
    from successor.verify.verdict import Facts, decide

    f = Facts(
        c2="verified",
        same_id=True,
        contract_changed=True,
        swap_label_only=True,
        old_market="unknown",
        new_market="alive",
        ratio_state="P",
        ratio_route="continuity",
        ratio=1.0,
        new_price=1.0,
    )
    d = decide(f)
    assert d.verdict == "NOT_VERIFIABLE" and "labelled this a swap" in d.reason
    assert decide(Facts(**{**f.__dict__, "swap_label_only": False})).verdict == "SWAP"


def test_malformed_tool_calls_end_as_reader_error_not_keyerror():
    import asyncio

    import pytest

    from successor.agent import reader as rd

    async def chat(_cfg, _body, _timeout):
        msg = {"role": "assistant", "tool_calls": [{"type": "function"}, "junk"]}
        return 200, {"choices": [{"message": msg}]}, 5

    s = rd.ReaderSession("notice text", "OLD", lambda *a: None, chat=chat, budget_s=5)
    with pytest.raises(rd.ReaderError):
        asyncio.run(s.propose())


def test_misshaped_cache_entry_is_a_miss(tmp_path, monkeypatch):
    from successor.agent import reader as rd

    monkeypatch.setattr(rd, "REPO_CACHE", tmp_path)
    monkeypatch.setattr(rd, "TMP_CACHE", tmp_path / "none")
    f = tmp_path / f"{rd.cache_key(1, 'n')}.json"
    for body in ("[]", '{"proposals": {}}', '{"x": 1}', "not json"):
        f.write_text(body)
        assert rd.load_cached(1, "n") is None
    f.write_text('{"proposals": [{"proposal": {}}]}')
    assert rd.load_cached(1, "n") is not None


def test_hard_deadline_cancels_a_hung_await_and_ends_with_an_error_event():
    import asyncio
    import time

    from successor import flow
    from successor.cmc import CmcClient

    class Hang(CmcClient):
        async def get(self, path, params=None, *, strict=False):
            await asyncio.sleep(30)

    async def run(monkey_budget):
        c = Hang(key="k")
        c.deadline = time.monotonic() + monkey_budget
        old = flow.DEADLINE_GRACE_S
        flow.DEADLINE_GRACE_S = 0.0
        try:
            return [e async for e in flow.lookup_stream("CPOOL", cmc=c, guard_credits=False)]
        finally:
            flow.DEADLINE_GRACE_S = old

    t0 = time.monotonic()
    evs = asyncio.run(run(0.3))
    assert time.monotonic() - t0 < 5 and evs[-1]["step"] == "deadline" and evs[-1]["http_status"] == 504


# --- P1d loop QA round 2 ----------------------------------------------------------------------------------
def test_label_only_swap_through_the_real_flow_ends_r10():
    """Production path: ONE (ticker change on one CMC id, recorded CMC rows) replayed with the Reader's label
    switched to token_swap. No swap wording in the notice, so the label alone must not reach SWAP or R4."""
    import asyncio
    import copy
    import json
    from pathlib import Path

    from successor.evals import replay

    fx = json.loads((Path(__file__).parent / "fixtures/cases/one.json").read_text())
    base = asyncio.run(replay(fx))[-1]
    assert (base["verdict"], base["rule_id"]) == ("NOTHING_TO_DO", "R4")
    fx2 = copy.deepcopy(fx)
    fx2["extraction"]["proposals"][-1]["event_type"] = "token_swap"
    final = asyncio.run(replay(fx2))[-1]
    assert (final["verdict"], final["rule_id"]) == ("NOT_VERIFIABLE", "R10"), final
    assert "labelled this a swap" in final["reason"]


def test_timeout_retry_is_skipped_when_it_would_not_fit_the_deadline():
    import asyncio
    import time

    import httpx
    import pytest

    from successor.cmc import BASE_URL, CmcClient

    seen = []

    def handler(request):
        seen.append(request.url.path)
        raise httpx.ReadTimeout("slow", request=request)

    async def run(left):
        c = CmcClient(key="k", deadline=time.monotonic() + left)
        c._client = httpx.AsyncClient(base_url=BASE_URL, transport=httpx.MockTransport(handler))
        try:
            await c.get("/v1/key/info")
        finally:
            await c._client.aclose()

    with pytest.raises(httpx.TimeoutException):
        asyncio.run(run(3.5))  # per_try 2.5 s; a retry needs > 4.5 s left -> exactly one request
    assert len(seen) == 1
    seen.clear()
    with pytest.raises(httpx.TimeoutException):
        asyncio.run(run(60))  # room for the retry -> two requests
    assert len(seen) == 2


def test_census_buckets_cover_the_new_r10_reasons():
    from successor.census import reason_group

    assert "swap" in reason_group(
        "the Reader labelled this a swap, but the notice has no swap wording, contract change or ratio"
    )
    assert "does not contain" in reason_group(
        "C3 dropped new_contract: the Reader proposed it without a verbatim quote"
    )
    assert "no price or volume" in reason_group(
        "CMC returned no price or volume for the successor; no swap value"
    )


def test_flat_price_needs_a_pair_with_its_own_volume():
    from successor.verify import market as mk

    flat = [{"date": f"d{i}", "price": 0.5, "volume_24h": 1} for i in range(30)]
    row = {"quote": {"USD": {"price": 0.5, "volume_24h": 100}}}
    leftover = {
        "market_pairs": [{"outlier_detected": 0, "exclusions": None, "quote": {"USD": {"volume_24h": 0}}}]
    }
    assert mk.assess(row, leftover, flat).state == "dead"
