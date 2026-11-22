"""Lookup flow as a stream of trace events.

P1a scope (spike): resolve → read the notice → Reader proposal (cold, no cache) → check the proposed contracts
against CMC's contract arrays → quotes for old and new → a provisional outcome. The deterministic verifiers
C1–C6 and the verdict table replace `provisional_outcome` in the core-flow phase; until then every
final event carries `"engine": "spike"`.
"""

from __future__ import annotations

import re
import time
from collections.abc import AsyncIterator
from typing import Any

from successor.agent.reader import ReaderError, quotes_are_verbatim, read_notice
from successor.cmc import CmcClient


def _event(kind: str, t0: float, **data: Any) -> dict[str, Any]:
    return {"type": kind, "t_ms": round((time.perf_counter() - t0) * 1000), **data}


def _contracts(row: dict) -> set[str]:
    return {
        c["contract_address"].lower() for c in row.get("contract_address") or [] if c.get("contract_address")
    }


def _usd(row: dict | list | None) -> dict:
    row = row[0] if isinstance(row, list) and row else row
    return (((row or {}).get("quote") or {}).get("USD")) or {}


async def resolve(cmc: CmcClient, q: str) -> list[dict]:
    q = q.strip()
    if q.lower().startswith("0x"):
        r = await cmc.info(address=q.lower())  # CMC 400s on checksummed case
        return [
            {"id": int(k), "symbol": v.get("symbol"), "slug": v.get("slug")}
            for k, v in (r.data or {}).items()
        ]
    r = await cmc.map(symbol=q.upper())
    return [
        {
            "id": x["id"],
            "symbol": x["symbol"],
            "slug": x["slug"],
            "is_active": x.get("is_active"),
            "rank": x.get("rank"),
        }
        for x in (r.data or [])
    ]


def provisional_outcome(
    prop: dict, old: dict, new: dict | None, contract_ok: bool | None, quotes_ok: bool = True
) -> dict:
    """Spike rule. Anything short of verified contracts and verbatim quotes is NOT VERIFIABLE."""
    ratio = prop.get("ratio_new_per_old")
    if not new:
        return {"verdict": "NOT VERIFIABLE", "reason": "successor did not resolve to one CMC coin"}
    if not quotes_ok:
        return {"verdict": "NOT VERIFIABLE", "reason": "an evidence quote is not in the notice text"}
    if contract_ok is False:
        return {"verdict": "NOT VERIFIABLE", "reason": "a quoted contract differs from CMC's"}
    if contract_ok is None:
        return {"verdict": "NOT VERIFIABLE", "reason": "no quoted contract to check against CMC"}
    if ratio is None:
        return {"verdict": "NOT VERIFIABLE", "reason": "the notice states no swap ratio"}
    p_old, p_new = old.get("price"), new.get("price")
    if not p_old or not p_new:
        return {"verdict": "NOT VERIFIABLE", "reason": "a price is missing"}
    value_old, value_new = p_old, float(ratio) * p_new
    if (old.get("volume_24h") or 0) > 0 and value_old > value_new * 1.02:
        return {"verdict": "SELL OLD", "old_over_new": round(value_old / value_new, 4)}
    return {"verdict": "SWAP", "old_over_new": round(value_old / value_new, 4)}


def cmc_slugs_in(text: str) -> list[str]:
    """CMC coin slugs linked in a notice (coinmarketcap.com/currencies/<slug>/)."""
    return re.findall(r"coinmarketcap\.com/currencies/([a-z0-9-]+)", text or "")


def check_contracts(prop: dict, old_set: set[str] | None, new_set: set[str]) -> bool | None:
    """old_contract must be the old coin's, new_contract the successor's. None when nothing is quoted."""
    results = []
    if prop.get("old_contract"):
        results.append(old_set is not None and str(prop["old_contract"]).lower() in old_set)
    if prop.get("new_contract"):
        results.append(str(prop["new_contract"]).lower() in new_set)
    return all(results) if results else None


