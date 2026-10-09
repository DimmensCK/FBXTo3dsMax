# -*- coding: utf-8 -*-
"""3ds Max 2023 acceptance for SG baseline + sparse Explicit normal residuals.

This script is intentionally launcher-gated.  It creates only procedural test
meshes, never opens user assets, and writes one atomic JSON result under tests.
The companion PowerShell launcher owns the MaxBatch process and audits Max.log.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import math
import os
import re
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from pymxs import runtime as rt


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_ROOT = os.path.join(ROOT, "contents") if os.path.isdir(os.path.join(ROOT, "contents")) else ROOT
SCRIPT_PATH = os.path.normcase(os.path.abspath(__file__))
RESULT_PATH = os.path.join(
    ROOT,
    "tests",
    "_max_hybrid_normals_equivalence_v1320_result.json",
)
EXPECTED_VERSION = "1.4.26"
TOKEN_ENV = "F2M_HYBRID_NORMALS_TOKEN"
SCRIPT_ENV = "F2M_HYBRID_NORMALS_EXPECTED_SCRIPT"
RESULT_ENV = "F2M_HYBRID_NORMALS_RESULT"
TOKEN_PATTERN = re.compile(r"^[0-9a-f]{32}$")

SG_MASKS = (1, 1, 2, 2)
INITIAL_TARGET_MASKS = (4, 4, 4, 4)
RESIDUAL_TOLERANCE_DEGREES = 0.1
FINAL_TOLERANCE_DEGREES = 0.01
EDGE_TOLERANCE_DEGREES = 0.01
MIN_HARD_EDGE_DEGREES = 5.0
MIN_WRONG_ADDITION_DEGREES = 5.0
F2M_NORMAL_MODIFIER_NAME = "F2M_顶点法线"


@dataclasses.dataclass(frozen=True)
class FlatSnapshot:
    """Primitive-only, face/corner ordered normal snapshot."""

    face_count: int
    normal_count: int
    explicit_normal_count: int
    face_starts: tuple[int, ...]
    vertex_ids: tuple[int, ...]
    normal_xyz: tuple[float, ...]
    normal_ids: tuple[int, ...]
    specified: tuple[bool, ...]
    explicit: tuple[bool, ...]
    smoothing_masks: tuple[int, ...]

    @property
    def corner_count(self) -> int:
        return len(self.normal_ids)

    def vector(self, corner_index: int) -> tuple[float, float, float]:
        offset = corner_index * 3
        return (
            self.normal_xyz[offset],
            self.normal_xyz[offset + 1],
            self.normal_xyz[offset + 2],
        )


@dataclasses.dataclass(frozen=True)
class CaseExpectation:
    name: str
    target_name: str
    authority: FlatSnapshot
    baseline: FlatSnapshot
    residual_corners: tuple[int, ...]
    retained_corners: tuple[int, ...]
    expect_f2m_modifier: bool
    verify_mixed_edges: bool


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalized_path(value: str) -> str:
    return os.path.normcase(os.path.abspath(value))


def validate_launcher_environment() -> tuple[str, str]:
    token = os.environ.get(TOKEN_ENV, "").strip().lower()
    expected_script = os.environ.get(SCRIPT_ENV, "").strip()
    expected_result = os.environ.get(RESULT_ENV, "").strip()
    if TOKEN_PATTERN.fullmatch(token) is None:
        raise RuntimeError("缺少启动器生成的 32 位十六进制单次令牌。")
    if not expected_script or normalized_path(expected_script) != SCRIPT_PATH:
        raise RuntimeError("PythonHost 脚本身份与启动器指定的绝对路径不一致。")
    if not expected_result or normalized_path(expected_result) != normalized_path(
        RESULT_PATH
    ):
        raise RuntimeError("验收结果路径不是 tests 下的固定专用结果文件。")
    return token, normalized_path(expected_result)


def atomic_json_write(path: str, payload: dict[str, Any], token: str) -> None:
    temporary = f"{path}.tmp-{token}"
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def load_topology_module(token: str):
    path = os.path.join(RUNTIME_ROOT, "f2m_topology_transfer.py")
    module_name = f"_f2m_hybrid_normals_{token}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法创建生产模块加载规范：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    if normalized_path(str(module.__file__)) != normalized_path(path):
        raise RuntimeError(f"生产模块来源不一致：{module.__file__}")
    if str(getattr(module, "TOOL_VERSION", "")) != EXPECTED_VERSION:
        raise RuntimeError(
            "生产模块版本不一致："
            f"期望 {EXPECTED_VERSION}，实际 {getattr(module, 'TOOL_VERSION', '')}"
        )
    module.ensure_runtime()
    helper = rt.F2M_Helper
    try:
        if str(helper.apiKind) != "topology":
            raise RuntimeError(f"激活的 Helper 类型不是 topology：{helper.apiKind}")
        if str(helper.apiVersion) != EXPECTED_VERSION:
            raise RuntimeError(
                f"Helper 版本不一致：{helper.apiVersion}/{EXPECTED_VERSION}"
            )
    finally:
        helper = None
    return module


def install_maxscript_helpers() -> None:
    rt.execute(
        r"""
        global F2M_HNE_lastMessage = ""
        global F2M_HNE_captureSelectionHandles
        global F2M_HNE_restoreSelectionHandles
        global F2M_HNE_createBentFan
        global F2M_HNE_createSentinel
        global F2M_HNE_findEditNormals
        global F2M_HNE_snapshotFlat
        global F2M_HNE_authorAllBaseline
        global F2M_HNE_authorLocalTilt
        global F2M_HNE_authorSharedHardFan
        global F2M_HNE_countF2M

        fn F2M_HNE_captureSelectionHandles =
        (
            local handles = #()
            for nodeValue in selection do
                append handles (getHandleByAnim nodeValue)
            handles
        )

        fn F2M_HNE_restoreSelectionHandles handles =
        (
            clearSelection()
            for handleValue in handles do
            (
                local nodeValue = undefined
                try(nodeValue = getAnimByHandle handleValue)catch()
                if nodeValue != undefined and isValidNode nodeValue do
                    selectMore nodeValue
                nodeValue = undefined
            )
            true
        )

        fn F2M_HNE_activate n normalMod =
        (
            local activated = false
            try
            (
                select n
                max modify mode
                modPanel.setCurrentObject normalMod
                activated = (modPanel.getCurrentObject() == normalMod)
            )
            catch(activated = false)
            activated
        )

        fn F2M_HNE_createBentFan nodeName xOffset =
        (
            F2M_HNE_lastMessage = ""
            local nodeValue = undefined
            local nodeHandle = 0
            try
            (
                nodeValue = mesh name:nodeName vertices:#(
                        [0.0, 0.0, 0.0],
                        [1.0, 0.0, 0.0],
                        [0.0, 1.0, 0.0],
                        [-1.0, 0.0, 1.0],
                        [0.0, -1.0, -1.0]
                    ) faces:#(
                        [1,2,3],
                        [1,3,4],
                        [1,4,5],
                        [1,5,2]
                    )
                convertToPoly nodeValue
                nodeValue.position = [xOffset, 0.0, 0.0]
                update nodeValue
                nodeHandle = getHandleByAnim nodeValue
            )
            catch
            (
                F2M_HNE_lastMessage =
                    "创建四三角面折扇失败：" + getCurrentException()
                try(if nodeValue != undefined do delete nodeValue)catch()
                nodeHandle = 0
            )
            nodeValue = undefined
            nodeHandle
        )

        fn F2M_HNE_createSentinel nodeName =
        (
            F2M_HNE_lastMessage = ""
            local nodeValue = undefined
            local nodeHandle = 0
            try
            (
                nodeValue = point name:nodeName pos:[0.0, 100.0, 0.0] size:5.0 box:true
                nodeHandle = getHandleByAnim nodeValue
            )
            catch
            (
                F2M_HNE_lastMessage =
                    "创建选择哨兵失败：" + getCurrentException()
                try(if nodeValue != undefined do delete nodeValue)catch()
                nodeHandle = 0
            )
            nodeValue = undefined
            nodeHandle
        )

        fn F2M_HNE_findEditNormals n wantedName =
        (
            for normalMod in n.modifiers where
                classof normalMod == Edit_Normals and
                (normalMod.name as string) == wantedName do return normalMod
            undefined
        )

        fn F2M_HNE_makeAllExplicit n normalMod =
        (
            local normalCount = normalMod.GetNumNormals node:n
            local allNormals = #{}
            for normalIndex = 1 to normalCount do
                allNormals[normalIndex] = true
            local ok = normalCount > 0 and
                normalMod.MakeExplicit selection:allNormals node:n
            allNormals = #{}
            ok
        )

        fn F2M_HNE_specifyAllCorners n normalMod =
        (
            local faceCount = normalMod.GetNumFaces node:n
            for faceIndex = 1 to faceCount do
            (
                local degree = normalMod.GetFaceDegree faceIndex node:n
                for cornerIndex = 1 to degree do
                    normalMod.SetFaceNormalSpecified faceIndex cornerIndex specified:true node:n
            )
            true
        )

        fn F2M_HNE_addSourceReader n modName =
        (
            local normalMod = Edit_Normals()
            addModifier n normalMod
            normalMod.name = modName
            if not (F2M_HNE_activate n normalMod) then
            (
                try(deleteModifier n normalMod)catch()
                normalMod = undefined
            )
            else
                try(normalMod.RebuildNormals node:n)catch()
            normalMod
        )

        fn F2M_HNE_authorAllBaseline n modName =
        (
            F2M_HNE_lastMessage = ""
            local oldHandles = F2M_HNE_captureSelectionHandles()
            local normalMod = undefined
            local ok = false
            try
            (
                normalMod = F2M_HNE_addSourceReader n modName
                if normalMod == undefined do throw "无法建立源 Edit Normals。"
                if not (F2M_HNE_makeAllExplicit n normalMod) do
                    throw "无法冻结全部源基线法线。"
                F2M_HNE_specifyAllCorners n normalMod
                update n
                ok = true
            )
            catch
            (
                F2M_HNE_lastMessage =
                    "建立全部 Explicit 的 SG 等价源失败：" +
                    getCurrentException()
                ok = false
            )
            if not ok do
                try(if normalMod != undefined do deleteModifier n normalMod)catch()
            normalMod = undefined
            F2M_HNE_restoreSelectionHandles oldHandles
            oldHandles = #()
            ok
        )

        fn F2M_HNE_authorLocalTilt n faceIndex cornerIndex angleDegrees modName =
        (
            F2M_HNE_lastMessage = ""
            local oldHandles = F2M_HNE_captureSelectionHandles()
            local normalMod = undefined
            local breakNormals = #{}
            local ok = false
            try
            (
                normalMod = F2M_HNE_addSourceReader n modName
                if normalMod == undefined do throw "无法建立源 Edit Normals。"
                local originalId =
                    normalMod.GetNormalID faceIndex cornerIndex node:n
                breakNormals[originalId] = true
                -- This fixture must leave every newly split normal with a
                -- valid direction.  ``toAverage:false`` can create zero-vector
                -- sibling records in Max 2023; production correctly rejects
                -- any referenced zero normal before transfer.
                if not (normalMod.Break selection:breakNormals node:n toAverage:true) do
                        throw "无法打断局部自定义面角的法线扇区。"
                local chosenId =
                    normalMod.GetNormalID faceIndex cornerIndex node:n
                local referenceCount = 0
                for scanFace = 1 to (normalMod.GetNumFaces node:n) do
                (
                    local degree = normalMod.GetFaceDegree scanFace node:n
                    for scanCorner = 1 to degree where
                        (normalMod.GetNormalID scanFace scanCorner node:n) ==
                            chosenId do referenceCount += 1
                )
                if referenceCount != 1 do
                    throw "Break 后局部法线 ID 仍被多个面角引用。"
                if not (F2M_HNE_makeAllExplicit n normalMod) do
                    throw "无法冻结全部源基线法线。"
                F2M_HNE_specifyAllCorners n normalMod
                -- MakeExplicit may rebuild/compact the normal pool.  Resolve
                -- the authoritative face-corner ID again before reading and
                -- writing the local custom direction.
                chosenId =
                    normalMod.GetNormalID faceIndex cornerIndex node:n
                local baseValue =
                    normalize (normalMod.GetNormal chosenId node:n)
                local helperAxis =
                    if (abs (dot baseValue [0,0,1])) < 0.9 then
                        [0,0,1]
                    else
                        [0,1,0]
                local tangentValue = normalize (cross helperAxis baseValue)
                local customValue = normalize (
                    (baseValue * (cos angleDegrees)) +
                    (tangentValue * (sin angleDegrees))
                )
                normalMod.SetNormal chosenId &customValue node:n
                normalMod.SetFaceNormalSpecified faceIndex cornerIndex specified:true node:n
                update n
                baseValue = undefined
                tangentValue = undefined
                customValue = undefined
                helperAxis = undefined
                ok = true
            )
            catch
            (
                F2M_HNE_lastMessage =
                    "建立局部倾斜自定义法线源失败：" +
                    getCurrentException()
                ok = false
            )
            if not ok do
                try(if normalMod != undefined do deleteModifier n normalMod)catch()
            breakNormals = #{}
            normalMod = undefined
            F2M_HNE_restoreSelectionHandles oldHandles
            oldHandles = #()
            ok
        )

        fn F2M_HNE_authorSharedHardFan n faceA cornerA faceB cornerB modName =
        (
            F2M_HNE_lastMessage = ""
            local oldHandles = F2M_HNE_captureSelectionHandles()
            local normalMod = undefined
            local ok = false
            try
            (
                normalMod = F2M_HNE_addSourceReader n modName
                if normalMod == undefined do throw "无法建立源 Edit Normals。"
                local normalA = normalMod.GetNormalID faceA cornerA node:n
                local normalB = normalMod.GetNormalID faceB cornerB node:n
                if normalA == normalB do
                    throw "硬边两侧在夹具建立前已经共享 normal ID。"
                normalMod.SetNormalID faceB cornerB normalA node:n
                if (normalMod.GetNormalID faceB cornerB node:n) != normalA do
                    throw "无法让硬边两角共享源 normal ID。"
                if not (F2M_HNE_makeAllExplicit n normalMod) do
                    throw "无法冻结全部源基线法线。"
                F2M_HNE_specifyAllCorners n normalMod
                update n
                ok = true
            )
            catch
            (
                F2M_HNE_lastMessage =
                    "建立共享 ID 的局部残差源失败：" +
                    getCurrentException()
                ok = false
            )
            if not ok do
                try(if normalMod != undefined do deleteModifier n normalMod)catch()
            normalMod = undefined
            F2M_HNE_restoreSelectionHandles oldHandles
            oldHandles = #()
            ok
        )

        fn F2M_HNE_snapshotFlat n preferredName allowTemporary =
        (
            F2M_HNE_lastMessage = ""
            local oldHandles = F2M_HNE_captureSelectionHandles()
            local reader = undefined
            local readerIsTemporary = false
            local result = undefined
            local stage = "初始化"
            try
            (
                stage = "查找读取器"
                if preferredName != "" do
                    reader = F2M_HNE_findEditNormals n preferredName
                if reader == undefined and allowTemporary then
                (
                    reader = Edit_Normals()
                    addModifier n reader
                    reader.name = "F2M_HNE_临时只读法线"
                    readerIsTemporary = true
                )
                if reader == undefined do
                    throw "找不到指定 Edit Normals，且不允许临时读取器。"
                if not (F2M_HNE_activate n reader) do
                    throw "无法激活 Edit Normals 读取器。"
                if readerIsTemporary do
                    try(reader.RebuildNormals node:n)catch()

                stage = "读取面/法线数量"
                local faceCount = reader.GetNumFaces node:n
                local normalCount = reader.GetNumNormals node:n
                if faceCount < 1 or normalCount < 1 do
                    throw "Edit Normals 快照没有面或法线。"
                local totalExplicit = 0
                stage = "统计 Explicit"
                for normalIndex = 1 to normalCount where
                    reader.GetNormalExplicit normalIndex node:n do
                        totalExplicit += 1

                local faceStarts = #(1)
                local vertexIds = #()
                local normalXYZ = #()
                local normalIds = #()
                local specified01 = #()
                local explicit01 = #()
                local smoothingMasks = #()
                local baseObject = n.baseObject

                stage = "逐面读取"
                for faceIndex = 1 to faceCount do
                (
                    stage = "读取面角数"
                    local degree = reader.GetFaceDegree faceIndex node:n
                    stage = "读取基础面顶点"
                    local faceVertices =
                        polyop.getFaceVerts baseObject faceIndex
                    if faceVertices.count != degree do
                        throw "基础面角数与 Edit Normals 面角数不一致。"
                    stage = "读取光滑组"
                    append smoothingMasks (
                        polyop.getFaceSmoothGroup baseObject faceIndex
                    )
                    for cornerIndex = 1 to degree do
                    (
                        stage = "读取面角法线 ID"
                        local normalId =
                            reader.GetNormalID faceIndex cornerIndex node:n
                        stage = "读取面角法线向量"
                        local normalValue =
                            normalize (reader.GetNormal normalId node:n)
                        append vertexIds (faceVertices[cornerIndex] as integer)
                        append normalIds normalId
                        append normalXYZ normalValue.x
                        append normalXYZ normalValue.y
                        append normalXYZ normalValue.z
                        stage = "读取面角 Specified"
                        local isSpecified = reader.GetFaceNormalSpecified faceIndex cornerIndex node:n
                        append specified01 (if isSpecified then 1 else 0)
                        stage = "读取法线 Explicit"
                        local isExplicit = reader.GetNormalExplicit normalId node:n
                        append explicit01 (if isExplicit then 1 else 0)
                        normalValue = undefined
                    )
                    append faceStarts (normalIds.count + 1)
                    faceVertices = #()
                )
                baseObject = undefined
                result = #(
                    faceCount,
                    normalCount,
                    totalExplicit,
                    faceStarts,
                    vertexIds,
                    normalXYZ,
                    normalIds,
                    specified01,
                    explicit01,
                    smoothingMasks
                )
            )
            catch
            (
                F2M_HNE_lastMessage =
                    "扁平逐面角法线快照失败（" + stage + "）：" +
                    getCurrentException()
                result = undefined
            )
            if readerIsTemporary do
                try(if reader != undefined do deleteModifier n reader)catch()
            reader = undefined
            F2M_HNE_restoreSelectionHandles oldHandles
            oldHandles = #()
            result
        )

        fn F2M_HNE_countF2M n =
        (
            local result = 0
            for normalMod in n.modifiers do
            (
                local plugInOwned = matchPattern (normalMod.name as string) pattern:"F2M_顶点法线*" ignoreCase:false
                if classof normalMod == Edit_Normals and plugInOwned do
                    result += 1
            )
            result
        )
        """
    )


def helper_error() -> str:
    try:
        return str(rt.F2M_HNE_lastMessage)
    except Exception:
        return "MAXScript 专用 Helper 未提供诊断。"


def heap_check_text() -> str:
    return str(rt.heapCheck()).strip()


def heap_check_ok(value: str) -> bool:
    return value.strip().lower() in {"true", "ok"}


def valid_node(node: Any) -> bool:
    if node is None or str(node) == "undefined":
        return False
    try:
        return bool(rt.isValidNode(node))
    except Exception:
        return False


def node_by_handle(handle: int):
    node = rt.getAnimByHandle(int(handle))
    if not valid_node(node):
        node = None
        raise AssertionError(f"节点句柄已失效：{handle}")
    return node


def node_by_name(name: str):
    node = rt.getNodeByName(name)
    if not valid_node(node):
        node = None
        raise AssertionError(f"找不到重载节点：{name}")
    return node


def selection_handles() -> tuple[int, ...]:
    raw = rt.F2M_HNE_captureSelectionHandles()
    if raw is None or str(raw) == "undefined":
        raise AssertionError("无法按句柄读取选择。")
    try:
        return tuple(sorted(int(value) for value in list(raw)))
    finally:
        raw = None


def select_handle(handle: int) -> tuple[int, ...]:
    node = node_by_handle(handle)
    try:
        rt.select(node)
    finally:
        node = None
    selected = selection_handles()
    if selected != (int(handle),):
        raise AssertionError(f"选择哨兵设置失败：{selected}/{handle}")
    return selected


def set_smoothing_masks(node: Any, masks: Sequence[int]) -> None:
    max_values = rt.Array(*[int(value) for value in masks])
    try:
        if not bool(rt.F2M_Helper.setFaceSmoothingGroups(node, max_values)):
            raise AssertionError(str(rt.F2M_Helper.lastMessage))
    finally:
        max_values = None


def snapshot(
    node: Any,
    *,
    modifier_name: str = "",
    allow_temporary: bool,
) -> FlatSnapshot:
    raw = rt.F2M_HNE_snapshotFlat(
        node,
        str(modifier_name),
        bool(allow_temporary),
    )
    if raw is None or str(raw) == "undefined":
        raw = None
        raise AssertionError(helper_error())
    outer: list[Any] = []
    try:
        outer = list(raw)
        if len(outer) != 10:
            raise AssertionError(f"扁平快照字段数错误：{len(outer)}/10")
        face_count = int(outer[0])
        normal_count = int(outer[1])
        explicit_normal_count = int(outer[2])
        face_starts = tuple(int(value) for value in list(outer[3]))
        vertex_ids = tuple(int(value) for value in list(outer[4]))
        normal_xyz = tuple(float(value) for value in list(outer[5]))
        normal_ids = tuple(int(value) for value in list(outer[6]))
        specified = tuple(bool(int(value)) for value in list(outer[7]))
        explicit = tuple(bool(int(value)) for value in list(outer[8]))
        smoothing_masks = tuple(int(value) for value in list(outer[9]))
    finally:
        raw = None
        for index in range(len(outer)):
            outer[index] = None
        outer.clear()

    corner_count = len(normal_ids)
    if face_count != 4:
        raise AssertionError(f"程序夹具面数错误：{face_count}/4")
    if len(face_starts) != face_count + 1:
        raise AssertionError("faceStarts 长度错误。")
    if not face_starts or face_starts[0] != 1:
        raise AssertionError("faceStarts 必须以 1 开始。")
    if face_starts[-1] != corner_count + 1:
        raise AssertionError("faceStarts 末端与面角数不一致。")
    if len(vertex_ids) != corner_count:
        raise AssertionError("顶点 ID 数与面角数不一致。")
    if len(normal_xyz) != corner_count * 3:
        raise AssertionError("法线 XYZ 数与面角数不一致。")
    if len(specified) != corner_count or len(explicit) != corner_count:
        raise AssertionError("Specified/Explicit 数与面角数不一致。")
    if len(smoothing_masks) != face_count:
        raise AssertionError("光滑组掩码数与面数不一致。")
    if any(normal_id < 1 or normal_id > normal_count for normal_id in normal_ids):
        raise AssertionError("面角 normal ID 越界。")

    return FlatSnapshot(
        face_count=face_count,
        normal_count=normal_count,
        explicit_normal_count=explicit_normal_count,
        face_starts=face_starts,
        vertex_ids=vertex_ids,
        normal_xyz=normal_xyz,
        normal_ids=normal_ids,
        specified=specified,
        explicit=explicit,
        smoothing_masks=smoothing_masks,
    )


def normalized_vector(
    value: Sequence[float],
) -> tuple[float, float, float]:
    length = math.sqrt(sum(float(component) ** 2 for component in value))
    if length <= 1.0e-12:
        raise AssertionError(f"法线向量长度为零：{value}")
    return tuple(float(component) / length for component in value)  # type: ignore[return-value]


def angle_degrees(a: Sequence[float], b: Sequence[float]) -> float:
    na = normalized_vector(a)
    nb = normalized_vector(b)
    dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(na, nb))))
    return math.degrees(math.acos(dot))


def normalized_sum(
    a: Sequence[float], b: Sequence[float]
) -> tuple[float, float, float]:
    return normalized_vector(tuple(float(x) + float(y) for x, y in zip(a, b)))


def corner_index(snapshot_value: FlatSnapshot, face: int, corner: int) -> int:
    """Return a zero-based flat corner for one-based Max face/corner indices."""

    if face < 1 or face > snapshot_value.face_count:
        raise AssertionError(f"面索引越界：{face}")
    start = snapshot_value.face_starts[face - 1] - 1
    end = snapshot_value.face_starts[face] - 1
    if corner < 1 or start + corner > end:
        raise AssertionError(f"面角索引越界：{face}/{corner}")
    return start + corner - 1


def corner_for_vertex(
    snapshot_value: FlatSnapshot, face: int, vertex_id: int
) -> int:
    start = snapshot_value.face_starts[face - 1] - 1
    end = snapshot_value.face_starts[face] - 1
    matches = [
        index
        for index in range(start, end)
        if snapshot_value.vertex_ids[index] == int(vertex_id)
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"面 {face} 中顶点 {vertex_id} 出现次数不是 1：{matches}"
        )
    return matches[0]


def maximum_corner_angle(
    expected: FlatSnapshot, actual: FlatSnapshot
) -> float:
    if expected.face_starts != actual.face_starts:
        raise AssertionError("逐面角比较的 faceStarts 不一致。")
    if expected.vertex_ids != actual.vertex_ids:
        raise AssertionError("逐面角比较的顶点 ID 顺序不一致。")
    return max(
        (
            angle_degrees(expected.vector(index), actual.vector(index))
            for index in range(expected.corner_count)
        ),
        default=0.0,
    )


def classify_residual_corners(
    authority: FlatSnapshot, baseline: FlatSnapshot
) -> tuple[int, ...]:
    if authority.face_starts != baseline.face_starts:
        raise AssertionError("权威法线与 SG 基线 faceStarts 不一致。")
    if authority.vertex_ids != baseline.vertex_ids:
        raise AssertionError("权威法线与 SG 基线顶点角顺序不一致。")
    return tuple(
        index
        for index in range(authority.corner_count)
        if angle_degrees(authority.vector(index), baseline.vector(index))
        > RESIDUAL_TOLERANCE_DEGREES
    )


def retained_smoothing_fan_closure(
    baseline: FlatSnapshot,
    residual_corners: Iterable[int],
) -> tuple[int, ...]:
    residual = tuple(int(index) for index in residual_corners)
    baseline_ids = {baseline.normal_ids[index] for index in residual}
    return tuple(
        index
        for index, normal_id in enumerate(baseline.normal_ids)
        if normal_id in baseline_ids
    )


def assert_all_source_normals_authored(label: str, value: FlatSnapshot) -> None:
    if not all(value.specified):
        missing = [index for index, state in enumerate(value.specified) if not state]
        raise AssertionError(f"{label} 源法线并非全部 Specified：{missing}")
    if not all(value.explicit):
        missing = [index for index, state in enumerate(value.explicit) if not state]
        raise AssertionError(f"{label} 源法线并非全部 Explicit：{missing}")


def edge_angle(
    value: FlatSnapshot,
    face_a: int,
    face_b: int,
    vertex_id: int,
) -> float:
    corner_a = corner_for_vertex(value, face_a, vertex_id)
    corner_b = corner_for_vertex(value, face_b, vertex_id)
    return angle_degrees(value.vector(corner_a), value.vector(corner_b))


def assert_mixed_edges(label: str, value: FlatSnapshot) -> dict[str, list[float]]:
    soft_angles = [
        edge_angle(value, 1, 2, 1),
        edge_angle(value, 1, 2, 3),
    ]
    hard_angles = [
        edge_angle(value, 2, 3, 1),
        edge_angle(value, 2, 3, 4),
    ]
    if any(angle > EDGE_TOLERANCE_DEGREES for angle in soft_angles):
        raise AssertionError(f"{label} SG1 软边不连续：{soft_angles}")
    if any(angle < MIN_HARD_EDGE_DEGREES for angle in hard_angles):
        raise AssertionError(f"{label} SG1/SG2 硬边未断开：{hard_angles}")
    return {
        "soft_edge_angles_degrees": soft_angles,
        "hard_edge_angles_degrees": hard_angles,
    }


def assert_final_state(
    label: str,
    authority: FlatSnapshot,
    baseline: FlatSnapshot,
    final: FlatSnapshot,
    expected_residual: Iterable[int],
    expected_retained: Iterable[int],
) -> dict[str, Any]:
    semantic = set(int(index) for index in expected_residual)
    retained = set(int(index) for index in expected_retained)
    if not semantic.issubset(retained):
        raise AssertionError(
            f"{label} 语义残差不在最小稳定闭包内："
            f"{sorted(semantic)}/{sorted(retained)}"
        )
    specified = {
        index for index, state in enumerate(final.specified) if bool(state)
    }
    explicit_corners = {
        index for index, state in enumerate(final.explicit) if bool(state)
    }
    if specified != retained:
        raise AssertionError(
            f"{label} Specified 角集合不是最小稳定闭包："
            f"期望 {sorted(retained)}，实际 {sorted(specified)}"
        )
    if explicit_corners != retained:
        raise AssertionError(
            f"{label} Explicit 角集合不是最小稳定闭包："
            f"期望 {sorted(retained)}，实际 {sorted(explicit_corners)}"
        )

    expected_explicit_ids = {final.normal_ids[index] for index in retained}
    if final.explicit_normal_count != len(expected_explicit_ids):
        raise AssertionError(
            f"{label} 存在多余 Explicit normal 记录："
            f"{final.explicit_normal_count}/{len(expected_explicit_ids)}"
        )

    max_angle = maximum_corner_angle(authority, final)
    if max_angle > FINAL_TOLERANCE_DEGREES:
        raise AssertionError(
            f"{label} 最终逐面角方向不等价："
            f"{max_angle:.9f}° > {FINAL_TOLERANCE_DEGREES}°"
        )
    if final.smoothing_masks != SG_MASKS:
        raise AssertionError(
            f"{label} 法线写入改变了 SG 掩码：{final.smoothing_masks}"
        )

    wrong_addition: list[dict[str, float | int]] = []
    for index in sorted(semantic):
        wrong = normalized_sum(baseline.vector(index), authority.vector(index))
        wrong_to_authority = angle_degrees(wrong, authority.vector(index))
        actual_to_wrong = angle_degrees(final.vector(index), wrong)
        if wrong_to_authority < MIN_WRONG_ADDITION_DEGREES:
            raise AssertionError(
                f"{label} 第 {index} 角夹具不足以区分错误叠加："
                f"{wrong_to_authority:.6f}°"
            )
        if actual_to_wrong < MIN_WRONG_ADDITION_DEGREES:
            raise AssertionError(
                f"{label} 第 {index} 角结果接近错误的 normalize(SG+最终法线)："
                f"{actual_to_wrong:.6f}°"
            )
        wrong_addition.append(
            {
                "corner": index,
                "wrong_sum_to_authority_degrees": wrong_to_authority,
                "actual_to_wrong_sum_degrees": actual_to_wrong,
            }
        )

    return {
        "corner_count": final.corner_count,
        "semantic_residual_corners": sorted(semantic),
        "guard_corners": sorted(retained - semantic),
        "retained_corners": sorted(retained),
        "specified_corners": sorted(specified),
        "explicit_corners": sorted(explicit_corners),
        "explicit_normal_records": final.explicit_normal_count,
        "max_final_angle_degrees": max_angle,
        "wrong_addition_oracle": wrong_addition,
    }


def create_fan(name: str, offset: float) -> int:
    handle = int(rt.F2M_HNE_createBentFan(str(name), float(offset)))
    if handle <= 0:
        raise AssertionError(helper_error())
    return handle


def author_source(
    kind: str,
    node: Any,
    modifier_name: str,
) -> None:
    if kind == "all_sg":
        ok = bool(rt.F2M_HNE_authorAllBaseline(node, modifier_name))
    elif kind == "shared_id":
        # Faces 2 and 3 meet at vertex 4.  Their SG masks differ, so their
        # baseline directions differ.  Make both corners reference face 2's
        # normal ID: face 2 still matches SG, only face 3 needs an override.
        ok = bool(
            rt.F2M_HNE_authorSharedHardFan(
                node,
                2,
                3,
                3,
                2,
                modifier_name,
            )
        )
    elif kind == "local_tilt":
        # Face 3 corner 3 is vertex 5.  Break it away, then tilt exactly one
        # corner by 25 degrees while every other imported normal remains an
        # authored-but-SG-equivalent final direction.
        ok = bool(
            rt.F2M_HNE_authorLocalTilt(
                node,
                3,
                3,
                25.0,
                modifier_name,
            )
        )
    else:
        raise AssertionError(f"未知夹具类型：{kind}")
    if not ok:
        raise AssertionError(helper_error())


def transfer_hybrid(module: Any, source: Any, target: Any, sentinel: int):
    context = module.TransferContext(
        module.TransferOptions(
            fbx_path="",
            transfer_smoothing_groups=True,
            transfer_normals=True,
            show_ui=False,
        ),
        module.TransferLog(),
    )
    report = module.ObjectReport(name=str(target.name), status="验收")
    expected_selection = select_handle(sentinel)
    if not module.copy_smoothing_groups(source, target, context, report):
        raise AssertionError("光滑组传递失败：" + " | ".join(report.messages))
    if selection_handles() != expected_selection:
        raise AssertionError("光滑组传递改变了选择句柄。")

    baseline = snapshot(target, modifier_name="", allow_temporary=True)
    masks_before_normals = baseline.smoothing_masks

    if not module.copy_normals(
        source,
        target,
        report,
        smoothing_residual_only=True,
    ):
        raise AssertionError("混合法线传递失败：" + " | ".join(report.messages))
    if selection_handles() != expected_selection:
        raise AssertionError("混合法线传递改变了选择句柄。")
    if baseline.smoothing_masks != masks_before_normals:
        raise AssertionError("法线传递前的 SG 基线快照自相矛盾。")
    return baseline, report


def run_case(
    module: Any,
    *,
    name: str,
    author_kind: str,
    source_offset: float,
    sentinel: int,
    known_residual: tuple[int, ...],
    verify_mixed_edges: bool,
) -> tuple[CaseExpectation, dict[str, Any]]:
    source_name = f"F2M_HNE_{name}_Source"
    target_name = f"F2M_HNE_{name}_Target"
    modifier_name = f"F2M_HNE_SourceNormals_{name}"
    source_handle = create_fan(source_name, source_offset)
    target_handle = create_fan(target_name, source_offset + 3.0)
    source = None
    target = None
    try:
        source = node_by_handle(source_handle)
        target = node_by_handle(target_handle)
        set_smoothing_masks(source, SG_MASKS)
        set_smoothing_masks(target, INITIAL_TARGET_MASKS)

        source_baseline = snapshot(
            source,
            modifier_name="",
            allow_temporary=True,
        )
        if source_baseline.smoothing_masks != SG_MASKS:
            raise AssertionError(
                f"{name} 源 SG 写入失败：{source_baseline.smoothing_masks}"
            )
        author_source(author_kind, source, modifier_name)
        authority = snapshot(
            source,
            modifier_name=modifier_name,
            allow_temporary=False,
        )
        assert_all_source_normals_authored(name, authority)
        source_residual = classify_residual_corners(authority, source_baseline)
        if source_residual != known_residual:
            raise AssertionError(
                f"{name} 源夹具自身的必要残差角不符合设计："
                f"期望 {known_residual}，实际 {source_residual}"
            )
        source_retained = retained_smoothing_fan_closure(
            source_baseline,
            source_residual,
        )

        target_baseline, report = transfer_hybrid(
            module,
            source,
            target,
            sentinel,
        )
        if target_baseline.smoothing_masks != SG_MASKS:
            raise AssertionError(
                f"{name} SG 传递读回错误：{target_baseline.smoothing_masks}"
            )
        baseline_equivalence = maximum_corner_angle(
            source_baseline,
            target_baseline,
        )
        if baseline_equivalence > FINAL_TOLERANCE_DEGREES:
            raise AssertionError(
                f"{name} 源/目标 SG 基线不等价：{baseline_equivalence:.9f}°"
            )

        residual = classify_residual_corners(authority, target_baseline)
        if residual != known_residual:
            raise AssertionError(
                f"{name} 目标 SG 基线的必要残差角不符合设计："
                f"期望 {known_residual}，实际 {residual}"
            )
        if residual != source_residual:
            raise AssertionError(
                f"{name} 源/目标 SG 基线分类不一致："
                f"源 {source_residual}，目标 {residual}"
            )
        retained = retained_smoothing_fan_closure(target_baseline, residual)
        if retained != source_retained:
            raise AssertionError(
                f"{name} 源/目标 SG 最小稳定闭包不一致："
                f"源 {source_retained}，目标 {retained}"
            )

        f2m_count = int(rt.F2M_HNE_countF2M(target))
        # Keep the same stack-bottom modifier that evaluated the SG baseline.
        # With zero residual it remains non-Explicit instead of becoming a
        # short-lived native Edit_Normals instance that is immediately deleted.
        expect_f2m = True
        if f2m_count != (1 if expect_f2m else 0):
            raise AssertionError(
                f"{name} F2M Edit Normals 数错误：{f2m_count}/"
                f"{1 if expect_f2m else 0}"
            )
        final = snapshot(
            target,
            modifier_name=F2M_NORMAL_MODIFIER_NAME if expect_f2m else "",
            allow_temporary=not expect_f2m,
        )
        if final.smoothing_masks != target_baseline.smoothing_masks:
            raise AssertionError(
                f"{name} 法线写入改变了 SG："
                f"{target_baseline.smoothing_masks}->{final.smoothing_masks}"
            )
        metrics = assert_final_state(
            name,
            authority,
            target_baseline,
            final,
            residual,
            retained,
        )

        edge_metrics: dict[str, list[float]] = {}
        if verify_mixed_edges:
            edge_metrics = assert_mixed_edges(
                f"{name} SG 基线",
                target_baseline,
            )
            assert_mixed_edges(f"{name} 组合结果", final)

        if author_kind == "shared_id":
            matching_corner = corner_index(authority, 2, 3)
            residual_corner = corner_index(authority, 3, 2)
            if authority.normal_ids[matching_corner] != authority.normal_ids[
                residual_corner
            ]:
                raise AssertionError("共享 ID 夹具没有真正共享 source normal ID。")
            if residual != (residual_corner,):
                raise AssertionError(
                    "共享 ID 夹具必须只让硬边第二侧成为必要残差角。"
                )
            matching_angle = angle_degrees(
                authority.vector(matching_corner),
                target_baseline.vector(matching_corner),
            )
            residual_angle = angle_degrees(
                authority.vector(residual_corner),
                target_baseline.vector(residual_corner),
            )
            if matching_angle > FINAL_TOLERANCE_DEGREES:
                raise AssertionError(
                    f"共享 ID 第一角本应由 SG 表达：{matching_angle:.9f}°"
                )
            if residual_angle < MIN_HARD_EDGE_DEGREES:
                raise AssertionError(
                    f"共享 ID 第二角没有形成明确残差：{residual_angle:.9f}°"
                )
        elif author_kind == "local_tilt":
            expected_guard = (corner_index(authority, 4, 2),)
            actual_guard = tuple(
                index for index in retained if index not in set(residual)
            )
            if actual_guard != expected_guard:
                raise AssertionError(
                    "局部软扇区夹具必须产生一个确定的 Max 稳定保护角："
                    f"期望 {expected_guard}，实际 {actual_guard}"
                )

        expectation = CaseExpectation(
            name=name,
            target_name=target_name,
            authority=authority,
            baseline=target_baseline,
            residual_corners=residual,
            retained_corners=retained,
            expect_f2m_modifier=expect_f2m,
            verify_mixed_edges=verify_mixed_edges,
        )
        detail = {
            "name": name,
            "status": "PASS",
            "source_all_corners_specified": all(authority.specified),
            "source_all_corners_explicit": all(authority.explicit),
            "source_target_sg_baseline_max_angle_degrees": baseline_equivalence,
            "source_semantic_residual_corners": list(source_residual),
            "stable_retained_corners": list(retained),
            "stable_guard_corners": [
                index for index in retained if index not in set(residual)
            ],
            "smoothing_masks_before_normals": list(
                target_baseline.smoothing_masks
            ),
            "smoothing_masks_after_normals": list(final.smoothing_masks),
            "f2m_modifier_count": f2m_count,
            "report_messages": list(report.messages),
            "edge_metrics": edge_metrics,
            "before_reload": metrics,
        }
        return expectation, detail
    finally:
        source = None
        target = None


def validate_reloaded_case(
    expectation: CaseExpectation,
) -> dict[str, Any]:
    target = None
    try:
        target = node_by_name(expectation.target_name)
        f2m_count = int(rt.F2M_HNE_countF2M(target))
        wanted = 1 if expectation.expect_f2m_modifier else 0
        if f2m_count != wanted:
            raise AssertionError(
                f"{expectation.name} 重载后 F2M 修改器数错误："
                f"{f2m_count}/{wanted}"
            )
        final = snapshot(
            target,
            modifier_name=(
                F2M_NORMAL_MODIFIER_NAME
                if expectation.expect_f2m_modifier
                else ""
            ),
            allow_temporary=not expectation.expect_f2m_modifier,
        )
        metrics = assert_final_state(
            f"{expectation.name} 保存重载",
            expectation.authority,
            expectation.baseline,
            final,
            expectation.residual_corners,
            expectation.retained_corners,
        )
        if expectation.verify_mixed_edges:
            metrics["edge_metrics"] = assert_mixed_edges(
                f"{expectation.name} 保存重载",
                final,
            )
        metrics["f2m_modifier_count"] = f2m_count
        metrics["smoothing_masks"] = list(final.smoothing_masks)
        return metrics
    finally:
        target = None


def run_acceptance(token: str) -> dict[str, Any]:
    module = load_topology_module(token)
    install_maxscript_helpers()
    heap_before = heap_check_text()
    if not heap_check_ok(heap_before):
        raise AssertionError(f"运行前 heapCheck 异常：{heap_before}")

    scene_path = os.path.join(
        tempfile.gettempdir(),
        f"FBXTo3dsMax_hybrid_normals_{token}.max",
    )
    expectations: list[CaseExpectation] = []
    details: list[dict[str, Any]] = []
    persisted_details: list[dict[str, Any]] = []
    try:
        rt.resetMaxFile(rt.Name("noPrompt"))
        sentinel = int(rt.F2M_HNE_createSentinel("F2M_HNE_SelectionSentinel"))
        if sentinel <= 0:
            raise AssertionError(helper_error())
        select_handle(sentinel)

        # Four triangles have three corners each.  Face/corner choices below
        # therefore map to deterministic zero-based flat indices.
        all_sg, all_sg_detail = run_case(
            module,
            name="AllSGExpressible",
            author_kind="all_sg",
            source_offset=0.0,
            sentinel=sentinel,
            known_residual=(),
            verify_mixed_edges=False,
        )
        expectations.append(all_sg)
        details.append(all_sg_detail)

        shared_residual_index = 6 + 1  # face 3, corner 2
        shared, shared_detail = run_case(
            module,
            name="SharedIdPartialResidual",
            author_kind="shared_id",
            source_offset=10.0,
            sentinel=sentinel,
            known_residual=(shared_residual_index,),
            verify_mixed_edges=False,
        )
        expectations.append(shared)
        details.append(shared_detail)

        local_residual_index = 6 + 2  # face 3, corner 3
        mixed, mixed_detail = run_case(
            module,
            name="HardSoftLocalCustom",
            author_kind="local_tilt",
            source_offset=20.0,
            sentinel=sentinel,
            known_residual=(local_residual_index,),
            verify_mixed_edges=True,
        )
        expectations.append(mixed)
        details.append(mixed_detail)

        if selection_handles() != (sentinel,):
            raise AssertionError("三案例执行后选择句柄没有恢复到哨兵。")
        if not bool(rt.saveMaxFile(scene_path, useNewFile=False, quiet=True)):
            raise AssertionError(f"无法保存混合法线临时场景：{scene_path}")

        # Expectations contain only Python primitives.  Do not retain any
        # node/modifier wrapper while destroying and reloading the scene.
        rt.clearSelection()
        rt.resetMaxFile(rt.Name("noPrompt"))
        if not bool(rt.loadMaxFile(scene_path, quiet=True, useFileUnits=True)):
            raise AssertionError(f"无法重载混合法线临时场景：{scene_path}")

        for expectation in expectations:
            persisted_details.append(
                {
                    "name": expectation.name,
                    "status": "PASS",
                    "after_reload": validate_reloaded_case(expectation),
                }
            )
    finally:
        try:
            rt.clearSelection()
        except Exception:
            pass
        try:
            rt.resetMaxFile(rt.Name("noPrompt"))
        except Exception:
            pass
        try:
            if os.path.isfile(scene_path):
                os.remove(scene_path)
        except Exception:
            pass

    heap_after = heap_check_text()
    if not heap_check_ok(heap_after):
        raise AssertionError(f"运行后 heapCheck 异常：{heap_after}")
    if len(details) != 3 or len(persisted_details) != 3:
        raise AssertionError("混合法线三案例没有全部完成。")
    return {
        "version": EXPECTED_VERSION,
        "case_count": len(details),
        "cases": details,
        "persistence_case_count": len(persisted_details),
        "persistence_cases": persisted_details,
        "saved_and_reloaded": True,
        "heap_check_before": heap_before,
        "heap_check_after": heap_after,
        "residual_tolerance_degrees": RESIDUAL_TOLERANCE_DEGREES,
        "final_tolerance_degrees": FINAL_TOLERANCE_DEGREES,
        "temporary_scene_removed": not os.path.exists(scene_path),
    }


def main() -> None:
    token, result_path = validate_launcher_environment()
    pid = os.getpid()
    started = utc_now()
    print(
        "F2M_HYBRID_NORMALS_BEGIN "
        f"TOKEN={token} PID={pid} UTC={started}",
        flush=True,
    )
    payload: dict[str, Any] = {
        "state": "finished",
        "ok": False,
        "token": token,
        "pid": pid,
        "script_path": os.path.abspath(__file__),
        "started_at_utc": started,
        "finished_at_utc": "",
        "version": EXPECTED_VERSION,
        "error": "",
    }
    try:
        payload.update(run_acceptance(token))
        payload["ok"] = True
    except BaseException:
        payload["error"] = traceback.format_exc()
    payload["finished_at_utc"] = utc_now()
    atomic_json_write(result_path, payload, token)
    print(
        "F2M_HYBRID_NORMALS_END "
        f"TOKEN={token} PID={pid} UTC={payload['finished_at_utc']} "
        f"OK={'true' if payload['ok'] else 'false'}",
        flush=True,
    )
    if not payload["ok"]:
        raise RuntimeError(
            "混合法线逐面角等价验收失败；请查看专用 JSON 与 Max.log 发布门。"
        )


if __name__ == "__main__":
    main()
