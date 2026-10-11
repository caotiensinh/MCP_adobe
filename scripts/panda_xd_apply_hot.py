"""Reuse one PowerShell UIA process for repeated, strictly single-shot XD Apply.

Each call still targets the unique real XD document and exact menu command.
The *caller* must verify one owned queue item before applying and its receipt
after applying. A timeout or unknown result means STOP, never retry blindly.
"""
from __future__ import annotations

import atexit
import os
import queue
import subprocess
import threading
import time
from pathlib import Path

READY = "XD_HOT_READY"
APPLIED = "XD_HOT_APPLIED:ONCE"
UNKNOWN = "XD_HOT_UNKNOWN:"
WORKER = Path(__file__).with_name("panda_xd_apply_hot_worker.ps1")
TIMEOUT_SECONDS = 22.0


class HotApplyFailure(RuntimeError):
    """Worker status is absent/uncertain; inspect the Adobe receipt before replay."""


class HotApplyWorker:
    def __init__(self, *, timeout_seconds: float = TIMEOUT_SECONDS):
        if not os.getenv("PANDA_XD_SOURCE_RUN_ID", "").isdigit():
            raise HotApplyFailure("XD_APPLY_WORKER_SOURCE_DOCUMENT_NOT_SPECIFIED")
        self.timeout_seconds = timeout_seconds
        self._messages: queue.Queue[str] = queue.Queue()
        self._unsafe = False
        self._closed = False
        self._process = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-File", str(WORKER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        if self._process.stdout is None or self._process.stdin is None:
            self._unsafe = True
            raise HotApplyFailure("XD_APPLY_WORKER_MISSING_PIPES")
        threading.Thread(target=self._read_output, name="xd-apply-read", daemon=True).start()
        self._expect(READY, min(timeout_seconds, 12.0))

    def _read_output(self) -> None:
        try:
            for line in self._process.stdout:
                self._messages.put(line.strip())
        except Exception as exc:
            self._messages.put("XD_HOT_UNKNOWN:stdout-" + type(exc).__name__)
        finally:
            self._messages.put("XD_HOT_UNKNOWN:worker-output-closed")

    def _expect(self, token: str, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._unsafe = True
                raise HotApplyFailure("XD_APPLY_WORKER_TIMEOUT_UNKNOWN_NO_REPLAY")
            try:
                line = self._messages.get(timeout=remaining)
            except queue.Empty as exc:
                self._unsafe = True
                raise HotApplyFailure("XD_APPLY_WORKER_TIMEOUT_UNKNOWN_NO_REPLAY") from exc
            if line == token:
                return
            if line.startswith("XD_HOT_UNKNOWN:") or line.startswith("XD_HOT_ERROR:"):
                self._unsafe = True
                raise HotApplyFailure("XD_APPLY_WORKER_UNKNOWN_NO_REPLAY " + line[:350])
            # PowerShell may emit an informational startup banner; no command
            # is sent in response to any unknown worker output.

    def apply_once(self) -> None:
        if self._closed or self._unsafe or self._process.poll() is not None:
            raise HotApplyFailure("XD_APPLY_WORKER_NOT_SAFE_NO_REPLAY")
        assert self._process.stdin is not None
        # On any I/O exception the previous command may still have reached UIA.
        self._unsafe = True
        try:
            self._process.stdin.write("APPLY\n")
            self._process.stdin.flush()
            self._expect(APPLIED, self.timeout_seconds)
        except Exception as exc:
            raise HotApplyFailure("XD_APPLY_STATUS_UNKNOWN_NO_REPLAY: " + str(exc)[:350]) from exc
        self._unsafe = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._process.poll() is None:
            try:
                assert self._process.stdin is not None
                self._process.stdin.write("STOP\n")
                self._process.stdin.flush()
                self._process.wait(timeout=1.5)
            except (OSError, subprocess.TimeoutExpired):
                self._process.terminate()  # Only this worker, never Adobe.
                try:
                    self._process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    self._process.kill()  # Orphaned helper only; never host.
            finally:
                if self._process.stdin:
                    self._process.stdin.close()


_worker: HotApplyWorker | None = None
_worker_lock = threading.Lock()


def apply_one() -> None:
    """Invoke one verified XD UXP Apply without launching PowerShell per stroke."""
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = HotApplyWorker()
        _worker.apply_once()


def shutdown() -> None:
    global _worker
    with _worker_lock:
        if _worker is not None:
            _worker.close()
            _worker = None


atexit.register(shutdown)
