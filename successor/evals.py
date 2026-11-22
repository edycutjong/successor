"""Offline eval harness: replay each recorded case (real CMC rows + the Reader's recorded extraction) through the
real flow and assert verdict AND rule. Variants derive from a recorded case by removing evidence."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from successor.flow import lookup_stream
from successor.replay import ReplayCmc

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "evals" / "cases.json"
FIXTURES = ROOT / "tests" / "fixtures" / "cases"


def load_cases() -> list[dict]:
    return json.loads(CASES.read_text())


def _strip(fx: dict, how: str | None) -> dict:
    fx = json.loads(json.dumps(fx))
    if how == "fetches":  # the announcement was not fetchable: announcement-sourced fields fail C3
        fx["extraction"]["fetches"] = []
        fx["extraction"]["link_errors"] = [{"url": "(variant)", "error": "not fetchable"}]
    elif how == "misread-ratio":  # simulated LLM misread: true quote, wrong number (×2)
        f = fx["extraction"]["proposals"][-1]["ratio_new_per_old"]
        f["value"] = float(f["value"]) * 2
    elif how == "misread-deadline":  # simulated LLM misread: true quote, wrong date
        fx["extraction"]["proposals"][-1]["deadline"]["value"] = "2030-10-25"
    elif how == "misread-symbol":  # simulated LLM misread: a symbol that only appears inside another word
        fx["extraction"]["proposals"][-1]["successor_symbol"]["value"] = "LEAR"
    elif how == "event-history":  # no event-date rows: keep only the 30-day windows
        now = fx["now"][:10]
        for e in fx["cmc_log"]:
            if e["path"].endswith("quotes/historical") and e["params"].get("time_end") != now:
                data = e["body"].get("data") or {}
                if "quotes" in data:
                    data["quotes"] = []
    return fx


async def replay(fx: dict, *, strip: str | None = None) -> list[dict]:
    fx = _strip(fx, strip)
    case = fx["case"]
    now = datetime.fromisoformat(fx["now"].replace("Z", "+00:00"))
    return [
        e
        async for e in lookup_stream(
            case["q"],
            case["qty"],
            case["id"],
            cmc=ReplayCmc(fx["cmc_log"]),
            now=now,
            use_cache=False,
            write_cache=False,
            guard_credits=False,
            extraction=fx["extraction"],
        )
    ]


async def run_all() -> list[dict]:
    rows = []
    for case in load_cases():
        fx = json.loads((FIXTURES / f"{case['name']}.json").read_text())
        runs = [(case["name"], None, case["expect"], fx, True)]
        for v in case.get("variants") or ([case["variant"]] if case.get("variant") else []):
            vfx = json.loads((FIXTURES / f"{v['name']}.json").read_text()) if v.get("capture") else fx
            runs.append((v["name"], v.get("strip"), v["expect"], vfx, False))
        for name, strip, exp, f, counted in runs:
            final = (await replay(f, strip=strip))[-1]
            got = {"verdict": final.get("verdict"), "rule_id": final.get("rule_id")}
            rows.append(
                {
                    "n": case["n"],
                    "case": name,
                    "counted": counted,
                    "hand_made": f["hand_made"],
                    "expected": exp,
                    "got": got,
                    "pass": got == exp,
                    "reason": final.get("reason") or final.get("error"),
                    "captured": f["now"],
                }
            )
    return rows
