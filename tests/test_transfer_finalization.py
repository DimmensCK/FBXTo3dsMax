"""Real transfer orchestration/cleanup/rollback with fake native and IO boundaries.

These tests do not emulate mesh/Skin algorithms or qualify the 3ds Max host.
They exercise the production run functions and their actual recovery helpers.
"""
import contextlib
import importlib.util
import os
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid


CONTENTS = Path(__file__).resolve().parents[1] / "contents"


def load_engine(filename):
    name = "_finalization_test_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, CONTENTS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return name, module


class Node:
    def __init__(self, handle, name, geometry=True):
        self.handle = handle
        self.name = name
        self.geometry = geometry
        self.isNodeHidden = False
        self.content = "original"


class NativeScene:
    def __init__(self):
        self.nodes = {1: Node(1, "Body"), 2: Node(2, "Control", False)}
        self.selection = [self.nodes[2], self.nodes[1]]
        self.select_calls = 0
        self.deleted = []
        self.selection_fault = ""
        self.reverse_selection = True
        self.objects_fault = False
        self.validity_fault = ""
        self.handle_fault = ""

    @property
    def objects(self):
        if self.objects_fault:
            self.objects_fault = False
            raise RuntimeError("场景枚举故障")
        return list(self.nodes.values())

    def getHandleByAnim(self, node):
        if node.handle == 2:
            fault, self.handle_fault = self.handle_fault, ""
            if fault == "throw":
                raise RuntimeError("原生句柄读取故障")
            if fault == "zero":
                return 0
            if fault == "duplicate":
                return 1
            if fault == "bool":
                return True
            if fault == "float":
                return 2.0
        return node.handle

    def isValidNode(self, node):
        if node.handle == 2:
            fault, self.validity_fault = self.validity_fault, ""
            if fault == "throw":
                raise RuntimeError("原生有效性读取故障")
            if fault == "false":
                return False
        return self.nodes.get(node.handle) is node

    def getAnimByHandle(self, handle):
        return self.nodes.get(int(handle))

    def select(self, nodes):
        self.select_calls += 1
        if self.selection_fault == "always" or (
            self.selection_fault == "throw" and self.select_calls == 1
        ):
            raise RuntimeError("选择写入故障")
        if self.selection_fault == "readback" and self.select_calls == 1:
            self.selection = []
        else:
            # Max selection order is not part of the restoration contract.
            self.selection = list(nodes)
            if self.reverse_selection:
                self.selection.reverse()

    def clearSelection(self):
        self.select([])

    def delete_handles(self, handles):
        handles = set(handles)
        self.deleted.append(handles)
        for handle in handles:
            self.nodes.pop(handle, None)
        self.selection = [node for node in self.selection if node.handle in self.nodes]

    def execute(self, text):
        match = re.fullmatch(
            r"F2M_Helper.setNodeHiddenFlag \(getAnimByHandle (\d+)\) ([01])", text
        )
        if not match:
            raise AssertionError("Unexpected native operation: " + text)
        self.nodes[int(match[1])].isNodeHidden = bool(int(match[2]))
        return True

    def format(self, *args):
        pass

    def messageBox(self, *args, **kwargs):
        pass


