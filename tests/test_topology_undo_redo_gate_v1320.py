# -*- coding: utf-8 -*-
"""Static contracts for the real topology Undo/Redo MaxBatch gate."""

from __future__ import annotations

import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
GATE_PATH = ROOT / "tests" / "max_topology_undo_redo_v1320.py"
RUNNER_PATH = ROOT / "tests" / "run_topology_undo_redo_v1320.ps1"
SAVE_RUNNER_PATH = ROOT / "tests" / "run_topology_save_reload_v1320.ps1"


class TopologyUndoRedoGateV1320Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gate = GATE_PATH.read_text(encoding="utf-8")
        cls.runner = RUNNER_PATH.read_text(encoding="utf-8")
        cls.save_runner = SAVE_RUNNER_PATH.read_text(encoding="utf-8")

    def test_gate_is_fixture_bound_and_loads_current_module_absolutely(self):
        self.assertIn(
            '"tests", "fixtures", "topology_source.fbx"',
            self.gate,
        )
        self.assertIn(
            'MODULE_PATH = os.path.join(RUNTIME_ROOT, "f2m_topology_transfer.py")',
            self.gate,
        )
        self.assertIn("spec_from_file_location", self.gate)
        self.assertIn("os.path.abspath(module.__file__)", self.gate)
        self.assertIn('VERSION = "1.4.25"', self.gate)
        self.assertNotIn("Blender To 3dsMax", self.gate + self.runner)

    def test_gate_requires_launcher_token_and_records_all_identity_hashes(self):
        self.assertIn(
            'RUN_TOKEN_ENV = "F2M_TOPOLOGY_UNDO_REDO_RUN_TOKEN"',
            self.gate,
        )
        self.assertIn(
            're.fullmatch(r"[0-9a-fA-F]{32}", run_token)',
            self.gate,
        )
        for key in (
            '"run_token"',
            '"engine_pid"',
            '"gate_script_sha256"',
            '"module_sha256"',
            '"fixture_sha256"',
        ):
            self.assertIn(key, self.gate)
        self.assertIn("os.replace(temporary, RESULT)", self.gate)

    def test_formal_call_is_exactly_normals_plus_smoothing(self):
        call = re.search(
            r"topology\.run_from_max\((?P<body>.*?)\n    \)",
            self.gate,
            re.DOTALL,
        )
        self.assertIsNotNone(call)
        body = call.group("body")
        self.assertIn("dry_run=False", body)
        self.assertIn("transfer_normals=True", body)
        self.assertIn("transfer_smoothing_groups=True", body)
        for disabled in (
            "transfer_shape=False",
            "transfer_uv=False",
            "transfer_vertex_color=False",
            "transfer_alpha=False",
            "transfer_material_ids=False",
        ):
            self.assertIn(disabled, body)

    def test_gate_binds_current_strict_combo_and_rejects_full_override(self):
        for marker in (
            "_assert_production_combo_contract",
            "_inspect_smoothing_and_normal_data(ctx)",
            "_resolve_smoothing_masks_from_single_exact_import(",
            "smoothing_groups=False",
            r"ctx\.options\.transfer_smoothing_groups",
            r"ctx\.existing_smoothing_masks_by_handle",
            "smoothing_residual_only=",
            "use_smoothing_residual",
            "copy_smoothing_groups(",
            "copy_normals(",
            "FULL_OVERRIDE_REPORT_MARKERS",
            '"current_combo_contract_verified"',
            '"residual_not_full_override"',
        ):
            self.assertIn(marker, self.gate)
        self.assertIn(
            'payload["normal_contract"] = '
            "_assert_production_combo_contract()",
            self.gate,
        )
        self.assertNotIn(
            'payload["normal_contract"] = '
            "_assert_production_residual_contract()",
            self.gate,
        )
        self.assertIn(
            'if "smoothing_residual_only=False" in '
            "process_source[normals_at:]",
            self.gate,
        )
        self.assertIn(
            "expected_final_f2m_count = 1",
            self.gate,
        )
        self.assertIn(
            "if zero_residual == nonzero_residual:",
            self.gate,
        )
        self.assertIn(
            '"sg_write_readback_marker_verified": True',
            self.gate,
        )
        self.assertIn(
            '"zero_residual_blue_f2m"',
            self.gate,
        )
        self.assertIn("_assert_only_expected_f2m(", self.gate)
        self.assertIn(
            "_assert_final_f2m_at_stack_bottom(",
            self.gate,
        )
        self.assertIn("if smoothing_at >= normals_at:", self.gate)
        self.assertIn("if forbidden:", self.gate)
        self.assertIn(
            'int(final_state["specified_count"])',
            self.gate,
        )
        self.assertIn(
            '< int(final_state["corner_count"])',
            self.gate,
        )
        self.assertIn(
            'int(final_state["explicit_corner_count"])',
            self.gate,
        )
        self.assertNotIn(
            "_feed_int(corner_digest, normal_id)",
            self.gate,
        )
        self.assertIn(
            '"semantic_corner_sha256"',
            self.gate,
        )
        self.assertIn(
            '"normal_semantics_preserved_through_redo"',
            self.gate,
        )
        self.assertNotIn("getFaceRNormals", self.gate)
        self.assertNotIn("_render_corner_vectors", self.gate)
        self.assertNotIn("COLLAPSE_BLUE_DIAGNOSTIC", self.gate + self.runner)
        self.assertNotIn("modifier_stack_diagnostic", self.gate)
        self.assertNotIn("modifier_state_diagnostic", self.gate)

    def test_snapshots_cover_required_semantics_and_exact_round_trips(self):
        for marker in (
            '"base_point_sha256"',
            '"point_sha256"',
            '"topology_sha256"',
            '"uv1"',
            '"maps"',
            '"smoothing"',
            '"modifiers"',
            '"normals"',
            '"fingerprint_sha256"',
            "snapshotAsMesh",
            "GetNormalExplicit",
            "GetFaceNormalSpecified",
            '"semantic_corner_sha256"',
            "captureBaseVertexPositions",
        ):
            self.assertIn(marker, self.gate)
        self.assertIn("if after_undo != before:", self.gate)
        self.assertIn("if after_redo != after:", self.gate)
        self.assertIn(
            'payload["normal_semantics_preserved_through_redo"] = True',
            self.gate,
        )
        self.assertIn("_snapshot_map_channel", self.gate)
        self.assertIn("for channel in range(-2, 100)", self.gate)
        self.assertIn(
            'after_redo["modifiers"]["f2m_named"]',
            self.gate,
        )
        self.assertIn("[FINAL_NORMAL_MODIFIER]", self.gate)
        self.assertIn("temporary_f2m_names", self.gate)

    def test_exactly_one_undo_and_redo_use_the_production_label(self):
        self.assertEqual(self.gate.count("pymxs.run_undo()"), 1)
        self.assertEqual(self.gate.count("pymxs.run_redo()"), 1)
        self.assertIn(
            'expected_label = f"FBXTo3dsMax v{topology.TOOL_VERSION}: '
            '{target_name}"',
            self.gate,
        )
        self.assertIn("rt.theHold.getCurrentUndoLevels()", self.gate)
        self.assertIn("callbacks.notificationParam()", self.gate)
        self.assertIn("#sceneUndo", self.gate)
        self.assertIn("#sceneRedo", self.gate)
        self.assertIn("windows.processPostedMessages()", self.gate)
        self.assertIn("_wait_for_callback_counts(1, 0)", self.gate)
        self.assertIn("_wait_for_callback_counts(1, 1)", self.gate)
        self.assertIn('len(payload["scene_undo_labels"]) > 1', self.gate)
        self.assertIn('len(payload["scene_redo_labels"]) > 1', self.gate)
        self.assertNotIn("getUndoNames", self.gate)
        self.assertNotIn("getRedoNames", self.gate)
        self.assertEqual(self.gate.count("rt.clearUndoBuffer()"), 1)
        clear_at = self.gate.index("rt.clearUndoBuffer()")
        transfer_at = self.gate.index("topology.run_from_max(")
        undo_at = self.gate.index("pymxs.run_undo()")
        redo_at = self.gate.index("pymxs.run_redo()")
        self.assertLess(clear_at, transfer_at)
        self.assertLess(transfer_at, undo_at)
        self.assertLess(undo_at, redo_at)

    def test_heap_and_final_reset_are_hard_requirements(self):
        self.assertIn('"heap_check_after_undo"', self.gate)
        self.assertIn('"heap_check_after_redo"', self.gate)
        self.assertIn("if not _heap_ok", self.gate)
        self.assertIn("_safe_reset()", self.gate)
        self.assertIn('rt.Name("noPrompt")', self.gate)
        self.assertNotIn("gc.collect", self.gate)

    def test_save_reload_gate_is_token_bound_and_checks_persistence(self):
        for marker in (
            'RESULT_ENV = "F2M_TOPOLOGY_GATE_RESULT"',
            'SAVE_RELOAD_PATH_ENV = "F2M_TOPOLOGY_SAVE_RELOAD_PATH"',
            "_max_topology_save_reload_v1320_{token}.tmp.max",
            "rt.saveMaxFile(save_path, quiet=True)",
            "rt.resetMaxFile(rt.Name(\"noPrompt\"))",
            "rt.loadMaxFile(",
            '"base_points_exact": True',
            '"evaluated_points_exact": True',
            '"uv1_exact": True',
            '"smoothing_groups_exact": True',
            '"edit_normals_semantic_state_exact": True',
            '"final_f2m_contract_verified": True',
            "os.remove(save_reload_path)",
            '"temporary_max_removed"',
        ):
            self.assertIn(marker, self.gate)
        self.assertIn(
            'if int(entry["index"]) != int(modifiers["count"]):',
            self.gate,
        )
        self.assertIn("[switch]$SaveReload", self.runner)
        self.assertIn("F2M_TOPOLOGY_GATE_RESULT", self.runner)
        self.assertIn("F2M_TOPOLOGY_SAVE_RELOAD_PATH", self.runner)
        self.assertIn("$saveReloadVerified", self.runner)
        self.assertIn("$finalF2mContractVerified", self.runner)
        self.assertIn("$saveReloadF2mVerified", self.runner)
        self.assertIn("-SaveReload", self.save_runner)
        self.assertIn(
            "run_topology_undo_redo_v1320.ps1",
            self.save_runner,
        )

    def test_runner_binds_fresh_result_natural_exit_and_native_log(self):
        for marker in (
            "[Guid]::NewGuid().ToString('N')",
            "F2M_TOPOLOGY_UNDO_REDO_RUN_TOKEN",
            "$process.WaitForExit",
            "$process.ExitCode",
            "$business.run_token -ceq $runToken",
            "$business.engine_pid",
            "Get-FileHash -LiteralPath $scriptPath",
            "Get-FileHash -LiteralPath $modulePath",
            "Get-FileHash -LiteralPath $fixturePath",
            "LastWriteTimeUtc",
            "engine_exited_naturally",
            "native_error_count",
            "Update-OwnedProcessSet",
            "$ownedPids.Contains($enginePid)",
            "$identityPassed",
            "$LASTEXITCODE",
            "WaitForExit(5000)",
            "token_log_bound",
            "listener_token_bound",
            "[IO.FileShare]::None",
        ):
            self.assertIn(marker, self.runner)
        self.assertIn(
            "& taskkill.exe /PID $RootProcessId /T /F",
            self.runner,
        )
        self.assertIn("$pidPattern = '\\[0*'", self.runner)
        self.assertIn("MAXScript Garbage Collection Error", self.runner)
        self.assertIn("Exception in MAXScript Garbage Collector", self.runner)
        self.assertIn("$undoTransactionVerified", self.runner)
        self.assertIn(
            "$business.normal_semantics_preserved_through_redo -eq $true",
            self.runner,
        )
        self.assertIn("$afterFinalStates.Count -eq 1", self.runner)
        self.assertNotIn("authority_direction_check", self.runner)
        self.assertIn("scene_undo_labels", self.runner)
        self.assertIn("scene_redo_labels", self.runner)
        self.assertNotRegex(self.runner, r"WaitForExit\(\)")
        identity_at = self.runner.index("$identityPassed =")
        engine_wait_at = self.runner.index("$engineExitedNaturally =")
        self.assertLess(identity_at, engine_wait_at)


if __name__ == "__main__":
    unittest.main()
