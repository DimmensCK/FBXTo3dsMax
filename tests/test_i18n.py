"""Language preferences and display-only contracts; no Max or user settings writes."""
import ast
import builtins
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
        self.assertEqual(self.module.text("ui.meta", locale="en", author="Dimmens", version="1.4.25"),
                         "Author: Dimmens    Version: 1.4.25")
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
        self.assertEqual(loaded.TOOL_VERSION, "1.4.25")
        self.assertIs(loaded._F2M_IMPORT_COMPLETE, True)

    def test_language_handler_changes_only_display_and_preference(self):
        ui = (CONTENTS / "FBXTo3dsMax_UI.ms").read_text("utf-8-sig")
        apply_body = ui.split("fn applyLanguage =", 1)[1].split("fn switchLanguage requestedLocale =", 1)[0]
        switch_body = ui.split("fn switchLanguage requestedLocale =", 1)[1].split("fn selectedTargetOk =", 1)[0]
        events = ui.split("on btn_language_zh changed state do", 1)[1].split("on F2M_Transfer_Rollout open do", 1)[0]
        for forbidden in ("checkDone =", "checkedKey =", "currentMode =", "edt_fbx.text =", "markNeedCheck", "runPython", "select ", "resetMaxFile"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, apply_body)
                self.assertNotIn(forbidden, switch_body)
                self.assertNotIn(forbidden, events)
        self.assertIn("requestedLocale:requestedLocale persist:false", switch_body)
        self.assertIn("applyLanguage()", switch_body)
        self.assertIn("requestedLocale:currentLanguage persist:true", switch_body)
        self.assertIn("requestedLocale:previousLanguage persist:false", switch_body)
        self.assertIn("currentLanguage = previousLanguage", switch_body)
        self.assertIn('switchLanguage "zh-CN"', events)
        self.assertIn('switchLanguage "en"', events)
        self.assertNotIn("if state", events)
        self.assertIn('btn_language_zh.checked = currentLanguage == "zh-CN"', apply_body)
        self.assertIn('btn_language_en.checked = currentLanguage == "en"', apply_body)
        for control in ("btn_language_zh", "btn_language_en"):
            self.assertIn(control + ".enabled = false", ui)
            self.assertIn(control + ".enabled = true", ui)
        toolbar_tree = ast.parse((CONTENTS / "f2m_toolbar.py").read_text("utf-8-sig"))
        refresh = next(node for node in toolbar_tree.body if isinstance(node, ast.FunctionDef) and node.name == "refresh_language")
        refresh_source = ast.get_source_segment((CONTENTS / "f2m_toolbar.py").read_text("utf-8-sig"), refresh)
        for forbidden in ("_schedule_safe_install", "_make_button_action", "macros.run", "QTimer("):
            self.assertNotIn(forbidden, refresh_source)

    def test_compact_language_controls_fit_existing_mode_header(self):
        ui = (CONTENTS / "FBXTo3dsMax_UI.ms").read_text("utf-8-sig")
        self.assertNotIn("ddl_language", ui)

        def bounds(control):
            declaration = next(line for line in ui.splitlines()
                               if re.match(r"\s*(?:label|checkbutton|groupBox|dotNetControl)\s+" + control + r"\s", line))
            found = re.search(r"pos:\[(\d+),(\d+)\]\s+width:(\d+)\s+height:(\d+)", declaration)
            self.assertIsNotNone(found)
            return tuple(map(int, found.groups()))

        x, y, width, _ = bounds("grp_mode")
        self.assertLessEqual(y, 16)  # No dedicated language row above the mode frame.
        mode_top = bounds("btn_mode_topo")[1]
        header = [bounds(name) for name in ("lbl_language", "btn_language_zh", "btn_language_en")]
        for left, top, control_width, height in header:
            self.assertGreater(left, x + width // 2)
            self.assertGreaterEqual(top, y)
            self.assertLessEqual(left + control_width, x + width)
            self.assertLessEqual(top + height, mode_top)
        for previous, following in zip(header, header[1:]):
            self.assertLessEqual(previous[0] + previous[2], following[0])


    def _decoded_language_bridge(self, variable, locale, persist):
        """Execute the actual bridge literals; native UI calls remain a modeled boundary."""
        ui = (CONTENTS / "FBXTo3dsMax_UI.ms").read_text("utf-8-sig")
        body = ui.split("    fn initializeLanguage ", 1)[1].split("    fn tr ", 1)[0]
        expressions = []
        for line in body.splitlines():
            line = line.strip()
            for prefix in ("local " + variable + " = ", variable + " += "):
                if line.startswith(prefix):
                    expressions.append(line[len(prefix):])
                    break
        values = {"pyString pyLanguageFile": json.dumps(str(CONTENTS / "f2m_i18n.py")),
                  "pyString requestedLocale": json.dumps(locale),
                  "pyString currentLanguage": json.dumps(locale),
                  '(if persist then "True" else "False")': "True" if persist else "False"}
        result = []
        for expression in expressions:
            while expression:
                expression = expression.lstrip(" +")
                if not expression:
                    break
                if expression.startswith('"'):
                    value, length = json.JSONDecoder().raw_decode(expression)
                    result.append(value)
                    expression = expression[length:]
                else:
                    selected = next((term for term in values if expression.startswith(term)), None)
                    self.assertIsNotNone(selected, expression)
                    result.append(values[selected])
                    expression = expression[len(selected):]
        return "".join(result)

    def _actual_language_switch(self, failure=None, existing=True, rollback_failure=False):
        """Real bridge/i18n/toolbar code with fake Qt/native control boundaries, no Max."""
        if existing:
            self.module.set_language("zh-CN", persist=True)
        else:
            self.module.set_language("zh-CN", persist=False)
        path = self.module.language_file()
        before = path.read_bytes() if path.exists() else None
        name = self.module.MODULE_NAME
        previous_module = sys.modules.get(name)
        self.addCleanup(lambda: sys.modules.pop(name, None) if previous_module is None
                        else sys.modules.__setitem__(name, previous_module))
        sys.modules[name] = self.module
        original_api = getattr(builtins, "_FBXTO3DSMAX_TOOLBAR_API", None)
        had_api = hasattr(builtins, "_FBXTO3DSMAX_TOOLBAR_API")
        self.addCleanup(lambda: setattr(builtins, "_FBXTO3DSMAX_TOOLBAR_API", original_api)
                        if had_api else delattr(builtins, "_FBXTO3DSMAX_TOOLBAR_API"))
        store, events, calls = {}, [], {"refresh": 0, "readback": 0, "catalog": 0}

        class Button:
            def setText(inner, value):
                calls["refresh"] += 1
                events.append("refresh")
                if (failure == "refresh" and calls["refresh"] == 2) or (
                        rollback_failure and calls["refresh"] >= 3):
                    raise RuntimeError("Injected actual toolbar setText failure")
                inner.text = value

            def setToolTip(inner, value): pass
            def setStatusTip(inner, value): pass
            def setAccessibleName(inner, value): pass

        button = Button()
        toolbar_source = (CONTENTS / "f2m_toolbar.py").read_text("utf-8-sig")
        refresh = next(node for node in ast.parse(toolbar_source).body
                       if isinstance(node, ast.FunctionDef) and node.name == "refresh_language")
        scope = {"_manager": types.SimpleNamespace(shutting_down=False, button=button, fallback_toolbar=None),
                 "_t": self.module.translate, "BUTTON_TEXT": "FBX 转 MAX", "BUTTON_TOOLTIP": "打开 FBXTo3dsMax",
                 "_fit_button_size": lambda value: None, "builtins": builtins,
                 "API_SLOT": "_FBXTO3DSMAX_TOOLBAR_API", "_language_module": lambda: self.module}
        exec(compile(ast.Module(body=[refresh], type_ignores=[]), "actual_toolbar_refresh.py", "exec"), scope)
        setattr(builtins, "_FBXTO3DSMAX_TOOLBAR_API", {"refresh_language": scope["refresh_language"]})

        def set_global(key, value):
            if key == "F2M_UI_LanguageCode":
                calls["readback"] += 1
                if failure == "readback" and calls["readback"] == 2:
                    value = "zh-CN"  # Valid but wrong locale must also reject before save.
            store[key] = value

        rt = types.SimpleNamespace(globalVars=types.SimpleNamespace(set=set_global),
                                   Name=str, Array=lambda *values: list(values))
        original_catalog = self.module.ui_catalog_english

        def catalog():
            calls["catalog"] += 1
            if failure == "catalog" and calls["catalog"] == 2:
                raise RuntimeError("Injected actual catalog failure")
            return original_catalog()

        original_replace = self.module.os.replace

        def replace(source, destination):
            events.append("replace")
            if failure == "save":
                raise OSError("Injected atomic save failure")
            return original_replace(source, destination)

        def initialize(locale, persist):
            exec(compile(self._decoded_language_bridge("code", locale, persist),
                         "actual_initialize_preview.py", "exec"), {})
            actual = store["F2M_UI_LanguageCode"]
            # These two native readback gates are also asserted against the actual source below.
            if actual not in ("zh-CN", "en") or actual != locale:
                raise RuntimeError("Language preview readback mismatch")
            if persist:
                commit = self._decoded_language_bridge("commitCode", actual, persist)
                if commit:
                    exec(compile(commit, "actual_initialize_commit.py", "exec"), {})
            return actual

        errors = []
        with mock.patch.dict(sys.modules, {"pymxs": types.SimpleNamespace(runtime=rt)}), \
                mock.patch.object(self.module, "ui_catalog_english", side_effect=catalog), \
                mock.patch.object(self.module.os, "replace", side_effect=replace):
            try:
                current = initialize("en", False)
                # Native applyLanguage is not executable without Max; its boundary is modeled.
                if failure == "display":
                    raise RuntimeError("Injected native display boundary failure")
                current = initialize(current, True)
            except (RuntimeError, OSError) as error:
                errors.append(str(error))
                try:
                    initialize("zh-CN", False)
                except (RuntimeError, OSError) as recovery_error:
                    errors.append("Language session/display rollback failed: " + str(recovery_error))
                current = "zh-CN"
        after = path.read_bytes() if path.exists() else None
        return {"before": before, "after": after, "current": current,
                "session": self.module.get_language(), "toolbar": getattr(button, "text", None),
                "errors": errors, "events": events,
                "temporary": list(path.parent.glob(".language-*.tmp"))}

    def test_actual_language_bridge_failures_cannot_commit_preferences(self):
        for existing in (True, False):
            for failure in ("refresh", "catalog", "readback", "display", "save"):
                with self.subTest(existing=existing, failure=failure):
                    path = self.module.language_file()
                    if path.exists():
                        path.unlink()
                    result = self._actual_language_switch(failure, existing)
                    self.assertTrue(result["errors"])
                    self.assertEqual(result["after"], result["before"])
                    self.assertEqual(result["session"], "zh-CN")
                    self.assertEqual(result["current"], "zh-CN")
                    self.assertEqual(result["toolbar"], "FBX 转 MAX")
                    self.assertEqual(result["temporary"], [])
                    self.assertEqual(result["events"].count("replace"), int(failure == "save"))

    def test_actual_language_bridge_success_commits_once_after_display(self):
        result = self._actual_language_switch()
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["after"], b"en\n")
        self.assertEqual(result["session"], "en")
        self.assertEqual(result["current"], "en")
        self.assertEqual(result["toolbar"], "FBX to MAX")
        self.assertEqual(result["events"], ["refresh", "refresh", "replace"])
        self.assertEqual(result["temporary"], [])

    def test_language_commit_has_no_post_replace_filesystem_cleanup(self):
        with mock.patch.object(self.module.os.path, "exists", side_effect=AssertionError("post-commit exists")), \
                mock.patch.object(self.module.os, "unlink", side_effect=AssertionError("post-commit unlink")):
            self.module.set_language("en", persist=True)
        self.assertEqual(self.module.language_file().read_bytes(), b"en\n")
        self.assertEqual(self.module.get_language(), "en")

    def test_atomic_save_cleanup_keeps_original_error(self):
        self.module.set_language("zh-CN", persist=True)
        with mock.patch.object(self.module.os, "replace", side_effect=OSError("original save failure")), \
                mock.patch.object(self.module.os, "unlink", side_effect=PermissionError("cleanup failure")):
            with self.assertRaisesRegex(OSError, "original save failure"):
                self.module.set_language("en", persist=True)
        self.assertEqual(self.module.language_file().read_bytes(), b"zh-CN\n")
        self.assertEqual(self.module.get_language(), "zh-CN")

    def test_rollback_failure_is_reported_without_committing(self):
        result = self._actual_language_switch("refresh", rollback_failure=True)
        self.assertEqual(result["after"], result["before"])
        self.assertEqual(len(result["errors"]), 2)
        self.assertIn("rollback failed", result["errors"][1])
        ui = (CONTENTS / "FBXTo3dsMax_UI.ms").read_text("utf-8-sig")
        body = ui.split("fn switchLanguage requestedLocale =", 1)[1].split("fn selectedTargetOk =", 1)[0]
        self.assertIn("Language session/display rollback failed:", body)
        self.assertIn("Language control rollback failed:", body)
        self.assertIn("writeUiDiagnostic languageError", body)
        self.assertNotIn("catch()", body)

    def test_actual_commit_bridge_is_after_native_readback_and_identity_checked(self):
        ui = (CONTENTS / "FBXTo3dsMax_UI.ms").read_text("utf-8-sig")
        body = ui.split("    fn initializeLanguage ", 1)[1].split("    fn tr ", 1)[0]
        self.assertLess(body.index('throw "Language preview readback mismatch"'),
                        body.index("python.Execute commitCode"))
        self.assertNotIn("persist=True", self._decoded_language_bridge("code", "en", True))
        code = self._decoded_language_bridge("commitCode", "en", True)
        tree = ast.parse(code)
        final = tree.body[-1]
        self.assertIsInstance(final, ast.Expr)
        self.assertEqual(ast.get_source_segment(code, final), "m.set_language(chosen, persist=True)")
        foreign = types.SimpleNamespace(__file__=str(Path(self.directory.name) / "foreign.py"),
                                        TOOL_VERSION="1.4.25", _F2M_IMPORT_COMPLETE=True,
                                        get_language=lambda: "en", set_language=mock.Mock())
        with mock.patch.dict(sys.modules, {self.module.MODULE_NAME: foreign}):
            with self.assertRaisesRegex(RuntimeError, "identity/version mismatch"):
                exec(compile(code, "actual_commit_identity.py", "exec"), {})
        foreign.set_language.assert_not_called()


if __name__ == "__main__":
    unittest.main()
