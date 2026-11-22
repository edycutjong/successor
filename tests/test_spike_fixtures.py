"""Tests over the verbatim responses the day-one spike saved (docs/proof/spike/)."""

import json
from datetime import date
from pathlib import Path

from successor.agent.reader import Proposal, quotes_are_verbatim
from successor.flow import provisional_outcome
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
