# -*- coding: utf-8 -*-
"""Deterministic face-corner-normal to 3ds Max smoothing-group conversion.

This v1.3.24 module is deliberately independent from pymxs.  It operates on an
evaluated polygon mesh and returns one unsigned 32-bit smoothing mask per
face.  Conversion is fail-closed: malformed/non-manifold topology, ambiguous
normal data, an exhausted bounded coloring search, or an unrepresentable set of
constraints raises a typed exception instead of returning approximate masks.

The construction treats every desired soft edge as a requirement.  A color of
the requirement-conflict graph is a 3ds Max smoothing-group bit.  Requirement
nodes conflict when reusing a bit would smooth a desired hard edge or merge two
different source normal fans at a shared vertex.  Deterministic DSATUR supplies
the coloring, with bounded backtracking if the greedy pass exceeds the group
limit.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Dict, Hashable, Iterable, List, Mapping, Optional, Sequence, Set, Tuple


TOOL_VERSION = "1.3.24"
MAX_SMOOTHING_GROUPS = 32
UINT32_MASK = 0xFFFFFFFF
INT32_SIGN_BIT = 0x80000000
INT32_MODULUS = 0x100000000

Face = Tuple[int, ...]
Edge = Tuple[int, int]
CornerKey = Tuple[int, int]
Vector3 = Tuple[float, float, float]


class SmoothingError(Exception):
    """Base exception for smoothing conversion failures."""

    def __str__(self) -> str:
        return "光滑组转换失败。"


class SmoothingInputError(SmoothingError, ValueError):
    """Input data is incomplete, malformed, or internally inconsistent."""

    def __str__(self) -> str:
        return "光滑组输入数据不完整、格式错误或内部不一致。"


class NonManifoldTopologyError(SmoothingInputError):
    """The input is not a supported consistently wound two-manifold mesh."""

    def __str__(self) -> str:
        return "网格包含不受支持的非流形、蝴蝶结顶点或不一致绕序。"


class UnrepresentableSmoothingError(SmoothingError):
    """The requested corner-normal partition cannot be represented safely."""

    def __str__(self) -> str:
        return "当前软硬边约束无法用 3ds Max 光滑组安全且无损地表达。"


class ColoringSearchLimitError(UnrepresentableSmoothingError):
    """The bounded exact coloring fallback exhausted its search budget."""

    def __str__(self) -> str:
        return "光滑组精确分配搜索达到安全上限，已停止写入。"


class SmoothingValidationError(SmoothingError):
    """Generated or supplied masks violate one or more source constraints."""

    def __str__(self) -> str:
        return "生成的光滑组没有通过软硬边或法线扇区验证。"


@dataclass(frozen=True)
class EdgeConstraint:
    """A two-face edge and its desired Max smoothing state."""

    edge: Edge
    faces: Tuple[int, int]
    soft: bool


@dataclass(frozen=True)
class ValidationReport:
    """Summary of a successful strict validation pass."""

    face_count: int
    vertex_count: int
    soft_edge_count: int
    hard_edge_count: int
    smoothing_group_count: int


@dataclass(frozen=True)
class SmoothingAssignment:
    """A validated smoothing-group assignment."""

    masks: Tuple[int, ...]
    requirement_colors: Tuple[int, ...]
    group_count: int
    soft_edges: Tuple[EdgeConstraint, ...]
    hard_edges: Tuple[EdgeConstraint, ...]
    validation: ValidationReport
    strategy: str

    @property
    def maxscript_masks(self) -> Tuple[int, ...]:
        """Return the masks as signed int32 values expected by MAXScript."""

        return tuple(mask_to_signed32(mask) for mask in self.masks)


@dataclass(frozen=True)
class _Topology:
    faces: Tuple[Face, ...]
    edge_uses: Mapping[Edge, Tuple[Tuple[int, int, int], ...]]
    vertex_corners: Mapping[int, Tuple[CornerKey, ...]]
    face_corner_by_vertex: Tuple[Mapping[int, int], ...]


@dataclass(frozen=True)
class _SourceConstraints:
    tokens: Mapping[CornerKey, Hashable]
    soft_edges: Tuple[EdgeConstraint, ...]
    hard_edges: Tuple[EdgeConstraint, ...]


class _UnionFind:
    def __init__(self, items: Iterable[Hashable]) -> None:
        self.parent: Dict[Hashable, Hashable] = {}
        self.rank: Dict[Hashable, int] = {}
        for item in items:
            self.parent[item] = item
            self.rank[item] = 0

    def find(self, item: Hashable) -> Hashable:
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, first: Hashable, second: Hashable) -> None:
        root_a = self.find(first)
        root_b = self.find(second)
        if root_a == root_b:
            return
        rank_a = self.rank[root_a]
        rank_b = self.rank[root_b]
        if rank_a < rank_b:
            root_a, root_b = root_b, root_a
            rank_a, rank_b = rank_b, rank_a
        self.parent[root_b] = root_a
        if rank_a == rank_b:
            self.rank[root_a] += 1


def mask_to_signed32(mask: int) -> int:
    """Convert an unsigned smoothing mask to MAXScript's signed int32 form."""

    if isinstance(mask, bool) or not isinstance(mask, int):
        raise SmoothingInputError("A smoothing mask must be an integer.")
    if mask < 0 or mask > UINT32_MASK:
        raise SmoothingInputError(
            "Unsigned smoothing mask is outside the 32-bit range: {!r}".format(mask)
        )
    return mask - INT32_MODULUS if mask & INT32_SIGN_BIT else mask


