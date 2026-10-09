# -*- coding: utf-8 -*-
"""Bounded performance regressions for FBXTo3dsMax v1.4.26.

The first two cases exercise pure Python code and therefore run both under
ordinary CPython and 3ds Max's embedded Python.  When pymxs is available, a
third case creates one temporary Editable Poly in a fresh, unsaved Batch
scene, calls the production batched smoothing-group writer, verifies every
face, and resets the scene again.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence, Tuple

try:
    from pymxs import runtime as rt
except Exception:
    rt = None


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_ROOT = os.path.join(ROOT, "contents") if os.path.isdir(os.path.join(ROOT, "contents")) else ROOT
TESTS_DIR = os.path.join(ROOT, "tests")
INSIDE_3DS_MAX = rt is not None
DEFAULT_RESULT_NAME = (
    "_max_performance_regression_result.json"
    if INSIDE_3DS_MAX
    else "_performance_regression_python_result.json"
)
RESULT = os.environ.get(
    "F2M_PERFORMANCE_RESULT",
    os.path.join(TESTS_DIR, DEFAULT_RESULT_NAME),
)

SMOOTHING_ROWS = 200
SMOOTHING_COLUMNS = 200
SMOOTHING_FACE_COUNT = SMOOTHING_ROWS * SMOOTHING_COLUMNS
SMOOTHING_HARD_LIMIT_SECONDS = 15.0

TOPOLOGY_FACE_COUNT = 100_000
TOPOLOGY_HARD_LIMIT_SECONDS = 10.0

MAX_POLY_ROWS = 200
MAX_POLY_COLUMNS = 250
MAX_POLY_FACE_COUNT = MAX_POLY_ROWS * MAX_POLY_COLUMNS
MAX_BATCH_HARD_LIMIT_SECONDS = 5.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_module(filename: str, module_name: str) -> Any:
    path = os.path.abspath(os.path.join(RUNTIME_ROOT, filename))
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法为性能测试加载模块：{path}")
    sys.modules.pop(module_name, None)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    actual = os.path.normcase(os.path.abspath(module.__file__))
    if actual != os.path.normcase(path):
        raise RuntimeError(f"性能测试模块来源不一致：{actual} != {path}")
    return module


def _quad_grid(rows: int, columns: int) -> Tuple[Tuple[int, int, int, int], ...]:
    stride = columns + 1
    faces: List[Tuple[int, int, int, int]] = []
    append = faces.append
    for row in range(rows):
        row_start = row * stride
        next_row_start = (row + 1) * stride
        for column in range(columns):
            lower_left = row_start + column
            append(
                (
                    lower_left,
                    lower_left + 1,
                    next_row_start + column + 1,
                    next_row_start + column,
                )
            )
    return tuple(faces)


def _run_smoothing_case(smoothing: Any) -> Dict[str, Any]:
    generated_at = time.perf_counter()
    faces = _quad_grid(SMOOTHING_ROWS, SMOOTHING_COLUMNS)
    corner_normals = tuple(
        ((0.0, 0.0, 1.0),) * len(face)
        for face in faces
    )
    generation_seconds = time.perf_counter() - generated_at
    if len(faces) != SMOOTHING_FACE_COUNT:
        raise AssertionError(
            f"全光滑网格面数错误：{len(faces)}/{SMOOTHING_FACE_COUNT}"
        )

    started = time.perf_counter()
    # The production FBX-without-LayerElementSmoothing path derives soft/hard
    # edges from face-corner normal directions, not Autodesk's storage IDs.
    # Exercise that exact path on a substantial all-soft mesh.
    assignment = smoothing.compute_smoothing_assignment(
        faces,
        corner_normals=corner_normals,
        normal_angle_tolerance_degrees=0.01,
    )
    elapsed = time.perf_counter() - started

    expected_soft_edges = (
        SMOOTHING_ROWS * (SMOOTHING_COLUMNS - 1)
        + SMOOTHING_COLUMNS * (SMOOTHING_ROWS - 1)
    )
    unique_masks = sorted(set(int(mask) for mask in assignment.masks))
    if len(assignment.masks) != SMOOTHING_FACE_COUNT:
        raise AssertionError(
            f"光滑组结果面数错误：{len(assignment.masks)}/{SMOOTHING_FACE_COUNT}"
        )
    if unique_masks != [1] or int(assignment.group_count) != 1:
        raise AssertionError(
            f"全光滑网格没有收敛为唯一光滑组：masks={unique_masks}, "
            f"groups={assignment.group_count}"
        )
    if int(assignment.validation.soft_edge_count) != expected_soft_edges:
        raise AssertionError(
            "全光滑网格软边计数错误："
            f"{assignment.validation.soft_edge_count}/{expected_soft_edges}"
        )
    if int(assignment.validation.hard_edge_count) != 0:
        raise AssertionError(
            f"全光滑网格出现意外硬边：{assignment.validation.hard_edge_count}"
        )
    if elapsed > SMOOTHING_HARD_LIMIT_SECONDS:
        raise AssertionError(
            f"40,000 面全光滑求解耗时 {elapsed:.6f} 秒，"
            f"超过硬阈值 {SMOOTHING_HARD_LIMIT_SECONDS:.1f} 秒"
        )

    return {
        "id": "python_corner_normal_smoothing_all_soft_40000_faces",
        "status": "passed",
        "input": {
            "rows": SMOOTHING_ROWS,
            "columns": SMOOTHING_COLUMNS,
            "face_count": SMOOTHING_FACE_COUNT,
            "corner_normal_count": SMOOTHING_FACE_COUNT * 4,
            "normal_angle_tolerance_degrees": 0.01,
            "expected_soft_edge_count": expected_soft_edges,
        },
        "generation_seconds": round(generation_seconds, 6),
        "elapsed_seconds": round(elapsed, 6),
        "hard_limit_seconds": SMOOTHING_HARD_LIMIT_SECONDS,
        "evidence": {
            "unique_masks": unique_masks,
            "group_count": int(assignment.group_count),
            "soft_edge_count": int(assignment.validation.soft_edge_count),
            "hard_edge_count": int(assignment.validation.hard_edge_count),
        },
    }


def _disjoint_quads(
    face_count: int,
) -> Tuple[Tuple[int, int, int, int], ...]:
    return tuple(
        (index * 4 + 1, index * 4 + 2, index * 4 + 3, index * 4 + 4)
        for index in range(face_count)
    )


def _run_topology_case(topology: Any) -> Dict[str, Any]:
    generated_at = time.perf_counter()
    fbx_faces = _disjoint_quads(TOPOLOGY_FACE_COUNT)
    # Reverse face order and rotate every quad by two corners.  Winding remains
    # unchanged, so the production map must recover both the face and corner
    # correspondence without accepting a mirrored face.
    max_faces = tuple(
        (face[2], face[3], face[0], face[1])
        for face in reversed(fbx_faces)
    )
    generation_seconds = time.perf_counter() - generated_at

    started = time.perf_counter()
    mapping = topology._build_topology_map_from_faces(
        fbx_faces,
        max_faces,
        vertex_count=TOPOLOGY_FACE_COUNT * 4,
    )
    elapsed = time.perf_counter() - started

    expected_faces = tuple(range(TOPOLOGY_FACE_COUNT - 1, -1, -1))
    expected_corner_map = (2, 3, 0, 1)
    if mapping.fbx_face_for_max_face != expected_faces:
        raise AssertionError("100,000 个四边形的反序逐面映射不正确")
    if any(
        corner_map != expected_corner_map
        for corner_map in mapping.fbx_corner_for_max_corner
    ):
        raise AssertionError("100,000 个四边形的循环角起点映射不正确")
    if int(mapping.exact_face_count) != 0:
        raise AssertionError(f"意外出现精确角映射：{mapping.exact_face_count}")
    if int(mapping.cyclic_corner_face_count) != TOPOLOGY_FACE_COUNT:
        raise AssertionError(
            "循环角映射计数错误："
            f"{mapping.cyclic_corner_face_count}/{TOPOLOGY_FACE_COUNT}"
        )
    if int(mapping.reordered_face_count) != TOPOLOGY_FACE_COUNT:
        raise AssertionError(
            "重排面计数错误："
            f"{mapping.reordered_face_count}/{TOPOLOGY_FACE_COUNT}"
        )
    if elapsed > TOPOLOGY_HARD_LIMIT_SECONDS:
        raise AssertionError(
            f"100,000 个四边形拓扑映射耗时 {elapsed:.6f} 秒，"
            f"超过硬阈值 {TOPOLOGY_HARD_LIMIT_SECONDS:.1f} 秒"
        )

    return {
        "id": "python_topology_100000_rotated_quads",
        "status": "passed",
        "input": {
            "face_count": TOPOLOGY_FACE_COUNT,
            "vertex_count": TOPOLOGY_FACE_COUNT * 4,
            "max_face_order": "reversed",
            "corner_rotation": 2,
            "same_winding": True,
        },
        "generation_seconds": round(generation_seconds, 6),
        "elapsed_seconds": round(elapsed, 6),
        "hard_limit_seconds": TOPOLOGY_HARD_LIMIT_SECONDS,
        "evidence": {
            "first_face_map": int(mapping.fbx_face_for_max_face[0]),
            "last_face_map": int(mapping.fbx_face_for_max_face[-1]),
            "corner_map": list(expected_corner_map),
            "exact_face_count": int(mapping.exact_face_count),
            "cyclic_corner_face_count": int(mapping.cyclic_corner_face_count),
            "reordered_face_count": int(mapping.reordered_face_count),
        },
    }


def _max_array(values: Sequence[int]) -> Any:
    if rt is None:
        raise RuntimeError("当前进程没有 pymxs。")
    return rt.Array(*[int(value) for value in values])


def _run_max_batch_smoothing_case(topology: Any) -> Dict[str, Any]:
    if rt is None:
        return {
            "id": "max2023_batched_smoothing_50000_faces",
            "status": "skipped",
            "reason": "当前进程不是 3ds Max Batch；纯 Python 两项仍已执行。",
        }

    topology.ensure_runtime()
    rt.resetMaxFile(rt.Name("noPrompt"))
    node = None
    cleanup_ok = False
    try:
        generated_at = time.perf_counter()
        node = rt.Plane(
            name="F2M_Performance_Temporary_Plane",
            length=100.0,
            width=100.0,
            lengthsegs=MAX_POLY_COLUMNS,
            widthsegs=MAX_POLY_ROWS,
        )
        rt.convertToPoly(node)
        actual_face_count = int(rt.polyop.getNumFaces(node.baseObject))
        generation_seconds = time.perf_counter() - generated_at
        if actual_face_count != MAX_POLY_FACE_COUNT:
            raise AssertionError(
                f"Max 临时 Editable Poly 面数错误："
                f"{actual_face_count}/{MAX_POLY_FACE_COUNT}"
            )

        masks = tuple(1 << (index % 4) for index in range(MAX_POLY_FACE_COUNT))
        max_masks = _max_array(masks)

        started = time.perf_counter()
        batch_count = int(
            rt.F2M_Helper.setPolyFaceSmoothingGroupsBatched(
                node.baseObject,
                max_masks,
            )
        )
        rt.update(node)
        readback_raw = rt.F2M_Helper.getFaceSmoothingGroups(node)
        readback = tuple(int(value) for value in list(readback_raw))
        elapsed = time.perf_counter() - started

        if batch_count != 4:
            raise AssertionError(f"批量光滑组写入批次数错误：{batch_count}/4")
        if readback != masks:
            mismatch = next(
                (
                    index
                    for index, (expected, actual) in enumerate(
                        zip(masks, readback),
                        start=1,
                    )
                    if expected != actual
                ),
                None,
            )
            raise AssertionError(
                f"Max 批量光滑组写后读回不一致，首个差异面：{mismatch}"
            )
        if elapsed > MAX_BATCH_HARD_LIMIT_SECONDS:
            raise AssertionError(
                f"Max 50,000 面批量光滑组写入及全量读回耗时 {elapsed:.6f} 秒，"
                f"超过硬阈值 {MAX_BATCH_HARD_LIMIT_SECONDS:.1f} 秒"
            )

        return {
            "id": "max2023_batched_smoothing_50000_faces",
            "status": "passed",
            "input": {
                "rows": MAX_POLY_ROWS,
                "columns": MAX_POLY_COLUMNS,
                "face_count": MAX_POLY_FACE_COUNT,
                "base_object_class": str(rt.classOf(node.baseObject)),
                "mask_pattern": [1, 2, 4, 8],
            },
            "generation_seconds": round(generation_seconds, 6),
            "elapsed_seconds": round(elapsed, 6),
            "hard_limit_seconds": MAX_BATCH_HARD_LIMIT_SECONDS,
            "evidence": {
                "batch_count": batch_count,
                "readback_face_count": len(readback),
                "readback_matches": True,
                "helper_message": str(topology.helper_message()),
            },
        }
    finally:
        try:
            if node is not None and bool(rt.isValidNode(node)):
                rt.delete(node)
            rt.resetMaxFile(rt.Name("noPrompt"))
            cleanup_ok = len(list(rt.objects)) == 0
        finally:
            if not cleanup_ok:
                raise RuntimeError("Max 性能回归结束后未能清空临时场景。")


def _base_result() -> Dict[str, Any]:
    smoothing_path = os.path.join(RUNTIME_ROOT, "f2m_smoothing.py")
    topology_path = os.path.join(RUNTIME_ROOT, "f2m_topology_transfer.py")
    environment: Dict[str, Any] = {
        "inside_3ds_max": INSIDE_3DS_MAX,
        "process_id": os.getpid(),
        "python_executable": sys.executable,
        "python_version": sys.version,
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
    }
    if INSIDE_3DS_MAX:
        max_root = os.path.abspath(str(rt.getDir(rt.Name("maxroot"))))
        max_product_folder = os.path.basename(os.path.normpath(max_root))
        if max_product_folder.casefold() != "3ds max 2023":
            raise AssertionError(
                f"本性能回归要求 3ds Max 2023，实际 Max 根目录为 {max_root}"
            )
        environment.update(
            {
                "max_product_folder": max_product_folder,
                "max_product_year": 2023,
                "max_root": max_root,
            }
        )
    return {
        "schema_version": 1,
        "test": "FBXTo3dsMax performance regression",
        "started_at_utc": _utc_now(),
        "finished_at_utc": None,
        "overall_status": "running",
        "environment": environment,
        "core_files": {
            "f2m_smoothing.py": {
                "path": smoothing_path,
                "sha256": _sha256(smoothing_path),
            },
            "f2m_topology_transfer.py": {
                "path": topology_path,
                "sha256": _sha256(topology_path),
            },
        },
        "cases": [],
        "safety": {
            "isolated_batch_scene": INSIDE_3DS_MAX,
            "saved_scene": False,
            "user_asset_opened": False,
            "temporary_scene_cleared": False if INSIDE_3DS_MAX else None,
        },
    }


def _write_result(result: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(RESULT)), exist_ok=True)
    with open(RESULT, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> None:
    result = _base_result()
    try:
        smoothing = _load_module(
            "f2m_smoothing.py",
            "_f2m_performance_smoothing",
        )
        topology = _load_module(
            "f2m_topology_transfer.py",
            "_f2m_performance_topology",
        )
        result["tool_version"] = {
            "smoothing": str(smoothing.TOOL_VERSION),
            "topology": str(topology.TOOL_VERSION),
        }
        if result["tool_version"] != {
            "smoothing": "1.4.26",
            "topology": "1.4.26",
        }:
            raise AssertionError(f"性能回归加载到错误版本：{result['tool_version']}")

        result["cases"].append(_run_smoothing_case(smoothing))
        result["cases"].append(_run_topology_case(topology))
        result["cases"].append(_run_max_batch_smoothing_case(topology))
        if INSIDE_3DS_MAX:
            result["safety"]["temporary_scene_cleared"] = len(list(rt.objects)) == 0
        result["overall_status"] = "passed"
    except BaseException:
        result["overall_status"] = "failed"
        result["error"] = traceback.format_exc()
        raise
    finally:
        result["finished_at_utc"] = _utc_now()
        _write_result(result)


try:
    main()
except BaseException:
    raise
