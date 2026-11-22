# Successor

> CoinMarketCap tells you a coin migrated, but only in prose. Successor reads the notice, finds the successor
> token, verifies it against CMC's own data and gives the holder one verdict with the rows that prove it.

**Status: early build.** The CoinMarketCap and LLM integrations are proven (see `docs/proof/spike/`); the
verification engine and the board UI are in progress. The full README arrives with the first release.

## Run locally

```bash
uv venv && uv pip install -e '.[dev]'
export CMC_API_KEY=...        # CoinMarketCap Pro API key
export DASHSCOPE_API_KEY=...  # Qwen on Alibaba Cloud DashScope (intl)
uvicorn api.index:app --reload
curl -N 'localhost:8000/api/lookup?q=CPOOL&qty=10000'
```

## Tests

```bash
pytest -q
```

## License

MIT
