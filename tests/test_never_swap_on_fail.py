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
    for c2, old, new, rs, deadline, same, changed, trips, prices, dropped, label in itertools.product(
        C2,
        MARKET,
        NEW,
        RATIO,
        [False, True],
        [False, True],
        [False, True],
        [[], ["guard"]],
        PRICES,
        [[], ["new_contract"]],
        [False, True],
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
                c3_dropped=dropped,
                swap_label_only=label,
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
            assert not f.c3_dropped, f  # a2a r03: a contract the notice does not quote never reaches SWAP
            assert not f.swap_label_only, f  # a2a r04: the Reader's label alone never reaches SWAP
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
    # old 4.8 % above the swap: under R8's 5 % margin, so SWAP, and the reason says why it is not SELL OLD
    near = decide(
        Facts(**base, old_market="alive", ratio_state="P", ratio_route="event-date", old_price=1.048)
    )
    assert near.rule_id == "R9" and "4.8% above the swap, under the 5% R8 needs for SELL OLD" in near.reason
    # just under the margin the figure is cut, never rounded up to the 5 % it is under (a2a r12: 1.0499 printed
    # "5.0% above the swap, under the 5% R8 needs"); at the margin itself the verdict is R8
    edge = decide(
        Facts(**base, old_market="alive", ratio_state="P", ratio_route="event-date", old_price=1.0499)
    )
    assert edge.rule_id == "R9" and "4.99% above the swap, under the 5% R8 needs for SELL OLD" in edge.reason
    hair = decide(
        Facts(**base, old_market="alive", ratio_state="P", ratio_route="event-date", old_price=1.0003)
    )
    assert hair.rule_id == "R9" and "less than 0.1% above the swap, under the 5% R8 needs" in hair.reason
    assert decide(Facts(**base, old_market="alive", ratio_state="P", old_price=1.05)).rule_id == "R8"
    # an unbound ratio's R10 reason is one sentence (a2a r12: it read "ratio ratio quoted without a direction ...")
    why = "ratio quoted without a direction (which side is old?)"
    unbound = decide(Facts(**base, old_market="alive", ratio_state="none", ratio_reason=why, old_price=1.0))
    assert (unbound.rule_id, unbound.reason) == ("R10", why)
    loose = decide(Facts(**base, old_market="alive", ratio_state="none", ratio_reason="stated but not bound"))
    assert loose.reason == "ratio stated but not bound"
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


def test_a2a_r03_dropped_contract_or_ratio_quote_blocks_swap():
    base = dict(
        c2="verified",
        old_market="alive",
        new_market="alive",
        ratio_state="P",
        ratio_route="market-now",
        ratio=1.0,
        old_price=1.0,
        new_price=1.0,
    )
    assert decide(Facts(**base)).verdict == "SWAP"
    for name in ("new_contract", "old_contract", "ratio_new_per_old", "successor_symbol"):
        d = decide(Facts(**base, c3_dropped=[name]))
        assert d.verdict == "NOT_VERIFIABLE" and d.rule_id == "R10" and name in d.reason
    assert decide(Facts(**base, c3_dropped=["effective_date"])).verdict == "SWAP"


def test_a2a_r03_tiny_ratio_binding_is_relative():
    from successor.verify.quotes import bind_ratio

    q = "1 OLD = 0.000000001 NEW"
    assert bind_ratio(q, 0.000001, ["OLD"], ["NEW"]).state == "unbound"
    b = bind_ratio(q, 0.000000001, ["OLD"], ["NEW"])
    assert b.state == "bound" and b.parsed == 1e-9
