"""Tests over the verbatim responses the day-one spike saved (docs/proof/spike/)."""

import json
from datetime import date
from pathlib import Path

from successor.agent.reader import Proposal, quotes_are_verbatim
from successor.flow import check_contracts, cmc_slugs_in, provisional_outcome
from successor.verify.ratio import announcement_dates, snowflake_date

SPIKE = Path(__file__).resolve().parents[1] / "docs" / "proof" / "spike"


def test_snowflake_dates_the_clear_announcement():
    assert snowflake_date(2122523453270180117) == date(2026, 11, 17)


def test_clear_date_added_is_inherited_from_cpool():
    data = json.loads((SPIKE / "01-info.json").read_text())["response"]["data"]
    assert data["42884"]["date_added"] == data["12573"]["date_added"]
    assert announcement_dates(data["42884"]["notice"]) == [date(2026, 11, 17)]


def test_saved_reader_proposal_is_schema_valid_and_quotes_verbatim():
    t = json.loads((SPIKE / "llm-clear.json").read_text())
    p = Proposal.model_validate(t["proposal"])
    checks = quotes_are_verbatim(p, t["notice"])
    assert checks and all(checks.values())
    assert p.ratio_new_per_old.value == 1


def test_contract_mismatch_is_never_swap():
    prop = {"ratio_new_per_old": 1}
    out = provisional_outcome(prop, {"price": 1, "volume_24h": 5}, {"price": 1}, contract_ok=False)
    assert out["verdict"] == "NOT VERIFIABLE"


def test_missing_ratio_is_not_verifiable():
    out = provisional_outcome({"ratio_new_per_old": None}, {"price": 1}, {"price": 1}, contract_ok=True)
    assert out["verdict"] == "NOT VERIFIABLE"


def test_no_quoted_contract_is_never_swap():
    out = provisional_outcome({"ratio_new_per_old": 1}, {"price": 1, "volume_24h": 5}, {"price": 1}, None)
    assert out["verdict"] == "NOT VERIFIABLE"


def test_quote_miss_is_never_swap():
    out = provisional_outcome({"ratio_new_per_old": 1}, {"price": 1}, {"price": 1}, True, quotes_ok=False)
    assert out["verdict"] == "NOT VERIFIABLE"


def test_old_address_quoted_as_new_contract_fails():
    old, new = {"0xold"}, {"0xnew"}
    assert check_contracts({"old_contract": "0xOLD", "new_contract": "0xnew"}, old, new) is True
    assert check_contracts({"new_contract": "0xold"}, old, new) is False
    assert check_contracts({}, old, new) is None


def test_notice_slug_link_picks_the_successor():
    data = json.loads((SPIKE / "01-info.json").read_text())["response"]["data"]
    assert "sky" in cmc_slugs_in(data["1518"]["notice"])
