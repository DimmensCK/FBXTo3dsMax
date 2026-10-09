# -*- coding: utf-8 -*-
"""Historical world-space gate requiring caller-owned private test data.

Supply an external F2M_PRIVATE_MAX_FIXTURE scene, F2M_PRIVATE_FBX_VARIANT1/2
and optional F2M_PRIVATE_NODE_A/B selectors. No private assets are distributed.
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
from typing import Any, Iterable, Sequence

from pymxs import runtime as rt


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_ROOT = os.path.join(ROOT, "contents") if os.path.isdir(os.path.join(ROOT, "contents")) else ROOT
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
FBX_002 = _required_private_path("F2M_PRIVATE_FBX_VARIANT1")
FBX_003 = _required_private_path("F2M_PRIVATE_FBX_VARIANT2")
TARGET_002 = os.environ.get("F2M_PRIVATE_NODE_B", "ExampleMeshB")
TARGET_003 = os.environ.get("F2M_PRIVATE_NODE_A", "ExampleMeshA")
RESULT = os.path.join(os.environ["LOCALAPPDATA"], "FBXTo3dsMax", "Validation",
                      "_max_user_reported_regressions_v1321_result.json")
os.makedirs(os.path.dirname(RESULT), exist_ok=True)
TEMP_DIR = os.path.join(os.environ["LOCALAPPDATA"], "FBXTo3dsMax", "Tests")
TEMP_MAX = os.path.join(TEMP_DIR, f"mode2_003_{uuid.uuid4().hex}.max")
POSITION_TOLERANCE = 0.001
BOOLEAN_IMPORTER_PARAMS = {"Animation", "Skin", "SmoothingGroups"}
EXPECTED_VERSION = "1.4.25"


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
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    loaded = os.path.normcase(os.path.abspath(str(module.__file__)))
    expected = os.path.normcase(os.path.abspath(path))
    if loaded != expected:
        raise RuntimeError(f"模块路径不一致：{loaded}/{expected}")
    actual_version = str(getattr(module, "TOOL_VERSION", ""))
    if actual_version != EXPECTED_VERSION:
        raise RuntimeError(
            f"模块版本不一致：{filename}={actual_version}, "
            f"expected={EXPECTED_VERSION}"
        )
    module.ensure_runtime()
    return module


def matrix_tuple(value: Any) -> tuple[float, ...]:
    output: list[float] = []
    for row_name in ("row1", "row2", "row3", "row4"):
        row = getattr(value, row_name)
        output.extend((float(row.x), float(row.y), float(row.z)))
    return tuple(output)


def point_tuple(value: Any) -> tuple[float, float, float]:
    return (float(value.x), float(value.y), float(value.z))


def evaluated_world_positions(node: Any) -> list[tuple[float, float, float]]:
    """Capture evaluated geometry directly; do not reuse a transfer formula."""

    mesh = None
    try:
        mesh = rt.snapshotAsMesh(node)
        transform = node.objectTransform
        return [
            point_tuple(rt.getVert(mesh, index) * transform)
            for index in range(1, int(rt.getNumVerts(mesh)) + 1)
        ]
    finally:
        if mesh is not None:
            try:
                rt.free(mesh)
            except Exception:
                pass


def bbox(points: Sequence[Sequence[float]]) -> dict[str, list[float]]:
    return {
        "min": [min(point[axis] for point in points) for axis in range(3)],
        "max": [max(point[axis] for point in points) for axis in range(3)],
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
            f"{label} 世界空间顶点不一致：最大差 {maximum}，顶点 {worst}，"
            f"允许 {POSITION_TOLERANCE}"
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
        math.sqrt(sum((float(left) - float(right)) ** 2 for left, right in zip(a, b)))
        for a, b in zip(expected, actual)
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
        settings = {
            "Mode": rt.Name("create"),
            "Animation": False,
            "Skin": True,
            "SmoothingGroups": False,
        }
        for name, value in settings.items():
            set_importer_param(name, value)
        escaped = path.replace("\\", "\\\\").replace('"', '\\"')
        result = rt.execute(f'importFile "{escaped}" #noPrompt')
        if result is False or str(result).strip().lower() == "false":
            raise RuntimeError(f"导入失败：{path}")
    finally:
        for name, value in snapshot.items():
            set_importer_param(name, value)


def reset_scene() -> None:
    rt.clearSelection()
    if not bool(rt.resetMaxFile(rt.Name("noPrompt"))):
        raise RuntimeError("resetMaxFile 返回 false。")


def direct_fbx_reference(path: str, target_name: str) -> dict[str, Any]:
    reset_scene()
    import_fbx_isolated(path)
    node = rt.getNodeByName(target_name)
    if node is None or str(node) == "undefined":
        raise RuntimeError(f"FBX 缺少目标网格：{target_name}")
    points = evaluated_world_positions(node)
    return {
        "points": points,
        "vertex_count": len(points),
        "bbox": bbox(points),
        "object_transform": matrix_tuple(node.objectTransform),
        "pivot": point_tuple(node.pivot),
    }


def load_user_scene_and_select(name: str) -> Any:
    reset_scene()
    if not bool(rt.loadMaxFile(MAX_PATH, useFileUnits=True, quiet=True)):
        raise RuntimeError("无法加载 PrivateFixture 场景。")
    node = rt.getNodeByName(name)
    if node is None or str(node) == "undefined":
        raise RuntimeError(f"PrivateFixture 场景缺少目标：{name}")
    rt.select(node)
    return node


def assert_close_sequence(left: Iterable[float], right: Iterable[float], label: str) -> None:
    left_values = tuple(float(value) for value in left)
    right_values = tuple(float(value) for value in right)
    if len(left_values) != len(right_values) or any(
        abs(a - b) > 1.0e-6 for a, b in zip(left_values, right_values)
    ):
        raise AssertionError(f"{label} 发生变化：{left_values}/{right_values}")


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
    "assets": {},
    "modules": {},
    "mode1_002": {},
    "mode2_003": {},
    "error": "",
    "cleanup_error": "",
}

try:
    assets_before = {
        os.path.basename(path): sha256_file(path)
        for path in (MAX_PATH, FBX_002, FBX_003)
    }
    payload["assets"] = assets_before

    expected_002 = direct_fbx_reference(FBX_002, TARGET_002)
    node_002 = load_user_scene_and_select(TARGET_002)
    handle_002 = int(rt.getHandleByAnim(node_002))
    initial_delta_002 = max(
        position_deltas(expected_002["points"], evaluated_world_positions(node_002)),
        default=0.0,
    )
    if initial_delta_002 <= POSITION_TOLERANCE:
        raise AssertionError(
            "002 模式一调用前已与 FBX 参考一致，门无法证明本次传递实际生效。"
        )
    tm_before = matrix_tuple(node_002.objectTransform)
    pivot_before = point_tuple(node_002.pivot)
    topology = load_module("f2m_topology_transfer.py", "_f2m_reported_002")
    payload["modules"]["topology"] = {
        "path": os.path.abspath(str(topology.__file__)),
        "sha256": sha256_file(str(topology.__file__)),
        "version": str(topology.TOOL_VERSION),
    }
    importer_before_002 = snapshot_importer()
    summary_002 = topology.run_from_max(
        FBX_002,
        mode="topology_only",
        dry_run=False,
        transfer_shape=True,
        transfer_uv=False,
        transfer_normals=False,
        transfer_smoothing_groups=False,
        transfer_vertex_color=False,
        transfer_alpha=False,
        transfer_material_ids=False,
        keep_imported=False,
        show_ui=False,
    )
    importer_restore_002 = assert_importer_restored(
        importer_before_002,
        "002 模式一",
    )
    if not bool(topology.LAST_RUN_OK):
        raise AssertionError(f"002 模式一正式执行失败：{summary_002}")
    final_002 = rt.getAnimByHandle(handle_002)
    assert_close_sequence(tm_before, matrix_tuple(final_002.objectTransform), "002 objectTransform")
    assert_close_sequence(pivot_before, point_tuple(final_002.pivot), "002 pivot")
    comparison_002 = compare_positions(
        expected_002["points"],
        evaluated_world_positions(final_002),
        f"variant1/{TARGET_002}",
    )
    payload["mode1_002"] = {
        **comparison_002,
        "node_handle_preserved": int(rt.getHandleByAnim(final_002)) == handle_002,
        "object_transform_preserved": True,
        "pivot_preserved": True,
        "initial_max_world_delta": initial_delta_002,
        "summary": str(summary_002),
        "report_path": os.path.abspath(str(topology.LAST_RUN_REPORT_PATH)),
        "importer_restore": importer_restore_002,
    }

    expected_003 = direct_fbx_reference(FBX_003, TARGET_003)
    old_003 = load_user_scene_and_select(TARGET_003)
    old_handle_003 = int(rt.getHandleByAnim(old_003))
    skin = load_module("f2m_skin_replace.py", "_f2m_reported_003")
    payload["modules"]["skin"] = {
        "path": os.path.abspath(str(skin.__file__)),
        "sha256": sha256_file(str(skin.__file__)),
        "version": str(skin.TOOL_VERSION),
    }
    importer_before_003 = snapshot_importer()
    summary_003 = skin.run_from_max(
        FBX_003,
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
    importer_restore_003 = assert_importer_restored(
        importer_before_003,
        "003 模式二",
    )
    if not bool(skin.LAST_RUN_OK):
        raise AssertionError(f"003 模式二正式执行失败：{summary_003}")
    final_003 = rt.getNodeByName(TARGET_003)
    if final_003 is None or str(final_003) == "undefined":
        raise AssertionError("003 替换后缺少最终目标节点。")
    if int(rt.F2M_Helper.countSkin(final_003)) != 1:
        raise AssertionError("003 替换后最终节点没有且仅有一个 Skin。")
    final_handle_003 = int(rt.getHandleByAnim(final_003))
    if final_handle_003 == old_handle_003:
        raise AssertionError("003 模式二没有以 FBX 候选替换旧 Max 节点。")
    comparison_003 = compare_positions(
        expected_003["points"],
        evaluated_world_positions(final_003),
        f"variant2/{TARGET_003}",
    )

    os.makedirs(TEMP_DIR, exist_ok=True)
    if not bool(rt.saveMaxFile(TEMP_MAX, quiet=True)):
        raise RuntimeError("保存 003 隔离复验场景失败。")
    if not bool(rt.loadMaxFile(TEMP_MAX, useFileUnits=True, quiet=True)):
        raise RuntimeError("重载 003 隔离复验场景失败。")
    reloaded_003 = rt.getNodeByName(TARGET_003)
    reload_comparison = compare_positions(
        expected_003["points"],
        evaluated_world_positions(reloaded_003),
        "003 保存重载",
    )
    payload["mode2_003"] = {
        **comparison_003,
        "skin_count": 1,
        "old_handle": old_handle_003,
        "final_handle": final_handle_003,
        "saved_and_reloaded": True,
        "reload_max_world_delta": reload_comparison["max_world_delta"],
        "summary": str(summary_003),
        "report_path": os.path.abspath(str(skin.LAST_RUN_REPORT_PATH)),
        "importer_restore": importer_restore_003,
    }

    assets_after = {
        os.path.basename(path): sha256_file(path)
        for path in (MAX_PATH, FBX_002, FBX_003)
    }
    if assets_after != assets_before:
        raise AssertionError("用户测试资产哈希发生变化。")
    payload["assets_unchanged"] = True
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
    with open(RESULT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

if not payload["ok"]:
    raise RuntimeError("用户报告的 002/003 回归门失败，请查看结果 JSON。")