async def lookup_stream(q: str, qty: float = 1.0) -> AsyncIterator[dict[str, Any]]:
    t0 = time.perf_counter()
    async with CmcClient() as cmc:
        cands = await resolve(cmc, q)
        yield _event("step", t0, step="resolve", query=q, candidates=cands[:5])
        if not cands:
            yield _event("error", t0, step="resolve", message="no CMC coin for this query")
            return
        active = [c for c in cands if c.get("is_active", 1)] or cands
        coin = sorted(active, key=lambda c: c.get("rank") or 10**9)[0]

        r = await cmc.info(ids=[coin["id"]])
        if not r.ok:
            yield _event(
                "error", t0, step="info", message=r.status.get("error_message"), http_status=r.http_status
            )
            return
        row = (r.data or {}).get(str(coin["id"]), {})
        notice = row.get("notice") or ""
        yield _event(
            "step",
            t0,
            step="notice",
            coin=coin,
            has_notice=bool(notice),
            notice=notice,
            credits=r.credit_count,
        )
        if not notice:
            yield _event(
                "outcome",
                t0,
                outcome="no_notice",
                message="CMC states no migration for this coin",
                engine="spike",
            )
            return

        try:
            out = await read_notice(notice, f"{row.get('name')} ({row.get('symbol')})")
        except ReaderError as exc:
            yield _event("error", t0, step="reader", message=str(exc))
            return
        prop = {
            k: (v.get("value") if isinstance(v, dict) else v) for k, v in out["proposal"].model_dump().items()
        }
        yield _event(
            "step",
            t0,
            step="reader",
            model=out["transcript"]["model"],
            latency_ms=out["transcript"]["latency_ms"],
            proposal=prop,
            cache="miss",
        )

        source = notice
        verbatim = quotes_are_verbatim(out["proposal"], source)
        quotes_ok = all(verbatim.values())
        yield _event("step", t0, step="quotes_verbatim", checks=verbatim, ok=quotes_ok)

        succ_sym = prop.get("successor_symbol")
        new_coin = None
        if succ_sym:
            succ = [c for c in await resolve(cmc, str(succ_sym)) if c.get("is_active", 1)]
            linked = set(cmc_slugs_in(notice))
            by_link = [c for c in succ if c.get("slug") in linked]
            if len(succ) == 1:
                new_coin = succ[0]
            elif len(by_link) == 1:  # the notice links the successor's CMC page
                new_coin = by_link[0]
            elif succ and prop.get("new_contract"):
                ri = await cmc.info(ids=[c["id"] for c in succ])
                hits = [
                    c
                    for c in succ
                    if str(prop["new_contract"]).lower() in _contracts((ri.data or {}).get(str(c["id"]), {}))
                ]
                new_coin = hits[0] if len(hits) == 1 else None
        if new_coin and new_coin["id"] == coin["id"]:
            yield _event(
                "error",
                t0,
                step="contracts",
                message="looked-up coin is the successor; spike needs the old coin",
            )
            return
        ids = [coin["id"]] + ([new_coin["id"]] if new_coin else [])
        ri = await cmc.info(ids=ids)
        old_set = _contracts((ri.data or {}).get(str(coin["id"]), {}))
        new_set = _contracts((ri.data or {}).get(str(new_coin["id"]), {})) if new_coin else set()
        contract_ok = check_contracts(prop, old_set, new_set) if new_coin else None
        quoted = {k: prop[k] for k in ("old_contract", "new_contract") if prop.get(k)}
        yield _event("step", t0, step="contracts", successor=new_coin, quoted=quoted, match=contract_ok)

        rq = await cmc.quotes_latest(ids)
        old_q = _usd((rq.data or {}).get(str(coin["id"])))
        new_q = _usd((rq.data or {}).get(str(new_coin["id"]))) if new_coin else None
        yield _event(
            "step",
            t0,
            step="quotes",
            old={k: old_q.get(k) for k in ("price", "volume_24h", "last_updated")},
            new={k: new_q.get(k) for k in ("price", "volume_24h", "last_updated")} if new_q else None,
        )

        verdict = provisional_outcome(prop, old_q, new_q, contract_ok, quotes_ok)
        yield _event("verdict", t0, engine="spike", qty=qty, credits_used=cmc.credits_used, **verdict)
