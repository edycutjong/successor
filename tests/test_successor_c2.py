import json
from pathlib import Path

from successor.verify.successor import check_successor

SPIKE = Path(__file__).resolve().parents[1] / "docs" / "proof" / "spike"
INFO = json.loads((SPIKE / "01-info.json").read_text())["response"]["data"]
CLEAR = {"id": 42884, "symbol": "CLEAR", "name": "Clearpool", "slug": "clearpool-finance", "is_active": 1}
EVERCLEAR = {"id": 34512, "symbol": "CLEAR", "name": "Everclear", "slug": "everclear", "is_active": 0}
FET = {
    "id": 3773,
    "symbol": "FET",
    "name": "Artificial Superintelligence Alliance",
    "slug": "artificial-superintelligence-alliance",
    "is_active": 1,
}
NOTICE = INFO["12573"]["notice"]


def _c2(**kw):
    base = dict(
        symbol="CLEAR",
        name="Clearpool",
        new_contract=None,
        new_chain=None,
        notice=NOTICE,
        candidates=[CLEAR, EVERCLEAR],
        infos={"42884": INFO["42884"], "34512": {}},
    )
    return check_successor(**{**base, **kw})


def test_contract_match_verifies_even_with_a_symbol_collision():
    r = _c2(new_contract="0x5200F539478F58D9AEA962095BA3B16B5E550E00", new_chain="Ethereum")
    assert (r.state, r.match, r.successor["id"]) == ("verified", "contract", 42884)


def test_one_hex_digit_off_is_refuted_and_never_repairable():
    r = _c2(new_contract="0x5200f539478f58d9aea962095ba3b16b5e550e01")
    assert r.state == "refuted" and not r.repairable and "≠ CMC's contract" in r.reason


def test_contract_on_the_wrong_named_chain_is_refuted():
    r = _c2(new_contract="0x5200f539478f58d9aea962095ba3b16b5e550e00", new_chain="Solana")
    assert r.state == "refuted"


def test_collision_without_contract_is_unresolved_and_repairable():
    r = _c2(symbol="CLEAR", name=None, notice="renamed to CLEAR")
    assert r.state == "unresolved" and r.repairable


def test_named_successor_with_no_cmc_id_is_refuted_and_repairable_once():
    r = _c2(symbol="NOPE", name="Nope", candidates=[])
    assert r.state == "refuted" and r.match == "no-id" and r.repairable


def test_notice_link_resolved_by_cmc_id_verifies_identity():
    """AGIX's notice links coinmarketcap.com/currencies/fetch/; CMC returns id 3773 (FET) for that old slug."""
    r = check_successor(
        symbol="ASI",
        name="Artificial Superintelligence Alliance",
        new_contract=None,
        new_chain=None,
        notice=INFO["2424"]["notice"],
        candidates=[FET, {"id": 8876, "symbol": "ASI", "name": "ASI finance", "slug": "asi"}],
        infos={"3773": INFO["3773"]},
        linked_ids={3773},
    )
    assert (r.state, r.successor["id"]) == ("verified", 3773) and r.match.startswith("identity")


def test_unique_exact_name_and_symbol():
    r = _c2(notice="renamed", candidates=[CLEAR, EVERCLEAR])
    assert r.state == "verified" and r.match == "identity: unique name + symbol"
