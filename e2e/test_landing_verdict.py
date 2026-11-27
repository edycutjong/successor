"""The landing's verdict line must say what the rule says.

The lookup stream is stubbed here (page.route), so this tests the page's own logic, not CoinMarketCap: old against swap is
the story only for R8 and R9; a SWAP under R8's margin never prints as 5.0; a figure that prints as 0.0 is called equal;
every other verdict shows its own rule and reason. Each case below was a sentence the page once got wrong, or its twin.
"""

from __future__ import annotations

import json

CAPTION = "document.getElementById('h-cap').textContent.startsWith('live · lookup captured')"
MARGIN = "under the 5% margin R8 needs for SELL OLD"
R7 = "the swap window closed (2026-10-25); the old token still trades"
R6 = "CMC's data shows no market to exit through: the old token has no live market and the quoted swap deadline has passed"

# name, verdict event fields, the big figure, words the line must carry, words it must never carry
CASES = [
    ("R9 just under the margin", ("SWAP", "R9", "r", 104.97, 100.0, None), "+4.97%", MARGIN, ["5.0%"]),
    ("R9 a hair under the margin", ("SWAP", "R9", "r", 104.9999, 100.0, None), "+4.99%", MARGIN, ["5.0%"]),
    ("R9 above the swap", ("SWAP", "R9", "r", 101.5, 100.0, None), "+1.5%", MARGIN, []),
    (
        "R9 a hair above the swap",
        ("SWAP", "R9", "r", 100.03, 100.0, None),
        "0.0%",
        "worth the same",
        ["above the swap"],
    ),
    (
        "R9 a hair below the swap",
        ("SWAP", "R9", "r", 99.97, 100.0, None),
        "0.0%",
        "worth the same",
        ["worth more"],
    ),
    (
        "R9 below the swap",
        ("SWAP", "R9", "r", 97.3, 100.0, None),
        "-2.7%",
        "the swap is worth more than the old token",
        [],
    ),
    (
        "R8",
        ("SELL_OLD", "R8", "r", 115.7, 100.0, None),
        "+15.7%",
        "the old token is worth more than the swap",
        [],
    ),
    (
        "R7 with the swap worth more",
        ("SELL_OLD", "R7", R7, 90.0, 100.0, None),
        "R7",
        R7,
        ["the swap is worth more"],
    ),
    (
        "R6 with swap and tracker values",
        ("WRITE_OFF", "R6", R6, None, 100.0, 500.0),
        "R6",
        R6,
        ["worth swapped"],
    ),
    (
        "R9 on a dead old market",
        ("SWAP", "R9", "r", None, 544.71, 5932.28),
        "$544.71",
        "not the tracker's $5,932.28",
        [],
    ),
    ("R10", ("NOT_VERIFIABLE", "R10", "ratio not stated", 50.0, None, None), "R10", "ratio not stated", []),
]


def _stream(verdict, rule, reason, sell, swap, tracker) -> str:
    events = [
        {"type": "step", "step": "resolve", "chosen": {"symbol": "TST"}, "t_ms": 1},
        {"type": "step", "step": "notice", "notice": "Old (TST) swaps to New (NEW).", "t_ms": 2},
        {
            "type": "verdict",
            "verdict": verdict,
            "rule_id": rule,
            "reason": reason,
            "qty": 10000,
            "value_sell_old_usd": sell,
            "value_swap_usd": swap,
            "tracker_value_usd": tracker,
            "captured_at": "2026-11-27T19:00:00Z",
            "credits_used": 8,
            "t_ms": 400,
        },
    ]
    return "".join(json.dumps(e) + "\n" for e in events)


def _answer(body: str):
    def handler(route) -> None:  # one parameter: Playwright passes the request too when a handler takes two
        route.fulfill(status=200, content_type="application/x-ndjson", body=body)

    return handler


def test_the_landing_says_what_the_rule_says(browser_ctx, base_url):
    for name, fields, big, say, never in CASES:
        ctx = browser_ctx.new_context(viewport={"width": 1280, "height": 900}, reduced_motion="reduce")
        pg = ctx.new_page()
        errors: list[str] = []
        pg.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
        pg.route("**/api/lookup**", _answer(_stream(*fields)))
        pg.goto(base_url + "/about")
        pg.click('.runs button[data-q="DAI"]')
        pg.wait_for_function(CAPTION)
        line = pg.inner_text("#h-big") + " | " + pg.inner_text("#h-say") + " | " + pg.inner_text("#h-vals")
        assert pg.inner_text("#h-big") == big, f"{name}: {line}"
        assert say in line, f"{name}: {line}"
        assert not [w for w in never if w in line], f"{name}: {line}"
        assert not errors, f"{name}: {errors}"
        ctx.close()
