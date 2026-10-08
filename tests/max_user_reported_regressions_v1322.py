# -*- coding: utf-8 -*-
r"""Historical real-Max gate requiring caller-owned private test data.

Supply F2M_PRIVATE_MAX_FIXTURE, F2M_PRIVATE_FBX_VARIANT1 and optional
F2M_PRIVATE_NODE_A/B/C selectors. The assets are opened read-only; none are
distributed with this repository. Any save/reload probe writes only to
%LOCALAPPDATA%\FBXTo3dsMax\Tests and deletes the temporary scene afterwards.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import sys
import traceback
import uuid
from typing import Any, Sequence

from pymxs import runtime as rt


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE_PATH = os.path.abspath(__file__)


def _required_private_path(variable):
    path = os.environ.get(variable, "").strip()
    if not path or not os.path.isabs(path) or not os.path.isfile(path):
        raise RuntimeError(f"Provide an existing absolute private fixture: {variable}")
    path = os.path.abspath(path)
    try:
        inside_source = os.path.commonpath((ROOT, path)) == ROOT
    except ValueError:
        inside_source = False
    if inside_source:
        raise RuntimeError(f"Private fixtures must be outside the source tree: {variable}")
    return path


MAX_PATH = _required_private_path("F2M_PRIVATE_MAX_FIXTURE")
FBX_PATH = _required_private_path("F2M_PRIVATE_FBX_VARIANT1")
EVIDENCE_PATHS = {
    "gate": GATE_PATH,
    "topology_engine": os.path.join(ROOT, "f2m_topology_transfer.py"),
    "skin_engine": os.path.join(ROOT, "f2m_skin_replace.py"),
    "metadata_engine": os.path.join(ROOT, "f2m_fbx_metadata.py"),
    "smoothing_engine": os.path.join(ROOT, "f2m_smoothing.py"),
}
MODE1_NAMES = (
    os.environ.get("F2M_PRIVATE_NODE_A", "ExampleMeshA"),
    os.environ.get("F2M_PRIVATE_NODE_B", "ExampleMeshB"),
)
MODE2_NAME = os.environ.get("F2M_PRIVATE_NODE_C", "ExampleMeshC")
POSITION_TOLERANCE = 0.001
NORMAL_ANGLE_TOLERANCE_DEGREES = 0.1
SMOOTHING_NORMAL_ANGLE_TOLERANCE_DEGREES = 0.01
BOOLEAN_IMPORTER_PARAMS = {"Animation", "Skin", "SmoothingGroups"}
EXPECTED_VERSION = "1.3.24"
RESULT_PATH = os.path.join(
    os.environ["LOCALAPPDATA"],
    "FBXTo3dsMax", "Validation",
    "_max_user_reported_regressions_v1322_result.json",
)
os.makedirs(os.path.dirname(RESULT_PATH), exist_ok=True)
TEMP_ROOT = os.path.join(
    os.environ["LOCALAPPDATA"],
    "FBXTo3dsMax",
    "Tests",
)
TEMP_MAX = os.path.join(TEMP_ROOT, f"mode2_005_{uuid.uuid4().hex}.max")


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def load_module(filename: str, module_name: str) -> Any:
    path = os.path.join(ROOT, filename)
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
    module.ensure_runtime()
    return module


def reset_scene() -> None:
    rt.clearSelection()
    if not bool(rt.resetMaxFile(rt.Name("noPrompt"))):
        raise RuntimeError("resetMaxFile 返回 false。")


def point_tuple(value: Any) -> tuple[float, float, float]:
    result = (float(value.x), float(value.y), float(value.z))
    if any(not math.isfinite(item) for item in result):
        raise RuntimeError(f"点包含非有限值：{result}")
    return result


def matrix_tuple(value: Any) -> tuple[float, ...]:
    output: list[float] = []
    for row_name in ("row1", "row2", "row3", "row4"):
        output.extend(point_tuple(getattr(value, row_name)))
    return tuple(output)


def evaluated_world_positions(node: Any) -> list[tuple[float, float, float]]:
    mesh = None
    try:
        mesh = rt.snapshotAsMesh(node)
        transform = node.objectTransform
        return [
            point_tuple(rt.getVert(mesh, index) * transform)
            for index in range(1, int(rt.getNumVerts(mesh)) + 1)
        ]
    finally:
        if mesh is not None and str(mesh) != "undefined":
            rt.free(mesh)


def evaluated_corner_normals(
    node: Any,
    *,
    reset_to_smoothing_baseline: bool = False,
) -> tuple[list[list[tuple[float, float, float]]], dict[str, int]]:
    """Read the independently evaluated normal field above the complete stack."""

    modifier = rt.Edit_Normals()
    old_selection = list(rt.selection)
    old_selection_handles = [int(rt.getHandleByAnim(item)) for item in old_selection]
    modifier_handle = int(rt.getHandleByAnim(modifier))
    modifier_added = False
    faces: list[list[tuple[float, float, float]]] = []
    stats: dict[str, int] = {}
    try:
        modifier.name = "F2M_005_独立最终法线读取器"
        rt.addModifier(node, modifier)
        modifier_added = True
        rt.select(node)
        rt.execute("max modify mode")
        rt.modPanel.setCurrentObject(modifier)
        modifier.RebuildNormals(node=node)
        if reset_to_smoothing_baseline:
            initial_normal_count = int(modifier.GetNumNormals(node=node))
            initial_face_count = int(modifier.GetNumFaces(node=node))
            inherited_explicit = sum(
                1
                for normal_index in range(1, initial_normal_count + 1)
                if bool(modifier.GetNormalExplicit(normal_index, node=node))
            )
            inherited_specified = 0
            for face_index in range(1, initial_face_count + 1):
                degree = int(modifier.GetFaceDegree(face_index, node=node))
                inherited_specified += sum(
                    1
                    for corner_index in range(1, degree + 1)
                    if bool(
                        modifier.GetFaceNormalSpecified(
                            face_index,
                            corner_index,
                            node=node,
                        )
                    )
                )
            if inherited_explicit or inherited_specified:
                selection = rt.execute(f"#{{1..{initial_normal_count}}}")
                if not bool(modifier.Reset(selection=selection, node=node)):
                    raise AssertionError("独立光滑组基线 Reset(all) 返回 false。")
                selection = None
                modifier.RebuildNormals(node=node)
                rt.update(node)
                rt.select(node)
                rt.execute("max modify mode")
                rt.modPanel.setCurrentObject(modifier)
                rt.update(node)
                modifier.RebuildNormals(node=node)
        face_count = int(modifier.GetNumFaces(node=node))
        normal_count = int(modifier.GetNumNormals(node=node))
        if face_count < 1 or normal_count < 1:
            raise AssertionError("独立法线读取器没有有效面/法线数据。")
        specified = 0
        for face_index in range(1, face_count + 1):
            degree = int(modifier.GetFaceDegree(face_index, node=node))
            corners: list[tuple[float, float, float]] = []
            for corner_index in range(1, degree + 1):
                normal_id = int(
                    modifier.GetNormalID(face_index, corner_index, node=node)
                )
                if normal_id < 1 or normal_id > normal_count:
                    raise AssertionError(
                        f"独立法线读取器 normal ID 越界：{normal_id}/{normal_count}"
                    )
                value = point_tuple(modifier.GetNormal(normal_id, node=node))
                length = math.sqrt(sum(component * component for component in value))
                if length <= 1.0e-12:
                    raise AssertionError("独立法线读取器得到零向量。")
                corners.append(tuple(component / length for component in value))
                if bool(
                    modifier.GetFaceNormalSpecified(
                        face_index,
                        corner_index,
                        node=node,
                    )
                ):
                    specified += 1
            faces.append(corners)
        explicit = sum(
            1
            for normal_index in range(1, normal_count + 1)
            if bool(modifier.GetNormalExplicit(normal_index, node=node))
        )
        if reset_to_smoothing_baseline and (explicit or specified):
            raise AssertionError(
                "独立光滑组基线仍含 Explicit/Specified 状态："
                f"{explicit}/{specified}"
            )
        stats = {
            "face_count": face_count,
            "normal_count": normal_count,
            "corner_count": sum(len(face) for face in faces),
            "specified_corners": specified,
            "explicit_normals": explicit,
            "smoothing_baseline_reset": int(reset_to_smoothing_baseline),
        }
    finally:
        cleanup_errors: list[str] = []
        try:
            rt.execute("max create mode")
        except Exception as exc:
            cleanup_errors.append(f"退出修改面板失败：{exc}")
        if modifier_added:
            try:
                rt.deleteModifier(node, modifier)
            except Exception as exc:
                cleanup_errors.append(f"删除临时 Edit_Normals 失败：{exc}")
        try:
            remaining_handles = {
                int(rt.getHandleByAnim(item)) for item in list(node.modifiers)
            }
            if modifier_handle in remaining_handles:
                cleanup_errors.append(
                    f"临时 Edit_Normals 句柄仍在堆栈：{modifier_handle}"
                )
        except Exception as exc:
            cleanup_errors.append(f"验证临时修改器清理失败：{exc}")
        try:
            rt.clearSelection()
            if old_selection:
                rt.select(old_selection)
            restored_handles = [
                int(rt.getHandleByAnim(item)) for item in list(rt.selection)
            ]
            if sorted(restored_handles) != sorted(old_selection_handles):
                cleanup_errors.append(
                    "独立法线读取器没有严格恢复原选择："
                    f"{restored_handles}/{old_selection_handles}"
                )
        except Exception as exc:
            cleanup_errors.append(f"恢复原选择失败：{exc}")
        if cleanup_errors:
            raise AssertionError("；".join(cleanup_errors))
    stats["temporary_reader_removed"] = 1
    stats["selection_restored"] = 1
    return faces, stats


def compare_corner_normals(
    expected: Sequence[Sequence[Sequence[float]]],
    actual: Sequence[Sequence[Sequence[float]]],
    label: str,
) -> dict[str, Any]:
    if len(expected) != len(actual):
        raise AssertionError(
            f"{label} 法线面数不一致：{len(expected)}/{len(actual)}"
        )
    maximum = 0.0
    worst = (0, 0)
    corner_count = 0
    for face_index, (expected_face, actual_face) in enumerate(
        zip(expected, actual),
        start=1,
    ):
        if len(expected_face) != len(actual_face):
            raise AssertionError(
                f"{label} 第 {face_index} 面角数不一致："
                f"{len(expected_face)}/{len(actual_face)}"
            )
        for corner_index, (left, right) in enumerate(
            zip(expected_face, actual_face),
            start=1,
        ):
            dot = max(
                -1.0,
                min(1.0, sum(float(a) * float(b) for a, b in zip(left, right))),
            )
            angle = math.degrees(math.acos(dot))
            corner_count += 1
            if angle > maximum:
                maximum = angle
                worst = (face_index, corner_index)
    if maximum > NORMAL_ANGLE_TOLERANCE_DEGREES:
        raise AssertionError(
            f"{label} 最终逐面角法线最大角差 {maximum}°，"
            f"面/角 {worst[0]}/{worst[1]}，"
            f"允许 {NORMAL_ANGLE_TOLERANCE_DEGREES}°。"
        )
    return {
        "corner_count": corner_count,
        "max_final_normal_angle_degrees": maximum,
        "normal_angle_tolerance_degrees": NORMAL_ANGLE_TOLERANCE_DEGREES,
        "worst_face_corner": list(worst),
    }


def normal_difference_stats(
    expected: Sequence[Sequence[Sequence[float]]],
    actual: Sequence[Sequence[Sequence[float]]],
    label: str,
) -> dict[str, Any]:
    """Count directions that a smoothing-only baseline cannot express."""

    if len(expected) != len(actual):
        raise AssertionError(
            f"{label} 法线面数不一致：{len(expected)}/{len(actual)}"
        )
    residual_count = 0
    within_tolerance_count = 0
    maximum = 0.0
    maximum_within_tolerance = 0.0
    corner_count = 0
    for face_index, (expected_face, actual_face) in enumerate(
        zip(expected, actual),
        start=1,
    ):
        if len(expected_face) != len(actual_face):
            raise AssertionError(
                f"{label} 第 {face_index} 面角数不一致："
                f"{len(expected_face)}/{len(actual_face)}"
            )
        for expected_normal, actual_normal in zip(expected_face, actual_face):
            angle = normal_angle_degrees(expected_normal, actual_normal)
            maximum = max(maximum, angle)
            corner_count += 1
            if angle > NORMAL_ANGLE_TOLERANCE_DEGREES:
                residual_count += 1
            else:
                within_tolerance_count += 1
                maximum_within_tolerance = max(maximum_within_tolerance, angle)
    if corner_count < 1 or residual_count < 1:
        raise AssertionError(
            f"{label} 没有形成可证明的光滑组基线/自定义法线差异。"
        )
    return {
        "corner_count": corner_count,
        "residual_corner_count": residual_count,
        "within_tolerance_corner_count": within_tolerance_count,
        "max_baseline_angle_degrees": maximum,
        "max_within_tolerance_angle_degrees": maximum_within_tolerance,
        "residual_tolerance_degrees": NORMAL_ANGLE_TOLERANCE_DEGREES,
    }


def base_face_state(
    node: Any,
) -> tuple[tuple[tuple[int, ...], ...], tuple[int, ...]]:
    """Read base-object topology and smoothing masks without production helpers."""

    base_object = node.baseObject
    base_class = str(rt.classOf(base_object))
    if base_class == "Editable_Poly":
        face_count = int(rt.polyop.getNumFaces(base_object))
        faces = tuple(
            tuple(
                int(vertex_id)
                for vertex_id in list(
                    rt.polyop.getFaceVerts(base_object, face_index)
                )
            )
            for face_index in range(1, face_count + 1)
        )
        masks = tuple(
            int(rt.polyop.getFaceSmoothGroup(base_object, face_index))
            for face_index in range(1, face_count + 1)
        )
        return faces, masks
    if base_class in {"Editable_mesh", "Editable Mesh"}:
        mesh_value = rt.copy(base_object.mesh)
        try:
            face_count = int(rt.getNumFaces(mesh_value))
            faces = tuple(
                (
                    int(face.x),
                    int(face.y),
                    int(face.z),
                )
                for face in (
                    rt.getFace(mesh_value, face_index)
                    for face_index in range(1, face_count + 1)
                )
            )
            masks = tuple(
                int(rt.getFaceSmoothGroup(mesh_value, face_index))
                for face_index in range(1, face_count + 1)
            )
            return faces, masks
        finally:
            rt.free(mesh_value)
    raise AssertionError(f"不支持的基础对象类型：{base_class}")


def normal_angle_degrees(
    left: Sequence[float],
    right: Sequence[float],
) -> float:
    dot = max(
        -1.0,
        min(1.0, sum(float(a) * float(b) for a, b in zip(left, right))),
    )
    return math.degrees(math.acos(dot))


def compare_smoothing_semantics(
    expected_faces: Sequence[Sequence[int]],
    expected_corner_normals: Sequence[Sequence[Sequence[float]]],
    actual_faces: Sequence[Sequence[int]],
    actual_masks: Sequence[int],
    label: str,
) -> dict[str, Any]:
    """Compare Max smoothing overlap with the FBX normal discontinuities."""

    expected_signature = tuple(tuple(int(value) for value in face) for face in expected_faces)
    actual_signature = tuple(tuple(int(value) for value in face) for face in actual_faces)
    if expected_signature != actual_signature:
        raise AssertionError(f"{label} 基础面顶点签名与直接 FBX 参考不一致。")
    if len(expected_signature) != len(expected_corner_normals):
        raise AssertionError(f"{label} 参考面与参考角法线数量不一致。")
    if len(actual_signature) != len(actual_masks):
        raise AssertionError(f"{label} 最终面与光滑组掩码数量不一致。")

    edge_uses: dict[
        tuple[int, int],
        list[tuple[int, dict[int, Sequence[float]]]],
    ] = {}
    for face_index, (face, normals) in enumerate(
        zip(expected_signature, expected_corner_normals)
    ):
        if len(face) != len(normals) or len(face) < 3:
            raise AssertionError(f"{label} 第 {face_index + 1} 面的角数据无效。")
        normal_by_vertex = {
            int(vertex_id): normal
            for vertex_id, normal in zip(face, normals)
        }
        if len(normal_by_vertex) != len(face):
            raise AssertionError(f"{label} 第 {face_index + 1} 面包含重复顶点。")
        for corner_index, vertex_id in enumerate(face):
            next_vertex = face[(corner_index + 1) % len(face)]
            edge = tuple(sorted((int(vertex_id), int(next_vertex))))
            edge_uses.setdefault(edge, []).append((face_index, normal_by_vertex))

    internal_edges = 0
    boundary_edges = 0
    nonmanifold_edges = 0
    expected_smooth_edges = 0
    expected_hard_edges = 0
    mismatches: list[dict[str, Any]] = []
    for edge, uses in edge_uses.items():
        if len(uses) == 1:
            boundary_edges += 1
            continue
        if len(uses) != 2:
            nonmanifold_edges += 1
            continue
        internal_edges += 1
        (left_face, left_normals), (right_face, right_normals) = uses
        endpoint_angles = [
            normal_angle_degrees(left_normals[vertex_id], right_normals[vertex_id])
            for vertex_id in edge
        ]
        expected_smooth = all(
            angle <= SMOOTHING_NORMAL_ANGLE_TOLERANCE_DEGREES
            for angle in endpoint_angles
        )
        actual_smooth = bool(
            int(actual_masks[left_face]) & int(actual_masks[right_face])
        )
        if expected_smooth:
            expected_smooth_edges += 1
        else:
            expected_hard_edges += 1
        if expected_smooth != actual_smooth:
            mismatches.append(
                {
                    "edge": list(edge),
                    "faces": [left_face + 1, right_face + 1],
                    "endpoint_angles_degrees": endpoint_angles,
                    "expected_smooth": expected_smooth,
                    "actual_smooth": actual_smooth,
                    "masks": [
                        int(actual_masks[left_face]),
                        int(actual_masks[right_face]),
                    ],
                }
            )
    if nonmanifold_edges:
        raise AssertionError(f"{label} 有 {nonmanifold_edges} 条非流形边，门停止。")
    if internal_edges < 1 or expected_smooth_edges < 1 or expected_hard_edges < 1:
        raise AssertionError(
            f"{label} 光滑组门缺少有效的内部软/硬边覆盖："
            f"internal={internal_edges}, smooth={expected_smooth_edges}, "
            f"hard={expected_hard_edges}"
        )
    if mismatches:
        raise AssertionError(
            f"{label} 光滑组语义有 {len(mismatches)} 条共享边不一致；"
            f"首条={mismatches[0]}"
        )
    return {
        "face_signature_match": True,
        "face_count": len(actual_signature),
        "internal_edge_count": internal_edges,
        "boundary_edge_count": boundary_edges,
        "nonmanifold_edge_count": nonmanifold_edges,
        "expected_smooth_edge_count": expected_smooth_edges,
        "expected_hard_edge_count": expected_hard_edges,
        "mismatch_count": 0,
        "normal_angle_tolerance_degrees": (
            SMOOTHING_NORMAL_ANGLE_TOLERANCE_DEGREES
        ),
    }


def bbox(points: Sequence[Sequence[float]]) -> dict[str, list[float]]:
    if not points:
        raise AssertionError("空顶点集合没有包围盒。")
    return {
        "min": [min(float(point[axis]) for point in points) for axis in range(3)],
        "max": [max(float(point[axis]) for point in points) for axis in range(3)],
    }


def compare_positions(
    expected: Sequence[Sequence[float]],
    actual: Sequence[Sequence[float]],
    label: str,
) -> dict[str, Any]:
    if len(expected) != len(actual):
        raise AssertionError(f"{label} 顶点数不一致：{len(expected)}/{len(actual)}")
    deltas = position_deltas(expected, actual)
    maximum = max(deltas, default=0.0)
    if maximum > POSITION_TOLERANCE:
        worst = deltas.index(maximum) + 1
        raise AssertionError(
            f"{label} 世界顶点最大差 {maximum}，顶点 {worst}，"
            f"允许 {POSITION_TOLERANCE}。"
        )
    return {
        "vertex_count": len(actual),
        "max_world_delta": maximum,
        "tolerance": POSITION_TOLERANCE,
        "expected_bbox": bbox(expected),
        "actual_bbox": bbox(actual),
    }


def position_deltas(
    expected: Sequence[Sequence[float]],
    actual: Sequence[Sequence[float]],
) -> list[float]:
    if len(expected) != len(actual):
        raise AssertionError(f"顶点数不一致：{len(expected)}/{len(actual)}")
    return [
        math.sqrt(
            sum(
                (float(left) - float(right)) ** 2
                for left, right in zip(expected_point, actual_point)
            )
        )
        for expected_point, actual_point in zip(expected, actual)
    ]


def normalized_importer_value(name: str, value: Any) -> Any:
    if name in BOOLEAN_IMPORTER_PARAMS:
        text = str(value).strip().lower().lstrip("#")
        if text in {"true", "1", "1.0"}:
            return True
        if text in {"false", "0", "0.0"}:
            return False
        raise RuntimeError(f"FBX 导入器布尔参数 {name} 返回无效值：{value}")
    return str(value).strip().lower().lstrip("#")


def importer_values_equal(name: str, expected: Any, actual: Any) -> bool:
    if name in BOOLEAN_IMPORTER_PARAMS:
        return normalized_importer_value(name, expected) == normalized_importer_value(
            name, actual
        )
    return str(expected).strip().lower().lstrip("#") == str(actual).strip().lower().lstrip("#")


def set_importer_param(name: str, value: Any) -> None:
    result = rt.FBXImporterSetParam(rt.Name(name), value)
    if result is None or str(result).strip().lower() in {"undefined", "false"}:
        raise RuntimeError(f"FBX 导入器拒绝 {name}={value}")
    readback = rt.FBXImporterGetParam(rt.Name(name))
    if not importer_values_equal(name, value, readback):
        raise RuntimeError(
            f"FBX 导入器参数 {name} 读回不一致：期望 {value}，实际 {readback}"
        )


def snapshot_importer() -> dict[str, Any]:
    rt.execute("pluginManager.loadClass FbxImporter")
    return {
        name: normalized_importer_value(
            name,
            rt.FBXImporterGetParam(rt.Name(name)),
        )
        for name in ("Mode", "Animation", "Skin", "SmoothingGroups")
    }


def assert_importer_restored(before: dict[str, Any], label: str) -> dict[str, Any]:
    after = snapshot_importer()
    differences = [
        name
        for name in before
        if not importer_values_equal(name, before[name], after.get(name))
    ]
    if differences:
        raise AssertionError(
            f"{label} 后 FBX 全局导入设置未恢复：{differences}；"
            f"before={before}；after={after}"
        )
    return {"before": before, "after": after}


def import_fbx_isolated(path: str) -> None:
    snapshot = snapshot_importer()
    try:
        for name, value in {
            "Mode": rt.Name("create"),
            "Animation": False,
            "Skin": True,
            "SmoothingGroups": False,
        }.items():
            set_importer_param(name, value)
        escaped = path.replace("\\", "\\\\").replace('"', '\\"')
        result = rt.execute(f'importFile "{escaped}" #noPrompt')
        if result is False or str(result).strip().lower() == "false":
            raise RuntimeError(f"导入失败：{path}")
    finally:
        for name, value in snapshot.items():
            set_importer_param(name, value)


def direct_references() -> dict[str, dict[str, Any]]:
    reset_scene()
    import_fbx_isolated(FBX_PATH)
    result: dict[str, dict[str, Any]] = {}
    for name in (*MODE1_NAMES, MODE2_NAME):
        node = rt.getNodeByName(name)
        if node is None or str(node) == "undefined":
            raise RuntimeError(f"FBX 缺少目标：{name}")
        points = evaluated_world_positions(node)
        corner_normals, normal_stats = evaluated_corner_normals(node)
        face_vertex_ids, smoothing_masks = base_face_state(node)
        if len(face_vertex_ids) != len(corner_normals):
            raise AssertionError(
                f"{name} 的基础面数与独立法线读取面数不一致："
                f"{len(face_vertex_ids)}/{len(corner_normals)}"
            )
        result[name] = {
            "points": points,
            "corner_normals": corner_normals,
            "face_vertex_ids": face_vertex_ids,
            "smoothing_masks": smoothing_masks,
            "vertex_count": len(points),
            "face_count": len(face_vertex_ids),
            "bbox": bbox(points),
            "object_transform": matrix_tuple(node.objectTransform),
            "pivot": point_tuple(node.pivot),
            "visibility": visibility_state(node),
            "normal_stats": normal_stats,
            "smoothing_stats": {
                "nonzero_face_count": sum(
                    int(mask) != 0 for mask in smoothing_masks
                ),
                "distinct_masks": len(set(smoothing_masks)),
            },
        }
    return result


def load_user_scene(names: Sequence[str]) -> dict[str, Any]:
    reset_scene()
    if not bool(rt.loadMaxFile(MAX_PATH, useFileUnits=True, quiet=True)):
        raise RuntimeError("无法加载 PrivateFixture 场景。")
    result: dict[str, Any] = {}
    for name in names:
        node = rt.getNodeByName(name)
        if node is None or str(node) == "undefined":
            raise RuntimeError(f"PrivateFixture 场景缺少对象：{name}")
        result[name] = node
    rt.select(list(result.values()))
    return result


def visibility_state(node: Any) -> dict[str, Any]:
    return {
        "is_hidden": bool(node.isHidden),
        "layer_is_hidden": bool(node.layer.isHidden),
        "is_frozen": bool(node.isFrozen),
        "box_mode": bool(node.boxMode),
        "renderable": bool(node.renderable),
        "visibility": float(node.visibility),
    }


def assert_visible(node: Any, label: str) -> dict[str, Any]:
    state = visibility_state(node)
    if (
        state["is_hidden"]
        or state["layer_is_hidden"]
        or state["is_frozen"]
        or state["box_mode"]
        or not state["renderable"]
        or state["visibility"] <= 0.0
    ):
        raise AssertionError(f"{label} 最终候选不可正常看见/渲染：{state}")
    return state


def normal_modifier_stats(node: Any) -> dict[str, int]:
    """Inspect the user-visible state only on a disposable node copy."""

    old_selection = list(rt.selection)
    old_selection_handles = [int(rt.getHandleByAnim(item)) for item in old_selection]
    clone = None
    clone_handle = 0
    modifier = None
    stats: dict[str, int] = {}
    try:
        clone = rt.copy(node)
        if clone is None or str(clone) == "undefined":
            raise AssertionError(f"无法建立 {node.name} 的法线审计副本。")
        clone_handle = int(rt.getHandleByAnim(clone))
        clone.name = f"__F2M_005_NORMAL_AUDIT_{uuid.uuid4().hex}__"
        modifiers = [
            item
            for item in list(clone.modifiers)
            if str(rt.classOf(item)) == "Edit_Normals"
            and str(item.name).startswith("F2M_顶点法线")
        ]
        if len(modifiers) != 1:
            raise AssertionError(
                f"{node.name} 的审计副本 F2M Edit Normals 数量为 {len(modifiers)}。"
            )
        modifier = modifiers[0]
        rt.select(clone)
        rt.execute("max modify mode")
        rt.modPanel.setCurrentObject(modifier)
        face_count = int(modifier.GetNumFaces(node=clone))
        normal_count = int(modifier.GetNumNormals(node=clone))
        specified = 0
        corners = 0
        for face_index in range(1, face_count + 1):
            degree = int(modifier.GetFaceDegree(face_index, node=clone))
            corners += degree
            for corner_index in range(1, degree + 1):
                if bool(
                    modifier.GetFaceNormalSpecified(
                        face_index,
                        corner_index,
                        node=clone,
                    )
                ):
                    specified += 1
        explicit = sum(
            1
            for normal_index in range(1, normal_count + 1)
            if bool(modifier.GetNormalExplicit(normal_index, node=clone))
        )
        if face_count < 1 or normal_count < 1 or corners < 1:
            raise AssertionError(f"{node.name} 的审计副本法线结构无效。")
        stats = {
            "face_count": face_count,
            "corner_count": corners,
            "normal_count_after_ui_activation": normal_count,
            "specified_corners_after_ui_activation": specified,
            "explicit_normals_after_ui_activation": explicit,
            "observer_isolated_disposable_copy": 1,
        }
    finally:
        cleanup_errors: list[str] = []
        try:
            rt.execute("max create mode")
        except Exception as exc:
            cleanup_errors.append(f"法线审计副本退出修改面板失败：{exc}")
        modifier = None
        clone = None
        if clone_handle:
            try:
                deleted = rt.execute(
                    "(local auditNode = getAnimByHandle "
                    f"{clone_handle}; "
                    "if isValidNode auditNode then (delete auditNode; true) else false)"
                )
                if not bool(deleted):
                    cleanup_errors.append(
                        f"法线审计副本删除返回 false：{clone_handle}"
                    )
                remaining = rt.getAnimByHandle(clone_handle)
                if remaining is not None and str(remaining) != "undefined" and bool(
                    rt.isValidNode(remaining)
                ):
                    cleanup_errors.append(
                        f"法线审计副本删除后仍有效：{clone_handle}"
                    )
            except Exception as exc:
                cleanup_errors.append(f"删除法线审计副本失败：{exc}")
        try:
            rt.clearSelection()
            if old_selection:
                rt.select(old_selection)
            restored_handles = [
                int(rt.getHandleByAnim(item)) for item in list(rt.selection)
            ]
            if sorted(restored_handles) != sorted(old_selection_handles):
                cleanup_errors.append(
                    "法线审计副本没有恢复原选择："
                    f"{restored_handles}/{old_selection_handles}"
                )
        except Exception as exc:
            cleanup_errors.append(f"恢复法线审计前选择失败：{exc}")
        if cleanup_errors:
            raise AssertionError("；".join(cleanup_errors))
    return stats


def run_mode1_smoothing_baseline(
    references: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Independently prove which FBX directions require custom normals."""

    nodes = load_user_scene(MODE1_NAMES)
    handles = {
        name: int(rt.getHandleByAnim(node)) for name, node in nodes.items()
    }
    topology = load_module(
        "f2m_topology_transfer.py",
        f"_f2m_005_smoothing_baseline_{uuid.uuid4().hex}",
    )
    importer_before = snapshot_importer()
    summary = topology.run_from_max(
        FBX_PATH,
        mode="topology_only",
        dry_run=False,
        transfer_shape=True,
        transfer_uv=False,
        transfer_normals=False,
        transfer_smoothing_groups=True,
        transfer_vertex_color=False,
        transfer_alpha=False,
        transfer_material_ids=False,
        keep_imported=False,
        show_ui=False,
    )
    importer_restore = assert_importer_restored(
        importer_before,
        "模式一/独立光滑组基线",
    )
    if not bool(topology.LAST_RUN_OK):
        raise AssertionError(f"模式一独立光滑组基线执行失败：{summary}")
    output: dict[str, Any] = {
        "ok": True,
        "version": str(topology.TOOL_VERSION),
        "module_path": os.path.abspath(str(topology.__file__)),
        "module_sha256": sha256_file(str(topology.__file__)),
        "summary": str(summary),
        "report_path": os.path.abspath(str(topology.LAST_RUN_REPORT_PATH)),
        "importer_restore": importer_restore,
        "objects": {},
    }
    for name in MODE1_NAMES:
        final = rt.getAnimByHandle(handles[name])
        if final is None or str(final) == "undefined":
            raise AssertionError(f"独立光滑组基线丢失节点：{name}")
        f2m_normals = [
            modifier
            for modifier in list(final.modifiers)
            if str(rt.classOf(modifier)) == "Edit_Normals"
            and str(modifier.name).startswith("F2M_顶点法线")
        ]
        if f2m_normals:
            raise AssertionError(
                f"独立光滑组基线意外留下 {len(f2m_normals)} 个 F2M 法线修改器：{name}"
            )
        position_result = compare_positions(
            references[name]["points"],
            evaluated_world_positions(final),
            f"模式一/独立光滑组基线/{name}",
        )
        final_faces, final_masks = base_face_state(final)
        smoothing_result = compare_smoothing_semantics(
            references[name]["face_vertex_ids"],
            references[name]["corner_normals"],
            final_faces,
            final_masks,
            f"模式一/独立光滑组基线/{name}",
        )
        baseline_normals, reader_stats = evaluated_corner_normals(
            final,
            reset_to_smoothing_baseline=True,
        )
        difference_result = normal_difference_stats(
            references[name]["corner_normals"],
            baseline_normals,
            f"模式一/独立光滑组基线/{name}",
        )
        output["objects"][name] = {
            **position_result,
            **difference_result,
            "smoothing_semantics": smoothing_result,
            "baseline_reader_stats": reader_stats,
            "persistent_f2m_normal_modifier_count": 0,
        }
    return output


