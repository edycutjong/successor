"""Day-one spike: every CMC endpoint Successor depends on, for real, with the fields the verifier reads.

    python scripts/spike_cmc.py            # writes docs/proof/spike/*.json + docs/proof/spike/summary.json

Each saved file is a verbatim response (key redacted). summary.json records, per check, whether the
field the verifier needs is present, not merely whether the call returned HTTP 200.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from successor.cmc import CmcClient  # noqa: E402
from successor.verify.ratio import snowflake_date  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "proof" / "spike"
SYMBOLS = ["CPOOL", "CLEAR", "AGIX", "FET", "MKR", "SKY"]
# Expected slugs disambiguate symbol collisions (map returns every coin that ever used a ticker).
SLUGS = {
    "CPOOL": "clearpool",
    "CLEAR": "clearpool-finance",
    "AGIX": "singularitynet",
    "FET": "artificial-superintelligence-alliance",
    "MKR": "maker",
    "SKY": "sky",
}
OLD = ["CPOOL", "AGIX", "MKR"]


def save(name: str, resp) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(resp.receipt(), indent=1, ensure_ascii=False) + "\n")


def eth_contract(info_row: dict) -> str | None:
    for c in info_row.get("contract_address") or []:
        if (c.get("platform") or {}).get("name", "").lower() == "ethereum":
            return c.get("contract_address")
    plat = info_row.get("platform") or {}
    return plat.get("token_address")


async def main() -> int:
    checks: dict[str, dict] = {}

    def check(name: str, ok: bool, detail) -> None:
        checks[name] = {"ok": bool(ok), "detail": detail}
        print(("PASS " if ok else "FAIL ") + name + " — " + json.dumps(detail, ensure_ascii=False)[:220])

    async with CmcClient() as cmc:
        # 6. /v1/key/info — plan + credits (health)
        r = await cmc.key_info()
        save("06-key-info", r)
        plan = (r.data or {}).get("plan", {})
        usage = (r.data or {}).get("usage", {})
        check(
            "key_info.plan",
            r.ok and plan.get("credit_limit_monthly", 0) >= 1_000_000,
            {
                "credit_limit_monthly": plan.get("credit_limit_monthly"),
                "credits_left": (usage.get("current_month") or {}).get("credits_left"),
            },
        )

        # 2. /v1/cryptocurrency/map — resolve symbols, including inactive old coins
        r = await cmc.map(symbol=",".join(SYMBOLS))
        save("02-map", r)
        rows = r.data or []
        ids: dict[str, int] = {}
        for sym, slug in SLUGS.items():
            hit = [x for x in rows if x["symbol"] == sym and x["slug"] == slug]
            if hit:
                ids[sym] = hit[0]["id"]
        collisions = {
            s: [(x["id"], x["slug"], x.get("is_active")) for x in rows if x["symbol"] == s] for s in SYMBOLS
        }
        check(
            "map.resolve",
            len(ids) == len(SYMBOLS),
            {"ids": ids, "collisions": {k: len(v) for k, v in collisions.items()}},
        )
        if len(ids) < len(SYMBOLS):
            print("collisions:", json.dumps(collisions)[:800])

        # 1. /v2/cryptocurrency/info — notice text + contract arrays + date_added
        r = await cmc.info(ids=list(ids.values()))
        save("01-info", r)
        info = {sym: (r.data or {}).get(str(cid), {}) for sym, cid in ids.items()}
        notices = {s: bool(info[s].get("notice")) for s in ids}
        check("info.notice", notices.get("CLEAR") and notices.get("FET") and notices.get("SKY"), notices)
        contracts = {s: eth_contract(info[s]) for s in ids}
        arrays = {s: len(info[s].get("contract_address") or []) for s in ids}
        check(
            "info.contract_address[]",
            all(contracts.get(s) for s in ["CLEAR", "FET"]),
            {"eth": contracts, "array_len": arrays},
        )
        date_added = {s: info[s].get("date_added") for s in ids}
        check("info.date_added", all(date_added.values()), date_added)

        # 3. /v2/cryptocurrency/quotes/latest — price, volume, last_updated
        r = await cmc.quotes_latest(list(ids.values()))
        save("03-quotes-latest", r)
        q = {}
        for sym, cid in ids.items():
            row = (r.data or {}).get(str(cid))
            row = row[0] if isinstance(row, list) else row
            usd = ((row or {}).get("quote") or {}).get("USD") or {}
            q[sym] = {
                "price": usd.get("price"),
                "volume_24h": usd.get("volume_24h"),
                "last_updated": usd.get("last_updated"),
            }
        check("quotes_latest.price", all(v["price"] is not None for v in q.values()), q)

        # 4. /v2/cryptocurrency/quotes/historical — AGIX + FET daily rows around the ASI merger (2024-07-01)
        merger = date(2024, 7, 1)
        hist = {}
        for sym in ["AGIX", "FET"]:
            r = await cmc.quotes_historical(
                ids[sym], (merger - timedelta(days=3)).isoformat(), (merger + timedelta(days=3)).isoformat()
            )
            save(f"04-historical-{sym.lower()}-2024-07", r)
            quotes = ((r.data or {}).get("quotes") if isinstance(r.data, dict) else None) or []
            days = [x["timestamp"][:10] for x in quotes]
            hist[sym] = {
                "http": r.http_status,
                "rows": len(quotes),
                "within_1d": [d for d in days if abs((date.fromisoformat(d) - merger).days) <= 1],
                "error": r.status.get("error_message"),
            }
        check("quotes_historical.merger_rows", all(len(h["within_1d"]) >= 1 for h in hist.values()), hist)

        # 4b. CPOOL/CLEAR rows at the event date. CMC copies date_added from the old id to the new one
        # (CLEAR shows CPOOL's 2021-10-10), so date_added cannot date a rename. The notice's X status id is a
        # snowflake: its top bits are the post's timestamp, which dates the announcement deterministically.
        inherited = date_added.get("CLEAR") == date_added.get("CPOOL")
        m = re.search(r"(?:x|twitter)\.com/\w+/status/(\d+)", info["CLEAR"].get("notice") or "")
        ev = snowflake_date(int(m.group(1))).isoformat() if m else ""
        check(
            "info.date_added_inherited", True, {"clear_equals_cpool": inherited, "snowflake_event_date": ev}
        )
        if ev:
            d0 = date.fromisoformat(ev)
            cl = {}
            for sym in ["CPOOL", "CLEAR"]:
                r = await cmc.quotes_historical(
                    ids[sym], (d0 - timedelta(days=2)).isoformat(), (d0 + timedelta(days=3)).isoformat()
                )
                save(f"04-historical-{sym.lower()}-{ev}", r)
                quotes = ((r.data or {}).get("quotes") if isinstance(r.data, dict) else None) or []
                cl[sym] = [(x["timestamp"][:10], round(x["quote"]["USD"]["price"], 6)) for x in quotes]
            check("quotes_historical.clear_event_date", all(cl.values()), {"event_date": ev, **cl})

        # 5. /v2/cryptocurrency/market-pairs/latest — does the old token still trade on spot pairs?
        mp = {}
        for sym in ["CPOOL", "CLEAR", "AGIX"]:
            r = await cmc.market_pairs(ids[sym])
            save(f"05-market-pairs-{sym.lower()}", r)
            d = r.data if isinstance(r.data, dict) else {}
            mp[sym] = {
                "http": r.http_status,
                "num_market_pairs": d.get("num_market_pairs"),
                "returned": len(d.get("market_pairs") or []),
                "error": r.status.get("error_message"),
            }
        check("market_pairs.spot", mp["CLEAR"]["http"] == 200 and (mp["CLEAR"]["returned"] or 0) >= 1, mp)

        # 1b. info?address= — does CMC resolve the OLD contracts by address? (P0c: 2 of 4 gaps)
        by_addr = {}
        old_known = {"CPOOL": "0x66761fa41377003622aee3c7675fc7b5c1c2fac5"}
        for sym in OLD:
            addr = contracts.get(sym) or old_known.get(sym)
            if not addr:
                by_addr[sym] = {"address": None, "resolved_id": None}
                continue
            r = await cmc.info(address=addr.lower())  # CMC 400s on checksummed case
            save(f"01b-info-address-{sym.lower()}", r)
            got = list((r.data or {}).keys()) if isinstance(r.data, dict) else []
            by_addr[sym] = {
                "address": addr,
                "http": r.http_status,
                "resolved_ids": got,
                "expected_id": ids[sym],
                "error": r.status.get("error_message"),
            }
        resolved_index = {s: bool(contracts.get(s)) for s in OLD}
        check(
            "old_contracts.resolve",
            all(resolved_index.values())
            or all(str(by_addr[s].get("expected_id")) in (by_addr[s].get("resolved_ids") or []) for s in OLD),
            {"from_info_contract_array": resolved_index, "info_by_address": by_addr},
        )

        # convert= re-check: does convert=EUR rescale percent_change / supply on quotes/historical?
        r_usd = await cmc.quotes_historical(ids["FET"], "2026-11-01", "2026-11-02")
        r_eur = await cmc.quotes_historical(ids["FET"], "2026-11-01", "2026-11-02", convert="EUR")
        save("07-convert-usd", r_usd)
        save("07-convert-eur", r_eur)
        try:
            u = r_usd.data["quotes"][0]["quote"]["USD"]
            e = r_eur.data["quotes"][0]["quote"]["EUR"]
            conv = {
                "usd_price": u["price"],
                "eur_price": e["price"],
                "usd_pct24h": u.get("percent_change_24h"),
                "eur_pct24h": e.get("percent_change_24h"),
                "usd_circ": u.get("circulating_supply"),
                "eur_circ": e.get("circulating_supply"),
                "usd_mcap": u.get("market_cap"),
                "eur_mcap": e.get("market_cap"),
            }
        except (KeyError, IndexError, TypeError) as exc:
            conv = {"error": repr(exc)}
        checks["convert_recheck"] = {"ok": True, "detail": conv}
        print("INFO convert_recheck —", json.dumps(conv)[:300])

        summary = {
            "captured_by": "scripts/spike_cmc.py",
            "ids": ids,
            "credits_used": cmc.credits_used,
            "calls": len(cmc.calls),
            "checks": checks,
            "passed": sum(1 for c in checks.values() if c["ok"]),
            "total": len(checks),
        }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
    print(
        f"\n{summary['passed']}/{summary['total']} checks · {summary['calls']} calls · "
        f"{summary['credits_used']} credits"
    )
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
