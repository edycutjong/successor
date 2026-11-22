"""DX probe: /v2/cryptocurrency/info?address= with an EIP-55 checksummed address vs the same address lowercased.

    python scripts/probe_address_case.py   # writes docs/proof/spike/08-address-case-{checksum,lower}.json
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from successor.cmc import CmcClient  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "proof" / "spike"
AGIX = "0x5B7533812759B45C2B44C19e320ba2cD2681b542"  # as CMC itself lists it in contract_address[]


async def main() -> None:
    async with CmcClient() as cmc:
        for name, addr in (("checksum", AGIX), ("lower", AGIX.lower())):
            r = await cmc.get("/v2/cryptocurrency/info", {"address": addr})
            (OUT / f"08-address-case-{name}.json").write_text(json.dumps(r.receipt(), indent=1) + "\n")
            print(name, r.http_status, r.status.get("error_message"), list((r.data or {}).keys())[:3])


if __name__ == "__main__":
    asyncio.run(main())
