"""Bench: client-side wall time of a lookup against a live URL.

  python scripts/bench.py https://successor.edycu.dev CPOOL 12                 # cached Reader read (CMC calls are live)
  python scripts/bench.py https://successor.edycu.dev CPOOL 6 --fresh          # cold: Reader re-reads the notice live
  python scripts/bench.py https://successor.edycu.dev CPOOL 12 --gate-p95 3    # exit 1 if p95 > 3 s (performance gate in CI)

Writes docs/proof/bench/bench-<kind>-<date>.json (every sample, p50/p95, verdicts seen). Cold reads cost one Qwen call each and
are limited to 3 per 10 min per IP, so --fresh runs in batches of 3 with a 10 min pause between them.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

import httpx

OUT = Path(__file__).resolve().parents[1] / "docs" / "proof" / "bench"
COLD_BATCH, COLD_PAUSE_S = 3, 610


def one(base: str, q: str, fresh: bool) -> tuple[float, str]:
    params: dict[str, str] = {"q": q}
    if fresh:
        params["fresh"] = "1"
    t0 = time.perf_counter()
    r = httpx.get(f"{base}/api/lookup", params=params, headers={"Accept": "application/json"}, timeout=70)
    dt = time.perf_counter() - t0
    body = r.json()
    return dt, f"{r.status_code} {body.get('type')} {body.get('verdict')}/{body.get('rule_id')}"


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(p / 100 * (len(xs) - 1) + 0.4999))]


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    fresh = "--fresh" in sys.argv
    gate = float(sys.argv[sys.argv.index("--gate-p95") + 1]) if "--gate-p95" in sys.argv else None
    if gate is not None:
        args.remove(str(sys.argv[sys.argv.index("--gate-p95") + 1]))
    base, q, n = args[0].rstrip("/"), args[1], int(args[2])
    samples, seen = [], []
    for i in range(n):
        if fresh and i and i % COLD_BATCH == 0:
            time.sleep(COLD_PAUSE_S)  # stay under 3 fresh reads / 10 min / IP
        dt, tag = one(base, q, fresh)
        samples.append(round(dt, 3))
        seen.append(tag)
        if not fresh:
            time.sleep(4)  # stay under 20 lookups/min/IP
    kind = "cold" if fresh else "cached"
    out = {
        "url": base,
        "query": q,
        "n": n,
        "kind": (
            "cold: fresh=1, the Reader re-reads the notice live (one Qwen call), live CMC calls, full JSON answer"
            if fresh
            else "cached Reader read, live CMC calls, full JSON answer"
        ),
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "samples_s": samples,
        "p50_s": round(statistics.median(samples), 3),
        "p95_s": round(pct(samples, 95), 3),
        "max_s": max(samples),
        "outcomes": sorted(set(seen)),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    name = (
        f"bench-{time.strftime('%Y-%m-%d', time.gmtime())}.json"
        if not fresh
        else f"bench-{kind}-{time.strftime('%Y-%m-%d', time.gmtime())}.json"
    )
    (OUT / name).write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "samples_s"}, indent=2))
    if gate is not None and out["p95_s"] > gate:
        print(f"GATE FAIL: p95 {out['p95_s']} s > {gate} s")
        return 1
    if any(not t.startswith("200 verdict") for t in seen):
        print("GATE FAIL: a sample did not return a verdict")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
