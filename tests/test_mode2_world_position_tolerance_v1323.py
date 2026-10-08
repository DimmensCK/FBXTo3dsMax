# -*- coding: utf-8 -*-
"""Mode-2 scale-aware world-position tolerance regressions for v1.3.24."""

from __future__ import annotations

import ast
import importlib.util
import math
import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / "f2m_skin_replace.py"

# Numeric float32 round-trip regression at a large world-space coordinate.
# Only the boundary values are retained; no scene or private object names.
LARGE_COORDINATE_BEFORE = (
    -41.95558547973633,
    -68.1465072631836,
    1784.061279296875,
)
LARGE_COORDINATE_AFTER = (
    -41.95558547973633,
    -68.14637756347656,
    1784.0625,
)


def load_engine():
    module_name = f"_f2m_mode2_tolerance_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, ENGINE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load production engine: {ENGINE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return module


class Mode2WorldPositionToleranceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = load_engine()
        cls.source = ENGINE_PATH.read_text(encoding="utf-8-sig")
        cls.tree = ast.parse(
            cls.source,
            filename=str(ENGINE_PATH),
            feature_version=(3, 9),
        )

    def test_large_coordinate_float32_roundtrip_is_accepted(self) -> None:
        delta, tolerance, coordinate_scale = (
            self.engine._mode2_world_point_metrics(
                LARGE_COORDINATE_BEFORE,
                LARGE_COORDINATE_AFTER,
            )
        )

        self.assertAlmostEqual(delta, 0.0012275740846844061, places=15)
        self.assertAlmostEqual(coordinate_scale, 1784.0625, places=10)
        self.assertAlmostEqual(tolerance, 0.003570125, places=12)
        self.assertLessEqual(delta, tolerance)

    def test_small_coordinates_keep_the_legacy_absolute_floor(self) -> None:
        expected = (0.0, 0.0, 0.0)
        actual = (0.0009, 0.0, 0.0)

        delta, tolerance, coordinate_scale = (
            self.engine._mode2_world_point_metrics(expected, actual)
        )

        self.assertEqual(
            tolerance,
            self.engine.MODE2_WORLD_POSITION_ABSOLUTE_FLOOR,
        )
        self.assertEqual(tolerance, 0.001)
        self.assertEqual(coordinate_scale, 1.0)
        self.assertLessEqual(delta, tolerance)

    def test_large_coordinate_real_point_change_still_exceeds_tolerance(self) -> None:
        expected = (0.0, 0.0, 1784.0)
        actual = (0.0, 0.0, 1784.01)

        delta, tolerance, coordinate_scale = (
            self.engine._mode2_world_point_metrics(expected, actual)
        )

        self.assertAlmostEqual(coordinate_scale, 1784.01, places=10)
        self.assertGreater(delta, tolerance)
        self.assertAlmostEqual(delta, 0.01, places=10)
        self.assertLess(tolerance, 0.004)

    def test_invalid_coordinate_lengths_are_rejected(self) -> None:
        invalid_pairs = (
            ((), (0.0, 0.0, 0.0)),
            ((0.0, 0.0), (0.0, 0.0, 0.0)),
            ((0.0, 0.0, 0.0), (0.0, 0.0)),
            ((0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
            ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0)),
        )
        for expected, actual in invalid_pairs:
            with self.subTest(expected=expected, actual=actual):
                with self.assertRaises(ValueError):
                    self.engine.mode2_world_position_tolerance(
                        expected,
                        actual,
                    )

    def test_nan_and_infinity_are_rejected(self) -> None:
        invalid_values = (math.nan, math.inf, -math.inf)
        for invalid in invalid_values:
            for expected, actual in (
                ((invalid, 0.0, 0.0), (0.0, 0.0, 0.0)),
                ((0.0, 0.0, 0.0), (0.0, invalid, 0.0)),
            ):
                with self.subTest(invalid=invalid, expected=expected, actual=actual):
                    with self.assertRaises(ValueError):
                        self.engine.mode2_world_position_tolerance(
                            expected,
                            actual,
                        )

    def test_vertex_and_bbox_checks_share_the_same_metrics_helper(self) -> None:
        verify_node = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "verify_candidate_authority_snapshot"
        )
        metric_calls = [
            node
            for node in ast.walk(verify_node)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_mode2_world_point_metrics"
        ]
        self.assertEqual(
            len(metric_calls),
            2,
            "Per-vertex and bbox authority checks must each use the shared helper.",
        )

        verify_source = ast.get_source_segment(self.source, verify_node) or ""
        self.assertIn("expected.evaluated_world_positions", verify_source)
        self.assertIn("actual.evaluated_world_positions", verify_source)
        self.assertIn("expected.evaluated_world_bbox[:3]", verify_source)
        self.assertIn("actual.evaluated_world_bbox[:3]", verify_source)
        self.assertIn("expected.evaluated_world_bbox[3:]", verify_source)
        self.assertIn("actual.evaluated_world_bbox[3:]", verify_source)

    def test_legacy_fixed_tolerance_constant_is_not_used(self) -> None:
        self.assertNotIn("MODE2_WORLD_POSITION_TOLERANCE", self.source)

        metrics_node = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_mode2_world_point_metrics"
        )
        tolerance_calls = [
            node
            for node in ast.walk(metrics_node)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "mode2_world_position_tolerance"
        ]
        self.assertEqual(len(tolerance_calls), 1)

    def test_handled_formal_failure_shows_chinese_summary_and_report(self) -> None:
        calls = []

        class FakeRuntime:
            @staticmethod
            def messageBox(body, **kwargs):
                calls.append((body, kwargs))

        report = self.engine.ObjectReport(
            name="ExampleMesh",
            status="失败：替换网格并保留蒙皮",
        )
        report.add("整模替换：候选权威校验失败，旧模型未提交变更。")
        ctx = SimpleNamespace(
            options=SimpleNamespace(dry_run=False),
            safety_errors=[],
            reports=[report],
            log=SimpleNamespace(lines=[]),
        )
        original_rt = self.engine.rt
        self.engine.rt = FakeRuntime()
        try:
            self.engine.show_execution_failure(
                ctx,
                r"C:\Reports\example-mode2.txt",
            )
        finally:
            self.engine.rt = original_rt

        self.assertEqual(len(calls), 1)
        body, kwargs = calls[0]
        self.assertIn("传递未完成", body)
        self.assertIn("ExampleMesh", body)
        self.assertIn(r"C:\Reports\example-mode2.txt", body)
        self.assertEqual(kwargs["title"], "FBX 到 3ds Max 传递未完成")
        self.assertTrue(kwargs["beep"])

    def test_formal_success_does_not_show_failure_popup(self) -> None:
        calls = []

        class FakeRuntime:
            @staticmethod
            def messageBox(body, **kwargs):
                calls.append((body, kwargs))

        ctx = SimpleNamespace(
            options=SimpleNamespace(dry_run=False),
            safety_errors=[],
            reports=[
                self.engine.ObjectReport(
                    name="ExampleMesh",
                    status="完成：替换网格并保留蒙皮",
                )
            ],
            log=SimpleNamespace(lines=[]),
        )
        original_rt = self.engine.rt
        self.engine.rt = FakeRuntime()
        try:
            self.engine.show_execution_failure(ctx, r"C:\Reports\success.txt")
        finally:
            self.engine.rt = original_rt

        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
