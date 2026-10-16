"""Mock contract and regression tests; no real Adobe GUI is touched here."""
from __future__ import annotations

import os
import queue
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import panda_xd_apply_hot as hot


class FakeOutput:
    def __init__(self, events):
        self.events = events

    def __iter__(self):
        return self

    def __next__(self):
        line = self.events.get(timeout=2)
        if line is None:
            raise StopIteration
        return line + "\n"


class FakeInput:
    def __init__(self, proc):
        self.proc = proc

    def write(self, text):
        self.proc.commands.append(text)
        if text == "APPLY\n":
            if self.proc.ack is not None:
                self.proc.events.put(self.proc.ack)
        elif text == "PING\n":
            self.proc.events.put("XD_HOT_PONG")
        elif text == "STOP\n":
            self.proc.events.put(None)
        return len(text)

    def flush(self):
        pass

    def close(self):
        pass


class FakeProcess:
    def __init__(self, ack=hot.APPLIED):
        self.ack = ack
        self.events = queue.Queue()
        self.events.put(hot.READY)
        self.stdin = FakeInput(self)
        self.stdout = FakeOutput(self.events)
        self.commands = []
        self.exitcode = None
        self.terminated = False

    def poll(self):
        return self.exitcode

    def wait(self, timeout=None):
        self.exitcode = 0
        return 0

    def terminate(self):
        self.terminated = True
        self.events.put(None)
        self.exitcode = 1

    def kill(self):
        self.terminate()


class HotXdApplyTests(unittest.TestCase):
    def tearDown(self):
        hot.shutdown()

    def test_one_powershell_process_for_multiple_individually_acknowledged_strokes(self):
        fake = FakeProcess()
        with patch.dict(os.environ, {"PANDA_XD_SOURCE_RUN_ID": "38136531800"}):
            with patch.object(subprocess, "Popen", return_value=fake) as spawn:
                hot.apply_one()
                hot.apply_one()
                self.assertEqual(spawn.call_count, 1)
                self.assertEqual(fake.commands, ["APPLY\n", "APPLY\n"])
                self.assertEqual(spawn.call_args.args[0][0], "powershell")
                hot.shutdown()
                self.assertEqual(fake.commands[-1], "STOP\n")

    def test_reused_process_read_only_ping_without_any_apply(self):
        fake = FakeProcess()
        with patch.dict(os.environ, {"PANDA_XD_SOURCE_RUN_ID": "38136531800"}):
            with patch.object(subprocess, "Popen", return_value=fake) as spawn:
                worker = hot.HotApplyWorker(timeout_seconds=0.5)
                try:
                    samples = [worker.ping_once() for _ in range(12)]
                    self.assertTrue(all(value >= 0 for value in samples))
                    self.assertEqual(spawn.call_count, 1)
                    self.assertEqual(fake.commands, ["PING\n"] * 12)
                    self.assertFalse(any("APPLY" in cmd for cmd in fake.commands))
                finally:
                    worker.close()

    def test_ambiguous_invocation_is_not_replayed(self):
        fake = FakeProcess(ack="XD_HOT_UNKNOWN:APPLY_MENU_AMBIGUOUS")
        with patch.dict(os.environ, {"PANDA_XD_SOURCE_RUN_ID": "38136531800"}):
            with patch.object(subprocess, "Popen", return_value=fake) as spawn:
                with self.assertRaisesRegex(hot.HotApplyFailure, "UNKNOWN_NO_REPLAY"):
                    hot.apply_one()
                with self.assertRaisesRegex(hot.HotApplyFailure, "NOT_SAFE_NO_REPLAY"):
                    hot.apply_one()
                self.assertEqual(fake.commands, ["APPLY\n"])
                self.assertEqual(spawn.call_count, 1)

    def test_timeout_is_unknown_not_automatic_retry(self):
        fake = FakeProcess(ack=None)
        with patch.dict(os.environ, {"PANDA_XD_SOURCE_RUN_ID": "38136531800"}):
            with patch.object(subprocess, "Popen", return_value=fake):
                worker = hot.HotApplyWorker(timeout_seconds=0.08)
                try:
                    with self.assertRaisesRegex(hot.HotApplyFailure, "UNKNOWN_NO_REPLAY"):
                        worker.apply_once()
                    with self.assertRaisesRegex(hot.HotApplyFailure, "NOT_SAFE_NO_REPLAY"):
                        worker.apply_once()
                    self.assertEqual(fake.commands, ["APPLY\n"])
                finally:
                    worker.close()

    def test_cannot_start_without_verified_target_document_id(self):
        with patch.dict(os.environ, {"PANDA_XD_SOURCE_RUN_ID": ""}):
            with patch.object(subprocess, "Popen") as spawn:
                with self.assertRaisesRegex(hot.HotApplyFailure, "SOURCE_DOCUMENT_NOT_SPECIFIED"):
                    hot.HotApplyWorker()
                spawn.assert_not_called()

    def test_single_ui_action_and_no_host_process_restart_in_worker(self):
        body = Path("scripts/panda_xd_apply_hot_worker.ps1").read_text(encoding="utf-8")
        self.assertIn("'XD_HOT_APPLIED:ONCE'", body)
        self.assertIn("$invoke.Invoke()", body)
        self.assertIn("[Console]::ReadLine()", body)
        self.assertNotIn("Start-Process", body)
        self.assertNotIn("Stop-Process", body)
        self.assertNotIn("XD_APPLY_REAL_PLUGIN_MENU_INVOKED=ONCE", body)


if __name__ == "__main__":
    unittest.main()
