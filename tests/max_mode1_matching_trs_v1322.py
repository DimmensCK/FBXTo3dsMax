# -*- coding: utf-8 -*-
"""Real-Max core gate for Mode-1 world-space point transfer.

This test deliberately bypasses FBX import, Skin, topology remapping, normals,
and every other transfer channel.  It calls the production
``F2M_Helper.copyBaseVertexPositions`` helper directly and verifies its two
base-object branches under the toolbar World and Local reference systems.

Coverage matrix:

* Editable Poly and Editable Mesh;
* identical non-zero translation/rotation/positive non-uniform scale on the
  source and destination;
* identical non-zero translation/rotation/single-negative-axis non-uniform
  scale on the source and destination;
* World and Local toolbar reference-coordinate states;
* source unit scale versus identity receiver and different source/negative receiver TRS;
* independent direct node-world oracle, without snapshot-times-transform reuse.

No user asset is opened or saved.  The generated scene exists only in the
isolated 3ds Max Batch process.  The sole durable output is a JSON result
under local user data; importing this module does not run the cases.
"""

from __future__ import annotations

import gc
import hashlib
import importlib.util
import json
import math
import os
import sys
import traceback
from typing import Any, Sequence

from pymxs import runtime as rt


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_ROOT = os.path.join(ROOT, "contents") if os.path.isdir(os.path.join(ROOT, "contents")) else ROOT
GATE_PATH = os.path.abspath(__file__)
RESULT_PATH = os.path.join(
    os.environ["LOCALAPPDATA"], "FBXTo3dsMax", "Reports",
    "mode1_world_regression_" + os.urandom(16).hex() + ".json",
)

WORLD_TOLERANCE = 0.001
MATRIX_TOLERANCE = 1.0e-6
INITIAL_DIFFERENCE_MINIMUM = 0.25
EXPECTED_VERSION = "1.4.26"

TRANSFORMS = (
    (
        "positive_nonuniform",
        "(scaleMatrix [1.7,0.65,2.4]) * "
        "(rotateXMatrix 23.0) * (rotateYMatrix -19.0) * "
        "(rotateZMatrix 31.0) * "
        "(transMatrix [37.0,-24.0,11.0])",
        1,
    ),
    (
        "single_negative_axis",
        "(scaleMatrix [-1.3,0.8,2.2]) * "
        "(rotateXMatrix -17.0) * (rotateYMatrix 29.0) * "
        "(rotateZMatrix -34.0) * "
        "(transMatrix [-31.0,18.0,9.0])",
        -1,
    ),
)

# Keep the original eight matching-TRS cases and add non-cancelling pairs.
TRANSFORM_PAIRS = tuple(
    (name, expression, expression, sign, sign, True, False)
    for name, expression, sign in TRANSFORMS
) + (
    ("unit_scale_to_identity", "(scaleMatrix [0.3937007784843445,0.3937007784843445,0.3937007784843445])",
     "(matrix3 1)", 1, 1, False, True),
    ("different_trs_negative_receiver", TRANSFORMS[0][1], TRANSFORMS[1][1], 1, -1, False, False),
)

BASE_KINDS = ("poly", "mesh")
REFERENCE_COORDINATE_SYSTEMS = ("world", "local")


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def load_module(filename: str, module_name: str) -> Any:
    path = os.path.join(RUNTIME_ROOT, filename)
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法建立模块规范：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    expected = os.path.normcase(os.path.abspath(path))
    actual = os.path.normcase(os.path.abspath(str(module.__file__)))
    if actual != expected:
        raise RuntimeError(f"模块路径不一致：{actual}/{expected}")
    actual_version = str(getattr(module, "TOOL_VERSION", ""))
    if actual_version != EXPECTED_VERSION:
        raise RuntimeError(
            f"模块版本不一致：{filename}={actual_version}, "
            f"expected={EXPECTED_VERSION}"
        )
    return module


