"""用户可见中文、方向术语和内部诊断分离回归。"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(filename: str, name: str):
    path = ROOT / "contents" / filename
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class ChineseUserSurfaceTests(unittest.TestCase):
    def test_metadata_and_smoothing_errors_are_chinese(self) -> None:
        metadata = load_module(
            "f2m_fbx_metadata.py",
            "_f2m_test_chinese_metadata",
        )
        smoothing = load_module(
            "f2m_smoothing.py",
            "_f2m_test_chinese_smoothing",
        )
        values = (
            metadata.FbxMetadataIOError("English detail"),
            metadata.FbxFormatError("English detail"),
            metadata.FbxAmbiguityError("English detail"),
            smoothing.SmoothingInputError("English detail"),
            smoothing.NonManifoldTopologyError("English detail"),
            smoothing.UnrepresentableSmoothingError("English detail"),
            smoothing.ColoringSearchLimitError("English detail"),
            smoothing.SmoothingValidationError("English detail"),
        )
        for value in values:
            text = str(value)
            self.assertRegex(text, r"[\u3400-\u9fff]")
            self.assertNotIn("English detail", text)

    def test_transfer_traceback_is_written_only_to_internal_diagnostic(self) -> None:
        for filename, name in (
            ("f2m_topology_transfer.py", "_f2m_test_chinese_topology"),
            ("f2m_skin_replace.py", "_f2m_test_chinese_skin"),
        ):
            module = load_module(filename, name)
            with tempfile.TemporaryDirectory() as folder, mock.patch.dict(
                os.environ,
                {"LOCALAPPDATA": folder},
            ):
                path = module.write_diagnostic_file(
                    ["Traceback (most recent call last):\nRuntimeError: English"],
                    "test_chinese",
                )
                self.assertTrue(path)
                text = pathlib.Path(path).read_text(encoding="utf-8")
                self.assertIn("内部诊断", text)
                self.assertIn("Traceback", text)

            source = (ROOT / "contents" / filename).read_text(encoding="utf-8-sig")
            self.assertEqual(
                module.visible_exception_text(
                    RuntimeError("中文前缀：English detail")
                ),
                "底层操作失败，具体技术信息已写入内部诊断文件。",
            )
            self.assertNotIn(
                'error_text = f"传递失败：{exc}\\n\\n{traceback.format_exc()}"',
                source,
            )
            self.assertIn("write_diagnostic_file(ctx.diagnostics", source)

    def test_popup_sources_do_not_append_raw_exceptions(self) -> None:
        sources = {
            filename: (ROOT / filename).read_text(encoding="utf-8-sig")
            for filename in (
                "contents/FBXTo3dsMax_UI.ms",
                "contents/FBXTo3dsMax.mcr",
                "contents/f2m_toolbar.py",
                "Install_FBXTo3dsMax.ms",
                "Uninstall_FBXTo3dsMax.ms",
            )
        }
        self.assertNotIn(
            'messageBox ("Python 插件执行失败：\\n\\n" +',
            sources["contents/FBXTo3dsMax_UI.ms"],
        )
        self.assertNotIn(
            'messageBox ("运行自检失败：\\n\\n" +',
            sources["contents/FBXTo3dsMax_UI.ms"],
        )
        self.assertNotIn(
            'messageBox ("无法打开 FBXTo3dsMax。\\n\\n" +',
            sources["contents/FBXTo3dsMax.mcr"],
        )
        self.assertNotIn(
            'installError + "\\n\\n日志',
            sources["Install_FBXTo3dsMax.ms"],
        )
        self.assertNotIn(
            "uninstallError +",
            sources["Uninstall_FBXTo3dsMax.ms"],
        )

    def test_direction_labels_and_package_description_are_unambiguous(self) -> None:
        ui = (ROOT / "contents" / "FBXTo3dsMax_UI.ms").read_text(encoding="utf-8-sig")
        topology = (ROOT / "contents" / "f2m_topology_transfer.py").read_text(
            encoding="utf-8-sig"
        )
        skin = (ROOT / "contents" / "f2m_skin_replace.py").read_text(encoding="utf-8-sig")
        package = (ROOT / "PackageContents.xml").read_text(encoding="utf-8-sig")

        self.assertIn('checkbox chk_keep_mat "兼容：改用 Max 源材质"', ui)
        self.assertIn("checked:false visible:false", ui)
        self.assertIn("FBX 提供逐顶点权重、Unnormalized 和 DQ 数据", ui)
        self.assertNotIn("替换时保留目标材质", ui)
        self.assertIn("<- FBX 目标模型", topology)
        self.assertIn("Max 源模型 <- FBX 目标模型", skin)
        self.assertNotIn(" <= FBX目标 ", topology)
        self.assertNotIn("检查模式：{options.dry_run}", topology + skin)
        self.assertIn(
            "把 FBX 目标模型的数据传递给所选的 3ds Max 源模型。",
            package,
        )

    def test_selection_identity_never_uses_ambiguous_name_as_cache_key(self) -> None:
        ui = (ROOT / "contents" / "FBXTo3dsMax_UI.ms").read_text(encoding="utf-8-sig")
        key_start = ui.index("fn selectedTargetsKey")
        key_end = ui.index("fn currentCheckKey", key_start)
        key_source = ui[key_start:key_end]
        restore_start = ui.index("fn restoreSelectionByHandlesOrNames")
        restore_end = ui.index("fn confirmRunForSelection", restore_start)
        restore_source = ui[restore_start:restore_end]

        self.assertIn('if h == undefined do return ""', key_source)
        self.assertNotIn("catch(h = n.name as string)", key_source)
        self.assertNotIn("getNodeByName originalName", restore_source)
        self.assertIn("if exactMatches.count == 1", restore_source)

    def test_check_cache_matches_original_invalidation_contract(self) -> None:
        ui = (ROOT / "contents" / "FBXTo3dsMax_UI.ms").read_text(encoding="utf-8-sig")
        start = ui.index("on btn_run pressed do")
        run_handler = ui[start:]
        key_start = ui.index("fn currentCheckKey")
        key_end = ui.index("fn markNeedCheck", key_start)
        key_source = ui[key_start:key_end]
        option_start = ui.index("fn markOptionsChanged")
        option_end = ui.index("fn markChecked", option_start)
        option_source = ui[option_start:option_end]

        self.assertEqual(run_handler.count("currentCheckKey()"), 1)
        self.assertIn("local runCheckKey = currentCheckKey()", run_handler)
        self.assertIn("checkIsCurrent runCheckKey", run_handler)
        self.assertIn("confirmRunForSelection()", run_handler)
        self.assertIn("fbxFileFingerprint()", key_source)
        self.assertIn("chk_hidden.checked", key_source)
        self.assertIn("selectedTargetsKey()", key_source)
        for option_name in (
            "chk_shape",
            "chk_matid",
            "chk_normals",
            "chk_smoothing",
            "chk_uv1",
            "chk_uv2",
            "chk_uv3",
            "chk_vc",
            "chk_alpha",
            "chk_backup",
            "chk_keep_mat",
            "chk_keep_imported",
        ):
            self.assertNotIn(option_name, key_source)
        self.assertNotIn("markNeedCheck()", option_source)
        self.assertNotIn("nodeStateFingerprint", ui)
        self.assertNotIn("snapshotAsMesh", ui)
        self.assertNotIn("sha256Text", ui)

    def test_runtime_module_is_reused_until_path_or_version_changes(self) -> None:
        ui = (ROOT / "contents" / "FBXTo3dsMax_UI.ms").read_text(encoding="utf-8-sig")

        self.assertIn("_f2m_module = sys.modules.get(_f2m_module_name)", ui)
        self.assertIn("if not _f2m_reuse:", ui)
        self.assertIn(
            "str(getattr(_f2m_module, 'TOOL_VERSION', ''))",
            ui,
        )
        self.assertIn("_F2M_IMPORT_COMPLETE", ui)
        self.assertIn(
            "callable(getattr(_f2m_module, 'run_from_max', None))",
            ui,
        )
        self.assertIn(
            "if sys.modules.get(_f2m_module_name) is _f2m_module:",
            ui,
        )
        self.assertNotIn(
            'code += "sys.modules.pop(_f2m_module_name, None)\\n"\n'
            '        code += "_f2m_spec',
            ui,
        )

    def test_local_runtime_loader_evicts_partial_modules(self) -> None:
        topology = load_module(
            "f2m_topology_transfer.py",
            "_f2m_test_partial_loader_host",
        )
        module_name = "_f2m_test_partial_runtime"
        with tempfile.TemporaryDirectory() as folder:
            host_path = pathlib.Path(folder) / "host.py"
            failing_path = pathlib.Path(folder) / "failing.py"
            host_path.write_text("# host\n", encoding="utf-8")
            failing_path.write_text(
                "TOOL_VERSION = '1.4.24'\n"
                "raise RuntimeError('partial import')\n",
                encoding="utf-8",
            )
            original_file = topology.__file__
            topology.__file__ = str(host_path)
            try:
                with self.assertRaisesRegex(RuntimeError, "partial import"):
                    topology._load_local_runtime_module(
                        failing_path.name,
                        module_name,
                    )
                self.assertNotIn(module_name, sys.modules)
            finally:
                topology.__file__ = original_file
                sys.modules.pop(module_name, None)

    def test_ui_uses_supported_maxscript_python_status_bridge(self) -> None:
        ui = (ROOT / "contents" / "FBXTo3dsMax_UI.ms").read_text(encoding="utf-8-sig")

        # Autodesk's Python Core Interface exposes Execute/ExecuteFile, but no
        # Eval method.  Calling python.Eval lets the backend finish and then
        # throws only after the user closes the successful report dialog.
        self.assertNotRegex(ui, r"(?i)\bpython\.eval\b")
        self.assertIn("global F2M_UI_RunStatus", ui)
        self.assertIn(
            "globalVars.set(_f2m_bridge_rt.Name('F2M_UI_RunStatus')",
            ui,
        )
        self.assertIn("succeeded = (F2M_UI_RunStatus == 1)", ui)
        self.assertEqual(
            ui.count(
                "python.Execute code throwOnError:true clearUndoBuffer:false"
            ),
            3,
        )
        self.assertIn("initializeLanguage", ui)
        self.assertIn("writeUiDiagnostic", ui)

    def test_selfcheck_rejects_ui_bridge_semantic_mutations(self) -> None:
        selfcheck = load_module(
            "f2m_selfcheck.py",
            "_f2m_test_ui_bridge_selfcheck",
        )
        ui = (ROOT / "contents" / "FBXTo3dsMax_UI.ms").read_text(encoding="utf-8-sig")
        selfcheck._validate_ui_bridge_source(ui)

        mutations = {
            "重新使用不支持的 python.Eval": ui.replace(
                "succeeded = (F2M_UI_RunStatus == 1)",
                'succeeded = (python.Eval "__f2m_run_ok") == true',
                1,
            ),
            "缺少运行前 -1 重置": ui.replace(
                "F2M_UI_RunStatus = -1",
                "F2M_UI_RunStatus = -2",
                1,
            ),
            "未读取 LAST_RUN_OK": ui.replace(
                "'LAST_RUN_OK', False",
                "'LAST_RUN_FAILED', False",
                1,
            ),
            "成功状态不是 1": ui.replace(
                "1 if __f2m_run_ok else 0",
                "7 if __f2m_run_ok else 0",
                1,
            ),
            "失败状态不是 0": ui.replace(
                "1 if __f2m_run_ok else 0",
                "1 if __f2m_run_ok else 7",
                1,
            ),
            "诊断标题不是中文": ui.replace(
                "FBXTo3dsMax 界面内部诊断",
                "FBXTo3dsMax UI Diagnostic",
                1,
            ),
            "诊断目录错误": ui.replace(
                "FBXTo3dsMax\\\\Diagnostics\\\\",
                "FBXTo3dsMax\\\\Other\\\\",
                1,
            ),
            "诊断编码不是无 BOM UTF-8": ui.replace(
                'dotNetObject "System.Text.UTF8Encoding" false',
                'dotNetObject "System.Text.UTF8Encoding" true',
                1,
            ),
            "诊断未使用 UTF-8 写入": ui.replace(
                "fileClass.WriteAllText diagnosticPath diagnosticText utf8NoBom",
                "fileClass.WriteAllText diagnosticPath diagnosticText",
                1,
            ),
            "异常分支未写诊断": ui.replace(
                "local uiDiagnostic = writeUiDiagnostic uiException",
                'local uiDiagnostic = ""',
                1,
            ),
            "执行入口会清空撤销栈": ui.replace(
                "python.Execute code throwOnError:true clearUndoBuffer:false",
                "python.Execute code throwOnError:true",
                1,
            ),
        }
        for label, mutated_ui in mutations.items():
            with self.subTest(label=label):
                self.assertNotEqual(ui, mutated_ui, "突变没有命中生产代码。")
                with self.assertRaises(RuntimeError):
                    selfcheck._validate_ui_bridge_source(mutated_ui)

    def test_selfcheck_rejects_node_wrapper_and_nested_normal_regressions(self) -> None:
        selfcheck = load_module(
            "f2m_selfcheck.py",
            "_f2m_test_release_safety_selfcheck",
        )
        ui = (ROOT / "contents" / "FBXTo3dsMax_UI.ms").read_text(encoding="utf-8-sig")
        topology = (ROOT / "contents" / "f2m_topology_transfer.py").read_text(
            encoding="utf-8-sig"
        )
        skin = (ROOT / "contents" / "f2m_skin_replace.py").read_text(encoding="utf-8-sig")

        selfcheck._validate_ui_bridge_source(ui)
        selfcheck._validate_transfer_release_source(topology, skin)

        wrapper_mutation = ui.replace(
            "local handles = #()",
            "local handles = selection as array",
            1,
        )
        self.assertNotEqual(ui, wrapper_mutation)
        with self.assertRaises(RuntimeError):
            selfcheck._validate_ui_bridge_source(wrapper_mutation)
        with self.assertRaises(RuntimeError):
            selfcheck._validate_transfer_release_source(
                topology.replace(
                    "srcData = snapshotEditNormalsDataFlat src srcMod",
                    "srcData = snapshotEditNormalsData src srcMod",
                    1,
                ),
                skin,
            )
        with self.assertRaises(RuntimeError):
            selfcheck._validate_transfer_release_source(
                topology,
                skin.replace(
                    '_set_fbx_importer_param("SmoothingGroups", False)',
                    '_set_fbx_importer_param("SmoothingGroups", True)',
                    1,
                ),
            )

    def test_shape_readback_uses_scale_aware_max_precision_tolerance(self) -> None:
        topology = (ROOT / "contents" / "f2m_topology_transfer.py").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn("fn pointReadbackTolerance firstPoint secondPoint", topology)
        self.assertIn("fn pointsReadbackEqual firstPoint secondPoint", topology)
        self.assertIn("0.000002 + (scale * 0.000002)", topology)
        self.assertIn(
            "local nodeTolerance = pointReadbackTolerance actualNode expectedNode",
            topology,
        )
        self.assertIn(
            "local localTolerance = pointReadbackTolerance actualLocal expectedLocal",
            topology,
        )
        self.assertIn(
            "local tolerance = pointReadbackTolerance actual originalVerts[i]",
            topology,
        )

    def test_topology_fbx_import_is_readback_verified_and_restored(self) -> None:
        topology = (ROOT / "contents" / "f2m_topology_transfer.py").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn(
            "readback = rt.F2M_Helper.fbxImporterGet(name)",
            topology,
        )
        self.assertIn(
            "if not _importer_values_equal(name, value, readback):",
            topology,
        )
        self.assertIn(
            "import_result = rt.execute("
            "f'importFile \"{escaped}\" #noPrompt')",
            topology,
        )
        self.assertIn(
            'raise RuntimeError("3ds Max 导入命令明确返回失败状态。")',
            topology,
        )
        self.assertIn(
            'tracking_error = ""',
            topology,
        )
        self.assertIn(
            "tracking_error = _exception_text_and_release(exc)",
            topology,
        )
        self.assertIn(
            "finally:\n            try:\n                "
            "_restore_fbx_importer(ctx, snapshot)",
            topology,
        )

    def test_sg_only_stops_if_stale_f2m_normals_remain(self) -> None:
        topology = load_module(
            "f2m_topology_transfer.py",
            "_f2m_test_sg_only_cleanup_failure",
        )

        class FakeHelper:
            lastMessage = "模拟旧法线修改器仍然存在"
            write_called = False

            @staticmethod
            def canSetFaceSmoothingGroups(_node, _count):
                return True

            @staticmethod
            def removeF2MNormalModifiers(_node):
                return 0

            @staticmethod
            def countF2MNormalModifiers(_node):
                return 1

            @classmethod
            def setFaceSmoothingGroups(cls, _node, _masks):
                cls.write_called = True
                return True

        fake_runtime = mock.Mock()
        fake_runtime.F2M_Helper = FakeHelper
        context = topology.TransferContext(
            topology.TransferOptions(
                fbx_path="",
                transfer_smoothing_groups=True,
                transfer_normals=False,
                show_ui=False,
            ),
            topology.TransferLog(),
        )
        report = topology.ObjectReport(name="Max源模型", status="test")
        with (
            mock.patch.object(topology, "rt", fake_runtime),
            mock.patch.object(
                topology,
                "_resolved_topology_map",
                return_value=object(),
            ),
            mock.patch.object(
                topology,
                "smoothing_masks_for_source",
                return_value=[1],
            ),
            mock.patch.object(
                topology,
                "remap_per_face_values",
                return_value=[1],
            ),
        ):
            ok = topology.copy_smoothing_groups(
                mock.Mock(name="FBX目标模型"),
                mock.Mock(name="Max源模型"),
                context,
                report,
            )

        self.assertFalse(ok)
        self.assertFalse(FakeHelper.write_called)
        self.assertTrue(
            any("未能完整清理" in message for message in report.messages),
            report.messages,
        )


if __name__ == "__main__":
    unittest.main()
