"""R3 sanity guard: data integrity only. A trip means CMC's rows cannot carry a verdict. Pure."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def _ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (
        d if d.tzinfo else d.replace(tzinfo=UTC)
    )  # a2a r03: a naive stamp must not crash the aware subtraction


def check(
    *,
    legs: list[dict],
    ratio: float | None,
    now: datetime,
) -> list[str]:
    """legs: [{label, requested_id, returned_id, is_active, price, volume_24h, last_updated}]."""
    trips: list[str] = []
    for leg in legs:
        lab = leg.get("label", "coin")
        if leg.get("returned_id") is None:
            trips.append(f"{lab}: CMC returned no quote row for requested id {leg['requested_id']}")
            continue
        if int(leg["returned_id"]) != int(leg["requested_id"]):
            trips.append(
                f"{lab}: CMC returned id {leg['returned_id']} for requested id {leg['requested_id']}"
            )
        price, vol = leg.get("price"), leg.get("volume_24h") or 0
        if price is not None and price <= 0 and vol > 0:
            trips.append(f"{lab}: price {price} with volume {vol:,.0f}")
        lu = _ts(leg.get("last_updated"))
        if leg.get("is_active") and lu and now - lu > timedelta(hours=48):
            trips.append(f"{lab}: last_updated {leg['last_updated']} is more than 48 h old on an active id")
        elif leg.get("is_active") and price and vol > 0 and lu is None:
            # a2a r04: a priced, traded quote must prove when it was priced
            trips.append(
                f"{lab}: no readable last_updated on a priced active quote ({leg.get('last_updated')!r})"
            )
        elif lu and lu - now > timedelta(hours=1):
            trips.append(f"{lab}: last_updated {leg['last_updated']} is in the future")
    if ratio is not None and not (1e-9 <= float(ratio) <= 1e9):
        trips.append(f"ratio {ratio} is outside 1e-9..1e9")
    return trips