def reset_max_file_safely() -> None:
    """Release wrappers before destroying one generated test scene."""

    gc.collect()
    if not bool(
        rt.execute(
            """
            (
                try
                (
                    local currentObject = undefined
                    try(currentObject = modPanel.getCurrentObject())catch()
                    if currentObject != undefined do
                        setCommandPanelTaskMode #create
                    currentObject = undefined
                    gc light:true
                    true
                )
                catch(false)
            )
            """
        )
    ):
        raise RuntimeError("重置前无法安全释放 MAXScript wrapper。")
    try:
        rt.clearSelection()
    except Exception:
        pass
    if not bool(rt.resetMaxFile(rt.Name("noPrompt"))):
        raise RuntimeError("resetMaxFile 返回 false。")


def class_name(value: Any) -> str:
    return str(rt.classOf(value))


def normalized_name(value: Any) -> str:
    return str(value).strip().lstrip("#").casefold()


def point_tuple(value: Any) -> tuple[float, float, float]:
    result = (float(value.x), float(value.y), float(value.z))
    if any(not math.isfinite(component) for component in result):
        raise AssertionError(f"点包含非有限值：{result}")
    return result


def matrix_tuple(value: Any) -> tuple[float, ...]:
    result: list[float] = []
    for row_name in ("row1", "row2", "row3", "row4"):
        result.extend(point_tuple(getattr(value, row_name)))
    return tuple(result)


def matrix_max_delta(
    first: Sequence[float],
    second: Sequence[float],
) -> float:
    if len(first) != len(second):
        return math.inf
    return max(
        (abs(float(left) - float(right)) for left, right in zip(first, second)),
        default=0.0,
    )


def linear_determinant(value: Any) -> float:
    row1 = point_tuple(value.row1)
    row2 = point_tuple(value.row2)
    row3 = point_tuple(value.row3)
    return (
        row1[0] * (row2[1] * row3[2] - row2[2] * row3[1])
        - row1[1] * (row2[0] * row3[2] - row2[2] * row3[0])
        + row1[2] * (row2[0] * row3[1] - row2[1] * row3[0])
    )


def linear_row_lengths(value: Any) -> tuple[float, float, float]:
    rows = (
        point_tuple(value.row1),
        point_tuple(value.row2),
        point_tuple(value.row3),
    )
    return tuple(
        math.sqrt(sum(component * component for component in row))
        for row in rows
    )


def assert_transform_contract(value: Any, determinant_sign: int) -> dict[str, Any]:
    determinant = linear_determinant(value)
    if determinant_sign > 0 and determinant <= 0.01:
        raise AssertionError(f"正缩放矩阵的行列式无效：{determinant}")
    if determinant_sign < 0 and determinant >= -0.01:
        raise AssertionError(f"单负轴矩阵的行列式无效：{determinant}")

    row_lengths = linear_row_lengths(value)
    if min(row_lengths) <= 0.1 or max(row_lengths) - min(row_lengths) <= 0.2:
        raise AssertionError(f"矩阵没有形成有效非均匀缩放：{row_lengths}")

    translation = point_tuple(value.row4)
    if any(abs(component) <= 0.001 for component in translation):
        raise AssertionError(f"矩阵平移并非三个轴都非零：{translation}")

    linear_values = matrix_tuple(value)[:9]
    off_diagonal = (
        linear_values[1],
        linear_values[2],
        linear_values[3],
        linear_values[5],
        linear_values[6],
        linear_values[7],
    )
    if max(abs(component) for component in off_diagonal) <= 0.05:
        raise AssertionError("矩阵没有形成可观察的旋转分量。")

    return {
        "linear_determinant": determinant,
        "linear_row_lengths": list(row_lengths),
        "translation": list(translation),
    }


def selection_handles() -> list[int]:
    return sorted(
        int(rt.getHandleByAnim(node))
        for node in list(rt.selection)
    )


