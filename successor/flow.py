"""Lookup orchestrator: one stream of trace events ending in a Verdict (or an outcome / error, never both).

resolve (C1) → notice → Reader proposes (cache or live, ≤3 LLM calls) → C3 verbatim → C2 successor (one
identity repair turn) → quotes → C5 markets + C6 price integrity → C4 ratio → verdict rules R3–R10.
The Reader never sees prices and has no verdict field; every decision below is code over CMC rows.
Shared by /api/lookup and the CLI. CMC, the LLM, the link fetcher and the clock are injectable so the eval
harness can replay recorded runs offline.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from successor.agent import reader as rd
from successor.agent.fetch_link import allowed_hosts, follow_link
from successor.cmc import CmcClient, LookupDeadline
from successor.receipt import build as build_receipt
from successor.receipt import call_id
from successor.verify import market as mk
from successor.verify import ratio as rt
from successor.verify import sanity
from successor.verify.quotes import bind_ratio, check_quotes, parse_iso_date
from successor.verify.resolve import coin_ref, pick_holding
from successor.verify.successor import C2Result, addr_eq, check_successor, has_contract, linked_slugs
from successor.verify.verdict import SWAP_CRITICAL, Facts, decide

CREDIT_FLOOR = 5_000
LOOKUP_BUDGET_S = 52.0  # Vercel maxDuration is 60 s (vercel.json); 8 s margin for cold start + last event
POST_READER_S = 10.0
DEADLINE_GRACE_S = 3.0  # hard cancel at 55 s, still inside maxDuration 60
SWAP_WORDS = re.compile(r"\bswap|migrat|redenominat|new contract|/token/|/address/|contract address", re.I)
_credit_cache: dict[str, Any] = {}


class FlowError(Exception):
    def __init__(self, step: str, message: str, http_status: int | None = None):
        super().__init__(message)
        self.step, self.message, self.http_status = step, message, http_status


def _rid(cmc: CmcClient) -> str:
    return call_id(len(cmc.calls) - 1)


def _need(cmc: CmcClient, resp, step: str):
    if not resp.ok:
        raise FlowError(
            step, resp.status.get("error_message") or f"HTTP {resp.http_status}", resp.http_status
        )
    return resp


def _is_contract(q: str) -> bool:
    return (
        q.lower().startswith("0x") and len(q) >= 40 or bool(re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", q))
    )


def _map_rows(data: Any) -> list[dict]:
    return [coin_ref(x) for x in data or []]


def _info_as_cand(row: dict) -> dict:
    return {
        "id": row["id"],
        "symbol": row.get("symbol"),
        "name": row.get("name"),
        "slug": row.get("slug"),
        "is_active": 1 if (row.get("status") or "active") == "active" else 0,
    }


def dropped_contracts(prev, cur) -> list[str]:
    """Contracts a previous proposal kept (C3) that a resubmit drops or changes."""
    if prev is None:
        return []
    return [
        k
        for k in ("new_contract", "old_contract")
        if prev.value(k) and not addr_eq(str(prev.value(k)), str(cur.value(k) or ""))
    ]


def _assess(rp, row: dict, closes: list[dict]) -> mk.Market:
    """C5 from a market-pairs response: only a plan denial (403 / 1006) falls back to volume + flatness."""
    denied = rp.http_status == 403 or rp.status.get("error_code") == 1006
    if not rp.ok and not denied:
        return mk.Market("unknown", f"spot pairs unavailable (HTTP {rp.http_status}): market not assessed")
    return mk.assess(row, rp.data if rp.ok else None, closes, pairs_denied=denied)


def _check(cid: str, label: str, state: str, value: str, rows: list[str]) -> dict:
    return {"id": cid, "label": label, "state": state, "value": value, "rows": rows}


async def _credits_ok(cmc: CmcClient) -> tuple[bool, int | None]:
    hit = _credit_cache.get("v")
    if hit and time.monotonic() - hit[0] < 600:
        return hit[1] >= CREDIT_FLOOR, hit[1]
    r = await cmc.key_info()
    cmc.calls.pop()  # key/info is a health probe, not a verdict row
    left = (((r.data or {}).get("usage") or {}).get("current_month") or {}).get("credits_left")
    if not isinstance(left, int):
        # unknown is not cached (a2a r03): the next lookup probes again. The lookup itself proceeds: CMC
        # refuses calls once credits run out, and that refusal surfaces as a handled error event
        return True, None
    _credit_cache["v"] = (time.monotonic(), left)
    return left >= CREDIT_FLOOR, left


async def _history(cmc: CmcClient, cid: int, start: date, end: date) -> tuple[list[dict], str | None]:
    r = await cmc.quotes_historical(cid, start.isoformat(), end.isoformat())
    if not r.ok:
        return [], None
    return mk.daily_closes(r.data), _rid(cmc)


async def lookup_stream(
    q: str,
    qty: float = 1.0,
    cmc_id: int | None = None,
    fresh: bool = False,
    *,
    cmc: CmcClient | None = None,
    now: datetime | None = None,
    chat: rd.Chat | None = None,
    fetch: rd.Fetch | None = None,
    use_cache: bool = True,
    write_cache: bool = True,
    guard_credits: bool = True,
    extraction: dict | None = None,
) -> AsyncIterator[dict[str, Any]]:
    t0 = time.perf_counter()

    def ev(kind: str, **data: Any) -> dict[str, Any]:
        return {"type": kind, "t_ms": round((time.perf_counter() - t0) * 1000), **data}

    own = cmc is None
    client = cmc or CmcClient()
    if own:
        # one deadline for the whole lookup, inside Vercel's maxDuration 60 (a2a r03): CMC retries and the Reader
        # budget shrink to fit, so the stream always ends with a verdict or a handled error event
        client.deadline = time.monotonic() + LOOKUP_BUDGET_S
        await client.__aenter__()
    try:
        agen = _run(
            client,
            q,
            qty,
            cmc_id,
            fresh,
            now,
            chat,
            fetch,
            use_cache,
            write_cache,
            guard_credits,
            extraction,
            ev,
        )
        try:
            while True:
                dl = getattr(client, "deadline", None)
                try:
                    if dl is None:
                        e = await agen.__anext__()
                    else:
                        # a2a r04: httpx timeouts bound each read, not a response that trickles in; this cancels
                        # whatever is awaited (CMC, Qwen, a fetched page) once the lookup is out of time
                        cm = asyncio.timeout(max(0.01, dl + DEADLINE_GRACE_S - time.monotonic()))
                        try:
                            async with cm:
                                e = await agen.__anext__()
                        except TimeoutError:
                            if cm.expired():
                                raise LookupDeadline("hard cancel at the lookup deadline") from None
                            raise
                except StopAsyncIteration:
                    break
                yield e
        finally:
            await agen.aclose()
    except LookupDeadline:  # only the lookup budget, never an unrelated socket TimeoutError (P1d QA r2)
        yield ev(
            "error",
            step="deadline",
            error=f"the lookup ran past its {LOOKUP_BUDGET_S:.0f} s budget; no verdict is shown",
            http_status=504,
        )
    except FlowError as exc:
        yield ev("error", step=exc.step, error=exc.message, http_status=exc.http_status)
    except httpx.HTTPError as exc:
        yield ev("error", step="network", error=f"{type(exc).__name__}: {exc}"[:300], http_status=None)
    except RuntimeError as exc:  # missing key etc.
        yield ev("error", step="config", error=str(exc), http_status=None)
    except Exception as exc:  # noqa: BLE001 - last resort: the stream must end with a terminal event (a2a r03)
        yield ev("error", step="internal", error=f"{type(exc).__name__}: {exc}"[:300], http_status=None)
    finally:
        if own:
            await client.__aexit__(None, None, None)


async def _run(
    cmc, q, qty, cmc_id, fresh, now, chat, fetch, use_cache, write_cache, guard_credits, extraction, ev
):
    now = now or datetime.now(UTC)
    q = q.strip()
    checks: list[dict] = []

    if guard_credits:
        ok, left = await _credits_ok(cmc)
        if not ok:
            raise FlowError("credits", f"CMC credits low ({left} left): lookups paused", 429)

    # --- C1 resolve the holding -------------------------------------------------------------------
    if _is_contract(q):
        r = _need(cmc, await cmc.info(address=q.lower() if q.lower().startswith("0x") else q), "resolve")
        cands = [_info_as_cand(v) for v in (r.data or {}).values()]
    else:
        cands = []
        sym = q.lstrip("$").upper()
        if re.fullmatch(r"[A-Z0-9]{1,20}", sym):
            r = await cmc.map(symbol=sym)
            if (
                not r.ok and r.http_status != 400
            ):  # CMC answers 400 for an unknown symbol; fall through to slug
                _need(cmc, r, "resolve")
            cands = _map_rows(r.data) if r.ok else []
        slug = re.sub(r"[^a-z0-9]+", "-", q.lower()).strip("-")
        if not cands and slug:  # a slug or a name ("clearpool", "Maker"); CMC 400s on unknown slugs
            r = await cmc.info(slugs=[slug])
            cands = [_info_as_cand(v) for v in (r.data or {}).values()] if r.ok else []
    c1 = pick_holding(q, cands, cmc_id)
    rows_c1 = [_rid(cmc)]
    yield ev(
        "step", step="resolve", check="C1", query=q, candidates=cands[:8], chosen=c1.coin, reason=c1.reason
    )
    if not c1.coin:
        if c1.candidates:
            yield ev(
                "outcome", outcome="pick_one", rule_id="R2", candidates=c1.candidates[:12], message=c1.reason
            )
        else:
            yield ev("outcome", outcome="not_found", rule_id="R2", candidates=[], message=c1.reason)
        return
    hold = c1.coin
    checks.append(
        _check("C1", "holding resolved", "verified", f"{hold['symbol']} · CMC id {hold['id']}", rows_c1)
    )

    # --- notice -----------------------------------------------------------------------------------
    r = _need(cmc, await cmc.info(ids=[hold["id"]]), "notice")
    hrow = (r.data or {}).get(str(hold["id"])) or {}
    notice = (hrow.get("notice") or "").strip()
    rows_notice = [_rid(cmc)]
    yield ev(
        "step",
        step="notice",
        coin=coin_ref({**hold, "name": hrow.get("name") or hold.get("name")}),
        has_notice=bool(notice),
        notice=notice,
        notice_sha256=rd.notice_sha(notice) if notice else None,
        rows=rows_notice,
    )
    if not notice:
        yield ev(
            "outcome",
            outcome="no_notice",
            rule_id="R1",
            message="CMC states no migration for this coin",
            holding=coin_ref(hold),
        )
        return

    # coins the notice links on coinmarketcap.com: successor candidates and link allow-list sources
    slugs = sorted(linked_slugs(notice) - {hrow.get("slug")})
    linked_rows: list[dict] = []
    if slugs:
        rl = await cmc.info(slugs=slugs[:5])
        if rl.ok:
            linked_rows = list((rl.data or {}).values())
    hosts = allowed_hosts([hrow, *linked_rows])

    async def _fetch(url: str) -> dict:
        return await follow_link(url, notice, hosts)

    # --- Reader -----------------------------------------------------------------------------------
    label = f"{hrow.get('name')} ({hrow.get('symbol')})"
    cached = extraction or (rd.load_cached(hold["id"], notice) if use_cache and not fresh else None)
    if cached and cached.get("notice_sha256") not in (None, rd.notice_sha(notice)):
        cached = None  # a recorded extraction is only ever used for the exact notice it read
    session: rd.ReaderSession | None = None
    if cached:
        proposals, fetches, llm = cached["proposals"], cached.get("fetches", []), cached.get("llm", [])
        yield ev(
            "step",
            step="reader",
            cache="hit",
            model=(llm[0]["model"] if llm else None),
            recorded_at=cached.get("created_at"),
            llm_calls=len(llm),
            note=f"recorded extraction of this exact notice ({rd.cache_key(hold['id'], notice)})",
        )
        for f in fetches:  # the links the agent followed when it read this notice, labelled as recorded
            yield ev(
                "step",
                step="follow_link",
                url=f.get("url"),
                ok=True,
                host=f.get("host"),
                chars=len(f.get("text") or ""),
                sha256=f.get("sha256"),
                fetched_at=f.get("fetched_at"),
                recorded=True,
            )
        for le in cached.get("link_errors") or []:
            yield ev(
                "step", step="follow_link", url=le.get("url"), ok=False, error=le.get("error"), recorded=True
            )
    else:
        budget = rd.READER_BUDGET_S
        if getattr(cmc, "deadline", None) is not None:
            # leave ~10 s for the CMC calls after the Reader (history, pairs) inside the lookup deadline
            # (a2a r04) no 5 s floor: with no time left the Reader times out at once and ends R10 with its receipt
            budget = max(1.0, min(budget, cmc.deadline - time.monotonic() - POST_READER_S))
        session = rd.ReaderSession(notice, label, fetch or _fetch, chat=chat, budget_s=budget)
        yield ev("step", step="reader", cache="miss", model=session.model, live=True, fresh=fresh)
        try:
            await session.propose()
        except rd.ReaderError as exc:
            for e in session.events:
                yield ev("step", **e)
            yield from_reader_failure(ev, exc, hold, session, checks, cmc)
            return
        proposals, fetches, llm = session.proposals, session.fetches, session.calls
        for e in session.events:
            yield ev("step", **e)
        session.events.clear()

    # --- verify each proposal (the second exists only after a repair turn) ------------------------
    c2: C2Result | None = None
    c3 = None
    prev_c3 = None
    infos: dict[str, dict] = {str(hold["id"]): hrow}
    i = 0
    while True:
        prop = proposals[i]
        sources = {"notice": notice, "announcement": "\n\n".join(f["text"] for f in fetches)}
        c3 = check_quotes(prop, sources)
        yield ev(
            "step",
            step="proposal",
            n=i + 1,
            event_type=prop.get("event_type"),
            fields={k: v["value"] for k, v in c3.kept.items()},
            quotes={k: v["evidence_quote"] for k, v in c3.kept.items()},
            sources={k: v["source"] for k, v in c3.kept.items()},
            dropped=c3.dropped,
            unstated=c3.unstated,
            check="C3",
        )
        c2, rows_c2 = await _verify_successor(cmc, c3, notice, hold, hrow, linked_rows, infos)
        dropped = dropped_contracts(prev_c3, c3)
        if dropped:  # a repair may add evidence, never drop or change a contract the notice quotes
            c2 = C2Result(
                "refuted",
                "contract",
                None,
                f"the resubmitted proposal dropped or changed the quoted {', '.join(dropped)}",
            )
        prev_c3 = c3
        yield ev(
            "step",
            step="successor",
            check="C2",
            n=i + 1,
            state=c2.state,
            match=c2.match,
            successor=c2.successor,
            reason=c2.reason,
            rows=rows_c2,
        )
        if c2.repairable and i + 1 < len(proposals):
            yield ev("step", step="refute", n=i + 1, reason=c2.reason, sent_to_reader=True)
            i += 1
            continue
        if c2.repairable and session is not None and len(session.calls) < rd.MAX_CALLS:
            yield ev("step", step="refute", n=i + 1, reason=c2.reason, sent_to_reader=True)
            try:
                await session.repair(c2.reason)
            except rd.ReaderError as exc:
                for e in session.events:
                    yield ev("step", **e)
                yield ev("step", step="repair", ok=False, error=str(exc))
                break
            for e in session.events:
                yield ev("step", **e)
            session.events.clear()
            fetches, llm = session.fetches, session.calls
            i += 1
            continue
        break
    proposal = proposals[i]

    if session is not None and write_cache and session.proposals:
        try:
            rd.save_cache(
                hold["id"],
                notice,
                {
                    "cmc_id": hold["id"],
                    "symbol": hold["symbol"],
                    "notice_sha256": rd.notice_sha(notice),
                    "notice": notice,
                    "proposals": session.proposals,
                    "fetches": session.fetches,
                    "link_errors": session.link_errors,
                    "llm": session.calls,
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                },
                repo=not fresh,
            )
        except OSError:
            pass

    # the lamp follows the same critical set as R9 (a2a r04): a dropped date is listed, not shown as refuted
    c3_state = (
        "refuted" if any(n in SWAP_CRITICAL for n in c3.dropped) else "stale" if c3.dropped else "verified"
    )
    checks.append(
        _check(
            "C3",
            "every kept field is quoted verbatim",
            c3_state,
            f"{len(c3.kept)} kept, {len(c3.dropped)} dropped"
            + (f" ({', '.join(c3.dropped)})" if c3.dropped else ""),
            rows_notice,
        )
    )
    checks.append(
        _check(
            "C2",
            "successor and contract match CMC",
            {"verified": "verified", "refuted": "refuted"}.get(c2.state, "not_run"),
            c2.reason,
            rows_c2,
        )
    )

    # --- facts for the rules ----------------------------------------------------------------------
    succ = c2.successor if c2.state == "verified" else None
    if c2.state == "refuted" and c2.match == "contract":
        succ = None
    same_id = bool(succ and int(succ["id"]) == int(hold["id"]))
    old_c, new_c = c3.value("old_contract"), c3.value("new_contract")
    try:
        r_quoted = float(c3.value("ratio_new_per_old")) if c3.value("ratio_new_per_old") is not None else None
    except (TypeError, ValueError):
        r_quoted = None
    text_changed = bool(
        same_id
        and (
            (old_c and new_c and not addr_eq(str(old_c), str(new_c)))
            or (r_quoted is not None and r_quoted != 1)
            # swap / migration wording or a token link in the notice keeps R4 (NOTHING_TO_DO) off
            or SWAP_WORDS.search(notice) is not None
        )
    )
    # the LLM's event_type alone never makes a swap a rename (keeps R4 off), and never selects SWAP either
    # (a2a r04): a label with no textual signal blocks R9 and ends NOT VERIFIABLE
    swap_label_only = bool(
        same_id
        and not text_changed
        and proposal.get("event_type") in ("contract_swap", "chain_migration", "token_swap", "merger")
    )
    contract_changed = text_changed or swap_label_only
    if contract_changed and old_c and new_c and has_contract(hrow, new_c):
        # the coin looked up carries the new contract: if the old contract is a CMC id of its own, the holder
        # already holds the successor (someone entering CLEAR); otherwise this is a merged page (BDX)
        ra = await cmc.info(address=str(old_c).lower() if str(old_c).lower().startswith("0x") else str(old_c))
        if ra.ok and any(int(k) != int(hold["id"]) for k in (ra.data or {})):
            contract_changed = False
    old_verified = bool(old_c) and has_contract(hrow, old_c)
    if old_c and not old_verified and not same_id and c2.state == "verified":
        c2 = C2Result(
            "refuted",
            "contract",
            None,
            f"the quoted old contract {old_c} is not among CMC's contracts for {hold['symbol']}",
        )
        checks[-1] = _check("C2", "successor and contract match CMC", "refuted", c2.reason, rows_c2)
        succ = None
    new_verified = c2.state == "verified" and c2.match == "contract"

    ids = [hold["id"]] + ([succ["id"]] if succ and not same_id else [])
    rq = _need(cmc, await cmc.quotes_latest(ids), "quotes")
    rows_q = [_rid(cmc)]
    qd = rq.data or {}
    old_row = qd.get(str(hold["id"]))
    new_row = qd.get(str(succ["id"])) if succ else None
    old_row1 = old_row[0] if isinstance(old_row, list) and old_row else old_row or {}
    new_row1 = new_row[0] if isinstance(new_row, list) and new_row else new_row or {}

    start30 = (now - timedelta(days=31)).date()
    old_closes, r_oh = await _history(cmc, hold["id"], start30, now.date())
    new_closes, r_nh = ([], None)
    if succ and not same_id:
        new_closes, r_nh = await _history(cmc, succ["id"], start30, now.date())

    # C5 old market
    if same_id and contract_changed:
        old_m = mk.Market("unknown", "merged CMC page: the old contract has no CMC id of its own")
        rows_old = rows_q
    else:
        rp = await cmc.market_pairs(hold["id"])
        rows_old = [*rows_q, _rid(cmc)] + ([r_oh] if r_oh else [])
        old_m = _assess(rp, old_row1, old_closes)
    yield ev("step", step="market_old", check="C5", coin=hold["symbol"], **old_m.as_dict(), rows=rows_old)
    checks.append(_check("C5", f"old {hold['symbol']} market", _lamp(old_m.state), old_m.reason, rows_old))

    new_m = None
    rows_new: list[str] = []
    if succ:
        if same_id:
            rp = await cmc.market_pairs(succ["id"])
            rows_new = [*rows_q, _rid(cmc)] + ([r_oh] if r_oh else [])
            new_m = _assess(rp, old_row1, old_closes)
        elif not new_row1 or not new_row1.get("is_active", 1) or not succ.get("is_active", 1):
            new_m = mk.Market("dead", "successor CMC id is inactive")
            rows_new = rows_q
        else:
            rp = await cmc.market_pairs(succ["id"])
            rows_new = [*rows_q, _rid(cmc)] + ([r_nh] if r_nh else [])
            new_m = _assess(rp, new_row1, new_closes)
        yield ev("step", step="market_new", check="C5", coin=succ["symbol"], **new_m.as_dict(), rows=rows_new)
        checks.append(
            _check("C5", f"successor {succ['symbol']} market", _lamp(new_m.state), new_m.reason, rows_new)
        )

    # C4 ratio
    stated = c3.value("ratio_new_per_old")
    try:
        stated = float(stated) if stated is not None else None
    except (TypeError, ValueError):
        stated = None
    old_names = [hold.get("symbol"), hold.get("name"), hrow.get("name")]
    new_names = [c3.value("successor_symbol"), c3.value("successor_name")] + (
        [succ.get("symbol"), succ.get("name")] if succ else []
    )
    if succ and not same_id:
        # CMC's own page for the successor may name the token differently ("the $ASI" on FET's page)
        succ_notice = (infos.get(str(succ["id"])) or {}).get("notice") or ""
        olds = {str(n).upper() for n in old_names if n}
        new_names += [t for t in re.findall(r"\$([A-Z][A-Z0-9]{1,9})\b", succ_notice) if t not in olds]
    binding = bind_ratio(c3.quote("ratio_new_per_old"), stated, old_names, [str(n) for n in new_names if n])
    if binding.state == "bound":
        stated = binding.parsed  # the number parsed from the quote, never the Reader's float (a2a r03)
    eff = parse_iso_date(c3.value("effective_date"))
    eff_src = (c3.kept.get("effective_date") or {}).get("source")
    new_info = infos.get(str(succ["id"])) if succ else None
    event_day = rt.pick_event_date(
        eff, eff_src, notice, hrow.get("date_added"), (new_info or {}).get("date_added")
    )
    rows_ratio = [*rows_q]
    ev_old, ev_new = old_closes, new_closes
    if succ and event_day.day and stated is not None and binding.state == "bound":
        if event_day.day < start30 + timedelta(days=3):
            s, e = event_day.day - timedelta(days=3), min(event_day.day + timedelta(days=8), now.date())
            ev_old, r1 = await _history(cmc, hold["id"], s, e)
            rows_ratio += [r1] if r1 else []
            if not same_id:
                ev_new, r2 = await _history(cmc, succ["id"], s, e)
                rows_ratio += [r2] if r2 else []
        else:
            rows_ratio += [r for r in (r_oh, r_nh) if r]
    ratio = rt.ratio_state(
        stated=stated,
        bound=binding.state == "bound",
        contracts_verified=bool(old_verified and new_verified),
        event_day=event_day,
        old_closes=ev_old,
        new_closes=ev_new,
        old_alive=old_m.state == "alive",
        new_alive=bool(new_m and new_m.state == "alive"),
        old_price=old_m.price if old_m.state == "alive" else None,
        new_price=new_m.price if new_m and new_m.state == "alive" else None,
        single_id=same_id,
    )
    yield ev(
        "step",
        step="ratio",
        check="C4",
        stated=stated,
        binding=binding.state,
        binding_reason=binding.reason,
        state=ratio.state,
        route=ratio.route,
        reason=ratio.reason,
        observations=ratio.observations,
        event_day=event_day.day.isoformat() if event_day.day else None,
        event_day_source=event_day.source,
        rows=rows_ratio,
    )
    checks.append(
        _check(
            "C4",
            "swap ratio",
            {"P": "verified", "Q": "stale", "none": "not_run"}[ratio.state],
            f"{ratio.state}: {ratio.reason}" if stated is not None else binding.reason,
            rows_ratio,
        )
    )

    # deadline + C6 price integrity (R3 guard)
    deadline = parse_iso_date(c3.value("deadline"))
    deadline_passed = bool(deadline and deadline < now.date())
    legs = [
        {
            "label": hold["symbol"],
            "requested_id": hold["id"],
            "returned_id": old_row1.get("id"),
            "is_active": old_row1.get("is_active"),
            **{k: mk.usd(old_row1).get(k) for k in ("price", "volume_24h", "last_updated")},
        }
    ]
    if succ and not same_id:
        legs.append(
            {
                "label": succ["symbol"],
                "requested_id": succ["id"],
                "returned_id": new_row1.get("id"),
                "is_active": new_row1.get("is_active"),
                **{k: mk.usd(new_row1).get(k) for k in ("price", "volume_24h", "last_updated")},
            }
        )
    trips = sanity.check(legs=legs, ratio=stated, now=now)
    stale_note = "; ".join(
        f"{lab} price on $0 volume"
        for lab, m in ((hold["symbol"], old_m), (succ and succ["symbol"], new_m))
        if m and m.state == "dead" and m.price and not m.volume_24h
    )
    checks.append(
        _check(
            "C6",
            "price integrity",
            "refuted" if trips else "stale" if stale_note else "verified",
            "; ".join(trips) or stale_note or "prices fresh, ids agree",
            rows_q,
        )
    )

    facts = Facts(
        sanity_trips=trips,
        same_id=same_id,
        contract_changed=contract_changed,
        c2=c2.state,
        c2_reason=c2.reason,
        successor_named=c2.state != "not_run",
        old_market=old_m.state,
        new_market=new_m.state if new_m else None,
        ratio_state=ratio.state,
        ratio_route=ratio.route,
        ratio_reason=ratio.reason if stated is None or binding.state == "bound" else binding.reason,
        ratio=stated,
        old_price=old_m.price if old_m.state == "alive" else None,
        new_price=new_m.price if new_m and new_m.state == "alive" else None,
        deadline_quoted=deadline is not None,
        deadline_passed=deadline_passed,
        deadline_text=deadline.isoformat() if deadline else None,
        announcement_unfetchable=bool(
            (cached or {}).get("link_errors") or (session.link_errors if session else [])
        ),
        c3_dropped=list(c3.dropped),
        swap_label_only=swap_label_only,
        old_pairs_note=old_m.pairs_note(),
    )
    d = decide(facts)

    r_use = stated if binding.state == "bound" else None
    p_old, p_new = facts.old_price, facts.new_price
    tracker_price = mk.usd(old_row1).get("price")
    value_swap = qty * r_use * p_new if r_use and p_new else None
    value_sell = qty * p_old if p_old else None
    tracker = qty * tracker_price if (old_m.state != "alive" and tracker_price) else None
    caveats = ["excludes fees, gas and slippage"]
    if p_old and old_m.volume_24h and qty * p_old > 0.01 * old_m.volume_24h:
        caveats.append(
            "size caveat: this holding is over 1% of the old token's 24 h volume; the sell figure may not be achievable at that size"
        )
    window = (
        f"closed {deadline.isoformat()}"
        if deadline_passed
        else f"open until {deadline.isoformat()}"
        if deadline
        else "not stated"
    )
    checks.sort(key=lambda c: c["id"])  # stable: C5 old before C5 successor
    receipt = build_receipt(cmc.calls, llm, fetches, recorded=bool(cached))
    yield ev(
        "verdict",
        **d.as_dict(),
        holding=coin_ref(hold),
        successor=coin_ref(succ) if succ else None,
        qty=qty,
        value_swap_usd=value_swap,
        value_sell_old_usd=value_sell,
        tracker_value_usd=tracker,
        old_volume_24h_usd=old_m.volume_24h,
        old_price_usd=tracker_price,
        new_price_usd=mk.usd(new_row1).get("price") if new_row1 else None,
        ratio_new_per_old=r_use,
        swap_window=window,
        caveats=caveats,
        checks=checks,
        proposal=proposal,
        proposals_count=len(proposals[: i + 1]),
        receipt=receipt,
        captured_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        credits_used=receipt["credits_used"],
        engine="verdict-rules-v1",
    )


def _lamp(state: str) -> str:
    return {"alive": "verified", "dead": "stale", "unknown": "not_run"}.get(state, "not_run")


def from_reader_failure(ev, exc: Exception, hold: dict, session, checks: list[dict], cmc=None):
    """Agent failure: NOT VERIFIABLE (agent could not read the notice), with every attempt in the receipt."""
    receipt = build_receipt(cmc.calls if cmc else [], session.calls, session.fetches, recorded=False)
    return ev(
        "verdict",
        verdict="NOT_VERIFIABLE",
        rule_id="R10",
        reason=f"agent unavailable: {exc}",
        holding=coin_ref(hold),
        successor=None,
        checks=checks,
        proposal=None,
        receipt=receipt,
        engine="verdict-rules-v1",
    )


async def _verify_successor(cmc, c3, notice, hold, hrow, linked_rows, infos) -> tuple[C2Result, list[str]]:
    sym = c3.value("successor_symbol")
    name = c3.value("successor_name")
    new_c = c3.value("new_contract")
    rows: list[str] = []
    cands = [_info_as_cand(r) for r in linked_rows]
    for r in linked_rows:
        infos[str(r["id"])] = r
    if sym:
        rm = await cmc.map(symbol=str(sym).lstrip("$").upper())
        if rm.ok:
            cands += _map_rows(rm.data)
            rows.append(_rid(cmc))
    if new_c:
        ra = await cmc.info(address=str(new_c).lower() if str(new_c).lower().startswith("0x") else str(new_c))
        rows.append(_rid(cmc))
        if ra.ok:
            for v in (ra.data or {}).values():
                cands.append(_info_as_cand(v))
                infos[str(v["id"])] = v
    if (
        not any(int(c["id"]) == int(hold["id"]) for c in cands)
        and sym
        and str(sym).lstrip("$").upper() == hold["symbol"]
    ):
        cands.append(hold)
    missing = sorted({int(c["id"]) for c in cands} - {int(k) for k in infos})
    if missing:
        ri = await cmc.info(ids=missing[:20])
        rows.append(_rid(cmc))
        for k, v in (ri.data or {}).items():
            infos[k] = v
    res = check_successor(
        symbol=str(sym) if sym else None,
        name=str(name) if name else None,
        new_contract=str(new_c) if new_c else None,
        new_chain=str(c3.value("new_chain")) if c3.value("new_chain") else None,
        notice=notice,
        candidates=cands,
        infos=infos,
        linked_ids={int(r["id"]) for r in linked_rows},
    )
    # the ticker on the page is the holding itself: a rename or ticker change on one id
    if (
        res.state == "unresolved"
        and not new_c
        and sym
        and str(sym).lstrip("$").upper() == hold["symbol"].upper()
    ):
        res = C2Result(
            "verified",
            "identity: the coin you hold",
            hold,
            f"{hold['symbol']} is the coin you hold (CMC id {hold['id']})",
            cands,
        )
    if res.successor and str(res.successor["id"]) in infos:
        row = infos[str(res.successor["id"])]
        res.successor = {
            **res.successor,
            "is_active": res.successor.get("is_active", _info_as_cand(row)["is_active"]),
        }
    return res, rows
