from __future__ import annotations

import unittest
from unittest import mock

# Resolve runtime modules from the source distribution without a global PYTHONPATH.
import sys as _f2m_test_sys
from pathlib import Path as _F2MTestPath
_f2m_test_root = _F2MTestPath(__file__).resolve().parents[1]
_f2m_test_sys.path.insert(0, str(_f2m_test_root / "contents" if (_f2m_test_root / "contents").is_dir() else _f2m_test_root))

import f2m_topology_transfer as topology


class _ArrayOnlyRuntime:
    @staticmethod
    def Array(*values):
        return tuple(values)


class ExactNormalsFlatSnapshotV1320Tests(unittest.TestCase):
    def test_python_normal_map_has_one_flat_corner_array(self):
        mapping = topology.TopologyMap(
            fbx_face_for_max_face=(1, 0),
            fbx_corner_for_max_corner=((3, 0, 1, 2), (2, 0, 1)),
            exact_face_count=0,
            cyclic_corner_face_count=2,
            reordered_face_count=2,
        )
        with mock.patch.object(topology, "rt", _ArrayOnlyRuntime()):
            face_map, starts, corners = (
                topology._maxscript_topology_flat_arrays(mapping)
            )

        self.assertEqual(face_map, (2, 1))
        self.assertEqual(starts, (1, 5, 8))
        self.assertEqual(corners, (4, 1, 2, 3, 3, 1, 2))
        self.assertFalse(any(isinstance(value, tuple) for value in corners))

    def test_both_production_paths_use_flat_snapshot_only(self):
        helper = topology.HELPER_SCRIPT
        residual_start = helper.index("fn copyExplicitNormalResiduals")
        exact_start = helper.index("fn copyExplicitNormals", residual_start)
        end = helper.index("fn pointReadbackTolerance", exact_start)
        residual_block = helper[residual_start:exact_start]
        exact_block = helper[exact_start:end]

        self.assertIn("snapshotEditNormalsDataFlat src srcMod", residual_block)
        self.assertIn(
            "baselineData = snapshotEditNormalsDataFlat dst dstMod",
            residual_block,
        )
        self.assertIn(
            "buildEditNormalResidualSnapshotFlat srcData baselineData",
            residual_block,
        )
        self.assertIn("applyEditNormalResidualsFlatFromExact", residual_block)
        self.assertIn("editNormalResidualsFlatMatch", residual_block)
        self.assertNotIn("snapshotEditNormalsData src srcMod", residual_block)
        self.assertNotIn(
            "buildExternalSmoothingBaselineFlat",
            residual_block,
        )
        self.assertNotIn("addModifierWithLocalData", residual_block)
        self.assertNotIn("applyEditNormalsSnapshotFlatDifferential", residual_block)
        self.assertNotIn(
            "snapshotSmoothingBaselineFlatTransient",
            residual_block,
        )
        self.assertNotIn("useDenseExactFallback", residual_block)

        self.assertIn("snapshotEditNormalsDataFlat src srcMod", exact_block)
        self.assertIn("applyEditNormalsSnapshotFlat", exact_block)
        self.assertIn("editNormalsSnapshotFlatMatches", exact_block)
        self.assertNotIn("snapshotEditNormalsData src srcMod", exact_block)

    def test_external_baseline_builder_is_flat_pure_sg_data(self):
        helper = topology.HELPER_SCRIPT
        start = helper.index("fn buildExternalSmoothingBaselineFlat")
        end = helper.index("fn editNormalsSnapshotFlatMatches", start)
        block = helper[start:end]

        for token in (
            "faceDegrees",
            "fanIds",
            "cornerNormalValues",
            "normalValues",
            "faceStarts",
            "for fanId in fanIds collect (fanId as integer)",
        ):
            self.assertIn(token, block)
        self.assertIn(
            "normalAngleDegrees existingNormal inputNormal > 0.001",
            block,
        )
        self.assertIn("#{}", block)
        self.assertNotIn("Edit_Normals()", block)
        self.assertNotIn("addModifier", block)
        self.assertNotIn("RebuildNormals", block)
        self.assertNotIn("copy fanIds", block)

    def test_external_baseline_angle_helper_precedes_its_maxscript_callsite(self):
        helper = topology.HELPER_SCRIPT
        angle_helper = helper.index("fn normalAngleDegrees")
        baseline_builder = helper.index(
            "fn buildExternalSmoothingBaselineFlat"
        )

        self.assertLess(angle_helper, baseline_builder)

    def test_flat_snapshot_contract_avoids_nested_rows_and_point3_storage(self):
        helper = topology.HELPER_SCRIPT
        start = helper.index("fn snapshotEditNormalsDataFlat")
        end = helper.index("fn transformEditNormalsSnapshotFlat", start)
        block = helper[start:end]

        self.assertIn("normalValues", block)
        self.assertIn("explicitNormals", block)
        self.assertIn("authoredNormals", block)
        self.assertIn("faceCornerStarts", block)
        self.assertIn("cornerNormalIds", block)
        self.assertIn("specifiedCorners", block)
        self.assertNotIn("normalRows", block)
        self.assertNotIn("faceRows", block)
        self.assertNotIn("cornerRows", block)
        self.assertNotRegex(
            block,
            r"(?m)^\s*append normalValues normalValue\s*$",
        )

    def test_exact_apply_clears_make_explicit_smooth_fan_promotion(self):
        helper = topology.HELPER_SCRIPT
        start = helper.index("fn applyEditNormalsSnapshotFlat")
        end = helper.index("fn blockingNormalModifierNames", start)
        block = helper[start:end]

        make_explicit = block.index(
            "dstMod.MakeExplicit selection:explicitNormals node:dstNode"
        )
        post_clear = block.index(
            "not srcData[4][normalIndex] do",
            make_explicit,
        )
        authored_write = block.index(
            "srcData[5][normalIndex] do",
            post_clear,
        )
        self.assertLess(make_explicit, post_clear)
        self.assertLess(post_clear, authored_write)
        self.assertIn(
            "dstMod.SetNormalExplicit normalIndex explicit:false node:dstNode",
            block[post_clear:authored_write],
        )

    def test_exact_apply_replays_corner_states_after_normal_operations(self):
        helper = topology.HELPER_SCRIPT
        start = helper.index("fn applyEditNormalsSnapshotFlat")
        end = helper.index("fn blockingNormalModifierNames", start)
        block = helper[start:end]

        make_explicit = block.index(
            "dstMod.MakeExplicit selection:explicitNormals node:dstNode"
        )
        authored_write = block.index(
            "dstMod.SetNormal normalIndex &normalValue node:dstNode",
            make_explicit,
        )
        replay_comment = block.index(
            "Replay every per-corner state",
            authored_write,
        )
        replay_specified = block.index(
            "dstMod.SetFaceNormalSpecified faceIndex cornerIndex "
            "specified:(srcData[8][flatCornerIndex]) node:dstNode",
            replay_comment,
        )
        update = block.index("update dstNode", replay_specified)

        self.assertLess(make_explicit, authored_write)
        self.assertLess(authored_write, replay_specified)
        self.assertLess(replay_specified, update)
        self.assertEqual(
            block.count(
                "dstMod.SetFaceNormalSpecified faceIndex cornerIndex "
                "specified:(srcData[8][flatCornerIndex]) node:dstNode"
            ),
            2,
        )

    def test_no_forced_full_gc_or_undo_clear_was_added(self):
        helper_lower = topology.HELPER_SCRIPT.lower()
        self.assertNotIn("gc()", helper_lower)
        self.assertNotIn("clearundobuffer", helper_lower)


if __name__ == "__main__":
    unittest.main()