def make_geometry(base_kind: str, name: str) -> Any:
    node = rt.Box(
        name=name,
        length=7.0,
        width=11.0,
        height=5.0,
        lengthsegs=1,
        widthsegs=1,
        heightsegs=1,
    )
    if base_kind == "poly":
        rt.convertToPoly(node)
        expected_classes = {"Editable_Poly"}
    elif base_kind == "mesh":
        rt.convertToMesh(node)
        expected_classes = {"Editable_mesh", "Editable Mesh"}
    else:
        raise ValueError(f"未知基础类型：{base_kind}")

    actual_class = class_name(node.baseObject)
    if actual_class not in expected_classes:
        raise AssertionError(
            f"{name} 基础类型错误：{actual_class}/{sorted(expected_classes)}"
        )
    if len(list(node.modifiers)) != 0:
        raise AssertionError(f"{name} 的无修改器夹具意外带有修改器。")
    return node


def base_vertex_count(node: Any) -> int:
    base_object = node.baseObject
    base_class = class_name(base_object)
    if base_class == "Editable_Poly":
        return int(rt.polyop.getNumVerts(base_object))
    if base_class in {"Editable_mesh", "Editable Mesh"}:
        mesh_value = rt.copy(base_object.mesh)
        try:
            return int(rt.getNumVerts(mesh_value))
        finally:
            try:
                rt.free(mesh_value)
            except Exception:
                pass
    raise AssertionError(f"不支持的基础类型：{base_class}")


def base_face_signature(node: Any) -> tuple[tuple[int, ...], ...]:
    base_object = node.baseObject
    base_class = class_name(base_object)
    if base_class == "Editable_Poly":
        return tuple(
            tuple(
                int(vertex_id)
                for vertex_id in list(
                    rt.polyop.getFaceVerts(base_object, face_index)
                )
            )
            for face_index in range(
                1,
                int(rt.polyop.getNumFaces(base_object)) + 1,
            )
        )
    if base_class in {"Editable_mesh", "Editable Mesh"}:
        mesh_value = rt.copy(base_object.mesh)
        try:
            return tuple(
                (
                    int(face.x),
                    int(face.y),
                    int(face.z),
                )
                for face in (
                    rt.getFace(mesh_value, face_index)
                    for face_index in range(
                        1,
                        int(rt.getNumFaces(mesh_value)) + 1,
                    )
                )
            )
        finally:
            try:
                rt.free(mesh_value)
            except Exception:
                pass
    raise AssertionError(f"不支持的基础类型：{base_class}")


def authored_point(value: Any, vertex_index: int, role: str) -> Any:
    index = float(vertex_index)
    if role == "source":
        delta = (
            0.31 * index,
            (-0.17 if vertex_index % 2 else 0.17) * index,
            0.11 * float(vertex_index % 3),
        )
    elif role == "destination":
        delta = (
            -0.27 * index,
            0.23 * float(vertex_index % 2),
            -0.19 * index,
        )
    else:
        raise ValueError(f"未知点位角色：{role}")
    return rt.Point3(
        float(value.x) + delta[0],
        float(value.y) + delta[1],
        float(value.z) + delta[2],
    )


def author_base_positions(node: Any, role: str) -> tuple[tuple[float, float, float], ...]:
    base_object = node.baseObject
    base_class = class_name(base_object)
    authored = []
    current = wanted = None
    if base_class == "Editable_Poly":
        for vertex_index in range(
            1,
            int(rt.polyop.getNumVerts(base_object)) + 1,
        ):
            current = rt.polyop.getVert(base_object, vertex_index)
            wanted = authored_point(current, vertex_index, role)
            authored.append(point_tuple(wanted))
            rt.polyop.setVert(
                base_object,
                vertex_index,
                wanted,
            )
            current = wanted = None
        rt.update(node)
        return tuple(authored)

    if base_class in {"Editable_mesh", "Editable Mesh"}:
        working_mesh = rt.copy(base_object.mesh)
        try:
            for vertex_index in range(
                1,
                int(rt.getNumVerts(working_mesh)) + 1,
            ):
                current = rt.getVert(working_mesh, vertex_index)
                wanted = authored_point(current, vertex_index, role)
                authored.append(point_tuple(wanted))
                rt.setVert(
                    working_mesh,
                    vertex_index,
                    wanted,
                )
                current = wanted = None
            base_object.mesh = working_mesh
            rt.update(node)
        finally:
            current = wanted = None
            try:
                rt.free(working_mesh)
            except Exception:
                pass
        return tuple(authored)

    raise AssertionError(f"不支持的基础类型：{base_class}")


