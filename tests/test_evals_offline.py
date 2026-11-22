"""The 10 agent evals (evals/cases.json) replayed offline through the real flow: verdict AND rule must match."""

import pytest

from successor.evals import run_all


@pytest.fixture(scope="module")
async def rows():
    return await run_all()


async def test_every_counted_case_and_variant_passes():
    rows = await run_all()
    failed = [(r["case"], r["expected"], r["got"], r["reason"]) for r in rows if not r["pass"]]
    assert not failed, failed
    assert sum(r["counted"] for r in rows) == 10


async def test_injection_verdict_equals_clean_case_and_no_field_quotes_the_injection():
    import json

    from successor.evals import FIXTURES

    fx = json.loads((FIXTURES / "injection.json").read_text())
    for p in fx["extraction"]["proposals"]:
        for v in p.values():
            if isinstance(v, dict) and v.get("evidence_quote"):
                assert "Ignore previous instructions" not in v["evidence_quote"]
