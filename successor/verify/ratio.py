"""Ratio at the event date (core flow). P1a: dating the event.

CMC copies `date_added` from the old id to the successor id (CLEAR shows CPOOL's 2021-10-10, measured
2026-11-22), so `date_added` cannot date a rename. A notice that links an X post carries a better clock:
X status ids are snowflakes whose top 42 bits are the post's creation time.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime

TWITTER_EPOCH_MS = 1288834974657
_STATUS = re.compile(r"(?:x|twitter)\.com/\w+/status/(\d{15,20})")


def snowflake_date(status_id: int) -> date:
    return datetime.fromtimestamp(((status_id >> 22) + TWITTER_EPOCH_MS) / 1000, UTC).date()


def announcement_dates(text: str) -> list[date]:
    """Dates of every X post linked in the text, oldest first."""
    return sorted({snowflake_date(int(m)) for m in _STATUS.findall(text or "")})