def run_mode1_case(
    references: dict[str, dict[str, Any]],
    smoothing_baseline: dict[str, Any],
    ref_coord_sys: str,
) -> dict[str, Any]:
    nodes = load_user_scene(MODE1_NAMES)
    before = {
        name: {
            "handle": int(rt.getHandleByAnim(node)),
            "object_transform": matrix_tuple(node.objectTransform),
            "pivot": point_tuple(node.pivot),
            "points": evaluated_world_positions(node),
        }
        for name, node in nodes.items()
    }
    rt.execute(f"setRefCoordSys #{ref_coord_sys}")
    topology = load_module(
        "f2m_topology_transfer.py",
        f"_f2m_005_mode1_{ref_coord_sys}_{uuid.uuid4().hex}",
    )
    importer_before = snapshot_importer()
    summary = topology.run_from_max(
        FBX_PATH,
        mode="topology_only",
        dry_run=False,
        transfer_shape=True,
        transfer_uv=False,
        transfer_normals=True,
        transfer_smoothing_groups=True,
        transfer_vertex_color=False,
        transfer_alpha=False,
        transfer_material_ids=False,
        keep_imported=False,
        show_ui=False,
    )
    importer_restore = assert_importer_restored(
        importer_before,
        f"模式一/{ref_coord_sys}",
    )
    if not bool(topology.LAST_RUN_OK):
        raise AssertionError(f"模式一/{ref_coord_sys} 执行失败：{summary}")
    output: dict[str, Any] = {
        "ok": True,
        "ref_coord_sys": ref_coord_sys,
        "version": str(topology.TOOL_VERSION),
        "module_path": os.path.abspath(str(topology.__file__)),
        "module_sha256": sha256_file(str(topology.__file__)),
        "summary": str(summary),
        "report_path": os.path.abspath(str(topology.LAST_RUN_REPORT_PATH)),
        "objects": {},
        "importer_restore": importer_restore,
    }
    object_errors: list[str] = []
    for name in MODE1_NAMES:
        final = rt.getAnimByHandle(before[name]["handle"])
        if final is None or str(final) == "undefined":
            raise AssertionError(f"模式一/{ref_coord_sys} 丢失节点：{name}")
        if matrix_tuple(final.objectTransform) != before[name]["object_transform"]:
            raise AssertionError(f"模式一/{ref_coord_sys} 改变 objectTransform：{name}")
        if point_tuple(final.pivot) != before[name]["pivot"]:
            raise AssertionError(f"模式一/{ref_coord_sys} 改变 pivot：{name}")
        reference_transform = tuple(references[name]["object_transform"])
        final_transform = matrix_tuple(final.objectTransform)
        initial_max_world_delta = max(
            position_deltas(references[name]["points"], before[name]["points"]),
            default=0.0,
        )
        if initial_max_world_delta <= POSITION_TOLERANCE:
            raise AssertionError(
                f"模式一/{ref_coord_sys}/{name} 调用前已与 FBX 参考一致，"
                "门无法证明本次传递实际生效。"
            )
        transform_delta = max(
            abs(float(left) - float(right))
            for left, right in zip(reference_transform, final_transform)
        )
        if transform_delta > 1.0e-5:
            raise AssertionError(
                f"模式一/{ref_coord_sys}/{name} 与直接 FBX 参考变换不一致："
                f"{transform_delta}"
            )
        try:
            position_result = compare_positions(
                references[name]["points"],
                evaluated_world_positions(final),
                f"模式一/{ref_coord_sys}/{name}",
            )
        except BaseException:
            position_result = {
                "position_error": traceback.format_exc(),
            }
            object_errors.append(name)
        visible_normal_stats = normal_modifier_stats(final)
        expected_residual_corners = int(
            smoothing_baseline["objects"][name]["residual_corner_count"]
        )
        if (
            visible_normal_stats["specified_corners_after_ui_activation"]
            != expected_residual_corners
        ):
            raise AssertionError(
                f"模式一/{ref_coord_sys}/{name} 用户可见 Specified 面角与独立基线残差不一致："
                f"{visible_normal_stats['specified_corners_after_ui_activation']}/"
                f"{expected_residual_corners}"
            )
        if not (
            0 < visible_normal_stats["explicit_normals_after_ui_activation"]
            <= visible_normal_stats["specified_corners_after_ui_activation"]
        ):
            raise AssertionError(
                f"模式一/{ref_coord_sys}/{name} 审计副本 Explicit 法线池不合理："
                f"{visible_normal_stats}"
            )
        try:
            final_corner_normals, final_reader_stats = evaluated_corner_normals(
                final
            )
            normal_result = compare_corner_normals(
                references[name]["corner_normals"],
                final_corner_normals,
                f"模式一/{ref_coord_sys}/{name}",
            )
        except BaseException:
            normal_result = {
                "normal_error": traceback.format_exc(),
            }
            final_reader_stats = {}
            object_errors.append(name + "/法线")
        try:
            final_faces, final_masks = base_face_state(final)
            smoothing_result = compare_smoothing_semantics(
                references[name]["face_vertex_ids"],
                references[name]["corner_normals"],
                final_faces,
                final_masks,
                f"模式一/{ref_coord_sys}/{name}",
            )
        except BaseException:
            smoothing_result = {
                "smoothing_error": traceback.format_exc(),
            }
            object_errors.append(name + "/光滑组")
        output["objects"][name] = {
            **position_result,
            **normal_result,
            "handle_preserved": True,
            "object_transform_preserved": True,
            "pivot_preserved": True,
            "reference_transform_max_delta": transform_delta,
            "initial_max_world_delta": initial_max_world_delta,
            "normal_stats_on_disposable_copy": visible_normal_stats,
            "independent_smoothing_baseline_residual_corners": (
                expected_residual_corners
            ),
            "residual_storage_match": True,
            "final_evaluated_normal_stats": final_reader_stats,
            "smoothing_semantics": smoothing_result,
        }
    if object_errors:
        output["ok"] = False
        output["error"] = "模式一对象验收失败：" + "，".join(object_errors)
    return output


