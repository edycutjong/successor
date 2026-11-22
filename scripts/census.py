"""Census of CoinMarketCap notices in the top N coins, and the pre-warm pass.

  python scripts/census.py scan [--top 2000]      CMC map + info(aux=notice) -> data/census.json (counts, flags)
  python scripts/census.py warm [--workers 3]     run every notice coin through the real lookup flow (this also
                                                  writes data/extractions/*), record verdict + capture time
  python scripts/census.py report                 print the counts and the verdict distribution

Every number in data/census.json carries `captured_at`. The classification here is plain regex over the
notice text (no LLM): the census states what CMC's own field contains, the verdicts come from the real flow.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from successor.cmc import CmcClient  # noqa: E402
from successor.flow import lookup_stream  # noqa: E402

CENSUS = ROOT / "data" / "census.json"
SNAP_DIR = ROOT / "data" / "notices"

MIGRATION = re.compile(
    r"migrat|swap|redenominat|rebrand|renam|new contract|new token|merge|consolidat|upgrade|"
    r"ticker|symbol change|changed (?:its )?(?:name|symbol|ticker)|replac|convert|exchange .* for",
    re.I,
)
CONTRACT_LINK = re.compile(r"/(?:token|address)/0x[0-9a-fA-F]{6,}|\b0x[0-9a-fA-F]{40}\b")
UNFETCHABLE = ("x.com", "twitter.com", "t.me", "discord.gg", "discord.com", "medium.com")
RATIO = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?::|to|for)\s*\d+(?:[.,]\d+)?\b|\b1\s*[:=]\s*1\b|ratio|per\s+(?:old|1)\b", re.I
)
URL = re.compile(r"https?://[^\s)\]>\"']+")


FEATURED = [12573, 2424, 35716, 11221]  # CPOOL, AGIX, RZUSD, BIT: the demo coins; outside the active top 2000


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def host(u: str) -> str:
    m = re.match(r"https?://([^/]+)", u)
    return (m.group(1).lower() if m else "").removeprefix("www.")


def classify(notice: str) -> dict:
    links = URL.findall(notice)
    hosts = sorted({host(u) for u in links})
    # exact host or a subdomain: a bare suffix test would count "notcoinmarketcap.com" as CMC (CodeQL py/incomplete-url-substring-sanitization)
    non_cmc = [h for h in hosts if h != "coinmarketcap.com" and not h.endswith(".coinmarketcap.com")]
    only_unfetchable = bool(non_cmc) and all(
        any(h == b or h.endswith("." + b) for b in UNFETCHABLE) for h in non_cmc
    )
    ntype = "migration" if MIGRATION.search(notice) else "other"
    return {
        "type": ntype,
        "prose_only": ntype == "migration" and not CONTRACT_LINK.search(notice),
        "names_contract": bool(CONTRACT_LINK.search(notice)),
        "names_ratio": bool(RATIO.search(notice)),
        "links": len(links),
        "only_unfetchable_hosts": only_unfetchable,
    }


async def scan(top: int) -> None:
    async with CmcClient() as cmc:
        r = await cmc.get(
            "/v1/cryptocurrency/map", {"listing_status": "active", "sort": "cmc_rank", "limit": top}
        )
        assert r.ok, r.status
        coins = [c for c in r.data if c.get("rank")][:top]
        credits = r.credit_count
        rows: list[dict] = []
        for i in range(0, len(coins), 100):
            batch = coins[i : i + 100]
            ri = await cmc.info(ids=[c["id"] for c in batch], aux="notice,date_added")
            assert ri.ok, ri.status
            credits += ri.credit_count
            for c in batch:
                info = (ri.data or {}).get(str(c["id"])) or {}
                if isinstance(info, list):
                    info = info[0] if info else {}
                notice = (info.get("notice") or "").strip()
                if notice:
                    rows.append(
                        {
                            "id": c["id"],
                            "symbol": c["symbol"],
                            "name": c["name"],
                            "slug": c["slug"],
                            "rank": c["rank"],
                            "notice": notice,
                            **classify(notice),
                        }
                    )
        rf = await cmc.info(ids=FEATURED, aux="notice")
        credits += rf.credit_count
        for fid in FEATURED:
            info = (rf.data or {}).get(str(fid)) or {}
            if isinstance(info, list):
                info = info[0] if info else {}
            notice = (info.get("notice") or "").strip()
            if notice and not any(r["id"] == fid for r in rows):
                rows.append(
                    {
                        "id": fid,
                        "symbol": info["symbol"],
                        "name": info["name"],
                        "slug": info["slug"],
                        "rank": None,
                        "featured": True,
                        "notice": notice,
                        **classify(notice),
                    }  # fmt: skip
                )
    prev = json.loads(CENSUS.read_text()) if CENSUS.exists() else {}
    keep = {c["id"]: c for c in prev.get("coins", [])}
    for row in rows:
        old = keep.get(row["id"])
        if old and old.get("notice") == row["notice"]:
            for k in (
                "verdict",
                "rule_id",
                "reason",
                "verdict_captured_at",
                "agent_needed",
                "cold_ms",
                "successor",
            ):
                if k in old:
                    row[k] = old[k]
    captured = now()
    doc = {
        "captured_at": captured,
        "scope": f"top {top} by cmc_rank, listing_status=active",
        "coins_scanned": len(coins),
        "credits": credits,
        "coins": rows,
    }
    CENSUS.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    (SNAP_DIR / f"{captured[:10]}.json").write_text(
        json.dumps(
            {"captured_at": captured, "notices": {c["id"]: c["notice"] for c in rows}},
            indent=1,
            ensure_ascii=False,
        )
        + "\n"
    )
    print(f"scanned {len(coins)} coins, {len(rows)} notices, {credits} credits, captured {captured}")


async def warm(workers: int, only: set[int] | None, redo: bool) -> None:
    doc = json.loads(CENSUS.read_text())
    todo = [c for c in doc["coins"] if (only is None or c["id"] in only) and (redo or "verdict" not in c)]
    print(f"{len(todo)} coins to warm, {workers} workers", flush=True)
    sem = asyncio.Semaphore(workers)
    lock = asyncio.Lock()

    async def one(c: dict) -> None:
        async with sem:
            steps: list[str] = []
            final: dict | None = None
            t_agent = False
            try:
                async for ev in lookup_stream(c["symbol"], 1.0, c["id"], False, guard_credits=True):
                    if ev["type"] == "step":
                        steps.append(ev.get("step", ""))
                        if ev.get("step") in ("follow_link", "link", "fetch", "followed"):
                            t_agent = True
                        if ev.get("url") and ev.get("step") not in ("resolve", "notice"):
                            t_agent = True
                    final = ev
            except Exception as exc:  # noqa: BLE001 - one bad coin must not stop the pass
                final = {"type": "error", "error": f"{type(exc).__name__}: {exc}"[:200], "t_ms": 0}
            async with lock:
                if final and final["type"] == "verdict":
                    c["verdict"] = final["verdict"]
                    c["rule_id"] = final.get("rule_id")
                    c["reason"] = (final.get("reason") or "")[:300]
                    succ = final.get("successor") or {}
                    c["successor"] = succ.get("symbol") if isinstance(succ, dict) else None
                    c["old_volume_24h_usd"] = final.get("old_volume_24h_usd")
                    c["old_price_usd"] = final.get("old_price_usd")
                else:
                    c["verdict"] = "ERROR"
                    c["rule_id"] = None
                    c["reason"] = ((final or {}).get("error") or (final or {}).get("message") or "no result")[
                        :300
                    ]
                c["verdict_captured_at"] = now()
                c["agent_needed"] = t_agent
                c["cold_ms"] = (final or {}).get("t_ms")
                CENSUS.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
                print(f"{c['symbol']:>8} {c['verdict']:<14} {c.get('rule_id')} {c['cold_ms']} ms", flush=True)

    await asyncio.gather(*(one(c) for c in todo))


def report() -> None:
    doc = json.loads(CENSUS.read_text())
    cs = doc["coins"]
    print(doc["captured_at"], doc["scope"], "notices:", len(cs))
    print("types:", dict(Counter(c["type"] for c in cs)))
    mig = [c for c in cs if c["type"] == "migration"]
    print("migration prose_only:", sum(c["prose_only"] for c in mig), "/", len(mig))
    print(
        "no ratio named:",
        sum(not c["names_ratio"] for c in mig),
        "only unfetchable hosts:",
        sum(c["only_unfetchable_hosts"] for c in mig),
    )
    print("verdicts:", dict(Counter(c.get("verdict", "unwarmed") for c in cs)))
    print("agent needed:", sum(bool(c.get("agent_needed")) for c in cs), "/", sum("verdict" in c for c in cs))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--top", type=int, default=2000)
    w = sub.add_parser("warm")
    w.add_argument("--workers", type=int, default=3)
    w.add_argument("--only", type=int, nargs="*")
    w.add_argument("--redo", action="store_true")
    sub.add_parser("report")
    a = ap.parse_args()
    if a.cmd == "scan":
        asyncio.run(scan(a.top))
    elif a.cmd == "warm":
        asyncio.run(warm(a.workers, set(a.only) if a.only else None, a.redo))
    else:
        report()
