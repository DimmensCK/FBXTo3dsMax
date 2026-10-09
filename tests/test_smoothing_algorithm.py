# -*- coding: utf-8 -*-
"""Unit tests for the standalone FBX-to-Max smoothing conversion."""

from __future__ import annotations

import math
import unittest
from unittest import mock
from typing import Dict, Iterable, List, Sequence, Tuple

# Resolve runtime modules from the source distribution without a global PYTHONPATH.
import sys as _f2m_test_sys
from pathlib import Path as _F2MTestPath
_f2m_test_root = _F2MTestPath(__file__).resolve().parents[1]
_f2m_test_sys.path.insert(0, str(_f2m_test_root / "contents" if (_f2m_test_root / "contents").is_dir() else _f2m_test_root))

import f2m_smoothing as smoothing_impl
from f2m_smoothing import (
    NonManifoldTopologyError,
    SmoothingInputError,
    SmoothingValidationError,
    TOOL_VERSION,
    UnrepresentableSmoothingError,
    compute_smoothing_assignment,
    compute_smoothing_masks,
    mask_to_signed32,
    signed32_to_mask,
    validate_smoothing_masks,
)


Face = Tuple[int, ...]


class _CornerUnion:
    def __init__(self, faces: Sequence[Face]) -> None:
        self.parent: Dict[Tuple[int, int], Tuple[int, int]] = {}
        for face_index, face in enumerate(faces):
            for corner_index, _ in enumerate(face):
                key = (face_index, corner_index)
                self.parent[key] = key

    def find(self, key: Tuple[int, int]) -> Tuple[int, int]:
        parent = self.parent[key]
        if parent != key:
            self.parent[key] = self.find(parent)
        return self.parent[key]

    def union(self, first: Tuple[int, int], second: Tuple[int, int]) -> None:
        root_a = self.find(first)
        root_b = self.find(second)
        if root_a != root_b:
            self.parent[max(root_a, root_b)] = min(root_a, root_b)


def _corner_for_vertex(face: Face, vertex: int) -> int:
    return face.index(vertex)


def _fan_ids_from_soft_face_pairs(
    faces: Sequence[Face],
    soft_face_pairs: Iterable[Tuple[int, int]],
) -> List[List[int]]:
    """Build exact corner fan IDs by unifying both ends of selected shared edges."""

    union = _CornerUnion(faces)
    for face_a, face_b in soft_face_pairs:
        shared = sorted(set(faces[face_a]).intersection(faces[face_b]))
        if len(shared) != 2:
            raise AssertionError(
                "Soft face pair {}-{} does not share one edge.".format(
                    face_a, face_b
                )
            )
        for vertex in shared:
            union.union(
                (face_a, _corner_for_vertex(faces[face_a], vertex)),
                (face_b, _corner_for_vertex(faces[face_b], vertex)),
            )

    roots = sorted({union.find(key) for key in union.parent})
    root_to_id = {root: index for index, root in enumerate(roots)}
    result: List[List[int]] = []
    for face_index, face in enumerate(faces):
        result.append(
            [
                root_to_id[union.find((face_index, corner_index))]
                for corner_index, _ in enumerate(face)
            ]
        )
    return result


def _wheel(pair_count: int) -> Tuple[List[Face], List[List[int]]]:
    """Create 2*N triangles with N isolated two-face smooth fans at the center."""

    face_count = pair_count * 2
    faces: List[Face] = []
    for face_index in range(face_count):
        outer_a = face_index + 1
        outer_b = ((face_index + 1) % face_count) + 1
        faces.append((0, outer_a, outer_b))
    soft_pairs = [(index, index + 1) for index in range(0, face_count, 2)]
    return faces, _fan_ids_from_soft_face_pairs(faces, soft_pairs)


