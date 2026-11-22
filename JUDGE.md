# For judges

Mirror of the live page **https://successor.edycu.dev/judge** (no login, no keys, no rate-limit exemption needed).

## The claim

CoinMarketCap says a coin migrated, but only in prose. Successor reads the notice, finds the successor token, checks it against CMC's own rows, and gives the holder one verdict: SWAP, SELL OLD, WRITE OFF, or NOT VERIFIABLE.

## The 30-second path

1. Open https://successor.edycu.dev: it runs **CPOOL** on load (the CPOOL chip re-runs it). The board streams the CMC notice, the Reader's proposal, the code checks and the verdict. When this was written (2026-11-22): **SELL OLD** (rule R8). Verdicts follow the market, so the capture time is on screen.
2. Click **Receipt**: the CMC calls behind the verdict.
3. Click **AGIX**: the Reader follows the notice's link, code confirms the ratio against CMC prices on the event date, verdict **SWAP** (R9).
4. Type **GAS**: its notice quotes a contract (`0xd2a4…76cf`) that no CMC coin carries. Code finds no CMC coin with that contract, so check C2 fails and the verdict is **NOT VERIFIABLE** (R5), not a guess (captured 2026-11-22 07:11 UTC, `docs/proof/assets/lookup-GAS-2026-11-22T0711Z.ndjson`). Offline, `python scripts/run_evals.py` shows the same refusal for a contract one hex digit off (`cpool-bad-contract`).
5. Scroll to the **census**: every notice in CMC's top 2000 and the verdict code gives each. Most end NOT VERIFIABLE; the page says why.
6. Terminal: `curl -N 'https://successor.edycu.dev/api/lookup?q=CPOOL&qty=10000'`

If a live lookup errors or runs long (CMC or the model slow), the board says so and shows no verdict. The landing page https://successor.edycu.dev/about replays a captured CPOOL lookup, labelled with its capture time (2026-11-22 03:49 UTC), and `docs/proof/assets/` holds the raw streams.

## Receipts

| What | Where |
|---|---|
| Live health (CMC key status, model, cache size, build SHA, timestamps) | `GET /api/health` |
| Census (161 notices in the top 2000, verdicts, capture time) | `GET /api/census` |
| Lookup latency p50/p95, cached and cold | `docs/proof/bench/`, `python scripts/bench.py <url> CPOOL 12` |
| Tests, evals, coverage | README "Engineering Rigor"; `make ci`, `python scripts/run_evals.py` |
| Unplug test: no CMC key means an error and no verdict | `tests/test_unplugged.py`, `tests/test_unplugged_http.py` |
| Live-URL browser tests (open, click a coin, assert a verdict and receipt) | `e2e/`, `make e2e` |

## Reproduce (the real path)

```bash
git clone https://github.com/edycutjong/successor && cd successor
pip install -e .
export CMC_API_KEY=...  DASHSCOPE_API_KEY=...
uvicorn api.index:app
```

This calls the real CoinMarketCap Pro API and Qwen. `python scripts/run_evals.py` is a separate deterministic replay over recorded rows, an eval, not the product.

## Honest limitations

- Most notices cannot be confirmed from CMC's data alone and end NOT VERIFIABLE; the census counts them.
- Verdicts are market-sensitive and can flip between runs.
- The Reader is slow on a notice it has not seen (seconds); cached notices answer in about a second.

## Links

[Repository](https://github.com/edycutjong/successor) · [Live app](https://successor.edycu.dev) · [CMC API Hackathon, Round 2](https://dorahacks.io/hackathon/coinmarketcap-api-202611/detail)

Not financial advice. Values exclude fees, gas and slippage.
