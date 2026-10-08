"""模式二 Skin 权重写入策略的纯 Python 回归。"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name: str):
    path = ROOT / "f2m_skin_replace.py"
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _PerVertexSkinOps:
    def __init__(self) -> None:
        self.calls = []
        self.dq_override_calls = []
        self.set_bone_calls = []

    def enableDQOverrideWeighting(self, *args, **kwargs):
        if kwargs:
            raise AssertionError("DQ Override 不应探测关键字参数")
        self.dq_override_calls.append(args)

    def ReplaceVertexWeights(self, *args, **kwargs):
        if kwargs:
            raise AssertionError("逐顶点权威路径不应在循环中探测 node: 关键字")
        self.calls.append(args)

    def SetBoneWeights(self, *args, **kwargs):
        self.set_bone_calls.append((args, kwargs))
        raise AssertionError("生产路径不得调用 SetBoneWeights")



class SkinAuthoritativeWeightTests(unittest.TestCase):
    def test_production_path_writes_each_authoritative_vertex_once(self) -> None:
        module = load_module("_f2m_test_skin_authoritative_rows")
        skin_ops = _PerVertexSkinOps()
        module.rt = types.SimpleNamespace(skinOps=skin_ops)
        rows = (((7, 1.0),), ((7, 0.25), (11, 0.75)))
        states = (
            module.SkinVertexState(False, 0.0),
            module.SkinVertexState(False, 0.0),
        )
        modifier_state = module.SkinModifierState(False)

        with mock.patch.object(module, "activate_modifier", return_value=True), mock.patch.object(
            module,
            "_set_skin_modifier_state",
        ), mock.patch.object(
            module,
            "_prepare_vertex_unnormalized_states",
        ), mock.patch.object(
            module,
            "_write_dq_and_verify_weight_rows",
        ) as verify:
            applied = module.apply_weight_rows(
                "候选Skin",
                "候选节点",
                rows,
                states,
                modifier_state,
            )

        self.assertEqual(applied, 2)
        self.assertEqual(
            skin_ops.calls,
            [
                ("候选Skin", 1, [7], [1.0]),
                ("候选Skin", 2, [7, 11], [0.25, 0.75]),
            ],
        )
        self.assertEqual(skin_ops.set_bone_calls, [])
        self.assertEqual(skin_ops.dq_override_calls, [("候选Skin", False)])
        verify.assert_called_once()
        self.assertEqual(module.LAST_WEIGHT_WRITE_METHOD, "逐顶点权威写入")
        self.assertEqual(module.LAST_WEIGHT_BULK_FALLBACK_REASON, "")

    def test_per_vertex_writer_uses_one_max2023_signature_without_probe_errors(
        self,
    ) -> None:
        module = load_module("_f2m_test_skin_per_vertex_signature")
        skin_ops = _PerVertexSkinOps()
        module.rt = types.SimpleNamespace(skinOps=skin_ops)

        applied = module._apply_weight_rows_per_vertex(
            "候选Skin",
            "候选节点",
            (
                ((7, 1.0),),
                ((7, 0.25), (11, 0.75)),
            ),
        )

        self.assertEqual(applied, 2)
        self.assertEqual(
            skin_ops.calls,
            [
                ("候选Skin", 1, [7], [1.0]),
                ("候选Skin", 2, [7, 11], [0.25, 0.75]),
            ],
        )
        self.assertEqual(skin_ops.set_bone_calls, [])

    def test_empty_authoritative_row_fails_before_native_write(self) -> None:
        module = load_module("_f2m_test_skin_empty_authoritative_row")
        skin_ops = _PerVertexSkinOps()
        module.rt = types.SimpleNamespace(skinOps=skin_ops)

        with self.assertRaisesRegex(RuntimeError, "映射权重为空"):
            module._apply_weight_rows_per_vertex(
                "候选Skin",
                "候选节点",
                ((),),
            )

        self.assertEqual(skin_ops.calls, [])
        self.assertEqual(skin_ops.set_bone_calls, [])


if __name__ == "__main__":
    unittest.main()
