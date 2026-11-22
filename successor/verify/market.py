"""C5 market state: is there a real market to exit through? Pure functions over CMC rows.

alive = volume_24h > 0 AND at least one spot pair with outlier_detected == 0 and no exclusions. A flat 30-day
        price (a peg) stays alive when valid pairs back it, with a note.
dead  = volume_24h == 0, or no valid pair, or a flat price with no pair check. A dead price never enters a ratio
        or a sell figure.
unknown = CMC returned no price or no volume field (missing is not $0), or the old contract has no CMC id of its
        own (merged page, decided by the caller).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import median


def usd(row: dict | list | None) -> dict:
    row = row[0] if isinstance(row, list) and row else row
    return (((row or {}).get("quote") or {}).get("USD")) or {}


def daily_closes(hist_data: dict | None) -> list[dict]:
    """[{date, price, volume_24h}] from a quotes/historical `data` object (id-keyed or flat)."""
    if not hist_data:
        return []
    if "quotes" not in hist_data and len(hist_data) == 1:
        hist_data = next(iter(hist_data.values()))
    if isinstance(hist_data, list):
        hist_data = hist_data[0] if hist_data else {}
    out = []
    for q in hist_data.get("quotes") or []:
        u = (q.get("quote") or {}).get("USD") or {}
        if u.get("price") is not None:
            out.append(
                {
                    "date": str(q.get("timestamp", ""))[:10],
                    "price": u["price"],
                    "volume_24h": u.get("volume_24h"),
                }
            )
    return out


def is_flat(closes: list[dict]) -> bool | None:
    """(max - min) / median < 0.1% over >= 25 daily closes. None when there are too few closes to say."""
    prices = [c["price"] for c in closes if c.get("price")]
    if len(prices) < 25:
        return None
    med = median(prices)
    return med > 0 and (max(prices) - min(prices)) / med < 0.001


@dataclass
class Market:
    state: str  # alive | dead | unknown
    reason: str
    price: float | None = None
    volume_24h: float | None = None
    last_updated: str | None = None
    top_venue: str | None = None
    valid_pairs: int | None = None
    pairs_checked: bool = True
    flat: bool | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None and v != []}


def _num(v) -> float | None:
    """Finite non-negative numbers only; anything else counts as missing."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) and f >= 0 else None


def assess(
    quote_row: dict | None, pairs_data: dict | None, closes: list[dict], *, pairs_denied=False
) -> Market:
    u = usd(quote_row)
    price, vol = _num(u.get("price")), _num(u.get("volume_24h"))
    m = Market("dead", "", price=price, volume_24h=vol, last_updated=u.get("last_updated"))
    m.flat = is_flat(closes)
    if pairs_denied or pairs_data is None:
        m.pairs_checked = False
        m.notes.append("spot pairs not checked: key plan")
    else:
        pairs = [
            p
            for p in pairs_data.get("market_pairs") or []
            if p.get("category", "spot") == "spot"
            and not p.get("outlier_detected")
            and not p.get("exclusions")
        ]
        m.valid_pairs = len(pairs)
        if pairs:
            top = max(pairs, key=lambda p: ((p.get("quote") or {}).get("USD") or {}).get("volume_24h") or 0)
            m.top_venue = (top.get("exchange") or {}).get("name")
    if vol is None or price is None:
        # a missing field is not an observed $0 (a2a r03): unknown keeps R6 (WRITE OFF) and R9 (SWAP) off
        m.state = "unknown"
        m.reason = "CMC returned no " + ("24 h volume" if vol is None else "price") + " for it"
    elif not vol:
        m.reason = "24 h volume is $0: CMC's price for it is stale"
    elif m.pairs_checked and not m.valid_pairs:
        m.reason = "no spot pair CMC counts (every pair is an outlier or excluded)"
    elif m.flat and not m.valid_pairs:
        # a flat print counts as stale only when no valid spot pair backs it; a peg that trades on counted
        # pairs is a live market (a2a r03: a traded stablecoin must never reach R6)
        m.reason = "price flat over 30 days (CMC carries a stale price)"
    elif price <= 0:
        m.reason = "no price"
    else:
        if m.flat:
            m.notes.append(
                "price flat over 30 days (a peg); counted as live because valid spot pairs trade it"
            )
        m.state = "alive"
        venue = f", top venue {m.top_venue}" if m.top_venue else ""
        m.reason = f"trades ${vol:,.0f} / 24 h{venue}"
    return m
