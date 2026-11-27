"""Verdict rules R3–R10 (R1 no notice and R2 unresolved holding return outcomes before this runs).

Deterministic and pure: first match wins. The Reader's output reaches this function only as fields that
survived C3 (verbatim) and were checked by C2/C4/C5 against CMC rows; it has no verdict, advice or price
field of its own, so nothing it writes can choose the outcome.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

SWAP, SELL_OLD, WRITE_OFF, NOT_VERIFIABLE, NOTHING_TO_DO = (
    "SWAP",
    "SELL_OLD",
    "WRITE_OFF",
    "NOT_VERIFIABLE",
    "NOTHING_TO_DO",
)
PREMIUM = 1.05  # old trades ≥ 5% above the swap value → sell the old token
DISCOUNT = 0.95  # old trades > 5% below the swap value → the market doubts the swap
# WRITE OFF needs both of CMC's views of the old token to agree: the quote reports $0 of 24 h volume AND market-pairs
# lists less than this across unflagged spot pairs. Listed volume beside a $0 quote in this repo's captures and
# fixtures: EPS $41.75 and $51.05, REP $49.20 (dust: WRITE OFF); RZUSD $2,388 and $4,441 (a market: NOT VERIFIABLE).
# The line sits between the two groups; it is a judgment, like PREMIUM (docs/DX-REPORT.md, finding 5).
LISTED_FLOOR_USD = 100.0


@dataclass
class Facts:
    sanity_trips: list[str] = field(default_factory=list)
    same_id: bool = False
    contract_changed: bool = False
    c2: str = "not_run"  # verified | refuted | unresolved | not_run
    c2_reason: str = ""
    successor_named: bool = True
    old_market: str = "dead"  # alive | dead | unknown
    new_market: str | None = None  # alive | dead | None (successor not verified)
    ratio_state: str = "none"  # P | Q | none
    ratio_route: str | None = None
    ratio_reason: str = ""
    ratio: float | None = None
    old_price: float | None = None
    new_price: float | None = None
    deadline_quoted: bool = False
    deadline_passed: bool = False
    deadline_text: str | None = None
    ended_no_successor: bool = False
    announcement_unfetchable: bool = False
    agent_unavailable: str | None = None
    # C3: identity / quantity fields the Reader quoted but the notice does not contain (a2a r03: a dropped
    # contract must not read as "not stated" when the Reader asserted one)
    c3_dropped: list[str] = field(default_factory=list)
    # same CMC id, the Reader labelled it a swap/migration, but the notice text carries no swap signal (a2a r04)
    swap_label_only: bool = False
    # CMC's quote reports $0 of 24 h volume for the old token while market-pairs still lists counted pairs with volume
    # (market.Market.pairs_note): the old market stays "dead", and R6 says what both endpoints show (a2a r13)
    old_pairs_note: str = ""
    old_pairs_usd: float = (
        0.0  # what those pairs list between them; at LISTED_FLOOR_USD or more there is no WRITE OFF
    )


@dataclass
class Decision:
    verdict: str
    rule_id: str
    reason: str

    def as_dict(self) -> dict:
        return {"verdict": self.verdict, "rule_id": self.rule_id, "reason": self.reason}


SWAP_CRITICAL = (
    "old_contract",
    "new_contract",
    "ratio_new_per_old",
    "successor_symbol",
    "successor_name",
    "new_chain",
)


def _swap_blocked(f: Facts) -> list[str]:
    return [n for n in f.c3_dropped if n in SWAP_CRITICAL] + (["event_type"] if f.swap_label_only else [])


def _pct_under(pct: float, limit: float) -> str:
    """A percentage the rules judged to be under `limit`, printed so it never reads as meeting it.

    One decimal, as everywhere else. Where rounding would print the limit itself (4.96 -> "5.0") the figure is cut to
    two decimals instead ("4.96"), and anything that would print as "0.0" reads "less than 0.1"."""
    if pct < 0.05:
        return "less than 0.1"
    shown = f"{pct:.1f}"
    if float(shown) >= limit:
        shown = f"{min(math.floor(pct * 100) / 100, limit - 0.01):.2f}"
    return shown


def _missing(f: Facts) -> str:
    """R10: name what is missing, most fundamental first."""
    if f.agent_unavailable:
        return f"agent unavailable: {f.agent_unavailable}"
    if not f.successor_named:
        return "successor not named in the notice" + (
            "; the linked announcement was not fetchable" if f.announcement_unfetchable else ""
        )
    if f.swap_label_only and not [n for n in f.c3_dropped if n in SWAP_CRITICAL]:
        return (
            "the Reader labelled this a swap, but the notice has no swap wording, contract change or ratio, and the "
            "coin keeps one CMC id: no textual evidence of a swap"
        )
    if _swap_blocked(f):
        return (
            "C3 dropped "
            + ", ".join(n for n in f.c3_dropped if n in SWAP_CRITICAL)
            + ": the Reader proposed it without a verbatim quote that contains it,"
            " so SWAP is withheld"
        )
    if f.c2 != "verified":
        return f"successor not verified against CMC: {f.c2_reason}"
    if f.same_id and f.old_market == "unknown" and f.ratio_state != "P":
        return "merged CMC page: the old contract has no CMC id of its own, and continuity did not confirm the ratio"
    if f.old_market == "dead" and f.deadline_passed:
        return "swap window closed and the old token has no market of its own"
    if f.new_market == "unknown":
        return "CMC returned no price or volume for the successor; no swap value to compare"
    if f.new_market != "alive":
        return "successor has no live market; no swap value to compare"
    if f.ratio is None:
        return "ratio not stated" + (
            "; the linked announcement was not fetchable" if f.announcement_unfetchable else ""
        )
    if f.ratio_state == "none":
        # C3b's own reasons already name the subject ("ratio quoted without a direction", "no ratio expression in the
        # quote"); prefixing them printed "ratio ratio quoted ..."
        why = f.ratio_reason
        return why if why.startswith(("ratio ", "no ratio ")) else f"ratio {why}"
    if f.ratio_state == "Q" and f.old_market != "alive":
        return "ratio stated but not price-confirmed, and the old token has no market to compare"
    if (
        f.old_market == "alive"
        and f.old_price
        and f.new_price
        and f.old_price < f.ratio * f.new_price * DISCOUNT
    ):
        pct = (1 - f.old_price / (f.ratio * f.new_price)) * 100
        return f"old token trades {pct:.1f}% below the swap value at the stated ratio (the market doubts the swap)"
    if f.ratio_state == "Q":
        return "ratio stated but not price-confirmed"
    return "no rule matched with the checks available"


def decide(f: Facts) -> Decision:
    alive_old, alive_new = f.old_market == "alive", f.new_market == "alive"
    r = f.ratio
    if f.sanity_trips:
        return Decision(NOT_VERIFIABLE, "R3", "sanity guard: " + "; ".join(f.sanity_trips))
    if f.same_id and not f.contract_changed and f.c2 == "verified":
        return Decision(
            NOTHING_TO_DO,
            "R4",
            "the coin you hold is the successor itself (same CMC id): a rename, a ticker change or the new token; nothing to swap",
        )
    if f.c2 == "refuted":
        return Decision(NOT_VERIFIABLE, "R5", f"successor fails a check against CMC's data: {f.c2_reason}")
    new_dead = f.c2 == "verified" and f.new_market == "dead"
    if f.old_market == "dead" and (new_dead or f.deadline_passed or f.ended_no_successor):
        why = (
            "the successor has no live market either"
            if new_dead
            else f"the quoted swap deadline ({f.deadline_text}) has passed"
            if f.deadline_passed
            else "the notice states the project ended with no successor"
        )
        if f.old_pairs_usd >= LISTED_FLOOR_USD:
            # the quote says nothing trades, market-pairs lists real volume: CMC's data does not show "no market".
            # No later rule can fire here (R7 and R8 need a live old market, R9 a live successor and an open window)
            return Decision(
                NOT_VERIFIABLE,
                "R10",
                f"CMC's data does not settle whether the old token can still be sold: its quote reports $0 of 24 h "
                f"volume, but {f.old_pairs_note}. WRITE OFF needs under ${LISTED_FLOOR_USD:,.0f} of listed volume; "
                f"{why}",
            )
        lead = (
            f"CMC's quote shows no market to exit through: it reports $0 of 24 h volume for the old token "
            f"({f.old_pairs_note})"
            if f.old_pairs_note
            else "CMC's data shows no market to exit through: the old token has no live market"
        )
        return Decision(WRITE_OFF, "R6", f"{lead} and {why}. This does not rule out an issuer claim process.")
    if alive_old and f.deadline_passed:
        return Decision(
            SELL_OLD, "R7", f"the swap window closed ({f.deadline_text}); the old token still trades"
        )
    priced = (
        r is not None and r > 0 and f.old_price and f.new_price
    )  # r > 0 is upstream-guaranteed for P/Q (bind_ratio); kept so no path divides by it
    # typed copies for the arithmetic below; only read when `priced` is truthy (all three are set)
    rr, op, np_ = r or 0.0, f.old_price or 0.0, f.new_price or 0.0
    if alive_old and alive_new and f.ratio_state in ("P", "Q") and priced and op >= rr * np_ * PREMIUM:
        prem = (op / (rr * np_) - 1) * 100
        return Decision(
            SELL_OLD,
            "R8",
            f"at CMC's quotes the old token is worth {prem:.1f}% more than the {r:g}:1 swap "
            f"(old ${f.old_price:.6g} vs {r:g} × new ${f.new_price:.6g})",
        )
    discount = alive_old and priced and op < rr * np_ * DISCOUNT
    old_ok = (
        (alive_old and not discount)
        or f.old_market == "dead"
        or (f.old_market == "unknown" and f.ratio_route == "continuity")
    )
    if (
        f.c2 == "verified"
        and f.ratio_state == "P"
        and alive_new
        and old_ok
        and not f.deadline_passed
        and not _swap_blocked(f)
    ):
        window = (
            f"the swap window is open until {f.deadline_text}"
            if f.deadline_quoted
            else "the notice states no window: SWAP, if the issuer's swap is still open"
        )
        margin = ""
        if (
            alive_old and priced and op > rr * np_
        ):  # old above the swap, but under R8's margin: say why it is not SELL OLD
            need = round((PREMIUM - 1) * 100, 6)  # 5.0, not the float 5.000000000000004
            margin = (
                f"; at CMC's quotes the old token is {_pct_under((op / (rr * np_) - 1) * 100, need)}% above the swap, "
                f"under the {need:.0f}% R8 needs for SELL OLD"
            )
        return Decision(SWAP, "R9", f"ratio {r:g} price-confirmed ({f.ratio_route}); {window}{margin}")
    return Decision(NOT_VERIFIABLE, "R10", _missing(f))
