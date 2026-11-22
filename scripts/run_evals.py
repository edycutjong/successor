"""Run the agent evals offline (replayed real rows + recorded Reader output) and print the pass count.

python scripts/run_evals.py [--json evidence/evals-<date>.json]
Live drift: re-record with scripts/capture_case.py, then run this again.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from successor.evals import run_all  # noqa: E402


def main() -> int:
    rows = asyncio.run(run_all())
    for r in rows:
        tag = "PASS" if r["pass"] else "FAIL"
        kind = "case" if r["counted"] else "variant"
        print(
            f"{tag} {kind:<7} {r['n']:>2} {r['case']:<32} {r['got']['verdict']}/{r['got']['rule_id']}  {str(r['reason'])[:110]}"
        )
    counted = [r for r in rows if r["counted"]]
    passed = sum(r["pass"] for r in counted)
    print(
        f"\nevals: {passed}/{len(counted)} counted cases pass; variants {sum(r['pass'] for r in rows if not r['counted'])}/"
        f"{sum(not r['counted'] for r in rows)}"
    )
    if "--json" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--json") + 1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({"counted_pass": passed, "counted_total": len(counted), "rows": rows}, indent=1)
        )
    return 0 if passed == len(counted) and all(r["pass"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
