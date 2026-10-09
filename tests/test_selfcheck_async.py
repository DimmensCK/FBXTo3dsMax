# -*- coding: utf-8 -*-
"""Focused pure-Python checks for the modeless self-check control plane."""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import time
import unittest
import builtins
import contextlib
import io
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "contents" / "f2m_selfcheck.py"
UI_PATH = ROOT / "contents" / "FBXTo3dsMax_UI.ms"


def load_selfcheck():
    name = "_f2m_selfcheck_async_test"
    spec = importlib.util.spec_from_file_location(name, str(MODULE_PATH))
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载自检模块。")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeRuntime:
    def __init__(self) -> None:
        self.reset_count = 0
        self.objects = []

    @staticmethod
    def Name(value):
        return value

    def resetMaxFile(self, _mode):
        self.reset_count += 1
        self.objects.clear()

    @staticmethod
    def execute(_source):
        return True

    @staticmethod
    def clearSelection():
        return None


class FakeProcess:
    def __init__(self, pid: int = 43210, return_code=None) -> None:
        self.pid = pid
        self.return_code = return_code
        self.killed = False

    def poll(self):
        return self.return_code

    def kill(self):
        self.killed = True
        self.return_code = -9

    def wait(self, timeout=None):
        if self.return_code is None:
            raise TimeoutError(f"still running after {timeout}")
        return self.return_code


class FakeLabel:
    def __init__(self) -> None:
        self.text = ""

    def setText(self, value) -> None:
        self.text = str(value)


class FakeButton:
    def __init__(self) -> None:
        self.enabled = True

    def setEnabled(self, value) -> None:
        self.enabled = bool(value)


class FakeSignal:
    def __init__(self) -> None:
        self.disconnect_calls = 0

    def disconnect(self, _callback) -> None:
        self.disconnect_calls += 1


class FakeTimer:
    def __init__(self) -> None:
        self.stop_calls = 0
        self.start_calls = 0
        self.timeout = FakeSignal()

    def stop(self) -> None:
        self.stop_calls += 1

    def start(self) -> None:
        self.start_calls += 1


class FakeDialog:
    def __init__(self) -> None:
        self.hide_calls = 0
        self.show_calls = 0
        self.raise_calls = 0
        self.close_calls = 0

    def hide(self) -> None:
        self.hide_calls += 1

    def show(self) -> None:
        self.show_calls += 1

    def raise_(self) -> None:
        self.raise_calls += 1

    def close(self) -> None:
        self.close_calls += 1


class FakeApplication:
    def __init__(self) -> None:
        self.aboutToQuit = FakeSignal()


