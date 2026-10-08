# -*- coding: utf-8 -*-
"""拓扑引擎异常链不得跨原生清理阶段保留 pymxs frame。"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "f2m_topology_transfer.py"


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, str(MODULE_PATH))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def function_source(source: str, name: str) -> str:
    marker = f"def {name}("
    start = source.find(marker)
    if start < 0:
        raise AssertionError(f"缺少函数：{name}")
    end = source.find("\ndef ", start + len(marker))
    return source[start:] if end < 0 else source[start:end]


class TopologyExceptionReleaseV1320Tests(unittest.TestCase):
    def test_release_recursively_clears_traceback_cause_and_context(self):
        module = load_module("_f2m_test_topology_exception_release")

        def fail_inner():
            retained_wrapper = object()
            del retained_wrapper
            raise ValueError("内层")

        try:
            try:
                fail_inner()
            except ValueError as cause:
                raise RuntimeError("外层") from cause
        except RuntimeError as outer:
            cause = outer.__cause__
            self.assertIsNotNone(outer.__traceback__)
            self.assertIsNotNone(cause)
            self.assertEqual(
                module._exception_text_and_release(outer),
                "外层",
            )
            self.assertIsNone(outer.__traceback__)
            self.assertIsNone(outer.__cause__)
            self.assertIsNone(outer.__context__)
            self.assertIsNone(cause.__traceback__)
            self.assertIsNone(cause.__cause__)
            self.assertIsNone(cause.__context__)

    def test_import_and_recovery_convert_exceptions_before_cleanup(self):
        source = MODULE_PATH.read_text(encoding="utf-8-sig")
        importer = function_source(source, "_import_fbx_once")
        self.assertNotIn("Optional[BaseException]", importer)
        self.assertGreaterEqual(
            importer.count("_exception_text_and_release(exc)"),
            3,
        )
        self.assertIn('import_error = ""', importer)
        self.assertIn('tracking_error = ""', importer)
        self.assertIn('restore_error = ""', importer)
        self.assertIn('raise RuntimeError("；".join(parts)) from None', importer)

        runner = function_source(source, "run_transfer")
        outer_release = runner.index("_exception_text_and_release(exc)")
        cleanup = runner.index("cleanup_imported_nodes(ctx)", outer_release)
        cleanup_release = runner.index(
            "_exception_text_and_release(cleanup_exc)",
            cleanup,
        )
        restore = runner.index("restore_scene_names(ctx)", cleanup_release)
        restore_release = runner.index(
            "_exception_text_and_release(restore_exc)",
            restore,
        )
        context_release = runner.index(
            "_release_context_node_references(ctx)",
            restore_release,
        )
        self.assertLess(outer_release, cleanup)
        self.assertLess(cleanup, cleanup_release)
        self.assertLess(cleanup_release, restore)
        self.assertLess(restore, restore_release)
        self.assertLess(restore_release, context_release)


if __name__ == "__main__":
    unittest.main()