def run_mode2_case(references: dict[str, dict[str, Any]]) -> dict[str, Any]:
    nodes = load_user_scene((MODE2_NAME,))
    old_node = nodes[MODE2_NAME]
    old_handle = int(rt.getHandleByAnim(old_node))
    skin = load_module(
        "f2m_skin_replace.py",
        f"_f2m_005_mode2_{uuid.uuid4().hex}",
    )
    importer_before = snapshot_importer()
    summary = skin.run_from_max(
        FBX_PATH,
        mode="replace",
        dry_run=False,
        transfer_shape=False,
        transfer_uv=False,
        transfer_normals=False,
        transfer_vertex_color=False,
        transfer_alpha=False,
        transfer_material_ids=False,
        keep_imported=False,
        backup_old_mesh=True,
        show_ui=False,
    )
    importer_restore = assert_importer_restored(importer_before, "模式二/005")
    if not bool(skin.LAST_RUN_OK):
        raise AssertionError(f"模式二执行失败：{summary}")
    final = rt.getNodeByName(MODE2_NAME)
    if final is None or str(final) == "undefined":
        raise AssertionError("模式二替换后缺少最终节点。")
    final_handle = int(rt.getHandleByAnim(final))
    if final_handle == old_handle:
        raise AssertionError("模式二没有以 FBX 候选替换旧 Max 网格。")
    if int(rt.F2M_Helper.countSkin(final)) != 1:
        raise AssertionError("模式二最终候选没有且仅有一个 Skin。")
    position_result = compare_positions(
        references[MODE2_NAME]["points"],
        evaluated_world_positions(final),
        "模式二/005/Leg",
    )
    visibility_result = assert_visible(final, "模式二/005")
    result = {
        "ok": True,
        "version": str(skin.TOOL_VERSION),
        "module_path": os.path.abspath(str(skin.__file__)),
        "module_sha256": sha256_file(str(skin.__file__)),
        "summary": str(summary),
        "report_path": os.path.abspath(str(skin.LAST_RUN_REPORT_PATH)),
        "importer_restore": importer_restore,
        "old_handle": old_handle,
        "final_handle": final_handle,
        "visibility": visibility_result,
        **position_result,
    }
    os.makedirs(TEMP_ROOT, exist_ok=True)
    if not bool(rt.saveMaxFile(TEMP_MAX, quiet=True)):
        raise RuntimeError("保存模式二隔离复验场景失败。")
    if not bool(rt.loadMaxFile(TEMP_MAX, useFileUnits=True, quiet=True)):
        raise RuntimeError("重载模式二隔离复验场景失败。")
    reloaded = rt.getNodeByName(MODE2_NAME)
    if reloaded is None or str(reloaded) == "undefined":
        raise AssertionError("模式二保存重载后缺少最终节点。")
    if int(rt.F2M_Helper.countSkin(reloaded)) != 1:
        raise AssertionError("模式二保存重载后 Skin 数量错误。")
    result["reload"] = {
        "visibility": assert_visible(reloaded, "模式二/005 保存重载"),
        **compare_positions(
            references[MODE2_NAME]["points"],
            evaluated_world_positions(reloaded),
            "模式二/005/Leg 保存重载",
        ),
    }
    return result


