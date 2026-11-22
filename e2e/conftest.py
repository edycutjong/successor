"""Browser tests against a running Successor. Default target is the live URL; override with E2E_BASE_URL.

These hit the real product (real CMC calls, cached Reader reads). They never use fresh=1, so they cost no Qwen calls.
"""

from __future__ import annotations

import os

import httpx
import pytest

BASE = os.environ.get("E2E_BASE_URL", "https://successor.edycu.dev").rstrip("/")
# Vercel Deployment Protection bypass for CI previews (header only, never sent to other hosts)
BYPASS = os.environ.get("E2E_BYPASS_SECRET", "")
VERDICTS = {"SWAP", "SELL_OLD", "WRITE_OFF", "NOT_VERIFIABLE", "NOTHING_TO_DO"}


if BYPASS:
    _build_request = httpx.Client.build_request

    def _with_bypass(self, method, url, *args, **kwargs):
        req = _build_request(self, method, url, *args, **kwargs)
        if str(req.url).startswith(BASE):
            req.headers["x-vercel-protection-bypass"] = BYPASS
        return req

    httpx.Client.build_request = _with_bypass  # type: ignore[method-assign]


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE


@pytest.fixture(scope="session")
def browser_ctx():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(browser_ctx):
    ctx = browser_ctx.new_context(viewport={"width": 1280, "height": 900})
    if BYPASS:
        ctx.route(
            f"{BASE}/**",
            lambda route: route.continue_(
                headers={**route.request.headers, "x-vercel-protection-bypass": BYPASS}
            ),
        )
    pg = ctx.new_page()
    pg.set_default_timeout(75_000)
    yield pg
    ctx.close()
