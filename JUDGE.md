# For judges

Mirror of the live page **https://successor.edycu.dev/judge** (no login, no keys, no rate-limit exemption needed).

## The claim

CoinMarketCap says a coin migrated, but only in prose. Successor reads the notice, finds the successor token, checks it against CMC's own rows, and gives the holder one verdict: SWAP, SELL OLD, WRITE OFF, or NOT VERIFIABLE.

## The 2-minute path (steps 1–3 take 30 seconds)

Only ten seconds? Click **AGIX** on the board, then **Receipt**: the agent (a recorded run) follows the notice's link, code confirms the ratio against CMC's prices, and the receipt shows CMC's own rows.

1. Open https://successor.edycu.dev: it runs **CPOOL** on load (the CPOOL chip re-runs it). The board streams the CMC notice, the Reader's proposal, the code checks and the verdict. On 2026-11-22 03:49 UTC it read **SELL OLD** (rule R8): CMC's quotes put the old token 15.7% above the 1:1 swap. R8 needs at least 5%; under that margin the same lookup reads **SWAP** (R9), and when the old token is still above the swap its reason gives the margin. CPOOL has shown both, so read the verdict with the capture time on screen.
2. Click **Receipt**: the CMC calls behind the verdict.
3. Click **AGIX**: the trace shows the Reader's recorded run (the trace labels it "recorded extraction") following the notice's link to fetch.ai; code confirms the ratio against CMC prices on the event date, live, verdict **SWAP** (R9).
4. Open `/?q=GAS&id=1785` (Neo's GAS): its notice quotes a contract (`0xd2a4…76cf`) that no CMC coin carries, so check C2 fails and the verdict is **NOT VERIFIABLE** (R5), not a guess.¹ Offline, `python scripts/run_evals.py` shows the same refusal for a contract one hex digit off (`cpool-bad-contract`).
5. Optional, the agent live: on AGIX press **Re-read live**. The Reader runs now (qwen4-max, live), not from the recording. Three fresh runs on 2026-11-22 each ended **SWAP** (R9) in 18 to 26 s server time (`docs/proof/assets/agix-fresh-runs-2026-11-22.json`). Fresh reads are limited to 3 per 10 minutes per client; if it errors, the demo video shows a fresh run (real wait about 21 s, labelled speed-up) and `docs/proof/assets/agix-fresh-runs-2026-11-22.json` holds all three.
6. Scroll to the **census**: every notice in CMC's top 2000 and the verdict code gives each. Most end NOT VERIFIABLE; the page says why.
7. Terminal: `curl -N 'https://successor.edycu.dev/api/lookup?q=CPOOL&qty=10000'`

¹ The id is needed because the symbol GAS also matches another coin. The notice may be right: CMC's `info?address=` knows that hash in neither byte order (`docs/proof/spike/09-address-gas-n3.json`), so CMC's data cannot confirm it. Raw stream captured 2026-11-22 07:11 UTC: `docs/proof/assets/lookup-GAS-2026-11-22T0711Z.ndjson`. Captures and the census from before a 2026-11-22 wording change say "successor refuted by CMC's data"; the live board says "fails a check against CMC's data": same rule, same verdict.

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
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
export CMC_API_KEY=...  DASHSCOPE_API_KEY=...
SERVE_STATIC=1 .venv/bin/uvicorn api.index:app
# open http://localhost:8000 and click CPOOL
```

This calls the real CoinMarketCap Pro API and Qwen. `python scripts/run_evals.py` is a separate deterministic replay over recorded rows, an eval, not the product.

## Honest limitations

- Most notices cannot be confirmed from CMC's data alone and end NOT VERIFIABLE; the census counts them.
- Verdicts are market-sensitive and can flip between runs.
- The Reader is slow on a notice it has not seen (seconds); cached notices answer in about a second.

## Links

[Repository](https://github.com/edycutjong/successor) · [Live app](https://successor.edycu.dev) · [CMC API Hackathon, Round 2](https://dorahacks.io/hackathon/coinmarketcap-api-202611/detail)

Not financial advice. Values exclude fees, gas and slippage.
