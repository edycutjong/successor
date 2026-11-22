# Demo video receipts (2026-11-22)

Each file is the event stream (`/api/lookup` NDJSON) of one lookup shown in the demo video, dumped from the board's own
`state.events` right after the shot (one JSON object per line, in arrival order),
recorded against https://successor.edycu.dev (build a09efb9; the Re-read shot at build 4277add and the GAS shot at build 5cc9fea, both after the tick and
'market value, no verdict' fixes). Every number on screen in those shots comes from these files.

| File | Shot | Verdict | Reader |
|---|---|---|---|
| `lookup-AGIX-20261122T092421Z.ndjson` | AGIX typed on the board | SWAP (R9) | recorded extraction (cache) |
| `lookup-AGIX-fresh-20261122T095743Z.ndjson` | Re-read live (`fresh=1`; verdict at 21.0 s, shown sped up ×4.8) | SWAP (R9) | live qwen4-max |
| `lookup-AGIX-receipt-20261122T092054Z.ndjson` | Receipt drawer (12 calls, 10 credits) | SWAP (R9) | recorded extraction (cache) |
| `lookup-GAS-20261122T100747Z.ndjson` | GAS typed on the board (old token shown as 'market value, no verdict') | NOT VERIFIABLE (R5) | recorded extraction (cache) |
| `lookup-CPOOL-20261122T094352Z.ndjson` | CPOOL chip (old token worth 15.4% more than the 1:1 swap) | SELL OLD (R8) | recorded extraction (cache) |

The opening card uses the same capture as the AGIX board shot (`lookup-AGIX-20261122T092421Z.ndjson`, verdict event):
`tracker_value_usd` 5927.95 and `value_swap_usd` 470.29 for `qty` 10000, shown as $5,928 and $470 (the board rounds dollar values of 100
or more to whole dollars), `old_volume_24h_usd` 0 ("$0 traded in 24 h"), ratio 0.43335. The census figures are `/api/census`
(scan 2026-11-22T02:32:34Z). The code card is `successor/cmc.py` lines 168, 173-175 and 182 (the elided lines are marked).