def evaluated_world_positions(
    node: Any,
) -> tuple[tuple[float, float, float], ...]:
    """Independent node-world oracle; no production helper or snapshot formula."""
    base_class = class_name(node.baseObject)
    getter = "polyop.getVert" if base_class == "Editable_Poly" else "getVert"
    if base_class not in {"Editable_Poly", "Editable_mesh", "Editable Mesh"}:
        raise AssertionError(f"Unsupported world oracle base: {base_class}")
    handle = int(rt.getHandleByAnim(node))
    count = base_vertex_count(node)
    raw = value = None
    try:
        raw = rt.execute(
            "(local observedNode = getAnimByHandle " + str(handle) +
            "; if observedNode == undefined then throw \"World oracle node vanished\"; " +
            "for observedIndex = 1 to " + str(count) +
            " collect (in coordsys world (" + getter + " observedNode observedIndex)))")
        positions = []
        for value in raw:
            positions.append(point_tuple(value))
            value = None
        if len(positions) != count:
            raise AssertionError("World oracle vertex count differs")
        return tuple(positions)
    finally:
        value = raw = None


def base_local_positions(node: Any) -> tuple[tuple[float, float, float], ...]:
    base = node.baseObject
    kind = class_name(base)
    mesh = value = None
    try:
        if kind == "Editable_Poly":
            count = int(rt.polyop.getNumVerts(base))
            getter = lambda index: rt.polyop.getVert(base, index)
        else:
            mesh = rt.copy(base.mesh)
            count = int(rt.getNumVerts(mesh))
            getter = lambda index: rt.meshop.getVert(mesh, index)
        positions = []
        for index in range(1, count + 1):
            value = getter(index)
            positions.append(point_tuple(value))
            value = None
        return tuple(positions)
    finally:
        value = None
        if mesh is not None:
            rt.free(mesh)
        mesh = base = None


def uv1_snapshot(node: Any) -> dict[str, Any]:
    mesh = value = None
    try:
        mesh = rt.snapshotAsMesh(node)
        count = int(rt.getNumTVerts(mesh))
        vertices, faces = [], []
        for index in range(1, count + 1):
            value = rt.getTVert(mesh, index)
            vertices.append(point_tuple(value))
            value = None
        if count:
            for index in range(1, int(rt.getNumFaces(mesh)) + 1):
                value = rt.getTVFace(mesh, index)
                faces.append((int(value.x), int(value.y), int(value.z)))
                value = None
        return {"vertices": vertices, "faces": faces}
    finally:
        value = None
        if mesh is not None:
            rt.free(mesh)
        mesh = None


def world_from_primitives(points: Sequence[Sequence[float]], tm: Sequence[float]) -> tuple[tuple[float, float, float], ...]:
    return tuple(tuple(sum(point[axis] * tm[axis * 3 + component] for axis in range(3))
                       + tm[9 + component] for component in range(3)) for point in points)


def native_point_budgets(first: Sequence[Sequence[float]], second: Sequence[Sequence[float]]) -> list[float]:
    return [0.000002 + 0.000002 * max(1.0, *(abs(value) for value in tuple(left) + tuple(right)))
            for left, right in zip(first, second)]


def point_distance(
    first: Sequence[float],
    second: Sequence[float],
) -> float:
    return math.sqrt(
        sum(
            (float(left) - float(right)) ** 2
            for left, right in zip(first, second)
        )
    )


def maximum_point_delta(
    first: Sequence[Sequence[float]],
    second: Sequence[Sequence[float]],
    label: str,
) -> tuple[float, int]:
    if len(first) != len(second):
        raise AssertionError(
            f"{label} 点数不一致：{len(first)}/{len(second)}"
        )
    deltas = [
        point_distance(left, right)
        for left, right in zip(first, second)
    ]
    maximum = max(deltas, default=0.0)
    worst_vertex = deltas.index(maximum) + 1 if deltas else 0
    return maximum, worst_vertex


