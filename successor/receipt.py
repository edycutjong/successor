"""Receipts: every CMC row and every Reader turn behind a verdict, verbatim, with the key replaced by a placeholder."""

from __future__ import annotations

import shlex
from typing import Any
from urllib.parse import urlencode

from successor.cmc import BASE_URL, CmcResponse


def call_id(i: int) -> str:
    return f"r{i + 1}"


def curl(resp: CmcResponse) -> str:
    """A command a judge can paste: the key expands from the shell (double quotes), the URL is encoded and
    single-quoted (a2a r03: the header used to sit in single quotes, so $CMC_API_KEY never expanded)."""
    query = urlencode(resp.params, safe=",")
    url = f"{BASE_URL}{resp.path}" + (f"?{query}" if query else "")
    return f'curl -s -H "X-CMC_PRO_API_KEY: $CMC_API_KEY" {shlex.quote(url)}'


def build(
    calls: list[CmcResponse], llm: list[dict], fetches: list[dict], *, recorded: bool
) -> dict[str, Any]:
    return {
        "calls": [
            {
                "id": call_id(i),
                "endpoint": c.path,
                "params": c.params,
                "http_status": c.http_status,
                "latency_ms": c.elapsed_ms,
                "credit_count": c.credit_count,
                "ts": c.captured_at,
                "data": c.body,
            }
            for i, c in enumerate(calls)
        ],
        "curl": [curl(c) for c in calls],
        "llm": llm,
        "llm_source": "recorded extraction (cache)" if recorded else "live",
        "pages": [
            {k: f.get(k) for k in ("url", "final_url", "host", "sha256", "fetched_at", "latency_ms")}
            | {"label": f"read from {f.get('host')} on {str(f.get('fetched_at', ''))[:10]}"}
            for f in fetches
        ],
        "credits_used": sum(c.credit_count for c in calls),
    }
