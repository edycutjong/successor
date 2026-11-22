PY ?= .venv/bin/python
BASE ?= https://successor.edycu.dev

.PHONY: unplug-e2e help install lint lint-fix typecheck test test-coverage evals unplug e2e bench bench-cold lighthouse audit secrets security-scan ci

help: ## list targets
	@grep -E '^[a-z0-9-]+:.*##' Makefile | sed 's/:.*## /\t/'

install: ## dev + e2e dependencies and the Chromium for the browser tests
	$(PY) -m pip install -e '.[dev,e2e]' && $(PY) -m playwright install chromium

lint: ## ruff check + format check
	$(PY) -m ruff check . && $(PY) -m ruff format --check .

lint-fix: ## ruff autofix + format
	$(PY) -m ruff check --fix . && $(PY) -m ruff format .

typecheck: ## mypy over successor/ and api/
	$(PY) -m mypy

test: ## unit tests
	$(PY) -m pytest -q

test-coverage: ## unit tests with coverage (fails under 70 %)
	$(PY) -m pytest -q --cov --cov-report=term-missing --cov-report=xml

evals: ## offline replay of the 10 counted cases + variants (an eval, not the product)
	$(PY) scripts/run_evals.py

unplug: ## unplug the keys: the demo path must fail, never fall back to canned output
	$(PY) -m pytest -q tests/test_unplugged.py tests/test_unplugged_http.py

unplug-e2e: ## run the app with NO keys and point the live-flow tests at it; they must fail
	./scripts/unplug_e2e.sh

e2e: ## browser tests against $(BASE) (default: the live URL)
	E2E_BASE_URL=$(BASE) $(PY) -m pytest e2e -q -p no:cacheprovider --override-ini="norecursedirs="

bench: ## cached lookup p50/p95 against $(BASE), gate p95 <= 3 s
	$(PY) scripts/bench.py $(BASE) CPOOL 12 --gate-p95 3

bench-cold: ## cold lookup p50/p95 (3 Qwen reads per 10 min; takes ~12 min)
	$(PY) scripts/bench.py $(BASE) CPOOL 6 --fresh

lighthouse: ## Lighthouse against $(BASE); gates in lighthouserc.json
	npx --yes @lhci/cli@0.14 autorun --config=lighthouserc.json

audit: ## dependency CVEs (pip-audit)
	$(PY) -m pip_audit --skip-editable

secrets: ## gitleaks over the full history
	gitleaks detect --no-banner --redact --log-opts="--all"

security-scan: audit secrets

ci: lint typecheck test-coverage unplug evals audit secrets ## everything CI runs before the live stages (needs the gitleaks binary)
