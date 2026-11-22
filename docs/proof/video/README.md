# Demo video receipts (2026-11-22)

Each file is the verbatim event stream (`/api/lookup` NDJSON, as the board received it) of one lookup shown in the demo video,
recorded against https://successor.edycu.dev at build a09efb9. Every number on screen in those shots comes from these files.

| File | Shot | Verdict | Reader |
|---|---|---|---|
| `lookup-AGIX-20261122T092421Z.ndjson` | AGIX typed on the board | SWAP (R9) | recorded extraction (cache) |
| `lookup-AGIX-fresh-20261122T090934Z.ndjson` | Re-read live (`fresh=1`) | SWAP (R9) | live qwen4-max |
| `lookup-AGIX-receipt-20261122T092054Z.ndjson` | Receipt drawer (12 calls, 10 credits) | SWAP (R9) | recorded extraction (cache) |
| `lookup-GAS-20261122T092454Z.ndjson` | GAS typed on the board | NOT VERIFIABLE (R5) | recorded extraction (cache) |
| `lookup-CPOOL-20261122T092522Z.ndjson` | CPOOL chip | SELL OLD (R8) | recorded extraction (cache) |

The opening dollar figures (10,000 AGIX: $5,924.93 at the stale old price vs $463.42 as FET) are the dated capture in
`docs/proof/assets/lookup-AGIX-2026-11-22T0349Z.ndjson`; the census figures are `/api/census` (scan 2026-11-22T02:32:34Z).
