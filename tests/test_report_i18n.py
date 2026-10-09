"""Presentation regression: language never changes business acceptance."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
CONTENTS = ROOT / "contents"


def load(filename, name):
    path = CONTENTS / filename
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class BackendReportLanguageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = load("f2m_report_i18n.py", "_f2m_test_report_display")
        cls.topology = load("f2m_topology_transfer.py", "_f2m_test_report_topology")
        cls.skin = load("f2m_skin_replace.py", "_f2m_test_report_skin")
        cls.selfcheck = load("f2m_selfcheck.py", "_f2m_test_report_selfcheck")

    def setUp(self):
        self.language = self.topology._language_runtime()
        self.previous = self.language.get_language()

    def tearDown(self):
        self.language.set_language(self.previous, persist=False)

    def test_fixed_success_failure_and_notice_catalog_has_english_content(self):
        for source, target in self.report.CATALOG.items():
            with self.subTest(source=source):
                self.assertTrue(target)
                self.assertNotRegex(target, r"[\u3400-\u9fff]")
                self.assertEqual(self.report.translate_english(source), target)

    def test_templates_keep_all_runtime_fields_and_bullet_context(self):
        for source, target in self.report.TEMPLATES:
            with self.subTest(source=source):
                values = tuple("IDENT_%d" % index for index in range(10))
                rendered = source.format(*values)
                expected = target.format(*values)
                self.assertEqual(self.report.translate_english(rendered), expected)
                self.assertEqual(self.report.translate_english("  - " + rendered), "  - " + expected)

    def test_node_names_and_retained_originals_are_not_rewritten(self):
        raw = "传递方向：Max 源模型 光滑组模型 <- FBX 目标模型 失败模型"
        self.assertEqual(self.report.translate_english(raw),
                         "Transfer direction: Max source 光滑组模型 <- FBX target 失败模型")
        translated = self.report.translate_english("未知异常：exact error 123")
        self.assertIn("未知异常：exact error 123", translated)
        self.assertEqual(self.report.translate_english(translated), translated)

    def test_unknown_failure_is_preserved_and_never_relabelled_as_success(self):
        value = "失败：未知原生错误 ObjectID=31415"
        translated = self.report.translate_english(value)
        self.assertIn("未知原生错误", translated)
        self.assertIn("ObjectID=31415", translated)
        self.assertIn("original retained", translated)
        self.assertNotIn("检查已完成", translated)
        self.assertNotIn("completed", translated.lower())
        self.assertEqual(self.report.translate_english("RuntimeError: exact detail"),
                         "RuntimeError: exact detail")

    def test_free_paths_and_unknown_identifiers_remain_verbatim(self):
        for value in (r"C:\光滑组\scene.max", r"C:\Reports\显式法线.txt",
                      r"\\server\光滑组\显式法线.fbx", "/光滑组/显式法线.txt"):
            with self.subTest(path=value):
                self.assertEqual(self.report.translate_english(value), value)
        for value in ("ObjectID=光滑组_显式法线", "未知异常：光滑组_显式法线"):
            with self.subTest(identifier=value):
                translated = self.report.translate_english(value)
                self.assertIn(value, translated)
                self.assertNotIn("Smoothing groups", translated)
                self.assertNotIn("Specified normals", translated)

    def test_both_report_field_orders_preserve_node_identity(self):
        for name in ("光滑组", "显式法线", "通过", "失败", "完成", "跳过", "节点[光滑组]"):
            with self.subTest(name=name):
                self.assertEqual(
                    self.report.translate_english("[%s] 完成：同拓扑传递" % name),
                    "[%s] Completed: matching-topology transfer" % name,
                )
                self.assertEqual(
                    self.report.translate_english("[完成：同拓扑传递] " + name),
                    "[Completed: matching-topology transfer] " + name,
                )
        ambiguous = "[完成：同拓扑传递] 失败：已回滚"
        self.assertIn(ambiguous, self.report.translate_english(ambiguous))

    def test_known_templates_never_translate_interpolated_paths_or_names(self):
        values = tuple(r"C:\光滑组\节点[显式法线]_%d.fbx" % index for index in range(10))
        for source, target in self.report.TEMPLATES:
            with self.subTest(template=source):
                self.assertEqual(self.report.translate_english(source.format(*values)),
                                 target.format(*values))
        path = r"C:\Reports\显式法线.txt"
        self.assertEqual(self.report.translate_english("报告文件：" + path),
                         "Report file: " + path + "\nTechnical detail (original retained): 报告文件：" + path)

    def test_english_presentation_preserves_internal_chinese_status_contract(self):
        self.language.set_language("en", persist=False)
        for engine in (self.topology, self.skin):
            context = engine.TransferContext(engine.TransferOptions(fbx_path="", show_ui=False), engine.TransferLog())
            item = engine.ObjectReport(name="Original_Node_中文", status="完成：同拓扑传递")
            item.add("光滑组：完成，已按面写入并回读验证。")
            context.reports.append(item)
            self.assertTrue(engine.reports_succeeded(context))
            raw = engine.summarize_reports(context)
            with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {"LOCALAPPDATA": folder}):
                path = engine.write_log_file(raw, "language_test")
                display = Path(path).read_text("utf-8")
            self.assertIn("Completed: matching-topology transfer", display)
            self.assertIn("Original_Node_中文", display)
            self.assertEqual(item.status, "完成：同拓扑传递")
            self.assertTrue(engine.reports_succeeded(context))
            item.status = "失败：已回滚"
            self.assertFalse(engine.reports_succeeded(context))

    def test_english_exception_keeps_original_native_detail(self):
        self.language.set_language("en", persist=False)
        for engine in (self.topology, self.skin):
            self.assertEqual(engine.visible_exception_text(RuntimeError("native error 123")), "native error 123")

    def test_selfcheck_report_language_does_not_change_json_or_boolean_result(self):
        checks = [self.selfcheck.Check("运行文件、绝对路径与版本", False, "FAIL: original error", 23)]
        for locale in ("zh-CN", "en"):
            self.language.set_language(locale, persist=False)
            with tempfile.TemporaryDirectory() as folder, mock.patch.object(self.selfcheck, "_report_folder", return_value=folder):
                result = self.selfcheck._write_report(checks, "language_test")
                display = Path(result["report_path"]).read_text("utf-8")
            self.assertFalse(result["ok"])
            self.assertEqual(result["passed"], 0)
            self.assertEqual(result["total"], 1)
            self.assertEqual(result["checks"][0]["name"], checks[0].name)
            self.assertIn("失败", result["summary"])
            if locale == "en":
                self.assertIn("[Failed]", display)
                self.assertIn("23 ms", display)
            else:
                self.assertIn("[失败]", display)

    def test_unlocalized_selfcheck_error_is_never_hidden(self):
        for locale in ("zh-CN", "en"):
            self.language.set_language(locale, persist=False)
            displayed = self.selfcheck._localize_visible_text("FAIL: unexpected object 123")
            self.assertIn("unexpected object 123", displayed)
            self.assertNotIn("隐藏", displayed)

    def test_language_loader_rejects_fresh_foreign_version(self):
        for engine in (self.topology, self.skin, self.selfcheck):
            name = "_fbx_to_3dsmax_i18n_runtime"
            previous = sys.modules.pop(name, None)
            try:
                with tempfile.TemporaryDirectory() as folder:
                    host = Path(folder) / "host.py"
                    target = Path(folder) / "f2m_i18n.py"
                    target.write_text("TOOL_VERSION='0.0.0'\n_F2M_IMPORT_COMPLETE=True\ndef translate(text): return text\ndef get_language(): return 'en'\n", "utf-8")
                    with mock.patch.object(engine, "__file__", str(host)):
                        with self.assertRaisesRegex(RuntimeError, "identity/version/API"):
                            engine._language_runtime()
                    self.assertNotIn(name, sys.modules)
            finally:
                if previous is not None:
                    sys.modules[name] = previous


import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

FORMATTER_ROOT = Path(__file__).resolve().parents[1]
FORMATTER_CONTENTS = FORMATTER_ROOT / "contents"
FORMATTER_MARKER = "Technical detail (original retained): "
FORMATTER_NOTICE = "说明：自检覆盖已知关键不变量和内置样本，不能证明不存在所有未知缺陷。"
FORMATTER_CASES = (
    "运行文件、绝对路径与版本",
    "光滑组纯算法与32位限制",
    "3ds Max 过程网格与修改器栈",
    "显式法线空间、共存与失败回滚",
    "内置 FBX 同拓扑完整链路",
    "内置 FBX 蒙皮替换完整链路",
)
FORMATTER_UNKNOWN = "未知诊断：节点 [失败]；C:\\光滑组\\保留原文.max\n第二行包含括号 {raw}、[显式法线] 与错误 token"

def load_formatter_source(name, filename):
    spec = importlib.util.spec_from_file_location(name, str(FORMATTER_CONTENTS / filename))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

class SelfcheckReportFormatterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = load_formatter_source("_formatter_catalog_" + str(id(cls)), "f2m_report_i18n.py")
        cls.module = load_formatter_source("_formatter_selfcheck_" + str(id(cls)), "f2m_selfcheck.py")

    def setUp(self):
        base = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "FBXTo3dsMax" / "Validation"
        base.mkdir(parents=True, exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(prefix="formatter_", dir=str(base))
        self.addCleanup(self.folder.cleanup)
        self.locale = "en"
        self.language = types.SimpleNamespace(get_language=lambda: self.locale, translate=self.translate)
        self.patch = mock.patch.object(self.module, "_language_runtime", return_value=self.language)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def translate(self, value, locale=None):
        return self.report.translate_english(value) if (locale or self.locale) == "en" else str(value)

    def write(self, checks, run_id="formatter"):
        with mock.patch.object(self.module, "_report_folder", return_value=self.folder.name):
            result = self.module._write_report(checks, run_id)
        return result, Path(result["report_path"]).read_text(encoding="utf-8")

    def check(self, name=FORMATTER_CASES[0], ok=False, detail=FORMATTER_UNKNOWN, elapsed=23, diagnostic=""):
        return self.module.Check(name, ok, detail, elapsed, diagnostic)

    def test_unknown_multiline_does_not_block_typed_english_structure(self):
        checks = [self.check(name, index != 0, FORMATTER_UNKNOWN if index == 0 else "光滑组算法测试通过。", index + 23) for index, name in enumerate(FORMATTER_CASES)]
        expected_details = [self.module._localize_visible_text(item.detail) for item in checks]
        result, visible = self.write(checks)
        self.assertEqual(result["summary"], "FBXTo3dsMax v1.4.24 自检失败：5/6 项通过。")
        self.assertEqual(visible.splitlines()[0], "FBXTo3dsMax v1.4.24 self-check Failed: 5/6 checks passed.")
        self.assertIn(self.report.CATALOG[FORMATTER_NOTICE], visible)
        for index, item in enumerate(checks):
            row = "[" + ("Passed" if item.ok else "Failed") + "] " + self.report.CATALOG[item.name] + " (" + str(item.elapsed_ms) + " ms)"
            self.assertIn(row, visible)
            self.assertIn(expected_details[index], visible)
        for raw_line in FORMATTER_UNKNOWN.split("\n"):
            self.assertIn(raw_line, visible)
        self.assertEqual(result["checks"][0]["detail"], FORMATTER_UNKNOWN)
        self.assertFalse(result["ok"])

    def test_prelocalized_marker_retains_complete_opaque_multiline_body(self):
        retained = "Unknown diagnostic\n" + FORMATTER_MARKER + FORMATTER_UNKNOWN + "\n[失败] 内置 FBX 同拓扑完整链路（23 毫秒）"
        result, visible = self.write([self.check(detail=retained)])
        self.assertIn("self-check Failed: 0/1 checks passed.", visible)
        self.assertIn("[Failed] Runtime files, absolute paths and versions (23 ms)", visible)
        self.assertIn(retained, visible)
        self.assertEqual(visible.count(FORMATTER_MARKER), 1)
        self.assertEqual(result["checks"][0]["detail"], retained)

    def test_known_success_and_elapsed_rows_are_english(self):
        result, visible = self.write([self.check(ok=True, detail="光滑组算法测试通过。", elapsed=1000)])
        self.assertTrue(result["ok"])
        self.assertIn("self-check Passed: 1/1 checks passed.", visible)
        self.assertIn("[Passed] Runtime files, absolute paths and versions (1000 ms)", visible)
        self.assertIn("Smoothing algorithm tests passed.", visible)

    def test_empty_suite_stays_failed_and_has_typed_header(self):
        result, visible = self.write([])
        self.assertFalse(result["ok"])
        self.assertEqual((result["passed"], result["total"]), (0, 0))
        self.assertIn("self-check Failed: 0/0 checks passed.", visible)
        self.assertIn(self.report.CATALOG[FORMATTER_NOTICE], visible)

    def test_localize_detail_exactly_once_and_never_translate_assembled_body(self):
        checks = [self.check(), self.check(name=FORMATTER_CASES[1], ok=True, detail="光滑组算法测试通过。")]
        localize = self.module._localize_visible_text
        display = self.module._display_text
        with mock.patch.object(self.module, "_localize_visible_text", wraps=localize) as detail_spy, mock.patch.object(self.module, "_display_text", wraps=display) as display_spy:
            self.write(checks)
        self.assertEqual(detail_spy.call_args_list, [mock.call(item.detail) for item in checks])
        self.assertFalse(any(FORMATTER_NOTICE in str(call.args[0]) and "=" * 72 in str(call.args[0]) for call in display_spy.call_args_list))

    def test_protocol_and_raw_diagnostics_are_language_independent(self):
        checks = [self.check(diagnostic=FORMATTER_UNKNOWN + "\ntraceback: original [失败]")]
        raw_results = []
        raw_diagnostics = []
        for locale in ("zh-CN", "en"):
            self.locale = locale
            result, _ = self.write(checks, locale)
            raw_results.append({key: value for key, value in result.items() if key not in ("report_path", "diagnostic_report_path")})
            raw_diagnostics.append(Path(result["diagnostic_report_path"]).read_bytes())
        self.assertEqual(raw_results[0], raw_results[1])
        self.assertEqual(raw_results[0]["checks"], [item.__dict__ for item in checks])
        self.assertEqual(raw_diagnostics[0], raw_diagnostics[1])
        self.assertIn(FORMATTER_UNKNOWN.replace("\n", os.linesep).encode("utf-8"), raw_diagnostics[0])

    def write_opaque_child(self, body=None):
        path = Path(self.folder.name) / "child.txt"
        value = body if body is not None else "Original child report\n" + FORMATTER_MARKER + FORMATTER_UNKNOWN + "\n"
        path.write_text(value, encoding="utf-8")
        return path, value

    def test_atomic_writer_is_raw_and_does_not_translate_payload(self):
        path = Path(self.folder.name) / "raw.txt"
        value = "[失败] " + FORMATTER_UNKNOWN + "\n" + FORMATTER_MARKER + "opaque\n"
        with mock.patch.object(self.module, "_display_text", side_effect=AssertionError("Raw writer must not translate")):
            self.module._atomic_write_text(str(path), value)
        self.assertEqual(path.read_text(encoding="utf-8"), value)

    def test_native_prefix_translates_own_fields_without_touching_child_or_path(self):
        path, child = self.write_opaque_child()
        log = "C:\\光滑组\\[失败]\\Max.log"
        self.module._prepend_native_log_failure_to_report({"report_path": str(path)}, {"checked": True, "gc_error_count": 2, "path": log})
        actual = path.read_text(encoding="utf-8")
        self.assertTrue(actual.startswith("[Parent controller final verdict]\nSelf-check failed: "))
        self.assertIn("2 MAXScript garbage-collection errors", actual)
        self.assertIn("Native log: " + log, actual)
        self.assertIn("The six business checks below do not override", actual)
        self.assertTrue(actual.endswith(child))
        self.assertEqual(actual.count(FORMATTER_MARKER), child.count(FORMATTER_MARKER))

    def test_native_unverified_prefix_remains_failed_and_english(self):
        path, child = self.write_opaque_child()
        result = self.module._apply_native_max_log_gate({"ok": True, "summary": "自检通过：原始摘要", "report_path": str(path)}, {"checked": False, "path": ""})
        actual = path.read_text(encoding="utf-8")
        self.assertFalse(result["ok"])
        self.assertTrue(result["native_max_log_failure"])
        self.assertFalse(result["native_max_log_checked"])
        self.assertIn("could not be verified", actual)
        self.assertIn("Native log: Not found", actual)
        self.assertTrue(actual.endswith(child))

    def test_process_prefix_known_reason_and_unknown_multiline_keep_boundaries(self):
        for reason in ("独立 3ds Max Batch 未以退出代码 0 完成（实际退出代码 -8）。", "Technical reason\n" + FORMATTER_MARKER + FORMATTER_UNKNOWN):
            with self.subTest(reason=reason):
                path, child = self.write_opaque_child()
                self.module._prepend_process_exit_failure_to_report({"report_path": str(path)}, reason)
                actual = path.read_text(encoding="utf-8")
                self.assertTrue(actual.startswith("[Parent controller process-exit gate]\nSelf-check failed: "))
                self.assertIn(self.module._localize_visible_text(reason), actual)
                self.assertIn("The original child business report", actual)
                self.assertTrue(actual.endswith(child))
                self.assertEqual(actual.count(FORMATTER_MARKER), child.count(FORMATTER_MARKER) + reason.count(FORMATTER_MARKER))

    def test_each_parent_prefix_is_idempotent_in_same_language(self):
        for locale in ("zh-CN", "en"):
            for phase in ("native", "process"):
                with self.subTest(locale=locale, phase=phase):
                    self.locale = locale
                    path, _ = self.write_opaque_child()
                    call = (lambda: self.module._prepend_native_log_failure_to_report({"report_path": str(path)}, {"checked": False})) if phase == "native" else (lambda: self.module._prepend_process_exit_failure_to_report({"report_path": str(path)}, FORMATTER_UNKNOWN))
                    call()
                    before = path.read_bytes()
                    call()
                    self.assertEqual(path.read_bytes(), before)

    def test_english_reader_recognizes_existing_chinese_exact_marker(self):
        for phase, marker in (("native", "【父控制器最终判定】"), ("process", "【父控制器进程退出门禁】")):
            with self.subTest(phase=phase):
                path, _ = self.write_opaque_child(marker + "\nunchanged old verdict\n")
                before = path.read_bytes()
                if phase == "native":
                    self.module._prepend_native_log_failure_to_report({"report_path": str(path)}, {"checked": False})
                else:
                    self.module._prepend_process_exit_failure_to_report({"report_path": str(path)}, FORMATTER_UNKNOWN)
                self.assertEqual(path.read_bytes(), before)

    def test_marker_inside_child_is_not_mistaken_for_existing_parent_prefix(self):
        path, child = self.write_opaque_child("Opaque first line\n【父控制器最终判定】\n" + FORMATTER_UNKNOWN)
        self.module._prepend_native_log_failure_to_report({"report_path": str(path)}, {"checked": False})
        actual = path.read_text(encoding="utf-8")
        self.assertTrue(actual.startswith("[Parent controller final verdict]\n"))
        self.assertTrue(actual.endswith(child))

    def test_parent_exact_markers_are_idempotent_across_language_switches(self):
        for first, second in (("zh-CN", "en"), ("en", "zh-CN")):
            for phase in ("native", "process"):
                with self.subTest(first=first, second=second, phase=phase):
                    path, _ = self.write_opaque_child()
                    call = (lambda: self.module._prepend_native_log_failure_to_report({"report_path": str(path)}, {"checked": False})) if phase == "native" else (lambda: self.module._prepend_process_exit_failure_to_report({"report_path": str(path)}, FORMATTER_UNKNOWN))
                    self.locale = first
                    call()
                    before = path.read_bytes()
                    self.locale = second
                    call()
                    self.assertEqual(path.read_bytes(), before)

    def test_unknown_process_reason_preserves_outer_whitespace_and_raw_lines(self):
        path, child = self.write_opaque_child()
        reason = "  unknown\n" + FORMATTER_MARKER + FORMATTER_UNKNOWN + "\n\t  "
        self.module._prepend_process_exit_failure_to_report({"report_path": str(path)}, reason)
        visible = path.read_text(encoding="utf-8")
        self.assertIn("Self-check failed: " + reason + "\n", visible)
        self.assertTrue(visible.endswith(child))

    def test_process_json_exit_verdict_uses_original_protocol(self):
        for code, forced in ((0, False), (-8, False), (0, True), (None, False)):
            with self.subTest(code=code, forced=forced):
                path, child = self.write_opaque_child()
                result = self.module._apply_process_exit_gate({"ok": True, "summary": "自检通过：原始摘要", "report_path": str(path)}, return_code=code, completion_stop_requested=forced)
                passed = code == 0 and not forced
                self.assertEqual(result["ok"], passed)
                self.assertEqual(result["child_process_exit_gate_passed"], passed)
                self.assertEqual(result["child_process_exit_failure"], not passed)
                self.assertEqual(result["child_process_exit_code"], code)
                self.assertEqual(result["child_process_natural_exit"], code is not None and not forced)
                if not passed:
                    self.assertTrue(result["summary"].startswith("自检失败："))
                    self.assertTrue(path.read_text(encoding="utf-8").endswith(child))


import copy
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

CONSUMER_ROOT = Path(__file__).resolve().parents[1]
CONSUMER_CONTENTS = CONSUMER_ROOT / "contents"
CONSUMER_MARKER = "Technical detail (original retained): "
CONSUMER_UNKNOWN = "未知故障：节点 [失败]；C:\\光滑组\\[显式法线]\\原样.max\n第二行 {opaque} NativeError42"

def load_consumer_source(filename, tag):
    spec = importlib.util.spec_from_file_location(tag, str(CONSUMER_CONTENTS / filename))
    module = importlib.util.module_from_spec(spec)
    sys.modules[tag] = module
    spec.loader.exec_module(module)
    return module

class ConsumerWidget:
    def __init__(self): self.text = None
    def stop(self): pass
    def setValue(self, value): pass
    def maximum(self): return 6
    def value(self): return 2
    def setText(self, value): self.text = value
    def setEnabled(self, value): pass
    def show(self): pass
    def raise_(self): pass

class TypedSelfcheckGateDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_consumer_source("f2m_report_i18n.py", "_typed_gate_catalog_" + str(id(cls)))
        cls.module = load_consumer_source("f2m_selfcheck.py", "_typed_gate_module_" + str(id(cls)))

    def setUp(self):
        self.locale = "en"
        def translate(value, locale=None):
            return self.catalog.translate_english(value) if (locale or self.locale) == "en" else str(value)
        patch = mock.patch.object(self.module, "_language_runtime", return_value=types.SimpleNamespace(get_language=lambda: self.locale, translate=translate))
        patch.start()
        self.addCleanup(patch.stop)
        self.original = "Framework error\n" + CONSUMER_MARKER + CONSUMER_UNKNOWN

    def native(self, result=None, checked=True):
        return self.module._apply_native_max_log_gate(result or {"ok": True, "summary": self.original, "report_path": ""}, {"checked": checked, "gc_error_count": 2 if checked else 0})

    def process(self, result=None, code=-8, forced=False):
        return self.module._apply_process_exit_gate(result or {"ok": False, "summary": self.original, "report_path": ""}, return_code=code, completion_stop_requested=forced)

    def finish(self, result):
        controller = self.module._AsyncSelfCheckController.__new__(self.module._AsyncSelfCheckController)
        controller.finished = False
        for key in ("timer", "progress_bar", "state_label", "detail_label", "action_button", "dialog"):
            setattr(controller, key, ConsumerWidget())
        controller._remove_transient_files = lambda **kwargs: None
        before = copy.deepcopy(result)
        controller._finish(result, keep_output=True)
        self.assertEqual(result, before)
        self.assertEqual(controller.result, before)
        return controller.state_label.text

    def test_actual_native_gate_to_finish_keeps_unknown_tail_and_english_verdict(self):
        for checked in (True, False):
            with self.subTest(checked=checked):
                result = self.native(checked=checked)
                raw = result["summary"]
                visible = self.finish(result)
                self.assertTrue(visible.startswith("Self-check failed: "))
                self.assertIn("Original business-check summary: " + self.original, visible)
                self.assertTrue(visible.endswith(self.original))
                self.assertEqual(result["summary"], raw)
                self.assertFalse(result["ok"])

    def test_actual_exit_gates_to_finish_preserve_failure_and_original_summary(self):
        for code, forced in ((-8, False), (0, True), (None, False)):
            with self.subTest(code=code, forced=forced):
                result = self.process(code=code, forced=forced)
                visible = self.finish(result)
                self.assertTrue(visible.startswith("Self-check failed: "))
                self.assertTrue(visible.endswith(self.original))
                self.assertFalse(result["ok"])
                self.assertTrue(result["child_process_exit_failure"])

    def test_two_actual_gate_orders_translate_each_layer_once(self):
        for order in (("native", "process"), ("process", "native")):
            with self.subTest(order=order):
                result = {"ok": False, "summary": self.original, "report_path": ""}
                for phase in order:
                    result = self.native(result) if phase == "native" else self.process(result)
                with mock.patch.object(self.module, "_localize_visible_text", wraps=self.module._localize_visible_text) as localize:
                    visible = self.finish(result)
                self.assertEqual(visible.count("Self-check failed: "), 2)
                self.assertEqual(visible.count("Original business-check summary: "), 2)
                self.assertTrue(visible.endswith(self.original))
                self.assertEqual(localize.call_args_list, [mock.call(self.original)])
                self.assertEqual(visible.count(CONSUMER_MARKER), 1)

    def test_false_or_inconsistent_native_metadata_falls_back_without_guessing(self):
        base = self.native()
        mutations = (
            {"native_max_log_failure": False}, {"native_max_log_failure": "True"},
            {"native_max_log_checked": "True"}, {"native_max_log_gc_error_count": True},
            {"native_max_log_gc_error_count": "2"}, {"native_max_log_gc_error_count": -1},
            {"native_max_log_gc_error_count": 3}, {"business_result_ok": "True"},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = dict(base, **mutation)
                self.assertEqual(self.finish(result), self.module._localize_visible_text(result["summary"]))

    def test_false_or_inconsistent_exit_metadata_falls_back_without_guessing(self):
        base = self.process()
        mutations = (
            {"child_process_exit_failure": False}, {"child_process_exit_gate_passed": True},
            {"child_process_exit_observed": "True"}, {"child_process_exit_observed": False},
            {"child_process_exit_code": True}, {"child_process_exit_code": "-8"},
            {"child_process_exit_code": -7}, {"child_process_natural_exit": False},
            {"child_process_completion_stop_requested": "False"},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = dict(base, **mutation)
                self.assertEqual(self.finish(result), self.module._localize_visible_text(result["summary"]))

    def test_complete_exact_prefix_required_and_embedded_words_remain_opaque(self):
        base = self.process()
        for summary in (
            "Node [失败] " + base["summary"], base["summary"].replace("原业务检查摘要：", "原业务检查摘要:", 1),
            base["summary"].replace("实际退出代码 -8", "实际退出代码 -7", 1),
            "Framework error\n" + CONSUMER_MARKER + "节点名 自检失败：原业务检查摘要： " + base["summary"],
        ):
            with self.subTest(summary=summary):
                result = dict(base, summary=summary)
                self.assertEqual(self.finish(result), self.module._localize_visible_text(summary))

    def test_one_kind_cannot_recursively_strip_unbounded_repeated_prefixes(self):
        result = self.process(self.process())
        visible = self.finish(result)
        self.assertEqual(visible.count("Self-check failed: "), 1)
        self.assertIn("自检失败：", visible)
        self.assertTrue(visible.endswith(self.original))

    def test_chinese_display_bytes_match_old_summary_localization(self):
        self.locale = "zh-CN"
        for result in (self.native(), self.process(), self.native(self.process()), self.process(self.native())):
            self.assertEqual(self.finish(result).encode("utf-8"), self.module._localize_visible_text(result["summary"]).encode("utf-8"))

    def test_no_prior_summary_and_success_fallback_preserve_protocol(self):
        for phase in ("native", "process"):
            result = self.native({"ok": True, "summary": "", "report_path": ""}) if phase == "native" else self.process({"ok": True, "summary": "", "report_path": ""})
            visible = self.finish(result)
            self.assertTrue(visible.startswith("Self-check failed: "))
            self.assertNotIn("Original business-check summary", visible)
        result = self.process({"ok": True, "summary": "FBXTo3dsMax v1.4.24 自检通过：6/6 项通过。", "report_path": ""}, code=0)
        self.assertTrue(result["ok"])
        self.assertIn("self-check Passed: 6/6 checks passed.", self.finish(result))

class BackendExceptionTerminalDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_consumer_source("f2m_report_i18n.py", "_exception_terminal_catalog_" + str(id(cls)))
        cls.engines = [load_consumer_source(filename, "_exception_terminal_" + filename[:-3] + str(id(cls))) for filename in ("f2m_topology_transfer.py", "f2m_skin_replace.py")]

    def setUp(self):
        base = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "FBXTo3dsMax" / "Validation"
        base.mkdir(parents=True, exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(prefix="terminal_formatter_", dir=str(base))
        self.addCleanup(self.folder.cleanup)
        self.locale = "en"
        def translate(value, locale=None):
            return self.catalog.translate_english(value) if (locale or self.locale) == "en" else str(value)
        self.language = types.SimpleNamespace(get_language=lambda: self.locale, translate=translate)
        for engine in self.engines:
            patch = mock.patch.object(engine, "_language_runtime", return_value=self.language)
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch.dict(os.environ, {"LOCALAPPDATA": self.folder.name})
        patch.start()
        self.addCleanup(patch.stop)

    def test_exception_raw_until_terminal_and_native_english_exact(self):
        for engine in self.engines:
            with self.subTest(engine=engine.__name__):
                self.assertEqual(engine.visible_exception_text(RuntimeError(CONSUMER_UNKNOWN)), CONSUMER_UNKNOWN)
                self.assertEqual(engine.visible_exception_text(RuntimeError("native error 123")), "native error 123")
                self.assertEqual(engine.visible_exception_text(RuntimeError("")), "底层操作失败，未返回可读原因。")

    def test_actual_exception_to_log_has_english_header_and_opaque_names_paths(self):
        for engine in self.engines:
            with self.subTest(engine=engine.__name__):
                raw = engine.visible_exception_text(RuntimeError(CONSUMER_UNKNOWN))
                body = "FBX 到 3ds Max 数据传递报告 v1.4.24\n[失败：已回滚] [显式法线]\n传递失败：" + raw
                path = engine.write_log_file(body, "terminal_" + engine.__name__)
                visible = Path(path).read_text(encoding="utf-8")
                self.assertTrue(visible.startswith("FBX to 3ds Max transfer report v1.4.24\n"))
                self.assertIn("[Failed: rolled back] [显式法线]", visible)
                self.assertIn("Transfer failed: ", visible)
                for line in CONSUMER_UNKNOWN.split("\n"):
                    self.assertIn(line, visible)
                self.assertEqual(raw, CONSUMER_UNKNOWN)

    def test_actual_object_report_to_summary_to_log_keeps_failure_state(self):
        for engine in self.engines:
            with self.subTest(engine=engine.__name__):
                report = engine.ObjectReport(name="[失败]", status="失败：已回滚")
                report.add_exception("对象处理发生异常：", RuntimeError(CONSUMER_UNKNOWN))
                ctx = types.SimpleNamespace(reports=[report], safety_errors=[], options=types.SimpleNamespace(dry_run=False))
                self.assertEqual(report.messages, ["对象处理发生异常：" + CONSUMER_UNKNOWN])
                self.assertFalse(engine.reports_succeeded(ctx))
                summary = engine.summarize_reports(ctx)
                visible = Path(engine.write_log_file(summary, "object_" + engine.__name__)).read_text(encoding="utf-8")
                self.assertIn("[Failed: rolled back] [失败]", visible)
                self.assertIn("Object processing raised an exception: ", visible)
                self.assertEqual(report.status, "失败：已回滚")

    def test_actual_exception_branch_report_popup_and_listener_translate_once(self):
        for engine in self.engines:
            with self.subTest(engine=engine.__name__):
                popup = mock.Mock()
                listener = mock.Mock()
                fake_rt = types.SimpleNamespace(selection=[], messageBox=popup, format=listener)
                raw_log = engine.TransferLog()
                context = types.SimpleNamespace(log=raw_log, diagnostics=[], run_id="exception_branch", committed_replacements=[])
                mode = "topology_only" if "topology" in engine.__name__ else "replace"
                options = engine.TransferOptions(fbx_path="", mode=mode, show_ui=True)
                patches = [mock.patch.object(engine, "rt", fake_rt), mock.patch.object(engine, "ensure_runtime"),
                    mock.patch.object(engine, "ensure_maxscript_heap_reserve", side_effect=RuntimeError(CONSUMER_UNKNOWN)),
                    mock.patch.object(engine, "TransferContext", return_value=context),
                    mock.patch.object(engine, "TransferLog", return_value=raw_log),
                    mock.patch.object(engine, "cleanup_imported_nodes"), mock.patch.object(engine, "restore_scene_names", return_value=True),
                    mock.patch.object(engine, "_release_context_node_references"),
                    mock.patch.object(engine, "_exception_text_and_release", return_value=CONSUMER_UNKNOWN),
                    mock.patch.object(engine, "write_diagnostic_file", return_value="C:\\光滑组\\diagnostic.txt")]
                if mode == "replace":
                    patches.append(mock.patch.object(engine, "rollback_committed_replacements", return_value=[]))
                else:
                    patches.append(mock.patch.object(engine, "restore_selection_by_handle"))
                for patch in patches: patch.start()
                try:
                    result = engine.run_transfer(options) if mode == "topology_only" else engine._run_transfer_impl(options)
                finally:
                    for patch in reversed(patches): patch.stop()
                self.assertFalse(engine.LAST_RUN_OK)
                self.assertEqual(engine.LAST_RUN_SUMMARY, result)
                self.assertTrue(result.startswith("传递失败：" + CONSUMER_UNKNOWN))
                self.assertNotIn(CONSUMER_MARKER, result)
                visible = Path(engine.LAST_RUN_REPORT_PATH).read_text(encoding="utf-8")
                self.assertIn("Transfer failed: ", visible)
                self.assertEqual(popup.call_count, 1)
                message = popup.call_args.args[0]
                self.assertTrue(message.startswith("Transfer failed: "))
                self.assertIn("Report: ", message)
                self.assertIn("C:\\光滑组\\diagnostic.txt", message)
                for line in CONSUMER_UNKNOWN.split("\n"):
                    self.assertIn(line, visible)
                    self.assertIn(line, message)
                self.assertTrue(any("Transfer failed: " in str(call.args[1]) for call in listener.call_args_list))

    def test_chinese_exception_branch_contract_unchanged(self):
        self.locale = "zh-CN"
        for engine in self.engines:
            self.assertEqual(engine.visible_exception_text(RuntimeError("native error 123")), "底层操作失败，具体技术信息已写入内部诊断文件。")
            self.assertEqual(engine.visible_exception_text(RuntimeError("未知中文原因")), "未知中文原因")
            self.assertEqual(engine.visible_exception_text(RuntimeError("")), "底层操作失败，未返回可读原因。")


class NativeSmoothingReportProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topology = load("f2m_topology_transfer.py", "_f2m_test_native_report_topology")
        cls.selfcheck = load("f2m_selfcheck.py", "_f2m_test_native_report_selfcheck")

    def setUp(self):
        language = self.topology._language_runtime()
        previous = language._session_locale
        self.addCleanup(setattr, language, "_session_locale", previous)
        language._session_locale = None

    def _production_report(self, folder, locale, method="FBX 原生平滑层 / Autodesk 精确导入", name="Opaque_Node_中文"):
        from types import SimpleNamespace
        topology = self.topology
        topology._language_runtime().set_language(locale, persist=False)
        options = topology.TransferOptions(fbx_path="", show_ui=False, transfer_normals=True)
        context = topology.TransferContext(options, topology.TransferLog())
        context.smoothing_method_by_name[name] = method
        report = topology.ObjectReport(name=name, status="完成：同拓扑传递")
        native = SimpleNamespace(canSetFaceSmoothingGroups=lambda *args: True,
                                 setFaceSmoothingGroups=lambda *args: True)
        runtime = SimpleNamespace(F2M_Helper=native, Array=lambda *args: args)
        with mock.patch.object(topology, "rt", runtime), mock.patch.object(topology, "_resolved_topology_map", return_value=object()), \
                mock.patch.object(topology, "smoothing_masks_for_source", return_value=[1, 1]), \
                mock.patch.object(topology, "remap_per_face_values", return_value=[1, 1]), \
                mock.patch.object(topology, "helper_message", return_value="光滑组完成：已写入并回读验证 2 个面，通过基础 TriMesh 单次事务写回。"):
            self.assertTrue(topology.copy_smoothing_groups(SimpleNamespace(name=name), object(), context, report))
        context.reports.append(report)
        summary = topology.summarize_reports(context)
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": folder, "F2M_LANGUAGE": locale}):
            path = topology.write_log_file(summary, "native_report_test")
        return summary, Path(path).read_text(encoding="utf-8"), path

    def _run_native_case(self, locale, masks=(1, 1), succeeded=True):
        from types import SimpleNamespace
        topology, selfcheck = self.topology, self.selfcheck
        with tempfile.TemporaryDirectory() as folder:
            fixture = Path(folder) / "topology.fbx"
            native_fixture = Path(folder) / "native.fbx"
            fixture.touch()
            native_fixture.touch()
            summary, displayed, path = self._production_report(folder, locale)
            node = SimpleNamespace(name="Opaque_Node_中文")
            runtime = SimpleNamespace(execute=lambda *args: None, select=lambda *args: None,
                                      clearSelection=lambda: None,
                                      F2M_Helper=SimpleNamespace(getFaceSmoothingGroups=lambda *args: list(masks)))
            fixtures = SimpleNamespace(get_fixture_paths=lambda: {"topology": str(fixture), "native_smoothing": str(native_fixture)})
            def run_from_max(**options):
                topology.LAST_RUN_OK = succeeded if options["fbx_path"] == str(native_fixture) else True
                topology.LAST_RUN_REPORT_PATH = path
                topology.LAST_RUN_SUMMARY = summary
            with mock.patch.dict(os.environ, {"F2M_LANGUAGE": locale}), \
                    mock.patch.object(selfcheck, "rt", runtime), mock.patch.object(selfcheck, "_require_runtime"), \
                    mock.patch.object(selfcheck, "_reset_max_file_safely"), \
                    mock.patch.object(selfcheck, "_load_local", side_effect=lambda filename, name: fixtures if filename == "f2m_test_fixtures.py" else topology), \
                    mock.patch.object(topology, "ensure_runtime"), mock.patch.object(topology, "_import_fbx_once", side_effect=lambda *args, **kwargs: [node]), \
                    mock.patch.object(topology, "is_geometry_node", return_value=True), \
                    mock.patch.object(topology, "run_from_max", side_effect=run_from_max), \
                    mock.patch.object(topology, "smoothing_masks_for_source", return_value=[1, 1]), \
                    mock.patch.object(topology, "_release_context_node_references"), \
                    mock.patch.object(topology, "LAST_RUN_OK", False), mock.patch.object(topology, "LAST_RUN_REPORT_PATH", ""), \
                    mock.patch.object(topology, "LAST_RUN_SUMMARY", ""):
                return selfcheck._topology_fbx_check()

    def test_actual_topology_selfcheck_accepts_original_and_english_saved_report(self):
        for locale in ("zh-CN", "en"):
            with self.subTest(locale=locale):
                self.assertIn("原生 LayerElementSmoothing 精确保留", self._run_native_case(locale))

    def test_actual_topology_selfcheck_still_rejects_failed_transfer_and_mask_mismatch(self):
        for locale in ("zh-CN", "en"):
            with self.subTest(locale=locale), self.assertRaisesRegex(AssertionError, "逐面掩码"):
                self._run_native_case(locale, masks=(1, 0))
            with self.subTest(locale=locale), self.assertRaisesRegex(AssertionError, "传递失败"):
                self._run_native_case(locale, succeeded=False)

    def test_native_report_proof_rejects_wrong_missing_or_opaque_source_marker(self):
        marker = "FBX 原生平滑层 / Autodesk 精确导入"
        for locale in ("zh-CN", "en"):
            with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {"F2M_LANGUAGE": locale}):
                for method in ("当前 FBX 目标网格逐面光滑组", "FBX 原生平滑层 / 错误导入", ""):
                    summary, displayed, path = self._production_report(folder, locale, method=method, name=marker)
                    with self.subTest(locale=locale, method=method), self.assertRaisesRegex(AssertionError, "生产分支"):
                        self.selfcheck._assert_native_smoothing_report(displayed, summary)
                summary, displayed, path = self._production_report(folder, locale)
                for unrelated in ("", marker, self.selfcheck._display_text(marker),
                                  "[完成：同拓扑传递] " + marker, "C:\\原生报告\\" + marker + ".txt",
                                  "Technical detail (original retained): " + marker):
                    with self.subTest(locale=locale, unrelated=unrelated), self.assertRaisesRegex(AssertionError, "生产分支"):
                        self.selfcheck._assert_native_smoothing_report(unrelated, summary)

    def test_native_report_proof_uses_the_real_full_message_translator(self):
        for locale in ("zh-CN", "en"):
            with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {"F2M_LANGUAGE": locale}):
                summary, displayed, path = self._production_report(folder, locale)
                self.selfcheck._assert_native_smoothing_report(displayed, summary)
                message = next(line for line in summary.splitlines() if line.startswith("  - "))
                self.selfcheck._assert_native_smoothing_report(self.selfcheck._display_text(message), summary)
                self.assertIn("Opaque_Node_中文", displayed)
                if locale == "en":
                    self.assertIn("Technical detail (original retained): ", displayed)
                    self.assertNotIn(self.selfcheck._display_text("FBX 原生平滑层 / Autodesk 精确导入"), displayed)


if __name__ == "__main__":
    unittest.main()
