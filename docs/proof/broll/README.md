# B-roll receipts (2026-11-23)

`docs/assets/successor-broll.gif` is a screen recording of https://successor.edycu.dev (production build 7ccc8d5, v1.1.4),
taken in headless Google Chrome 157 at 2x on 2026-11-23 at 13:53 UTC. The viewport was 980×1000 CSS px. The board is the
browser's own paints, cropped and scaled; nothing on it is drawn or edited. The strip above the board is a caption. In the
typing shot, only the band around the input is shown, and the rest of the frame is the page colour.

It shows two AGIX lookups, both typed into the board. Each file below is the board's own `state.events`, dumped right after
the take: the NDJSON lines from `/api/lookup`, in the order they arrived.

| File | Frames it covers | Verdict | Reader |
|---|---|---|---|
| `lookup-AGIX-20261123T135344Z.ndjson` | opening hold, typing (the board as it stood before Enter) | SWAP (R9) | recorded extraction (cache) |
| `lookup-AGIX-20261123T135352Z.ndjson` | stream, verdict, closing hold | SWAP (R9) | recorded extraction (cache) |

- **Figures (same in both runs).** Each run has `qty` 10000, `value_swap_usd` 469.42 (shown as $469) and `tracker_value_usd`
  5931.79 (shown as $5,932). Dollar values of 100 or more are rounded to whole dollars (`public/app.js:5`). FET's 24 h volume
  was $128,218,418 and AGIX's was $0.
- **Time.** From the Enter keypress to the verdict painted on the board, the lookup took 0.87 s; the caption says
  "lookup took 0.87 s". The recording cuts the first 0.57 s after Enter: the network wait and the first three trace lines,
  while the collapsed board showed the census below it. Those lines are on screen right after the cut, with their real
  times. From the agent block to the moment the SWAP flaps settle, the recording plays 6x slower, and the caption says
  "Slowed ×6" for exactly that span. Everything else plays at 1x. The trace times on the board are the server's `t_ms`.
- **The README's worked example is a different capture.** It quotes $5,924.93 / $463.42 from the 2026-11-22 03:49 UTC
  capture. CMC prices move, and every figure set in this repo carries its own capture time.
