from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "f2m_skin_replace.py"


class Mode2BindingBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = ENGINE.read_text(encoding="utf-8-sig")
        cls.tree = ast.parse(cls.source, filename=str(ENGINE), feature_version=(3, 9))
        cls.replace_block = cls.source[
            cls.source.index("def replace_with_source_skin(") :
            cls.source.index("def should_replace_after_fail(")
        ]
        cls.copy_helper = cls.source[
            cls.source.index("fn copySkinModifierToNode") :
            cls.source.index("fn createFreshSkinAtIndex")
        ]

    def test_skin_local_data_copy_is_exact_and_fail_closed(self) -> None:
        self.assertIn(
            "fn copySkinModifierToNode sourceNode sourceSkin targetNode stackIndex",
            self.copy_helper,
        )
        self.assertIn(
            "addModifierWithLocalData targetNode copied sourceNode sourceSkin before:requestedIndex",
            self.copy_helper,
        )
        self.assertIn("(modifierIndex targetNode copied) != requestedIndex", self.copy_helper)
        self.assertNotIn("addModifier targetNode copied", self.copy_helper)

    def test_replace_path_copies_max_skin_instead_of_rebuilding_fbx_bind_state(self) -> None:
        self.assertIn("target_modifier_state = source_skin_modifier_state", self.replace_block)
        self.assertIn("target_bone_states = source_skin_bone_states", self.replace_block)
        self.assertIn("expected_scene_bones = tuple", self.replace_block)
        self.assertIn("copied_skin = copy_target_skin_to_node", self.replace_block)
        self.assertNotIn("create_fbx_authority_skin(", self.replace_block)
        self.assertNotIn("_set_skin_bone_states(", self.replace_block)

    def test_fbx_only_supplies_vertex_state_and_global_dq(self) -> None:
        self.assertIn("rows = source_skin_weight_rows", self.replace_block)
        self.assertIn("vertex_states = source_skin_vertex_states", self.replace_block)
        self.assertIn("enable_dq=source_modifier_state.enable_dq", self.replace_block)
        self.assertIn("property_values=target_modifier_state.property_values", self.replace_block)
        self.assertIn("copied_modifier_state = source_skin_modifier_state", self.replace_block)
        self.assertIn("mesh_bind_tm=copied_modifier_state.mesh_bind_tm", self.replace_block)

    def test_replace_path_preserves_candidate_adapted_mesh_bind_without_rewrite(self) -> None:
        self.assertIn("write_mesh_bind_tm=False", self.replace_block)
        self.assertEqual(self.source.count("write_mesh_bind_tm=False"), 1)
        apply_block = self.source[
            self.source.index("def apply_weight_rows(") :
            self.source.index("def _set_node_name_exact(")
        ]
        self.assertIn("write_mesh_bind_tm: bool = True", apply_block)
        setter_block = self.source[
            self.source.index("def _set_skin_modifier_state(") :
            self.source.index("def _set_skin_bone_states(")
        ]
        self.assertIn("state.mesh_bind_tm and write_mesh_bind_tm", setter_block)

        create_block = self.source[
            self.source.index("def create_fbx_authority_skin(") :
            self.source.index("def _read_vertex_weight_map(")
        ]
        self.assertIn("_set_skin_modifier_state(fresh_skin, modifier_state, dst_node)", create_block)
        self.assertNotIn("write_mesh_bind_tm=False", create_block)

    def test_scene_bones_and_bind_state_are_reverified_through_commit(self) -> None:
        commit = self.source[
            self.source.index("def commit_replacement(") :
            self.source.index("def replace_with_source_skin(")
        ]
        self.assertGreaterEqual(commit.count("verify_scene_bound_skin("), 4)
        self.assertIn("expected_scene_bones", commit)
        self.assertIn("expected_bone_states", commit)
        self.assertIn("actual_handle != expected_handle", self.source)

    def test_weight_writer_remains_single_per_vertex_path(self) -> None:
        apply_block = self.source[
            self.source.index("def apply_weight_rows(") :
            self.source.index("def _set_node_name_exact(")
        ]
        self.assertIn("_apply_weight_rows_per_vertex", apply_block)
        self.assertNotIn("_apply_weight_rows_by_bone", apply_block)
        self.assertIn('LAST_WEIGHT_WRITE_METHOD = "逐顶点权威写入"', apply_block)


if __name__ == "__main__":
    unittest.main()
