# -*- coding: utf-8 -*-
"""Pure-Python regression tests for the post-exit native Max.log gate."""

from __future__ import annotations

import importlib.util
import os
import pathlib
import re
import sys
import tempfile
import time
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "contents" / "f2m_selfcheck.py"


def load_selfcheck():
    name = "_f2m_selfcheck_max_log_gate_test"
    spec = importlib.util.spec_from_file_location(name, str(MODULE_PATH))
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载自检模块。")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def max_log_line(pid: int, message: str, *, stamp: str = "") -> str:
    timestamp = stamp or time.strftime("%Y/%m/%d %H:%M:%S")
    return f"{timestamp} WRN: [{pid}] [1234] {message}\r\n"


def append_gb18030(path: str, text: str) -> None:
    with open(path, "ab") as handle:
        handle.write(text.encode("gb18030"))
        handle.flush()
        os.fsync(handle.fileno())


class FakeProcess:
    def __init__(self, pid: int, return_code=None) -> None:
        self.pid = pid
        self.return_code = return_code

    def poll(self):
        return self.return_code


class FakeLabel:
    def __init__(self) -> None:
        self.text = ""

    def setText(self, value) -> None:
        self.text = str(value)


class NativeMaxLogGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_selfcheck()

    def test_old_errors_and_other_processes_do_not_fail_current_run(self) -> None:
        child_pid = 43120
        with tempfile.TemporaryDirectory() as folder:
            log_path = os.path.join(folder, "Max.log")
            append_gb18030(
                log_path,
                max_log_line(child_pid, "MAXScript 内存收集错误: 历史错误"),
            )
            checkpoint = self.module._capture_max_log_checkpoint(log_path)
            started_at = time.time()
            append_gb18030(
                log_path,
                max_log_line(child_pid, "本次普通日志")
                + max_log_line(99999, "MAXScript 内存收集错误: 其它进程"),
            )

            audit = self.module._inspect_max_log_since(
                checkpoint,
                child_pid=child_pid,
                process_started_at=started_at,
                process_finished_at=time.time(),
            )

        self.assertTrue(audit["checked"])
        self.assertEqual(audit["pid_line_count"], 1)
        self.assertEqual(audit["gc_error_count"], 0)

    def test_truncation_or_replacement_restarts_from_zero_safely(self) -> None:
        child_pid = 43121
        with tempfile.TemporaryDirectory() as folder:
            log_path = os.path.join(folder, "Max.log")
            append_gb18030(log_path, max_log_line(100, "历史普通日志") * 4)
            checkpoint = self.module._capture_max_log_checkpoint(log_path)
            started_at = time.time()
            pathlib.Path(log_path).write_bytes(
                (
                    max_log_line(child_pid, "本次普通日志")
                    + max_log_line(
                        child_pid,
                        "MAXScript Garbage Collection Error: simulated",
                    )
                ).encode("gb18030")
            )

            audit = self.module._inspect_max_log_since(
                checkpoint,
                child_pid=child_pid,
                process_started_at=started_at,
                process_finished_at=time.time(),
            )

        self.assertTrue(audit["checked"])
        self.assertEqual(audit["effective_offset"], 0)
        self.assertEqual(audit["gc_error_count"], 1)

    def test_out_of_window_pid_line_cannot_validate_wrong_log(self) -> None:
        child_pid = 43122
        with tempfile.TemporaryDirectory() as folder:
            log_path = os.path.join(folder, "Max.log")
            checkpoint = self.module._capture_max_log_checkpoint(log_path)
            append_gb18030(
                log_path,
                max_log_line(
                    child_pid,
                    "MAXScript 内存收集错误: 过期日志",
                    stamp="2000/01/01 00:00:00",
                ),
            )
            now = time.time()
            audit = self.module._inspect_max_log_since(
                checkpoint,
                child_pid=child_pid,
                process_started_at=now - 1,
                process_finished_at=now,
            )

        self.assertFalse(audit["checked"])
        self.assertEqual(audit["gc_error_count"], 0)
        self.assertIn("PID", audit["error"])

    def test_green_business_result_is_rejected_only_after_child_exit(self) -> None:
        launcher_pid = 43123
        child_pid = 43125
        controller = self.module._AsyncSelfCheckController.__new__(
            self.module._AsyncSelfCheckController
        )
        controller.process = FakeProcess(launcher_pid)
        controller.finished = False
        controller.cancel_requested = False
        controller.cancel_started_at = 0.0
        controller.timed_out = False
        controller.started_at = time.monotonic()
        controller.completed_result = None
        controller.result_seen_at = 0.0
        controller.completion_stop_requested = False
        controller.max_log_child_pid = 0
        controller.state_label = FakeLabel()
        controller.terminator = None
        controller._update_progress = mock.Mock()
        controller._close_output = mock.Mock()
        controller._finish = mock.Mock()

        with tempfile.TemporaryDirectory() as folder:
            controller.paths = {
                "result": os.path.join(folder, "result.json"),
                "progress": os.path.join(folder, "progress.json"),
                "cancel": os.path.join(folder, "cancel.json"),
                "output": os.path.join(folder, "batch.log"),
            }
            report_path = os.path.join(folder, "自检报告.txt")
            pathlib.Path(report_path).write_text(
                "FBXTo3dsMax v1.4.24 自检通过：6/6 项通过。\n",
                encoding="utf-8",
            )
            log_path = os.path.join(folder, "Max.log")
            controller.max_log_checkpoint = (
                self.module._capture_max_log_checkpoint(log_path)
            )
            controller.process_started_wall_time = time.time()
            append_gb18030(log_path, max_log_line(child_pid, "本次普通日志"))
            self.module._atomic_write_json(
                controller.paths["progress"],
                {"child_pid": child_pid},
            )
            self.module._atomic_write_json(
                controller.paths["result"],
                {
                    "ok": True,
                    "summary": "自检通过：6/6 项通过。",
                    "report_path": report_path,
                    "passed": 6,
                    "total": 6,
                },
            )

            controller._poll()
            controller._finish.assert_not_called()
            self.assertIsNotNone(controller.completed_result)

            append_gb18030(
                log_path,
                max_log_line(
                    child_pid,
                    "MAXScript 内存收集错误: 退出阶段错误",
                ),
            )
            controller.process.return_code = 0
            controller._poll()

            final = controller._finish.call_args.args[0]
            rewritten_report = pathlib.Path(report_path).read_text(
                encoding="utf-8"
            )

        self.assertFalse(final["ok"])
        self.assertTrue(final["business_result_ok"])
        self.assertTrue(final["native_max_log_checked"])
        self.assertEqual(
            final["native_max_log_audit"]["child_pid"],
            child_pid,
        )
        self.assertEqual(final["native_max_log_gc_error_count"], 1)
        self.assertTrue(final["child_process_natural_exit"])
        self.assertTrue(final["child_process_exit_gate_passed"])
        self.assertEqual(final["child_process_exit_code"], 0)
        self.assertIn("子进程完全退出后", final["summary"])
        self.assertIn("内存收集错误", final["summary"])
        self.assertTrue(controller._finish.call_args.kwargs["keep_output"])
        self.assertTrue(rewritten_report.startswith("【父控制器最终判定】"))
        self.assertIn("自检失败", rewritten_report)

    def test_clean_log_cannot_hide_forced_completion_stop(self) -> None:
        launcher_pid = 43126
        child_pid = 43127
        controller = self.module._AsyncSelfCheckController.__new__(
            self.module._AsyncSelfCheckController
        )
        controller.process = FakeProcess(launcher_pid, return_code=0)
        controller.finished = False
        controller.cancel_requested = False
        controller.cancel_started_at = 0.0
        controller.timed_out = False
        controller.started_at = time.monotonic()
        controller.completed_result = {
            "ok": True,
            "summary": "自检通过：6/6 项通过。",
            "passed": 6,
            "total": 6,
        }
        controller.result_seen_at = time.monotonic()
        controller.completion_stop_requested = True
        controller.max_log_child_pid = child_pid
        controller.state_label = FakeLabel()
        controller.terminator = None
        controller._update_progress = mock.Mock()
        controller._close_output = mock.Mock()
        controller._finish = mock.Mock()

        with tempfile.TemporaryDirectory() as folder:
            report_path = os.path.join(folder, "自检报告.txt")
            pathlib.Path(report_path).write_text(
                "FBXTo3dsMax v1.4.24 自检通过：6/6 项通过。\n",
                encoding="utf-8",
            )
            controller.completed_result["report_path"] = report_path
            controller.paths = {
                "result": os.path.join(folder, "result.json"),
                "progress": os.path.join(folder, "progress.json"),
                "cancel": os.path.join(folder, "cancel.json"),
                "output": os.path.join(folder, "batch.log"),
            }
            log_path = os.path.join(folder, "Max.log")
            controller.max_log_checkpoint = (
                self.module._capture_max_log_checkpoint(log_path)
            )
            controller.process_started_wall_time = time.time()
            append_gb18030(log_path, max_log_line(child_pid, "本次普通日志"))

            controller._poll()
            final = controller._finish.call_args.args[0]
            rewritten_report = pathlib.Path(report_path).read_text(
                encoding="utf-8"
            )

        self.assertTrue(final["business_result_ok"])
        self.assertTrue(final["native_max_log_checked"])
        self.assertEqual(final["native_max_log_gc_error_count"], 0)
        self.assertFalse(final["ok"])
        self.assertFalse(final["child_process_natural_exit"])
        self.assertFalse(final["child_process_exit_gate_passed"])
        self.assertTrue(final["child_process_completion_stop_requested"])
        self.assertEqual(final["child_process_exit_code"], 0)
        self.assertIn("强制结束", final["summary"])
        self.assertEqual(final["report_path"], report_path)
        self.assertEqual(
            final["diagnostic_output"],
            controller.paths["output"],
        )
        self.assertTrue(controller._finish.call_args.kwargs["keep_output"])
        self.assertTrue(rewritten_report.startswith("【父控制器进程退出门禁】"))
        self.assertIn("FBXTo3dsMax v1.4.24 自检通过", rewritten_report)

    def test_unreadable_native_log_cannot_leave_green_result(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            missing_path = os.path.join(folder, "missing", "Max.log")
            audit = self.module._inspect_max_log_since(
                self.module._capture_max_log_checkpoint(missing_path),
                child_pid=43124,
                process_started_at=time.time() - 1,
                process_finished_at=time.time(),
            )
            final = self.module._apply_native_max_log_gate(
                {
                    "ok": True,
                    "summary": "自检通过：6/6 项通过。",
                    "report_path": "",
                },
                audit,
            )

        self.assertFalse(final["ok"])
        self.assertFalse(final["native_max_log_checked"])
        self.assertIn("无法核验", final["summary"])
        self.assertIn("内存收集错误", final["summary"])


class PowerShellRunnerPidPaddingTests(unittest.TestCase):
    def test_all_direct_max_log_pid_runners_allow_leading_zeroes(self) -> None:
        runner_expressions = {
            "run_topology_fbx_gc_gate_v1320.ps1": "([string]$enginePid)",
            "run_source_selfcheck_v1320.ps1": "([string]$enginePid)",
            "run_procedural_gc_gate_v1320.ps1": "([string]$enginePid)",
            "run_mode2_target_authority_v1320.ps1": "([string]$enginePid)",
            "run_hybrid_normals_equivalence_v1320.ps1": (
                "([int]$result.pid).ToString()"
            ),
        }
        tests_root = ROOT / "tests"

        for runner_name, escaped_expression in runner_expressions.items():
            with self.subTest(runner=runner_name):
                source = (tests_root / runner_name).read_text(
                    encoding="utf-8-sig"
                )
                normalized = "\n".join(
                    line.strip() for line in source.splitlines()
                )
                expected = (
                    "$pidPattern = '\\[0*' +\n"
                    f"[regex]::Escape({escaped_expression}) +\n"
                    "'\\]'"
                )
                self.assertIn(expected, normalized)

        legacy_exact_pattern = re.compile(
            r"\$pidPattern\s*=\s*'\\\['\s*\+\s*"
            r"\[regex\]::Escape"
        )
        self.assertIsNotNone(
            legacy_exact_pattern.search(
                "$pidPattern = '\\[' + [regex]::Escape('6044')"
            )
        )
        for runner_path in tests_root.glob("*.ps1"):
            with self.subTest(no_unpadded_pattern=runner_path.name):
                source = runner_path.read_text(encoding="utf-8-sig")
                self.assertIsNone(legacy_exact_pattern.search(source))

    def test_padded_pid_pattern_keeps_square_bracket_boundaries(self) -> None:
        pattern = re.compile(r"\[0*6044\]")

        for value in ("[6044]", "[06044]", "[0000006044]"):
            with self.subTest(accepted=value):
                self.assertIsNotNone(pattern.fullmatch(value))

        for value in ("6044", "[60440]", "[16044]", "[06044x]"):
            with self.subTest(rejected=value):
                self.assertIsNone(pattern.search(value))


if __name__ == "__main__":
    unittest.main()
