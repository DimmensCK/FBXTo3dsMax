# -*- coding: utf-8 -*-
"""Real 3ds Max 2023 safety regression for smoothing-group writes.

This script is intended only for an isolated ``3dsmaxbatch.exe`` process.  It
creates procedural fixtures in a new unsaved scene, verifies the production
MAXScript bridge, and resets the scene after every case and again at exit.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Sequence, Tuple

from pymxs import runtime as rt


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_ROOT = os.path.join(ROOT, "contents") if os.path.isdir(os.path.join(ROOT, "contents")) else ROOT
RESULT = os.path.join(
    ROOT,
    "tests",
    "_max_smoothing_write_safety_result.json",
)
CORE_PATH = os.path.join(RUNTIME_ROOT, "f2m_topology_transfer.py")
SIGNED_MASKS = (0, 1, -2147483648, -1)
UNIQUE_MASK_MIN_REPEAT_COUNT = 100
UNIQUE_MASK_HARD_LIMIT_SECONDS = 5.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_topology() -> Any:
    path = os.path.abspath(CORE_PATH)
    name = "_f2m_smoothing_write_safety_runtime"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载当前核心：{path}")
    sys.modules.pop(name, None)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    actual = os.path.normcase(os.path.abspath(str(module.__file__)))
    if actual != os.path.normcase(path):
        raise RuntimeError(f"核心模块来源不一致：{actual} != {path}")
    if str(module.TOOL_VERSION) != "1.4.25":
        raise RuntimeError(f"加载到错误插件版本：{module.TOOL_VERSION}")
    module.ensure_runtime()
    return module


def _max_array(values: Iterable[int]) -> Any:
    return rt.Array(*[int(value) for value in values])


def _valid_node(node: Any) -> bool:
    try:
        return bool(rt.isValidNode(node))
    except Exception:
        return False


def _class_name(value: Any) -> str:
    return str(rt.classOf(value))


def _anim_handle(value: Any) -> int:
    try:
        return int(rt.getHandleByAnim(value))
    except Exception:
        return -1


def _make_poly(
    name: str,
    *,
    rows: int = 2,
    columns: int = 2,
) -> Any:
    node = rt.Plane(
        name=name,
        length=100.0,
        width=100.0,
        lengthsegs=columns,
        widthsegs=rows,
    )
    rt.convertToPoly(node)
    if _class_name(node.baseObject) != "Editable_Poly":
        raise AssertionError(
            f"{name} 没有转换为 Editable Poly：{_class_name(node.baseObject)}"
        )
    expected_faces = rows * columns
    actual_faces = int(rt.polyop.getNumFaces(node.baseObject))
    if actual_faces != expected_faces:
        raise AssertionError(f"{name} 面数错误：{actual_faces}/{expected_faces}")
    return node


def _make_mesh_four_faces(name: str) -> Any:
    vertices = rt.Array(
        rt.Point3(0, 0, 0),
        rt.Point3(10, 0, 0),
        rt.Point3(20, 0, 0),
        rt.Point3(0, 10, 0),
        rt.Point3(10, 10, 0),
        rt.Point3(20, 10, 0),
    )
    faces = rt.Array(
        rt.Point3(1, 2, 5),
        rt.Point3(1, 5, 4),
        rt.Point3(2, 3, 6),
        rt.Point3(2, 6, 5),
    )
    node = rt.mesh(name=name, vertices=vertices, faces=faces)
    if _class_name(node.baseObject) not in {"Editable_mesh", "Editable Mesh"}:
        raise AssertionError(
            f"{name} 不是 Editable Mesh：{_class_name(node.baseObject)}"
        )
    if int(rt.getNumFaces(node.baseObject.mesh)) != 4:
        raise AssertionError(f"{name} 没有 4 个基础三角面。")
    return node


def _read_masks(topology: Any, node: Any) -> Tuple[int, ...]:
    raw = rt.F2M_Helper.getFaceSmoothingGroups(node)
    if raw is None or str(raw) == "undefined":
        raise AssertionError(
            f"{node.name} 无法读取光滑组：{topology.helper_message()}"
        )
    return tuple(int(value) for value in list(raw))


def _write_masks(
    topology: Any,
    node: Any,
    values: Sequence[int],
) -> Tuple[float, str]:
    max_values = _max_array(values)
    started = time.perf_counter()
    ok = bool(rt.F2M_Helper.setFaceSmoothingGroups(node, max_values))
    elapsed = time.perf_counter() - started
    message = str(topology.helper_message())
    if not ok:
        raise AssertionError(f"{node.name} 光滑组写入失败：{message}")
    return elapsed, message


def _base_vertex_count(node: Any) -> int:
    base_class = _class_name(node.baseObject)
    if base_class == "Editable_Poly":
        return int(rt.polyop.getNumVerts(node.baseObject))
    if base_class in {"Editable_mesh", "Editable Mesh"}:
        mesh_value = rt.copy(node.baseObject.mesh)
        try:
            return int(rt.getNumVerts(mesh_value))
        finally:
            try:
                rt.free(mesh_value)
            except Exception:
                pass
    raise AssertionError(f"不支持的基础对象：{base_class}")


def _modifier_signature(node: Any) -> Tuple[Tuple[str, str, int], ...]:
    return tuple(
        (
            _class_name(modifier),
            str(modifier.name),
            _anim_handle(modifier),
        )
        for modifier in list(node.modifiers)
    )


def _bone_signature(skin: Any) -> Tuple[Tuple[int, str], ...]:
    bone_count = int(rt.skinOps.GetNumberBones(skin))
    values: List[Tuple[int, str]] = []
    for list_id in range(1, bone_count + 1):
        bone_id = int(rt.skinOps.GetBoneIDByListID(skin, list_id))
        bone_name = str(rt.skinOps.GetBoneName(skin, bone_id, 0))
        values.append((bone_id, bone_name))
    return tuple(values)


def _weight_snapshot(skin: Any, vertex_count: int) -> Tuple[Tuple[Tuple[int, float], ...], ...]:
    rows: List[Tuple[Tuple[int, float], ...]] = []
    for vertex_index in range(1, vertex_count + 1):
        influence_count = int(
            rt.skinOps.GetVertexWeightCount(skin, vertex_index)
        )
        influences = [
            (
                int(
                    rt.skinOps.GetVertexWeightBoneID(
                        skin,
                        vertex_index,
                        influence_index,
                    )
                ),
                float(
                    rt.skinOps.GetVertexWeight(
                        skin,
                        vertex_index,
                        influence_index,
                    )
                ),
            )
            for influence_index in range(1, influence_count + 1)
        ]
        rows.append(tuple(sorted(influences)))
    return tuple(rows)


def _assert_weights_equal(
    expected: Sequence[Sequence[Tuple[int, float]]],
    actual: Sequence[Sequence[Tuple[int, float]]],
) -> None:
    if len(expected) != len(actual):
        raise AssertionError(f"Skin 权重顶点数改变：{len(expected)}/{len(actual)}")
    for vertex_index, (expected_row, actual_row) in enumerate(
        zip(expected, actual),
        start=1,
    ):
        if len(expected_row) != len(actual_row):
            raise AssertionError(
                f"顶点 {vertex_index} 的 Skin 影响数量改变："
                f"{len(expected_row)}/{len(actual_row)}"
            )
        for (expected_bone, expected_weight), (
            actual_bone,
            actual_weight,
        ) in zip(expected_row, actual_row):
            if expected_bone != actual_bone:
                raise AssertionError(
                    f"顶点 {vertex_index} 的 BoneID 改变："
                    f"{expected_bone}/{actual_bone}"
                )
            if abs(expected_weight - actual_weight) > 0.0001:
                raise AssertionError(
                    f"顶点 {vertex_index} / BoneID {expected_bone} 权重改变："
                    f"{expected_weight:.8f}/{actual_weight:.8f}"
                )


def _replace_vertex_weights(
    skin: Any,
    node: Any,
    vertex_index: int,
    influences: Sequence[Tuple[int, float]],
) -> None:
    bone_ids = _max_array(bone_id for bone_id, _weight in influences)
    weights = rt.Array(*[float(weight) for _bone_id, weight in influences])
    try:
        rt.skinOps.ReplaceVertexWeights(
            skin,
            vertex_index,
            bone_ids,
            weights,
            node=node,
        )
    except Exception:
        rt.skinOps.ReplaceVertexWeights(
            skin,
            vertex_index,
            bone_ids,
            weights,
        )


def _add_skin_fixture(topology: Any, node: Any, label: str) -> Any:
    # Keep a harmless non-Skin modifier in the stack so the regression checks
    # identity and ordering, not merely the continued existence of one Skin.
    bend = rt.Bend(angle=0.0)
    bend.name = f"{label}_Bend"
    rt.addModifier(node, bend)
    skin = rt.Skin()
    skin.name = f"{label}_Skin"
    rt.addModifier(node, skin)
    if not topology.activate_modifier(node, skin):
        raise AssertionError(f"{label} 无法激活 Skin。")

    bone_a = rt.Dummy(name=f"{label}_Bone_A")
    bone_b = rt.Dummy(name=f"{label}_Bone_B")
    rt.skinOps.addBone(skin, bone_a, 0, node=node)
    rt.skinOps.addBone(skin, bone_b, 1, node=node)
    bone_ids = (
        int(rt.skinOps.GetBoneIDByListID(skin, 1)),
        int(rt.skinOps.GetBoneIDByListID(skin, 2)),
    )

    vertex_count = _base_vertex_count(node)
    patterns = (
        ((bone_ids[0], 1.0),),
        ((bone_ids[1], 1.0),),
        ((bone_ids[0], 0.25), (bone_ids[1], 0.75)),
        ((bone_ids[0], 0.6), (bone_ids[1], 0.4)),
    )
    for vertex_index in range(1, vertex_count + 1):
        _replace_vertex_weights(
            skin,
            node,
            vertex_index,
            patterns[(vertex_index - 1) % len(patterns)],
        )
    rt.update(node)
    return skin


def _skin_state(topology: Any, node: Any, skin: Any) -> Dict[str, Any]:
    if not topology.activate_modifier(node, skin):
        raise AssertionError(f"{node.name} 无法激活 Skin 读取状态。")
    vertex_count = _base_vertex_count(node)
    return {
        "base_vertex_count": vertex_count,
        "modifier_stack": _modifier_signature(node),
        "skin_handle": _anim_handle(skin),
        "skin_count": sum(
            1
            for modifier in list(node.modifiers)
            if _class_name(modifier) == "Skin"
        ),
        "bones": _bone_signature(skin),
        "weights": _weight_snapshot(skin, vertex_count),
    }


def _assert_skin_state_equal(before: Dict[str, Any], after: Dict[str, Any]) -> None:
    for key in (
        "base_vertex_count",
        "modifier_stack",
        "skin_handle",
        "skin_count",
        "bones",
    ):
        if before[key] != after[key]:
            raise AssertionError(f"Skin 状态字段 {key} 改变：{before[key]}/{after[key]}")
    _assert_weights_equal(before["weights"], after["weights"])


def _case_signed_roundtrip(topology: Any) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    for kind in ("poly", "mesh"):
        node = (
            _make_poly(f"F2M_Signed_{kind}")
            if kind == "poly"
            else _make_mesh_four_faces(f"F2M_Signed_{kind}")
        )
        if len(list(node.modifiers)) != 0:
            raise AssertionError(f"{kind} 无修改器夹具意外带有修改器。")
        elapsed, message = _write_masks(topology, node, SIGNED_MASKS)
        readback = _read_masks(topology, node)
        if readback != SIGNED_MASKS:
            raise AssertionError(
                f"{kind} int32 光滑组读回错误：{readback}/{SIGNED_MASKS}"
            )
        results.append(
            {
                "kind": kind,
                "base_object_class": _class_name(node.baseObject),
                "elapsed_seconds": round(elapsed, 6),
                "input_masks": list(SIGNED_MASKS),
                "readback_masks": list(readback),
                "helper_message": message,
                "modifier_count": 0,
            }
        )
        rt.delete(node)
    return {"fixtures": results}


def _case_skin_roundtrip(
    topology: Any,
    *,
    kind: str,
) -> Dict[str, Any]:
    node = (
        _make_poly(f"F2M_Skin_{kind}")
        if kind == "poly"
        else _make_mesh_four_faces(f"F2M_Skin_{kind}")
    )
    skin = _add_skin_fixture(topology, node, f"F2M_{kind}")
    before = _skin_state(topology, node, skin)
    elapsed, message = _write_masks(topology, node, SIGNED_MASKS)
    readback = _read_masks(topology, node)
    after_skin = rt.F2M_Helper.findSkin(node)
    if after_skin is None or str(after_skin) == "undefined":
        raise AssertionError(f"{kind} 写入后 Skin 丢失。")
    after = _skin_state(topology, node, after_skin)
    _assert_skin_state_equal(before, after)
    if readback != SIGNED_MASKS:
        raise AssertionError(
            f"{kind}+Skin 光滑组读回错误：{readback}/{SIGNED_MASKS}"
        )
    if kind == "mesh" and "基础 TriMesh 单次事务写回" not in message:
        raise AssertionError(f"Mesh+Skin 没有报告事务写回路径：{message}")
    return {
        "kind": kind,
        "base_object_class": _class_name(node.baseObject),
        "elapsed_seconds": round(elapsed, 6),
        "input_masks": list(SIGNED_MASKS),
        "readback_masks": list(readback),
        "helper_message": message,
        "skin_unchanged": True,
        "base_vertex_count": int(after["base_vertex_count"]),
        "modifier_stack": [
            {"class": entry[0], "name": entry[1], "handle": entry[2]}
            for entry in after["modifier_stack"]
        ],
        "skin_handle": int(after["skin_handle"]),
        "skin_count": int(after["skin_count"]),
        "bones": [
            {"bone_id": bone_id, "name": bone_name}
            for bone_id, bone_name in after["bones"]
        ],
        "weight_vertex_count": len(after["weights"]),
    }


def _case_many_unique_masks(topology: Any) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    for unique_count in (256, 257):
        # Plane segment parameters are kept at or below Max's primitive limit.
        # Both fixtures still repeat every unique mask at least 100 times, so a
        # regression to tens of thousands of per-face native calls is visible.
        rows, columns = (
            (128, 200)
            if unique_count == 256
            else (129, 200)
        )
        face_count = rows * columns
        node = _make_poly(
            f"F2M_Unique_{unique_count}",
            rows=rows,
            columns=columns,
        )
        masks = tuple(index % unique_count for index in range(face_count))
        if len(set(masks)) != unique_count:
            raise AssertionError(f"{unique_count} 种掩码夹具生成错误。")
        max_masks = _max_array(masks)

        started = time.perf_counter()
        ok = bool(rt.F2M_Helper.setFaceSmoothingGroups(node, max_masks))
        message = str(topology.helper_message())
        readback = _read_masks(topology, node)
        elapsed = time.perf_counter() - started

        if not ok:
            raise AssertionError(f"{unique_count} 种掩码写入失败：{message}")
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
                f"{unique_count} 种掩码全量读回失败，首个差异面：{mismatch}"
            )
        match = re.search(r"合并为\s+(\d+)\s+个批次", message)
        if match is None or int(match.group(1)) != unique_count:
            raise AssertionError(
                f"{unique_count} 种掩码没有报告对应批次数：{message}"
            )
        if unique_count == 257 and (
            "逐面" in message
            or "安全路径" in message
            or "回退" in message
        ):
            raise AssertionError(f"257 种掩码退化为旧逐面路径：{message}")
        if elapsed > UNIQUE_MASK_HARD_LIMIT_SECONDS:
            raise AssertionError(
                f"{face_count} 面/{unique_count} 种掩码耗时 {elapsed:.6f} 秒，"
                f"超过硬阈值 {UNIQUE_MASK_HARD_LIMIT_SECONDS:.1f} 秒"
            )
        results.append(
            {
                "unique_mask_count": unique_count,
                "face_count": face_count,
                "minimum_repeat_count": face_count // unique_count,
                "elapsed_seconds": round(elapsed, 6),
                "hard_limit_seconds": UNIQUE_MASK_HARD_LIMIT_SECONDS,
                "batch_count": int(match.group(1)),
                "readback_face_count": len(readback),
                "readback_matches": True,
                "used_legacy_per_face_fallback": False,
                "helper_message": message,
            }
        )
        if face_count // unique_count < UNIQUE_MASK_MIN_REPEAT_COUNT:
            raise AssertionError(
                f"{unique_count} 种掩码每种重复次数不足 "
                f"{UNIQUE_MASK_MIN_REPEAT_COUNT}。"
            )
        rt.delete(node)
    return {"fixtures": results}


def _invalid_inputs() -> Tuple[Tuple[str, str, str], ...]:
    return (
        ("undefined_array", "undefined", "没有可写入"),
        ("empty_array", "#()", "数组为空"),
        (
            "undefined_element",
            "#(0, 1, undefined, -1)",
            "不是 32 位整数",
        ),
        ("non_integer_float", "#(0, 1, 1.25, -1)", "不是 32 位整数"),
        (
            "positive_int64_overflow",
            "#(0, 1, 2147483648L, -1)",
            "超出 32 位有符号整数范围",
        ),
        (
            "negative_int64_overflow",
            "#(0, 1, -2147483649L, -1)",
            "超出 32 位有符号整数范围",
        ),
    )


def _describe_max_value(value: Any) -> Dict[str, Any]:
    if value is None or str(value) == "undefined":
        return {
            "class": "undefined",
            "value": "undefined",
        }
    try:
        items = list(value)
    except Exception:
        items = [value]
    described: List[Dict[str, Any]] = []
    for item in items:
        entry: Dict[str, Any] = {
            "class": _class_name(item),
            "value": str(item),
        }
        try:
            entry["python_int"] = int(item)
        except Exception:
            pass
        described.append(entry)
    return {
        "class": _class_name(value),
        "items": described,
    }


def _case_invalid_inputs(topology: Any) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    seed = (1, 2, 4, 8)
    for label, expression, expected_fragment in _invalid_inputs():
        node = _make_poly(f"F2M_Invalid_{label}")
        _write_masks(topology, node, seed)
        before = _read_masks(topology, node)
        invalid_value = rt.execute(expression)
        input_description = _describe_max_value(invalid_value)

        started = time.perf_counter()
        ok = bool(rt.F2M_Helper.setFaceSmoothingGroups(node, invalid_value))
        elapsed = time.perf_counter() - started
        message = str(topology.helper_message())
        after = _read_masks(topology, node)

        if ok:
            raise AssertionError(
                f"{label} 非法输入被错误接受：input={input_description}；"
                f"message={message}；readback={after}"
            )
        if before != seed or after != seed:
            raise AssertionError(
                f"{label} 写入前失败却改变原值：{before}/{after}/{seed}"
            )
        if not message.startswith("光滑组写入前检查失败："):
            raise AssertionError(f"{label} 没有明确报告写入前失败：{message}")
        if expected_fragment not in message:
            raise AssertionError(
                f"{label} 错误消息缺少“{expected_fragment}”：{message}"
            )
        if "回滚失败" in message or "已完整回滚" in message:
            raise AssertionError(f"{label} 写入前失败却声称执行了回滚：{message}")
        results.append(
            {
                "input": label,
                "maxscript_expression": expression,
                "resolved_input": input_description,
                "elapsed_seconds": round(elapsed, 6),
                "accepted": False,
                "original_masks": list(before),
                "readback_masks": list(after),
                "original_unchanged": True,
                "prewrite_failure": True,
                "claimed_rollback_failure": False,
                "helper_message": message,
            }
        )
        rt.delete(node)
    return {"fixtures": results}


def _run_isolated_case(
    case_id: str,
    callback: Callable[[], Dict[str, Any]],
) -> Dict[str, Any]:
    rt.resetMaxFile(rt.Name("noPrompt"))
    started = time.perf_counter()
    record: Dict[str, Any] = {
        "id": case_id,
        "status": "running",
    }
    try:
        if len(list(rt.objects)) != 0:
            raise AssertionError("隔离用例开始前场景不为空。")
        record.update(callback())
        record["status"] = "passed"
    except BaseException:
        record["status"] = "failed"
        record["error"] = traceback.format_exc()
    finally:
        record["case_total_seconds"] = round(
            time.perf_counter() - started,
            6,
        )
        try:
            rt.resetMaxFile(rt.Name("noPrompt"))
            record["scene_cleared"] = len(list(rt.objects)) == 0
        except BaseException:
            record["scene_cleared"] = False
            record["cleanup_error"] = traceback.format_exc()
        if not record["scene_cleared"]:
            record["status"] = "failed"
    return record


def _write_result(payload: Dict[str, Any]) -> None:
    with open(RESULT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> None:
    started_at = _utc_now()
    core_hash_before = _sha256(CORE_PATH)
    payload: Dict[str, Any] = {
        "schema_version": 1,
        "test": "FBXTo3dsMax smoothing write safety",
        "tool_version": "1.4.25",
        "started_at_utc": started_at,
        "finished_at_utc": None,
        "overall_status": "running",
        "environment": {
            "inside_3ds_max": True,
            "max_product_folder": os.path.basename(
                os.path.normpath(
                    os.path.abspath(str(rt.getDir(rt.Name("maxroot"))))
                )
            ),
            "max_root": os.path.abspath(str(rt.getDir(rt.Name("maxroot")))),
            "process_id": os.getpid(),
            "python_executable": sys.executable,
            "python_version": sys.version,
        },
        "core_file": {
            "path": CORE_PATH,
            "sha256_before": core_hash_before,
            "sha256_after": None,
            "unchanged_during_test": False,
        },
        "safety": {
            "isolated_batch_scene": True,
            "saved_scene": False,
            "user_asset_opened": False,
            "all_case_scenes_cleared": False,
            "final_scene_cleared": False,
        },
        "cases": [],
    }

    try:
        if payload["environment"]["max_product_folder"].casefold() != "3ds max 2023":
            raise AssertionError(
                "本回归要求 3ds Max 2023，实际根目录为 "
                + payload["environment"]["max_root"]
            )
        topology = _load_topology()
        payload["cases"] = [
            _run_isolated_case(
                "editable_poly_and_mesh_signed_int32_roundtrip",
                lambda: _case_signed_roundtrip(topology),
            ),
            _run_isolated_case(
                "editable_mesh_skin_transaction_preserves_skin",
                lambda: _case_skin_roundtrip(topology, kind="mesh"),
            ),
            _run_isolated_case(
                "editable_poly_skin_preserves_skin",
                lambda: _case_skin_roundtrip(topology, kind="poly"),
            ),
            _run_isolated_case(
                "poly_256_and_257_unique_masks_no_per_face_fallback",
                lambda: _case_many_unique_masks(topology),
            ),
            _run_isolated_case(
                "invalid_inputs_fail_before_write",
                lambda: _case_invalid_inputs(topology),
            ),
        ]
        core_hash_after = _sha256(CORE_PATH)
        payload["core_file"]["sha256_after"] = core_hash_after
        payload["core_file"]["unchanged_during_test"] = (
            core_hash_before == core_hash_after
        )
        payload["safety"]["all_case_scenes_cleared"] = all(
            bool(case.get("scene_cleared"))
            for case in payload["cases"]
        )
        payload["overall_status"] = (
            "passed"
            if all(case.get("status") == "passed" for case in payload["cases"])
            and payload["core_file"]["unchanged_during_test"]
            and payload["safety"]["all_case_scenes_cleared"]
            else "failed"
        )
    except BaseException:
        payload["overall_status"] = "failed"
        payload["framework_error"] = traceback.format_exc()
    finally:
        try:
            rt.resetMaxFile(rt.Name("noPrompt"))
            payload["safety"]["final_scene_cleared"] = len(list(rt.objects)) == 0
        except BaseException:
            payload["safety"]["final_scene_cleared"] = False
            payload["final_cleanup_error"] = traceback.format_exc()
            payload["overall_status"] = "failed"
        payload["finished_at_utc"] = _utc_now()
        _write_result(payload)

    if payload["overall_status"] != "passed":
        failed = [
            case.get("id", "unknown")
            for case in payload.get("cases", [])
            if case.get("status") != "passed"
        ]
        raise AssertionError(f"光滑组写入安全回归失败：{failed}")


main()
