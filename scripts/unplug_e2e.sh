#!/usr/bin/env bash
# Unplug -> must fail. Runs the app with NO keys (empty HOME, so no ~/.config fallback either) and points the
# live-flow browser tests at it. The product must answer an error and the tests must FAIL; if they pass, the
# demo is not using the sponsor's API and this script exits 1.
set -u
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
PORT=${PORT:-8765}
OUT=docs/proof/unplug/unplug-$(date -u +%F).txt
HOME_DIR=$(mktemp -d)
env -i PATH="$PATH" HOME="$HOME_DIR" SERVE_STATIC=1 "$PY" -m uvicorn api.index:app --port "$PORT" --log-level warning >/dev/null 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null; rm -rf "$HOME_DIR"' EXIT
sleep 4
{
  echo "# unplug test $(date -u +%FT%TZ): app started with no CMC_API_KEY, no DASHSCOPE_API_KEY, empty HOME"
  echo "\$ curl -H 'Accept: application/json' http://127.0.0.1:$PORT/api/lookup?q=CPOOL"
  curl -s -w '\nHTTP %{http_code}\n' -H 'Accept: application/json' "http://127.0.0.1:$PORT/api/lookup?q=CPOOL"
  echo "\$ pytest e2e -k 'json or cpool'   (expected: FAIL)"
  E2E_BASE_URL="http://127.0.0.1:$PORT" "$PY" -m pytest e2e -q -p no:cacheprovider --override-ini="norecursedirs=" \
    -k "json_is_a_verdict or health_reports" 2>&1 | tail -6
} | tee "$OUT"
if grep -q "passed" "$OUT" && ! grep -q "failed" "$OUT"; then echo "UNPLUG FAIL: tests passed without keys" | tee -a "$OUT"; exit 1; fi
echo "UNPLUG OK: with the sources removed the product errors and the tests fail" | tee -a "$OUT"
