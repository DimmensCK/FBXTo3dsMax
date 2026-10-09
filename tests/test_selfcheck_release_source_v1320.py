# -*- coding: utf-8 -*-
"""发布自检对 Mode2 生命周期/强制 GC 退化的静态门禁。"""

from __future__ import annotations

import importlib.util
import inspect
import pathlib
import sys
import types
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SELFCHECK_PATH = ROOT / "contents" / "f2m_selfcheck.py"
TOPOLOGY_PATH = ROOT / "contents" / "f2m_topology_transfer.py"
SKIN_PATH = ROOT / "contents" / "f2m_skin_replace.py"


def load_selfcheck():
    name = "_f2m_selfcheck_release_source_v1320"
    spec = importlib.util.spec_from_file_location(name, str(SELFCHECK_PATH))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {SELFCHECK_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class SelfCheckReleaseSourceV1320Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.selfcheck = load_selfcheck()
        cls.topology_source = TOPOLOGY_PATH.read_text(encoding="utf-8-sig")
        cls.skin_source = SKIN_PATH.read_text(encoding="utf-8-sig")

    def test_current_transfer_sources_pass_release_lifecycle_validation(
        self,
    ) -> None:
        self.selfcheck._validate_transfer_release_source(
            self.topology_source,
            self.skin_source,
        )

    def test_release_validation_rejects_forced_gc_entry_points(self) -> None:
        forced_gc_samples = (
            "gc.collect()",
            'rt.execute("gc light:true")',
            'rt.execute("gc()")',
            "collect_wrappers_before_native_destruction()",
        )
        for sample in forced_gc_samples:
            with self.subTest(sample=sample):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "主动强制垃圾回收",
                ):
                    self.selfcheck._validate_transfer_release_source(
                        self.topology_source,
                        self.skin_source + "\n" + sample,
                    )

    def test_release_validation_rejects_direct_node_wrapper_delete(
        self,
    ) -> None:
        safe_delete = "delete (getAnimByHandle handleValue)"
        self.assertIn(safe_delete, self.skin_source)
        unsafe_source = self.skin_source.replace(
            safe_delete,
            "delete nodeValue",
            1,
        )
        with self.assertRaisesRegex(RuntimeError, "待删 wrapper"):
            self.selfcheck._validate_transfer_release_source(
                self.topology_source,
                unsafe_source,
            )

    def test_release_validation_requires_both_fresh_skin_failure_cleanups(
        self,
    ) -> None:
        safe_cleanup = (
            "F2M_Helper.removeModifierByAnimHandle targetNode freshHandle"
        )
        self.assertEqual(self.skin_source.count(safe_cleanup), 2)
        unsafe_source = self.skin_source.replace(
            safe_cleanup,
            "deleteModifier targetNode freshSkin",
            1,
        )
        with self.assertRaisesRegex(RuntimeError, "待删 wrapper"):
            self.selfcheck._validate_transfer_release_source(
                self.topology_source,
                unsafe_source,
            )

    def test_isolated_scene_reset_does_not_dismantle_residual_normals(self) -> None:
        reset_source = inspect.getsource(self.selfcheck._reset_max_file_safely)
        self.assertNotIn("deleteNodesByHandles", reset_source)
        self.assertNotIn("deleteModifier", reset_source)
        self.assertLess(
            reset_source.index("rt.clearSelection()"),
            reset_source.index("rt.resetMaxFile"),
        )

        events: list[str] = []
        scene_nodes = [object()]

        def reset_scene(_mode: str) -> None:
            events.append("reset")
            scene_nodes.clear()

        fake_runtime = types.SimpleNamespace(
            Name=lambda value: str(value),
            clearSelection=lambda: events.append("clear-selection"),
            resetMaxFile=reset_scene,
            objects=scene_nodes,
        )
        with mock.patch.object(self.selfcheck, "rt", fake_runtime):
            self.selfcheck._reset_max_file_safely()
        self.assertEqual(events, ["clear-selection", "reset"])


if __name__ == "__main__":
    unittest.main()
