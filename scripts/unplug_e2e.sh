#!/usr/bin/env bash
# Unplug -> must fail. Runs the app with NO keys (empty HOME, so no ~/.config fallback either) and points the
# live-flow tests at it. The product must answer HTTP 502 "CMC_API_KEY is not set" and the tests must FAIL on
# that (an assertion, not a refused connection). If they pass, the demo is not using the sponsor's API: exit 1.
set -u
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
PORT=${PORT:-8765}
OUT=docs/proof/unplug/unplug-$(date -u +%F).txt
HOME_DIR=$(mktemp -d)
env -i PATH="$PATH" HOME="$HOME_DIR" SERVE_STATIC=1 "$PY" -m uvicorn api.index:app --port "$PORT" --log-level warning >/dev/null 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null; rm -rf "$HOME_DIR"' EXIT
for _ in $(seq 1 40); do curl -s -o /dev/null "http://127.0.0.1:$PORT/judge" && break; sleep 0.5; done
URL="http://127.0.0.1:$PORT"
{
  echo "# unplug test $(date -u +%FT%TZ): app started with no CMC_API_KEY, no DASHSCOPE_API_KEY, empty HOME"
  echo "\$ curl -H 'Accept: application/json' $URL/api/lookup?q=CPOOL"
  curl -s -w '\nHTTP %{http_code}\n' -H 'Accept: application/json' "$URL/api/lookup?q=CPOOL"
  echo "\$ pytest e2e -k 'json_is_a_verdict or health_reports'   (expected: FAIL)"
  E2E_BASE_URL="$URL" "$PY" -m pytest e2e -q -p no:cacheprovider --override-ini="norecursedirs=" \
    -k "json_is_a_verdict or health_reports" 2>&1 | tail -12
} | tee "$OUT"
grep -q '"error":"CMC_API_KEY is not set"' "$OUT" && grep -q "HTTP 502" "$OUT" || { echo "UNPLUG FAIL: the app did not answer the expected error" | tee -a "$OUT"; exit 1; }
grep -q "2 failed" "$OUT" && ! grep -qiE "ConnectError|Connection refused" "$OUT" || { echo "UNPLUG FAIL: the tests did not fail on an assertion" | tee -a "$OUT"; exit 1; }
echo "UNPLUG OK: with the sources removed the product errors (HTTP 502) and the live-flow tests fail" | tee -a "$OUT"
