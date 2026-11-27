import json
from datetime import date
from pathlib import Path

from successor.verify import market as mk
from successor.verify import ratio as rt

SPIKE = Path(__file__).resolve().parents[1] / "docs" / "proof" / "spike"


def _closes(prices, vols=None, start=1):
    vols = vols or [1.0] * len(prices)
    return [
        {"date": f"2026-01-{start + i:02d}", "price": p, "volume_24h": v}
        for i, (p, v) in enumerate(zip(prices, vols, strict=True))
    ]


def test_event_date_check_needs_volume_on_both_legs():
    old = _closes([1.0, 1.0, 1.0], [5, 0, 5])
    new = _closes([1.0, 1.0, 1.0])
    ok, msg = rt.event_date_check(1.0, old, new, date(2026, 1, 2))
    assert ok and "2026-01-02" not in msg.split(":")[0]  # day 2 skipped: old volume 0
    ok, _ = rt.event_date_check(1.0, _closes([1.0] * 3, [0, 0, 0]), new, date(2026, 1, 2))
    assert not ok


def test_zero_volume_successor_leg_never_confirms():
    old = _closes([1.0] * 3)
    new = _closes([1.0] * 3, [0, 0, 0])
    assert rt.event_date_check(1.0, old, new, date(2026, 1, 2))[0] is False


def test_continuity_only_confirms_a_stated_one_to_one():
    smooth = _closes([1.0, 1.01, 1.0, 1.02, 1.01])
    assert rt.continuity_check(1.0, smooth, date(2026, 1, 3))[0] is True
    assert rt.continuity_check(100.0, smooth, date(2026, 1, 3))[0] is False  # 1:100 on a smooth series
    jump = _closes([1.0, 1.0, 1.2, 1.2, 1.2])
    assert rt.continuity_check(1.0, jump, date(2026, 1, 3))[0] is False


def test_ratio_state_q_needs_both_contracts_and_market_now_needs_both_alive():
    e = rt.EventDate(None, "none")
    kw = dict(stated=1.0, bound=True, event_day=e, old_closes=[], new_closes=[], single_id=False)
    assert (
        rt.ratio_state(
            **kw, contracts_verified=True, old_alive=True, new_alive=True, old_price=1.155, new_price=1.0
        ).state
        == "Q"
    )
    assert (
        rt.ratio_state(
            **kw, contracts_verified=False, old_alive=True, new_alive=True, old_price=1.155, new_price=1.0
        ).state
        == "none"
    )
    r = rt.ratio_state(
        **kw, contracts_verified=False, old_alive=True, new_alive=True, old_price=1.02, new_price=1.0
    )
    assert (r.state, r.route) == ("P", "market-now")
    # no quoted ratio: parity is an observation only, never P or Q
    r = rt.ratio_state(
        **{**kw, "stated": None},
        contracts_verified=True,
        old_alive=True,
        new_alive=True,
        old_price=1.0,
        new_price=1.0,
    )
    assert r.state == "none" and "consistent with 1:1" in r.observations[0]


def test_event_date_sources():
    notice = "see https://x.com/ClearpoolFin/status/2122523453270180117"
    assert rt.pick_event_date(None, None, notice, "2021-10-10", "2021-10-10").day == date(2026, 11, 17)
    assert (
        rt.pick_event_date(date(2024, 7, 1), "announcement", notice, None, None).source
        == "quoted (announcement)"
    )
    # CMC copies date_added old -> new on a rename: equal dates never date the event
    assert rt.pick_event_date(None, None, "", "2021-10-10T00:00:00Z", "2021-10-10T00:00:00Z").day is None
    assert rt.pick_event_date(None, None, "", "2019-01-01", "2024-09-18").day == date(2024, 9, 18)


def test_market_from_recorded_rows():
    q = json.loads((SPIKE / "03-quotes-latest.json").read_text())["response"]["data"]
    cpool_pairs = json.loads((SPIKE / "05-market-pairs-cpool.json").read_text())["response"]["data"]
    agix_pairs = json.loads((SPIKE / "05-market-pairs-agix.json").read_text())["response"]["data"]
    alive = mk.assess(q["12573"], cpool_pairs, [])
    assert alive.state == "alive" and alive.top_venue == "Upbit"
    dead = mk.assess(q["2424"], agix_pairs, [])
    assert dead.state == "dead" and "$0" in dead.reason
    assert mk.assess(q["12573"], None, [], pairs_denied=True).notes == ["spot pairs not checked: key plan"]


