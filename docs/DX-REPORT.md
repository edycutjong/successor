# CoinMarketCap API: what made this possible, what got in the way

A running log of the CMC Pro API as Successor uses it. Every finding links to a verbatim response
in `docs/proof/`. First written 2026-11-22 from the day-one spike (`scripts/spike_cmc.py`,
`scripts/probe_address_case.py`).

## Made possible

| Endpoint | What it gives Successor | Evidence |
|---|---|---|
| `/v2/cryptocurrency/info` (`aux=notice`) | The notice: the only place CMC says a coin was renamed, swapped or merged. All six spike coins (CPOOL, CLEAR, AGIX, FET, MKR, SKY) carry one, on the old page and on the new | `docs/proof/spike/01-info.json` |
| `/v2/cryptocurrency/info` `contract_address[]` | Every chain's contract per coin, so a contract the notice quotes can be checked for equality against CMC's own list | `01-info.json` |
| `/v1/cryptocurrency/map` (`listing_status=active,inactive,untracked`) | Symbol collisions made visible: `CLEAR` maps to 2 coins, `SKY` to 5 | `02-map.json` |
| `/v2/cryptocurrency/quotes/historical` | Daily rows for AGIX and FET on 2024-06-30, 07-01 and 07-02, around the ASI merger | `04-historical-agix-2024-07.json`, `04-historical-fet-2024-07.json` |
| `/v2/cryptocurrency/market-pairs/latest` | Whether the old token still trades on spot pairs (CPOOL 20 pairs, AGIX 3) | `05-market-pairs-*.json` |
| `/v1/key/info` | Plan and credits left, for `/api/health` | `06-key-info.json` |

## Got in the way

1. **`info?address=` is case-sensitive, and the error message is misleading.** CMC lists AGIX's contract in
   EIP-55 checksummed case (`0x5B75…b542`). Passing that exact string back to `info?address=` returns HTTP 400
   `Invalid value for 'slug': 'null'`; the lowercased address returns AGIX (id 2424). Successor lowercases `0x`
   addresses before the call; base58 addresses (Solana) keep their case.
   Evidence: `08-address-case-checksum.json`, `08-address-case-lower.json`.
2. **`date_added` is copied from the old coin to its successor, so it cannot date a rename.** CLEAR (id 42884)
   reports `date_added` 2021-10-10T08:04:07Z, identical to CPOOL (id 12573), although CLEAR's notice links an
   announcement posted on 2026-11-17 and CLEAR's daily history in the spike starts on 2026-11-19. Successor dates the
   event from the X post the notice links: an X status id is a snowflake whose top bits are its creation time.
   Evidence: `01-info.json`, `04-historical-clear-2026-11-17.json`.
3. **`convert=EUR` on `quotes/historical` scales supply and percent change by the FX rate.** For FET on 2026-11-01,
   EUR `circulating_supply` is 2,177,348,323 against 2,429,181,578 in USD, and `percent_change_24h` is 1.3296 against
   1.4834. Both ratios equal the EUR/USD price ratio (0.8963). Supply does not depend on currency, and a percent change
   in EUR would not differ from USD by exactly the FX factor. Successor requests USD only.
   Evidence: `07-convert-usd.json`, `07-convert-eur.json`.
4. **The notice is free text.** Contract addresses, ratios and dates sit inside prose and markdown links, which is
   why Successor reads the notice with an LLM and then verifies every field it proposes against the endpoints above.
5. **`quotes/latest` can report `volume_24h` 0 while `market-pairs/latest` lists counted pairs with volume.** For the
   old RZUSD (id 35716) at 2026-11-27 19:05 UTC, `quotes/latest` returned `volume_24h` 0 with `last_updated`
   19:04:04, and `market-pairs/latest` returned five spot pairs on PancakeSwap v2 (BSC) with $2,388 of 24 h volume
   between them, each with `outlier_detected` 0 and `exclusions` null, last updated between 14:50 and 17:40 UTC.
   Neither response says why the quote includes none of them (the quote's own `num_market_pairs` is 26, the spot
   listing returns 5). Successor's market check (C5) still follows the quote for the price, which is stale on $0 of
   quoted volume either way. Since 2026-11-27 a WRITE OFF also needs `market-pairs/latest` to list under $100 of 24 h
   volume across unflagged pairs: above that the verdict is NOT VERIFIABLE, and below it the WRITE OFF sentence states
   both figures instead of "no live market".
   The 2026-11-22 captures hold the same disagreement for EPS (two unflagged pairs, $41.75) and REP (one unflagged
   pair with volume, $49.20; REP's third pair, $195.02 on Indodax, carries `exclusions` ["price", "volume"], so there
   CMC does say why).
   Evidence: `docs/proof/assets/lookup-RZUSD-2026-11-27T1905Z.ndjson` (receipt rows r6 and r9),
   `docs/proof/assets/lookup-EPS-2026-11-22T0349Z.ndjson`, `docs/proof/assets/lookup-REP-2026-11-22T0349Z.ndjson`.