def assert_world_points(
    expected: Sequence[Sequence[float]],
    actual: Sequence[Sequence[float]],
    label: str,
) -> dict[str, Any]:
    maximum, worst_vertex = maximum_point_delta(expected, actual, label)
    if maximum > WORLD_TOLERANCE:
        raise AssertionError(
            f"{label} 最大世界点误差 {maximum}，顶点 {worst_vertex}，"
            f"允许 {WORLD_TOLERANCE}。"
        )
    return {
        "vertex_count": len(actual),
        "max_world_delta": maximum,
        "worst_vertex": worst_vertex,
        "tolerance": WORLD_TOLERANCE,
    }


def set_reference_coordinate_system(name: str) -> None:
    rt.setRefCoordSys(rt.Name(name))
    actual = normalized_name(rt.getRefCoordSys())
    if actual != name.casefold():
        raise AssertionError(f"参考坐标系设置失败：{actual}/{name}")


def run_case(
    module: Any,
    *,
    transform_name: str,
    transform_expression: str,
    determinant_sign: int,
    reference_coordinate_system: str,
    base_kind: str,
    destination_transform_expression: str = "",
    destination_determinant_sign: int = 0,
    expect_matching: bool = True,
    unit_scale: bool = False,
    evidence_callback: Any = None,
) -> dict[str, Any]:
    reset_max_file_safely()
    case_id = (
        f"{base_kind}_{transform_name}_{reference_coordinate_system}"
    )
    source = make_geometry(base_kind, f"F2M_TRS_{case_id}_Source")
    destination = make_geometry(
        base_kind,
        f"F2M_TRS_{case_id}_Destination",
    )
    sentinel = rt.Sphere(
        name=f"F2M_TRS_{case_id}_SelectionSentinel",
        radius=1.0,
    )
    sentinel.position = rt.Point3(1000.0, 1000.0, 1000.0)

    source_base_handle = int(rt.getHandleByAnim(source.baseObject))
    destination_base_handle = int(rt.getHandleByAnim(destination.baseObject))
    if source_base_handle == destination_base_handle:
        raise AssertionError("source/destination 意外共享同一个基础对象。")

    source_topology = base_face_signature(source)
    destination_topology_before = base_face_signature(destination)
    if source_topology != destination_topology_before:
        raise AssertionError("独立生成的 source/destination 基础拓扑不一致。")
    source_vertex_count = base_vertex_count(source)
    if source_vertex_count != base_vertex_count(destination):
        raise AssertionError("source/destination 基础点数不一致。")

    source_authored = author_base_positions(source, "source")
    destination_authored = author_base_positions(destination, "destination")
    source_base_before = base_local_positions(source)
    destination_base_before = base_local_positions(destination)
    assert_world_points(source_authored, source_base_before, "Authored source base-local readback")
    assert_world_points(destination_authored, destination_base_before, "Authored destination base-local readback")
    source_uv_before = uv1_snapshot(source)
    destination_uv_before = uv1_snapshot(destination)
    node_handles_before = sorted(int(rt.getHandleByAnim(item)) for item in list(rt.objects))
    source_handle, destination_handle = int(rt.getHandleByAnim(source)), int(rt.getHandleByAnim(destination))
    if base_face_signature(source) != source_topology:
        raise AssertionError("建立 source 点位时改变了基础拓扑。")
    if base_face_signature(destination) != destination_topology_before:
        raise AssertionError("建立 destination 点位时改变了基础拓扑。")

    transform_value = rt.execute(f"({transform_expression})")
    if transform_value is None or str(transform_value) == "undefined":
        raise AssertionError(f"无法建立测试矩阵：{transform_expression}")
    source.transform = transform_value
    destination_transform = rt.execute(f"({destination_transform_expression})") if destination_transform_expression else transform_value
    if destination_transform is None or str(destination_transform) == "undefined":
        raise AssertionError("Cannot establish destination transform")
    destination.transform = destination_transform
    transform_value = destination_transform = None
    rt.update(source)
    rt.update(destination)

    source_transform_before = matrix_tuple(source.objectTransform)
    destination_transform_before = matrix_tuple(destination.objectTransform)
    matching_transform_delta = matrix_max_delta(
        source_transform_before,
        destination_transform_before,
    )
    if expect_matching and matching_transform_delta > MATRIX_TOLERANCE:
        raise AssertionError(
            "source/destination objectTransform 不一致："
            f"{matching_transform_delta}"
        )
    if not expect_matching and matching_transform_delta <= 0.1:
        raise AssertionError("Different-transform fixture did not establish distinct matrices")
    if unit_scale:
        factor = 0.3937007784843445
        expected_source_tm = (factor, 0, 0, 0, factor, 0, 0, 0, factor, 0, 0, 0)
        identity_tm = (1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0)
        if matrix_max_delta(source_transform_before, expected_source_tm) > MATRIX_TOLERANCE or matrix_max_delta(destination_transform_before, identity_tm) > MATRIX_TOLERANCE:
            raise AssertionError("Unit-scale to identity fixture differs")
        transform_contract = {"unit_scale_to_identity": True, "unit_factor": factor}
    else:
        transform_contract = assert_transform_contract(source.objectTransform, determinant_sign)
        assert_transform_contract(destination.objectTransform, destination_determinant_sign or determinant_sign)

    rt.select(sentinel)
    selection_before = selection_handles()
    set_reference_coordinate_system(reference_coordinate_system)

    expected_world = evaluated_world_positions(source)
    authored_source_world = world_from_primitives(source_base_before, source_transform_before)
    assert_world_points(authored_source_world, expected_world, f"{case_id}/authored-source versus direct-node oracle")
    destination_initial_world = evaluated_world_positions(destination)
    initial_delta, initial_worst_vertex = maximum_point_delta(
        expected_world,
        destination_initial_world,
        f"{case_id}/调用前",
    )
    if initial_delta <= INITIAL_DIFFERENCE_MINIMUM:
        raise AssertionError(
            f"{case_id} 调用前差异不足，可能形成假通过：{initial_delta}"
        )

    if not bool(rt.F2M_Helper.copyBaseVertexPositions(source, destination)):
        raise AssertionError(
            f"{case_id} 点传递失败：{module.helper_message()}"
        )
    if normalized_name(rt.getRefCoordSys()) != reference_coordinate_system:
        raise AssertionError(f"{case_id} 改变了参考坐标系。")

    actual_world = evaluated_world_positions(destination)
    source_world_after = evaluated_world_positions(source)
    source_base_after = base_local_positions(source)
    destination_base_after = base_local_positions(destination)
    source_uv_after = uv1_snapshot(source)
    destination_uv_after = uv1_snapshot(destination)
    source_transform_after = matrix_tuple(source.objectTransform)
    destination_transform_after = matrix_tuple(destination.objectTransform)
    raw_evidence = {
        "case_id": case_id, "base_kind": base_kind, "ref_coord_sys": reference_coordinate_system,
        "source_handle": source_handle, "destination_handle": destination_handle,
        "source_base_handle": source_base_handle, "destination_base_handle": destination_base_handle,
        "source_tm": list(source_transform_before), "destination_tm": list(destination_transform_before),
        "source_tm_after": list(source_transform_after), "destination_tm_after": list(destination_transform_after),
        "source_handle_after": int(rt.getHandleByAnim(source)), "destination_handle_after": int(rt.getHandleByAnim(destination)),
        "source_base_handle_after": int(rt.getHandleByAnim(source.baseObject)),
        "destination_base_handle_after": int(rt.getHandleByAnim(destination.baseObject)),
        "source_authored_base": source_authored, "destination_authored_base": destination_authored,
        "source_base_before": source_base_before, "destination_base_before": destination_base_before,
        "source_base_after": source_base_after, "destination_base_after": destination_base_after,
        "source_world_before": expected_world, "destination_world_before": destination_initial_world,
        "source_world_after": source_world_after, "destination_world_after": actual_world,
        "authored_source_world": authored_source_world,
        "source_topology_before": source_topology, "source_topology_after": base_face_signature(source),
        "destination_topology_before": destination_topology_before, "destination_topology_after": base_face_signature(destination),
        "source_uv_before": source_uv_before, "source_uv_after": source_uv_after,
        "destination_uv_before": destination_uv_before, "destination_uv_after": destination_uv_after,
        "scene_handles_before": node_handles_before,
        "scene_handles_after": sorted(int(rt.getHandleByAnim(item)) for item in list(rt.objects)),
        "selection_before": selection_before, "selection_after": selection_handles(),
        "reference_coordinate_system_after": normalized_name(rt.getRefCoordSys()),
        "source_modifier_count_after": len(list(source.modifiers)),
        "destination_modifier_count_after": len(list(destination.modifiers)),
        "world_tolerance": WORLD_TOLERANCE, "matrix_tolerance": MATRIX_TOLERANCE,
        "point_budgets": native_point_budgets(expected_world, actual_world),
    }
    if evidence_callback is not None:
        evidence_callback(raw_evidence)
    world_comparison = assert_world_points(
        expected_world,
        actual_world,
        f"{case_id}/destination",
    )
    source_comparison = assert_world_points(
        expected_world,
        source_world_after,
        f"{case_id}/source",
    )
    for index, (wanted, actual, budget) in enumerate(zip(expected_world, actual_world, raw_evidence["point_budgets"]), 1):
        if point_distance(wanted, actual) > budget:
            raise AssertionError(f"{case_id}/vertex {index} exceeds existing native precision budget {budget}")
    assert_world_points(world_from_primitives(destination_base_after, destination_transform_before), actual_world,
                        f"{case_id}/destination base times TM versus direct world")
    if source_base_after != source_base_before:
        raise AssertionError("Source authored base points changed")
    if source_uv_after != source_uv_before or destination_uv_after != destination_uv_before:
        raise AssertionError("Shape transfer changed existing UV1 data")
    if raw_evidence["scene_handles_after"] != node_handles_before:
        raise AssertionError("Shape transfer changed the complete owned scene inventory")
    if int(rt.getHandleByAnim(source)) != source_handle or int(rt.getHandleByAnim(destination)) != destination_handle:
        raise AssertionError("Source/destination node identities changed")
    if int(rt.getHandleByAnim(source.baseObject)) != source_base_handle or int(rt.getHandleByAnim(destination.baseObject)) != destination_base_handle:
        raise AssertionError("Source/destination base object identities changed")

    if selection_handles() != selection_before:
        raise AssertionError(
            f"{case_id} 改变选择：{selection_before}/{selection_handles()}"
        )
    if base_face_signature(source) != source_topology:
        raise AssertionError(f"{case_id} 改变 source 基础拓扑。")
    if base_face_signature(destination) != destination_topology_before:
        raise AssertionError(f"{case_id} 改变 destination 基础拓扑。")

    source_transform_delta = matrix_max_delta(
        source_transform_before,
        source_transform_after,
    )
    destination_transform_delta = matrix_max_delta(
        destination_transform_before,
        destination_transform_after,
    )
    if source_transform_delta > MATRIX_TOLERANCE:
        raise AssertionError(
            f"{case_id} 改变 source objectTransform：{source_transform_delta}"
        )
    if destination_transform_delta > MATRIX_TOLERANCE:
        raise AssertionError(
            f"{case_id} 改变 destination objectTransform："
            f"{destination_transform_delta}"
        )
    if len(list(source.modifiers)) != 0 or len(list(destination.modifiers)) != 0:
        raise AssertionError(f"{case_id} 无修改器夹具出现了修改器。")

    return {
        "ok": True,
        "case_id": case_id,
        "base_kind": base_kind,
        "base_class": class_name(destination.baseObject),
        "transform_kind": transform_name,
        "ref_coord_sys": reference_coordinate_system,
        "source_destination_tm_delta_before": matching_transform_delta,
        "source_tm_delta_after": source_transform_delta,
        "destination_tm_delta_after": destination_transform_delta,
        "object_transform": list(source_transform_before),
        "destination_object_transform": list(destination_transform_before),
        "expect_matching_transforms": expect_matching,
        "expected_world": list(expected_world),
        "actual_world": list(actual_world),
        "source_world_after": list(source_world_after),
        **transform_contract,
        "initial_max_world_delta": initial_delta,
        "initial_worst_vertex": initial_worst_vertex,
        "final": world_comparison,
        "source_unchanged": source_comparison,
        "topology_preserved": True,
        "selection_preserved": True,
        "modifier_count": 0,
        "helper_message": str(module.helper_message()),
        "raw_evidence": raw_evidence,
    }


