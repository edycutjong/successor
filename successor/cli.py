"""`python -m successor.cli lookup <query> [--qty N] [--id CMC_ID] [--fresh] [--json]`: the same stream as /api/lookup."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from successor.flow import lookup_stream


def _line(ev: dict) -> str:
    t = f"{ev['t_ms']:>6} ms"
    if ev["type"] == "step":
        keys = ("state", "reason", "cache", "match", "url", "error", "chosen")
        detail = " · ".join(f"{k}={ev[k]}" for k in keys if ev.get(k) not in (None, "", []))
        if ev["step"] == "proposal":
            detail = f"#{ev['n']} {ev['fields']} dropped={ev['dropped']}"
        return f"{t}  {ev['step']:<11} {detail}"[:400]
    if ev["type"] == "verdict":
        return f"{t}  VERDICT {ev['verdict']} ({ev['rule_id']}): {ev['reason']}"
    return f"{t}  {ev['type'].upper()} {json.dumps({k: v for k, v in ev.items() if k not in ('t_ms', 'type')})[:300]}"


async def _main(a: argparse.Namespace) -> int:
    last = None
    async for ev in lookup_stream(a.query, a.qty, a.id, a.fresh):
        last = ev
        if not a.json:
            print(_line(ev), flush=True)
    if a.json:
        print(json.dumps(last, indent=1, ensure_ascii=False))
    return 0 if last and last["type"] != "error" else 1


def main() -> None:
    p = argparse.ArgumentParser(prog="successor")
    sub = p.add_subparsers(dest="cmd", required=True)
    lk = sub.add_parser("lookup")
    lk.add_argument("query")
    lk.add_argument("--qty", type=float, default=1.0)
    lk.add_argument("--id", type=int)
    lk.add_argument("--fresh", action="store_true")
    lk.add_argument("--json", action="store_true")
    sys.exit(asyncio.run(_main(p.parse_args())))


if __name__ == "__main__":
    main()
