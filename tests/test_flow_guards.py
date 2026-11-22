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
