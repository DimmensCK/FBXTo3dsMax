# -*- coding: utf-8 -*-
"""Real MaxBatch gate for the Mode-1 normals+SG Undo/Redo contract.

The gate creates an isolated target by importing the bundled topology fixture,
changes only its smoothing masks to a deterministic pre-transfer sentinel, and
then calls the production ``run_from_max`` entry.  The production per-object
``pymxs.undo`` label must be the sole undo entry.  One Undo and one Redo must
round-trip exact semantic snapshots of the target.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import re
import struct
import sys
import time
import traceback
from typing import Any, Dict, Iterable, List, Mapping, Tuple

import pymxs
from pymxs import runtime as rt


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_ROOT = os.path.join(ROOT, "contents") if os.path.isdir(os.path.join(ROOT, "contents")) else ROOT
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "topology_source.fbx")
MODULE_PATH = os.path.join(RUNTIME_ROOT, "f2m_topology_transfer.py")
DEFAULT_RESULT = os.path.join(
    ROOT,
    "tests",
    "_max_topology_undo_redo_v1320_result.json",
)
RUN_TOKEN_ENV = "F2M_TOPOLOGY_UNDO_REDO_RUN_TOKEN"
RESULT_ENV = "F2M_TOPOLOGY_GATE_RESULT"
SAVE_RELOAD_PATH_ENV = "F2M_TOPOLOGY_SAVE_RELOAD_PATH"
SAVE_RELOAD_RESULT_NAME = "_max_topology_save_reload_v1320_result.json"
_requested_result = os.path.abspath(
    os.environ.get(RESULT_ENV, DEFAULT_RESULT).strip() or DEFAULT_RESULT
)
_tests_root = os.path.abspath(os.path.join(ROOT, "tests"))
_allowed_result_names = {
    os.path.basename(DEFAULT_RESULT),
    SAVE_RELOAD_RESULT_NAME,
}
RESULT_CONFIGURATION_ERROR = ""
if (
    os.path.normcase(os.path.dirname(_requested_result))
    == os.path.normcase(_tests_root)
    and os.path.basename(_requested_result) in _allowed_result_names
):
    RESULT = _requested_result
else:
    RESULT = os.path.abspath(DEFAULT_RESULT)
    RESULT_CONFIGURATION_ERROR = (
        "Refused unsafe gate result path: " + _requested_result
    )
VERSION = "1.4.26"
FINAL_NORMAL_MODIFIER = "F2M_顶点法线"
MODULE_NAME = "_f2m_topology_undo_redo_v1320"
SG_REPORT_MARKER = "光滑组完成：已写入并回读验证"
RESIDUAL_REPORT_MARKER = (
    "；最终 Explicit 法线记录 "
)
ZERO_RESIDUAL_REPORT_MARKER = (
    "自定义法线残差为 0，保留一个全蓝色 Unspecified 的 "
    "F2M Edit Normals 基线"
)
FULL_OVERRIDE_REPORT_MARKERS = (
    "保留完整 FBX Explicit/Specified 法线作为最终着色权威",
    "不执行混合残差去冗余",
    "FBX 自定义法线作为最终着色权威，不执行残差混合",
)


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


def _feed_int(digest: "hashlib._Hash", value: int) -> None:
    digest.update(struct.pack("<q", int(value)))


def _feed_float(digest: "hashlib._Hash", value: float) -> None:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise RuntimeError(f"摘要遇到非有限浮点数：{numeric}")
    if numeric == 0.0:
        numeric = 0.0
    digest.update(struct.pack("<d", numeric))


def _feed_text(digest: "hashlib._Hash", value: str) -> None:
    encoded = str(value).encode("utf-8")
    _feed_int(digest, len(encoded))
    digest.update(encoded)


def _point3_tuple(value: Any) -> Tuple[float, float, float]:
    return (float(value.x), float(value.y), float(value.z))


def _feed_point3(digest: "hashlib._Hash", value: Any) -> None:
    for component in _point3_tuple(value):
        _feed_float(digest, component)


def _heap_text() -> str:
    return str(rt.execute("heapCheck() as string")).strip()


def _heap_ok(value: str) -> bool:
    return str(value).strip().casefold() in {"ok", "true"}


def _log_marker(kind: str, run_token: str, engine_pid: int, **fields: Any) -> None:
    parts = [
        f"F2M_TOPOLOGY_UNDO_REDO_{kind}",
        f"TOKEN={run_token}",
        f"PID={int(engine_pid)}",
    ]
    for key, value in fields.items():
        parts.append(f"{str(key).upper()}={value}")
    message = " ".join(parts)
    try:
        rt.logsystem.logEntry(message, broadcast=True)
    except Exception:
        escaped = message.replace("\\", "\\\\").replace('"', '\\"')
        rt.execute(f'logsystem.logEntry "{escaped}" broadcast:true')
    print(message, flush=True)


def _valid_node(node: Any) -> bool:
    if node is None or str(node) == "undefined":
        return False
    try:
        return bool(rt.isValidNode(node))
    except Exception:
        return False


def _node_by_handle(handle: int) -> Any:
    node = rt.getAnimByHandle(int(handle))
    if not _valid_node(node):
        return None
    return node


def _select_handle(handle: int) -> None:
    node = _node_by_handle(handle)
    if node is None:
        raise AssertionError(f"目标句柄已失效：{handle}")
    try:
        rt.select(node)
    finally:
        node = None


def _load_topology_module() -> Any:
    sys.modules.pop(MODULE_NAME, None)
    spec = importlib.util.spec_from_file_location(MODULE_NAME, MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    setattr(module, "_F2M_IMPORT_COMPLETE", True)
    actual_path = os.path.normcase(os.path.abspath(module.__file__))
    expected_path = os.path.normcase(os.path.abspath(MODULE_PATH))
    if actual_path != expected_path:
        raise RuntimeError(
            f"Undo/Redo 门加载到了错误模块：{actual_path}/{expected_path}"
        )
    if str(module.TOOL_VERSION) != VERSION:
        raise RuntimeError(
            f"Undo/Redo 门版本不一致：{module.TOOL_VERSION}/{VERSION}"
        )
    if not callable(getattr(module, "run_from_max", None)):
        raise RuntimeError("当前 topology 模块没有可调用的 run_from_max。")
    module.ensure_runtime()
    return module


def _assert_production_residual_contract() -> Dict[str, Any]:
    with open(MODULE_PATH, "r", encoding="utf-8") as handle:
        source = handle.read()
    process_start = source.index("def process_pair(")
    process_end = source.index(
        "def process_pair_transactional(",
        process_start,
    )
    process_source = source[process_start:process_end]
    smoothing_at = process_source.index("copy_smoothing_groups(")
    normals_at = process_source.index("copy_normals(", smoothing_at)
    baseline_lookup_pattern = (
        r"smoothing_baseline\s*=\s*"
        r"ctx\.smoothing_normal_baselines_by_name\.get\("
    )
    residual_selector_pattern = (
        r"use_smoothing_residual\s*=\s*"
        r"smoothing_baseline\s+is\s+not\s+None"
    )
    residual_argument_pattern = (
        r"smoothing_residual_only\s*=\s*use_smoothing_residual"
    )
    if smoothing_at >= normals_at:
        raise AssertionError(
            "生产 process_pair 没有先写光滑组、后写顶点法线。"
        )
    baseline_lookup_match = re.search(
        baseline_lookup_pattern,
        process_source,
    )
    residual_selector_match = re.search(
        residual_selector_pattern,
        process_source,
    )
    residual_argument_match = re.search(
        residual_argument_pattern,
        process_source[normals_at:],
    )
    if (
        baseline_lookup_match is None
        or residual_selector_match is None
        or residual_argument_match is None
    ):
        raise AssertionError(
            "生产组合路径没有从隔离导入 SG 基线选择 residual normal 模式。"
        )
    if "smoothing_residual_only=False" in process_source[normals_at:]:
        raise AssertionError(
            "生产组合路径仍硬编码为 exact/full normal override。"
        )
    return {
        "smoothing_call_offset": smoothing_at,
        "normal_call_offset": normals_at,
        "baseline_lookup": baseline_lookup_match.group(0),
        "residual_selector": residual_selector_match.group(0),
        "residual_argument": residual_argument_match.group(0),
        "source_order_verified": True,
    }


def _assert_runtime_residual_report(report_path: str) -> Dict[str, Any]:
    if not os.path.isfile(report_path):
        raise RuntimeError(f"正式传递报告不存在：{report_path}")
    with open(report_path, "r", encoding="utf-8") as handle:
        report_text = handle.read()
    smoothing_at = report_text.find(SG_REPORT_MARKER)
    residual_at = report_text.find(RESIDUAL_REPORT_MARKER)
    zero_residual_at = report_text.find(ZERO_RESIDUAL_REPORT_MARKER)
    zero_residual = zero_residual_at >= 0
    if zero_residual:
        residual_at = zero_residual_at
        marker = ZERO_RESIDUAL_REPORT_MARKER
    else:
        marker = RESIDUAL_REPORT_MARKER
    forbidden = [
        candidate
        for candidate in FULL_OVERRIDE_REPORT_MARKERS
        if candidate in report_text
    ]
    if smoothing_at < 0:
        raise AssertionError("正式报告缺少光滑组写入/读回完成标签。")
    if residual_at < 0:
        raise AssertionError("正式报告缺少 SG baseline + residual 法线标签。")
    if smoothing_at >= residual_at:
        raise AssertionError("正式报告没有证明 SG 先于 residual normals。")
    if forbidden:
        raise AssertionError(
            "正式报告仍接受 exact/full override 标签：" + str(forbidden)
        )
    return {
        "report_path": os.path.abspath(report_path),
        "report_sha256": _sha256_file(report_path),
        "smoothing_marker": SG_REPORT_MARKER,
        "residual_marker": marker,
        "zero_residual": zero_residual,
        "expected_final_f2m_count": 0 if zero_residual else 1,
        "smoothing_marker_offset": smoothing_at,
        "residual_marker_offset": residual_at,
        "full_override_markers": forbidden,
        "runtime_order_verified": True,
    }


def _assert_production_combo_contract() -> Dict[str, Any]:
    """Bind the gate to the current strict-resolver production combo."""

    with open(MODULE_PATH, "r", encoding="utf-8") as handle:
        source = handle.read()

    import_start = source.index("def import_fbx(")
    import_end = source.index("def imported_geometry_by_name(", import_start)
    import_source = source[import_start:import_end]
    inspect_at = import_source.index(
        "_inspect_smoothing_and_normal_data(ctx)"
    )
    exact_import_at = import_source.index(
        "_import_fbx_once(",
        inspect_at,
    )
    smoothing_false_at = import_source.index(
        "smoothing_groups=False",
        exact_import_at,
    )
    resolver_at = import_source.index(
        "_resolve_smoothing_masks_from_single_exact_import(",
        smoothing_false_at,
    )
    if not (
        inspect_at < exact_import_at < smoothing_false_at < resolver_at
    ):
        raise AssertionError(
            "Current combo no longer performs strict resolution before its "
            "single SmoothingGroups=false import is consumed."
        )

    process_start = source.index("def process_pair(")
    process_end = source.index(
        "def process_pair_transactional(",
        process_start,
    )
    process_source = source[process_start:process_end]
    smoothing_at = process_source.index("copy_smoothing_groups(")
    normals_at = process_source.index("copy_normals(", smoothing_at)
    residual_selector_pattern = (
        r"use_smoothing_residual\s*=\s*\(\s*"
        r"ctx\.options\.transfer_smoothing_groups\s+or\s+"
        r"target_record\.handle\s+in\s+"
        r"ctx\.existing_smoothing_masks_by_handle\s*\)"
    )
    residual_argument_pattern = (
        r"smoothing_residual_only\s*=\s*use_smoothing_residual"
    )
    residual_selector_match = re.search(
        residual_selector_pattern,
        process_source,
    )
    residual_argument_match = re.search(
        residual_argument_pattern,
        process_source[normals_at:],
    )
    if smoothing_at >= normals_at:
        raise AssertionError(
            "Current production process_pair no longer orders SG before "
            "custom normals."
        )
    if (
        residual_selector_match is None
        or residual_argument_match is None
    ):
        raise AssertionError(
            "Current production combo no longer selects the SG-aware "
            "residual normal route."
        )
    if "smoothing_residual_only=False" in process_source[normals_at:]:
        raise AssertionError(
            "Current production combo still hard-codes a full normal override."
        )

    return {
        "strict_resolver_call_offset": inspect_at,
        "single_exact_import_offset": exact_import_at,
        "single_exact_import_smoothing_false_offset": smoothing_false_at,
        "resolver_consume_offset": resolver_at,
        "smoothing_call_offset": smoothing_at,
        "normal_call_offset": normals_at,
        "residual_selector": residual_selector_match.group(0),
        "residual_argument": residual_argument_match.group(0),
        "strict_resolver_verified": True,
        "single_exact_import_verified": True,
        "source_order_verified": True,
    }


def _assert_runtime_combo_report(
    report_path: str,
    target_name: str,
) -> Dict[str, Any]:
    """Require a fresh non-empty production report for this exact target."""

    if not os.path.isfile(report_path):
        raise RuntimeError(
            f"Production transfer report does not exist: {report_path}"
        )
    with open(report_path, "r", encoding="utf-8") as handle:
        report_text = handle.read()
    if not report_text.strip():
        raise AssertionError("Production transfer report is empty.")
    if target_name not in report_text:
        raise AssertionError(
            "Production transfer report does not identify the gate target: "
            + target_name
        )
    forbidden = [
        candidate
        for candidate in FULL_OVERRIDE_REPORT_MARKERS
        if candidate in report_text
    ]
    if forbidden:
        raise AssertionError(
            "Production report still accepts a full normal override marker: "
            + str(forbidden)
        )
    if SG_REPORT_MARKER not in report_text:
        raise AssertionError(
            "Production report does not prove the complete SG write/readback."
        )
    zero_residual = ZERO_RESIDUAL_REPORT_MARKER in report_text
    nonzero_residual = RESIDUAL_REPORT_MARKER in report_text
    if zero_residual == nonzero_residual:
        raise AssertionError(
            "Production report does not identify exactly one zero/nonzero "
            "normal residual outcome."
        )
    # The residual route always retains one final stack-bottom Edit_Normals.
    # A zero residual is represented by the same modifier as an all-blue
    # Explicit=0/Specified=0 SG baseline, not by deleting the modifier and
    # exposing stale embedded base-object normals.
    expected_final_f2m_count = 1
    return {
        "report_path": os.path.abspath(report_path),
        "report_sha256": _sha256_file(report_path),
        "report_target": target_name,
        "report_target_verified": True,
        "full_override_markers": forbidden,
        "sg_write_readback_marker_verified": True,
        "zero_residual": zero_residual,
        "nonzero_residual": nonzero_residual,
        "expected_final_f2m_count": expected_final_f2m_count,
        "runtime_report_verified": True,
    }


def _modifier_entries(node: Any) -> Tuple[List[Dict[str, Any]], List[Any]]:
    entries: List[Dict[str, Any]] = []
    final_modifiers: List[Any] = []
    for index, modifier in enumerate(list(node.modifiers), start=1):
        name = str(modifier.name)
        class_name = str(rt.classOf(modifier))
        entries.append(
            {
                "index": index,
                "class": class_name,
                "name": name,
            }
        )
        if name == FINAL_NORMAL_MODIFIER and class_name.casefold() == (
            "Edit_Normals".casefold()
        ):
            final_modifiers.append(modifier)
        modifier = None
    return entries, final_modifiers


def _snapshot_final_normal_modifier(node: Any, modifier: Any) -> Dict[str, Any]:
    if not bool(rt.F2M_Helper.activateModifier(node, modifier)):
        raise RuntimeError(
            "无法激活最终 F2M Edit Normals：" + str(rt.F2M_Helper.lastMessage)
        )

    face_count = int(modifier.GetNumFaces(node=node))
    normal_count = int(modifier.GetNumNormals(node=node))
    if face_count < 1 or normal_count < 1:
        raise RuntimeError("最终 F2M Edit Normals 没有完整法线数据。")

    # The modifier's normal-pool allocation and normal IDs are not semantic
    # authority: Max may renumber records across a valid Undo/Redo.  Hash only
    # resolved face-corner direction plus vertex/Specified/Explicit state.
    corner_digest = hashlib.sha256()
    _feed_int(corner_digest, face_count)
    corner_count = 0
    specified_count = 0
    explicit_corner_count = 0
    explicit_count = sum(
        int(bool(modifier.GetNormalExplicit(index, node=node)))
        for index in range(1, normal_count + 1)
    )
    for face_index in range(1, face_count + 1):
        degree = int(modifier.GetFaceDegree(face_index, node=node))
        if degree < 3:
            raise RuntimeError(f"最终 F2M 法线第 {face_index} 面少于 3 个角。")
        _feed_int(corner_digest, face_index)
        _feed_int(corner_digest, degree)
        for corner_index in range(1, degree + 1):
            normal_id = int(
                modifier.GetNormalID(
                    face_index,
                    corner_index,
                    node=node,
                )
            )
            vertex_id = int(
                modifier.GetVertexID(
                    face_index,
                    corner_index,
                    node=node,
                )
            )
            specified = bool(
                modifier.GetFaceNormalSpecified(
                    face_index,
                    corner_index,
                    node=node,
                )
            )
            explicit = bool(
                modifier.GetNormalExplicit(normal_id, node=node)
            )
            direction = modifier.GetNormal(normal_id, node=node)
            specified_count += int(specified)
            explicit_corner_count += int(explicit)
            corner_count += 1
            _feed_int(corner_digest, corner_index)
            _feed_int(corner_digest, vertex_id)
            _feed_int(corner_digest, int(specified))
            _feed_int(corner_digest, int(explicit))
            _feed_point3(corner_digest, direction)

    return {
        "face_count": face_count,
        "normal_count": normal_count,
        "corner_count": corner_count,
        "explicit_count": explicit_count,
        "explicit_corner_count": explicit_corner_count,
        "specified_count": specified_count,
        "semantic_corner_sha256": corner_digest.hexdigest().upper(),
        "normal_ids_compared": False,
    }


def _snapshot_map_channel(mesh: Any, channel: int) -> Dict[str, Any]:
    digest = hashlib.sha256()
    _feed_int(digest, channel)
    supported = bool(rt.meshop.getMapSupport(mesh, channel))
    _feed_int(digest, int(supported))
    vertex_count = 0
    face_count = 0
    if supported:
        vertex_count = int(rt.meshop.getNumMapVerts(mesh, channel))
        face_count = int(rt.meshop.getNumMapFaces(mesh, channel))
        _feed_int(digest, vertex_count)
        _feed_int(digest, face_count)
        for map_vertex_index in range(1, vertex_count + 1):
            _feed_int(digest, map_vertex_index)
            _feed_point3(
                digest,
                rt.meshop.getMapVert(
                    mesh,
                    channel,
                    map_vertex_index,
                ),
            )
        for map_face_index in range(1, face_count + 1):
            map_face = rt.meshop.getMapFace(
                mesh,
                channel,
                map_face_index,
            )
            _feed_int(digest, map_face_index)
            _feed_int(digest, int(map_face.x))
            _feed_int(digest, int(map_face.y))
            _feed_int(digest, int(map_face.z))
    return {
        "channel": channel,
        "supported": supported,
        "vertex_count": vertex_count,
        "face_count": face_count,
        "sha256": digest.hexdigest().upper(),
    }


def _snapshot_target(handle: int) -> Dict[str, Any]:
    node = _node_by_handle(handle)
    if node is None:
        raise AssertionError(f"目标句柄已失效：{handle}")
    mesh = None
    try:
        rt.update(node)
        entries, final_modifiers = _modifier_entries(node)
        f2m_named = [
            entry["name"]
            for entry in entries
            if str(entry["name"]).startswith("F2M_")
        ]
        temporary_names = [
            name for name in f2m_named if name != FINAL_NORMAL_MODIFIER
        ]

        modifier_states: List[Dict[str, Any]] = []
        for modifier in final_modifiers:
            modifier_states.append(
                _snapshot_final_normal_modifier(node, modifier)
            )
            modifier = None
        final_modifiers.clear()

        base_point_values = (
            rt.F2M_Helper.captureBaseVertexPositions(node)
        )
        if (
            base_point_values is None
            or str(base_point_values) == "undefined"
        ):
            raise RuntimeError(
                "Undo/Redo snapshot could not read target base points."
            )
        base_points = list(base_point_values)
        base_point_values = None
        if not base_points:
            raise RuntimeError(
                "Undo/Redo snapshot could not read target base points."
            )
        base_point_digest = hashlib.sha256()
        _feed_int(base_point_digest, len(base_points))
        for base_point_index, base_point in enumerate(
            base_points,
            start=1,
        ):
            _feed_int(base_point_digest, base_point_index)
            _feed_point3(base_point_digest, base_point)
        base_point_count = len(base_points)
        base_points.clear()

        mesh = rt.snapshotAsMesh(node)
        vertex_count = int(rt.getNumVerts(mesh))
        face_count = int(rt.getNumFaces(mesh))
        if vertex_count < 1 or face_count < 1:
            raise RuntimeError("Undo/Redo 摘要读到空网格。")

        point_digest = hashlib.sha256()
        _feed_int(point_digest, vertex_count)
        for vertex_index in range(1, vertex_count + 1):
            _feed_int(point_digest, vertex_index)
            _feed_point3(point_digest, rt.getVert(mesh, vertex_index))

        topology_digest = hashlib.sha256()
        _feed_int(topology_digest, face_count)
        smoothing_digest = hashlib.sha256()
        _feed_int(smoothing_digest, face_count)
        smoothing_masks: List[int] = []
        for face_index in range(1, face_count + 1):
            face = rt.getFace(mesh, face_index)
            _feed_int(topology_digest, face_index)
            _feed_int(topology_digest, int(face.x))
            _feed_int(topology_digest, int(face.y))
            _feed_int(topology_digest, int(face.z))
            mask = int(rt.getFaceSmoothGroup(mesh, face_index))
            smoothing_masks.append(mask)
            _feed_int(smoothing_digest, mask)

        map_channels: Dict[str, Dict[str, Any]] = {}
        uv1 = _snapshot_map_channel(mesh, 1)
        for channel in range(-2, 100):
            channel_summary = (
                uv1
                if channel == 1
                else _snapshot_map_channel(mesh, channel)
            )
            if channel_summary["supported"]:
                map_channels[str(channel)] = channel_summary
        maps_summary = {
            "supported_channels": sorted(
                int(channel) for channel in map_channels
            ),
            "channels": map_channels,
            "sha256": _sha256_json(map_channels),
        }

        modifier_summary = {
            "count": len(entries),
            "entries": entries,
            "f2m_named": f2m_named,
            "temporary_f2m_names": temporary_names,
            "final_f2m_count": len(modifier_states),
            "sha256": _sha256_json(entries),
        }
        normal_summary = {
            "final_f2m_states": modifier_states,
            "sha256": _sha256_json(modifier_states),
        }
        summary: Dict[str, Any] = {
            "target_handle": int(handle),
            "target_name": str(node.name),
            "vertex_count": vertex_count,
            "face_count": face_count,
            "base_point_count": base_point_count,
            "base_point_sha256": base_point_digest.hexdigest().upper(),
            "point_sha256": point_digest.hexdigest().upper(),
            "topology_sha256": topology_digest.hexdigest().upper(),
            "uv1": uv1,
            "maps": maps_summary,
            "smoothing": {
                "face_count": face_count,
                "nonzero_face_count": sum(mask != 0 for mask in smoothing_masks),
                "unique_masks": sorted(set(smoothing_masks)),
                "sha256": smoothing_digest.hexdigest().upper(),
            },
            "modifiers": modifier_summary,
            "normals": normal_summary,
        }
        summary["fingerprint_sha256"] = _sha256_json(summary)
        return summary
    finally:
        free_error = ""
        if mesh is not None:
            try:
                rt.free(mesh)
            except Exception:
                free_error = traceback.format_exc()
        mesh = None
        node = None
        try:
            rt.execute(
                "(try(subObjectLevel = 0)catch(); "
                "try(setCommandPanelTaskMode #create)catch())"
            )
        except Exception:
            if not free_error:
                free_error = traceback.format_exc()
        if free_error:
            raise RuntimeError(
                "Undo/Redo 摘要无法安全释放临时 TriMesh/Modify 面板：\n"
                + free_error
            )


def _undo_level_count() -> int:
    return int(rt.theHold.getCurrentUndoLevels())


def _install_undo_callbacks() -> None:
    rt.execute(
        r"""
        callbacks.removeScripts id:#F2M_TOUR_gate
        global F2M_TOUR_sceneUndoLabels = #()
        global F2M_TOUR_sceneRedoLabels = #()
        callbacks.addScript #sceneUndo "append F2M_TOUR_sceneUndoLabels ((callbacks.notificationParam()) as string)" id:#F2M_TOUR_gate
        callbacks.addScript #sceneRedo "append F2M_TOUR_sceneRedoLabels ((callbacks.notificationParam()) as string)" id:#F2M_TOUR_gate
        """
    )


def _remove_undo_callbacks() -> None:
    try:
        rt.execute("callbacks.removeScripts id:#F2M_TOUR_gate")
    except Exception:
        pass


def _scene_undo_labels() -> List[str]:
    return [str(value) for value in list(rt.F2M_TOUR_sceneUndoLabels)]


def _scene_redo_labels() -> List[str]:
    return [str(value) for value in list(rt.F2M_TOUR_sceneRedoLabels)]


def _pump_posted_messages() -> None:
    try:
        rt.execute("try(windows.processPostedMessages())catch()")
    except Exception:
        pass


def _wait_for_callback_counts(
    undo_count: int,
    redo_count: int,
    timeout_seconds: float = 2.0,
) -> Tuple[List[str], List[str]]:
    """Let Max 2023 deliver sceneUndo/sceneRedo callback evidence."""

    deadline = time.time() + float(timeout_seconds)
    undo_labels: List[str] = []
    redo_labels: List[str] = []
    while True:
        _pump_posted_messages()
        undo_labels = _scene_undo_labels()
        redo_labels = _scene_redo_labels()
        if (
            len(undo_labels) >= int(undo_count)
            and len(redo_labels) >= int(redo_count)
        ):
            return undo_labels, redo_labels
        if time.time() >= deadline:
            return undo_labels, redo_labels
        time.sleep(0.01)


def _assert_only_expected_f2m(
    snapshot: Mapping[str, Any],
    expected_count: int,
) -> None:
    if expected_count not in (0, 1):
        raise AssertionError(f"无效的最终 F2M 修改器期望数：{expected_count}")
    modifiers = snapshot["modifiers"]
    expected_names = [FINAL_NORMAL_MODIFIER] if expected_count else []
    if int(modifiers["final_f2m_count"]) != expected_count:
        raise AssertionError(
            "最终 F2M 顶点法线修改器数量不符合 residual 结果："
            + str(modifiers)
        )
    if list(modifiers["f2m_named"]) != expected_names:
        raise AssertionError(
            "最终存在错误或临时 F2M 修改器：" + str(modifiers)
        )
    if list(modifiers["temporary_f2m_names"]):
        raise AssertionError(
            "最终残留 F2M 临时 baseline：" + str(modifiers)
        )


def _assert_pre_has_no_f2m(snapshot: Mapping[str, Any]) -> None:
    modifiers = snapshot["modifiers"]
    if list(modifiers["f2m_named"]):
        raise AssertionError(
            "传递前/Undo 后不应存在 F2M 修改器：" + str(modifiers)
        )
    if int(modifiers["final_f2m_count"]) != 0:
        raise AssertionError("传递前/Undo 后仍有最终 F2M 法线修改器。")


def _assert_final_f2m_at_stack_bottom(
    snapshot: Mapping[str, Any],
) -> Mapping[str, Any]:
    _assert_only_expected_f2m(snapshot, 1)
    modifiers = snapshot["modifiers"]
    entries = [
        entry
        for entry in modifiers["entries"]
        if (
            str(entry["name"]) == FINAL_NORMAL_MODIFIER
            and str(entry["class"]).casefold()
            == "Edit_Normals".casefold()
        )
    ]
    if len(entries) != 1:
        raise AssertionError(
            "Expected exactly one final F2M Edit Normals entry: "
            + str(modifiers)
        )
    entry = entries[0]
    if int(entry["index"]) != int(modifiers["count"]):
        raise AssertionError(
            "Final F2M Edit Normals is not at the bottom of the modifier "
            "stack: "
            + str(modifiers)
        )
    return entry


def _validate_gate_paths(
    result_path: str,
    save_reload_path: str,
    token: str,
) -> None:
    tests_root = os.path.abspath(os.path.join(ROOT, "tests"))
    expected_result_name = (
        SAVE_RELOAD_RESULT_NAME
        if save_reload_path
        else os.path.basename(DEFAULT_RESULT)
    )
    normalized_result = os.path.abspath(result_path)
    if (
        os.path.normcase(os.path.dirname(normalized_result))
        != os.path.normcase(tests_root)
        or os.path.basename(normalized_result) != expected_result_name
    ):
        raise RuntimeError(
            "Gate result path is not the exact expected tests artifact: "
            + normalized_result
        )
    if not save_reload_path:
        return
    normalized_save = os.path.abspath(save_reload_path)
    expected_save_name = (
        f"_max_topology_save_reload_v1320_{token}.tmp.max"
    )
    if (
        os.path.normcase(os.path.dirname(normalized_save))
        != os.path.normcase(tests_root)
        or os.path.basename(normalized_save) != expected_save_name
    ):
        raise RuntimeError(
            "Temporary save/reload path is not the exact token-bound tests "
            "artifact: "
            + normalized_save
        )


def _unique_geometry_handle_by_name(
    topology: Any,
    target_name: str,
) -> int:
    objects = list(rt.objects)
    matches: List[int] = []
    try:
        for node in objects:
            if (
                _valid_node(node)
                and str(node.name) == target_name
                and topology.is_geometry_node(node)
            ):
                matches.append(int(topology.node_handle(node)))
            node = None
    finally:
        objects.clear()
    if len(matches) != 1:
        raise AssertionError(
            "Save/reload did not restore exactly one target geometry named "
            f"{target_name}: {matches}"
        )
    return matches[0]


def _save_reload_verify(
    topology: Any,
    save_path: str,
    target_name: str,
    post_snapshot: Mapping[str, Any],
    expected_final_f2m_count: int,
    zero_residual: bool,
) -> Dict[str, Any]:
    _assert_only_expected_f2m(
        post_snapshot,
        expected_final_f2m_count,
    )
    post_bottom_entry: Dict[str, Any] = {}
    if expected_final_f2m_count:
        post_bottom_entry = dict(
            _assert_final_f2m_at_stack_bottom(post_snapshot)
        )
    if os.path.exists(save_path):
        raise RuntimeError(
            "Token-bound temporary Max file unexpectedly already exists: "
            + save_path
        )
    saved = bool(rt.saveMaxFile(save_path, quiet=True))
    if not saved or not os.path.isfile(save_path):
        raise RuntimeError(
            "3ds Max did not save the token-bound temporary scene: "
            + save_path
        )
    save_size = os.path.getsize(save_path)
    if save_size <= 0:
        raise RuntimeError("Temporary Max scene is empty: " + save_path)
    save_sha256 = _sha256_file(save_path)

    rt.execute(
        "(try(subObjectLevel = 0)catch(); "
        "try(setCommandPanelTaskMode #create)catch())"
    )
    rt.clearSelection()
    rt.resetMaxFile(rt.Name("noPrompt"))
    reset_objects = list(rt.objects)
    remaining_after_reset = len(reset_objects)
    reset_objects.clear()
    if remaining_after_reset != 0:
        raise RuntimeError(
            "Save/reload reset did not produce an empty scene."
        )
    loaded = bool(
        rt.loadMaxFile(
            save_path,
            useFileUnits=True,
            quiet=True,
        )
    )
    if not loaded:
        raise RuntimeError(
            "3ds Max did not reload the token-bound temporary scene: "
            + save_path
        )

    reloaded_handle = _unique_geometry_handle_by_name(
        topology,
        target_name,
    )
    reloaded_snapshot = _snapshot_target(reloaded_handle)
    _assert_only_expected_f2m(
        reloaded_snapshot,
        expected_final_f2m_count,
    )
    reloaded_bottom_entry: Dict[str, Any] = {}
    if expected_final_f2m_count:
        reloaded_bottom_entry = dict(
            _assert_final_f2m_at_stack_bottom(reloaded_snapshot)
        )
    if (
        post_snapshot["base_point_sha256"]
        != reloaded_snapshot["base_point_sha256"]
    ):
        raise AssertionError("Save/reload changed target base points.")
    if (
        post_snapshot["point_sha256"]
        != reloaded_snapshot["point_sha256"]
    ):
        raise AssertionError(
            "Save/reload changed evaluated target points."
        )
    if (
        post_snapshot["topology_sha256"]
        != reloaded_snapshot["topology_sha256"]
    ):
        raise AssertionError("Save/reload changed target topology.")
    if post_snapshot["uv1"] != reloaded_snapshot["uv1"]:
        raise AssertionError("Save/reload changed target UV1.")
    if post_snapshot["maps"] != reloaded_snapshot["maps"]:
        raise AssertionError("Save/reload changed target map channels.")
    if (
        post_snapshot["smoothing"]
        != reloaded_snapshot["smoothing"]
    ):
        raise AssertionError("Save/reload changed target smoothing groups.")
    if (
        post_snapshot["normals"]["final_f2m_states"]
        != reloaded_snapshot["normals"]["final_f2m_states"]
    ):
        raise AssertionError(
            "Save/reload changed final F2M Edit Normals semantic state."
        )
    post_final_state = post_snapshot["normals"]["final_f2m_states"][0]
    reloaded_final_state = (
        reloaded_snapshot["normals"]["final_f2m_states"][0]
    )
    zero_residual_blue_f2m_persisted = bool(
        not zero_residual
        or (
            int(post_final_state["explicit_count"]) == 0
            and int(post_final_state["specified_count"]) == 0
            and int(reloaded_final_state["explicit_count"]) == 0
            and int(reloaded_final_state["specified_count"]) == 0
        )
    )
    if not zero_residual_blue_f2m_persisted:
        raise AssertionError(
            "Save/reload zero-residual F2M is not all-blue "
            "Explicit=0/Specified=0."
        )

    undo_levels_after_reload = _undo_level_count()
    if undo_levels_after_reload != 0:
        raise AssertionError(
            "Save/reload did not clear the prior production Undo history: "
            + str(undo_levels_after_reload)
        )
    post_final_f2m_count = int(
        post_snapshot["modifiers"]["final_f2m_count"]
    )
    reloaded_final_f2m_count = int(
        reloaded_snapshot["modifiers"]["final_f2m_count"]
    )
    return {
        "temporary_max_path": os.path.abspath(save_path),
        "temporary_max_size": save_size,
        "temporary_max_sha256": save_sha256,
        "post_target_handle": int(post_snapshot["target_handle"]),
        "reloaded_target_handle": reloaded_handle,
        "post_bottom_entry": post_bottom_entry,
        "reloaded_bottom_entry": reloaded_bottom_entry,
        "expected_final_f2m_count": expected_final_f2m_count,
        "post_final_f2m_count": post_final_f2m_count,
        "reloaded_final_f2m_count": reloaded_final_f2m_count,
        "zero_residual": zero_residual,
        "zero_residual_blue_f2m_persisted": (
            zero_residual_blue_f2m_persisted
        ),
        "final_f2m_contract_verified": True,
        "base_points_exact": True,
        "evaluated_points_exact": True,
        "topology_exact": True,
        "uv1_exact": True,
        "all_map_channels_exact": True,
        "smoothing_groups_exact": True,
        "edit_normals_semantic_state_exact": True,
        "final_f2m_at_stack_bottom": bool(
            expected_final_f2m_count == 0
            or (
                post_bottom_entry
                and reloaded_bottom_entry
            )
        ),
        "undo_level_count_after_reload": undo_levels_after_reload,
        "verified": True,
        "reloaded_snapshot": reloaded_snapshot,
    }


def _safe_reset() -> None:
    rt.execute(
        "(try(subObjectLevel = 0)catch(); "
        "try(setCommandPanelTaskMode #create)catch())"
    )
    rt.clearSelection()
    rt.resetMaxFile(rt.Name("noPrompt"))
    reset_objects = list(rt.objects)
    remaining = len(reset_objects)
    reset_objects.clear()
    if remaining != 0:
        raise RuntimeError(f"Undo/Redo 门最终 reset 后仍有 {remaining} 个节点。")


def _write_payload_atomic(payload: Mapping[str, Any]) -> None:
    token = str(payload.get("run_token", "invalid"))
    temporary = RESULT + "." + token + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, RESULT)


run_token = os.environ.get(RUN_TOKEN_ENV, "").strip()
save_reload_path = os.path.abspath(
    os.environ.get(SAVE_RELOAD_PATH_ENV, "").strip()
) if os.environ.get(SAVE_RELOAD_PATH_ENV, "").strip() else ""
save_reload_requested = bool(save_reload_path)
payload: Dict[str, Any] = {
    "schema_version": 1,
    "test": (
        "Mode-1 normals+smoothing save/reload acceptance"
        if save_reload_requested
        else "Mode-1 normals+smoothing Undo/Redo acceptance"
    ),
    "gate_mode": "save_reload" if save_reload_requested else "undo_redo",
    "save_reload_requested": save_reload_requested,
    "ok": False,
    "version": VERSION,
    "run_token": run_token,
    "engine_pid": os.getpid(),
    "started_at_utc_epoch": time.time(),
    "finished_at_utc_epoch": 0.0,
    "gate_script_path": os.path.abspath(__file__),
    "gate_script_sha256": "",
    "result_path": os.path.abspath(RESULT),
    "module_path": os.path.abspath(MODULE_PATH),
    "module_sha256": "",
    "fixture": os.path.abspath(FIXTURE),
    "fixture_sha256": "",
    "target_handle": 0,
    "target_name": "",
    "expected_transaction_label": "",
    "normal_contract": {},
    "normal_semantics_preserved_through_redo": False,
    "undo_names_after_transfer": [],
    "undo_names_after_undo": [],
    "redo_names_after_undo": [],
    "undo_names_after_redo": [],
    "redo_names_after_redo": [],
    "undo_level_count_before_transfer": -1,
    "undo_level_count_after_transfer": -1,
    "undo_level_count_after_undo": -1,
    "undo_level_count_after_redo": -1,
    "scene_undo_labels": [],
    "scene_redo_labels": [],
    "heap_check_before": "",
    "heap_check_after_undo": "",
    "heap_check_after_redo": "",
    "snapshots": {},
    "comparison": {},
    "save_reload": {},
    "temporary_max_removed": not save_reload_requested,
    "report_path": "",
    "cleanup_reset": False,
    "error": "",
    "cleanup_error": "",
}

topology = None
setup_context = None
imported: List[Any] = []
targets: List[Any] = []
target = None
_log_marker(
    "BEGIN",
    run_token,
    int(payload["engine_pid"]),
)
try:
    if re.fullmatch(r"[0-9a-fA-F]{32}", run_token) is None:
        raise RuntimeError(
            f"{RUN_TOKEN_ENV} 必须是启动器提供的 32 位十六进制令牌。"
        )
    if RESULT_CONFIGURATION_ERROR:
        raise RuntimeError(RESULT_CONFIGURATION_ERROR)
    _validate_gate_paths(
        RESULT,
        save_reload_path,
        run_token,
    )
    payload["gate_script_sha256"] = _sha256_file(__file__)
    payload["module_sha256"] = _sha256_file(MODULE_PATH)
    payload["fixture_sha256"] = _sha256_file(FIXTURE)
    payload["heap_check_before"] = _heap_text()
    if not _heap_ok(payload["heap_check_before"]):
        raise AssertionError(
            "Undo/Redo 门执行前 heapCheck 失败："
            + payload["heap_check_before"]
        )

    topology = _load_topology_module()
    payload["normal_contract"] = _assert_production_combo_contract()
    rt.resetMaxFile(rt.Name("noPrompt"))
    setup_options = topology.TransferOptions(
        fbx_path=FIXTURE,
        mode="topology_only",
        dry_run=True,
        transfer_shape=False,
        transfer_uv=False,
        transfer_normals=True,
        transfer_smoothing_groups=True,
    )
    setup_context = topology.TransferContext(
        setup_options,
        topology.TransferLog(),
    )
    imported = list(
        topology._import_fbx_once(
            setup_context,
            smoothing_groups=False,
        )
    )
    targets = [
        node
        for node in imported
        if topology.is_geometry_node(node)
    ]
    if len(targets) != 1:
        raise AssertionError(
            f"topology_source.fbx 应隔离导入恰好 1 个目标网格，实际 {len(targets)}。"
        )
    target = targets[0]
    target_handle = int(topology.node_handle(target))
    target_name = str(target.name)
    payload["target_handle"] = target_handle
    payload["target_name"] = target_name

    setup_context.imported_nodes.clear()
    topology._release_context_node_references(setup_context)
    imported.clear()
    targets.clear()
    setup_context = None

    face_count = int(topology.base_face_count(target))
    if face_count < 1:
        raise AssertionError("隔离目标没有基础面。")
    if not bool(
        rt.F2M_Helper.setFaceSmoothingGroups(
            target,
            topology.max_array([0] * face_count),
        )
    ):
        raise RuntimeError(
            "无法建立确定性的传递前 SG=0 sentinel："
            + str(rt.F2M_Helper.lastMessage)
        )
    target = None

    # This is a dedicated disposable scene.  Clear setup/import history once,
    # before the production call, so the production per-object transaction
    # must become the sole entry exercised by exactly one Undo and one Redo.
    rt.clearUndoBuffer()
    payload["undo_level_count_before_transfer"] = _undo_level_count()
    if payload["undo_level_count_before_transfer"] != 0:
        raise AssertionError("正式传递前无法建立空 Undo/Redo 栈。")
    _install_undo_callbacks()

    before = _snapshot_target(target_handle)
    _assert_pre_has_no_f2m(before)
    _select_handle(target_handle)
    topology.run_from_max(
        fbx_path=FIXTURE,
        mode="topology_only",
        dry_run=False,
        transfer_shape=False,
        transfer_uv=False,
        uv_channels="",
        transfer_normals=True,
        transfer_smoothing_groups=True,
        transfer_vertex_color=False,
        transfer_alpha=False,
        transfer_material_ids=False,
        keep_imported=False,
        backup_old_mesh=True,
        include_hidden=True,
        keep_target_material_on_replace=False,
        limit_to_selection=False,
        show_ui=False,
    )
    if not bool(topology.LAST_RUN_OK):
        raise AssertionError(
            "normals+SG 正式传递失败：" + str(topology.LAST_RUN_SUMMARY)
        )
    payload["report_path"] = str(topology.LAST_RUN_REPORT_PATH)
    payload["normal_contract"].update(
        _assert_runtime_combo_report(
            payload["report_path"],
            target_name,
        )
    )
    expected_final_f2m_count = int(
        payload["normal_contract"]["expected_final_f2m_count"]
    )
    zero_residual = bool(payload["normal_contract"]["zero_residual"])

    after = _snapshot_target(target_handle)
    _assert_only_expected_f2m(after, expected_final_f2m_count)
    post_bottom_entry: Dict[str, Any] = {}
    if expected_final_f2m_count:
        post_bottom_entry = dict(
            _assert_final_f2m_at_stack_bottom(after)
        )
    if expected_final_f2m_count:
        final_state = after["normals"]["final_f2m_states"][0]
        residual_not_full_override = (
            int(final_state["specified_count"])
            < int(final_state["corner_count"])
            or int(final_state["explicit_corner_count"])
            < int(final_state["corner_count"])
        )
    else:
        residual_not_full_override = True
    zero_residual_blue_f2m = bool(
        not zero_residual
        or (
            int(final_state["explicit_count"]) == 0
            and int(final_state["specified_count"]) == 0
        )
    )
    if not zero_residual_blue_f2m:
        raise AssertionError(
            "零残差报告没有留下全蓝色 "
            "Explicit=0/Specified=0 的最终 F2M。"
        )
    if not residual_not_full_override:
        raise AssertionError(
            "topology_source 组合结果仍是全量 Explicit/Specified override，"
            "没有扣除 SG 已表达的法线。"
        )
    if (
        before["base_point_sha256"]
        != after["base_point_sha256"]
    ):
        raise AssertionError(
            "normals+SG transfer unexpectedly changed base points."
        )
    if before["point_sha256"] != after["point_sha256"]:
        raise AssertionError("normals+SG 传递意外改变了点。")
    if before["topology_sha256"] != after["topology_sha256"]:
        raise AssertionError("normals+SG 传递意外改变了拓扑。")
    if before["uv1"] != after["uv1"]:
        raise AssertionError("normals+SG 传递意外改变了 UV1。")
    if before["maps"] != after["maps"]:
        raise AssertionError("normals+SG 传递意外改变了其它 Map 通道。")
    if before["smoothing"]["sha256"] == after["smoothing"]["sha256"]:
        raise AssertionError("SG=0 sentinel 没有被正式光滑组传递改变。")
    if before["fingerprint_sha256"] == after["fingerprint_sha256"]:
        raise AssertionError("正式传递前后摘要没有发生可观测变化。")

    expected_label = f"FBXTo3dsMax v{topology.TOOL_VERSION}: {target_name}"
    payload["expected_transaction_label"] = expected_label
    payload["undo_level_count_after_transfer"] = _undo_level_count()
    # MaxBatch may expose a valid pymxs transaction as either 0 or 1 through
    # theHold.  The real acceptance is the labelled Undo/Redo callbacks plus
    # the exact before/after semantic round-trip below.
    if payload["undo_level_count_after_transfer"] not in (0, 1):
        raise AssertionError(
            "正式传递形成了异常数量的对象级事务："
            + str(payload["undo_level_count_after_transfer"])
        )
    if _scene_undo_labels() or _scene_redo_labels():
        raise AssertionError("正式传递前意外触发了 Undo/Redo 回调。")

    pymxs.run_undo()
    undo_callback_labels, redo_callback_labels = (
        _wait_for_callback_counts(1, 0)
    )
    payload["undo_level_count_after_undo"] = _undo_level_count()
    payload["scene_undo_labels"] = undo_callback_labels
    payload["scene_redo_labels"] = redo_callback_labels
    if payload["undo_level_count_after_undo"] not in (0, 1):
        raise AssertionError(
            "一次 Undo 后 Batch 报告了异常 Undo 层数："
            + str(payload["undo_level_count_after_undo"])
        )
    if len(payload["scene_undo_labels"]) > 1:
        raise AssertionError(
            "一次 Undo 触发了多余回调："
            + str(payload["scene_undo_labels"])
        )
    if payload["scene_redo_labels"]:
        raise AssertionError("一次 Undo 时意外触发了 Redo 回调。")
    after_undo = _snapshot_target(target_handle)
    payload["heap_check_after_undo"] = _heap_text()
    if not _heap_ok(payload["heap_check_after_undo"]):
        raise AssertionError(
            "一次 Undo 后 heapCheck 失败："
            + payload["heap_check_after_undo"]
        )
    _assert_pre_has_no_f2m(after_undo)
    if after_undo != before:
        raise AssertionError(
            "一次 Undo 没有精确回到传递前摘要："
            f"{after_undo['fingerprint_sha256']}/"
            f"{before['fingerprint_sha256']}"
        )
    pymxs.run_redo()
    undo_callback_labels, redo_callback_labels = (
        _wait_for_callback_counts(1, 1)
    )
    payload["undo_level_count_after_redo"] = _undo_level_count()
    payload["scene_undo_labels"] = undo_callback_labels
    payload["scene_redo_labels"] = redo_callback_labels
    if payload["undo_level_count_after_redo"] not in (0, 1):
        raise AssertionError(
            "一次 Redo 后形成了异常数量的 Undo 事务："
            + str(payload["undo_level_count_after_redo"])
        )
    if len(payload["scene_undo_labels"]) > 1:
        raise AssertionError(
            "Redo 后 Undo 回调数量异常："
            + str(payload["scene_undo_labels"])
        )
    if len(payload["scene_redo_labels"]) > 1:
        raise AssertionError(
            "一次 Redo 触发了多余回调："
            + str(payload["scene_redo_labels"])
        )
    after_redo = _snapshot_target(target_handle)
    payload["heap_check_after_redo"] = _heap_text()
    if not _heap_ok(payload["heap_check_after_redo"]):
        raise AssertionError(
            "一次 Redo 后 heapCheck 失败："
            + payload["heap_check_after_redo"]
        )
    _assert_only_expected_f2m(after_redo, expected_final_f2m_count)
    redo_bottom_entry: Dict[str, Any] = {}
    if expected_final_f2m_count:
        redo_bottom_entry = dict(
            _assert_final_f2m_at_stack_bottom(after_redo)
        )
    redo_final_state = after_redo["normals"]["final_f2m_states"][0]
    zero_residual_blue_f2m_after_redo = bool(
        not zero_residual
        or (
            int(redo_final_state["explicit_count"]) == 0
            and int(redo_final_state["specified_count"]) == 0
        )
    )
    if not zero_residual_blue_f2m_after_redo:
        raise AssertionError(
            "Redo 后零残差 F2M 不再是全蓝色 "
            "Explicit=0/Specified=0。"
        )
    semantic_fields = (
        "semantic_corner_sha256",
        "corner_count",
        "explicit_count",
        "explicit_corner_count",
        "specified_count",
    )
    normal_semantics_preserved_through_redo = all(
        final_state[field] == redo_final_state[field]
        for field in semantic_fields
    )
    if not normal_semantics_preserved_through_redo:
        raise AssertionError(
            "Redo changed final F2M face-corner semantic normals: "
            + str(
                {
                    field: (final_state[field], redo_final_state[field])
                    for field in semantic_fields
                }
            )
        )
    payload["normal_semantics_preserved_through_redo"] = True
    if after_redo != after:
        raise AssertionError(
            "一次 Redo 没有精确回到传递后摘要："
            f"{after_redo['fingerprint_sha256']}/"
            f"{after['fingerprint_sha256']}"
        )
    if save_reload_requested:
        payload["save_reload"] = {
            "requested": True,
            **_save_reload_verify(
                topology,
                save_reload_path,
                target_name,
                after_redo,
                expected_final_f2m_count,
                bool(payload["normal_contract"]["zero_residual"]),
            ),
        }
    else:
        payload["save_reload"] = {
            "requested": False,
            "verified": True,
        }
    payload["snapshots"] = {
        "before": before,
        "after": after,
        "after_undo": after_undo,
        "after_redo": after_redo,
    }
    payload["comparison"] = {
        "base_points_preserved_by_transfer": (
            before["base_point_sha256"]
            == after["base_point_sha256"]
        ),
        "points_preserved_by_transfer": (
            before["point_sha256"] == after["point_sha256"]
        ),
        "topology_preserved_by_transfer": (
            before["topology_sha256"] == after["topology_sha256"]
        ),
        "uv1_preserved_by_transfer": before["uv1"] == after["uv1"],
        "all_map_channels_preserved_by_transfer": (
            before["maps"] == after["maps"]
        ),
        "smoothing_changed_by_transfer": (
            before["smoothing"]["sha256"]
            != after["smoothing"]["sha256"]
        ),
        "current_combo_contract_verified": (
            payload["normal_contract"]["source_order_verified"]
            and payload["normal_contract"]["strict_resolver_verified"]
            and payload["normal_contract"]["single_exact_import_verified"]
            and payload["normal_contract"]["runtime_report_verified"]
        ),
        "residual_not_full_override": residual_not_full_override,
        "expected_final_f2m_count": expected_final_f2m_count,
        "post_f2m_at_stack_bottom": bool(
            expected_final_f2m_count == 0
            or post_bottom_entry
        ),
        "zero_residual_blue_f2m": bool(
            zero_residual_blue_f2m
            and zero_residual_blue_f2m_after_redo
        ),
        "nonzero_residual_f2m_at_stack_bottom": bool(
            expected_final_f2m_count == 0
            or (
                post_bottom_entry
                and redo_bottom_entry
            )
        ),
        "normal_semantics_preserved_through_redo": (
            normal_semantics_preserved_through_redo
        ),
        "pre_equals_after_undo": before == after_undo,
        "post_equals_after_redo": after == after_redo,
        "undo_has_no_f2m_baseline": (
            not after_undo["modifiers"]["f2m_named"]
        ),
        "redo_has_only_final_f2m": (
            after_redo["modifiers"]["f2m_named"]
            == (
                [FINAL_NORMAL_MODIFIER]
                if expected_final_f2m_count
                else []
            )
        ),
        "save_reload_verified": bool(
            payload["save_reload"]["verified"]
        ),
    }
    payload["ok"] = all(payload["comparison"].values())
except BaseException:
    payload["error"] = traceback.format_exc()
    payload["ok"] = False
finally:
    target = None
    targets.clear()
    imported.clear()
    if setup_context is not None and topology is not None:
        try:
            setup_context.imported_nodes.clear()
            topology._release_context_node_references(setup_context)
        except BaseException:
            if not payload["cleanup_error"]:
                payload["cleanup_error"] = traceback.format_exc()
    setup_context = None
    topology = None
    sys.modules.pop(MODULE_NAME, None)
    _remove_undo_callbacks()
    try:
        _safe_reset()
        payload["cleanup_reset"] = True
    except BaseException:
        payload["cleanup_error"] = traceback.format_exc()
        payload["ok"] = False
    if save_reload_requested:
        try:
            _validate_gate_paths(
                RESULT,
                save_reload_path,
                run_token,
            )
            if os.path.isfile(save_reload_path):
                os.remove(save_reload_path)
            if os.path.exists(save_reload_path):
                raise RuntimeError(
                    "Token-bound temporary Max file still exists after "
                    "cleanup: "
                    + save_reload_path
                )
            payload["temporary_max_removed"] = True
        except BaseException:
            cleanup_detail = traceback.format_exc()
            if payload["cleanup_error"]:
                payload["cleanup_error"] += "\n" + cleanup_detail
            else:
                payload["cleanup_error"] = cleanup_detail
            payload["temporary_max_removed"] = False
            payload["ok"] = False
    payload["finished_at_utc_epoch"] = time.time()
    try:
        _write_payload_atomic(payload)
    except BaseException:
        payload["ok"] = False
        raise
    _log_marker(
        "END",
        run_token,
        int(payload["engine_pid"]),
        ok=str(bool(payload["ok"])).lower(),
    )

if not payload["ok"]:
    raise RuntimeError(
        "Topology Undo/Redo gate failed; inspect its JSON result."
    )
