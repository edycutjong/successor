"""Bench: client-side wall time of a lookup against a live URL (cached Reader read; CMC calls are live).

python scripts/bench.py https://successor.edycu.dev CPOOL 12
Writes docs/proof/bench/bench-<date>.json (every sample, p50/p95, verdicts seen).
Cold (fresh=1) reads are not benched here: each costs a Reader call and is rate-limited to 3 per 10 min per IP;
the single cold samples we have are in docs/proof/deploy/.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

import httpx

OUT = Path(__file__).resolve().parents[1] / "docs" / "proof" / "bench"


def one(base: str, q: str) -> tuple[float, str]:
    t0 = time.perf_counter()
    r = httpx.get(f"{base}/api/lookup", params={"q": q}, headers={"Accept": "application/json"}, timeout=70)
    dt = time.perf_counter() - t0
    body = r.json()
    return dt, f"{r.status_code} {body.get('type')} {body.get('verdict')}/{body.get('rule')}"


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(p / 100 * (len(xs) - 1) + 0.4999))]


def main() -> None:
    base, q, n = sys.argv[1].rstrip("/"), sys.argv[2], int(sys.argv[3])
    samples, seen = [], []
    for _ in range(n):
        dt, tag = one(base, q)
        samples.append(round(dt, 3))
        seen.append(tag)
        time.sleep(4)  # stay under 20 lookups/min/IP
    out = {
        "url": base,
        "query": q,
        "n": n,
        "kind": "cached Reader read, live CMC calls, full JSON answer",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "samples_s": samples,
        "p50_s": round(statistics.median(samples), 3),
        "p95_s": round(pct(samples, 95), 3),
        "max_s": max(samples),
        "outcomes": sorted(set(seen)),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"bench-{time.strftime('%Y-%m-%d', time.gmtime())}.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "samples_s"}, indent=2))


if __name__ == "__main__":
    main()
