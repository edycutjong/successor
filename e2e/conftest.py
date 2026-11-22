"""Browser tests against a running Successor. Default target is the live URL; override with E2E_BASE_URL.

These hit the real product (real CMC calls, cached Reader reads). They never use fresh=1, so they cost no Qwen calls.
"""

from __future__ import annotations

import os

import pytest

BASE = os.environ.get("E2E_BASE_URL", "https://successor.edycu.dev").rstrip("/")
VERDICTS = {"SWAP", "SELL_OLD", "WRITE_OFF", "NOT_VERIFIABLE", "NOTHING_TO_DO"}


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
    pg = ctx.new_page()
    pg.set_default_timeout(75_000)
    yield pg
    ctx.close()
