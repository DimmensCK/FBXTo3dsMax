from __future__ import annotations

import re
import unittest
from pathlib import Path

# Resolve runtime modules from the source distribution without a global PYTHONPATH.
import sys as _f2m_test_sys
from pathlib import Path as _F2MTestPath
_f2m_test_root = _F2MTestPath(__file__).resolve().parents[1]
_f2m_test_sys.path.insert(0, str(_f2m_test_root / "contents" if (_f2m_test_root / "contents").is_dir() else _f2m_test_root))

import f2m_topology_transfer as topology


def _function_block(source: str, name: str, next_name: str) -> str:
    start = source.index(f"fn {name}")
    end = source.index(f"fn {next_name}", start)
    return source[start:end]


class HybridFinalCornerNormalsV1320Tests(unittest.TestCase):
    def test_explicit_overrides_are_full_vectors_not_vector_subtraction(self):
        helper = topology.HELPER_SCRIPT
        apply_block = _function_block(
            helper,
            "applyEditNormalResidualsFlatFromExact",
            "copyExplicitNormalResiduals",
        )

        self.assertIn(
            "expectedNormal =",
            apply_block,
        )
        self.assertIn(
            "flatEditNormalVector srcData expectedSourceId",
            apply_block,
        )
        self.assertIn(
            "dstMod.SetNormal normalIndex &expectedNormal node:dstNode",
            apply_block,
        )
        self.assertNotRegex(
            apply_block,
            r"(?i)(source|expected|normalValue|expectedNormal)\w*\s*-\s*"
            r"(baseline|smooth|sg)\w*",
        )

    def test_hybrid_transform_includes_every_referenced_corner_normal(self):
        helper = topology.HELPER_SCRIPT
        transform_block = _function_block(
            helper,
            "transformEditNormalsSnapshotFlat",
            "remapEditNormalsSnapshotFlat",
        )
        residual_block = _function_block(
            helper,
            "copyExplicitNormalResiduals",
            "copyExplicitNormals",
        )
        self.assertIn("includeAllReferenced:false", transform_block)
        self.assertIn(
            "for flatCornerIndex = 1 to srcData[7].count do",
            transform_block,
        )
        self.assertIn(
            "normalsToTransform[referencedNormalId] = true",
            transform_block,
        )
        self.assertIn(
            "transformEditNormalsSnapshotFlat srcData src dst "
            "includeAllReferenced:true",
            residual_block,
        )

    def test_residual_classification_compares_all_face_corners(self):
        helper = topology.HELPER_SCRIPT
        build_block = _function_block(
            helper,
            "buildEditNormalResidualSnapshotFlat",
            "editNormalResidualsFlatMatch",
        )

        self.assertIn("for faceIndex = 1 to srcData[1] do", build_block)
        self.assertIn("for cornerIndex = 1 to srcDegree do", build_block)
        self.assertIn(
            "normalAngleDegrees sourceNormal baselineNormal",
            build_block,
        )
        self.assertIn(
            "residualNormalIds[srcNormalId] = true",
            build_block,
        )
        self.assertIn(
            "residualSpecifiedCorners[srcFlatCorner] = true",
            build_block,
        )
        self.assertNotIn("if authored do", build_block)
        self.assertNotIn(
            "if residualNormalIds[normalId] do",
            build_block,
        )
        self.assertNotRegex(
            build_block,
            re.compile(
                r"for\s+cornerIndex\s*=\s*1\s+to\s+srcDegree\s+where",
                re.IGNORECASE,
            ),
        )

    def test_shared_source_normal_id_does_not_expand_residual_corners(self):
        helper = topology.HELPER_SCRIPT
        build_block = _function_block(
            helper,
            "buildEditNormalResidualSnapshotFlat",
            "editNormalResidualsFlatMatch",
        )
        threshold_branch = build_block[
            build_block.index("if angleValue > angleToleranceDegrees then") :
            build_block.index("else if angleValue > maxIgnoredAngle do")
        ]

        self.assertIn(
            "residualSpecifiedCorners[srcFlatCorner] = true",
            threshold_branch,
        )
        self.assertIn(
            "residualNormalIds[srcNormalId] = true",
            threshold_branch,
        )
        self.assertIn("residualCornerCount += 1", threshold_branch)
        self.assertNotIn("for flatCornerIndex", threshold_branch)

    def test_semantic_residual_expands_only_to_its_sg_fan_guard_closure(self):
        helper = topology.HELPER_SCRIPT
        build_block = _function_block(
            helper,
            "buildEditNormalResidualSnapshotFlat",
            "editNormalResidualsFlatMatch",
        )

        self.assertIn(
            "residualBaselineNormalIds[baselineNormalId] = true",
            build_block,
        )
        self.assertIn(
            "if residualBaselineNormalIds[baselineNormalId] do",
            build_block,
        )
        self.assertIn(
            "retainedSpecifiedCorners[flatCornerIndex] = true",
            build_block,
        )
        self.assertIn(
            "guardCornerCount",
            build_block,
        )

    def test_final_verifier_covers_blue_and_green_corners(self):
        helper = topology.HELPER_SCRIPT
        verify_block = _function_block(
            helper,
            "finalFaceCornerNormalsFlatMatch",
            "applyEditNormalResidualsFlatFromExact",
        )

        self.assertIn(
            "for faceIndex = 1 to expectedData[1] do",
            verify_block,
        )
        self.assertIn(
            "for cornerIndex = 1 to expectedDegree do",
            verify_block,
        )
        self.assertIn(
            "dstMod.GetNormalID faceIndex cornerIndex node:dstNode",
            verify_block,
        )
        self.assertIn(
            "normalAngleDegrees expectedNormal actualNormal",
            verify_block,
        )
        self.assertIn(
            "if angleValue > angleToleranceDegrees do",
            verify_block,
        )
        self.assertIn("maxFinalAngle", verify_block)
        self.assertNotIn("expectedData[8][flatCornerIndex] do", verify_block)

    def test_apply_rebuilds_residual_ids_from_target_face_corners(self):
        helper = topology.HELPER_SCRIPT
        apply_block = _function_block(
            helper,
            "applyEditNormalResidualsFlatFromExact",
            "copyExplicitNormalResiduals",
        )

        self.assertIn(
            "if srcData[8][flatCornerIndex] then",
            apply_block,
        )
        self.assertIn(
            "dstMod.GetNormalID faceIndex cornerIndex node:dstNode",
            apply_block,
        )
        self.assertIn(
            "dstMod.Break selection:retainedFans",
            apply_block,
        )
        self.assertIn(
            "(retainedFans * baselineFans).numberSet > 0",
            apply_block,
        )
        self.assertIn(
            "(residualNormals * baselineFans).numberSet > 0",
            apply_block,
        )
        self.assertNotIn(
            "dstMod.Reset",
            apply_block,
        )
        self.assertIn(
            "dstMod.MakeExplicit selection:residualNormals",
            apply_block,
        )
        self.assertIn(
            "dstMod.SetNormalExplicit normalIndex explicit:false node:dstNode",
            apply_block,
        )
        self.assertIn(
            "specified:(srcData[8][flatCornerIndex]) node:dstNode",
            apply_block,
        )
        self.assertNotIn("rebuildEditNormalsStrict", apply_block)
        self.assertNotIn("dstMod.RebuildNormals", apply_block)
        self.assertIn(
            "expectedSourceIdByActual",
            apply_block,
        )
        self.assertIn(
            "flatEditNormalVector srcData expectedSourceId",
            apply_block,
        )
        self.assertIn(
            "dstMod.SetNormal normalIndex &expectedNormal node:dstNode",
            apply_block,
        )
        self.assertIn(
            "Break 后仍有 SG 基线和残差共用 actual normal ID",
            apply_block,
        )
        # The fresh destination modifier starts as legal SG fans.  Break can
        # renumber its local pool, so residual IDs are collected only after
        # breaking the complete retained fans.
        break_position = apply_block.index(
            "dstMod.Break selection:retainedFans"
        )
        residual_position = apply_block.index(
            "local residualNormals = #{}",
            break_position,
        )
        make_explicit_position = apply_block.index(
            "dstMod.MakeExplicit selection:residualNormals",
            residual_position,
        )
        self.assertLess(break_position, residual_position)
        self.assertLess(residual_position, make_explicit_position)
        self.assertEqual(apply_block.count("local residualNormals = #{}"), 1)

    def test_hybrid_apply_replays_all_final_corner_states(self):
        helper = topology.HELPER_SCRIPT
        apply_block = _function_block(
            helper,
            "applyEditNormalResidualsFlatFromExact",
            "copyExplicitNormalResiduals",
        )

        make_explicit = apply_block.index(
            "dstMod.MakeExplicit selection:residualNormals"
        )
        set_normal = apply_block.index(
            "dstMod.SetNormal normalIndex &expectedNormal node:dstNode",
            make_explicit,
        )
        baseline_clear = apply_block.index(
            "dstMod.SetNormalExplicit normalIndex explicit:false node:dstNode",
            set_normal,
        )
        every_corner = apply_block.index(
            "for cornerIndex = 1 to sourceDegree do",
            baseline_clear,
        )
        flat_corner = apply_block.index(
            "local flatCornerIndex =",
            every_corner,
        )
        replay_state = apply_block.index(
            "dstMod.SetFaceNormalSpecified faceIndex cornerIndex "
            "specified:(srcData[8][flatCornerIndex]) node:dstNode",
            flat_corner,
        )
        final_update = apply_block.index("update dstNode", replay_state)

        self.assertLess(make_explicit, set_normal)
        self.assertLess(set_normal, baseline_clear)
        self.assertLess(baseline_clear, every_corner)
        self.assertLess(every_corner, flat_corner)
        self.assertLess(flat_corner, replay_state)
        self.assertLess(replay_state, final_update)
        self.assertEqual(
            apply_block.count(
                "specified:(srcData[8][flatCornerIndex]) node:dstNode"
            ),
            1,
        )

    def test_blue_corners_must_reference_non_explicit_normals(self):
        helper = topology.HELPER_SCRIPT
        match_block = _function_block(
            helper,
            "editNormalResidualsFlatMatch",
            "finalFaceCornerNormalsFlatMatch",
        )

        self.assertIn(
            "if dstMod.GetNormalExplicit actualId node:dstNode do",
            match_block,
        )
        self.assertIn(
            "应由光滑组求值",
            match_block,
        )

    def test_hybrid_path_rechecks_structure_after_each_final_direction(self):
        helper = topology.HELPER_SCRIPT
        residual_block = _function_block(
            helper,
            "copyExplicitNormalResiduals",
            "copyExplicitNormals",
        )

        self.assertEqual(
            residual_block.count(
                "editNormalResidualsFlatMatch residualData dst dstMod"
            ),
            6,
        )
        self.assertEqual(
            residual_block.count(
                "finalFaceCornerNormalsFlatMatch srcData dst dstMod"
            ),
            4,
        )
        self.assertIn("update dst", residual_block)
        self.assertIn(
            "dstMod = Edit_Normals()",
            residual_block,
        )
        self.assertIn(
            "resetEditNormalsToSmoothingBaselineStrict dst dstMod",
            residual_block,
        )
        self.assertIn(
            "baselineData = snapshotEditNormalsDataFlat dst dstMod",
            residual_block,
        )
        self.assertIn(
            "applyEditNormalResidualsFlatFromExact residualData dst dstMod",
            residual_block,
        )
        self.assertNotIn("buildExternalSmoothingBaselineFlat", residual_block)
        self.assertNotIn(
            "applyEditNormalsSnapshotFlatDifferential",
            residual_block,
        )
        self.assertNotIn("addModifierWithLocalData", residual_block)
        self.assertNotIn("useDenseExactFallback", residual_block)
        zero_start = residual_block.index("if retainedNormalCount == 0 then")
        nonzero_start = residual_block.index("else", zero_start)
        for branch in (
            residual_block[zero_start:nonzero_start],
            residual_block[nonzero_start:],
        ):
            structure_marker = (
                "editNormalResidualsFlatMatch residualData dst dstMod"
            )
            direction_marker = (
                "finalFaceCornerNormalsFlatMatch srcData dst dstMod"
            )
            self.assertEqual(branch.count(structure_marker), 3)
            self.assertEqual(branch.count(direction_marker), 2)
            structure_one = branch.find(structure_marker)
            direction_one = branch.find(direction_marker, structure_one)
            structure_two = branch.find(structure_marker, direction_one)
            direction_two = branch.find(direction_marker, structure_two)
            structure_three = branch.find(structure_marker, direction_two)
            self.assertGreater(direction_one, structure_one)
            self.assertGreater(structure_two, direction_one)
            self.assertGreater(direction_two, structure_two)
            self.assertGreater(structure_three, direction_two)
            self.assertEqual(branch.rfind(structure_marker), structure_three)
        self.assertIn("最大最终角差", residual_block)
        self.assertIn("全部面角最终方向已完成两次读回", residual_block)

    def test_dense_exact_fallback_is_forbidden(self):
        helper = topology.HELPER_SCRIPT
        residual_block = _function_block(
            helper,
            "copyExplicitNormalResiduals",
            "copyExplicitNormals",
        )

        self.assertNotIn("useDenseExactFallback", residual_block)
        self.assertNotIn("retainedCornerRatio", residual_block)
        self.assertNotIn(">= 0.95", residual_block)
        self.assertNotIn("高覆盖安全阈值", residual_block)
        self.assertNotIn("不执行混合残差去冗余", residual_block)
        self.assertIn(
            "applyEditNormalResidualsFlatFromExact residualData dst dstMod",
            residual_block,
        )

    def test_fresh_actual_destination_baseline_precedes_residual_write(self):
        helper = topology.HELPER_SCRIPT
        residual_block = _function_block(
            helper,
            "copyExplicitNormalResiduals",
            "copyExplicitNormals",
        )

        self.assertIn("dstMod = Edit_Normals()", residual_block)
        self.assertIn(
            "addModifier dst dstMod before:(dst.modifiers.count + 1)",
            residual_block,
        )
        self.assertIn(
            "baselineData = snapshotEditNormalsDataFlat dst dstMod",
            residual_block,
        )
        self.assertIn(
            "baselineData[4].numberSet != 0",
            residual_block,
        )
        self.assertIn(
            "baselineData[8].numberSet != 0",
            residual_block,
        )
        self.assertNotIn("dstMod = copy srcMod", residual_block)
        self.assertNotIn("addModifierWithLocalData", residual_block)
        self.assertNotIn("buildExternalSmoothingBaselineFlat", residual_block)
        _assert_ordered = (
            "removeF2MNormalModifiers dst",
            "dstMod = Edit_Normals()",
            "addModifier dst dstMod",
            "resetEditNormalsToSmoothingBaselineStrict dst dstMod",
            "baselineData = snapshotEditNormalsDataFlat dst dstMod",
            "buildEditNormalResidualSnapshotFlat",
            "applyEditNormalResidualsFlatFromExact residualData dst dstMod",
        )
        positions = [
            residual_block.index(marker)
            for marker in _assert_ordered
        ]
        self.assertEqual(positions, sorted(positions))

    def test_zero_residual_retains_blue_baseline_modifier(self):
        helper = topology.HELPER_SCRIPT
        residual_block = _function_block(
            helper,
            "copyExplicitNormalResiduals",
            "copyExplicitNormals",
        )

        zero_start = residual_block.index("if retainedNormalCount == 0 then")
        final_start = residual_block.index("else", zero_start)
        zero_block = residual_block[zero_start:final_start]
        self.assertNotIn("dstMod = copy srcMod", zero_block)
        self.assertNotIn("addModifierWithLocalData", zero_block)
        self.assertLess(
            residual_block.index("removeF2MNormalModifiers dst"),
            zero_start,
        )
        self.assertNotIn("getHandleByAnim dstMod", zero_block)
        self.assertNotIn("removeModifierByAnimHandle dst", zero_block)
        self.assertIn("保留一个全蓝色 ", zero_block)
        self.assertIn("Unspecified 的 F2M Edit Normals 基线", zero_block)
        self.assertEqual(
            zero_block.count(
                "editNormalResidualsFlatMatch residualData dst dstMod"
            ),
            3,
        )
        self.assertEqual(
            zero_block.count(
                "finalFaceCornerNormalsFlatMatch srcData dst dstMod"
            ),
            2,
        )

    def test_hybrid_contract_adds_no_forced_gc_heap_or_undo_operations(self):
        helper_lower = topology.HELPER_SCRIPT.lower()
        self.assertNotIn("gc()", helper_lower)
        self.assertNotIn("heapfree", helper_lower)
        self.assertNotIn("heapsize", helper_lower)
        self.assertNotIn("clearundobuffer", helper_lower)

    def test_formal_normal_rebuilds_are_fail_closed(self):
        helper = topology.HELPER_SCRIPT
        strict_block = _function_block(
            helper,
            "rebuildEditNormalsStrict",
            "findEditNormals",
        )
        residual_block = _function_block(
            helper,
            "copyExplicitNormalResiduals",
            "copyExplicitNormals",
        )
        exact_block = _function_block(
            helper,
            "copyExplicitNormals",
            "pointReadbackTolerance",
        )

        self.assertIn("rebuildError = getCurrentException()", strict_block)
        self.assertIn("if rebuildError != \"\" do", strict_block)
        self.assertNotRegex(
            residual_block + exact_block,
            r"try\([^\r\n]*RebuildNormals[^\r\n]*\)catch\(\)",
        )
        # Residual production directly rebuilds only the FBX source reader.
        # The destination baseline uses the dedicated reset helper below;
        # Break/MakeExplicit and both final checks must not rebuild it again.
        self.assertEqual(
            residual_block.count("rebuildEditNormalsStrict"),
            1,
        )
        self.assertIn(
            "rebuildEditNormalsStrict src srcMod",
            residual_block,
        )
        self.assertIn(
            "resetEditNormalsToSmoothingBaselineStrict dst dstMod",
            residual_block,
        )
        reset_block = _function_block(
            helper,
            "resetEditNormalsToSmoothingBaselineStrict",
            "findEditNormals",
        )
        self.assertEqual(
            reset_block.count("rebuildEditNormalsStrict n modInst"),
            3,
        )
        self.assertIn(
            "modInst.Reset selection:allNormals node:n",
            reset_block,
        )
        self.assertIn(
            "if not (activateModifier n modInst) do",
            reset_block,
        )
        self.assertIn(
            "if normalId < 1 or normalId > finalNormalCount do",
            reset_block,
        )
        self.assertIn(
            "if modInst.GetFaceNormalSpecified faceIndex cornerIndex node:n do",
            reset_block,
        )
        self.assertIn("resetError = getCurrentException()", reset_block)
        self.assertIn("Reset 后重新激活法线重建失败", reset_block)
        apply_block = _function_block(
            helper,
            "applyEditNormalResidualsFlatFromExact",
            "copyExplicitNormalResiduals",
        )
        self.assertNotIn("rebuildEditNormalsStrict", apply_block)
        self.assertNotIn("RebuildNormals", apply_block)
        self.assertIn(
            "rebuildBeforeRead:false",
            residual_block,
        )
        self.assertGreaterEqual(
            exact_block.count("rebuildEditNormalsStrict"),
            2,
        )

    def test_process_pair_rereads_smoothing_after_normals(self):
        with open(topology.__file__, "r", encoding="utf-8") as stream:
            source = stream.read()
        start = source.index("def process_pair(")
        end = source.index("def process_pair_transactional(", start)
        block = source[start:end]

        self.assertIn(
            "actual_values = rt.F2M_Helper.getFaceSmoothingGroups(dst)",
            block,
        )
        self.assertIn(
            "if actual_smoothing != expected_smoothing:",
            block,
        )
        self.assertIn(
            "残差验收：顶点法线写入后已再次逐面读取光滑组",
            block,
        )
        self.assertIn(
            "use_smoothing_residual = (\n"
            "            ctx.options.transfer_smoothing_groups\n"
            "            or target_record.handle\n"
            "            in ctx.existing_smoothing_masks_by_handle\n"
            "        )",
            block,
        )
        self.assertIn(
            "smoothing_residual_only=use_smoothing_residual",
            block,
        )
        self.assertNotIn("smoothing_baseline=", block)
        self.assertNotIn(
            "ctx.smoothing_normal_baselines_by_name.get(",
            block,
        )
        self.assertIn(
            "if ctx.options.transfer_smoothing_groups and not smoothing_ok:",
            block,
        )
        self.assertIn(
            "组合策略要求先成功写入并逐面读回光滑组",
            block,
        )
        self.assertNotIn("copyExplicitNormalResiduals(", block)
        self.assertIn(
            "随后只保留光滑组不能等价表达的自定义法线残差",
            block,
        )
        self.assertIn(
            "仅法线差异策略：Max 源模型已有非零光滑组",
            block,
        )

    def test_normals_only_branches_on_existing_target_smoothing(self):
        with open(topology.__file__, "r", encoding="utf-8") as stream:
            source = stream.read()

        prepare_start = source.index(
            "def _prepare_normals_only_smoothing_targets("
        )
        prepare_end = source.index(
            "def imported_geometry_nodes(",
            prepare_start,
        )
        prepare = source[prepare_start:prepare_end]
        import_start = source.index("def import_fbx(")
        import_end = source.index(
            "def imported_geometry_by_name(",
            import_start,
        )
        import_block = source[import_start:import_end]

        self.assertIn("if any(value != 0 for value in masks):", prepare)
        self.assertIn(
            "ctx.existing_smoothing_masks_by_handle[record.handle] = masks",
            prepare,
        )
        self.assertIn(
            "现有光滑组全部为 0；",
            prepare,
        )
        self.assertIn(
            "将完整复制 FBX 自定义法线",
            prepare,
        )
        self.assertIn(
            "and ctx.existing_smoothing_masks_by_handle",
            import_block,
        )
        self.assertIn(
            "仅传递顶点法线且 Max 源模型已有光滑组：只导入一次 FBX",
            import_block,
        )
        self.assertIn(
            "蓝色 SG 基线直接由实际接收模型的现有",
            import_block,
        )
        self.assertIn(
            "ctx.imported_nodes = _import_fbx_once(",
            import_block,
        )
        self.assertIn(
            "_inspect_smoothing_and_normal_data(ctx)",
            import_block,
        )
        self.assertIn(
            "只执行一次 "
            '"\n                "SmoothingGroups=false 精确导入',
            import_block,
        )
        self.assertIn(
            "_resolve_smoothing_masks_from_single_exact_import(",
            import_block,
        )
        self.assertIn("_capture_smoothing_masks(ctx, first_pass)", import_block)
        self.assertNotIn(
            "_capture_existing_target_smoothing_baselines",
            import_block,
        )
        self.assertNotIn(
            "_validate_external_smoothing_baselines_against_second_import",
            import_block,
        )

    def test_real_max_gate_distinguishes_semantic_residual_and_guard_closure(self):
        runner = (
            Path(__file__).with_name(
                "run_hybrid_normals_equivalence_v1320.ps1"
            )
            .read_text(encoding="utf-8")
        )

        self.assertIn("semantic_residual_corners", runner)
        self.assertIn("retained_corners", runner)
        self.assertIn("HardSoftLocalCustom", runner)
        self.assertIn("retained = '8,10'", runner)
        self.assertIn("$pidPattern = '\\[0*'", runner)


if __name__ == "__main__":
    unittest.main()
