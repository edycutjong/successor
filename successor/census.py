"""Read side of the notice census (`data/census.json`, written by scripts/census.py)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

CENSUS_FILE = Path(__file__).resolve().parents[1] / "data" / "census.json"
EXTRACTIONS = Path(__file__).resolve().parents[1] / "data" / "extractions"

HERO_ID = 12573  # CPOOL: the first-screen lookup (live verification, cached extraction)
HERO_Q = "CPOOL"

VERDICTS = ("SWAP", "SELL_OLD", "WRITE_OFF", "NOT_VERIFIABLE", "NOTHING_TO_DO")


def reason_group(reason: str) -> str:
    """Plain-language bucket for a recorded NOT_VERIFIABLE reason (the full reason stays in the row)."""
    r = (reason or "").lower()
    if "merged cmc page" in r:
        return "old and new token share one CMC page; the ratio could not be confirmed"
    if "successor not named" in r:
        return "the notice names no successor"
    if "refuted" in r:
        return "CMC's data refutes what the notice says"
    if "no live market" in r:
        return "the successor has no live market to compare"
    if "agent" in r:
        return "the agent did not finish in budget"
    if "ratio" in r:
        return "no swap ratio stated, or the linked announcement could not be fetched"
    return "other"


def load() -> dict[str, Any]:
    if not CENSUS_FILE.exists():
        return {"captured_at": None, "scope": None, "coins_scanned": 0, "coins": []}
    return json.loads(CENSUS_FILE.read_text())


def notices(doc: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The census list: one row per notice, no notice text (the lookup fetches it live)."""
    doc = doc or load()
    keep = (
        "id", "symbol", "name", "rank", "type", "prose_only", "names_contract", "names_ratio",
        "only_unfetchable_hosts", "featured", "verdict", "rule_id", "reason", "successor", "verdict_captured_at", "agent_needed",
    )  # fmt: skip
    rows = sorted(doc["coins"], key=lambda c: (not c.get("featured"), c.get("rank") or 0))  # demo coins first
    return [{k: c[k] for k in keep if k in c} for c in rows]


def summary(doc: dict[str, Any] | None = None) -> dict[str, Any]:
    doc = doc or load()
    cs = [
        c for c in doc["coins"] if not c.get("featured")
    ]  # featured demo coins sit outside the top-2000 scan
    mig = [c for c in cs if c["type"] == "migration"]
    warmed = [c for c in cs if c.get("verdict") and c["verdict"] != "ERROR"]
    dist = Counter(c["verdict"] for c in warmed)
    return {
        "captured_at": doc["captured_at"],
        "scope": doc["scope"],
        "coins_scanned": doc["coins_scanned"],
        "notices": len(cs),
        "featured_extra": len(doc["coins"]) - len(cs),
        "migration_type": len(mig),
        "other_type": len(cs) - len(mig),
        "prose_only": sum(1 for c in mig if c["prose_only"]),
        "no_ratio_named": sum(1 for c in mig if not c["names_ratio"]),
        "only_unfetchable_hosts": sum(1 for c in mig if c["only_unfetchable_hosts"]),
        "verdicts": {v: dist.get(v, 0) for v in VERDICTS},
        "verdicts_total": len(warmed),
        "verdicts_errors": sum(1 for c in cs if c.get("verdict") == "ERROR"),
        "verdicts_captured": max((c.get("verdict_captured_at") or "" for c in warmed), default="") or None,
        "reader_opened_link": sum(1 for c in warmed if c.get("agent_needed")),
        "not_verifiable_reasons": dict(
            Counter(
                reason_group(c.get("reason", "")) for c in warmed if c["verdict"] == "NOT_VERIFIABLE"
            ).most_common()
        ),
        "old_zero_volume": sum(1 for c in warmed if c.get("old_volume_24h_usd") == 0),
        "market_checked": sum(1 for c in warmed if c.get("old_volume_24h_usd") is not None),
        "method": "regex over CMC's own `notice` field (no LLM); verdicts = the real lookup flow at qty 1, cached reads, one run per coin",
    }


def cache_count() -> int:
    return len(list(EXTRACTIONS.glob("*.json"))) if EXTRACTIONS.exists() else 0