payload: dict[str, Any] = {
    "ok": False,
    "gate": {
        "path": GATE_PATH,
        "sha256": sha256_file(GATE_PATH),
        "run_id": uuid.uuid4().hex,
        "expected_version": EXPECTED_VERSION,
    },
    "source_files_read_only": True,
    "user_assets_saved": False,
    "evidence_files": {},
    "assets": {},
    "references": {},
    "mode1_smoothing_baseline": {},
    "mode1_world": {},
    "mode1_local": {},
    "mode2_leg": {},
    "error": "",
    "cleanup_error": "",
}

try:
    evidence_files_before = {
        name: sha256_file(path) for name, path in EVIDENCE_PATHS.items()
    }
    payload["evidence_files"] = evidence_files_before
    assets_before = {
        os.path.basename(path): sha256_file(path)
        for path in (MAX_PATH, FBX_PATH)
    }
    payload["assets"] = assets_before
    references = direct_references()
    payload["references"] = {
        name: {
            key: value
            for key, value in reference.items()
            if key not in {
                "points",
                "corner_normals",
                "face_vertex_ids",
                "smoothing_masks",
            }
        }
        for name, reference in references.items()
    }
    smoothing_baseline = run_mode1_smoothing_baseline(references)
    payload["mode1_smoothing_baseline"] = smoothing_baseline
    case_errors: dict[str, str] = {}
    for case_name, runner in (
        (
            "mode1_world",
            lambda: run_mode1_case(references, smoothing_baseline, "world"),
        ),
        (
            "mode1_local",
            lambda: run_mode1_case(references, smoothing_baseline, "local"),
        ),
        ("mode2_leg", lambda: run_mode2_case(references)),
    ):
        try:
            payload[case_name] = runner()
            if payload[case_name].get("ok") is False:
                case_errors[case_name] = str(
                    payload[case_name].get("error", "子门返回失败")
                )
        except BaseException:
            case_errors[case_name] = traceback.format_exc()
            payload[case_name] = {
                "ok": False,
                "error": case_errors[case_name],
            }
    assets_after = {
        os.path.basename(path): sha256_file(path)
        for path in (MAX_PATH, FBX_PATH)
    }
    if assets_after != assets_before:
        raise AssertionError("用户输入资产 SHA-256 发生变化。")
    payload["assets_unchanged"] = True
    evidence_files_after = {
        name: sha256_file(path) for name, path in EVIDENCE_PATHS.items()
    }
    if evidence_files_after != evidence_files_before:
        raise AssertionError(
            "门或生产依赖在执行期间发生变化："
            f"before={evidence_files_before}；after={evidence_files_after}"
        )
    payload["evidence_files_unchanged"] = True
    if case_errors:
        raise AssertionError(
            "005 独立场景失败：" + "，".join(sorted(case_errors))
        )
    payload["ok"] = True
except BaseException:
    payload["error"] = traceback.format_exc()
finally:
    try:
        reset_scene()
        if os.path.isfile(TEMP_MAX):
            os.remove(TEMP_MAX)
        payload["temporary_max_removed"] = not os.path.exists(TEMP_MAX)
    except BaseException:
        payload["cleanup_error"] = traceback.format_exc()
        payload["ok"] = False
    with open(RESULT_PATH, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

if not payload["ok"]:
    raise RuntimeError("005 用户回归门失败，请查看结果 JSON。")
