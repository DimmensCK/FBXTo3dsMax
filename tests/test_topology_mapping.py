from __future__ import annotations

import unittest
from unittest import mock

import f2m_topology_transfer as topology


class TopologyMappingTests(unittest.TestCase):
    def build(self, fbx_faces, max_faces, vertex_count=20):
        def counts(_node):
            faces = fbx_faces if _node == "fbx" else max_faces
            edges = {
                tuple(sorted((face[index], face[(index + 1) % len(face)])))
                for face in faces
                for index in range(len(face))
            }
            return vertex_count, len(edges), len(faces)

        def faces(_node):
            return tuple(
                tuple(face)
                for face in (fbx_faces if _node == "fbx" else max_faces)
            )

        with (
            mock.patch.object(topology, "mesh_counts", side_effect=counts),
            mock.patch.object(topology, "_base_topology_faces", side_effect=faces),
            mock.patch.object(
                topology,
                "_evaluated_triangle_difference_count",
                return_value=0,
            ),
        ):
            return topology.build_topology_map("fbx", "max")

    def test_user_face_995_cyclic_start_is_accepted_and_remapped(self):
        mapping = self.build(
            [(942, 586, 937, 941)],
            [(941, 942, 586, 937)],
            vertex_count=1000,
        )
        self.assertEqual(mapping.fbx_face_for_max_face, (0,))
        self.assertEqual(mapping.fbx_corner_for_max_corner, ((3, 0, 1, 2),))
        self.assertEqual(mapping.cyclic_corner_face_count, 1)
        self.assertEqual(
            topology.remap_per_corner_values(
                [["角942", "角586", "角937", "角941"]],
                mapping,
            ),
            [["角941", "角942", "角586", "角937"]],
        )

    def test_unique_oriented_face_reorder_is_accepted(self):
        mapping = self.build(
            [(1, 2, 3), (4, 5, 6, 7)],
            [(7, 4, 5, 6), (1, 2, 3)],
        )
        self.assertEqual(mapping.fbx_face_for_max_face, (1, 0))
        self.assertEqual(
            mapping.fbx_corner_for_max_corner,
            ((3, 0, 1, 2), (0, 1, 2)),
        )
        self.assertEqual(mapping.reordered_face_count, 2)
        self.assertEqual(
            topology.remap_per_face_values(["三角面", "四边面"], mapping),
            ["四边面", "三角面"],
        )

    def test_reversed_winding_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "绕序反向"):
            self.build([(1, 2, 3, 4)], [(1, 4, 3, 2)])

    def test_changed_vertex_id_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "连接关系或顶点 ID"):
            self.build([(1, 2, 3, 4)], [(1, 2, 3, 5)])

    def test_duplicate_oriented_face_key_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "重复的同向多边面键"):
            self.build(
                [(1, 2, 3), (2, 3, 1)],
                [(1, 2, 3), (2, 3, 1)],
            )

    def test_per_face_and_corner_lengths_fail_closed(self):
        mapping = self.build([(1, 2, 3)], [(2, 3, 1)])
        with self.assertRaisesRegex(ValueError, "逐面数据数量"):
            topology.remap_per_face_values([], mapping)
        with self.assertRaisesRegex(ValueError, "面角数据面数"):
            topology.remap_per_corner_values([], mapping)
        with self.assertRaisesRegex(ValueError, "角数据数量"):
            topology.remap_per_corner_values([["a", "b"]], mapping)

    def test_installed_selfcheck_entry(self):
        detail = topology.run_topology_mapping_selfcheck()
        self.assertIn("同向循环换起点", detail)
        self.assertIn("反向绕序阻断", detail)


if __name__ == "__main__":
    unittest.main()
