"""Day-one spike: the Reader (Qwen via DashScope) on real CMC notices saved by spike_cmc.py.

    python scripts/spike_llm.py [--model qwen4-max]

Checks per notice: a schema-valid Proposal comes back through the submit_proposal tool call, every
evidence quote is a verbatim substring of the notice, and any proposed contract equals one CMC lists
for that coin (case-insensitive for 0x addresses). Transcripts go to docs/proof/spike/llm-<sym>.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from successor.agent.reader import FALLBACK_MODEL, ReaderError, quotes_are_verbatim, read_notice  # noqa: E402

SPIKE = Path(__file__).resolve().parents[1] / "docs" / "proof" / "spike"
TARGETS = ["CLEAR", "FET", "SKY"]


def cmc_contracts(row: dict) -> set[str]:
    return {
        c["contract_address"].lower() for c in row.get("contract_address") or [] if c.get("contract_address")
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None)
    args = ap.parse_args()
    summary_ids = json.loads((SPIKE / "summary.json").read_text())["ids"]
    info = json.loads((SPIKE / "01-info.json").read_text())["response"]["data"]
    by_id = {int(k): v for k, v in info.items()}
    results = {}
    for sym in TARGETS:
        row = by_id[summary_ids[sym]]
        notice = row["notice"]
        model = args.model
        try:
            out = await read_notice(notice, f"{row['name']} ({sym})", model=model)
        except ReaderError as exc:
            print(f"{sym}: primary model failed ({exc}); falling back to {FALLBACK_MODEL}")
            out = await read_notice(notice, f"{row['name']} ({sym})", model=FALLBACK_MODEL)
        p = out["proposal"]
        t = out["transcript"]
        verbatim = quotes_are_verbatim(p, notice)
        known = set()
        for s in summary_ids:
            known |= cmc_contracts(by_id[summary_ids[s]])
        contracts = {k: getattr(p, k).value for k in ("old_contract", "new_contract") if getattr(p, k).value}
        contract_match = {k: str(v).lower() in known for k, v in contracts.items()}
        usage = t["response"].get("usage", {})
        results[sym] = {
            "model": t["model"],
            "latency_ms": t["latency_ms"],
            "usage": usage,
            "event_type": p.event_type,
            "successor": p.successor_symbol.value,
            "ratio": p.ratio_new_per_old.value,
            "contracts": contracts,
            "quotes_verbatim": verbatim,
            "contracts_match_cmc": contract_match,
            "unstated": p.unstated,
            "links_to_follow": p.links_to_follow,
            "ok": all(verbatim.values()) and all(contract_match.values()),
        }
        (SPIKE / f"llm-{sym.lower()}.json").write_text(
            json.dumps({**t, "proposal": p.model_dump(), "notice": notice}, indent=1, ensure_ascii=False)
            + "\n"
        )
        print(
            ("PASS " if results[sym]["ok"] else "FAIL ")
            + sym
            + " — "
            + json.dumps(results[sym], ensure_ascii=False)[:400]
        )
    (SPIKE / "llm-summary.json").write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n")
    ok = sum(r["ok"] for r in results.values())
    print(f"\n{ok}/{len(results)} notices: schema-valid, quotes verbatim, contracts equal CMC's")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
