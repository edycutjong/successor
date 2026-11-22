import json

import httpx
import pytest
import respx

from successor.cmc import BASE_URL, CmcClient

KEY = "test-key-should-never-appear"


@respx.mock
async def test_receipt_redacts_key_and_keeps_verbatim_body():
    body = {"status": {"error_code": 0, "credit_count": 1}, "data": {"12573": {"symbol": "CPOOL"}}}
    respx.get(f"{BASE_URL}/v2/cryptocurrency/info").mock(return_value=httpx.Response(200, json=body))
    async with CmcClient(key=KEY) as cmc:
        r = await cmc.info(ids=[12573])
    receipt = json.dumps(r.receipt())
    assert KEY not in receipt
    assert "$CMC_API_KEY" in receipt
    assert r.receipt()["response"] == body
    assert cmc.credits_used == 1


@respx.mock
async def test_error_status_is_not_ok():
    body = {
        "status": {
            "error_code": 1006,
            "error_message": "Your API Key subscription plan doesn't support this endpoint.",
        }
    }
    respx.get(f"{BASE_URL}/v2/cryptocurrency/market-pairs/latest").mock(
        return_value=httpx.Response(403, json=body)
    )
    async with CmcClient(key=KEY) as cmc:
        r = await cmc.market_pairs(12573)
    assert not r.ok
    assert r.status["error_code"] == 1006


async def test_unplugged_key_fails_loudly(monkeypatch):
    monkeypatch.delenv("CMC_API_KEY", raising=False)
    cmc = CmcClient(key="")
    with pytest.raises(RuntimeError, match="CMC_API_KEY"):
        await cmc.key_info()
