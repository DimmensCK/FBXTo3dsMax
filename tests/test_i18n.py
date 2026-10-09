"""Language preferences and display-only contracts; no Max or user settings writes."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import re
import string
import sys
import tempfile
import types
import unittest
from unittest import mock
import uuid

ROOT = Path(__file__).resolve().parents[1]
CONTENTS = ROOT / "contents"


def load_language():
    name = "_f2m_i18n_test_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, CONTENTS / "f2m_i18n.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LanguageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.environment = mock.patch.dict(os.environ, {"LOCALAPPDATA": self.directory.name})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        os.environ.pop("F2M_LANGUAGE", None)
        self.module = load_language()

    def test_default_is_chinese_and_read_does_not_create_preferences(self):
        self.assertEqual(self.module.get_language(), "zh-CN")
        self.assertFalse(self.module.language_file().exists())

    def test_explicit_override_does_not_write_and_rejects_unsupported_codes(self):
        with mock.patch.dict(os.environ, {"F2M_LANGUAGE": "en"}):
            self.assertEqual(self.module.get_language(), "en")
            self.assertEqual(self.module.translate("开始执行"), "Run Transfer")
        self.assertFalse(self.module.language_file().exists())
        for value in ("EN", "zh", "en-US", "../en", "en\n"):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"F2M_LANGUAGE": value}):
                with self.assertRaises(ValueError):
                    self.module.get_language()

    def test_saved_language_reopens_and_uses_exact_utf8_values(self):
        self.module.set_language("en")
        self.assertEqual(self.module.language_file().read_bytes(), b"en\n")
        self.assertEqual(load_language().get_language(), "en")
        self.module.set_language("zh-CN")
        self.assertEqual(self.module.language_file().read_bytes(), b"zh-CN\n")
        self.assertEqual(load_language().get_language(), "zh-CN")

    def test_ui_choice_wins_in_session_without_mutating_test_override(self):
        with mock.patch.dict(os.environ, {"F2M_LANGUAGE": "en"}):
            self.assertEqual(self.module.get_language(), "en")
            self.module.set_language("zh-CN", persist=False)
            self.assertEqual(self.module.get_language(), "zh-CN")
            self.assertEqual(os.environ["F2M_LANGUAGE"], "en")
            self.assertFalse(self.module.language_file().exists())

    def test_atomic_failure_preserves_previous_file_and_session(self):
        self.module.set_language("en")
        before = self.module.language_file().read_bytes()
        with mock.patch.object(self.module.os, "replace", side_effect=OSError("write failed")):
            with self.assertRaises(OSError):
                self.module.set_language("zh-CN")
        self.assertEqual(self.module.language_file().read_bytes(), before)
        self.assertEqual(self.module.get_language(), "en")
        self.assertEqual(list(self.module.language_file().parent.glob(".language-*.tmp")), [])

    def test_invalid_saved_preferences_are_bounded_and_not_rewritten(self):
        path = self.module.language_file()
        path.parent.mkdir(parents=True)
        for value in (b"en-US\n", b"\xff", b"en" * 100):
            with self.subTest(value=value[:10]):
                path.write_bytes(value)
                self.assertEqual(load_language().get_language(), "zh-CN")
                self.assertEqual(path.read_bytes(), value)

    def test_invalid_explicit_choice_cannot_change_file_or_session(self):
        self.module.set_language("en")
        before = self.module.language_file().read_bytes()
        with self.assertRaises(ValueError):
            self.module.set_language("fr")
        self.assertEqual(self.module.get_language(), "en")
        self.assertEqual(self.module.language_file().read_bytes(), before)

    def test_catalog_pairs_have_same_format_fields_and_complete_ui_lookups(self):
        formatter = string.Formatter()
        self.assertEqual(len(self.module.ui_catalog_sources()), len(self.module.ui_catalog_english()))
        self.assertEqual(len(self.module.CATALOG), len(self.module.UI_TEXT))
        for key, (chinese, english) in self.module.UI_TEXT.items():
            fields = lambda value: {name for _, name, _, _ in formatter.parse(value) if name is not None}
            with self.subTest(key=key):
                self.assertTrue(chinese and english)
                self.assertEqual(fields(chinese), fields(english))
                if key != "ui.language":
                    self.assertIsNone(re.search(r"[\u3400-\u9fff]", english))
        ui = (CONTENTS / "FBXTo3dsMax_UI.ms").read_text("utf-8-sig")
        lookups = re.findall(r'\b(?:tr|setWarning)\s+"((?:\\.|[^"\\])*)"', ui)
        for raw in lookups:
            source = json.loads('"' + raw + '"')
            with self.subTest(source=source):
                self.assertIn(source, self.module.CATALOG)

    def test_display_formatting_preserves_names_paths_and_version(self):
        self.assertEqual(self.module.text("ui.meta", locale="en", author="Dimmens", version="1.4.24"),
                         "Author: Dimmens    Version: 1.4.24")
        path = r"C:\User Models\中文网格\mesh.fbx"
        original = self.module.text("macro.missing", locale="zh-CN", path=path)
        rendered = self.module.translate(original, locale="en")
        self.assertIn(path, rendered)
        self.assertIn("installation is incomplete", rendered)
        self.assertEqual(self.module.translate("顶部按钮数量异常：应为 1，实际为 2。", locale="en"),
                         "Toolbar button count is incorrect: expected 1, found 2.")
        self.assertEqual(self.module.translate(original, locale="zh-CN"), original)

    def test_report_loader_evicts_foreign_identity_and_checks_real_origin(self):
        name = self.module.REPORT_MODULE_NAME
        previous = sys.modules.get(name)
        self.addCleanup(lambda: sys.modules.pop(name, None) if previous is None else sys.modules.__setitem__(name, previous))
        foreign = types.ModuleType(name)
        foreign.__file__ = str(Path(self.directory.name) / "f2m_report_i18n.py")
        foreign.TOOL_VERSION = self.module.TOOL_VERSION
        foreign._F2M_IMPORT_COMPLETE = True
        foreign.translate_english = lambda value: "FOREIGN"
        sys.modules[name] = foreign
        rendered = self.module.translate("完成：同拓扑传递", locale="en")
        self.assertNotEqual(rendered, "FOREIGN")
        loaded = sys.modules[name]
        self.assertEqual(Path(loaded.__file__).resolve(), CONTENTS / "f2m_report_i18n.py")
        self.assertEqual(loaded.TOOL_VERSION, "1.4.24")
        self.assertIs(loaded._F2M_IMPORT_COMPLETE, True)

    def test_language_handler_changes_only_display_and_preference(self):
        ui = (CONTENTS / "FBXTo3dsMax_UI.ms").read_text("utf-8-sig")
        apply_body = ui.split("fn applyLanguage =", 1)[1].split("fn selectedTargetOk =", 1)[0]
        event = ui.split("on ddl_language selected index do", 1)[1].split("on F2M_Transfer_Rollout open do", 1)[0]
        for forbidden in ("checkDone =", "checkedKey =", "currentMode =", "edt_fbx.text =", "markNeedCheck", "runPython", "select ", "resetMaxFile"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, apply_body)
                self.assertNotIn(forbidden, event)
        self.assertIn("persist:false", event)
        self.assertIn("persist:true", event)
        toolbar_tree = ast.parse((CONTENTS / "f2m_toolbar.py").read_text("utf-8-sig"))
        refresh = next(node for node in toolbar_tree.body if isinstance(node, ast.FunctionDef) and node.name == "refresh_language")
        refresh_source = ast.get_source_segment((CONTENTS / "f2m_toolbar.py").read_text("utf-8-sig"), refresh)
        for forbidden in ("_schedule_safe_install", "_make_button_action", "macros.run", "QTimer("):
            self.assertNotIn(forbidden, refresh_source)


if __name__ == "__main__":
    unittest.main()
