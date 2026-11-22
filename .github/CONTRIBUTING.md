# Contributing

Thanks for your interest in improving Successor!

## Getting Started
1. Fork the repo and branch from `main`: `git checkout -b feat/your-feature`
2. Install dependencies: `python -m venv .venv && .venv/bin/pip install -e '.[dev,e2e]'`
3. Set the two keys the real flow needs: `export CMC_API_KEY=...` (CoinMarketCap Pro API) and `export DASHSCOPE_API_KEY=...` (Qwen). Never commit them; see `.env.example`.
4. Start the app: `SERVE_STATIC=1 .venv/bin/uvicorn api.index:app`

## Before You Open a PR
- `make ci` passes (ruff, mypy, pytest with coverage, the unplug tests, the offline evals, pip-audit, gitleaks; install the `gitleaks` binary first, e.g. `brew install gitleaks`).
- `make e2e` passes (Playwright against the live URL, or `BASE=http://localhost:8000 make e2e` against your local run).
- A change to a verdict rule needs a test that pins the case. The rule SWAP requires a verified contract and a price-confirmed ratio; do not weaken it.
- Add or update tests for any behavior change, and keep every number in the README greppable to a file in `docs/proof/` or a test.
- Keep commit messages descriptive: say what changed and why.

## Reporting Bugs / Requesting Features
Open an issue using the provided templates. Include repro steps, expected vs. actual behavior, and the capture time of the lookup (verdicts follow the market).
