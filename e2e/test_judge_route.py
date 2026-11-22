"""/judge must answer 200 with no credentials, no cookies and no session, and carry the claim."""

from __future__ import annotations

import httpx

CLAIM = "CoinMarketCap says a coin migrated, but only in prose"


def test_judge_page_is_open(base_url):
    with httpx.Client(follow_redirects=False, timeout=30) as c:
        r = c.get(base_url + "/judge")
    assert r.status_code == 200 and CLAIM in r.text
    assert "set-cookie" not in r.headers


def test_judge_page_links_resolve(base_url):
    for path in ("/", "/api/health", "/api/census"):
        assert httpx.get(base_url + path, timeout=30).status_code == 200