class SmoothingAlgorithmTests(unittest.TestCase):
    def test_version_is_v1320(self) -> None:
        self.assertEqual(TOOL_VERSION, "1.4.25")

    def test_two_triangles_all_soft_from_corner_normals(self) -> None:
        faces = [(0, 1, 2), (0, 2, 3)]
        normals = [
            [(0.0, 0.0, 1.0)] * 3,
            [(0.0, 0.0, 1.0)] * 3,
        ]

        assignment = compute_smoothing_assignment(
            faces,
            corner_normals=normals,
        )

        self.assertEqual(assignment.masks, (1, 1))
        self.assertEqual(assignment.group_count, 1)
        self.assertEqual(assignment.validation.soft_edge_count, 1)
        self.assertEqual(assignment.validation.hard_edge_count, 0)

    def test_distinct_normal_ids_with_equal_vectors_are_soft_by_vector_partition(
        self,
    ) -> None:
        faces = [(0, 1, 2), (0, 2, 3)]
        # Autodesk/Edit Normals is allowed to assign a different storage ID to
        # every face corner even when the authored vectors are identical.
        normal_ids = [[101, 102, 103], [201, 202, 203]]
        self.assertEqual(
            len({normal_id for row in normal_ids for normal_id in row}),
            6,
        )
        normals = [
            [(0.0, 0.0, 1.0)] * 3,
            # Different magnitudes also prove that the solver normalizes before
            # comparing directions.
            [(0.0, 0.0, 10.0)] * 3,
        ]

        assignment = compute_smoothing_assignment(
            faces,
            corner_normals=normals,
            normal_angle_tolerance_degrees=0.01,
        )

        self.assertEqual(assignment.masks, (1, 1))
        self.assertEqual(assignment.group_count, 1)
        self.assertEqual(assignment.validation.soft_edge_count, 1)
        self.assertEqual(assignment.validation.hard_edge_count, 0)

    def test_distinct_normal_ids_with_different_vectors_are_hard_by_vector_partition(
        self,
    ) -> None:
        faces = [(0, 1, 2), (0, 2, 3)]
        normal_ids = [[101, 102, 103], [201, 202, 203]]
        self.assertEqual(
            len({normal_id for row in normal_ids for normal_id in row}),
            6,
        )
        normals = [
            [(0.0, 0.0, 1.0)] * 3,
            [(0.0, 1.0, 0.0)] * 3,
        ]

        assignment = compute_smoothing_assignment(
            faces,
            corner_normals=normals,
            normal_angle_tolerance_degrees=0.01,
        )

        self.assertEqual(assignment.masks, (0, 0))
        self.assertEqual(assignment.group_count, 0)
        self.assertEqual(assignment.validation.soft_edge_count, 0)
        self.assertEqual(assignment.validation.hard_edge_count, 1)

    def test_raw_distinct_normal_ids_must_not_override_equal_vector_partition(
        self,
    ) -> None:
        faces = [(0, 1, 2), (0, 2, 3)]
        normal_ids = [[101, 102, 103], [201, 202, 203]]
        normals = [
            [(0.0, 0.0, 1.0)] * 3,
            [(0.0, 0.0, 1.0)] * 3,
        ]

        # Passing both inputs asks the solver to prove that their partitions
        # are identical. Raw Edit Normals IDs are storage identities, not that
        # semantic partition, so this must fail closed instead of silently
        # turning equal vectors into a hard edge.
        with self.assertRaises(SmoothingInputError):
            compute_smoothing_assignment(
                faces,
                corner_normals=normals,
                corner_fan_ids=normal_ids,
                normal_angle_tolerance_degrees=0.01,
            )

    def test_corner_normal_angle_tolerance_separates_numeric_drift_from_hard_edge(
        self,
    ) -> None:
        faces = [(0, 1, 2), (0, 2, 3)]

        def tilted(degrees: float) -> Tuple[float, float, float]:
            radians = math.radians(degrees)
            return math.sin(radians), 0.0, math.cos(radians)

        within_tolerance = compute_smoothing_assignment(
            faces,
            corner_normals=[
                [(0.0, 0.0, 1.0)] * 3,
                [tilted(0.005)] * 3,
            ],
            normal_angle_tolerance_degrees=0.01,
        )
        outside_tolerance = compute_smoothing_assignment(
            faces,
            corner_normals=[
                [(0.0, 0.0, 1.0)] * 3,
                [tilted(0.02)] * 3,
            ],
            normal_angle_tolerance_degrees=0.01,
        )

        self.assertEqual(within_tolerance.validation.soft_edge_count, 1)
        self.assertEqual(within_tolerance.validation.hard_edge_count, 0)
        self.assertEqual(outside_tolerance.validation.soft_edge_count, 0)
        self.assertEqual(outside_tolerance.validation.hard_edge_count, 1)

    def test_two_triangles_all_hard(self) -> None:
        faces = [(0, 1, 2), (0, 2, 3)]
        fan_ids = [[0, 1, 2], [3, 4, 5]]

        assignment = compute_smoothing_assignment(
            faces,
            corner_fan_ids=fan_ids,
        )

        self.assertEqual(assignment.masks, (0, 0))
        self.assertEqual(assignment.group_count, 0)
        self.assertEqual(assignment.validation.soft_edge_count, 0)
        self.assertEqual(assignment.validation.hard_edge_count, 1)

    def test_two_quads_preserve_one_soft_shared_edge(self) -> None:
        faces = [(0, 1, 2, 3), (1, 4, 5, 2)]
        fan_ids = _fan_ids_from_soft_face_pairs(faces, [(0, 1)])

        assignment = compute_smoothing_assignment(
            faces,
            corner_fan_ids=fan_ids,
        )

        self.assertEqual(assignment.masks, (1, 1))
        self.assertEqual(assignment.group_count, 1)
        self.assertEqual(assignment.validation.soft_edge_count, 1)

    def test_quad_and_pentagon_use_their_closing_edges(self) -> None:
        # The shared edge is the closing edge of both polygons; this catches
        # accidental triangle-only modulo arithmetic in edge enumeration.
        faces = [(0, 1, 2, 3), (3, 6, 5, 4, 0)]
        fan_ids = _fan_ids_from_soft_face_pairs(faces, [(0, 1)])

        assignment = compute_smoothing_assignment(
            faces,
            corner_fan_ids=fan_ids,
        )

        self.assertEqual(assignment.masks, (1, 1))
        self.assertEqual(assignment.validation.soft_edge_count, 1)

    def test_disconnected_soft_regions_use_separate_groups_while_available(
        self,
    ) -> None:
        faces = [
            (0, 1, 2),
            (0, 2, 3),
            (10, 11, 12),
            (10, 12, 13),
        ]
        fan_ids = _fan_ids_from_soft_face_pairs(faces, [(0, 1), (2, 3)])

        assignment = compute_smoothing_assignment(
            faces,
            corner_fan_ids=fan_ids,
        )

        self.assertEqual(assignment.masks, (1, 1, 2, 2))
        self.assertEqual(assignment.group_count, 2)
        self.assertEqual(assignment.strategy, "coherent_soft_regions")

    def test_more_than_32_disconnected_regions_reuse_only_after_budget(self) -> None:
        faces: List[Face] = []
        soft_pairs: List[Tuple[int, int]] = []
        for region_index in range(40):
            vertex = region_index * 10
            first_face = len(faces)
            faces.extend(
                [
                    (vertex, vertex + 1, vertex + 2),
                    (vertex, vertex + 2, vertex + 3),
                ]
            )
            soft_pairs.append((first_face, first_face + 1))
        fan_ids = _fan_ids_from_soft_face_pairs(faces, soft_pairs)

        assignment = compute_smoothing_assignment(
            faces,
            corner_fan_ids=fan_ids,
        )

        self.assertEqual(assignment.group_count, 32)
        self.assertEqual(assignment.strategy, "coherent_soft_regions")
        for first_face, second_face in soft_pairs:
            self.assertEqual(
                assignment.masks[first_face],
                assignment.masks[second_face],
            )
        self.assertGreater(len(set(assignment.masks)), 1)
        validate_smoothing_masks(
            faces,
            assignment.masks,
            corner_fan_ids=fan_ids,
        )

    def test_vertex_fan_conflict_prevents_indirect_leakage(self) -> None:
        # Requirements 0-1 and 3-4 are not separated by a direct hard edge.
        # They do meet at vertex 0 in different normal fans, so reusing a bit
        # would incorrectly merge the two source normals.
        face_count = 6
        faces = [
            (0, index + 1, ((index + 1) % face_count) + 1)
            for index in range(face_count)
        ]
        fan_ids = _fan_ids_from_soft_face_pairs(faces, [(0, 1), (3, 4)])

        assignment = compute_smoothing_assignment(
            faces,
            corner_fan_ids=fan_ids,
        )

        self.assertEqual(assignment.group_count, 2)
        self.assertNotEqual(assignment.masks[0], assignment.masks[3])
        self.assertEqual(assignment.masks[0] & assignment.masks[3], 0)
        validate_smoothing_masks(
            faces,
            assignment.masks,
            corner_fan_ids=fan_ids,
        )

        with self.assertRaises(SmoothingValidationError):
            validate_smoothing_masks(
                faces,
                (1, 1, 0, 1, 1, 0),
                corner_fan_ids=fan_ids,
            )

    def test_k33_fails_closed(self) -> None:
        faces, fan_ids = _wheel(33)

        with self.assertRaises(UnrepresentableSmoothingError):
            compute_smoothing_assignment(
                faces,
                corner_fan_ids=fan_ids,
            )

    def test_group_32_and_signed_conversion(self) -> None:
        faces, fan_ids = _wheel(32)
        assignment = compute_smoothing_assignment(
            faces,
            corner_fan_ids=fan_ids,
        )

        self.assertEqual(assignment.group_count, 32)
        self.assertTrue(any(mask & 0x80000000 for mask in assignment.masks))
        self.assertIn(-0x80000000, assignment.maxscript_masks)
        self.assertEqual(mask_to_signed32(0x80000000), -0x80000000)
        self.assertEqual(signed32_to_mask(-0x80000000), 0x80000000)
        self.assertEqual(mask_to_signed32(0xFFFFFFFF), -1)
        self.assertEqual(signed32_to_mask(-1), 0xFFFFFFFF)

    def test_idempotent_and_deterministic(self) -> None:
        faces, fan_ids = _wheel(8)

        first = compute_smoothing_masks(faces, corner_fan_ids=fan_ids)
        second = compute_smoothing_masks(faces, corner_fan_ids=fan_ids)

        self.assertEqual(first, second)
        validate_smoothing_masks(
            faces,
            first,
            corner_fan_ids=fan_ids,
        )

    def test_large_uniform_grid_uses_linear_no_conflict_fast_path(self) -> None:
        # A large fully smooth surface creates many soft-edge requirements but
        # no requirement conflicts.  It must reuse one group directly instead
        # of entering either graph-coloring scan.  The mocks make this a
        # deterministic complexity guard rather than a timing-sensitive test.
        side = 100
        faces: List[Face] = []
        fan_ids: List[List[int]] = []
        for row in range(side):
            for column in range(side):
                first = row * (side + 1) + column
                face = (
                    first,
                    first + 1,
                    first + side + 2,
                    first + side + 1,
                )
                faces.append(face)
                fan_ids.append(list(face))

        with mock.patch.object(
            smoothing_impl,
            "_greedy_dsatur",
            side_effect=AssertionError("无冲突网格不应进入 DSATUR"),
        ), mock.patch.object(
            smoothing_impl,
            "_greedy_maximal_clique",
            side_effect=AssertionError("无冲突网格不应搜索最大团"),
        ):
            assignment = compute_smoothing_assignment(
                faces,
                corner_fan_ids=fan_ids,
            )

        self.assertEqual(len(assignment.masks), side * side)
        self.assertEqual(assignment.group_count, 1)
        self.assertEqual(set(assignment.masks), {1})

    def test_bounded_backtracking_recovers_from_greedy_overcolor(self) -> None:
        # This graph is 3-colorable, while the deterministic greedy DSATUR pass
        # uses four colors.  It therefore exercises the bounded exact fallback.
        edges = [
            (0, 2),
            (0, 4),
            (0, 5),
            (1, 3),
            (1, 4),
            (1, 6),
            (2, 4),
            (3, 5),
            (3, 6),
            (5, 6),
        ]
        mutable_adjacency = [set() for _ in range(7)]
        for node_a, node_b in edges:
            mutable_adjacency[node_a].add(node_b)
            mutable_adjacency[node_b].add(node_a)
        adjacency = tuple(frozenset(neighbors) for neighbors in mutable_adjacency)

        greedy = smoothing_impl._greedy_dsatur(adjacency)
        recovered = smoothing_impl._color_conflict_graph(
            adjacency,
            max_colors=3,
            backtrack_limit=10_000,
        )

        self.assertEqual(max(greedy) + 1, 4)
        self.assertEqual(max(recovered) + 1, 3)
        for node_a, node_b in edges:
            self.assertNotEqual(recovered[node_a], recovered[node_b])

    def test_non_manifold_edge_fails_closed(self) -> None:
        faces = [
            (0, 1, 2),
            (1, 0, 3),
            (0, 1, 4),
        ]
        fan_ids = [[0, 1, 2], [3, 4, 5], [6, 7, 8]]

        with self.assertRaises(NonManifoldTopologyError):
            compute_smoothing_masks(faces, corner_fan_ids=fan_ids)

    def test_bowtie_vertex_fails_closed(self) -> None:
        faces = [(0, 1, 2), (0, 3, 4)]
        fan_ids = [[0, 1, 2], [3, 4, 5]]

        with self.assertRaises(NonManifoldTopologyError):
            compute_smoothing_masks(faces, corner_fan_ids=fan_ids)

    def test_one_endpoint_only_soft_edge_fails_closed(self) -> None:
        faces = [(0, 1, 2), (0, 2, 3)]
        # The shared edge is continuous at vertex 0 but split at vertex 2.
        fan_ids = [[10, 11, 12], [10, 13, 14]]

        with self.assertRaises(UnrepresentableSmoothingError):
            compute_smoothing_masks(faces, corner_fan_ids=fan_ids)


if __name__ == "__main__":
    unittest.main()
