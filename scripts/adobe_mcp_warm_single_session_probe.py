"""Fast read-only MCP latency: one client, one existing Adobe app, no app restarts.

This measures WARM MCP calls, never Illustrator/Photoshop artwork creation or
native-save E2E. Failed probes do not enter p50/p95 as "fast successes".
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp import Client


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    nums = sorted(values)
    index = (len(nums) - 1) * q
    i = int(index)
    return round(nums[i] + (nums[min(i + 1, len(nums) - 1)] - nums[i]) * (index - i), 3)


async def probe(app: str, samples: int = 12) -> dict[str, Any]:
    if app not in {"xd", "illustrator", "photoshop"}:
        raise ValueError("application must be exactly xd, illustrator or photoshop")
    if samples < 3 or samples > 100:
        raise ValueError("read-only probe sample count outside 3..100")
    record: dict[str, Any] = {
        "schema": "adobe-mcp-warm-single-session/v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "host": os.getenv("COMPUTERNAME"),
        "application": app,
        "session": os.getenv("ADOBE_SESSION"),
        "github_run_id": os.getenv("GITHUB_RUN_ID"),
        "intent": "read-only warm MCP measurements with one pre-existing Adobe process",
        "not_measured": ["app_startup", "GUI_focus", "rect_create", "UXP_Apply", "native_save", "app_shutdown"],
        "metric_semantics": "illustrator probe=false health is gateway/coordinator, NOT host JSX round-trip",
        "rows": [],
        "ok": False,
    }
    started = time.perf_counter_ns()
    timings: dict[str, list[float]] = {}
    try:
        t = time.perf_counter_ns()
        async with Client("http://127.0.0.1:8787/mcp") as client:
            record["new_client_connect_ms"] = round((time.perf_counter_ns() - t) / 1e6, 3)
            for capability in ("creative.health", "creative.scenegraph.list") if app == "xd" else ("creative.health",):
                arguments = {"probe": False, "timeout": 5} if app == "illustrator" else {}
                for i in range(samples):
                    ts = time.perf_counter_ns()
                    answer = await asyncio.wait_for(client.call_tool("creative_read", {
                        "application": app, "capability": capability, "arguments": arguments,
                    }), timeout=7)
                    elapsed = round((time.perf_counter_ns() - ts) / 1e6, 3)
                    response = answer.structured_content or {}
                    valid = not answer.is_error and response.get("ok") is True
                    data = response.get("result") or {}
                    if valid and app == "xd":
                        if capability == "creative.health":
                            valid = data.get("bridge") == "connected" and data.get("pending_count") == 0
                        else:
                            valid = data.get("complete") is True and bool(data.get("document_id"))
                            if valid:
                                record["xd_document_id"] = data["document_id"]
                    if valid and app == "illustrator":
                        coordinator = (data.get("connection") or {}).get("data") or {}
                        panel = (coordinator.get("layers") or {}).get("panel") or {}
                        valid = panel.get("status") == "ok" and panel.get("busy") is False
                        record["illustrator_panel_state"] = panel.get("status")
                        record["illustrator_blocked_at"] = coordinator.get("blockedAt")
                        record["illustrator_unresolved_jobs"] = ((coordinator.get("execution") or {}).get("unresolvedJobs") or [])
                        if record["illustrator_unresolved_jobs"]:
                            valid = False
                    if not valid:
                        record["rows"].append({"capability": capability, "sample": i + 1,
                                               "ms": elapsed, "success": False})
                        raise RuntimeError("WARM_READ_NOT_VERIFIED " + capability + " n=" + str(i + 1))
                    record["rows"].append({"capability": capability, "sample": i + 1,
                                           "ms": elapsed, "success": True})
                    timings.setdefault(capability, []).append(elapsed)
        record["statistics"] = {
            cap: {"n": len(vals), "p50_ms": percentile(vals, .5),
                  "p95_ms": percentile(vals, .95), "max_ms": max(vals)}
            for cap, vals in timings.items()
        }
        record["ok"] = True
    except BaseException as exc:
        record["error"] = type(exc).__name__ + ": " + str(exc)[:240]
    finally:
        record["elapsed_total_ms"] = round((time.perf_counter_ns() - started) / 1e6, 3)
        out = Path(os.environ.get("ADOBE_WARM_REPORT", "adobe_mcp_warm_report.json"))
        out.parent.mkdir(parents=True, exist_ok=True)
        temp = out.with_suffix(".tmp")
        temp.write_text(json.dumps(record, indent=2, ensure_ascii=True), encoding="utf-8")
        os.replace(temp, out)
        print("ADOBE_MCP_WARM_REPORT=" + json.dumps({
            k: v for k, v in record.items() if k not in ("rows",)
        }), flush=True)
    return record


def main() -> None:
    if os.environ.get("COMPUTERNAME") != "MRCAO":
        raise RuntimeError("WARM_SPEED_WRONG_RUNNER")
    if len(sys.argv) != 2:
        raise SystemExit("usage: python adobe_mcp_warm_single_session_probe.py [xd|illustrator|photoshop]")
    result = asyncio.run(probe(sys.argv[1]))
    if not result.get("ok"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
