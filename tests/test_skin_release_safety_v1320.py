# -*- coding: utf-8 -*-
"""模式二 v1.4.25 发布安全修复的纯 Python 专项回归。"""

from __future__ import annotations

import importlib.util
import inspect
import pathlib
import sys
import types
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "contents" / "f2m_skin_replace.py"


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, str(MODULE_PATH))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _Log:
    def __init__(self) -> None:
        self.lines = []

    def add(self, text="") -> None:
        self.lines.append(str(text))


class _Node:
    def __init__(self, handle: int, name: str, hidden: bool = False) -> None:
        self.handle = int(handle)
        self._name = str(name)
        self._hidden = bool(hidden)
        self.deleted = False
        self.deleted_name_reads = 0

    @property
    def name(self):
        if self.deleted:
            self.deleted_name_reads += 1
            raise RuntimeError("测试禁止解引用已删除的 MXSWrapper")
        return self._name

    @name.setter
    def name(self, value):
        if self.deleted:
            self.deleted_name_reads += 1
            raise RuntimeError("测试禁止写入已删除的 MXSWrapper")
        self._name = str(value)

    @property
    def isHidden(self):
        if self.deleted:
            raise RuntimeError("测试禁止解引用已删除的 MXSWrapper")
        return self._hidden

    @isHidden.setter
    def isHidden(self, value):
        if self.deleted:
            raise RuntimeError("测试禁止写入已删除的 MXSWrapper")
        self._hidden = bool(value)

    @property
    def isNodeHidden(self):
        return self.isHidden

    @isNodeHidden.setter
    def isNodeHidden(self, value):
        self.isHidden = value


class _DeleteHelper:
    def __init__(self, runtime) -> None:
        self.runtime = runtime

    def deleteNodesByHandles(self, handles):
        nodes = []
        for handle in handles:
            node = self.runtime.getAnimByHandle(handle)
            if node is not None and self.runtime.isValidNode(node):
                nodes.append(node)
        try:
            if nodes:
                self.runtime.delete(nodes)
        except Exception:
            pass
        return [
            int(handle)
            for handle in handles
            if self.runtime.getAnimByHandle(handle) is not None
        ]

    def setNodeHiddenFlag(self, node, hidden_flag):
        node.isNodeHidden = int(hidden_flag) != 0
        return node.isNodeHidden == (int(hidden_flag) != 0)


class _Runtime:
    def __init__(self, nodes=(), fail_first_batch: bool = False) -> None:
        self.objects = list(nodes)
        self.delete_calls = []
        self.fail_first_batch = bool(fail_first_batch)
        self.F2M_Helper = _DeleteHelper(self)

    @staticmethod
    def Name(value):
        return str(value)

    def isValidNode(self, node):
        return (
            isinstance(node, _Node)
            and not node.deleted
            and node in self.objects
        )

    def getHandleByAnim(self, node):
        if not self.isValidNode(node):
            raise RuntimeError("无效节点不能读取句柄")
        return node.handle

    def getAnimByHandle(self, handle):
        for node in self.objects:
            if not node.deleted and node.handle == int(handle):
                return node
        return None

    def delete(self, value):
        is_batch = isinstance(value, list)
        nodes = list(value) if is_batch else [value]
        self.delete_calls.append(tuple(node.handle for node in nodes))
        if is_batch and self.fail_first_batch:
            self.fail_first_batch = False
            raise RuntimeError("模拟旧版 pymxs 拒绝 Python list")
        for node in nodes:
            if self.isValidNode(node):
                self.objects.remove(node)
                node.deleted = True


class _ImporterHelper:
    def __init__(self) -> None:
        self.params = {
            "Mode": "merge",
            "Animation": True,
            "Skin": False,
            "SmoothingGroups": True,
        }

    def fbxImporterGet(self, name):
        return self.params[str(name)]

    def fbxImporterSet(self, name, value):
        self.params[str(name)] = value
        return value


