# Deploy proof (2026-11-22)

Captured with `scripts/capture_deploy_proof.py https://successor.edycu.dev CPOOL MKR` against the Vercel production
deployment of commit `37b3b58` (`/api/health` → `build_sha`). Each JSON file holds the request URL, the response
headers (`server: Vercel`, `x-vercel-id`), and the client-side arrival time of every NDJSON line.

- `stream-probe-2026-11-22.json`: 5 lines emitted 1 s apart by the function arrive about 1 s apart at the client,
  so Vercel's Python runtime streams NDJSON line by line instead of buffering.
- `live-lookup-CPOOL-2026-11-22.json` / `live-lookup-MKR-2026-11-22.json`: cold lookups (no extraction cache exists
  yet), each streaming to a final event well inside the 50 s wall (`maxDuration` 60 in `vercel.json`).
- The per-deployment `*.vercel.app` URL answers HTTP 302 to `vercel.com/sso-api` (Vercel deployment protection), so
  the proof is taken on the production alias, which is the same deployment and the same function.
- The final events carry `"engine": "spike"`: a provisional rule used only to rehearse timing. The deterministic
  verifiers and verdict table replace it in the core flow.
