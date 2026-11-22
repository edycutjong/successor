"""Properties of the verdict rules over every combination of check states (exhaustive, not sampled)."""

import itertools

from successor.verify.verdict import Facts, decide

C2 = ["verified", "refuted", "unresolved", "not_run"]
MARKET = ["alive", "dead", "unknown"]
NEW = ["alive", "dead", None]
RATIO = ["P", "Q", "none"]
ROUTE = {"P": ["event-date", "continuity", "market-now"], "Q": ["stated"], "none": [None]}
PRICES = [(1.0, 1.0), (1.2, 1.0), (0.8, 1.0)]  # parity, old premium 20%, old discount 20% (ratio 1)


def all_facts():
    for c2, old, new, rs, deadline, same, changed, trips, prices in itertools.product(
        C2, MARKET, NEW, RATIO, [False, True], [False, True], [False, True], [[], ["guard"]], PRICES
    ):
        for route in ROUTE[rs]:
            yield Facts(
                sanity_trips=trips,
                same_id=same,
                contract_changed=changed,
                c2=c2,
                old_market=old,
                new_market=new,
                ratio_state=rs,
                ratio_route=route,
                ratio=1.0,
                old_price=prices[0] if old == "alive" else None,
                new_price=prices[1] if new == "alive" else None,
                deadline_quoted=deadline,
                deadline_passed=deadline,
                deadline_text="2025-01-01" if deadline else None,
            )


def test_properties_hold_for_every_combination():
    n = 0
    for f in all_facts():
        d = decide(f)
        n += 1
        if d.verdict == "SWAP":
            assert f.c2 == "verified" and f.ratio_state == "P", f
            assert not f.deadline_passed, f
            assert not (f.old_market == "alive" and f.old_price < 0.95 * f.ratio * f.new_price), f
            assert not f.sanity_trips
        if d.verdict == "SELL_OLD":
            assert f.old_market == "alive", f
        if d.verdict == "WRITE_OFF":
            assert f.old_market == "dead", f
        if f.sanity_trips:
            assert (d.verdict, d.rule_id) == ("NOT_VERIFIABLE", "R3")
        if f.c2 == "refuted" and not f.sanity_trips:
            assert d.verdict in ("NOT_VERIFIABLE", "NOTHING_TO_DO") or d.rule_id == "R5"
    assert n > 5000


def test_a2a_counterexample_old_discount_with_price_confirmed_ratio_is_not_swap():
    f = Facts(
        c2="verified",
        old_market="alive",
        new_market="alive",
        ratio_state="P",
        ratio_route="market-now",
        ratio=1.0,
        old_price=0.90,
        new_price=1.0,
    )
    d = decide(f)
    assert d.verdict == "NOT_VERIFIABLE" and "below the swap value" in d.reason


def test_a2a_counterexample_passed_deadline_on_merged_page_is_not_swap():
    f = Facts(
        c2="verified",
        same_id=True,
        contract_changed=True,
        old_market="unknown",
        new_market="alive",
        ratio_state="P",
        ratio_route="continuity",
        ratio=1.0,
        new_price=1.0,
        deadline_quoted=True,
        deadline_passed=True,
        deadline_text="2025-01-01",
    )
    assert decide(f).verdict != "SWAP"


def test_rule_order_examples():
    base = dict(c2="verified", new_market="alive", ratio=1.0, new_price=1.0)
    assert decide(Facts(**base, old_market="alive", ratio_state="Q", old_price=1.155)).rule_id == "R8"
    assert decide(Facts(**base, old_market="dead", ratio_state="P", ratio_route="event-date")).rule_id == "R9"
    assert decide(Facts(c2="verified", old_market="dead", new_market="dead")).rule_id == "R6"
    assert decide(Facts(c2="verified", same_id=True)).rule_id == "R4"
    assert decide(Facts(c2="refuted", c2_reason="x")).rule_id == "R5"
    assert (
        decide(
            Facts(
                **base,
                old_market="alive",
                old_price=1.0,
                deadline_quoted=True,
                deadline_passed=True,
                deadline_text="2025-01-01",
            )
        ).rule_id
        == "R7"
    )
    # Q alone never gives SWAP, even at parity
    assert (
        decide(Facts(**base, old_market="alive", ratio_state="Q", old_price=1.0)).verdict == "NOT_VERIFIABLE"
    )
    # a passed quoted deadline beats a price-confirmed ratio when the old token has no market
    d = decide(
        Facts(
            **base,
            old_market="dead",
            ratio_state="P",
            ratio_route="event-date",
            deadline_quoted=True,
            deadline_passed=True,
            deadline_text="2025-01-01",
        )
    )
    assert d.rule_id == "R6"
    # old alive with a dead successor: no swap value to compare
    d = decide(
        Facts(c2="verified", old_market="alive", new_market="dead", ratio_state="Q", ratio=1.0, old_price=2.0)
    )
    assert d.rule_id == "R10" and "no live market" in d.reason
