"""Capture deploy proof: request URL, host headers and client-side arrival time of every NDJSON line.

python scripts/capture_deploy_proof.py https://successor.edycu.dev CPOOL MKR
# writes docs/proof/deploy/{stream-probe,live-lookup-<Q>}-<date>.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

OUT = Path(__file__).resolve().parents[1] / "docs" / "proof" / "deploy"
KEEP = ("server", "x-vercel-id", "x-vercel-cache", "content-type", "date")


def capture(url: str) -> dict:
    t0 = time.perf_counter()
    lines = []
    with httpx.stream("GET", url, headers={"Accept": "application/x-ndjson"}, timeout=70) as r:
        headers = {k: v for k, v in r.headers.items() if k in KEEP}
        for line in r.iter_lines():
            if line.strip():
                lines.append({"client_s": round(time.perf_counter() - t0, 3), "event": json.loads(line)})
        status = r.status_code
    return {
        "url": url,
        "http_status": status,
        "headers": headers,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "client_wall_s": round(time.perf_counter() - t0, 3),
        "lines": lines,
    }


def main() -> None:
    base, queries = sys.argv[1].rstrip("/"), sys.argv[2:]
    day = time.strftime("%Y-%m-%d", time.gmtime())
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = {"stream-probe": f"{base}/api/stream-probe?n=5&gap=1"}
    jobs.update({f"live-lookup-{q}": f"{base}/api/lookup?q={q}&qty=1000" for q in queries})
    for name, url in jobs.items():
        rec = capture(url)
        (OUT / f"{name}-{day}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n")
        last = rec["lines"][-1]["event"] if rec["lines"] else {}
        print(
            name,
            rec["http_status"],
            rec["headers"].get("server"),
            f"{rec['client_wall_s']}s",
            [round(x["client_s"], 2) for x in rec["lines"]],
            last.get("verdict") or last.get("message", ""),
        )


if __name__ == "__main__":
    main()
