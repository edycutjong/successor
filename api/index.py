"""Successor API — the only serverless function. Vercel routes /api/* here (vercel.json)."""

from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict, deque
from pathlib import Path

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from successor import __version__  # noqa: E402
from successor import census as cn  # noqa: E402
from successor.agent.reader import load_config  # noqa: E402
from successor.cmc import CmcClient  # noqa: E402
from successor.flow import lookup_stream  # noqa: E402

app = FastAPI(title="Successor", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json")

# --- abuse gate (a2a r03) ------------------------------------------------------------------------------------
# Every lookup calls CMC live; fresh=1 forces a paid Reader call. Windows are per serverless instance, so this
# bounds a burst from one client, not the deployment (the Reader's daily cap is per instance too).
LIMITS = {"lookup": (20, 60.0), "hero": (60, 60.0), "fresh": (3, 600.0), "fresh_all": (30, 3600.0)}
_hits: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    """Platform-set client address first (a2a r04): Vercel writes x-real-ip / x-vercel-forwarded-for itself; the
    left-most X-Forwarded-For is only a fallback for other hosts."""
    for h in ("x-real-ip", "x-vercel-forwarded-for"):
        v = request.headers.get(h, "").split(",")[0].strip()
        if v:
            return v
    fwd = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return fwd or (request.client.host if request.client else "?")


def _wait(bucket: str, kind: str, now: float) -> float | None:
    """Seconds to wait when the window is full, else None. Prunes the window; records nothing."""
    n, win = LIMITS[kind]
    q = _hits.get(bucket)
    while q and now - q[0] > win:
        q.popleft()
    if q is not None and not q:
        del _hits[bucket]  # idle keys do not accumulate on a warm instance
        q = None
    return win - (now - q[0]) if q is not None and len(q) >= n else None


def _limited(request: Request, fresh: bool, kind: str = "lookup") -> JSONResponse | None:
    ip, now = _client_ip(request), time.monotonic()
    # the first-screen hero has its own wider bucket, so a shared-NAT room still sees it (P1d QA r2)
    checks = [(f"{kind}:{ip}", kind)] + (
        [(f"fresh:{ip}", "fresh"), ("fresh:*", "fresh_all")] if fresh else []
    )
    for bucket, kind in checks:
        wait = _wait(bucket, kind, now)
        if wait is not None:
            what = "live re-reads" if kind.startswith("fresh") else "lookups"
            body = {
                "type": "error",
                "step": "rate_limit",
                "error": f"too many {what} from this client; try again in {int(wait) + 1} s (cached reads stay open)",
                "http_status": 429,
                "t_ms": 0,
            }
            return JSONResponse(body, status_code=429, headers={"Retry-After": str(int(wait) + 1)})
    for bucket, _ in checks:  # a hit is recorded only once every bucket agreed (a2a r04)
        _hits[bucket].append(now)
    return None


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
        except (RuntimeError, httpx.HTTPError) as exc:
            cmc_part = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}
    llm = load_config()
    return JSONResponse(
        {
            "cmc": cmc_part,
            "llm": {"model": llm["model"], "configured": bool(llm["api_key"])},
            "cache": {"extractions": cn.cache_count()},
            "census_captured_at": cn.load().get("captured_at"),
            "build_sha": os.environ.get("VERCEL_GIT_COMMIT_SHA") or os.environ.get("BUILD_SHA", "local"),
            "version": __version__,
        }
    )


@app.get("/api/notices")
async def notices() -> JSONResponse:
    doc = cn.load()
    return JSONResponse(
        {"captured_at": doc["captured_at"], "count": len(doc["coins"]), "notices": cn.notices(doc)}
    )


@app.get("/api/census")
async def census() -> JSONResponse:
    return JSONResponse(cn.summary())


@app.get("/api/hero")
async def hero(request: Request, qty: float = Query(10000.0, ge=0, le=1e15)):
    """The first-screen lookup (CPOOL): the same live flow as /api/lookup, cached extraction."""
    if (blocked := _limited(request, False, kind="hero")) is not None:
        return blocked
    return await _lookup(request, cn.HERO_Q, qty, cn.HERO_ID, False)


@app.get("/api/lookup")
async def lookup(
    request: Request,
    q: str = Query(..., min_length=1, max_length=80),
    qty: float = Query(1.0, ge=0, le=1e15),
    id: int | None = Query(None, ge=1),  # noqa: A002 - CMC id picked from the candidates
    fresh: bool = Query(False),
):
    if (blocked := _limited(request, fresh)) is not None:
        return blocked
    return await _lookup(request, q, qty, id, fresh)


async def _lookup(request: Request, q: str, qty: float, id: int | None, fresh: bool):  # noqa: A002
    if "application/json" in request.headers.get("accept", "") and "ndjson" not in request.headers.get(
        "accept", ""
    ):
        final = None
        async for ev in lookup_stream(q, qty, id, fresh):
            final = ev
        if final is None:  # a2a r03: never answer `null`
            final = {
                "type": "error",
                "step": "stream",
                "error": "the lookup produced no event",
                "http_status": 502,
            }
        status = 200 if final["type"] != "error" else final.get("http_status") or 502
        return JSONResponse(final, status_code=status if status >= 400 or status == 200 else 502)

    async def gen():
        async for ev in lookup_stream(q, qty, id, fresh):
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


if os.environ.get("SERVE_STATIC") == "1":  # local development only; Vercel serves public/ itself
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(Path(__file__).resolve().parents[1] / "public"), html=True))
