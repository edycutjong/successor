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
