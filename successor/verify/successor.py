"""C2: is the successor the Reader named the coin CMC lists, with the contract the notice quotes? Pure.

verified  = exactly one CMC id, and either (a) the named new contract equals one of that id's contracts (same
            platform as the named chain, when one is named), or (b) no contract is named and identity is
            unambiguous: the notice links that coin's coinmarketcap.com page, or a unique exact name + symbol match.
refuted   = a named contract differs from CMC's, or the named successor matches no CMC id at all.
unresolved = several candidates and nothing to pick one by (repairable once by the Reader).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_CHAIN_ALIASES = {
    "ethereum": ("ethereum", "erc20", "erc-20", "eth"),
    "bnb smart chain": ("bnb", "bsc", "bep20", "bep-20", "binance smart chain"),
    "solana": ("solana", "sol", "spl"),
    "base": ("base",),
    "arbitrum": ("arbitrum",),
    "polygon": ("polygon", "matic"),
}


def addr_eq(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    a, b = a.strip(), b.strip()
    if a.lower().startswith("0x") and b.lower().startswith("0x"):
        return a.lower() == b.lower()
    return a == b


def contracts_of(info_row: dict | None) -> list[tuple[str, str]]:
    """[(address, platform name)] from contract_address[] and platform.token_address."""
    row = info_row or {}
    out: list[tuple[str, str]] = []
    for c in row.get("contract_address") or []:
        if c.get("contract_address"):
            out.append((c["contract_address"], ((c.get("platform") or {}).get("name")) or ""))
    plat = row.get("platform") or {}
    if plat.get("token_address") and not any(addr_eq(a, plat["token_address"]) for a, _ in out):
        out.append((plat["token_address"], plat.get("name") or ""))
    return out


def chain_matches(proposed: str | None, platform: str) -> bool:
    if not proposed:
        return True
    p, plat = proposed.lower().strip(), platform.lower().strip()
    if not plat:
        return False
    if p in plat or plat.split(" (")[0] in p:
        return True
    for canon, aliases in _CHAIN_ALIASES.items():
        if canon in plat and any(a == p or a in p.split() for a in aliases):
            return True
    return False


def has_contract(info_row: dict | None, addr: str | None, chain: str | None = None) -> bool:
    return any(addr_eq(a, addr) and chain_matches(chain, plat) for a, plat in contracts_of(info_row))


def linked_slugs(notice: str) -> set[str]:
    return set(re.findall(r"coinmarketcap\.com/currencies/([a-z0-9-]+)", notice or ""))


@dataclass
class C2Result:
    state: str  # verified | refuted | unresolved | not_run
    match: str | None  # "contract" | "identity: notice links its CMC page" | "identity: unique name + symbol"
    successor: dict | None
    reason: str
    candidates: list[dict] = field(default_factory=list)
    contract_quoted: bool = False

    @property
    def repairable(self) -> bool:
        """The Reader gets one repair turn for an unresolved identity, never for a contract mismatch."""
        return self.state == "unresolved" or (
            self.state == "refuted" and self.match == "no-id" and not self.contract_quoted
        )


def check_successor(
    *,
    symbol: str | None,
    name: str | None,
    new_contract: str | None,
    new_chain: str | None,
    notice: str,
    candidates: list[dict],
    infos: dict[str, dict],
    linked_ids: set[int] | None = None,
) -> C2Result:
    """candidates: CMC map rows (id, symbol, name, slug, is_active) for the named symbol, the named contract and
    the notice's linked slugs. infos: id -> /v2/cryptocurrency/info row. linked_ids: the ids CMC itself returns for
    the notice's coinmarketcap.com/currencies/<slug> links (an old slug such as "fetch" still resolves to its id)."""
    sym = (symbol or "").strip().lstrip("$").upper() or None
    nm = (name or "").strip().lower() or None
    if not sym and not nm and not new_contract:
        return C2Result("not_run", None, None, "successor not named in the notice")
    uniq = {c["id"]: c for c in candidates}
    cands = list(uniq.values())
    by_sym = [c for c in cands if sym and (c.get("symbol") or "").upper() == sym]
    by_name = [c for c in cands if nm and (c.get("name") or "").lower() == nm]
    named = {c["id"]: c for c in by_sym + by_name}
    label = sym or name or new_contract

    if new_contract:
        hits = [c for c in cands if has_contract(infos.get(str(c["id"])), new_contract, new_chain)]
        if len(hits) == 1:
            c = hits[0]
            if named and c["id"] not in named:
                return C2Result(
                    "refuted",
                    "contract",
                    c,
                    f"the quoted contract belongs to {c.get('symbol')} (CMC id {c['id']}), not to the named {label}",
                    cands,
                )
            return C2Result(
                "verified",
                "contract",
                c,
                f"quoted contract {new_contract} = CMC's contract for {c.get('symbol')} (id {c['id']})",
                cands,
            )
        if len(hits) > 1:
            return C2Result("unresolved", None, None, "the quoted contract maps to several CMC ids", hits)
        loose = [c for c in cands if has_contract(infos.get(str(c["id"])), new_contract)]
        if loose and new_chain:
            return C2Result(
                "refuted",
                "contract",
                loose[0],
                f"contract {new_contract} is on CMC, but not on the named chain {new_chain}",
                cands,
            )
        if named:
            c = next(iter(named.values()))
            theirs = ", ".join(a for a, _ in contracts_of(infos.get(str(c["id"])))) or "none listed"
            return C2Result(
                "refuted",
                "contract",
                c,
                f"quoted contract {new_contract} ≠ CMC's contract for {c.get('symbol')} ({theirs})",
                cands,
            )
        return C2Result(
            "refuted", "no-id", None, f"no CMC coin carries the quoted contract {new_contract}", cands, True
        )

    if not named:
        return C2Result("refuted", "no-id", None, f"the named successor {label} matches no CMC id", cands)
    slugs = linked_slugs(notice)
    linked = [c for c in named.values() if c.get("slug") in slugs or int(c["id"]) in (linked_ids or set())]
    if len(linked) == 1:
        c = linked[0]
        return C2Result(
            "verified",
            "identity: notice links its CMC page",
            c,
            f"{c.get('name')} ({c.get('symbol')}, id {c['id']}): the notice links its coinmarketcap.com page",
            cands,
        )
    both = [c for c in by_sym if nm and (c.get("name") or "").lower() == nm]
    if len(both) == 1:
        c = both[0]
        return C2Result(
            "verified",
            "identity: unique name + symbol",
            c,
            f"{c.get('name')} ({c.get('symbol')}) is the only CMC id with that exact name and symbol",
            cands,
        )
    if len(named) == 1 and not (sym and nm):
        c = next(iter(named.values()))
        return C2Result(
            "unresolved",
            None,
            c,
            f"only one CMC id ({c.get('symbol')}, id {c['id']}) matches, but the notice gives neither its contract "
            "nor its CMC page, and not both name and symbol",
            cands,
        )
    return C2Result(
        "unresolved",
        None,
        None,
        f"{label} collides with {len(named)} CMC ids and the notice quotes no contract to pick one",
        list(named.values()),
    )
