from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SKIN_PATH = ROOT / "contents" / "f2m_skin_replace.py"
TOPOLOGY_PATH = ROOT / "contents" / "f2m_topology_transfer.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def python_function_source(source: str, name: str) -> str:
    marker = f"def {name}("
    start = source.find(marker)
    if start < 0:
        raise AssertionError(f"缺少函数：{name}")
    end = source.find("\ndef ", start + len(marker))
    return source[start:] if end < 0 else source[start:end]


def maxscript_function_source(source: str, name: str) -> str:
    marker = f"fn {name} ="
    start = source.find(marker)
    if start < 0:
        raise AssertionError(f"缺少 MAXScript 函数：{name}")
    end = source.find("\n    fn ", start + len(marker))
    return source[start:] if end < 0 else source[start:end]


class _Log:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, text: str) -> None:
        self.lines.append(text)


class NativeImportPanelBoundaryV1323Tests(unittest.TestCase):
    def test_skin_helper_verifies_previous_current_object_is_detached(self):
        source = SKIN_PATH.read_text(encoding="utf-8-sig")
        helper = maxscript_function_source(
            source,
            "releaseModifierPanelReference",
        )
        for token in (
            "subObjectLevel = 0",
            "modPanel.getCurrentObject()",
            "previousHandle = getHandleByAnim previousObject",
            "previousObject = undefined",
            "setCommandPanelTaskMode #create",
            "currentHandle = getHandleByAnim currentObject",
            "currentObject = undefined",
            "previousHandle == undefined or currentHandle != previousHandle",
        ):
            self.assertIn(token, helper)

    def test_both_native_importers_park_before_configuring_or_importing(self):
        cases = (
            (SKIN_PATH, "import_fbx", "configure_fbx_import(ctx)"),
            (
                TOPOLOGY_PATH,
                "_import_fbx_once",
                "configure_fbx_import(ctx, smoothing_groups)",
            ),
        )
        for path, function_name, configure_call in cases:
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8-sig")
                importer = python_function_source(source, function_name)
                park = importer.index("release_modifier_panel_reference()")
                configure = importer.index(configure_call)
                native_import = importer.index("rt.execute(")
                self.assertLess(park, configure)
                self.assertLess(configure, native_import)
                self.assertIn("已阻止调用原生 FBX", importer)
                self.assertIn("FBX 原生导入安全边界", importer)
                self.assertNotIn("restore_command_panel_mode", importer)

    def test_skin_boundary_failure_does_not_touch_importer_or_native_import(self):
        module = load_module(SKIN_PATH, "_f2m_test_skin_import_panel_boundary")
        execute = mock.Mock(return_value=True)
        module.rt = types.SimpleNamespace(execute=execute)
        ctx = types.SimpleNamespace(
            options=types.SimpleNamespace(fbx_path="fixture.fbx"),
            imported_nodes=[],
            log=_Log(),
        )

        with (
            mock.patch.object(module.os.path, "exists", return_value=True),
            mock.patch.object(
                module,
                "command_panel_mode_name",
                return_value="modify",
            ),
            mock.patch.object(
                module,
                "release_modifier_panel_reference",
                return_value=False,
            ),
            mock.patch.object(module, "configure_fbx_import") as configure,
            mock.patch.object(module, "all_scene_nodes") as enumerate_nodes,
        ):
            with self.assertRaisesRegex(RuntimeError, "FBX 导入前安全停靠"):
                module.import_fbx(ctx)

        configure.assert_not_called()
        enumerate_nodes.assert_not_called()
        execute.assert_not_called()

    def test_topology_boundary_failure_does_not_touch_importer_or_native_import(self):
        module = load_module(
            TOPOLOGY_PATH,
            "_f2m_test_topology_import_panel_boundary",
        )
        execute = mock.Mock(return_value=True)
        module.rt = types.SimpleNamespace(execute=execute)
        ctx = types.SimpleNamespace(
            options=types.SimpleNamespace(fbx_path="fixture.fbx"),
            imported_nodes=[],
            log=_Log(),
        )

        with (
            mock.patch.object(module.os.path, "exists", return_value=True),
            mock.patch.object(
                module,
                "command_panel_mode_name",
                return_value="modify",
            ),
            mock.patch.object(
                module,
                "release_modifier_panel_reference",
                return_value=False,
            ),
            mock.patch.object(module, "configure_fbx_import") as configure,
            mock.patch.object(module, "all_scene_nodes") as enumerate_nodes,
        ):
            with self.assertRaisesRegex(RuntimeError, "FBX 导入前安全停靠"):
                module._import_fbx_once(ctx, False)

        configure.assert_not_called()
        enumerate_nodes.assert_not_called()
        execute.assert_not_called()

    def test_final_mode1_normal_pair_is_also_parked(self):
        source = TOPOLOGY_PATH.read_text(encoding="utf-8-sig")
        process = python_function_source(source, "_process_imported_pairs")
        self.assertIn("_release_completed_pair_boundary(ctx, object_name)", process)
        self.assertNotIn("pair_index + 1 < len(handle_queue)", process)


if __name__ == "__main__":
    unittest.main()
