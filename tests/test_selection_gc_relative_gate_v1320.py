# -*- coding: utf-8 -*-
"""选择切换 GC 发布门的原生对照与相对增长契约回归。"""

from __future__ import annotations

import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW_BASELINE = ROOT / "tests" / "max_fbx_import_gc_baseline.py"
PLUGIN_STRESS = ROOT / "tests" / "max_selection_switch_gc_stress.py"
RUNNER = ROOT / "tests" / "run_selection_switch_gc_stress.ps1"


class SelectionGcRelativeGateV1320Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = RAW_BASELINE.read_text(encoding="utf-8-sig")
        cls.plugin = PLUGIN_STRESS.read_text(encoding="utf-8-sig")
        cls.runner = RUNNER.read_text(encoding="utf-8-sig")

    def test_raw_baseline_requires_explicit_external_fingerprinted_assets(self) -> None:
        for source in (self.raw, self.plugin):
            for variable in (
                "F2M_PRIVATE_MAX_FIXTURE", "F2M_PRIVATE_FBX_VARIANT1",
                "F2M_PRIVATE_FBX_VARIANT2", "F2M_PRIVATE_MAX_SHA256",
                "F2M_PRIVATE_FBX_VARIANT1_SHA256", "F2M_PRIVATE_FBX_VARIANT2_SHA256",
            ):
                self.assertIn(variable, source)
            self.assertIn("os.path.isabs(path)", source)
            self.assertIn("Private fixtures must be outside the source tree", source)
            self.assertIn('re.fullmatch(r"[0-9a-f]{64}", value)', source)
            self.assertNotIn('os.path.join(ROOT, "Test"', source)
        self.assertIn(
            'os.environ.get("F2M_FBX_GC_BASELINE_ITERATIONS", "16")',
            self.raw,
        )
        self.assertIn("matrix[index % len(matrix)]", self.raw)
        self.assertIn('"import_passes": 2 if mixed else 1', self.raw)
        self.assertIn("rt.select(selected)", self.raw)
        self.assertIn('"imported_total": imported_total', self.raw)
        self.assertIn("EXPECTED_ASSET_HASHES", self.raw)

    def test_raw_baseline_uses_only_autodesk_import_and_releases_each_node(
        self,
    ) -> None:
        self.assertIn("FBXImporterGetParam", self.raw)
        self.assertIn("FBXImporterSetParam", self.raw)
        self.assertIn("snapshot_import_options()", self.raw)
        self.assertIn("restore_import_options(snapshot)", self.raw)
        self.assertIn('rt.execute(f\'importFile "{escaped}" #noPrompt\')', self.raw)
        self.assertIn("for handleValue in handleValues do", self.raw)
        self.assertIn("try(delete n)catch()", self.raw)
        self.assertIn("n = undefined", self.raw)
        self.assertNotIn("local doomed = #()", self.raw)
        self.assertNotRegex(
            self.raw,
            r"(?m)^\s*(?:from|import)\s+f2m[_\w]*",
        )
        self.assertNotIn("run_from_max(", self.raw)
        self.assertNotRegex(self.raw, r"\bgc\s*\(")
        self.assertNotIn("clearUndoBuffer", self.raw)

    def test_raw_baseline_proves_scene_assets_and_module_isolation(self) -> None:
        self.assertIn("node_identity_sha256", self.raw)
        self.assertIn("selection_handles", self.raw)
        self.assertIn("assert_scene_restored(", self.raw)
        self.assertIn("loaded_production_modules()", self.raw)
        self.assertIn('"production_modules_loaded"', self.raw)
        self.assertIn(
            "hashes_after != hashes_before or "
            "hashes_after != EXPECTED_ASSET_HASHES",
            self.raw,
        )
        self.assertIn('run_result["assets"]["unchanged"] = True', self.raw)
        self.assertIn(
            '"delete_strategy": "single_node_by_handle_immediate_release"',
            self.raw,
        )

    def test_plugin_gate_measures_only_excess_over_the_raw_baseline(self) -> None:
        self.assertIn(
            "F2M_SELECTION_STRESS_RAW_PRIVATE_GROWTH_BYTES",
            self.plugin,
        )
        self.assertIn(
            "F2M_SELECTION_STRESS_MAX_PRIVATE_EXCESS_GROWTH_MB",
            self.plugin,
        )
        self.assertIn('"256"', self.plugin)
        self.assertIn(
            "private_excess_growth = private_growth - raw_private_growth",
            self.plugin,
        )
        self.assertIn('"private_usage_excess_over_raw"', self.plugin)
        self.assertIn(
            "private_excess_growth > MAX_PRIVATE_EXCESS_GROWTH_BYTES",
            self.plugin,
        )
        self.assertNotIn("MAX_PRIVATE_GROWTH_BYTES", self.plugin)
        self.assertNotIn(
            "F2M_SELECTION_STRESS_MAX_PRIVATE_GROWTH_MB",
            self.plugin,
        )

    def test_runner_serializes_fresh_raw_then_plugin_and_binds_evidence(
        self,
    ) -> None:
        expected_executable = (
            r"D:\Autodesk\3dsmax2023\3ds Max 2023\3dsmaxbatch.exe"
        )
        self.assertIn(expected_executable, self.runner)
        self.assertIn("[int]$MaxPrivateExcessGrowthMiB = 256", self.runner)
        raw_call = self.runner.index("$rawRun = Invoke-IsolatedMaxBatch")
        binding = self.runner.index(
            "'F2M_SELECTION_STRESS_RAW_PRIVATE_GROWTH_BYTES'"
        )
        plugin_call = self.runner.index("$pluginRun = Invoke-IsolatedMaxBatch")
        self.assertLess(raw_call, binding)
        self.assertLess(binding, plugin_call)
        self.assertIn("LastWriteTimeUtc", self.runner)
        self.assertIn("$rawRun.owned_pids.Contains", self.runner)
        self.assertIn("$rawRun.timed_out", self.runner)
        self.assertIn("$rawResult.production_modules_loaded", self.runner)
        self.assertIn("$assetHashesAfterRaw", self.runner)
        self.assertIn("F2M_RAW_FBX_GC_BASELINE_BEGIN", self.runner)
        self.assertIn("F2M_RAW_FBX_GC_BASELINE_END", self.runner)
        self.assertIn("F2M_SELECTION_GC_STRESS_BEGIN", self.runner)
        self.assertIn("F2M_SELECTION_GC_STRESS_END", self.runner)
        self.assertIn("private_usage_excess_over_raw", self.runner)
        self.assertIn("$process.WaitForExit()", self.runner)


if __name__ == "__main__":
    unittest.main()
