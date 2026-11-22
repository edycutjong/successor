"""Layout holds at phone, tablet and desktop widths: no sideways scroll, the form and chips stay usable."""

from __future__ import annotations

import pytest

SIZES = [("phone", 375, 780), ("tablet", 768, 1024), ("desktop", 1440, 900)]


@pytest.mark.parametrize("name,w,h", SIZES)
def test_no_horizontal_overflow(browser_ctx, base_url, name, w, h):
    ctx = browser_ctx.new_context(viewport={"width": w, "height": h})
    pg = ctx.new_page()
    pg.goto(base_url + "/")
    pg.wait_for_selector("#chips button")
    over = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert over <= 1, f"{name}: page scrolls sideways by {over}px"
    assert pg.locator("#q").is_visible() and pg.locator("#go").is_visible()
    ctx.close()
