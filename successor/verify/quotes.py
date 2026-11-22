"""C3 verbatim quotes and C3b ratio binding. Pure functions, no I/O.

C3: a proposed field is kept only if its evidence quote is a substring of the text it claims to come from
(whitespace-normalised). Anything else is dropped and listed as unstated, so the Reader cannot launder a
value it did not read.

C3b: a quoted ratio counts only if the quote itself contains a ratio expression whose sides map to the old
and new coin and whose parse reproduces the proposed `ratio_new_per_old`. "1:1" needs no direction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

FIELD_NAMES = (
    "successor_name",
    "successor_symbol",
    "new_chain",
    "new_contract",
    "old_contract",
    "ratio_new_per_old",
    "effective_date",
    "deadline",
)


def norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").replace(" ", " ")).strip()


def _in_text(quote: str, text: str) -> bool:
    return bool(quote) and norm(quote).lower() in norm(text).lower()


def _value_in_quote(name: str, value: object, quote: str) -> bool:
    """A contract or symbol value must itself appear in its quote (stops a true quote carrying a false value)."""
    if value is None:
        return True
    q = norm(quote).lower()
    if name in ("new_contract", "old_contract", "successor_symbol"):
        return str(value).lower().lstrip("$") in q
    return True


@dataclass
class C3Result:
    kept: dict[str, dict] = field(default_factory=dict)  # name -> {value, evidence_quote, source}
    dropped: dict[str, str] = field(default_factory=dict)  # name -> reason
    unstated: list[str] = field(default_factory=list)

    def value(self, name: str):
        f = self.kept.get(name)
        return f["value"] if f else None

    def quote(self, name: str) -> str | None:
        f = self.kept.get(name)
        return f["evidence_quote"] if f else None


def check_quotes(proposal: dict, sources: dict[str, str]) -> C3Result:
    """proposal: Proposal.model_dump(); sources: {"notice": text, "announcement": text-or-empty}."""
    out = C3Result()
    for name in FIELD_NAMES:
        f = proposal.get(name) or {}
        value, quote, src = f.get("value"), f.get("evidence_quote"), f.get("source", "notice")
        if value in (None, ""):
            out.unstated.append(name)
            continue
        if not quote:
            out.dropped[name] = "no evidence quote"
        elif not _in_text(quote, sources.get(src) or ""):
            out.dropped[name] = f"quote not found verbatim in the {src}"
        elif not _value_in_quote(name, value, quote):
            out.dropped[name] = "value does not appear inside its own quote"
        else:
            out.kept[name] = {"value": value, "evidence_quote": quote, "source": src}
            continue
        out.unstated.append(name)
    return out


# --- C3b ratio binding --------------------------------------------------------------------------------

_NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def _names_re(names: list[str]) -> str:
    alts = sorted({n.strip().lstrip("$") for n in names if n and n.strip()}, key=len, reverse=True)
    return "(?:" + "|".join(re.escape(a) for a in alts) + ")" if alts else r"(?!x)x"


@dataclass
class Binding:
    state: str  # "bound" | "unbound"
    parsed: float | None
    reason: str


def bind_ratio(
    quote: str | None, proposed: float | None, old_names: list[str], new_names: list[str]
) -> Binding:
    if quote is None or proposed is None:
        return Binding("unbound", None, "ratio not quoted")
    q = norm(quote)
    old, new = _names_re(old_names), _names_re(new_names)
    sep = r"\s*(?:=|:|to|for|into|→|->|converts? into|(?:will be )?(?:swapped|exchanged|converted) (?:for|into|to))\s*"
    cands: list[tuple[float, str]] = []
    # "1 OLD = N NEW" / "N NEW for 1 OLD" (direction from the names)
    for m in re.finditer(rf"{_NUM}\s*\$?({old}|{new})\b{sep}{_NUM}\s*\$?({old}|{new})\b", q, re.I):
        a, sa, b, sb = _num(m[1]), m[2], _num(m[3]), m[4]
        a_old = re.fullmatch(old, sa, re.I) is not None
        b_new = re.fullmatch(new, sb, re.I) is not None
        if a_old and b_new and a > 0:
            cands.append((b / a, m[0]))
        elif not a_old and not b_new and b > 0:
            cands.append((a / b, m[0]))
    # "N NEW per OLD" / "N NEW per 1 OLD"
    for m in re.finditer(rf"{_NUM}\s*\$?{new}\b\s*(?:per|for each|for every)\s*(?:1\s*)?\$?{old}\b", q, re.I):
        cands.append((_num(m[1]), m[0]))
    # bare "a:b": only 1:1 is direction-free
    for m in re.finditer(rf"(?<![\d.]){_NUM}\s*:\s*{_NUM}(?![\d.])", q):
        a, b = _num(m[1]), _num(m[2])
        if a == b and a > 0:
            cands.append((1.0, m[0]))
    if not cands:
        if re.search(rf"(?<![\d.]){_NUM}\s*:\s*{_NUM}", q):
            return Binding("unbound", None, "ratio quoted without a direction (which side is old?)")
        return Binding("unbound", None, "no ratio expression in the quote")
    for val, text in cands:
        if abs(val - float(proposed)) <= 1e-6 * max(1.0, abs(val)):
            return Binding("bound", val, f'"{text}" gives {val:g} new per old')
    val, text = cands[0]
    return Binding(
        "unbound", val, f'"{text}" gives {val:g} new per old, the Reader proposed {float(proposed):g}'
    )


def parse_iso_date(value: object) -> date | None:
    """The Reader is asked for ISO dates; anything else counts as not stated (never guessed)."""
    if not isinstance(value, str):
        return None
    m = re.fullmatch(r"\s*(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?", value)
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None
