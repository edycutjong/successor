"""CoinMarketCap Pro API client.

Every call returns a `CmcResponse` that keeps the verbatim body, the HTTP status and CMC's own
`credit_count`, so any row shown to a user can be traced back to the exact response it came from.
The API key is read from `CMC_API_KEY` (production: Vercel env) and is never written to a receipt.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

BASE_URL = "https://pro-api.coinmarketcap.com"
LOCAL_KEY_FILE = Path.home() / ".config" / "coinmarketcap" / "credentials.json"


def load_key() -> str | None:
    key = os.environ.get("CMC_API_KEY")
    if key:
        return key
    # Local development only: the key lives outside the repo.
    if LOCAL_KEY_FILE.exists():
        try:
            return json.loads(LOCAL_KEY_FILE.read_text()).get("api_key")
        except (OSError, ValueError):
            return None
    return None


@dataclass
class CmcResponse:
    path: str
    params: dict[str, Any]
    http_status: int
    body: dict[str, Any]
    elapsed_ms: int
    captured_at: str

    @property
    def status(self) -> dict[str, Any]:
        return self.body.get("status") or {}

    @property
    def ok(self) -> bool:
        return self.http_status == 200 and not self.status.get("error_code")

    @property
    def credit_count(self) -> int:
        return int(self.status.get("credit_count") or 0)

    @property
    def data(self) -> Any:
        return self.body.get("data")

    def receipt(self) -> dict[str, Any]:
        """Verbatim response plus the request with the key replaced by a placeholder."""
        query = "&".join(f"{k}={v}" for k, v in self.params.items())
        return {
            "request": {
                "method": "GET",
                "url": f"{BASE_URL}{self.path}" + (f"?{query}" if query else ""),
                "headers": {"X-CMC_PRO_API_KEY": "$CMC_API_KEY"},
            },
            "http_status": self.http_status,
            "elapsed_ms": self.elapsed_ms,
            "captured_at": self.captured_at,
            "credit_count": self.credit_count,
            "response": self.body,
        }


class CmcError(RuntimeError):
    def __init__(self, resp: CmcResponse):
        self.resp = resp
        msg = resp.status.get("error_message") or f"HTTP {resp.http_status}"
        super().__init__(f"CMC {resp.path}: {msg}")


@dataclass
class CmcClient:
    key: str | None = None
    timeout: float = 20.0
    credits_used: int = 0
    calls: list[CmcResponse] = field(default_factory=list)
    _client: httpx.AsyncClient | None = None

    def __post_init__(self) -> None:
        if self.key is None:
            self.key = load_key()

    async def __aenter__(self) -> CmcClient:
        self._client = httpx.AsyncClient(base_url=BASE_URL, timeout=self.timeout)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()

    async def get(
        self, path: str, params: dict[str, Any] | None = None, *, strict: bool = False
    ) -> CmcResponse:
        if not self.key:
            raise RuntimeError("CMC_API_KEY is not set")
        params = {k: v for k, v in (params or {}).items() if v is not None}
        client = self._client or httpx.AsyncClient(base_url=BASE_URL, timeout=self.timeout)
        t0 = time.perf_counter()
        try:
            for attempt in (0, 1):  # one backoff retry on 429 / 5xx / timeout, then the error stands
                try:
                    r = await client.get(
                        path,
                        params=params,
                        headers={"X-CMC_PRO_API_KEY": self.key, "Accept": "application/json"},
                    )
                except httpx.TimeoutException:
                    if attempt:
                        raise
                    await asyncio.sleep(1.0)
                    continue
                if (r.status_code == 429 or r.status_code >= 500) and not attempt:
                    await asyncio.sleep(1.5)
                    continue
                break
        finally:
            if client is not self._client:
                await client.aclose()
        try:
            body = r.json()
        except ValueError:
            body = {"status": {"error_code": r.status_code, "error_message": r.text[:300]}}
        resp = CmcResponse(
            path=path,
            params=params,
            http_status=r.status_code,
            body=body,
            elapsed_ms=round((time.perf_counter() - t0) * 1000),
            captured_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        self.credits_used += resp.credit_count
        self.calls.append(resp)
        if strict and not resp.ok:
            raise CmcError(resp)
        return resp

    # --- the six endpoints Successor reads -------------------------------------------------------

    async def info(
        self,
        ids: list[int] | None = None,
        address: str | None = None,
        slugs: list[str] | None = None,
        aux: str = "urls,platform,date_added,notice,status",
    ) -> CmcResponse:
        params: dict[str, Any] = {"aux": aux}
        if ids:
            params["id"] = ",".join(map(str, ids))
        if slugs:
            params["slug"] = ",".join(slugs)
        if address:
            params["address"] = address
        return await self.get("/v2/cryptocurrency/info", params)

    async def map(
        self, symbol: str | None = None, listing_status: str = "active,inactive,untracked", **extra: Any
    ) -> CmcResponse:
        return await self.get(
            "/v1/cryptocurrency/map", {"listing_status": listing_status, "symbol": symbol, **extra}
        )

    async def quotes_latest(self, ids: list[int], convert: str | None = "USD") -> CmcResponse:
        return await self.get(
            "/v2/cryptocurrency/quotes/latest", {"id": ",".join(map(str, ids)), "convert": convert}
        )

    async def quotes_historical(
        self, cid: int, time_start: str, time_end: str, interval: str = "daily", convert: str | None = "USD"
    ) -> CmcResponse:
        return await self.get(
            "/v2/cryptocurrency/quotes/historical",
            {
                "id": cid,
                "time_start": time_start,
                "time_end": time_end,
                "interval": interval,
                "convert": convert,
            },
        )

    async def market_pairs(self, cid: int, limit: int = 100) -> CmcResponse:
        return await self.get(
            "/v2/cryptocurrency/market-pairs/latest", {"id": cid, "category": "spot", "limit": limit}
        )

    async def key_info(self) -> CmcResponse:
        return await self.get("/v1/key/info")