class AsyncSelfCheckTests(unittest.TestCase):
    def test_installed_manifest_requires_exact_32_target_set(self) -> None:
        selfcheck = load_selfcheck()
        with tempfile.TemporaryDirectory() as folder:
            package_root = pathlib.Path(folder) / "FBXTo3dsMax"
            contents = package_root / "contents"
            contents.mkdir(parents=True)
            targets = [
                "PackageContents.xml",
                "contents\\FBXTo3dsMax.files",
            ] + [
                f"contents\\fixture_{index:02d}.bin"
                for index in range(2, 32)
            ]
            mapping_path = contents / "FBXTo3dsMax.files"
            mapping_path.write_text(
                "\n".join(
                    f"source_{index:02d}|{target}"
                    for index, target in enumerate(targets)
                )
                + "\n",
                encoding="utf-8",
            )
            for index, target in enumerate(targets):
                target_path = package_root.joinpath(*target.split("\\"))
                if target_path == mapping_path:
                    continue
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_bytes(f"fixture-{index}".encode("ascii"))

            manifest_path = (
                contents / "FBXTo3dsMax.install-manifest.sha256"
            )

            def valid_lines():
                return [
                    f"{target}|{selfcheck._sha256(str(package_root.joinpath(*target.split(chr(92)))))}"
                    for target in targets
                ]

            lines = valid_lines()
            manifest_path.write_text(
                "\n".join(lines) + "\n",
                encoding="utf-8",
            )
            with mock.patch.object(selfcheck, "ROOT", str(contents)):
                result = selfcheck._verify_installed_manifest()
                self.assertIn("32 项全部匹配", result)

                manifest_path.write_text(lines[0] + "\n", encoding="utf-8")
                with self.assertRaisesRegex(
                    RuntimeError,
                    "记录数量错误",
                ):
                    selfcheck._verify_installed_manifest()

                duplicate_lines = list(lines)
                duplicate_lines[1] = duplicate_lines[0]
                manifest_path.write_text(
                    "\n".join(duplicate_lines) + "\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(RuntimeError, "目标路径重复"):
                    selfcheck._verify_installed_manifest()

                invalid_hash_lines = list(lines)
                invalid_hash_lines[0] = (
                    invalid_hash_lines[0].split("|", 1)[0] + "|" + "x" * 64
                )
                manifest_path.write_text(
                    "\n".join(invalid_hash_lines) + "\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(
                    RuntimeError,
                    "SHA-256 格式错误",
                ):
                    selfcheck._verify_installed_manifest()

    def setUp(self) -> None:
        self.module = load_selfcheck()

    def test_atomic_progress_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "progress.json")
            self.module._atomic_write_json(path, {"状态": "正在运行", "完成": 2})
            with open(path, "r", encoding="utf-8") as handle:
                value = json.load(handle)
            self.assertEqual(value, {"状态": "正在运行", "完成": 2})
            self.assertEqual(list(pathlib.Path(folder).glob("*.tmp-*")), [])

    def test_invalid_child_context_never_enters_scene_runner(self) -> None:
        keys = (
            self.module.CHILD_ENV,
            self.module.RESULT_ENV,
            self.module.PROGRESS_ENV,
            self.module.CANCEL_ENV,
        )
        clean_environment = {key: os.environ.get(key) for key in keys}
        try:
            for key in keys:
                os.environ.pop(key, None)
            with mock.patch.object(self.module, "_run_isolated") as isolated:
                with self.assertRaisesRegex(RuntimeError, "已拒绝"):
                    self.module._child_entry()
                isolated.assert_not_called()
        finally:
            for key, value in clean_environment.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_six_cases_publish_atomic_chinese_progress(self) -> None:
        fake_runtime = FakeRuntime()
        callback_names = (
            "_module_check",
            "_algorithm_check",
            "_procedural_max_check",
            "_normal_safety_check",
            "_topology_fbx_check",
            "_skin_fbx_check",
        )
        patches = [
            mock.patch.object(self.module, name, return_value="通过")
            for name in callback_names
        ]
        with tempfile.TemporaryDirectory() as folder:
            progress = os.path.join(folder, "progress.json")
            cancel = os.path.join(folder, "cancel.json")
            with mock.patch.object(self.module, "rt", fake_runtime), mock.patch.object(
                self.module,
                "_write_report",
                return_value={
                    "ok": True,
                    "summary": "自检通过：6/6 项通过。",
                    "report_path": "报告.txt",
                    "passed": 6,
                    "total": 6,
                },
            ):
                for patcher in patches:
                    patcher.start()
                try:
                    result = self.module._run_isolated(progress, cancel)
                finally:
                    for patcher in reversed(patches):
                        patcher.stop()
            self.assertTrue(result["ok"])
            self.assertEqual(fake_runtime.reset_count, 1)
            state = self.module._read_json_if_ready(progress)
            self.assertIsNotNone(state)
            self.assertEqual(state["completed"], 6)
            self.assertEqual(state["total"], 6)

    def test_report_uses_chinese_status_and_units(self) -> None:
        checks = [
            self.module.Check(
                "显式法线",
                True,
                "plain: PASS - plain mesh rejected; selection and temporary stack restored",
                23,
            ),
            self.module.Check(
                "光滑组",
                False,
                "FAIL",
                7,
                diagnostic="Traceback: internal detail",
            ),
        ]
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(
            self.module, "_report_folder", return_value=folder
        ):
            result = self.module._write_report(checks, "test")
            text = pathlib.Path(result["report_path"]).read_text(encoding="utf-8")
            diagnostic = pathlib.Path(
                result["diagnostic_report_path"]
            ).read_text(encoding="utf-8")
        self.assertIn("[通过] 显式法线（23 毫秒）", text)
        self.assertIn("[失败] 光滑组（7 毫秒）", text)
        self.assertIn("普通自动法线", text)
        self.assertNotIn("[PASS]", text)
        self.assertNotIn("[FAIL]", text)
        self.assertNotIn(" ms)", text)
        self.assertNotIn("Traceback", text)
        self.assertTrue(result["diagnostic_report_path"])
        self.assertIn("自检内部诊断", diagnostic)
        self.assertIn("Traceback: internal detail", diagnostic)

    def test_uncaught_framework_error_persists_traceback(self) -> None:
        keys = (
            self.module.CHILD_ENV,
            self.module.RESULT_ENV,
            self.module.PROGRESS_ENV,
            self.module.CANCEL_ENV,
        )
        previous = {key: os.environ.get(key) for key in keys}
        try:
            with tempfile.TemporaryDirectory() as folder:
                result_path = os.path.join(folder, "result.json")
                progress_path = os.path.join(folder, "progress.json")
                cancel_path = os.path.join(folder, "cancel.json")
                os.environ[self.module.CHILD_ENV] = "1"
                os.environ[self.module.RESULT_ENV] = result_path
                os.environ[self.module.PROGRESS_ENV] = progress_path
                os.environ[self.module.CANCEL_ENV] = cancel_path
                stderr = io.StringIO()
                with mock.patch.object(
                    self.module,
                    "_run_isolated",
                    side_effect=RuntimeError("模拟框架错误"),
                ), contextlib.redirect_stderr(stderr):
                    self.module._child_entry()

                result = self.module._read_json_if_ready(result_path)
                self.assertIsNotNone(result)
                diagnostic_path = pathlib.Path(result["diagnostic_report_path"])
                self.assertTrue(diagnostic_path.is_file())
                diagnostic = diagnostic_path.read_text(encoding="utf-8")
                self.assertIn("模拟框架错误", diagnostic)
                self.assertIn("Traceback", diagnostic)
                self.assertIn("模拟框架错误", stderr.getvalue())
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_child_flushes_result_and_completed_progress(self) -> None:
        keys = (
            self.module.CHILD_ENV,
            self.module.RESULT_ENV,
            self.module.PROGRESS_ENV,
            self.module.CANCEL_ENV,
        )
        previous = {key: os.environ.get(key) for key in keys}
        try:
            with tempfile.TemporaryDirectory() as folder:
                result_path = os.path.join(folder, "result.json")
                progress_path = os.path.join(folder, "progress.json")
                cancel_path = os.path.join(folder, "cancel.json")
                os.environ[self.module.CHILD_ENV] = "1"
                os.environ[self.module.RESULT_ENV] = result_path
                os.environ[self.module.PROGRESS_ENV] = progress_path
                os.environ[self.module.CANCEL_ENV] = cancel_path
                expected = {
                    "ok": True,
                    "summary": "自检通过。",
                    "report_path": "报告.txt",
                    "passed": 6,
                    "total": 6,
                }
                with mock.patch.object(
                    self.module,
                    "_run_isolated",
                    return_value=expected,
                ):
                    self.module._child_entry()

                self.assertEqual(
                    self.module._read_json_if_ready(result_path),
                    expected,
                )
                progress = self.module._read_json_if_ready(progress_path)
                self.assertEqual(progress["state"], "已完成")
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_ui_starts_modeless_controller_instead_of_waiting(self) -> None:
        ui_text = UI_PATH.read_text(encoding="utf-8")
        module_text = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("_f2m_sc.start_from_max()", ui_text)
        self.assertNotIn("_f2m_sc.run_from_max(show_dialog=False)", ui_text)
        self.assertIn("subprocess.Popen(", module_text)
        self.assertIn("self.QtCore.QTimer(", module_text)
        self.assertIn("CONTROLLER_SLOT", module_text)
        self.assertIn("taskkill.exe", module_text)
        self.assertIn("SELF_CHECK_TIMEOUT_SECONDS = 300", module_text)

    def test_single_instance_returns_existing_controller(self) -> None:
        class Existing:
            def __init__(self) -> None:
                self.process = FakeProcess(pid=24680)
                self.shown = 0

            @staticmethod
            def is_running():
                return True

            def show(self):
                self.shown += 1

        existing = Existing()
        previous = getattr(builtins, self.module.CONTROLLER_SLOT, None)
        setattr(builtins, self.module.CONTROLLER_SLOT, existing)
        try:
            with mock.patch.object(self.module, "rt", object()), mock.patch.object(
                self.module, "_find_batch_executable"
            ) as find_batch:
                result = self.module.start_from_max()
            self.assertFalse(result["started"])
            self.assertTrue(result["already_running"])
            self.assertEqual(result["child_pid"], 24680)
            self.assertEqual(existing.shown, 1)
            find_batch.assert_not_called()
        finally:
            if previous is None:
                delattr(builtins, self.module.CONTROLLER_SLOT)
            else:
                setattr(builtins, self.module.CONTROLLER_SLOT, previous)

    def test_cancel_writes_request_and_terminates_process_tree(self) -> None:
        controller = self.module._AsyncSelfCheckController.__new__(
            self.module._AsyncSelfCheckController
        )
        controller.process = FakeProcess()
        controller.finished = False
        controller.cancel_requested = False
        controller.timed_out = False
        controller.cancel_started_at = 0.0
        controller.state_label = FakeLabel()
        controller.action_button = FakeButton()
        controller.terminator = None
        with tempfile.TemporaryDirectory() as folder:
            controller.paths = {
                "cancel": os.path.join(folder, "cancel.json"),
                "result": os.path.join(folder, "result.json"),
                "progress": os.path.join(folder, "progress.json"),
                "output": os.path.join(folder, "output.log"),
            }
            with mock.patch.object(self.module.subprocess, "Popen") as popen:
                controller.cancel("用户请求取消。")
            popen.assert_called_once()
            command = popen.call_args.args[0]
            self.assertIn("/PID", command)
            self.assertIn("/T", command)
            self.assertIn("/F", command)
            request = self.module._read_json_if_ready(controller.paths["cancel"])
            self.assertEqual(request["reason"], "用户请求取消。")
            self.assertTrue(controller.cancel_requested)
            self.assertFalse(controller.action_button.enabled)

    def test_poll_turns_300_seconds_into_timeout_cancel(self) -> None:
        controller = self.module._AsyncSelfCheckController.__new__(
            self.module._AsyncSelfCheckController
        )
        controller.process = FakeProcess()
        controller.finished = False
        controller.cancel_requested = False
        controller.cancel_started_at = 0.0
        controller.started_at = time.monotonic() - 301
        controller.paths = {"progress": os.path.join(tempfile.gettempdir(), uuid_name())}
        called = {}

        def cancel(reason, *, timeout=False):
            called["reason"] = reason
            called["timeout"] = timeout
            controller.cancel_requested = True
            controller.cancel_started_at = time.monotonic()

        controller.cancel = cancel
        controller._poll()
        self.assertTrue(called["timeout"])
        self.assertIn("300", called["reason"])

    def test_completed_result_stops_a_lingering_batch_tree_after_grace(self) -> None:
        controller = self.module._AsyncSelfCheckController.__new__(
            self.module._AsyncSelfCheckController
        )
        controller.process = FakeProcess()
        controller.finished = False
        controller.cancel_requested = False
        controller.cancel_started_at = 0.0
        controller.started_at = time.monotonic()
        controller.completed_result = None
        controller.result_seen_at = 0.0
        controller.completion_stop_requested = False
        controller.state_label = FakeLabel()
        controller.terminator = None
        with tempfile.TemporaryDirectory() as folder:
            controller.paths = {
                "result": os.path.join(folder, "result.json"),
                "progress": os.path.join(folder, "progress.json"),
                "cancel": os.path.join(folder, "cancel.json"),
                "output": os.path.join(folder, "batch.log"),
            }
            expected = {
                "ok": True,
                "summary": "自检通过。",
                "report_path": "报告.txt",
            }
            self.module._atomic_write_json(controller.paths["result"], expected)
            controller._poll()
            self.assertEqual(controller.completed_result, expected)
            self.assertIn("自然退出", controller.state_label.text)

            controller.result_seen_at = (
                time.monotonic()
                - self.module.SELF_CHECK_EXIT_GRACE_SECONDS
                - 0.1
            )
            with mock.patch.object(self.module.subprocess, "Popen") as popen:
                controller._poll()
            popen.assert_called_once()
            command = popen.call_args.args[0]
            self.assertIn("/PID", command)
            self.assertIn("/T", command)
            self.assertTrue(controller.completion_stop_requested)

            controller.process.return_code = 0
            controller.max_log_checkpoint = {}
            controller.max_log_child_pid = controller.process.pid
            controller.process_started_wall_time = time.time()
            controller._close_output = mock.Mock()
            controller._finish = mock.Mock()
            controller._poll()
            final = controller._finish.call_args.args[0]
            self.assertFalse(final["ok"])
            self.assertTrue(final["business_result_ok"])
            self.assertFalse(final["child_process_natural_exit"])
            self.assertFalse(final["child_process_exit_gate_passed"])
            self.assertTrue(final["child_process_completion_stop_requested"])
            self.assertEqual(final["child_process_exit_code"], 0)
            self.assertEqual(final["report_path"], expected["report_path"])
            self.assertEqual(
                final["diagnostic_output"],
                controller.paths["output"],
            )
            self.assertTrue(controller._finish.call_args.kwargs["keep_output"])

    def test_process_exit_gate_preserves_green_only_for_natural_zero_exit(self) -> None:
        original = {
            "ok": True,
            "summary": "自检通过：6/6 项通过。",
            "report_path": "报告.txt",
            "native_max_log_path": "Max.log",
        }
        final = self.module._apply_process_exit_gate(
            original,
            return_code=0,
            completion_stop_requested=False,
        )
        self.assertTrue(final["ok"])
        self.assertTrue(final["child_process_natural_exit"])
        self.assertTrue(final["child_process_exit_gate_passed"])
        self.assertFalse(final["child_process_exit_failure"])
        self.assertEqual(final["report_path"], original["report_path"])
        self.assertEqual(
            final["native_max_log_path"],
            original["native_max_log_path"],
        )

    def test_process_exit_gate_rejects_nonzero_exit_without_losing_evidence(self) -> None:
        original = {
            "ok": True,
            "summary": "自检通过：6/6 项通过。",
            "report_path": "报告.txt",
            "diagnostic_report_path": "内部报告.txt",
            "native_max_log_audit": {"checked": True},
        }
        with mock.patch.object(
            self.module,
            "_prepend_process_exit_failure_to_report",
        ) as prepend:
            final = self.module._apply_process_exit_gate(
                original,
                return_code=3,
                completion_stop_requested=False,
            )
        self.assertFalse(final["ok"])
        self.assertTrue(final["child_process_natural_exit"])
        self.assertFalse(final["child_process_exit_gate_passed"])
        self.assertEqual(final["child_process_exit_code"], 3)
        self.assertIn("退出代码 3", final["summary"])
        self.assertEqual(
            final["diagnostic_report_path"],
            original["diagnostic_report_path"],
        )
        self.assertEqual(
            final["native_max_log_audit"],
            original["native_max_log_audit"],
        )
        prepend.assert_called_once()

    def test_failed_child_result_exposes_preserved_diagnostic_output(self) -> None:
        controller = self.module._AsyncSelfCheckController.__new__(
            self.module._AsyncSelfCheckController
        )
        controller.process = FakeProcess(return_code=1)
        controller.finished = False
        controller.cancel_requested = False
        controller.cancel_started_at = 0.0
        controller.started_at = time.monotonic()
        with tempfile.TemporaryDirectory() as folder:
            controller.paths = {
                "result": os.path.join(folder, "result.json"),
                "progress": os.path.join(folder, "progress.json"),
                "cancel": os.path.join(folder, "cancel.json"),
                "output": os.path.join(folder, "batch.log"),
            }
            self.module._atomic_write_json(
                controller.paths["result"],
                {"ok": False, "summary": "自检失败。", "report_path": "报告.txt"},
            )
            controller._close_output = mock.Mock()
            controller._finish = mock.Mock()
            controller._poll()
            result = controller._finish.call_args.args[0]
            self.assertEqual(
                result["diagnostic_output"],
                controller.paths["output"],
            )
            self.assertTrue(controller._finish.call_args.kwargs["keep_output"])
            self.assertEqual(result["child_process_exit_code"], 1)
            self.assertFalse(result["child_process_exit_gate_passed"])
            self.assertIn("退出代码 1", result["summary"])

    def test_shutdown_stops_qt_callbacks_closes_dialog_and_kills_child(self) -> None:
        controller = self.module._AsyncSelfCheckController.__new__(
            self.module._AsyncSelfCheckController
        )
        controller.process = FakeProcess()
        controller.finished = False
        controller.cancel_requested = False
        controller.timer = FakeTimer()
        controller.dialog = FakeDialog()
        controller.application = FakeApplication()
        controller.output_handle = None
        with tempfile.TemporaryDirectory() as folder:
            controller.paths = {
                "result": os.path.join(folder, "result.json"),
                "progress": os.path.join(folder, "progress.json"),
                "cancel": os.path.join(folder, "cancel.json"),
                "output": os.path.join(folder, "batch.log"),
            }
            pathlib.Path(controller.paths["progress"]).write_text(
                "{}", encoding="utf-8"
            )
            with mock.patch.object(
                self.module.subprocess, "run", return_value=mock.Mock(returncode=0)
            ):
                controller.shutdown()

        self.assertTrue(controller.finished)
        self.assertTrue(controller.cancel_requested)
        self.assertEqual(controller.timer.stop_calls, 1)
        self.assertEqual(controller.timer.timeout.disconnect_calls, 1)
        self.assertEqual(controller.application.aboutToQuit.disconnect_calls, 1)
        self.assertEqual(controller.dialog.hide_calls, 1)
        self.assertEqual(controller.dialog.close_calls, 1)
        self.assertTrue(controller.process.killed)
        self.assertFalse(controller.is_running())

    def test_shutdown_failure_keeps_controller_running_and_monitoring(self) -> None:
        class UnkillableProcess(FakeProcess):
            def kill(self):
                self.killed = True

        controller = self.module._AsyncSelfCheckController.__new__(
            self.module._AsyncSelfCheckController
        )
        controller.process = UnkillableProcess()
        controller.finished = False
        controller.cancel_requested = False
        controller.timer = FakeTimer()
        controller.dialog = FakeDialog()
        controller.application = FakeApplication()
        controller.output_handle = mock.Mock()
        with tempfile.TemporaryDirectory() as folder:
            controller.paths = {
                "result": os.path.join(folder, "result.json"),
                "progress": os.path.join(folder, "progress.json"),
                "cancel": os.path.join(folder, "cancel.json"),
                "output": os.path.join(folder, "batch.log"),
            }
            pathlib.Path(controller.paths["progress"]).write_text(
                "{}", encoding="utf-8"
            )
            with mock.patch.object(
                self.module.subprocess, "run", side_effect=OSError("模拟停止失败")
            ):
                with self.assertRaisesRegex(RuntimeError, "仍然运行"):
                    controller.shutdown()
            self.assertTrue(os.path.exists(controller.paths["progress"]))

        self.assertFalse(controller.finished)
        self.assertTrue(controller.is_running())
        self.assertEqual(controller.timer.start_calls, 1)
        self.assertEqual(controller.timer.timeout.disconnect_calls, 0)
        self.assertEqual(controller.application.aboutToQuit.disconnect_calls, 0)
        self.assertEqual(controller.dialog.show_calls, 1)
        self.assertEqual(controller.dialog.raise_calls, 1)
        self.assertEqual(controller.dialog.close_calls, 0)
        controller.output_handle.close.assert_not_called()


def uuid_name() -> str:
    return "f2m_missing_progress_" + str(os.getpid()) + "_" + str(time.time_ns())


if __name__ == "__main__":
    unittest.main()
