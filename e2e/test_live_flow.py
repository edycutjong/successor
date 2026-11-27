"""The judged flow on the live URL: open, click a coin, assert a real verdict and its receipt."""

from __future__ import annotations

import re

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
    # the first screen: the board looks CPOOL up by itself on load, through /api/hero (its own rate bucket). No click:
    # this is what a judge sees before touching anything. The CPOOL chip is covered by the receipt test below.
    with page.expect_response(lambda r: "/api/hero" in r.url) as first:
        page.goto(base_url + "/")
    assert first.value.status == 200, f"/api/hero answered {first.value.status} on page load"
    page.wait_for_function(DONE)
    word, text = verdict_of(page)
    assert word in VERDICTS, f"no verdict class on #f-verdict (got {word!r}, text {text!r})"
    assert text, "verdict flaps are empty"
    assert "".join(page.locator("#f-old .flap").all_inner_texts()).strip() == "CPOOL"
    assert page.locator("#checks li").count() >= 5, "the code checks did not render"
    assert page.locator("#reason").inner_text().strip(), "verdict has no stated reason"
    assert re.search(r"captured \d{4}-\d\d-\d\dT", page.locator("#captured").inner_text())
    # verdict-agnostic: CPOOL's verdict moves with the market; NOT VERIFIABLE labels the same figure "market value, no verdict"
    assert re.search(
        r"(sell old|market value, no verdict): \$[\d,.]+", page.locator("#figures").inner_text()
    ), "no CMC-derived dollar figure"


def test_the_receipt_opens_and_names_cmc_endpoints(page, base_url):
    run_chip(page, base_url, "CPOOL")
    page.click("#receipt-btn")
    body = page.locator("body").inner_text()
    assert "pro-api.coinmarketcap.com/v" in body, "receipt shows no CMC Pro API call"
    assert re.search(r"/v\d/cryptocurrency/(info|quotes|market-pairs)", body), (
        "receipt names no CMC endpoint path"
    )


def test_agix_follows_a_link_and_reaches_a_verdict(page, base_url):
    run_chip(page, base_url, "AGIX")
    word, _ = verdict_of(page)
    assert word in VERDICTS
    trace = page.locator("#trace").inner_text().lower()
    assert "fetch" in trace or "not verifiable" in trace or "link" in trace, (
        "the trace shows neither a link read nor why not"
    )


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
    assert body["type"] == "verdict" and body["verdict"] in VERDICTS and body["rule_id"]


def test_health_reports_a_working_cmc_key_and_the_model(base_url):
    h = httpx.get(base_url + "/api/health", timeout=30).json()
    assert h["cmc"]["ok"] is True and h["llm"]["configured"] is True and h["llm"]["model"]


def test_census_lists_the_notices(base_url):
    c = httpx.get(base_url + "/api/census", timeout=30).json()
    assert c.get("captured_at")
    assert httpx.get(base_url + "/api/notices", timeout=30).status_code == 200
