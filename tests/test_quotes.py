from successor.verify.quotes import bind_ratio, check_quotes, parse_iso_date


def _f(value, quote, source="notice"):
    return {"value": value, "evidence_quote": quote, "source": source}


NOTICE = "Clearpool (CPOOL) has rebranded to Clearpool (CLEAR) and undergone a 1:1  swap."


def test_c3_keeps_verbatim_quotes_whitespace_normalised_and_drops_the_rest():
    prop = {
        "successor_symbol": _f("CLEAR", "rebranded to Clearpool (CLEAR)"),
        "ratio_new_per_old": _f(1, "undergone a 1:1 swap"),  # double space in the source
        "new_contract": _f("0xabc", "new contract 0xabc"),  # not in the text
        "deadline": _f(None, None),
    }
    r = check_quotes(prop, {"notice": NOTICE, "announcement": ""})
    assert set(r.kept) == {"successor_symbol", "ratio_new_per_old"}
    assert "new_contract" in r.dropped and "new_contract" in r.unstated and "deadline" in r.unstated


def test_c3_drops_a_true_quote_carrying_a_false_value():
    prop = {"successor_symbol": _f("CPOOL2", "rebranded to Clearpool (CLEAR)")}
    r = check_quotes(prop, {"notice": NOTICE})
    assert "successor_symbol" in r.dropped


def test_c3_announcement_quote_must_be_in_the_fetched_page_not_the_notice():
    prop = {"ratio_new_per_old": _f(0.43335, "1 $AGIX to 0.433350 $ASI", "announcement")}
    assert "ratio_new_per_old" in check_quotes(prop, {"notice": NOTICE, "announcement": ""}).dropped
    page = "tokens migrate to $ASI, at a conversion rate of 1 $AGIX to 0.433350 $ASI"
    assert "ratio_new_per_old" in check_quotes(prop, {"notice": NOTICE, "announcement": page}).kept


def test_c3b_binding():
    assert bind_ratio("undergone a 1:1 swap", 1, ["CPOOL"], ["CLEAR"]).state == "bound"
    assert bind_ratio("1 $AGIX to 0.433350 $ASI", 0.43335, ["AGIX"], ["ASI", "FET"]).state == "bound"
    # /a2a r02: "1 OLD converts into 5 NEW" proposed as 0.5 is unbound
    b = bind_ratio("1 OLD converts into 5 NEW", 0.5, ["OLD"], ["NEW"])
    assert b.state == "unbound" and b.parsed == 5
    assert bind_ratio("1 OLD converts into 5 NEW", 5, ["OLD"], ["NEW"]).state == "bound"
    assert bind_ratio("10 NEW for 1 OLD", 10, ["OLD"], ["NEW"]).state == "bound"
    assert bind_ratio("0.1 NEW per OLD", 0.1, ["OLD"], ["NEW"]).state == "bound"
    # a direction-less 1:1000 cannot be bound
    assert bind_ratio("a 1:1000 redenomination", 1000, ["OLD"], ["NEW"]).state == "unbound"
    assert bind_ratio("a 1:X swap", 1, ["OLD"], ["NEW"]).state == "unbound"
    assert bind_ratio(None, 1, ["OLD"], ["NEW"]).state == "unbound"


def test_iso_dates_only():
    assert str(parse_iso_date("2024-07-01")) == "2024-07-01"
    assert parse_iso_date("July 1, 2024") is None
    assert parse_iso_date("2024-13-01") is None
