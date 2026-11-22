"""Successor API — the only serverless function. Vercel routes /api/* here (vercel.json)."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from successor import __version__  # noqa: E402
from successor.agent.reader import load_config  # noqa: E402
from successor.cmc import CmcClient  # noqa: E402
from successor.flow import lookup_stream  # noqa: E402

app = FastAPI(title="Successor", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.get("/api/health")
async def health() -> JSONResponse:
    async with CmcClient() as cmc:
        try:
            r = await cmc.key_info()
            d = r.data or {}
            cmc_part = {
                "ok": r.ok,
                "plan_credit_limit_monthly": (d.get("plan") or {}).get("credit_limit_monthly"),
                "credits_left": ((d.get("usage") or {}).get("current_month") or {}).get("credits_left"),
                "checked_at": r.captured_at,
            }
        except RuntimeError as exc:
            cmc_part = {"ok": False, "error": str(exc)}
    llm = load_config()
    return JSONResponse(
        {
            "cmc": cmc_part,
            "llm": {"model": llm["model"], "configured": bool(llm["api_key"])},
            "build_sha": os.environ.get("VERCEL_GIT_COMMIT_SHA") or os.environ.get("BUILD_SHA", "local"),
            "version": __version__,
        }
    )


@app.get("/api/lookup")
async def lookup(
    request: Request, q: str = Query(..., min_length=1, max_length=80), qty: float = Query(1.0, ge=0)
):
    if "application/json" in request.headers.get("accept", "") and "ndjson" not in request.headers.get(
        "accept", ""
    ):
        final = None
        async for ev in lookup_stream(q, qty):
            final = ev
        return JSONResponse(final, status_code=200 if final and final["type"] != "error" else 502)

    async def gen():
        async for ev in lookup_stream(q, qty):
            yield json.dumps(ev, ensure_ascii=False) + "\n"

    return StreamingResponse(
        gen(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@app.get("/api/stream-probe")
async def stream_probe(n: int = Query(5, ge=1, le=20), gap: float = Query(1.0, ge=0, le=5)):
    """Proves the host streams NDJSON line by line instead of buffering the whole body."""
    import asyncio

    async def gen():
        t0 = time.perf_counter()
        for i in range(n):
            yield json.dumps({"i": i, "server_ms": round((time.perf_counter() - t0) * 1000)}) + "\n"
            await asyncio.sleep(gap)

    return StreamingResponse(gen(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"})
