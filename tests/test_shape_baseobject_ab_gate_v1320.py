from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "contents" / "f2m_topology_transfer.py"
SKIN_ENGINE = ROOT / "contents" / "f2m_skin_replace.py"
RUNNER = ROOT / "tests" / "max_user_reported_regressions_v1321.py"
RUNNER_1322 = ROOT / "tests" / "max_user_reported_regressions_v1322.py"
TRS_RUNNER = ROOT / "tests" / "max_mode1_matching_trs_v1322.py"


class UserReportedWorldSpaceGateSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = ENGINE.read_text(encoding="utf-8-sig")
        cls.skin_engine = SKIN_ENGINE.read_text(encoding="utf-8-sig")
        cls.runner = RUNNER.read_text(encoding="utf-8-sig")
        cls.runner_1322 = RUNNER_1322.read_text(encoding="utf-8-sig")
        cls.trs_runner = TRS_RUNNER.read_text(encoding="utf-8-sig")
        cls.shape_helper = cls.engine[
            cls.engine.index("fn copyBaseVertexPositions src dst") :
            cls.engine.index("fn captureBaseVertexPositions n")
        ]

    def test_runner_is_valid_python(self) -> None:
        ast.parse(self.runner, filename=str(RUNNER), feature_version=(3, 9))
        ast.parse(
            self.runner_1322,
            filename=str(RUNNER_1322),
            feature_version=(3, 9),
        )
        ast.parse(
            self.trs_runner,
            filename=str(TRS_RUNNER),
            feature_version=(3, 9),
        )
        for source in (self.runner, self.runner_1322, self.trs_runner):
            with self.subTest(source=source[:40]):
                self.assertIn('EXPECTED_VERSION = "1.4.26"', source)
                self.assertIn('"gate": {', source)
                self.assertIn('"sha256": sha256_file(GATE_PATH)', source)
                self.assertIn('"run_id":', source)
                self.assertIn('"expected_version": EXPECTED_VERSION', source)

    def test_success_path_uses_node_coordinate_domain(self) -> None:
        self.assertIn(
            "local expectedNode = meshop.getVert srcMesh i",
            self.shape_helper,
        )
        for marker in (
            "setPolyVertWorld dst i expectedNode",
            "getPolyVertWorld dst i",
            "setMeshVertWorld dst i expectedNode",
            "getMeshVertWorld dst i",
            "local expectedLocal = expectedNode * dstInvTM",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.shape_helper)
        self.assertNotIn("local srcTM", self.shape_helper)
        self.assertNotIn("(meshop.getVert srcMesh i) *", self.shape_helper)
        self.assertNotIn("polyop.setVert baseObj i expectedNode", self.shape_helper)
        self.assertNotIn("meshop.setVert workingMesh i expectedNode", self.shape_helper)
        self.assertNotIn("baseObj.mesh = workingMesh", self.shape_helper)
        self.assertNotIn("compensateExistingSkin", self.shape_helper)
        self.assertNotIn("setPolyVertLocal", self.shape_helper)
        self.assertNotIn("setMeshVertLocal", self.shape_helper)

    def test_world_oracle_and_different_transform_cases_are_independent(self) -> None:
        tree = ast.parse(self.trs_runner, filename=str(TRS_RUNNER), feature_version=(3, 9))
        oracle = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                      and node.name == "evaluated_world_positions")
        oracle_source = ast.get_source_segment(self.trs_runner, oracle)
        self.assertIn("in coordsys world", oracle_source)
        self.assertIn("getAnimByHandle", oracle_source)
        self.assertNotIn("snapshotAsMesh", oracle_source)
        self.assertNotIn("objectTransform", oracle_source)
        for marker in ("unit_scale_to_identity", "different_trs_negative_receiver",
                       "destination_transform_expression", "expect_matching", "TRANSFORM_PAIRS"):
            self.assertIn(marker, self.trs_runner)

    def test_final_transactional_rollback_is_retained(self) -> None:
        required = (
            "local writeStarted = false",
            "originalMesh = copy baseObj.mesh",
            "polyop.setVert rollbackBaseObj i originalVerts[i]",
            "rollbackBaseObj.mesh = originalMesh",
            "已完整回滚 Max 源模型原点位",
        )
        for text in required:
            with self.subTest(text=text):
                self.assertIn(text, self.engine)

    def test_oracle_requires_explicit_private_inputs_and_world_geometry(self) -> None:
        required = (
            '_required_private_path("F2M_PRIVATE_MAX_FIXTURE")',
            '_required_private_path("F2M_PRIVATE_FBX_VARIANT1")',
            '_required_private_path("F2M_PRIVATE_FBX_VARIANT2")',
            'TARGET_002 = os.environ.get("F2M_PRIVATE_NODE_B", "ExampleMeshB")',
            'TARGET_003 = os.environ.get("F2M_PRIVATE_NODE_A", "ExampleMeshA")',
            "os.path.isabs(path)",
            "Private fixtures must be outside the source tree",
            "direct_fbx_reference",
            "evaluated_world_positions",
            "compare_positions",
            "expected_002[\"points\"]",
            "expected_003[\"points\"]",
        )
        for text in required:
            with self.subTest(text=text):
                self.assertIn(text, self.runner)

    def test_offset_identity_and_mode2_reload_are_required(self) -> None:
        required = (
            '"002 objectTransform"',
            '"002 pivot"',
            '"node_handle_preserved"',
            "saveMaxFile",
            "loadMaxFile(TEMP_MAX",
            '"saved_and_reloaded": True',
            '"skin_count": 1',
            '"old_handle": old_handle_003',
            '"final_handle": final_handle_003',
        )
        for text in required:
            with self.subTest(text=text):
                self.assertIn(text, self.runner)

    def test_test_is_isolated_and_absolute_module_paths_are_verified(self) -> None:
        self.assertIn('os.environ["LOCALAPPDATA"]', self.runner)
        self.assertIn('"source_files_read_only": True', self.runner)
        self.assertIn('"user_assets_saved": False', self.runner)
        self.assertIn("module.__file__", self.runner)
        self.assertIn("assets_after != assets_before", self.runner)
        self.assertIn("assert_importer_restored", self.runner)
        self.assertIn("assert_importer_restored", self.runner_1322)
        self.assertIn('"initial_max_world_delta"', self.runner)
        self.assertIn('"initial_max_world_delta"', self.runner_1322)

    def test_mode1_imports_skin_and_restores_all_touched_settings(self) -> None:
        self.assertIn(
            'for name in ("Mode", "Animation", "Skin", "SmoothingGroups")',
            self.engine,
        )
        self.assertIn('_set_fbx_importer_param("Skin", True)', self.engine)
        self.assertIn(
            'readback = rt.F2M_Helper.fbxImporterGet(name)',
            self.engine,
        )
        self.assertIn('"Animation", "Skin", "SmoothingGroups"', self.engine)
        self.assertIn("try((value as float) != 0.0)catch undefined", self.skin_engine)
        self.assertIn("observedVisibility == undefined", self.skin_engine)

    def test_normal_authority_uses_a_dedicated_evaluated_stack_reader(self) -> None:
        for marker in (
            'srcMod.name = "F2M_读取 FBX 目标模型求值顶点法线"',
            "addModifier src srcMod",
            "srcReaderIsTemp = true",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.engine)
        self.assertNotIn("srcMod = findEditNormals src", self.engine)

    def test_005_gate_covers_both_toolbar_states_normals_and_visibility(self) -> None:
        required = (
            '_required_private_path("F2M_PRIVATE_MAX_FIXTURE")',
            '_required_private_path("F2M_PRIVATE_FBX_VARIANT1")',
            'os.environ.get("F2M_PRIVATE_NODE_A", "ExampleMeshA")',
            'os.environ.get("F2M_PRIVATE_NODE_B", "ExampleMeshB")',
            'os.environ.get("F2M_PRIVATE_NODE_C", "ExampleMeshC")',
            'lambda: run_mode1_case(references, smoothing_baseline, "world")',
            'lambda: run_mode1_case(references, smoothing_baseline, "local")',
            "NORMAL_ANGLE_TOLERANCE_DEGREES = 0.1",
            "SMOOTHING_NORMAL_ANGLE_TOLERANCE_DEGREES = 0.01",
            "compare_smoothing_semantics",
            '"mismatch_count": 0',
            "run_mode1_smoothing_baseline",
            "normal_difference_stats",
            '"residual_storage_match": True',
            '"observer_isolated_disposable_copy": 1',
            "reset_to_smoothing_baseline=True",
            '"evidence_files_unchanged"',
            '"temporary_reader_removed"',
            "modifier_handle in remaining_handles",
            "sorted(restored_handles) != sorted(old_selection_handles)",
            "assert_visible",
            "saveMaxFile",
            "loadMaxFile",
            '"assets_unchanged"',
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, self.runner_1322)


if __name__ == "__main__":
    unittest.main()
