# -*- coding: utf-8 -*-
"""Pure regression tests for PID/token-scoped selection GC log evidence."""

from __future__ import annotations

import base64
import json
import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
HELPER = ROOT / "tests" / "selection_gc_log_gate.ps1"
RUNNER = ROOT / "tests" / "run_selection_switch_gc_stress.ps1"
CRITICAL_PATTERN = r"MAXScript\s*内存收集错误"


def _ps_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class SelectionGcLogGateV1320Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = RUNNER.read_text(encoding="utf-8-sig")
        cls.helper = HELPER.read_text(encoding="utf-8-sig")

    def _run_window(
        self,
        text: str,
        *,
        pid: int,
        begin_pattern: str,
        end_pattern: str,
        structured: bool,
    ) -> subprocess.CompletedProcess[str]:
        encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
        structured_switch = " -StructuredMaxLog" if structured else ""
        command = (
            "$ErrorActionPreference='Stop';"
            "[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false);"
            f". {_ps_literal(str(HELPER))};"
            "$text=[Text.Encoding]::UTF8.GetString("
            f"[Convert]::FromBase64String('{encoded}'));"
            "$window=Get-F2MMarkerWindow "
            f"-Text $text -TargetPid {pid} "
            f"-BeginMessagePattern {_ps_literal(begin_pattern)} "
            f"-EndMessagePattern {_ps_literal(end_pattern)}"
            f"{structured_switch};"
            "$hits=@(Get-F2MCriticalLogHits "
            f"-Text $window.text -Patterns @({_ps_literal(CRITICAL_PATTERN)}));"
            "[pscustomobject]@{"
            "hit_count=$hits.Count;"
            "contains_old=$window.text.Contains('OLD_PID_ERROR');"
            "contains_current=$window.text.Contains('CURRENT_PID_ERROR');"
            "line_count=$window.line_count;"
            "post_end_line_count=$window.post_end_line_count;"
            "end_line_index=$window.end_line_index;"
            "scan_end_line_index=$window.scan_end_line_index"
            "}|ConvertTo-Json -Compress"
        )
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_rewritten_max_log_ignores_an_old_pid_error(self) -> None:
        text = "\r\n".join(
            [
                "2026/07/30 18:57:30 DBG: [35464] [00001] "
                "F2M_RAW_FBX_GC_BASELINE_BEGIN PID=35464 "
                "UTC=2026-07-30T10:57:30Z",
                "2026/07/30 18:59:05 WRN: [35464] [00001] "
                "OLD_PID_ERROR MAXScript 内存收集错误",
                "2026/07/30 19:00:10 DBG: [35464] [00001] "
                "F2M_RAW_FBX_GC_BASELINE_END PID=35464 "
                "UTC=2026-07-30T11:00:10Z OK=true",
                "2026/07/30 19:01:23 DBG: [14188] [00002] "
                "F2M_RAW_FBX_GC_BASELINE_BEGIN PID=14188 "
                "UTC=2026-07-30T11:01:23Z",
                "2026/07/30 19:02:00 INF: [14188] [00002] clean",
                "2026/07/30 19:03:17 DBG: [14188] [00002] "
                "F2M_RAW_FBX_GC_BASELINE_END PID=14188 "
                "UTC=2026-07-30T11:03:17Z OK=true",
            ]
        )
        completed = self._run_window(
            text,
            pid=14188,
            begin_pattern=(
                r"^F2M_RAW_FBX_GC_BASELINE_BEGIN\s+PID=14188"
                r"\s+UTC=\S+\s*$"
            ),
            end_pattern=(
                r"^F2M_RAW_FBX_GC_BASELINE_END\s+PID=14188"
                r"\s+UTC=\S+\s+OK=true\s*$"
            ),
            structured=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["hit_count"], 0)
        self.assertFalse(payload["contains_old"])
        self.assertFalse(payload["contains_current"])
        self.assertEqual(payload["line_count"], 3)

    def test_current_json_pid_error_is_a_critical_hit(self) -> None:
        text = "\r\n".join(
            [
                "2026/07/30 19:01:23 DBG: [14188] [00002] "
                "F2M_RAW_FBX_GC_BASELINE_BEGIN PID=14188 "
                "UTC=2026-07-30T11:01:23Z",
                "2026/07/30 19:02:00 WRN: [14188] [00002] "
                "CURRENT_PID_ERROR MAXScript 内存收集错误",
                "2026/07/30 19:03:17 DBG: [14188] [00002] "
                "F2M_RAW_FBX_GC_BASELINE_END PID=14188 "
                "UTC=2026-07-30T11:03:17Z OK=true",
            ]
        )
        completed = self._run_window(
            text,
            pid=14188,
            begin_pattern=(
                r"^F2M_RAW_FBX_GC_BASELINE_BEGIN\s+PID=14188"
                r"\s+UTC=\S+\s*$"
            ),
            end_pattern=(
                r"^F2M_RAW_FBX_GC_BASELINE_END\s+PID=14188"
                r"\s+UTC=\S+\s+OK=true\s*$"
            ),
            structured=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["hit_count"], 1)
        self.assertTrue(payload["contains_current"])

    def test_current_pid_error_after_end_is_a_critical_hit(self) -> None:
        text = "\r\n".join(
            [
                "2026/07/30 19:01:23 DBG: [14188] [00002] "
                "F2M_SELECTION_GC_STRESS_BEGIN TOKEN=currenttoken "
                "PID=14188 UTC=2026-07-30T11:01:23Z",
                "2026/07/30 19:02:00 INF: [14188] [00002] clean",
                "2026/07/30 19:03:17 DBG: [14188] [00002] "
                "F2M_SELECTION_GC_STRESS_END TOKEN=currenttoken "
                "PID=14188 UTC=2026-07-30T11:03:17Z OK=true",
                "2026/07/30 19:03:18 WRN: [35464] [00001] "
                "OLD_PID_ERROR MAXScript 内存收集错误",
                "2026/07/30 19:03:19 WRN: [14188] [00002] "
                "CURRENT_PID_ERROR MAXScript 内存收集错误",
                "2026/07/30 19:03:20 INF: [14188] [00002] shutdown",
            ]
        )
        completed = self._run_window(
            text,
            pid=14188,
            begin_pattern=(
                r"^F2M_SELECTION_GC_STRESS_BEGIN\s+TOKEN=currenttoken"
                r"\s+PID=14188\s+UTC=\S+\s*$"
            ),
            end_pattern=(
                r"^F2M_SELECTION_GC_STRESS_END\s+TOKEN=currenttoken"
                r"\s+PID=14188\s+UTC=\S+\s+OK=true\s*$"
            ),
            structured=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["hit_count"], 1)
        self.assertTrue(payload["contains_current"])
        self.assertFalse(payload["contains_old"])
        self.assertEqual(payload["post_end_line_count"], 2)
        self.assertGreater(
            payload["scan_end_line_index"],
            payload["end_line_index"],
        )

    def test_listener_slice_isolated_by_current_token_and_json_pid(self) -> None:
        old_token = "oldtoken"
        token = "currenttoken"
        text = "\r\n".join(
            [
                "F2M_SELECTION_GC_STRESS_BEGIN "
                f"TOKEN={old_token} PID=35464 UTC=2026-07-30T10:57:30Z",
                "OLD_PID_ERROR MAXScript 内存收集错误",
                "F2M_SELECTION_GC_STRESS_END "
                f"TOKEN={old_token} PID=35464 "
                "UTC=2026-07-30T11:00:10Z OK=true",
                "F2M_SELECTION_GC_STRESS_BEGIN "
                f"TOKEN={token} PID=14188 UTC=2026-07-30T11:01:23Z",
                "clean",
                "F2M_SELECTION_GC_STRESS_END "
                f"TOKEN={token} PID=14188 "
                "UTC=2026-07-30T11:03:17Z OK=true",
            ]
        )
        completed = self._run_window(
            text,
            pid=14188,
            begin_pattern=(
                r"^F2M_SELECTION_GC_STRESS_BEGIN\s+TOKEN=currenttoken"
                r"\s+PID=14188\s+UTC=\S+\s*$"
            ),
            end_pattern=(
                r"^F2M_SELECTION_GC_STRESS_END\s+TOKEN=currenttoken"
                r"\s+PID=14188\s+UTC=\S+\s+OK=true\s*$"
            ),
            structured=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["hit_count"], 0)
        self.assertFalse(payload["contains_old"])
        self.assertEqual(payload["line_count"], 3)

    def test_missing_end_marker_fails_closed(self) -> None:
        text = (
            "2026/07/30 19:01:23 DBG: [14188] [00002] "
            "F2M_RAW_FBX_GC_BASELINE_BEGIN PID=14188 "
            "UTC=2026-07-30T11:01:23Z"
        )
        completed = self._run_window(
            text,
            pid=14188,
            begin_pattern=(
                r"^F2M_RAW_FBX_GC_BASELINE_BEGIN\s+PID=14188"
                r"\s+UTC=\S+\s*$"
            ),
            end_pattern=(
                r"^F2M_RAW_FBX_GC_BASELINE_END\s+PID=14188"
                r"\s+UTC=\S+\s+OK=true\s*$"
            ),
            structured=True,
        )
        self.assertNotEqual(completed.returncode, 0)

    def test_missing_begin_marker_fails_closed(self) -> None:
        text = (
            "2026/07/30 19:03:17 DBG: [14188] [00002] "
            "F2M_RAW_FBX_GC_BASELINE_END PID=14188 "
            "UTC=2026-07-30T11:03:17Z OK=true"
        )
        completed = self._run_window(
            text,
            pid=14188,
            begin_pattern=(
                r"^F2M_RAW_FBX_GC_BASELINE_BEGIN\s+PID=14188"
                r"\s+UTC=\S+\s*$"
            ),
            end_pattern=(
                r"^F2M_RAW_FBX_GC_BASELINE_END\s+PID=14188"
                r"\s+UTC=\S+\s+OK=true\s*$"
            ),
            structured=True,
        )
        self.assertNotEqual(completed.returncode, 0)

    def test_duplicate_markers_fail_closed(self) -> None:
        duplicate_begin_text = "\r\n".join(
            [
                "2026/07/30 19:01:23 DBG: [14188] [00002] "
                "F2M_RAW_FBX_GC_BASELINE_BEGIN PID=14188 "
                "UTC=2026-07-30T11:01:23Z",
                "2026/07/30 19:01:24 DBG: [14188] [00002] "
                "F2M_RAW_FBX_GC_BASELINE_BEGIN PID=14188 "
                "UTC=2026-07-30T11:01:24Z",
                "2026/07/30 19:03:17 DBG: [14188] [00002] "
                "F2M_RAW_FBX_GC_BASELINE_END PID=14188 "
                "UTC=2026-07-30T11:03:17Z OK=true",
            ]
        )
        duplicate_end_text = "\r\n".join(
            [
                "2026/07/30 19:01:23 DBG: [14188] [00002] "
                "F2M_RAW_FBX_GC_BASELINE_BEGIN PID=14188 "
                "UTC=2026-07-30T11:01:23Z",
                "2026/07/30 19:03:17 DBG: [14188] [00002] "
                "F2M_RAW_FBX_GC_BASELINE_END PID=14188 "
                "UTC=2026-07-30T11:03:17Z OK=true",
                "2026/07/30 19:03:18 DBG: [14188] [00002] "
                "F2M_RAW_FBX_GC_BASELINE_END PID=14188 "
                "UTC=2026-07-30T11:03:18Z OK=true",
            ]
        )
        arguments = dict(
            pid=14188,
            begin_pattern=(
                r"^F2M_RAW_FBX_GC_BASELINE_BEGIN\s+PID=14188"
                r"\s+UTC=\S+\s*$"
            ),
            end_pattern=(
                r"^F2M_RAW_FBX_GC_BASELINE_END\s+PID=14188"
                r"\s+UTC=\S+\s+OK=true\s*$"
            ),
            structured=True,
        )
        for label, text in (
            ("duplicate BEGIN", duplicate_begin_text),
            ("duplicate END", duplicate_end_text),
        ):
            with self.subTest(label=label):
                completed = self._run_window(text, **arguments)
                self.assertNotEqual(completed.returncode, 0)

    def test_runner_scans_marker_windows_not_rewritten_byte_delta(self) -> None:
        self.assertIn(". $logGatePath", self.runner)
        self.assertIn("Read-F2MLogTextStrict -Path $rawAfterLogPath", self.runner)
        self.assertIn("Read-F2MLogTextStrict -Path $afterLogPath", self.runner)
        self.assertIn("-StructuredMaxLog", self.runner)
        self.assertIn("-Text $rawMaxWindowText", self.runner)
        self.assertIn("-Text $maxLogWindowText", self.runner)
        self.assertIn("-Text $listenerLogSlice", self.runner)
        self.assertIn("post_end_line_count", self.helper)
        self.assertIn("scan_end_line_index", self.helper)
        self.assertIn(
            "target_pid_last_structured_line_after_process_exit",
            self.runner,
        )
        self.assertNotIn("$rawLogText -match $pattern", self.runner)
        self.assertNotIn("$maxLogDeltaText -match $pattern", self.runner)
        self.assertIn("raw_listener_log_current_slice", self.runner)

    def test_strict_reader_rejects_missing_or_empty_logs(self) -> None:
        self.assertIn("Log file does not exist", self.helper)
        self.assertIn("Log file is unreadable", self.helper)
        self.assertIn("Log file is empty", self.helper)


if __name__ == "__main__":
    unittest.main()