class SkinReleaseSafetyV1320Tests(unittest.TestCase):
    def test_mode2_disables_smoothing_groups_and_restores_original_preset(self):
        module = load_module("_f2m_test_skin_release_import_options")
        helper = _ImporterHelper()
        runtime = types.SimpleNamespace(
            F2M_Helper=helper,
            Name=lambda value: str(value),
            execute=lambda _code: True,
        )
        module.rt = runtime
        ctx = types.SimpleNamespace(log=_Log(), safety_errors=[])

        snapshot = module.configure_fbx_import(ctx)

        self.assertIs(helper.params["SmoothingGroups"], False)
        self.assertIn("优先保留 FBX 显式/自定义法线", "\n".join(ctx.log.lines))
        module._restore_fbx_importer(ctx, snapshot)
        self.assertEqual(
            helper.params,
            {
                "Mode": "merge",
                "Animation": True,
                "Skin": False,
                "SmoothingGroups": True,
            },
        )

    def test_tracking_failure_cannot_skip_importer_restore(self):
        module = load_module("_f2m_test_skin_release_nested_restore")
        module.rt = types.SimpleNamespace(execute=lambda _code: True)
        ctx = types.SimpleNamespace(
            options=types.SimpleNamespace(fbx_path="fixture.fbx"),
            imported_nodes=[],
            log=_Log(),
        )
        snapshot = {"Mode": "merge"}

        with (
            mock.patch.object(module.os.path, "exists", return_value=True),
            mock.patch.object(module, "all_scene_nodes", return_value=[]),
            mock.patch.object(
                module,
                "configure_fbx_import",
                return_value=snapshot,
            ),
            mock.patch.object(
                module,
                "command_panel_mode_name",
                return_value="modify",
            ),
            mock.patch.object(
                module,
                "release_modifier_panel_reference",
                return_value=True,
            ),
            mock.patch.object(
                module,
                "_new_nodes_since",
                side_effect=RuntimeError("模拟节点追踪异常"),
            ),
            mock.patch.object(module, "_restore_fbx_importer") as restore,
        ):
            with self.assertRaisesRegex(RuntimeError, "跟踪临时导入节点失败"):
                module.import_fbx(ctx)

        restore.assert_called_once_with(ctx, snapshot)

    def test_native_validity_check_never_dereferences_deleted_wrapper(self):
        module = load_module("_f2m_test_skin_release_valid_node")
        deleted = _Node(10, "已删除")
        deleted.deleted = True
        runtime = _Runtime()
        module.rt = runtime

        self.assertFalse(module.is_valid_node(deleted))
        self.assertEqual(deleted.deleted_name_reads, 0)

        runtime.isValidNode = mock.Mock(
            side_effect=RuntimeError("模拟原生谓词异常")
        )
        self.assertFalse(module.is_valid_node(deleted))
        self.assertEqual(deleted.deleted_name_reads, 0)

    def test_cleanup_uses_one_bulk_delete_and_releases_deleted_wrappers(self):
        module = load_module("_f2m_test_skin_release_bulk_cleanup")
        original = _Node(1, "场景原节点")
        temp_a = _Node(10, "临时A")
        temp_b = _Node(11, "临时B")
        kept = _Node(20, "正式替换候选")
        runtime = _Runtime((original, temp_a, temp_b, kept))
        module.rt = runtime
        ctx = types.SimpleNamespace(
            imported_nodes=[temp_a, temp_b, kept],
            keep_imported_nodes={kept.handle},
            pre_handles={original.handle},
            options=types.SimpleNamespace(keep_imported=False),
            safety_errors=[],
        )

        module.cleanup_imported_nodes(ctx)

        self.assertEqual(runtime.delete_calls, [(10, 11)])
        self.assertEqual(ctx.imported_nodes, [kept])
        self.assertNotIn(temp_a, runtime.objects)
        self.assertNotIn(temp_b, runtime.objects)
        self.assertEqual(temp_a.deleted_name_reads, 0)
        self.assertEqual(temp_b.deleted_name_reads, 0)

    def test_bulk_delete_failure_rescans_before_single_node_fallback(self):
        module = load_module("_f2m_test_skin_release_bulk_fallback")
        temp_a = _Node(30, "临时A")
        temp_b = _Node(31, "临时B")
        runtime = _Runtime((temp_a, temp_b), fail_first_batch=True)
        module.rt = runtime
        remaining = module._delete_node_handles_strict(
            {30, 31},
            {30: "临时A", 31: "临时B"},
            label="临时 FBX 节点",
        )

        self.assertEqual(remaining, {})
        self.assertEqual(runtime.delete_calls, [(30, 31), (30,), (31,)])
        self.assertEqual(runtime.objects, [])
        self.assertEqual(temp_a.deleted_name_reads, 0)
        self.assertEqual(temp_b.deleted_name_reads, 0)

    def test_batch_rollback_deletes_candidate_by_handle_without_stale_probe(self):
        module = load_module("_f2m_test_skin_release_rollback")
        candidate = _Node(40, "导入候选")
        old_target = _Node(41, "旧网格备份", hidden=True)
        runtime = _Runtime((candidate, old_target))
        module.rt = runtime
        target_record = module.SceneRecord(
            handle=old_target.handle,
            original_name="身体",
            temp_name="__F2M_SCENE__身体",
            node=old_target,
            renamed=True,
            skip_restore=True,
        )
        report = module.ObjectReport(name="身体", status="完成：整模替换")
        entry = module.CommittedReplacement(
            target_record=target_record,
            candidate_handle=candidate.handle,
            candidate_name=candidate.name,
            old_hidden=False,
            report=report,
        )
        ctx = types.SimpleNamespace(
            committed_replacements=[entry],
            imported_nodes=[candidate],
            keep_imported_nodes={candidate.handle},
            replacement_nodes={candidate.handle},
            import_prefix="__F2M_SRC__",
            safety_errors=[],
            log=_Log(),
        )

        strict_delete = module._delete_node_handles_strict

        def guarded_delete(*args, **kwargs):
            self.assertIsNone(target_record.node)
            self.assertEqual(ctx.imported_nodes, [])
            return strict_delete(*args, **kwargs)

        with mock.patch.object(
            module,
            "_delete_node_handles_strict",
            side_effect=guarded_delete,
        ):
            failures = module.rollback_committed_replacements(
                ctx,
                "模拟后续对象失败",
            )

        self.assertEqual(failures, [])
        self.assertEqual(runtime.delete_calls, [(candidate.handle,)])
        self.assertEqual(candidate.deleted_name_reads, 0)
        self.assertIs(target_record.node, old_target)
        self.assertEqual(old_target.name, target_record.temp_name)
        self.assertFalse(old_target.isHidden)
        self.assertEqual(report.status, "失败：批次已回滚")

    def test_delete_commit_clears_old_target_record_before_handle_delete(self):
        module = load_module("_f2m_test_skin_release_delete_commit")
        candidate = _Node(60, "导入候选")
        old_target = _Node(61, "__F2M_SCENE__身体")
        runtime = _Runtime((candidate, old_target))
        module.rt = runtime
        target_record = module.SceneRecord(
            handle=old_target.handle,
            original_name="身体",
            temp_name=old_target.name,
            node=old_target,
            renamed=True,
        )
        ctx = types.SimpleNamespace(
            options=types.SimpleNamespace(backup_old_mesh=False),
            keep_imported_nodes=set(),
            replacement_nodes=set(),
        )
        copied_skin = object()

        def guarded_delete(handles, names_by_handle=None, label="节点"):
            self.assertEqual(set(handles), {old_target.handle})
            self.assertIsNone(target_record.node)
            runtime.delete(old_target)
            return {}

        with (
            mock.patch.object(module, "verify_weight_rows"),
            mock.patch.object(module, "verify_scene_bound_skin"),
            mock.patch.object(module, "verify_candidate_authority_snapshot"),
            mock.patch.object(module, "find_skin", return_value=copied_skin),
            mock.patch.object(
                module,
                "_delete_node_handles_strict",
                side_effect=guarded_delete,
            ),
        ):
            module.commit_replacement(
                ctx,
                candidate,
                target_record,
                copied_skin,
                object(),
                [],
                [],
                object(),
                [],
                [],
                module.ObjectReport(name="身体", status="处理中"),
            )

        self.assertTrue(old_target.deleted)
        self.assertEqual(old_target.deleted_name_reads, 0)
        self.assertIsNone(target_record.node)
        self.assertTrue(target_record.skip_restore)
        self.assertEqual(ctx.replacement_nodes, {candidate.handle})

    def test_commit_and_rollback_source_enforce_handle_only_delete_boundary(self):
        module = load_module("_f2m_test_skin_release_static_boundaries")

        fields = module.CommittedReplacement.__dataclass_fields__
        self.assertNotIn("candidate", fields)
        self.assertIn("candidate_handle", fields)
        self.assertIn("candidate_name", fields)

        commit_source = inspect.getsource(module.commit_replacement)
        commit_delete = commit_source.index("_delete_node_handles_strict")
        self.assertLess(
            commit_source.index("target_record.node = None"),
            commit_delete,
        )
        self.assertLess(commit_source.index("old_target = None"), commit_delete)
        self.assertNotIn(
            "is_valid_node(old_target)",
            commit_source[commit_delete:],
        )
        self.assertIn("node_by_handle(target_handle)", commit_source[commit_delete:])

        rollback_source = inspect.getsource(
            module.rollback_committed_replacements
        )
        rollback_delete = rollback_source.index("_delete_node_handles_strict")
        self.assertLess(
            rollback_source.index("entry.target_record.node = None"),
            rollback_delete,
        )
        self.assertLess(
            rollback_source.index("_forget_imported_node_handle"),
            rollback_delete,
        )
        self.assertNotIn("entry.candidate =", rollback_source)

    def test_isolated_reset_detaches_panel_without_forced_gc(self):
        module = load_module("_f2m_test_skin_release_reset_lifetime")
        reset_source = inspect.getsource(module._reset_max_file_safely)
        self.assertNotIn("gc.collect", reset_source)
        self.assertNotIn("gc light:true", reset_source)
        self.assertLess(
            reset_source.index("release_modifier_panel_reference()"),
            reset_source.index("rt.resetMaxFile"),
        )

        events = []
        module.rt = types.SimpleNamespace(
            Name=lambda value: str(value),
            clearSelection=lambda: events.append("clear-selection"),
            resetMaxFile=lambda _mode: events.append("reset"),
        )
        with mock.patch.object(
            module,
            "release_modifier_panel_reference",
            side_effect=lambda: events.append("detach-panel") or True,
        ):
            module._reset_max_file_safely()
        self.assertEqual(
            events,
            ["detach-panel", "clear-selection", "reset"],
        )

        events.clear()
        with mock.patch.object(
            module,
            "release_modifier_panel_reference",
            return_value=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "解除 Modify 面板"):
                module._reset_max_file_safely()
        self.assertEqual(events, [])

    def test_context_release_drops_every_pymxs_node_reference(self):
        module = load_module("_f2m_test_skin_release_context_refs")
        imported = _Node(50, "导入节点")
        original = _Node(51, "原节点")
        candidate = _Node(52, "候选节点")
        record = module.SceneRecord(
            handle=original.handle,
            original_name="身体",
            temp_name="__F2M_SCENE__身体",
            node=original,
        )
        entry = module.CommittedReplacement(
            target_record=record,
            candidate_handle=candidate.handle,
            candidate_name=candidate.name,
            old_hidden=False,
            report=module.ObjectReport(name="身体", status="完成"),
        )
        ctx = types.SimpleNamespace(
            imported_nodes=[imported],
            committed_replacements=[entry],
            scene_records=[record],
            scene_by_original={"身体": [record]},
            keep_imported_nodes={candidate.handle},
            replacement_nodes={candidate.handle},
            imported_bone_names={99: "骨骼"},
        )

        module._release_context_node_references(ctx)

        self.assertEqual(ctx.imported_nodes, [])
        self.assertEqual(ctx.committed_replacements, [])
        self.assertEqual(ctx.scene_records, [])
        self.assertEqual(ctx.scene_by_original, {})
        self.assertEqual(ctx.keep_imported_nodes, set())
        self.assertEqual(ctx.replacement_nodes, set())
        self.assertEqual(ctx.imported_bone_names, {})
        self.assertIsNone(record.node)
        self.assertNotIn("candidate", entry.__dataclass_fields__)


if __name__ == "__main__":
    unittest.main()
