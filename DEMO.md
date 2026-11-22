# Successor: demo walkthrough

Sections 1, 2 and 4 run against the live deployment, https://successor.edycu.dev; sections 3 and 5 add offline and local checks. All figures are from captures dated
2026-11-22 (raw streams in `docs/proof/assets/`, bench in `docs/proof/bench/`). Market-sensitive verdicts are shown with
the time they were captured; run the commands again and the live figures will differ slightly.

## 1. The hero lookup (about 1 s, cached Reader read, live CMC calls)

1. Open https://successor.edycu.dev. The first screen streams `/api/lookup` for CPOOL (`/api/hero` is the same flow on its own rate bucket).
2. Watch the board: the CMC notice (prose) appears, the Reader proposes CLEAR, the trace streams each check as it runs
   (C2 contract, C5 markets, C4 ratio), the successor column flaps to CLEAR, the status column settles on
   **SELL OLD**, and seven check rows light (C1 holding resolved · C2 successor and contract match CMC · C3 every kept field quoted verbatim · C4 swap ratio · C5 market, once per token · C6 price integrity). On 2026-11-22 03:49 UTC the old token was worth 15.7% more than a 1:1 swap into the new one.
3. Open the receipt drawer: every CMC endpoint, params, timestamp, credit cost, the verbatim rows, the Reader's prompt
   and raw output, and a `curl` with a placeholder for the key.

Same thing from a terminal (NDJSON trace, one line per step):

```bash
curl -N 'https://successor.edycu.dev/api/lookup?q=CPOOL&qty=10000'
```

## 2. The agent earns its place: AGIX

```bash
curl -N 'https://successor.edycu.dev/api/lookup?q=AGIX&qty=10000'
```

The notice is prose and links `fetch.ai`. The Reader opens that link, reads the ratio **0.43335**, and proposes the
successor as `$ASI`; code maps it to FET through CMC's own link and confirms the ratio with CMC prices on the event date.
Verdict **SWAP** (rule R9). On 2026-11-22 03:49 UTC: 10,000 AGIX is $5,924.93 at the old price, which is stale ($0 traded in 24 h), and $463.42 as FET after the swap.

## 3. Code catches the Reader

Run `python scripts/run_evals.py` (offline, replays saved CMC rows and recorded Reader output). Cases to look at:

- `cpool-bad-contract`: the Reader's contract differs from CMC's by one hex digit. Result: NOT VERIFIABLE, rule R5.
- `cpool-misread-ratio`: the Reader proposes ratio 2 where the notice says 1:1. Result: NOT VERIFIABLE, rule R10.
- `injection`: a notice that tries to instruct the model. Result: the normal SELL OLD verdict.

Expected last line: `evals: 10/10 counted cases pass; variants 4/4`.

## 4. The census: what CMC says only in prose

Open the census screen on the site, or:

```bash
curl -s https://successor.edycu.dev/api/census | python3 -m json.tool | head -40
```

161 coins in the active top 2000 carry a notice (scan 2026-11-22T02:32:34Z), 141 of them migration-type. Verdicts over
them (captured 2026-11-22T03:45:14Z): NOT VERIFIABLE 130 · NOTHING TO DO 26 · WRITE OFF 3 · SWAP 2 · SELL OLD 0.
Most notices cannot be confirmed from CMC's data alone, and the page lists why.

## 5. Unplug test

Without a CMC key the app returns an error and no verdict; without an LLM key a cold notice ends NOT VERIFIABLE
(`tests/test_unplugged.py`, `tests/test_unplugged_http.py`). `make unplug-e2e` starts the app with no keys and an empty home
directory and points the live-flow browser tests at it: the app answers HTTP 502 `CMC_API_KEY is not set` and the tests fail
(`docs/proof/unplug/`). With the sources removed the live-flow tests fail; they pass only against the real product.

## 6. Numbers to quote

| Item | Value | Source |
|---|---|---|
| Tests | 83 passed (82 % coverage), 12 live-URL E2E | `make test-coverage`, `make e2e` |
| Evals | 10/10 cases, 4/4 variants | `python scripts/run_evals.py` |
| Cached lookup, live CMC calls | p50 1.007 s, p95 1.454 s (n=12, 2026-11-22 04:29 UTC). Re-measured on HEAD 0f2e719, 2026-11-22 11:16 UTC: p50 0.796 s · p95 1.363 s (n=12, `docs/proof/bench/bench-cached-2026-11-22T1116Z.json`); an earlier run that hour hit one slow call (p95 5.148 s, n not recorded, file overwritten), so the p95 is network-dependent. | `docs/proof/bench/` |
| Cold Reader lookup (`fresh=1`) | p50 15.44 s, p95 21.45 s (n=6, CPOOL, 2026-11-22 05:22 UTC); day-one singles 16.89 s (CPOOL), 8.79 s (MKR) | `docs/proof/bench/bench-cold-2026-11-22.json`, `docs/proof/deploy/` |
| Notices in the active top 2000 | 161 (141 migration-type) | `/api/census` |
