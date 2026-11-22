"""C1: which CMC coin does the user hold? Pure. A symbol that maps to several ids is resolved only by an
explicit id, a contract or an exact name, never by rank."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class C1Result:
    coin: dict | None
    candidates: list[dict] = field(default_factory=list)
    reason: str = ""


def coin_ref(row: dict) -> dict:
    return {
        k: row.get(k) for k in ("id", "symbol", "name", "slug", "is_active", "rank") if row.get(k) is not None
    }


def pick_holding(q: str, candidates: list[dict], cmc_id: int | None = None) -> C1Result:
    cands = list({c["id"]: c for c in candidates}.values())
    if cmc_id is not None:
        hit = [c for c in cands if int(c["id"]) == int(cmc_id)]
        if hit:
            return C1Result(hit[0], cands, f"CMC id {cmc_id}")
        return C1Result(None, cands, f"CMC id {cmc_id} is not among the matches for {q!r}")
    if not cands:
        return C1Result(None, [], f"no CMC coin for {q!r}")
    if len(cands) == 1:
        return C1Result(cands[0], cands, "one CMC id")
    ql = q.strip().lower()
    for key, why in (("slug", "exact slug"), ("name", "exact name")):
        hit = [c for c in cands if (c.get(key) or "").lower() == ql]
        if len(hit) == 1:
            return C1Result(hit[0], cands, why)
    return C1Result(None, cands, f"{q!r} matches {len(cands)} CMC ids; pick one by name or contract")
