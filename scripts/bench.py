"""Bench: client-side wall time of a lookup against a live URL.

  python scripts/bench.py https://successor.edycu.dev CPOOL 12                 # cached Reader read (CMC calls are live)
  python scripts/bench.py https://successor.edycu.dev CPOOL 6 --fresh          # cold: Reader re-reads the notice live
  python scripts/bench.py https://successor.edycu.dev CPOOL 20 --gate-p95 3    # exit 1 if p95 > 3 s (performance gate in CI)
  add --warmup to discard one untimed call first (CI does: a fresh deployment's first request is a function cold start)
  add --confirm to re-measure once when only the latency gate fails (CI does); both batches are kept in the file

p95 is the nearest-rank percentile: the ceil(0.95 n)-th fastest sample. At n <= 19 that is the slowest single call (the
2026-11-22 figures, n=12 and n=6, are maxima), so the CI gate takes n=20, where one slow call no longer decides it alone.
Each sample also records the server's own t_ms and its slowest CMC call, so a slow sample shows whether the time went to
the network or a cold start (client >> server) or to CMC (slow call or a 429 retry).

Writes docs/proof/bench/bench-<kind>-<UTC timestamp>.json (every sample, p50/p95, verdicts seen); a re-run never overwrites an
earlier capture. A cold read costs one agent read (1 to 3 Qwen calls; CPOOL's takes one) and fresh reads are limited to 3 per 10 min
per IP, so --fresh runs in batches of 3 with a 10 min pause between them.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

import httpx

OUT = Path(__file__).resolve().parents[1] / "docs" / "proof" / "bench"
COLD_BATCH, COLD_PAUSE_S = 3, 610


def one(base: str, q: str, fresh: bool) -> tuple[float, str, dict]:
    params: dict[str, str] = {"q": q}
    if fresh:
        params["fresh"] = "1"
    headers = {"Accept": "application/json"}
    if os.environ.get("BENCH_BYPASS_SECRET"):  # Vercel Deployment Protection bypass for CI previews
        headers["x-vercel-protection-bypass"] = os.environ["BENCH_BYPASS_SECRET"]
    t0 = time.perf_counter()
    try:
        r = httpx.get(f"{base}/api/lookup", params=params, headers=headers, timeout=70)
    except httpx.HTTPError as exc:  # a timeout or reset is a failed sample, recorded like any other
        return time.perf_counter() - t0, f"0 network-error {type(exc).__name__}", {"server_ms": None}
    dt = time.perf_counter() - t0
    try:
        body = r.json()
    except (
        ValueError
    ):  # an HTML error page (e.g. a platform 502) is a failed sample, not a crash that loses the file
        body = {"type": "non-json"}
    calls = (body.get("receipt") or {}).get("calls") or []
    server = {
        "server_ms": body.get("t_ms"),
        "slowest_cmc_call_ms": max((c.get("latency_ms") or 0 for c in calls), default=None),
    }
    return dt, f"{r.status_code} {body.get('type')} {body.get('verdict')}/{body.get('rule_id')}", server


def pct(xs: list[float], p: float) -> float:
    """Nearest-rank percentile: the smallest sample with at least p % of the samples at or below it."""
    xs = sorted(xs)
    return xs[max(0, math.ceil(p / 100 * len(xs)) - 1)]


def batch(base: str, q: str, n: int, fresh: bool) -> dict:
    samples, seen, server = [], [], []
    for i in range(n):
        if fresh and i and i % COLD_BATCH == 0:
            time.sleep(COLD_PAUSE_S)  # stay under 3 fresh reads / 10 min / IP
        dt, tag, srv = one(base, q, fresh)
        samples.append(round(dt, 3))
        seen.append(tag)
        server.append(srv)
        if not fresh:
            time.sleep(4)  # stay under 20 lookups/min/IP
    return {
        "url": base,
        "query": q,
        "n": n,
        "kind": (
            "cold: fresh=1, the Reader re-reads the notice live (1 to 3 Qwen calls), live CMC calls, full JSON answer"
            if fresh
            else "cached Reader read, live CMC calls, full JSON answer"
        ),
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "samples_s": samples,
        "server": server,
        "p50_s": round(statistics.median(samples), 3),
        "p95_s": round(pct(samples, 95), 3),
        "p95_rule": "nearest rank, ceil(0.95 n)-th fastest; equals max_s when n <= 19",
        "max_s": max(samples),
        "outcomes": sorted(set(seen)),
    }


def save(out: dict, kind: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    stem = f"bench-{kind}-{time.strftime('%Y-%m-%dT%H%MZ', time.gmtime())}"
    path, k = OUT / f"{stem}.json", 2
    while path.exists():  # two runs in the same minute: suffix, never overwrite
        path, k = OUT / f"{stem}-{k}.json", k + 1
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in out.items() if k not in ("samples_s", "server", "first_batch")}, indent=2
        )
    )


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    fresh = "--fresh" in sys.argv
    gate = float(sys.argv[sys.argv.index("--gate-p95") + 1]) if "--gate-p95" in sys.argv else None
    if gate is not None:
        args.remove(str(sys.argv[sys.argv.index("--gate-p95") + 1]))
    base, q, n = args[0].rstrip("/"), args[1], int(args[2])
    kind = "cold" if fresh else "cached"
    if (
        "--warmup" in sys.argv and not fresh
    ):  # one untimed call: a just-created deployment pays a function cold start
        one(base, q, fresh)
        time.sleep(4)
    out = batch(base, q, n, fresh)
    # correctness first: a fast 429, 502 or error is a failure however quick it was
    if any(not t.startswith("200 verdict") for t in out["outcomes"]):
        save(out, kind)
        print("GATE FAIL: a sample did not return a verdict")
        return 1
    if gate is not None and out["p95_s"] > gate and "--confirm" in sys.argv and not fresh:
        # latency only: measure one more batch at the same threshold; the file keeps the failed batch beside it
        print(
            f"p95 {out['p95_s']} s > {gate} s on the first batch; one confirmation batch at the same threshold"
        )
        first, out = out, batch(base, q, n, fresh)
        out["first_batch"] = first
        if any(not t.startswith("200 verdict") for t in out["outcomes"]):
            save(out, kind)
            print("GATE FAIL: a sample did not return a verdict")
            return 1
    save(out, kind)
    if gate is not None and out["p95_s"] > gate:
        print(f"GATE FAIL: p95 {out['p95_s']} s > {gate} s")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
