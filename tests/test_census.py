"""Census read side: counts are derived from data/census.json, never typed in; API routes serve them."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from successor import census as cn

DOC = {
    "captured_at": "2026-11-22T00:00:00Z",
    "scope": "top 2000 by cmc_rank, listing_status=active",
    "coins_scanned": 2000,
    "coins": [
        {"id": 1, "symbol": "AAA", "name": "A", "rank": 5, "notice": "x", "type": "migration", "prose_only": True,
         "names_contract": False, "names_ratio": False, "links": 1, "only_unfetchable_hosts": True,
         "verdict": "NOT_VERIFIABLE", "rule_id": "R10", "verdict_captured_at": "2026-11-22T01:00:00Z", "agent_needed": True},
        {"id": 2, "symbol": "BBB", "name": "B", "rank": 9, "notice": "y", "type": "migration", "prose_only": False,
         "names_contract": True, "names_ratio": True, "links": 2, "only_unfetchable_hosts": False,
         "verdict": "SWAP", "rule_id": "R9", "verdict_captured_at": "2026-11-22T02:00:00Z", "agent_needed": False},
        {"id": 3, "symbol": "CCC", "name": "C", "rank": 11, "notice": "z", "type": "other", "prose_only": False,
         "names_contract": False, "names_ratio": False, "links": 0, "only_unfetchable_hosts": False, "verdict": "ERROR"},
    ],
}  # fmt: skip


def test_summary_counts_come_from_the_rows() -> None:
    s = cn.summary(DOC)
    assert (s["notices"], s["migration_type"], s["other_type"]) == (3, 2, 1)
    assert s["prose_only"] == 1 and s["no_ratio_named"] == 1 and s["only_unfetchable_hosts"] == 1
    assert s["verdicts"]["NOT_VERIFIABLE"] == 1 and s["verdicts"]["SWAP"] == 1
    assert s["verdicts_total"] == 2 and s["verdicts_errors"] == 1  # ERROR rows are not counted as verdicts
    assert s["verdicts_captured"] == "2026-11-22T02:00:00Z"


def test_notices_list_omits_notice_text() -> None:
    rows = cn.notices(DOC)
    assert len(rows) == 3 and all("notice" not in r for r in rows)


def test_empty_census_is_valid(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(cn, "CENSUS_FILE", tmp_path / "none.json")
    assert cn.summary()["notices"] == 0


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> TestClient:
    f = tmp_path / "census.json"
    f.write_text(json.dumps(DOC))
    monkeypatch.setattr(cn, "CENSUS_FILE", f)
    from api.index import app

    return TestClient(app)


def test_api_census_and_notices(client: TestClient) -> None:
    c = client.get("/api/census").json()
    assert c["notices"] == 3 and c["captured_at"] == DOC["captured_at"]
    n = client.get("/api/notices").json()
    assert n["count"] == 3 and n["notices"][0]["symbol"] == "AAA"


def test_committed_census_has_a_verdict_for_every_notice() -> None:
    """After the pre-warm pass every census coin has a recorded verdict (no ERROR left)."""
    doc = cn.load()
    if not doc["coins"]:
        pytest.skip("no census committed yet")
    bad = [c["symbol"] for c in doc["coins"] if c.get("verdict") in (None, "ERROR")]
    assert not bad, f"unwarmed or errored: {bad[:10]}"


def test_reason_groups_and_zero_volume() -> None:
    doc = json.loads(json.dumps(DOC))
    doc["coins"][0]["reason"] = "merged CMC page: the old contract has no CMC id of its own"
    doc["coins"][0]["old_volume_24h_usd"] = 0
    doc["coins"][1]["old_volume_24h_usd"] = 1234.5
    s = cn.summary(doc)
    assert s["not_verifiable_reasons"] == {
        "old and new token share one CMC page; the ratio could not be confirmed": 1
    }
    assert (s["old_zero_volume"], s["market_checked"]) == (1, 2)
    assert cn.reason_group("successor not named in the notice") == "the notice names no successor"
    assert all("reason" in r for r in cn.notices(doc)[:1])


def test_fresh_rereads_are_rate_limited_per_client(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a2a r03: fresh=1 forces a paid Reader call; one client gets 3 per 10 min, cached reads stay open
    import api.index as idx

    async def fake(q, qty, cmc_id, fresh):
        yield {"type": "verdict", "verdict": "NOT_VERIFIABLE"}

    monkeypatch.setattr(idx, "lookup_stream", fake)
    idx._hits.clear()
    h = {"accept": "application/json", "x-forwarded-for": "203.0.113.7"}
    codes = [client.get("/api/lookup?q=CPOOL&fresh=1", headers=h).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    r = client.get("/api/lookup?q=CPOOL&fresh=1", headers=h)
    assert r.status_code == 429 and r.json()["step"] == "rate_limit" and int(r.headers["retry-after"]) > 0
    assert client.get("/api/lookup?q=CPOOL", headers=h).status_code == 200
    other = {**h, "x-forwarded-for": "198.51.100.9"}
    assert client.get("/api/lookup?q=CPOOL&fresh=1", headers=other).status_code == 200
    idx._hits.clear()
