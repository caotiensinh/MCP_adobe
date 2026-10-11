"""Actual MRCAO hot PowerShell host RTT with ZERO Adobe document operations."""
from __future__ import annotations

import hashlib
import json
import os
import statistics
import time
from pathlib import Path

from panda_xd_apply_hot import HotApplyWorker

ROOT = Path(os.environ["USERPROFILE"]) / "Documents" / "MCPAdobe"
NATIVE = ROOT / "MCP_Mode1_Panda_XD_38136531800.xd"
EXPECTED = "3a10e1510abc41eccd4485d6f852ea6ced7acc2cf50109e7c1bd123353589ed1"


def checksum() -> str:
    if not NATIVE.is_file():
        raise RuntimeError("XD_HOT_BENCH_SOURCE_NOT_FOUND")
    return hashlib.sha256(NATIVE.read_bytes()).hexdigest()


def percentile(samples: list[float], p: float) -> float:
    ordered = sorted(samples)
    x = (len(ordered) - 1) * p
    low = int(x)
    return round(ordered[low] + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low]) * (x - low), 3)


def main() -> None:
    if os.getenv("COMPUTERNAME") != "MRCAO" or os.getenv("PANDA_XD_SOURCE_RUN_ID") != "38136531800":
        raise RuntimeError("XD_HOT_BENCH_MACHINE_OR_DOCUMENT_INVALID")
    before = checksum()
    if before != EXPECTED:
        raise RuntimeError("XD_HOT_BENCH_NATIVE_SHA_MISMATCH_NO_HOST_ACTION")
    t0 = time.perf_counter()
    with_worker = HotApplyWorker()
    startup_ms = (time.perf_counter() - t0) * 1000
    try:
        ping_ms = [with_worker.ping_once() for _ in range(40)]
    finally:
        with_worker.close()
    after = checksum()
    if after != before:
        raise RuntimeError("XD_HOT_BENCH_NATIVE_MUTATED_STOP")
    results = {
        "schema": "mcp-adobe-hot-worker-readonly/v1",
        "host": os.getenv("COMPUTERNAME"),
        "run": os.getenv("GITHUB_RUN_ID"),
        "startup_ms": round(startup_ms, 3),
        "warm_ping": {
            "samples": len(ping_ms), "success": len(ping_ms),
            "p50_ms": percentile(ping_ms, .50),
            "p95_ms": percentile(ping_ms, .95),
            "p99_ms": percentile(ping_ms, .99),
            "max_ms": round(max(ping_ms), 3)
        },
        "source_sha_before": before,
        "source_sha_after": after,
        "adobe_queued_writes": 0,
        "adobe_apply_invocations": 0,
        "note": "IPC-only benchmark; NOT shape-write+readback or end-to-end image latency."
    }
    Path("xd_apply_hot_benchmark.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("XD_APPLY_HOT_READONLY_BENCHMARK=" + json.dumps(results), flush=True)


if __name__ == "__main__":
    main()
