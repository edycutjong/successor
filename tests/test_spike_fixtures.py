"""Tests over the verbatim responses the day-one spike saved (docs/proof/spike/)."""

import json
from datetime import date
from pathlib import Path

from successor.agent.reader import Proposal, quotes_are_verbatim
from successor.verify.successor import has_contract, linked_slugs
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


def test_old_and_new_contracts_belong_to_their_own_ids():
    data = json.loads((SPIKE / "01-info.json").read_text())["response"]["data"]
    old, new = data["12573"], data["42884"]
    assert has_contract(old, "0x66761FA41377003622AEE3C7675FC7B5C1C2FAC5")  # 0x hex compares case-insensitively
    assert has_contract(new, "0x5200f539478f58d9aea962095ba3b16b5e550e00", "Ethereum")
    assert not has_contract(new, "0x66761fa41377003622aee3c7675fc7b5c1c2fac5")
    assert not has_contract(new, "0x5200f539478f58d9aea962095ba3b16b5e550e00", "Solana")


def test_notice_slug_link_picks_the_successor():
    data = json.loads((SPIKE / "01-info.json").read_text())["response"]["data"]
    assert "sky" in linked_slugs(data["1518"]["notice"])