class TransferFinalizationTests(unittest.TestCase):
    def setUp(self):
        # Reports stay outside source/installation directories, even in the suite.
        parent = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
        parent = parent / "FBXTo3dsMax" / "Validation"
        parent.mkdir(parents=True, exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(prefix="finalization_pure_", dir=parent)
        self.addCleanup(self.folder.cleanup)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {"LOCALAPPDATA": self.folder.name}))
        self.actual_importers = {}
        self.report_boundary_states = {}

    def engine(self, skin=False, backup=True, fault="", notification=False):
        name, module = load_engine(
            "f2m_skin_replace.py" if skin else "f2m_topology_transfer.py"
        )
        self.addCleanup(sys.modules.pop, name, None)
        self.actual_importers[module] = (
            module.import_fbx if skin else module._import_fbx_once
        )
        scene = NativeScene()
        contexts = []
        constructor = module.TransferContext

        def make_context(*args):
            ctx = constructor(*args)
            contexts.append(ctx)
            return ctx

        def import_boundary(ctx):
            source = Node(3, "Body")
            scene.nodes[3] = source
            ctx.imported_nodes.append(source)
            scene.selection = [source]
            if fault == "import":
                raise RuntimeError("导入中途故障")

        def native_replace(source, record, ctx, report):
            target = scene.nodes[record.handle]
            if backup:
                target.name = "Body__backup"
                target.isNodeHidden = True
                ctx.committed_replacements.append(module.CommittedReplacement(
                    target_record=record, candidate_handle=source.handle,
                    candidate_name="Body", old_hidden=False, report=report,
                ))
            else:
                scene.delete_handles({record.handle})
            record.skip_restore = True
            source.name = record.original_name
            ctx.keep_imported_nodes.add(source.handle)
            ctx.replacement_nodes.add(source.handle)
            if notification:
                ctx.missing_transfer_attrs.append("Body：UV 1")
            return True

        def native_topology_pairs(ctx, records):
            # The per-object native transaction has committed successfully.
            scene.nodes[records[0].handle].content = "transferred"
            ctx.reports.append(module.ObjectReport(name="Body", status="完成：同拓扑传递"))
            if notification:
                ctx.normal_residual_notice_objects.add("Body")

        values = dict(
            rt=scene, pymxs=SimpleNamespace(redraw=lambda enabled: contextlib.nullcontext()),
            ensure_runtime=lambda: None, TransferContext=make_context,
            is_geometry_node=lambda node: node.geometry,
            ensure_maxscript_heap_reserve=lambda: (1, 1),
            import_fbx=import_boundary,
            _display_text=lambda text: text,
            _language_runtime=lambda: SimpleNamespace(get_language=lambda: "zh-CN"),
        )
        if skin:
            values.update(
                mesh_counts=lambda node: (4, 5, 2),
                transform_pair_warnings=lambda source, target: [],
                node_state_warnings=lambda node: [],
                replace_with_source_skin=native_replace,
                _delete_node_handles_strict=lambda handles, names, label: scene.delete_handles(handles),
            )
        else:
            values.update(
                _prepare_normals_only_smoothing_targets=lambda ctx, records: None,
                _process_imported_pairs=native_topology_pairs,
                _delete_handles_strict=lambda names, label: scene.delete_handles(names),
            )
        self.stack.enter_context(patch.multiple(module, **values))
        if fault in ("throw", "readback", "always"):
            scene.selection_fault = fault
        elif fault == "heap":
            self.stack.enter_context(patch.object(
                module, "ensure_maxscript_heap_reserve", side_effect=RuntimeError("堆检查故障")
            ))
        elif fault == "objects":
            scene.objects_fault = True
        elif fault == "partial_snapshot":
            real_handle = scene.getHandleByAnim
            calls = [0]

            def handle_boundary(node):
                calls[0] += 1
                # Original selection capture consumes calls 1/2; fail during scan.
                if calls[0] == 4:
                    raise RuntimeError("句柄快照中途故障")
                return real_handle(node)

            self.stack.enter_context(patch.object(scene, "getHandleByAnim", handle_boundary))
        elif fault == "report":
            writer = module.write_log_file
            calls = [0]

            def report_boundary(text, run_id=""):
                calls[0] += 1
                if calls[0] == 1:
                    if skin:
                        self.report_boundary_states[module] = {
                            "replacement_handles": set(contexts[0].replacement_nodes),
                            "wrappers_released": all(
                                r.node is None for r in contexts[0].scene_records
                            ),
                            "rollback_entries": len(contexts[0].committed_replacements),
                        }
                    raise OSError("报告写入故障")
                return writer(text, run_id)

            self.stack.enter_context(patch.object(module, "write_log_file", report_boundary))
        if notification:
            # Fail inside the actual notice assembly, before its native UI call.
            self.stack.enter_context(patch.object(
                module, "unique_limited", side_effect=RuntimeError("通知组装故障")
            ))
        if fault in ("redraw_enter", "redraw_exit"):
            class RedrawBoundary:
                def __enter__(self):
                    if fault == "redraw_enter":
                        raise RuntimeError("重绘进入故障")
                    return self

                def __exit__(self, kind, value, traceback):
                    if fault == "redraw_exit" and kind is None:
                        raise RuntimeError("重绘退出故障")

            self.stack.enter_context(patch.object(
                module.pymxs, "redraw", lambda enabled: RedrawBoundary()
            ))
        options = module.TransferOptions(
            fbx_path="fake-native-boundary.fbx", mode="replace" if skin else "topology_only",
            backup_old_mesh=backup, show_ui=notification,
        )
        return module, scene, contexts, options

    def assert_original_scene(self, scene):
        self.assertEqual(set(scene.nodes), {1, 2})
        self.assertEqual(scene.nodes[1].name, "Body")
        self.assertEqual(scene.nodes[2].name, "Control")
        self.assertFalse(scene.nodes[1].isNodeHidden)

    def assert_failure(self, module, text):
        self.assertFalse(module.LAST_RUN_OK)
        self.assertTrue(text.startswith("传递失败："), text)
        self.assertEqual(module.LAST_RUN_SUMMARY, text)
        self.assertTrue(module.LAST_RUN_REPORT_PATH)
        report = Path(module.LAST_RUN_REPORT_PATH).read_text(encoding="utf-8")
        self.assertIn(text, report)

    def test_success_selection_is_set_based_and_recovery_state_is_discarded_last(self):
        for skin, backup in ((False, True), (True, True), (True, False)):
            with self.subTest(skin=skin, backup=backup):
                module, scene, contexts, options = self.engine(skin=skin, backup=backup)
                if not skin:
                    scene.reverse_selection = False
                text = module.run_transfer(options)
                self.assertTrue(module.LAST_RUN_OK, text)
                self.assertEqual({n.handle for n in scene.selection}, {2, 3} if skin else {1, 2})
                self.assertNotEqual(
                    [n.handle for n in scene.selection], [2, 3] if skin else [2, 1]
                )
                ctx = contexts[0]
                self.assertEqual(ctx.scene_records, [])
                self.assertEqual(ctx.keep_imported_nodes, set())
                if skin:
                    self.assertEqual(ctx.committed_replacements, [])
                    self.assertEqual(scene.nodes[3].name, "Body")
                    if backup:
                        self.assertTrue(scene.nodes[1].isNodeHidden)
                    else:
                        self.assertNotIn(1, scene.nodes)
                else:
                    self.assert_original_scene(scene)

    def test_selection_write_and_readback_faults_fail_and_recover(self):
        for skin, backup in ((False, True), (True, True), (True, False)):
            for fault in ("throw", "readback"):
                with self.subTest(skin=skin, backup=backup, fault=fault):
                    module, scene, contexts, options = self.engine(
                        skin=skin, backup=backup, fault=fault
                    )
                    text = module.run_transfer(options)
                    self.assert_failure(module, text)
                    if skin and not backup:
                        self.assertEqual(set(scene.nodes), {2, 3})
                        self.assertEqual(scene.nodes[3].name, "Body")
                        self.assertEqual({n.handle for n in scene.selection}, {2, 3})
                        self.assertFalse(any(3 in deleted for deleted in scene.deleted))
                        self.assertIn("不能将本次故障视为完整回滚", text)
                    else:
                        self.assert_original_scene(scene)
                        self.assertEqual({n.handle for n in scene.selection}, {1, 2})
                    self.assertGreaterEqual(scene.select_calls, 2)

    def test_recovery_selection_failure_keeps_primary_and_recovery_diagnostics(self):
        for skin in (False, True):
            with self.subTest(skin=skin):
                module, scene, contexts, options = self.engine(skin=skin, fault="always")
                text = module.run_transfer(options)
                self.assert_failure(module, text)
                self.assertIn("选择写入故障", text)
                self.assertIn("恢复阶段错误", text)
                self.assertIn("选择恢复失败", text)
                self.assertTrue(any("[选择恢复失败]" in d for d in contexts[0].diagnostics))
                self.assert_original_scene(scene)

    def test_report_or_notice_failure_rolls_back_backup_and_preserves_unbacked_result(self):
        for backup in (True, False):
            for fault in ("report", "notice"):
                with self.subTest(backup=backup, fault=fault):
                    module, scene, contexts, options = self.engine(
                        skin=True, backup=backup, fault=fault, notification=fault == "notice"
                    )
                    text = module.run_transfer(options)
                    self.assert_failure(module, text)
                    if fault == "report":
                        self.assertEqual(self.report_boundary_states[module], {
                            "replacement_handles": {3}, "wrappers_released": True,
                            "rollback_entries": int(backup),
                        })
                    if backup:
                        self.assert_original_scene(scene)
                        self.assertEqual({n.handle for n in scene.selection}, {1, 2})
                        self.assertTrue(any(3 in deleted for deleted in scene.deleted))
                    else:
                        self.assertEqual(set(scene.nodes), {2, 3})
                        self.assertEqual(scene.nodes[3].name, "Body")
                        self.assertEqual({n.handle for n in scene.selection}, {2, 3})
                        self.assertFalse(any(3 in deleted for deleted in scene.deleted))
                        self.assertIn("不能将本次故障视为完整回滚", text)

    def test_topology_tail_failure_keeps_committed_object_but_never_reports_success(self):
        for fault in ("report", "notice"):
            with self.subTest(fault=fault):
                module, scene, contexts, options = self.engine(
                    fault=fault, notification=fault == "notice"
                )
                text = module.run_transfer(options)
                self.assert_failure(module, text)
                self.assert_original_scene(scene)
                self.assertEqual(scene.nodes[1].content, "transferred")
                self.assertEqual({n.handle for n in scene.selection}, {1, 2})

    def test_early_or_partial_snapshot_failure_cannot_delete_original_scene(self):
        for skin in (False, True):
            for fault in ("heap", "objects", "partial_snapshot"):
                with self.subTest(skin=skin, fault=fault):
                    module, scene, contexts, options = self.engine(skin=skin, fault=fault)
                    text = module.run_transfer(options)
                    self.assert_failure(module, text)
                    self.assert_original_scene(scene)
                    self.assertEqual(contexts[0].pre_handles, None)
                    self.assertEqual(scene.deleted, [])

    def test_partial_import_uses_authoritative_snapshot_to_delete_only_new_nodes(self):
        for skin in (False, True):
            with self.subTest(skin=skin):
                module, scene, contexts, options = self.engine(skin=skin, fault="import")
                text = module.run_transfer(options)
                self.assert_failure(module, text)
                self.assert_original_scene(scene)
                self.assertEqual(contexts[0].pre_handles, {1, 2})
                self.assertEqual({n.handle for n in scene.selection}, {1, 2})
                self.assertTrue(any(deleted == {3} for deleted in scene.deleted))

    def test_no_snapshot_and_valid_empty_snapshot_are_distinct(self):
        for skin in (False, True):
            with self.subTest(skin=skin):
                module, scene, contexts, options = self.engine(skin=skin)
                ctx = module.TransferContext(options, module.TransferLog())
                ctx.imported_nodes = [scene.nodes[1]]
                with self.assertRaisesRegex(RuntimeError, "未取得完整"):
                    module.cleanup_imported_nodes(ctx)
                self.assertEqual(scene.deleted, [])
                ctx.imported_nodes.clear()
                scene.nodes.clear()
                scene.selection = []
                module.prepare_scene_names(ctx)
                self.assertEqual(ctx.pre_handles, set())
                scene.nodes[3] = Node(3, "PartialImport")
                module.cleanup_imported_nodes(ctx)
                self.assertEqual(scene.nodes, {})
                self.assertEqual(scene.deleted, [{3}])

    def test_missing_selected_node_is_an_error_not_partial_success(self):
        for skin in (False, True):
            with self.subTest(skin=skin):
                module, scene, contexts, options = self.engine(skin=skin)
                scene.nodes.pop(1)
                with self.assertRaises(RuntimeError):
                    if skin:
                        module._restore_selection_after_replace([(1, "Body"), (2, "Control")])
                    else:
                        module.restore_selection_by_handle([1, 2])

    def test_ambiguous_replacement_cannot_select_hidden_original_backup(self):
        module, scene, contexts, options = self.engine(skin=True)
        scene.nodes[1].name = "Body__backup"
        scene.nodes[1].isNodeHidden = True
        scene.nodes[3] = Node(3, "Body")
        scene.nodes[4] = Node(4, "Body")
        with self.assertRaises(RuntimeError):
            module._restore_selection_after_replace([(1, "Body"), (2, "Control")])
        self.assertEqual(scene.select_calls, 0)

    def test_direct_import_entry_captures_baseline_and_tracks_partial_native_failure(self):
        for skin in (False, True):
            with self.subTest(skin=skin):
                module, scene, contexts, options = self.engine(skin=skin)
                fixture = Path(self.folder.name) / ("skin.fbx" if skin else "topology.fbx")
                fixture.write_bytes(b"fake native-import input")
                options.fbx_path = str(fixture)
                ctx = module.TransferContext(options, module.TransferLog())
                self.assertIsNone(ctx.pre_handles)
                restored = []

                def native_import(text):
                    self.assertTrue(text.startswith("importFile "))
                    scene.nodes[3] = Node(3, "PartialImport")
                    raise RuntimeError("原生导入中途故障")

                with patch.object(scene, "execute", native_import), patch.multiple(
                    module, command_panel_mode_name=lambda: "create",
                    release_modifier_panel_reference=lambda: True,
                    configure_fbx_import=lambda *args: "settings snapshot",
                    _restore_fbx_importer=lambda context, settings: restored.append(settings),
                ):
                    with self.assertRaisesRegex(RuntimeError, "原生导入中途故障"):
                        if skin:
                            self.actual_importers[module](ctx)
                        else:
                            self.actual_importers[module](ctx, False)
                self.assertEqual(ctx.pre_handles, {1, 2})
                self.assertEqual([n.handle for n in ctx.imported_nodes], [3])
                self.assertEqual(restored, ["settings snapshot"])
                module.cleanup_imported_nodes(ctx)
                self.assert_original_scene(scene)
                self.assertEqual(scene.deleted, [{3}])

    def test_strict_prepare_snapshot_refuses_invalid_or_nonunique_native_identity(self):
        for skin in (False, True):
            for fault in ("validity_throw", "validity_false", "handle_throw", "zero", "duplicate", "bool", "float"):
                with self.subTest(skin=skin, fault=fault):
                    module, scene, contexts, options = self.engine(skin=skin)
                    ctx = module.TransferContext(options, module.TransferLog())
                    self.set_native_identity_fault(scene, fault)
                    error = None
                    try:
                        module.prepare_scene_names(ctx)
                    except RuntimeError as exc:
                        error = str(exc)
                    module.cleanup_imported_nodes(ctx)
                    self.assert_original_scene(scene)
                    self.assertIsNotNone(error)
                    self.assertIsNone(ctx.pre_handles)
                    self.assertEqual(scene.deleted, [])

    @staticmethod
    def set_native_identity_fault(scene, fault):
        if fault.startswith("validity_"):
            scene.validity_fault = fault.split("_", 1)[1]
        else:
            scene.handle_fault = fault.replace("handle_", "")

    def test_direct_import_rejects_incomplete_snapshot_before_native_import(self):
        for skin in (False, True):
            for fault in ("validity_throw", "validity_false", "handle_throw", "zero", "duplicate"):
                with self.subTest(skin=skin, fault=fault):
                    module, scene, contexts, options = self.engine(skin=skin)
                    fixture = Path(self.folder.name) / (uuid.uuid4().hex + ".fbx")
                    fixture.write_bytes(b"fake native-import input")
                    options.fbx_path = str(fixture)
                    ctx = module.TransferContext(options, module.TransferLog())
                    self.set_native_identity_fault(scene, fault)
                    configured = []
                    with patch.multiple(
                        module, command_panel_mode_name=lambda: "create",
                        release_modifier_panel_reference=lambda: True,
                        configure_fbx_import=lambda *args: configured.append(True),
                    ):
                        with self.assertRaises(RuntimeError):
                            if skin:
                                self.actual_importers[module](ctx)
                            else:
                                self.actual_importers[module](ctx, False)
                    self.assertIsNone(ctx.pre_handles)
                    self.assertEqual(configured, [])
                    module.cleanup_imported_nodes(ctx)
                    self.assert_original_scene(scene)
                    self.assertEqual(scene.deleted, [])

    def test_initial_selection_snapshot_cannot_silently_omit_an_original_node(self):
        for skin in (False, True):
            for fault in ("validity_throw", "validity_false", "handle_throw", "zero", "duplicate"):
                with self.subTest(skin=skin, fault=fault):
                    module, scene, contexts, options = self.engine(skin=skin)
                    module.LAST_RUN_OK = True
                    self.set_native_identity_fault(scene, fault)
                    with self.assertRaises(RuntimeError):
                        module.run_transfer(options)
                    self.assertFalse(module.LAST_RUN_OK)
                    self.assertEqual(contexts, [])
                    self.assert_original_scene(scene)
                    self.assertEqual([n.handle for n in scene.selection], [2, 1])
                    self.assertEqual(scene.deleted, [])

    def test_skin_redraw_enter_exit_failure_obeys_same_recovery_transaction(self):
        for backup in (True, False):
            for fault in ("redraw_enter", "redraw_exit"):
                with self.subTest(backup=backup, fault=fault):
                    module, scene, contexts, options = self.engine(
                        skin=True, backup=backup, fault=fault
                    )
                    text = module.run_transfer(options)
                    self.assert_failure(module, text)
                    if backup or fault == "redraw_enter":
                        self.assert_original_scene(scene)
                        self.assertEqual({n.handle for n in scene.selection}, {1, 2})
                    else:
                        self.assertEqual(set(scene.nodes), {2, 3})
                        self.assertEqual(scene.nodes[3].name, "Body")
                        self.assertEqual({n.handle for n in scene.selection}, {2, 3})
                        self.assertFalse(any(3 in deleted for deleted in scene.deleted))
                        self.assertIn("不能将本次故障视为完整回滚", text)

    def test_skin_wrapper_initialization_cannot_leave_previous_success(self):
        module, scene, contexts, options = self.engine(skin=True)
        module.LAST_RUN_OK = True
        module.LAST_RUN_REPORT_PATH = "old-success-report"
        module.LAST_RUN_SUMMARY = "old-success-summary"
        with patch.object(module, "ensure_runtime", side_effect=RuntimeError("初始化故障")):
            with self.assertRaisesRegex(RuntimeError, "初始化故障"):
                module.run_transfer(options)
        self.assertFalse(module.LAST_RUN_OK)
        self.assertEqual(module.LAST_RUN_REPORT_PATH, "")
        self.assertIn("运行环境初始化失败", module.LAST_RUN_SUMMARY)
        self.assertEqual(contexts, [])
        self.assert_original_scene(scene)

    def test_selection_readback_cannot_filter_an_extra_invalid_native_node(self):
        for skin in (False, True):
            with self.subTest(skin=skin):
                module, scene, contexts, options = self.engine(skin=skin)
                native_select = scene.select

                def select_with_invalid_extra(nodes):
                    native_select(nodes)
                    scene.selection.append(Node(99, "InvalidSelectionWrapper", False))

                with patch.object(scene, "select", select_with_invalid_extra):
                    with self.assertRaises(RuntimeError):
                        if skin:
                            module._restore_selection_after_replace([(1, "Body")])
                        else:
                            module.restore_selection_by_handle([1])


if __name__ == "__main__":
    unittest.main()
