"""Ratio at the event date (core flow). P1a: dating the event.

CMC copies `date_added` from the old id to the successor id (CLEAR shows CPOOL's 2021-10-10, measured
2026-11-22), so `date_added` cannot date a rename. A notice that links an X post carries a better clock:
X status ids are snowflakes whose top 42 bits are the post's creation time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

TWITTER_EPOCH_MS = 1288834974657
_STATUS = re.compile(r"(?:x|twitter)\.com/\w+/status/(\d{15,20})")


def snowflake_date(status_id: int) -> date:
    return datetime.fromtimestamp(((status_id >> 22) + TWITTER_EPOCH_MS) / 1000, UTC).date()


def announcement_dates(text: str) -> list[date]:
    """Dates of every X post linked in the text, oldest first."""
    return sorted({snowflake_date(int(m)) for m in _STATUS.findall(text or "")})


# --- C4: ratio state P / Q / none (pure) ---------------------------------------------------------------

TOL = 0.05


@dataclass
class EventDate:
    day: date | None
    source: str  # "quoted (notice)" | "quoted (announcement)" | "X post date, code-derived" | "≈ successor listing date…"


def pick_event_date(
    quoted: date | None,
    quoted_source: str | None,
    notice: str,
    old_date_added: str | None,
    new_date_added: str | None,
) -> EventDate:
    if quoted:
        return EventDate(quoted, f"quoted ({quoted_source or 'notice'})")
    posts = announcement_dates(notice)
    if posts:
        return EventDate(posts[0], "date of the X post the notice links, code-derived")
    if old_date_added and new_date_added and new_date_added[:10] > old_date_added[:10]:
        return EventDate(
            date.fromisoformat(new_date_added[:10]), "≈ successor listing date (CMC date_added), code-derived"
        )
    return EventDate(
        None, "no event date: none quoted, no dated post, successor not listed after the old token"
    )


def within(observed: float, stated: float) -> bool:
    return stated > 0 and abs(observed / stated - 1) <= TOL


@dataclass
class RatioResult:
    state: str  # P | Q | none
    route: str | None
    reason: str
    observations: list[str] = field(default_factory=list)
    event_day: str | None = None
    rows: list[str] = field(default_factory=list)


def event_date_check(
    stated: float, old_closes: list[dict], new_closes: list[dict], day: date, *, fallback_days: int = 7
) -> tuple[bool, str]:
    """Route 1: old/new daily closes within ±5% of the stated ratio on a day both legs traded (volume > 0).

    Tries the event day ±1 first. A successor whose CMC history starts later gets the first common traded
    day within `fallback_days` after the event, labelled as such."""
    old = {c["date"]: c for c in old_closes if (c.get("volume_24h") or 0) > 0 and c.get("price")}
    new = {c["date"]: c for c in new_closes if (c.get("volume_24h") or 0) > 0 and c.get("price")}
    days = [(day + timedelta(d)).isoformat() for d in (0, -1, 1)]
    label = "event day"
    common = [d for d in days if d in old and d in new]
    if not common:
        later = sorted(
            d
            for d in old.keys() & new.keys()
            if day.isoformat() < d <= (day + timedelta(fallback_days)).isoformat()
        )
        common, label = later[:1], "first common traded day after the event"
    if not common:
        return False, f"no day near {day} where both legs traded on CMC"
    d = common[0]
    implied = old[d]["price"] / new[d]["price"]
    ok = within(implied, stated)
    return ok, (
        f"{label} {d}: old/new = {implied:.6g} vs stated {stated:g} "
        f"({(implied / stated - 1) * 100:+.1f}%) → {'confirms' if ok else 'does not confirm'}"
    )


def continuity_check(stated: float, closes: list[dict], day: date) -> tuple[bool, str]:
    """Route 2 (C4b): one CMC id, stated 1:1, no day-over-day jump > 5% across the event date."""
    if stated != 1:
        return False, "continuity can only confirm a stated 1:1 (a smooth series hides an adjusted history)"
    win = [c for c in closes if abs((date.fromisoformat(c["date"]) - day).days) <= 2 and c.get("price")]
    win.sort(key=lambda c: c["date"])
    if len(win) < 3:
        return False, f"too few CMC closes around {day} to test continuity"
    # a2a r04: the series must straddle the event (a close before AND after it) on days that traded
    if not (
        any(date.fromisoformat(c["date"]) < day for c in win)
        and any(date.fromisoformat(c["date"]) > day for c in win)
    ):
        return False, f"CMC closes around {day} do not straddle the event date"
    if not all((c.get("volume_24h") or 0) > 0 for c in win):
        return False, f"a CMC close around {day} has $0 or no volume: a flat print proves no continuity"
    jumps = [abs(b["price"] / a["price"] - 1) for a, b in zip(win, win[1:], strict=False)]
    worst = max(jumps)
    return worst <= TOL, f"largest day-over-day move around {day}: {worst * 100:.1f}% (limit 5%)"


def ratio_state(
    *,
    stated: float | None,
    bound: bool,
    contracts_verified: bool,
    event_day: EventDate,
    old_closes: list[dict],
    new_closes: list[dict],
    old_alive: bool,
    new_alive: bool,
    old_price: float | None,
    new_price: float | None,
    single_id: bool,
) -> RatioResult:
    obs: list[str] = []
    if stated is None or not bound:
        if old_alive and new_alive and old_price and new_price:
            now = old_price / new_price
            if within(now, 1.0):
                obs.append(f"prices consistent with 1:1 (old/new = {now:.4f}); never used as a swap quantity")
        why = "ratio not stated" if stated is None else "ratio stated but not bound to the coins in its quote"
        return RatioResult("none", None, why, obs, event_day.day.isoformat() if event_day.day else None)
    day_txt = event_day.day.isoformat() if event_day.day else None
    # route 1: event-date check
    if event_day.day and not single_id:
        ok, msg = event_date_check(stated, old_closes, new_closes, event_day.day)
        obs.append(f"event-date check ({event_day.source}): {msg}")
        if ok:
            return RatioResult("P", "event-date", msg, obs, day_txt)
    # route 2: continuity on a merged page
    if single_id and event_day.day:
        ok, msg = continuity_check(stated, old_closes, event_day.day)
        obs.append(f"continuity (C4b): {msg}")
        if ok:
            return RatioResult("P", "continuity", msg, obs, day_txt)
    # route 3: market now
    if old_alive and new_alive and old_price and new_price:
        now = old_price / new_price
        ok = within(now, stated)
        msg = f"market now: old/new = {now:.4f} vs stated {stated:g} ({(now / stated - 1) * 100:+.1f}%)"
        obs.append(msg)
        if ok:
            return RatioResult("P", "market-now", msg, obs, day_txt)
    if contracts_verified:
        return RatioResult(
            "Q",
            "stated",
            "stated verbatim and bound, both contracts verified; not price-confirmed",
            obs,
            day_txt,
        )
    return RatioResult(
        "none", None, "stated but not price-confirmed, and the contracts are not both verified", obs, day_txt
    )