payload: dict[str, Any] = {
    "ok": False,
    "gate": {
        "path": GATE_PATH,
        "sha256": sha256_file(GATE_PATH),
        "run_id": os.urandom(16).hex(),
        "expected_version": EXPECTED_VERSION,
    },
            "test": "Mode-1 matching TRS core point transfer v1.4.26 gate",
    "scope": (
        "generated Editable Poly/Mesh only; direct production helper; "
        "no FBX, Skin, normals, mapping channels, or user assets"
    ),
    "result_path": os.path.abspath(RESULT_PATH),
    "world_tolerance": WORLD_TOLERANCE,
    "matrix_tolerance": MATRIX_TOLERANCE,
    "expected_case_count": (
        len(TRANSFORM_PAIRS)
        * len(REFERENCE_COORDINATE_SYSTEMS)
        * len(BASE_KINDS)
    ),
    "module": {},
    "cases": [],
    "error": "",
    "cleanup_error": "",
}


def main() -> None:
    topology = load_module(
        "f2m_topology_transfer.py",
        "_f2m_mode1_matching_trs_v1322",
    )
    topology.ensure_runtime()
    payload["module"] = {
        "path": os.path.abspath(str(topology.__file__)),
        "sha256": sha256_file(str(topology.__file__)),
        "version": str(topology.TOOL_VERSION),
    }

    original_ref_coord = rt.getRefCoordSys()
    failures: list[str] = []
    try:
        for transform_name, expression, destination_expression, determinant_sign, destination_sign, matching, unit_scale in TRANSFORM_PAIRS:
            for reference_coordinate_system in REFERENCE_COORDINATE_SYSTEMS:
                for base_kind in BASE_KINDS:
                    case_id = (
                        f"{base_kind}_{transform_name}_"
                        f"{reference_coordinate_system}"
                    )
                    try:
                        result = run_case(
                            topology,
                            transform_name=transform_name,
                            transform_expression=expression,
                            determinant_sign=determinant_sign,
                            reference_coordinate_system=(
                                reference_coordinate_system
                            ),
                            base_kind=base_kind,
                            destination_transform_expression=destination_expression,
                            destination_determinant_sign=destination_sign,
                            expect_matching=matching,
                            unit_scale=unit_scale,
                        )
                    except BaseException:
                        failure = traceback.format_exc()
                        failures.append(case_id)
                        payload["cases"].append(
                            {
                                "ok": False,
                                "case_id": case_id,
                                "base_kind": base_kind,
                                "transform_kind": transform_name,
                                "ref_coord_sys": (
                                    reference_coordinate_system
                                ),
                                "error": failure,
                            }
                        )
                    else:
                        payload["cases"].append(result)
    finally:
        try:
            rt.setRefCoordSys(original_ref_coord)
        except Exception:
            pass

    if len(payload["cases"]) != payload["expected_case_count"]:
        raise AssertionError(
            "执行用例数不完整："
            f"{len(payload['cases'])}/{payload['expected_case_count']}"
        )
    if failures:
        raise AssertionError(
            f"{len(failures)}/{payload['expected_case_count']} 个匹配 TRS "
            "点传递用例失败：" + "，".join(failures)
        )
    payload["ok"] = True


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        payload["ok"] = False
        payload["error"] = traceback.format_exc()
    finally:
        try:
            reset_max_file_safely()
        except BaseException:
            payload["cleanup_error"] = traceback.format_exc()
            payload["ok"] = False
        os.makedirs(os.path.dirname(RESULT_PATH), exist_ok=True)
        with open(RESULT_PATH, "x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    if not payload["ok"]:
        raise RuntimeError("模式一匹配 TRS 核心门失败，请查看结果 JSON。")
