"""Record / replay CMC traffic so tests and evals run the real flow offline on real saved rows.

`RecordingCmc` is the live client plus an optional notice mutation (the two hand-made adversarial fixtures);
`ReplayCmc` serves recorded bodies by (path, params) and fails loudly on any request that was not recorded.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from successor.cmc import CmcClient, CmcResponse


def _key(path: str, params: dict[str, Any]) -> str:
    return path + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))


class RecordingCmc(CmcClient):
    def __init__(self, mutate_notice: Callable[[int, str], str] | None = None, **kw: Any) -> None:
        super().__init__(**kw)
        self.mutate_notice = mutate_notice
        self.log: list[dict] = []

    async def get(self, path, params=None, *, strict=False) -> CmcResponse:
        resp = await super().get(path, params, strict=strict)
        if self.mutate_notice and path.endswith("/cryptocurrency/info") and isinstance(resp.data, dict):
            for k, row in resp.data.items():
                if row.get("notice"):
                    row["notice"] = self.mutate_notice(int(k), row["notice"])
        self.log.append(
            {
                "path": resp.path,
                "params": resp.params,
                "http_status": resp.http_status,
                "elapsed_ms": resp.elapsed_ms,
                "captured_at": resp.captured_at,
                "body": json.loads(json.dumps(resp.body)),
            }
        )
        return resp


class ReplayCmc(CmcClient):
    def __init__(self, log: list[dict]) -> None:
        super().__init__(key="replay")
        self.recorded = {_key(e["path"], e["params"]): e for e in log}

    async def __aenter__(self) -> ReplayCmc:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def get(self, path, params=None, *, strict=False) -> CmcResponse:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        e = self.recorded.get(_key(path, params))
        if e is None:
            raise RuntimeError(f"replay: request not recorded: {_key(path, params)}")
        resp = CmcResponse(
            path=path,
            params=params,
            http_status=e["http_status"],
            body=json.loads(json.dumps(e["body"])),
            elapsed_ms=e.get("elapsed_ms", 0),
            captured_at=e.get("captured_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        self.credits_used += resp.credit_count
        self.calls.append(resp)
        return resp
