"""The judged flow on the live URL: open, click a coin, assert a real verdict and its receipt."""

from __future__ import annotations

import httpx

from .conftest import VERDICTS

DONE = "document.querySelector('#receipt-btn') && !document.querySelector('#receipt-btn').disabled"


def verdict_of(page) -> tuple[str, str]:
    cls = (page.locator("#f-verdict").get_attribute("class") or "").split()
    word = next((c for c in cls if c in VERDICTS), "")
    text = "".join(page.locator("#f-verdict .flap").all_inner_texts()).replace("\xa0", " ").strip()
    return word, text


def run_chip(page, base_url: str, symbol: str) -> None:
    page.goto(base_url + "/")
    page.click(f'#chips button[data-q="{symbol}"]')
    page.wait_for_function(DONE)


def test_cpool_returns_a_verdict_with_checks_and_a_capture_time(page, base_url):
    run_chip(page, base_url, "CPOOL")
    word, text = verdict_of(page)
    assert word in VERDICTS, f"no verdict class on #f-verdict (got {word!r}, text {text!r})"
    assert text, "verdict flaps are empty"
    assert "".join(page.locator("#f-old .flap").all_inner_texts()).strip() == "CPOOL"
    assert page.locator("#checks li").count() >= 5, "the code checks did not render"
    assert page.locator("#reason").inner_text().strip(), "verdict has no stated reason"
    assert "captured 20" in page.locator("#captured").inner_text()


def test_the_receipt_opens_and_names_cmc_endpoints(page, base_url):
    run_chip(page, base_url, "CPOOL")
    page.click("#receipt-btn")
    body = page.locator("body").inner_text()
    assert "/v" in body and ("cryptocurrency" in body or "info" in body), "receipt shows no CMC endpoint"


def test_agix_follows_a_link_and_reaches_a_verdict(page, base_url):
    run_chip(page, base_url, "AGIX")
    word, _ = verdict_of(page)
    assert word in VERDICTS
    assert "fetch" in page.locator("#trace").inner_text().lower(), "the trace does not show the followed link"


def test_typed_lookup_works(page, base_url):
    page.goto(base_url + "/")
    page.fill("#q", "CPOOL")
    page.click("#go")
    page.wait_for_function(DONE)
    assert verdict_of(page)[0] in VERDICTS


def test_api_lookup_json_is_a_verdict_event(base_url):
    r = httpx.get(
        base_url + "/api/lookup", params={"q": "CPOOL"}, headers={"Accept": "application/json"}, timeout=70
    )
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "verdict" and body["verdict"] in VERDICTS and body["rule"]


def test_health_reports_a_working_cmc_key_and_the_model(base_url):
    h = httpx.get(base_url + "/api/health", timeout=30).json()
    assert h["cmc"]["ok"] is True and h["llm"]["configured"] is True and h["llm"]["model"]


def test_census_lists_the_notices(base_url):
    c = httpx.get(base_url + "/api/census", timeout=30).json()
    assert c.get("captured_at")
    assert httpx.get(base_url + "/api/notices", timeout=30).status_code == 200