def test_flat_price_is_live_when_valid_pairs_trade_it_and_dead_without_a_pair_check():
    # a2a r03: a traded peg must never read as a dead market (R6 would write it off)
    flat = [{"date": f"d{i}", "price": 0.5, "volume_24h": 1} for i in range(30)]
    row = {"quote": {"USD": {"price": 0.5, "volume_24h": 100}}}
    pairs = {
        "market_pairs": [
            {
                "outlier_detected": 0,
                "exclusions": None,
                "exchange": {"name": "X"},
                "quote": {"USD": {"volume_24h": 50}},
            }
        ]
    }
    m = mk.assess(row, pairs, flat)
    assert m.state == "alive" and any("peg" in n for n in m.notes)
    assert mk.assess(row, None, flat, pairs_denied=True).state == "dead"
    assert mk.is_flat(flat[:10]) is None


def test_missing_price_or_volume_is_unknown_not_dead():
    pairs = {"market_pairs": [{"outlier_detected": 0, "exclusions": None, "exchange": {"name": "X"}}]}
    assert mk.assess({"quote": {"USD": {"price": 0.5}}}, pairs, []).state == "unknown"
    assert mk.assess({"quote": {"USD": {"volume_24h": 10}}}, pairs, []).state == "unknown"
    assert (
        mk.assess({"quote": {"USD": {"price": float("nan"), "volume_24h": 10}}}, pairs, []).state == "unknown"
    )
    quiet = mk.assess({"quote": {"USD": {"price": 0.5, "volume_24h": 0}}}, pairs, [])
    assert quiet.state == "dead" and quiet.pairs_note() == ""
    # a2a r13: CMC's quote can report $0 of 24 h volume while market-pairs still lists counted pairs with volume
    # (RZUSD, 2026-11-27 19:05 UTC). The price is stale either way, so the state stays dead, and the reason says what
    # both endpoints show instead of "no market"
    listed = {
        "market_pairs": [
            {
                "outlier_detected": 0,
                "exclusions": None,
                "exchange": {"name": n},
                "quote": {"USD": {"volume_24h": v}},
            }
            for n, v in (("A", 877.33), ("B", 606.48), ("C", 586.14), ("D", 278.26), ("E", 40.25), ("F", 0))
        ]
    }
    split = mk.assess({"quote": {"USD": {"price": 0.2135, "volume_24h": 0}}}, listed, [])
    assert (split.state, split.traded_pairs, round(split.traded_volume_24h, 2)) == ("dead", 5, 2388.46)
    assert split.pairs_note() == (
        "market-pairs still lists 5 pairs with $2,388 of 24 h volume between them, none flagged as an outlier or "
        "excluded, which the quote does not include"
    )

    def one(volume: float) -> str:
        only = {
            "market_pairs": [
                {"outlier_detected": 0, "exclusions": None, "quote": {"USD": {"volume_24h": volume}}}
            ]
        }
        return mk.assess({"quote": {"USD": {"price": 0.5, "volume_24h": 0}}}, only, []).pairs_note()

    assert one(49.2).startswith(
        "market-pairs still lists 1 pair with $49.20 of 24 h volume on it, not flagged"
    )
    assert "with less than $0.01 of" in one(0.004) and "with $100 of" in one(
        99.996
    )  # never "$0.00" or "$100.00"
    # a pair CMC itself excludes is not listed volume (REP's Indodax pair, 2026-11-22)
    flagged = {
        "market_pairs": [{"exclusions": ["price", "volume"], "quote": {"USD": {"volume_24h": 195.02}}}]
    }
    assert mk.assess({"quote": {"USD": {"price": 0.5, "volume_24h": 0}}}, flagged, []).pairs_note() == ""
    assert split.reason == "24 h volume is $0 on CMC's quote, so its price is stale; " + split.pairs_note()
    assert (
        mk.assess({"quote": {"USD": {"price": 0.2135, "volume_24h": 917.0}}}, listed, []).pairs_note() == ""
    )