def signed32_to_mask(value: int) -> int:
    """Convert a MAXScript signed int32 smoothing value to an unsigned mask."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise SmoothingInputError("A MAXScript smoothing value must be an integer.")
    if value < -0x80000000 or value > 0x7FFFFFFF:
        raise SmoothingInputError(
            "Signed smoothing value is outside the int32 range: {!r}".format(value)
        )
    return value + INT32_MODULUS if value < 0 else value


def _popcount(value: int) -> int:
    """Python 3.9-compatible population count (3ds Max 2023 embeds 3.9)."""

    return bin(value & UINT32_MASK).count("1")


def compute_smoothing_masks(
    faces: Sequence[Sequence[int]],
    *,
    corner_normals: Optional[Sequence[Sequence[Sequence[float]]]] = None,
    corner_fan_ids: Optional[Sequence[Sequence[Hashable]]] = None,
    normal_angle_tolerance_degrees: float = 0.1,
    max_groups: int = MAX_SMOOTHING_GROUPS,
    backtrack_limit: int = 250_000,
) -> Tuple[int, ...]:
    """Return one validated unsigned 32-bit smoothing mask per face.

    ``faces`` must describe an evaluated polygon mesh.  Supply face-corner
    normal vectors, exact face-corner fan IDs, or both.  When both are supplied,
    their partitions must agree at every geometric vertex.
    """

    return compute_smoothing_assignment(
        faces,
        corner_normals=corner_normals,
        corner_fan_ids=corner_fan_ids,
        normal_angle_tolerance_degrees=normal_angle_tolerance_degrees,
        max_groups=max_groups,
        backtrack_limit=backtrack_limit,
    ).masks


def compute_smoothing_assignment(
    faces: Sequence[Sequence[int]],
    *,
    corner_normals: Optional[Sequence[Sequence[Sequence[float]]]] = None,
    corner_fan_ids: Optional[Sequence[Sequence[Hashable]]] = None,
    normal_angle_tolerance_degrees: float = 0.1,
    max_groups: int = MAX_SMOOTHING_GROUPS,
    backtrack_limit: int = 250_000,
) -> SmoothingAssignment:
    """Compute, color, and strictly validate a smoothing assignment."""

    _validate_limits(max_groups=max_groups, backtrack_limit=backtrack_limit)
    topology = _build_topology(faces)
    constraints = _build_source_constraints(
        topology,
        corner_normals=corner_normals,
        corner_fan_ids=corner_fan_ids,
        normal_angle_tolerance_degrees=normal_angle_tolerance_degrees,
    )

    coherent = _try_coherent_region_assignment(
        topology,
        constraints,
        max_groups=max_groups,
        backtrack_limit=backtrack_limit,
    )
    if coherent is not None:
        unsigned_masks, requirement_colors, report = coherent
        used_mask = 0
        for mask in unsigned_masks:
            used_mask |= mask
        group_count = _popcount(used_mask)
        strategy = "coherent_soft_regions"
    else:
        # Some valid Max masks require one face to carry several bits.  Keep the
        # original exact requirement-graph solver as a fail-safe for those rare
        # cases, but do not use it as the first choice because its aggressive
        # bit reuse makes group selections needlessly scattered.
        requirements = constraints.soft_edges
        conflicts = _build_requirement_conflicts(topology, constraints, requirements)
        zero_based_colors = _color_conflict_graph(
            conflicts,
            max_colors=max_groups,
            backtrack_limit=backtrack_limit,
        )

        masks = [0] * len(topology.faces)
        for requirement_index, requirement in enumerate(requirements):
            bit_index = zero_based_colors[requirement_index]
            bit_value = 1 << bit_index
            face_a, face_b = requirement.faces
            masks[face_a] |= bit_value
            masks[face_b] |= bit_value

        unsigned_masks = tuple(mask & UINT32_MASK for mask in masks)
        report = _validate_prebuilt(
            topology,
            constraints,
            unsigned_masks,
            max_groups=max_groups,
        )
        requirement_colors = tuple(color + 1 for color in zero_based_colors)
        group_count = len(set(requirement_colors))
        strategy = "edge_requirement_dsatur"

    return SmoothingAssignment(
        masks=unsigned_masks,
        requirement_colors=requirement_colors,
        group_count=group_count,
        soft_edges=constraints.soft_edges,
        hard_edges=constraints.hard_edges,
        validation=report,
        strategy=strategy,
    )


def validate_smoothing_masks(
    faces: Sequence[Sequence[int]],
    masks: Sequence[int],
    *,
    corner_normals: Optional[Sequence[Sequence[Sequence[float]]]] = None,
    corner_fan_ids: Optional[Sequence[Sequence[Hashable]]] = None,
    normal_angle_tolerance_degrees: float = 0.1,
    max_groups: int = MAX_SMOOTHING_GROUPS,
) -> ValidationReport:
    """Strictly validate external masks against edge and vertex-fan constraints."""

    _validate_limits(max_groups=max_groups, backtrack_limit=1)
    topology = _build_topology(faces)
    constraints = _build_source_constraints(
        topology,
        corner_normals=corner_normals,
        corner_fan_ids=corner_fan_ids,
        normal_angle_tolerance_degrees=normal_angle_tolerance_degrees,
    )
    normalized_masks = _normalize_masks(masks, len(topology.faces), max_groups)
    return _validate_prebuilt(
        topology,
        constraints,
        normalized_masks,
        max_groups=max_groups,
    )


def _validate_limits(max_groups: int, backtrack_limit: int) -> None:
    if isinstance(max_groups, bool) or not isinstance(max_groups, int):
        raise SmoothingInputError("max_groups must be an integer.")
    if max_groups < 1 or max_groups > MAX_SMOOTHING_GROUPS:
        raise SmoothingInputError("max_groups must be in the range 1..32.")
    if isinstance(backtrack_limit, bool) or not isinstance(backtrack_limit, int):
        raise SmoothingInputError("backtrack_limit must be an integer.")
    if backtrack_limit < 1:
        raise SmoothingInputError("backtrack_limit must be positive.")


def _build_topology(faces: Sequence[Sequence[int]]) -> _Topology:
    if isinstance(faces, (str, bytes)) or not isinstance(faces, Sequence):
        raise SmoothingInputError("faces must be a sequence of polygon faces.")
    if not faces:
        raise SmoothingInputError("At least one polygon face is required.")

    normalized_faces: List[Face] = []
    edge_uses_mutable: Dict[Edge, List[Tuple[int, int, int]]] = {}
    vertex_corners_mutable: Dict[int, List[CornerKey]] = {}
    face_corner_by_vertex: List[Mapping[int, int]] = []
    canonical_faces: Dict[Tuple[int, ...], int] = {}

    for face_index, raw_face in enumerate(faces):
        if isinstance(raw_face, (str, bytes)) or not isinstance(raw_face, Sequence):
            raise SmoothingInputError("Face {} is not a sequence.".format(face_index))
        if len(raw_face) < 3:
            raise SmoothingInputError(
                "Face {} has {} corners; a polygon needs at least three.".format(
                    face_index, len(raw_face)
                )
            )

        vertices: List[int] = []
        for raw_vertex in raw_face:
            if isinstance(raw_vertex, bool) or not isinstance(raw_vertex, int):
                raise SmoothingInputError(
                    "Face {} contains a non-integer vertex ID.".format(face_index)
                )
            if raw_vertex < 0:
                raise SmoothingInputError(
                    "Face {} contains a negative vertex ID.".format(face_index)
                )
            vertices.append(raw_vertex)

        if len(set(vertices)) != len(vertices):
            raise SmoothingInputError(
                "Face {} is degenerate because it repeats a vertex.".format(face_index)
            )

        face = tuple(vertices)
        canonical = tuple(sorted(face))
        if canonical in canonical_faces:
            raise NonManifoldTopologyError(
                "Faces {} and {} use the same vertex set.".format(
                    canonical_faces[canonical], face_index
                )
            )
        canonical_faces[canonical] = face_index
        normalized_faces.append(face)

        corner_lookup: Dict[int, int] = {}
        for corner_index, vertex_id in enumerate(face):
            corner_lookup[vertex_id] = corner_index
            vertex_corners_mutable.setdefault(vertex_id, []).append(
                (face_index, corner_index)
            )
        face_corner_by_vertex.append(corner_lookup)

        for side in range(len(face)):
            start = face[side]
            end = face[(side + 1) % len(face)]
            edge = (start, end) if start < end else (end, start)
            edge_uses_mutable.setdefault(edge, []).append((face_index, start, end))

    for edge, uses in sorted(edge_uses_mutable.items()):
        if len(uses) > 2:
            raise NonManifoldTopologyError(
                "Edge {} is referenced by {} faces.".format(edge, len(uses))
            )
        if len(uses) == 2:
            _, start_a, end_a = uses[0]
            _, start_b, end_b = uses[1]
            if not (start_a == end_b and end_a == start_b):
                raise NonManifoldTopologyError(
                    "Edge {} has inconsistent adjacent-face winding.".format(edge)
                )

    _reject_bowtie_vertices(vertex_corners_mutable, edge_uses_mutable)

    return _Topology(
        faces=tuple(normalized_faces),
        edge_uses={
            edge: tuple(sorted(uses, key=lambda use: use[0]))
            for edge, uses in edge_uses_mutable.items()
        },
        vertex_corners={
            vertex: tuple(sorted(corners))
            for vertex, corners in vertex_corners_mutable.items()
        },
        face_corner_by_vertex=tuple(face_corner_by_vertex),
    )


def _reject_bowtie_vertices(
    vertex_corners: Mapping[int, Sequence[CornerKey]],
    edge_uses: Mapping[Edge, Sequence[Tuple[int, int, int]]],
) -> None:
    face_links_by_vertex: Dict[int, Dict[int, Set[int]]] = {}
    for vertex, corners in vertex_corners.items():
        faces = {face_index for face_index, _ in corners}
        face_links_by_vertex[vertex] = {face_index: set() for face_index in faces}

    for edge, uses in edge_uses.items():
        if len(uses) != 2:
            continue
        face_a = uses[0][0]
        face_b = uses[1][0]
        for vertex in edge:
            face_links_by_vertex[vertex][face_a].add(face_b)
            face_links_by_vertex[vertex][face_b].add(face_a)

    for vertex, links in sorted(face_links_by_vertex.items()):
        if len(links) <= 1:
            continue
        remaining = set(links)
        component_count = 0
        while remaining:
            component_count += 1
            seed = min(remaining)
            stack = [seed]
            remaining.remove(seed)
            while stack:
                current = stack.pop()
                for neighbor in sorted(links[current]):
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        stack.append(neighbor)
        if component_count > 1:
            raise NonManifoldTopologyError(
                "Vertex {} is a bow-tie/non-manifold vertex with {} face fans.".format(
                    vertex, component_count
                )
            )


def _build_source_constraints(
    topology: _Topology,
    *,
    corner_normals: Optional[Sequence[Sequence[Sequence[float]]]],
    corner_fan_ids: Optional[Sequence[Sequence[Hashable]]],
    normal_angle_tolerance_degrees: float,
) -> _SourceConstraints:
    if corner_normals is None and corner_fan_ids is None:
        raise SmoothingInputError(
            "Supply corner_normals, corner_fan_ids, or both."
        )

    normal_tokens: Optional[Mapping[CornerKey, Hashable]] = None
    fan_tokens: Optional[Mapping[CornerKey, Hashable]] = None
    if corner_normals is not None:
        normal_tokens = _tokens_from_normals(
            topology,
            corner_normals,
            normal_angle_tolerance_degrees,
        )
    if corner_fan_ids is not None:
        fan_tokens = _tokens_from_fan_ids(topology, corner_fan_ids)

    if normal_tokens is not None and fan_tokens is not None:
        _require_matching_partitions(topology, normal_tokens, fan_tokens)
        tokens = fan_tokens
    else:
        tokens = normal_tokens if normal_tokens is not None else fan_tokens
    assert tokens is not None

    soft_edges: List[EdgeConstraint] = []
    hard_edges: List[EdgeConstraint] = []
    for edge, uses in sorted(topology.edge_uses.items()):
        if len(uses) != 2:
            continue
        face_a = uses[0][0]
        face_b = uses[1][0]
        vertex_a, vertex_b = edge
        corner_a0 = topology.face_corner_by_vertex[face_a][vertex_a]
        corner_b0 = topology.face_corner_by_vertex[face_b][vertex_a]
        corner_a1 = topology.face_corner_by_vertex[face_a][vertex_b]
        corner_b1 = topology.face_corner_by_vertex[face_b][vertex_b]
        same_at_first = (
            tokens[(face_a, corner_a0)] == tokens[(face_b, corner_b0)]
        )
        same_at_second = (
            tokens[(face_a, corner_a1)] == tokens[(face_b, corner_b1)]
        )
        if same_at_first != same_at_second:
            raise UnrepresentableSmoothingError(
                "Edge {} is smooth at only one endpoint; an edge-level smoothing "
                "group cannot represent that split safely.".format(edge)
            )
        constraint = EdgeConstraint(
            edge=edge,
            faces=(min(face_a, face_b), max(face_a, face_b)),
            soft=same_at_first and same_at_second,
        )
        if constraint.soft:
            soft_edges.append(constraint)
        else:
            hard_edges.append(constraint)

    _require_source_fans_connected(
        topology,
        tokens,
        tuple(soft_edges),
    )
    return _SourceConstraints(
        tokens=tokens,
        soft_edges=tuple(soft_edges),
        hard_edges=tuple(hard_edges),
    )


def _tokens_from_fan_ids(
    topology: _Topology,
    corner_fan_ids: Sequence[Sequence[Hashable]],
) -> Mapping[CornerKey, Hashable]:
    _require_face_corner_shape(topology, corner_fan_ids, "corner_fan_ids")
    tokens: Dict[CornerKey, Hashable] = {}
    for face_index, face_values in enumerate(corner_fan_ids):
        for corner_index, fan_id in enumerate(face_values):
            try:
                hash(fan_id)
            except Exception as exc:
                raise SmoothingInputError(
                    "Fan ID at face {}, corner {} is not hashable.".format(
                        face_index, corner_index
                    )
                ) from exc
            vertex = topology.faces[face_index][corner_index]
            tokens[(face_index, corner_index)] = (vertex, fan_id)
    return tokens


def _tokens_from_normals(
    topology: _Topology,
    corner_normals: Sequence[Sequence[Sequence[float]]],
    tolerance_degrees: float,
) -> Mapping[CornerKey, Hashable]:
    if not isinstance(tolerance_degrees, (int, float)) or isinstance(
        tolerance_degrees, bool
    ):
        raise SmoothingInputError(
            "normal_angle_tolerance_degrees must be numeric."
        )
    if not math.isfinite(float(tolerance_degrees)):
        raise SmoothingInputError(
            "normal_angle_tolerance_degrees must be finite."
        )
    if tolerance_degrees < 0.0 or tolerance_degrees >= 180.0:
        raise SmoothingInputError(
            "normal_angle_tolerance_degrees must be in [0, 180)."
        )

    _require_face_corner_shape(topology, corner_normals, "corner_normals")
    normalized: Dict[CornerKey, Vector3] = {}
    for face_index, face_values in enumerate(corner_normals):
        for corner_index, raw_normal in enumerate(face_values):
            if isinstance(raw_normal, (str, bytes)) or not isinstance(
                raw_normal, Sequence
            ):
                raise SmoothingInputError(
                    "Normal at face {}, corner {} is not a vector.".format(
                        face_index, corner_index
                    )
                )
            if len(raw_normal) != 3:
                raise SmoothingInputError(
                    "Normal at face {}, corner {} does not have three values.".format(
                        face_index, corner_index
                    )
                )
            values: List[float] = []
            for component in raw_normal:
                if isinstance(component, bool) or not isinstance(
                    component, (int, float)
                ):
                    raise SmoothingInputError(
                        "Normal at face {}, corner {} is non-numeric.".format(
                            face_index, corner_index
                        )
                    )
                numeric = float(component)
                if not math.isfinite(numeric):
                    raise SmoothingInputError(
                        "Normal at face {}, corner {} is not finite.".format(
                            face_index, corner_index
                        )
                    )
                values.append(numeric)
            length = math.sqrt(sum(component * component for component in values))
            if length <= 1.0e-12:
                raise SmoothingInputError(
                    "Normal at face {}, corner {} has zero length.".format(
                        face_index, corner_index
                    )
                )
            normalized[(face_index, corner_index)] = (
                values[0] / length,
                values[1] / length,
                values[2] / length,
            )

    cosine_threshold = math.cos(math.radians(float(tolerance_degrees)))
    tokens: Dict[CornerKey, Hashable] = {}
    for vertex, corners in sorted(topology.vertex_corners.items()):
        union_find = _UnionFind(corners)
        for index, first in enumerate(corners):
            for second in corners[index + 1 :]:
                if _dot(normalized[first], normalized[second]) >= cosine_threshold:
                    union_find.union(first, second)

        members_by_root: Dict[Hashable, List[CornerKey]] = {}
        for corner in corners:
            members_by_root.setdefault(union_find.find(corner), []).append(corner)

        ordered_clusters = sorted(
            (tuple(sorted(members)) for members in members_by_root.values()),
            key=lambda members: members[0],
        )
        for cluster_index, members in enumerate(ordered_clusters):
            for index, first in enumerate(members):
                for second in members[index + 1 :]:
                    if _dot(normalized[first], normalized[second]) < cosine_threshold:
                        raise SmoothingInputError(
                            "Normal tolerance creates an ambiguous chained fan at "
                            "vertex {}; provide explicit corner_fan_ids.".format(vertex)
                        )
            token = (vertex, cluster_index)
            for corner in members:
                tokens[corner] = token
    return tokens


def _require_face_corner_shape(
    topology: _Topology,
    values: Sequence[Sequence[object]],
    label: str,
) -> None:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise SmoothingInputError("{} must be a face-corner sequence.".format(label))
    if len(values) != len(topology.faces):
        raise SmoothingInputError(
            "{} has {} faces; expected {}.".format(
                label, len(values), len(topology.faces)
            )
        )
    for face_index, face_values in enumerate(values):
        if isinstance(face_values, (str, bytes)) or not isinstance(
            face_values, Sequence
        ):
            raise SmoothingInputError(
                "{} face {} is not a sequence.".format(label, face_index)
            )
        expected_corners = len(topology.faces[face_index])
        if len(face_values) != expected_corners:
            raise SmoothingInputError(
                "{} face {} has {} corners; expected {}.".format(
                    label, face_index, len(face_values), expected_corners
                )
            )


def _require_matching_partitions(
    topology: _Topology,
    first: Mapping[CornerKey, Hashable],
    second: Mapping[CornerKey, Hashable],
) -> None:
    for vertex, corners in sorted(topology.vertex_corners.items()):
        for index, corner_a in enumerate(corners):
            for corner_b in corners[index + 1 :]:
                if (first[corner_a] == first[corner_b]) != (
                    second[corner_a] == second[corner_b]
                ):
                    raise SmoothingInputError(
                        "corner_normals and corner_fan_ids disagree at vertex {}.".format(
                            vertex
                        )
                    )


def _require_source_fans_connected(
    topology: _Topology,
    tokens: Mapping[CornerKey, Hashable],
    soft_edges: Sequence[EdgeConstraint],
) -> None:
    soft_face_links_by_vertex: Dict[int, Dict[int, Set[int]]] = {
        vertex: {
            face_index: set()
            for face_index, _ in corners
        }
        for vertex, corners in topology.vertex_corners.items()
    }
    for constraint in soft_edges:
        face_a, face_b = constraint.faces
        for vertex in constraint.edge:
            soft_face_links_by_vertex[vertex][face_a].add(face_b)
            soft_face_links_by_vertex[vertex][face_b].add(face_a)

    for vertex, corners in sorted(topology.vertex_corners.items()):
        faces_by_token: Dict[Hashable, Set[int]] = {}
        for face_index, corner_index in corners:
            faces_by_token.setdefault(tokens[(face_index, corner_index)], set()).add(
                face_index
            )
        links = soft_face_links_by_vertex[vertex]
        for faces in faces_by_token.values():
            if len(faces) <= 1:
                continue
            remaining = set(faces)
            seed = min(remaining)
            stack = [seed]
            remaining.remove(seed)
            while stack:
                current = stack.pop()
                for neighbor in sorted(links[current]):
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        stack.append(neighbor)
            if remaining:
                raise UnrepresentableSmoothingError(
                    "Source normal fan at vertex {} is disconnected by hard edges.".format(
                        vertex
                    )
                )


def _try_coherent_region_assignment(
    topology: _Topology,
    constraints: _SourceConstraints,
    *,
    max_groups: int,
    backtrack_limit: int,
) -> Optional[Tuple[Tuple[int, ...], Tuple[int, ...], ValidationReport]]:
    """Prefer one readable smoothing bit per connected soft surface region.

    A smoothing-group ID is a bit rather than a mutually exclusive label, but
    selecting one ID in Max should still reveal a useful, coherent surface.
    The old requirement-edge coloring minimized the number of bits and thereby
    reused the same ID across many unrelated strips.  This representation gives
    every connected soft region its own bit while one is available.  With more
    than 32 regions it keeps a valid conflict coloring and spends every spare
    bit splitting the largest reused regions.  Strict edge/fan validation stays
    authoritative; a topology that needs multi-bit faces falls back to the
    original exact requirement solver.
    """

    face_count = len(topology.faces)
    if not constraints.soft_edges:
        masks = (0,) * face_count
        report = _validate_prebuilt(
            topology,
            constraints,
            masks,
            max_groups=max_groups,
        )
        return masks, (), report

    face_union = _UnionFind(range(face_count))
    faces_incident_to_soft: Set[int] = set()
    for constraint in constraints.soft_edges:
        face_a, face_b = constraint.faces
        face_union.union(face_a, face_b)
        faces_incident_to_soft.add(face_a)
        faces_incident_to_soft.add(face_b)

    faces_by_root: Dict[Hashable, List[int]] = {}
    for face_index in sorted(faces_incident_to_soft):
        faces_by_root.setdefault(face_union.find(face_index), []).append(face_index)
    ordered_regions = sorted(
        (tuple(sorted(faces)) for faces in faces_by_root.values()),
        key=lambda faces: (faces[0], len(faces), faces),
    )
    region_by_face: Dict[int, int] = {}
    for region_index, region_faces in enumerate(ordered_regions):
        for face_index in region_faces:
            region_by_face[face_index] = region_index

    region_count = len(ordered_regions)
    if region_count <= max_groups:
        colors = tuple(range(region_count))
    else:
        adjacency: List[Set[int]] = [set() for _ in ordered_regions]

        def connect(first: int, second: int) -> None:
            adjacency[first].add(second)
            adjacency[second].add(first)

        for constraint in constraints.hard_edges:
            face_a, face_b = constraint.faces
            region_a = region_by_face.get(face_a)
            region_b = region_by_face.get(face_b)
            if region_a is None or region_b is None:
                continue
            if region_a == region_b:
                return None
            connect(region_a, region_b)

        # Faces sharing only a vertex can still merge in Max when their masks
        # overlap.  Add conflicts for different source normal fans as well.
        for _vertex, corners in sorted(topology.vertex_corners.items()):
            regions_by_token: Dict[Hashable, Set[int]] = {}
            for face_index, corner_index in corners:
                region_index = region_by_face.get(face_index)
                if region_index is None:
                    continue
                token = constraints.tokens[(face_index, corner_index)]
                regions_by_token.setdefault(token, set()).add(region_index)
            token_region_sets = [
                regions_by_token[token]
                for token in sorted(regions_by_token, key=repr)
            ]
            for token_index, first in enumerate(token_region_sets):
                for second in token_region_sets[token_index + 1 :]:
                    if first.intersection(second):
                        return None
                    for region_a in sorted(first):
                        for region_b in sorted(second):
                            connect(region_a, region_b)

        base_colors = list(
            _color_conflict_graph(
                tuple(frozenset(neighbors) for neighbors in adjacency),
                max_colors=max_groups,
                backtrack_limit=backtrack_limit,
            )
        )
        used_colors = max(base_colors) + 1 if base_colors else 0
        colors = _split_reused_region_colors(
            ordered_regions,
            base_colors,
            next_color=used_colors,
            max_groups=max_groups,
        )

    masks_mutable = [0] * face_count
    for face_index, region_index in region_by_face.items():
        masks_mutable[face_index] = 1 << colors[region_index]
    masks = tuple(mask & UINT32_MASK for mask in masks_mutable)
    try:
        report = _validate_prebuilt(
            topology,
            constraints,
            masks,
            max_groups=max_groups,
        )
    except SmoothingValidationError:
        return None

    requirement_colors = tuple(
        colors[region_by_face[constraint.faces[0]]] + 1
        for constraint in constraints.soft_edges
    )
    return masks, requirement_colors, report


def _split_reused_region_colors(
    regions: Sequence[Sequence[int]],
    base_colors: Sequence[int],
    *,
    next_color: int,
    max_groups: int,
) -> Tuple[int, ...]:
    """Use spare IDs to isolate the largest regions without breaking validity."""

    colors = list(base_colors)
    members_by_color: Dict[int, List[int]] = {}
    for region_index, color in enumerate(colors):
        members_by_color.setdefault(color, []).append(region_index)
    candidates = [
        region_index
        for members in members_by_color.values()
        if len(members) > 1
        for region_index in members
    ]
    candidates.sort(
        key=lambda region_index: (
            -len(regions[region_index]),
            regions[region_index][0],
            region_index,
        )
    )
    for region_index in candidates:
        if next_color >= max_groups:
            break
        old_color = colors[region_index]
        if sum(1 for color in colors if color == old_color) <= 1:
            continue
        colors[region_index] = next_color
        next_color += 1
    return tuple(colors)


def _build_requirement_conflicts(
    topology: _Topology,
    constraints: _SourceConstraints,
    requirements: Sequence[EdgeConstraint],
) -> Tuple[frozenset[int], ...]:
    adjacency: List[Set[int]] = [set() for _ in requirements]
    incident_requirements: List[Set[int]] = [
        set() for _ in range(len(topology.faces))
    ]
    for requirement_index, requirement in enumerate(requirements):
        for face_index in requirement.faces:
            incident_requirements[face_index].add(requirement_index)

    for hard_edge in constraints.hard_edges:
        face_a, face_b = hard_edge.faces
        _connect_requirement_sets(
            adjacency,
            incident_requirements[face_a],
            incident_requirements[face_b],
            context="hard edge {}".format(hard_edge.edge),
        )

    for vertex, corners in sorted(topology.vertex_corners.items()):
        faces_by_token: Dict[Hashable, Set[int]] = {}
        for face_index, corner_index in corners:
            token = constraints.tokens[(face_index, corner_index)]
            faces_by_token.setdefault(token, set()).add(face_index)

        requirement_sets: List[Set[int]] = []
        for token in sorted(faces_by_token, key=repr):
            requirement_set: Set[int] = set()
            for face_index in faces_by_token[token]:
                requirement_set.update(incident_requirements[face_index])
            requirement_sets.append(requirement_set)

        for index, first in enumerate(requirement_sets):
            for second in requirement_sets[index + 1 :]:
                _connect_requirement_sets(
                    adjacency,
                    first,
                    second,
                    context="different normal fans at vertex {}".format(vertex),
                )

    return tuple(frozenset(neighbors) for neighbors in adjacency)


def _connect_requirement_sets(
    adjacency: List[Set[int]],
    first: Iterable[int],
    second: Iterable[int],
    *,
    context: str,
) -> None:
    first_set = set(first)
    second_set = set(second)
    self_conflicts = first_set.intersection(second_set)
    if self_conflicts:
        raise UnrepresentableSmoothingError(
            "A soft-edge requirement conflicts with itself through {}.".format(context)
        )
    for node_a in sorted(first_set):
        for node_b in sorted(second_set):
            if node_a == node_b:
                continue
            adjacency[node_a].add(node_b)
            adjacency[node_b].add(node_a)


def _color_conflict_graph(
    adjacency: Sequence[frozenset[int]],
    *,
    max_colors: int,
    backtrack_limit: int,
) -> Tuple[int, ...]:
    node_count = len(adjacency)
    if node_count == 0:
        return ()

    for node, neighbors in enumerate(adjacency):
        if node in neighbors:
            raise UnrepresentableSmoothingError(
                "Conflict graph contains a self-loop at requirement {}.".format(node)
            )
        for neighbor in neighbors:
            if neighbor < 0 or neighbor >= node_count or node not in adjacency[neighbor]:
                raise SmoothingInputError("Conflict graph is not symmetric.")

    # A fully smooth connected surface normally produces thousands of
    # independent requirements but no conflicts between them.  All of those
    # requirements can reuse one smoothing-group bit.  Bypassing DSATUR here
    # turns this common large-mesh case from quadratic work into a linear
    # validation/assignment pass.
    if not any(adjacency):
        return (0,) * node_count

    greedy = _greedy_dsatur(adjacency)
    if max(greedy) + 1 <= max_colors:
        return greedy

    # The clique is only needed as a lower bound and as exact-search
    # pre-coloring after the inexpensive greedy pass has actually exceeded
    # Max's group budget.  Computing it eagerly made ordinary large meshes pay
    # a second quadratic scan even when greedy coloring already succeeded.
    clique = _greedy_maximal_clique(adjacency)
    if len(clique) > max_colors:
        raise UnrepresentableSmoothingError(
            "At least {} smoothing groups are required, exceeding the limit of {}.".format(
                len(clique), max_colors
            )
        )

    return _bounded_dsatur_backtracking(
        adjacency,
        max_colors=max_colors,
        backtrack_limit=backtrack_limit,
        precolored_clique=clique,
    )


def _greedy_dsatur(adjacency: Sequence[frozenset[int]]) -> Tuple[int, ...]:
    """Return deterministic DSATUR colors in O((V + E) log V) updates.

    The former implementation rescanned every uncolored node and all of its
    neighbors for every selected node.  That is quadratic even for a graph
    with no edges, which is the common case for one fully smooth surface.
    Incremental saturation sets plus stale-entry heap invalidation preserve
    the exact selection order (saturation, degree, lowest node ID) without
    repeatedly scanning the whole graph.
    """

    colors = [-1] * len(adjacency)
    neighbor_colors: List[Set[int]] = [set() for _ in adjacency]
    revisions = [0] * len(adjacency)
    heap = [
        (0, -len(neighbors), node, 0)
        for node, neighbors in enumerate(adjacency)
    ]
    heapq.heapify(heap)

    remaining = len(adjacency)
    while remaining:
        while heap:
            _, _, node, revision = heapq.heappop(heap)
            if colors[node] < 0 and revision == revisions[node]:
                break
        else:
            raise SmoothingInputError(
                "DSATUR priority queue became empty before coloring completed."
            )

        forbidden = neighbor_colors[node]
        color = 0
        while color in forbidden:
            color += 1
        colors[node] = color
        remaining -= 1

        for neighbor in sorted(adjacency[node]):
            if colors[neighbor] >= 0 or color in neighbor_colors[neighbor]:
                continue
            neighbor_colors[neighbor].add(color)
            revisions[neighbor] += 1
            heapq.heappush(
                heap,
                (
                    -len(neighbor_colors[neighbor]),
                    -len(adjacency[neighbor]),
                    neighbor,
                    revisions[neighbor],
                ),
            )

    return tuple(colors)


def _select_dsatur_node(
    adjacency: Sequence[frozenset[int]],
    colors: Sequence[int],
) -> int:
    uncolored = [node for node, color in enumerate(colors) if color < 0]
    if not uncolored:
        raise SmoothingInputError("DSATUR requested a node from a complete coloring.")

    def selection_key(node: int) -> Tuple[int, int, int]:
        saturation = len(
            {
                colors[neighbor]
                for neighbor in adjacency[node]
                if colors[neighbor] >= 0
            }
        )
        return saturation, len(adjacency[node]), -node

    return max(uncolored, key=selection_key)


def _greedy_maximal_clique(
    adjacency: Sequence[frozenset[int]],
) -> Tuple[int, ...]:
    order = sorted(range(len(adjacency)), key=lambda node: (-len(adjacency[node]), node))
    best: Tuple[int, ...] = ()
    for start in order:
        clique = [start]
        candidates = [
            node
            for node in order
            if node != start and node in adjacency[start]
        ]
        while candidates:
            chosen = min(
                candidates,
                key=lambda node: (-len(adjacency[node]), node),
            )
            clique.append(chosen)
            candidates = [
                node
                for node in candidates
                if node != chosen
                and all(node in adjacency[member] for member in clique)
            ]
        candidate_clique = tuple(sorted(clique))
        if len(candidate_clique) > len(best) or (
            len(candidate_clique) == len(best) and candidate_clique < best
        ):
            best = candidate_clique
    return best


def _bounded_dsatur_backtracking(
    adjacency: Sequence[frozenset[int]],
    *,
    max_colors: int,
    backtrack_limit: int,
    precolored_clique: Sequence[int],
) -> Tuple[int, ...]:
    colors = [-1] * len(adjacency)
    for color, node in enumerate(precolored_clique):
        colors[node] = color

    visited_states = 0

    def search(colored_count: int) -> bool:
        nonlocal visited_states
        visited_states += 1
        if visited_states > backtrack_limit:
            raise ColoringSearchLimitError(
                "DSATUR backtracking exceeded {} states.".format(backtrack_limit)
            )
        if colored_count == len(colors):
            return True

        node = _select_dsatur_node(adjacency, colors)
        forbidden = {
            colors[neighbor]
            for neighbor in adjacency[node]
            if colors[neighbor] >= 0
        }
        used_colors = sorted({color for color in colors if color >= 0})
        candidates = [color for color in used_colors if color not in forbidden]
        if len(used_colors) < max_colors:
            candidates.append(len(used_colors))

        for color in candidates:
            colors[node] = color
            if _forward_check(adjacency, colors, max_colors) and search(
                colored_count + 1
            ):
                return True
            colors[node] = -1
        return False

    initially_colored = sum(1 for color in colors if color >= 0)
    if not search(initially_colored):
        raise UnrepresentableSmoothingError(
            "The smoothing requirement graph is not {}-colorable.".format(max_colors)
        )
    return tuple(colors)


def _forward_check(
    adjacency: Sequence[frozenset[int]],
    colors: Sequence[int],
    max_colors: int,
) -> bool:
    for node, color in enumerate(colors):
        if color >= 0:
            continue
        forbidden = {
            colors[neighbor]
            for neighbor in adjacency[node]
            if colors[neighbor] >= 0
        }
        if len(forbidden) >= max_colors:
            return False
    return True


def _normalize_masks(
    masks: Sequence[int],
    face_count: int,
    max_groups: int,
) -> Tuple[int, ...]:
    if isinstance(masks, (str, bytes)) or not isinstance(masks, Sequence):
        raise SmoothingInputError("masks must be a sequence of integers.")
    if len(masks) != face_count:
        raise SmoothingInputError(
            "masks has {} entries; expected {}.".format(len(masks), face_count)
        )
    allowed_mask = (1 << max_groups) - 1
    normalized: List[int] = []
    for face_index, mask in enumerate(masks):
        if isinstance(mask, bool) or not isinstance(mask, int):
            raise SmoothingInputError(
                "Mask for face {} is not an integer.".format(face_index)
            )
        if mask < 0 or mask > UINT32_MASK:
            raise SmoothingInputError(
                "Mask for face {} is outside the unsigned 32-bit range.".format(
                    face_index
                )
            )
        if mask & ~allowed_mask:
            raise SmoothingInputError(
                "Mask for face {} uses a bit above max_groups={}.".format(
                    face_index, max_groups
                )
            )
        normalized.append(mask)
    return tuple(normalized)


def _validate_prebuilt(
    topology: _Topology,
    constraints: _SourceConstraints,
    masks: Sequence[int],
    *,
    max_groups: int,
) -> ValidationReport:
    normalized_masks = _normalize_masks(masks, len(topology.faces), max_groups)
    problems: List[str] = []

    for face_index, mask in enumerate(normalized_masks):
        if _popcount(mask) > len(topology.faces[face_index]):
            problems.append(
                "face {} uses more smoothing bits than its {} edges".format(
                    face_index, len(topology.faces[face_index])
                )
            )

    for constraint in constraints.soft_edges:
        face_a, face_b = constraint.faces
        if normalized_masks[face_a] & normalized_masks[face_b] == 0:
            problems.append(
                "soft edge {} has no shared smoothing bit".format(constraint.edge)
            )
    for constraint in constraints.hard_edges:
        face_a, face_b = constraint.faces
        if normalized_masks[face_a] & normalized_masks[face_b]:
            problems.append(
                "hard edge {} shares a smoothing bit".format(constraint.edge)
            )

    for vertex, corners in sorted(topology.vertex_corners.items()):
        faces = sorted({face_index for face_index, _ in corners})
        if len(faces) <= 1:
            continue
        actual = _UnionFind(faces)
        for index, face_a in enumerate(faces):
            for face_b in faces[index + 1 :]:
                if normalized_masks[face_a] & normalized_masks[face_b]:
                    actual.union(face_a, face_b)

        corner_by_face = {
            face_index: corner_index for face_index, corner_index in corners
        }
        for index, face_a in enumerate(faces):
            for face_b in faces[index + 1 :]:
                desired_same = (
                    constraints.tokens[(face_a, corner_by_face[face_a])]
                    == constraints.tokens[(face_b, corner_by_face[face_b])]
                )
                actual_same = actual.find(face_a) == actual.find(face_b)
                if desired_same != actual_same:
                    relation = "merged" if actual_same else "split"
                    problems.append(
                        "vertex {} normal fan is incorrectly {} between faces {} "
                        "and {}".format(vertex, relation, face_a, face_b)
                    )

    if problems:
        preview = "; ".join(problems[:8])
        if len(problems) > 8:
            preview += "; ... {} more".format(len(problems) - 8)
        raise SmoothingValidationError(preview)

    used_mask = 0
    for mask in normalized_masks:
        used_mask |= mask
    group_count = _popcount(used_mask)
    return ValidationReport(
        face_count=len(topology.faces),
        vertex_count=len(topology.vertex_corners),
        soft_edge_count=len(constraints.soft_edges),
        hard_edge_count=len(constraints.hard_edges),
        smoothing_group_count=group_count,
    )


def _dot(first: Vector3, second: Vector3) -> float:
    return (
        first[0] * second[0]
        + first[1] * second[1]
        + first[2] * second[2]
    )


def run_self_check() -> Dict[str, object]:
    """Run a compact, dependency-free regression suite used by the Max plug-in."""

    checks: List[str] = []

    faces = [(0, 1, 2), (0, 2, 3)]
    normals = [
        [(0.0, 0.0, 1.0)] * 3,
        [(0.0, 0.0, 1.0)] * 3,
    ]
    soft = compute_smoothing_assignment(faces, corner_normals=normals)
    if soft.masks != (1, 1) or soft.group_count != 1:
        raise SmoothingValidationError("Two-triangle soft-edge regression failed.")
    checks.append("soft-edge")

    hard = compute_smoothing_assignment(
        faces,
        corner_fan_ids=[[0, 1, 2], [3, 4, 5]],
    )
    if hard.masks != (0, 0):
        raise SmoothingValidationError("Two-triangle hard-edge regression failed.")
    checks.append("hard-edge")

    region_faces = [
        (0, 1, 2),
        (0, 2, 3),
        (10, 11, 12),
        (10, 12, 13),
    ]
    region_assignment = compute_smoothing_assignment(
        region_faces,
        corner_normals=[[(0.0, 0.0, 1.0)] * 3 for _ in region_faces],
    )
    if (
        region_assignment.masks != (1, 1, 2, 2)
        or region_assignment.strategy != "coherent_soft_regions"
    ):
        raise SmoothingValidationError(
            "Disconnected regions did not receive separate readable IDs."
        )
    checks.append("coherent-regions")

    def make_wheel(pair_count: int) -> Tuple[List[Face], List[List[int]]]:
        face_count = pair_count * 2
        wheel = [
            (0, face_index + 1, ((face_index + 1) % face_count) + 1)
            for face_index in range(face_count)
        ]
        parent: Dict[Tuple[int, int], Tuple[int, int]] = {
            (face_index, corner_index): (face_index, corner_index)
            for face_index in range(face_count)
            for corner_index in range(3)
        }

        def find(item: Tuple[int, int]) -> Tuple[int, int]:
            while parent[item] != item:
                parent[item] = parent[parent[item]]
                item = parent[item]
            return item

        def union(first: Tuple[int, int], second: Tuple[int, int]) -> None:
            root_a = find(first)
            root_b = find(second)
            if root_a != root_b:
                parent[max(root_a, root_b)] = min(root_a, root_b)

        for face_a in range(0, face_count, 2):
            face_b = face_a + 1
            shared = set(wheel[face_a]).intersection(wheel[face_b])
            for vertex in shared:
                union(
                    (face_a, wheel[face_a].index(vertex)),
                    (face_b, wheel[face_b].index(vertex)),
                )

        roots = sorted({find(item) for item in parent})
        root_ids = {root: index for index, root in enumerate(roots)}
        fan_ids = [
            [
                root_ids[find((face_index, corner_index))]
                for corner_index in range(3)
            ]
            for face_index in range(face_count)
        ]
        return wheel, fan_ids

    wheel_faces, wheel_fans = make_wheel(32)
    bit32 = compute_smoothing_assignment(
        wheel_faces,
        corner_fan_ids=wheel_fans,
    )
    if bit32.group_count != 32 or -0x80000000 not in bit32.maxscript_masks:
        raise SmoothingValidationError("The 32nd smoothing-group bit was not preserved.")
    if signed32_to_mask(mask_to_signed32(0x80000000)) != 0x80000000:
        raise SmoothingValidationError("Signed int32 smoothing conversion failed.")
    checks.append("bit-32")

    first = compute_smoothing_masks(wheel_faces, corner_fan_ids=wheel_fans)
    second = compute_smoothing_masks(wheel_faces, corner_fan_ids=wheel_fans)
    if first != second:
        raise SmoothingValidationError("Deterministic/idempotent output regression failed.")
    validate_smoothing_masks(wheel_faces, first, corner_fan_ids=wheel_fans)
    checks.append("deterministic")

    overflow_faces, overflow_fans = make_wheel(33)
    try:
        compute_smoothing_assignment(
            overflow_faces,
            corner_fan_ids=overflow_fans,
        )
    except UnrepresentableSmoothingError:
        checks.append("group-overflow-fail-closed")
    else:
        raise SmoothingValidationError("A 33-group input did not fail closed.")

    try:
        compute_smoothing_masks(
            [(0, 1, 2), (1, 0, 3), (0, 1, 4)],
            corner_fan_ids=[[0, 1, 2], [3, 4, 5], [6, 7, 8]],
        )
    except NonManifoldTopologyError:
        checks.append("non-manifold-fail-closed")
    else:
        raise SmoothingValidationError("A non-manifold edge did not fail closed.")

    return {
        "ok": True,
        "summary": "光滑组算法自检通过：{}。".format(", ".join(checks)),
        "checks": tuple(checks),
    }


__all__ = [
    "TOOL_VERSION",
    "MAX_SMOOTHING_GROUPS",
    "SmoothingError",
    "SmoothingInputError",
    "NonManifoldTopologyError",
    "UnrepresentableSmoothingError",
    "ColoringSearchLimitError",
    "SmoothingValidationError",
    "EdgeConstraint",
    "ValidationReport",
    "SmoothingAssignment",
    "mask_to_signed32",
    "signed32_to_mask",
    "compute_smoothing_masks",
    "compute_smoothing_assignment",
    "validate_smoothing_masks",
    "run_self_check",
]
