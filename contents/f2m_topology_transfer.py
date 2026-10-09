# -*- coding: utf-8 -*-
"""
FBX 到 3ds Max 数据传递工具

运行环境：
- 3ds Max 2023 或更高版本
- 3ds Max 自带 Python / pymxs

这个文件是核心逻辑。中文界面在 FBXTo3dsMax_UI.ms 中。
"""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    import pymxs  # type: ignore

    rt = pymxs.runtime
except Exception:  # 允许在普通 Python 中做语法检查
    pymxs = None
    rt = None


TOOL_AUTHOR = "Dimmens"
TOOL_VERSION = "1.4.25"
LAST_RUN_OK = False
LAST_RUN_REPORT_PATH = ""
LAST_RUN_SUMMARY = ""

STRICT_RESOLVER_SCHEMA = "FBXTo3dsMax.strict_resolver"
STRICT_RESOLVER_SCHEMA_VERSION = 1
STRICT_RESOLVER_TOPOLOGY_ENCODING = (
    "little-endian uint32 face_degree followed by uint32 zero-based "
    "vertex IDs, repeated in FBX face order"
)
STRICT_RESOLVER_TIMEOUT_SECONDS = 180
STRICT_RESOLVER_MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAXSCRIPT_MIN_HEAP_BYTES = 512 * 1024 * 1024


def _language_runtime() -> Any:
    """Load the exact sibling presentation module; reject stale/foreign copies."""
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "f2m_i18n.py"))
    name = "_fbx_to_3dsmax_i18n_runtime"
    module = sys.modules.get(name)
    def valid(value: Any) -> bool:
        return bool(value is not None
            and os.path.normcase(os.path.abspath(str(getattr(value, "__file__", "")))) == os.path.normcase(path)
            and str(getattr(value, "TOOL_VERSION", "")) == TOOL_VERSION
            and getattr(value, "_F2M_IMPORT_COMPLETE", False) is True
            and callable(getattr(value, "translate", None))
            and callable(getattr(value, "get_language", None)))
    if not valid(module):
        sys.modules.pop(name, None)
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Cannot load the plug-in language module: " + path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
            if not valid(module):
                raise RuntimeError("Plug-in language module identity/version/API mismatch: " + path)
        except BaseException:
            if sys.modules.get(name) is module:
                sys.modules.pop(name, None)
            raise
    return module


def _display_text(text: Any) -> str:
    return str(_language_runtime().translate(str(text or "")))


HELPER_SCRIPT = r'''
global F2M_Helper
global F2M_TopologyHelper

struct F2M_TopologyHelperStruct
(
    lastMessage = "",
    apiKind = "topology",
    apiVersion = "1.4.25",

    fn setLastMessage msg =
    (
        lastMessage = msg as string
        true
    ),

    fn isGeometryNode n =
    (
        try
        (
            if (not isKindOf n GeometryClass) or (isKindOf n TargetObject) then
            (
                false
            )
            else
            (
                local baseName = ""
                try(baseName = (classof n.baseObject) as string)catch(baseName = "")
                baseName == "Editable_Poly" or
                baseName == "Editable_mesh" or
                baseName == "Editable Mesh" or
                matchPattern baseName pattern:"*PolyMesh*" ignoreCase:true or
                matchPattern baseName pattern:"*TriMesh*" ignoreCase:true or
                matchPattern baseName pattern:"*Mesh*" ignoreCase:true
            )
        )
        catch false
    ),

    fn findSkin n =
    (
        try
        (
            for m in n.modifiers where (classof m == Skin) do return m
        )
        catch()
        undefined
    ),

    fn skinIndex n =
    (
        local sk = findSkin n
        if sk == undefined then undefined else modPanel.getModifierIndex n sk
    ),

    fn modifierIndex n modInst =
    (
        try(modPanel.getModifierIndex n modInst)catch(undefined)
    ),

    fn modifierCount n =
    (
        try(n.modifiers.count)catch(0)
    ),

    fn addModifierBelowSkinOrStack n modInst =
    (
        if n.modifiers.count > 0 then
        (
            -- modifiers[1] 是栈顶。使用 count + 1 才会放到所有现有修改器下方、
            -- 基础对象上方，后续 CollapseNodeTo 不会吞掉用户原有修改器。
            addModifier n modInst before:(n.modifiers.count + 1)
        )
        else
        (
            addModifier n modInst
        )
        modInst
    ),

    fn collapseModifierSafely n modInst =
    (
        setLastMessage ""
        local newModNoSkin = undefined
        local idx = modifierIndex n modInst
        if idx == undefined do
        (
            setLastMessage "找不到要塌陷的 F2M 修改器。"
            modInst = undefined
            return false
        )

        local sk = findSkin n

        -- 把本次 F2M 修改器移到堆栈最底部再塌陷。
        -- CollapseNodeTo 会保留它上方的修改器，所以 Skin 和用户原有修改器不会被一起塌陷。
        if idx < n.modifiers.count then
        (
            local bottomIndex = n.modifiers.count + 1
            newModNoSkin = copy modInst
            local copiedNoSkin = false
            try
            (
                addModifierWithLocalData n newModNoSkin n modInst before:bottomIndex
                copiedNoSkin = true
            )
            catch
            (
                copiedNoSkin = false
            )
            if copiedNoSkin then
            (
                try(deleteModifier n modInst)catch()
                modInst = newModNoSkin
                idx = modifierIndex n modInst
            )
            else
            (
                setLastMessage "无法把 F2M 修改器安全移动到堆栈最底部，因此没有自动塌陷。"
                modInst = undefined
                newModNoSkin = undefined
                return false
            )
        )

        if idx == undefined do
        (
            setLastMessage "移动 F2M 修改器后无法重新定位。"
            modInst = undefined
            newModNoSkin = undefined
            return false
        )

        -- 只允许塌陷真正位于栈底的 F2M 修改器。否则 fail closed，
        -- 绝不拿用户原有 Skin/修改器冒险。
        if idx != n.modifiers.count do
        (
            setLastMessage "F2M 修改器没有位于栈底，已停止塌陷以保护原有修改器。"
            modInst = undefined
            newModNoSkin = undefined
            return false
        )

        try
        (
            local ok = maxOps.CollapseNodeTo n idx true
            -- CollapseNodeTo may destroy the modifier.  Drop every alias
            -- before any subsequent MAXScript/native call can trigger GC.
            modInst = undefined
            newModNoSkin = undefined
            if ok then
            (
                if sk != undefined then
                (
                    setLastMessage "已塌陷 F2M 修改器，Skin 和其它原有修改器保留在其上方。"
                )
                else
                (
                    setLastMessage "已塌陷 F2M 修改器，其它原有修改器保留在其上方。"
                )
            )
            else
            (
                setLastMessage "maxOps.CollapseNodeTo 返回失败，F2M 修改器可能仍在堆栈中。"
            )
            ok
        )
        catch
        (
            modInst = undefined
            newModNoSkin = undefined
            setLastMessage ("塌陷 F2M 修改器失败：" + getCurrentException())
            false
        )
    ),

    fn meshCounts n =
    (
        local out = #(0, 0, 0)
        try
        (
            local baseName = (classof n.baseObject) as string
            if baseName == "Editable_Poly" then
            (
                local baseObj = n.baseObject
                out[1] = polyop.getNumVerts baseObj
                out[2] = polyop.getNumEdges baseObj
                out[3] = polyop.getNumFaces baseObj
            )
            else if baseName == "Editable_mesh" or baseName == "Editable Mesh" then
            (
                out[1] = getNumVerts n
                out[3] = getNumFaces n
                try(out[2] = meshop.getNumEdges n.mesh)catch(out[2] = 0)
            )
        )
        catch()
        out
    ),

    fn matrixMaxDelta a b =
    (
        local valuesA = #(a.row1.x, a.row1.y, a.row1.z, a.row2.x, a.row2.y, a.row2.z, a.row3.x, a.row3.y, a.row3.z, a.row4.x, a.row4.y, a.row4.z)
        local valuesB = #(b.row1.x, b.row1.y, b.row1.z, b.row2.x, b.row2.y, b.row2.z, b.row3.x, b.row3.y, b.row3.z, b.row4.x, b.row4.y, b.row4.z)
        local delta = 0.0
        for i = 1 to valuesA.count do delta = amax delta (abs(valuesA[i] - valuesB[i]))
        delta
    ),

    fn nodeObjectTransformBuffer n =
    (
        try
        (
            local value = n.objectTransform
            #(
                value.row1.x, value.row1.y, value.row1.z,
                value.row2.x, value.row2.y, value.row2.z,
                value.row3.x, value.row3.y, value.row3.z,
                value.row4.x, value.row4.y, value.row4.z
            )
        )
        catch(undefined)
    ),

    fn transformPairWarnings fbxTarget maxSource =
    (
        local out = #()
        try
        (
            local delta = matrixMaxDelta fbxTarget.objectTransform maxSource.objectTransform
            if delta > 0.001 do append out (
                "FBX 目标模型与 Max 源模型的对象空间变换不同（矩阵最大差 " +
                (delta as string) +
                "）。UV/颜色/光滑组不受影响；显式法线按逆转置矩阵转换，"
                "变形按相同顶点 ID 做“FBX 目标模型局部→世界→Max 源模型局部”点变换。"
            )
        )
        catch
        (
            append out ("无法比较 FBX 目标模型与 Max 源模型的对象空间变换：" + getCurrentException())
        )
        out
    ),

    fn baseClassName n =
    (
        try((classof n.baseObject) as string)catch("")
    ),

    fn hasMapChannel n channelId =
    (
        local ok = false
        local m = undefined
        try
        (
            m = snapshotAsMesh n
            ok = meshop.getMapSupport m channelId
        )
        catch(ok = false)
        try(if m != undefined do free m)catch()
        ok
    ),

    fn isPolyBase n =
    (
        try(((classof n.baseObject) as string) == "Editable_Poly")catch(false)
    ),

    fn isMeshBase n =
    (
        local baseName = ""
        try(baseName = (classof n.baseObject) as string)catch(baseName = "")
        (baseName == "Editable_mesh" or baseName == "Editable Mesh")
    ),

    fn faceVertexIndices n faceIndex =
    (
        try
        (
            if isPolyBase n then
            (
                for v in (polyop.getFaceVerts n faceIndex) collect (v as integer)
            )
            else if isMeshBase n then
            (
                local f = getFace n faceIndex
                #((f.x as integer), (f.y as integer), (f.z as integer))
            )
            else undefined
        )
        catch(undefined)
    ),

    fn topologyFaces n =
    (
        try
        (
            local faceCount = if isPolyBase n then (polyop.getNumFaces n) else if isMeshBase n then (getNumFaces n) else 0
            if faceCount < 1 do throw "基础对象不是可读取的 Editable Poly / Editable Mesh。"
            for faceIndex = 1 to faceCount collect (faceVertexIndices n faceIndex)
        )
        catch
        (
            setLastMessage ("读取基础多边形拓扑失败：" + getCurrentException())
            undefined
        )
    ),

    fn topologyFaceBuffer n =
    (
        setLastMessage ""
        try
        (
            local faceCount = if isPolyBase n then
                (polyop.getNumFaces n)
            else if isMeshBase n then
                (getNumFaces n)
            else 0
            if faceCount < 1 do
                throw "基础对象不是可读取的 Editable Poly / Editable Mesh。"
            local buffer = #(faceCount)
            for faceIndex = 1 to faceCount do
            (
                local face = faceVertexIndices n faceIndex
                if face == undefined or face.count < 3 do
                    throw ("第 " + (faceIndex as string) + " 个基础面无法读取。")
                append buffer face.count
                join buffer face
            )
            buffer
        )
        catch
        (
            setLastMessage ("读取扁平基础多边形拓扑失败：" + getCurrentException())
            undefined
        )
    ),

    fn triangleCycleEqual firstFace secondFace =
    (
        (
            firstFace.x == secondFace.x and
            firstFace.y == secondFace.y and
            firstFace.z == secondFace.z
        ) or (
            firstFace.x == secondFace.y and
            firstFace.y == secondFace.z and
            firstFace.z == secondFace.x
        ) or (
            firstFace.x == secondFace.z and
            firstFace.y == secondFace.x and
            firstFace.z == secondFace.y
        )
    ),

    fn evaluatedTriangleDifferenceCount firstNode secondNode =
    (
        local firstMesh = undefined
        local secondMesh = undefined
        local result = 0
        try
        (
            firstMesh = snapshotAsMesh firstNode
            secondMesh = snapshotAsMesh secondNode
            local firstCount = getNumFaces firstMesh
            local secondCount = getNumFaces secondMesh
            local sharedCount = amin firstCount secondCount
            result = abs(firstCount - secondCount)
            for faceIndex = 1 to sharedCount do
            (
                if not (
                    triangleCycleEqual
                        (getFace firstMesh faceIndex)
                        (getFace secondMesh faceIndex)
                ) do result += 1
            )
        )
        catch
        (
            result = -1
        )
        try(if firstMesh != undefined do free firstMesh)catch()
        try(if secondMesh != undefined do free secondMesh)catch()
        result
    ),

    fn setTopologyMessage message =
    (
        setLastMessage message
        true
    ),

    fn topologyMatches src dst =
    (
        setLastMessage ""
        try
        (
            if not ((isPolyBase src or isMeshBase src) and (isPolyBase dst or isMeshBase dst)) do
                throw "FBX 目标模型与 Max 源模型的基础对象必须是 Editable Poly 或 Editable Mesh。"

            local srcFaceCount = if isPolyBase src then (polyop.getNumFaces src) else (getNumFaces src)
            local dstFaceCount = if isPolyBase dst then (polyop.getNumFaces dst) else (getNumFaces dst)
            local srcVertCount = if isPolyBase src then (polyop.getNumVerts src) else (getNumVerts src)
            local dstVertCount = if isPolyBase dst then (polyop.getNumVerts dst) else (getNumVerts dst)
            if srcVertCount != dstVertCount do throw "FBX 目标模型与 Max 源模型的基础网格点数不同。"
            if srcFaceCount != dstFaceCount do throw "FBX 目标模型与 Max 源模型的基础网格面数不同。"

            for faceIndex = 1 to srcFaceCount do
            (
                local srcVerts = faceVertexIndices src faceIndex
                local dstVerts = faceVertexIndices dst faceIndex
                if srcVerts == undefined or dstVerts == undefined do throw ("第 " + faceIndex as string + " 面无法读取拓扑。")
                if srcVerts.count != dstVerts.count do throw ("第 " + faceIndex as string + " 面角数量不同。")
                for cornerIndex = 1 to srcVerts.count where srcVerts[cornerIndex] != dstVerts[cornerIndex] do
                    throw ("第 " + faceIndex as string + " 面的点序/角序不同。")
            )
            setLastMessage ("严格拓扑一致：点 " + srcVertCount as string + "，面 " + srcFaceCount as string + "，面序/点序/角序全部一致。")
            true
        )
        catch
        (
            setLastMessage ("严格拓扑不一致：" + getCurrentException())
            false
        )
    ),

    fn getFaceSmoothingGroups n =
    (
        setLastMessage ""
        local baseMesh = undefined
        try
        (
            local values = #()
            local baseObj = n.baseObject
            if isPolyBase n then
            (
                for faceIndex = 1 to (polyop.getNumFaces baseObj) do
                    append values (polyop.getFaceSmoothGroup baseObj faceIndex)
            )
            else if isMeshBase n then
            (
                -- 对带 Skin/其它对象空间修改器的 Editable Mesh，直接把节点
                -- 传给 get* 会读取最终栈。必须显式读取基础对象的 TriMesh，
                -- 才能让面索引和之后的基础网格写入保持一致。
                baseMesh = copy baseObj.mesh
                for faceIndex = 1 to (getNumFaces baseMesh) do
                    append values (getFaceSmoothGroup baseMesh faceIndex)
            )
            else throw "基础对象不是 Editable Poly / Editable Mesh。"
            try(if baseMesh != undefined do free baseMesh)catch()
            setLastMessage ("已读取 " + values.count as string + " 个面的光滑组。")
            values
        )
        catch
        (
            try(if baseMesh != undefined do free baseMesh)catch()
            setLastMessage ("读取光滑组失败：" + getCurrentException())
            undefined
        )
    ),

    fn canSetFaceSmoothingGroups n expectedFaceCount =
    (
        local baseMesh = undefined
        try
        (
            local baseObj = n.baseObject
            if isPolyBase n then
                ((polyop.getNumFaces baseObj) == expectedFaceCount)
            else if isMeshBase n then
            (
                baseMesh = copy baseObj.mesh
                local result = ((getNumFaces baseMesh) == expectedFaceCount)
                try(free baseMesh)catch()
                result
            )
            else false
        )
        catch
        (
            try(if baseMesh != undefined do free baseMesh)catch()
            false
        )
    ),

    fn compareSmoothingFaceEntries firstEntry secondEntry =
    (
        if firstEntry[1] < secondEntry[1] then -1
        else if firstEntry[1] > secondEntry[1] then 1
        else if firstEntry[2] < secondEntry[2] then -1
        else if firstEntry[2] > secondEntry[2] then 1
        else 0
    ),

    fn setPolyFaceSmoothingGroupsBatched baseObj values =
    (
        -- Common production FBX files use one smoothing mask for the whole
        -- mesh.  Handle that case without creating and sorting one nested
        -- MAXScript array per face; those short-lived arrays otherwise remain
        -- pending until Max's collector runs and can accumulate across models.
        if values.count < 1 do return 0
        local uniformMask = values[1]
        local uniform = true
        for faceIndex = 2 to values.count while uniform do
            if values[faceIndex] != uniformMask do uniform = false
        if uniform do
        (
            local allFaces = #{}
            for faceIndex = 1 to values.count do allFaces[faceIndex] = true
            polyop.setFaceSmoothGroup baseObj allFaces uniformMask add:false
            allFaces = undefined
            return 1
        )

        -- 先按“光滑组掩码、面号”排序，再线性建立每个掩码的 BitArray。
        -- 这样即使原生 FBX 含有几百/几千种组合掩码，也不会退化为逐面
        -- polyop 调用或 O(面数 × 掩码种类) 的线性查找。
        local entries = for faceIndex = 1 to values.count collect
            #(values[faceIndex], faceIndex)
        qsort entries compareSmoothingFaceEntries

        local batchCount = 0
        local currentMask = undefined
        local currentFaces = #{}
        for entry in entries do
        (
            local maskValue = entry[1]
            local faceIndex = entry[2]
            if currentMask == undefined or maskValue != currentMask then
            (
                if currentMask != undefined then
                (
                    polyop.setFaceSmoothGroup baseObj currentFaces currentMask add:false
                    batchCount += 1
                )
                currentMask = maskValue
                currentFaces = #{}
            )
            currentFaces[faceIndex] = true
        )
        if currentMask != undefined then
        (
            polyop.setFaceSmoothGroup baseObj currentFaces currentMask add:false
            batchCount += 1
        )
        batchCount
    ),

    fn setFaceSmoothingGroups n values =
    (
        setLastMessage ""
        local originalValues = undefined
        local originalMesh = undefined
        local workingMesh = undefined
        local writeBatchCount = 0
        local writeStarted = false
        try
        (
            if values == undefined do throw "没有可写入的光滑组数组。"
            if values.count < 1 do throw "光滑组数组为空；已拒绝对空网格执行写入。"
            for faceIndex = 1 to values.count do
            (
                local maskValue = values[faceIndex]
                local maskClassName = (classof maskValue) as string
                if maskClassName != "Integer" and maskClassName != "Integer64" do
                    throw ("第 " + faceIndex as string + " 面的光滑组不是 32 位整数。")
                if maskValue < -2147483648L or maskValue > 2147483647L do
                    throw ("第 " + faceIndex as string + " 面的光滑组超出 32 位有符号整数范围。")
                values[faceIndex] = maskValue as integer
            )
            if not (canSetFaceSmoothingGroups n values.count) do throw "Max 源模型基础网格类型或面数不匹配。"
            originalValues = getFaceSmoothingGroups n
            if originalValues == undefined or originalValues.count != values.count do
                throw "无法在写入前完整快照 Max 源模型原光滑组。"
            -- The combined SG+normal contract is deliberately write-first:
            -- even an identical mask set must pass through the same explicit
            -- base-object write and readback before the residual normal
            -- baseline is rebuilt.  Skipping an "equal" write produces a
            -- different normal-cache lifecycle and violates that ordering.
            local baseObj = n.baseObject
            if isPolyBase n then
            (
                writeStarted = true
                writeBatchCount = setPolyFaceSmoothingGroupsBatched baseObj values
            )
            else if isMeshBase n then
            (
                -- Mesh 节点带 Skin 等 OSM 时，节点级 setFaceSmoothGroup 会被
                -- Max 拒绝。改为复制基础 TriMesh、离线修改后一次性写回
                -- baseObject.mesh；失败时可用完整基础网格快照恢复。
                originalMesh = copy baseObj.mesh
                workingMesh = copy originalMesh
                for faceIndex = 1 to values.count do
                    setFaceSmoothGroup workingMesh faceIndex values[faceIndex]
                writeStarted = true
                baseObj.mesh = workingMesh
                try(free workingMesh)catch()
                workingMesh = undefined
            )
            else throw "Max 源模型基础对象不是 Editable Poly / Editable Mesh。"
            update n

            local readback = getFaceSmoothingGroups n
            if readback == undefined or readback.count != values.count do throw "写后回读数量不一致。"
            for faceIndex = 1 to values.count where readback[faceIndex] != values[faceIndex] do
                throw ("第 " + faceIndex as string + " 面写后回读不一致。")
            local batchMessage = ""
            if writeBatchCount > 0 do
                batchMessage = "，按相同掩码合并为 " + writeBatchCount as string + " 个批次"
            if isMeshBase n do
                batchMessage = "，通过基础 TriMesh 单次事务写回"
            setLastMessage (
                "光滑组完成：已写入并回读验证 " + values.count as string +
                " 个面" + batchMessage + "。"
            )
            try(if originalMesh != undefined do free originalMesh)catch()
            true
        )
        catch
        (
            local writeError = getCurrentException()
            local rollbackOk = false
            local rollbackError = ""
            if not writeStarted then
            (
                try(if workingMesh != undefined do free workingMesh)catch()
                try(if originalMesh != undefined do free originalMesh)catch()
                setLastMessage ("光滑组写入前检查失败：" + writeError)
                return false
            )
            try
            (
                local rollbackBaseObj = n.baseObject
                if originalValues == undefined do
                (
                    rollbackError = "没有可回滚的原光滑组快照。"
                    throw()
                )
                if isPolyBase n then
                (
                    setPolyFaceSmoothingGroupsBatched rollbackBaseObj originalValues
                )
                else if isMeshBase n then
                (
                    if originalMesh == undefined do
                    (
                        rollbackError = "没有可回滚的基础 TriMesh 快照。"
                        throw()
                    )
                    rollbackBaseObj.mesh = originalMesh
                )
                else
                (
                    rollbackError = "Max 源模型基础类型已改变。"
                    throw()
                )
                update n
                local rollbackReadback = getFaceSmoothingGroups n
                if rollbackReadback == undefined or rollbackReadback.count != originalValues.count do
                (
                    rollbackError = "回滚读回数量不一致。"
                    throw()
                )
                for faceIndex = 1 to originalValues.count where rollbackReadback[faceIndex] != originalValues[faceIndex] do
                (
                    rollbackError = "回滚后第 " + faceIndex as string + " 面不一致。"
                    throw()
                )
                rollbackOk = true
            )
            catch(if rollbackError == "" do rollbackError = getCurrentException())
            try(if workingMesh != undefined do free workingMesh)catch()
            try(if originalMesh != undefined do free originalMesh)catch()
            if rollbackOk then
                setLastMessage ("光滑组失败：" + writeError + "；已完整回滚原光滑组。")
            else
                setLastMessage ("光滑组失败：" + writeError + "；原光滑组回滚失败：" + rollbackError)
            false
        )
    ),

    fn fbxImporterGet name =
    (
        try(FBXImporterGetParam name)catch(undefined)
    ),

    fn fbxImporterSet name value =
    (
        try(FBXImporterSetParam name value)catch(undefined)
    ),

    fn point3ToMapArray p =
    (
        #((p.x as integer), (p.y as integer), (p.z as integer))
    ),

    fn intArrayEqual a b =
    (
        if a == undefined or b == undefined or a.count != b.count do return false
        for i = 1 to a.count where (a[i] as integer) != (b[i] as integer) do return false
        true
    ),

    fn mappedSourceFace faceMap targetFace =
    (
        if faceMap == undefined or faceMap.count == 0 then targetFace else faceMap[targetFace]
    ),

    fn mappedCornerArray sourceValues cornerMaps targetFace =
    (
        if cornerMaps == undefined or cornerMaps.count == 0 then
        (
            for value in sourceValues collect (value as integer)
        )
        else
        (
            local cornerMap = cornerMaps[targetFace]
            if cornerMap == undefined or cornerMap.count != sourceValues.count do
                throw ("第 " + targetFace as string + " 面的角映射数量不一致。")
            for targetCorner = 1 to cornerMap.count collect
            (
                local sourceCorner = cornerMap[targetCorner]
                if sourceCorner < 1 or sourceCorner > sourceValues.count do
                    throw ("第 " + targetFace as string + " 面的角映射越界。")
                sourceValues[sourceCorner] as integer
            )
        )
    ),

    fn meshMapFaceToArray value =
    (
        #((value.x as integer), (value.y as integer), (value.z as integer))
    ),

    fn copyMapChannelDirect src dst channelId faceMap:#() cornerMaps:#() =
    (
        setLastMessage ""
        local ok = false
        local snapshotType = ""
        local originalSupport = false
        local originalMapVerts = #()
        local originalMapFaces = #()
        try
        (
            if isPolyBase src and isPolyBase dst then
            (
                if not (polyop.getMapSupport src channelId) do throw ("FBX 目标模型没有通道 " + (channelId as string))
                local srcMapVerts = polyop.getNumMapVerts src channelId
                local srcMapFaces = polyop.getNumMapFaces src channelId
                if (polyop.getNumFaces dst) != srcMapFaces do throw ("Max 源模型 Poly 面数量与 FBX 目标通道面数量不一致，不能直接写入。")

                snapshotType = "poly"
                originalSupport = polyop.getMapSupport dst channelId
                if originalSupport then
                (
                    for i = 1 to (polyop.getNumMapVerts dst channelId) do
                        append originalMapVerts (polyop.getMapVert dst channelId i)
                    for f = 1 to (polyop.getNumMapFaces dst channelId) do
                    (
                        local originalFace = polyop.getMapFace dst channelId f
                        append originalMapFaces (
                            for value in originalFace collect (value as integer)
                        )
                    )
                )

                polyop.setMapSupport dst channelId true
                polyop.setNumMapVerts dst channelId srcMapVerts keep:false
                polyop.setNumMapFaces dst channelId srcMapFaces keep:false

                for i = 1 to srcMapVerts do
                (
                    polyop.setMapVert dst channelId i (polyop.getMapVert src channelId i)
                )
                for f = 1 to srcMapFaces do
                (
                    local sourceFace = mappedSourceFace faceMap f
                    if sourceFace < 1 or sourceFace > srcMapFaces do throw ("第 " + f as string + " 个 Max 源面映射到越界 FBX 目标面。")
                    local mappedFace = mappedCornerArray (polyop.getMapFace src channelId sourceFace) cornerMaps f
                    polyop.setMapFace dst channelId f mappedFace
                )
                update dst
                if (polyop.getNumMapVerts dst channelId) != srcMapVerts do throw "写后回读 Map Vert 数量不一致。"
                if (polyop.getNumMapFaces dst channelId) != srcMapFaces do throw "写后回读 Map Face 数量不一致。"
                for i = 1 to srcMapVerts where (distance (polyop.getMapVert dst channelId i) (polyop.getMapVert src channelId i)) > 0.000001 do
                    throw ("写后回读第 " + i as string + " 个 Map Vert 不一致。")
                for f = 1 to srcMapFaces do
                (
                    local sourceFace = mappedSourceFace faceMap f
                    local mappedFace = mappedCornerArray (polyop.getMapFace src channelId sourceFace) cornerMaps f
                    if not (intArrayEqual (polyop.getMapFace dst channelId f) mappedFace) do
                        throw ("写后回读第 " + f as string + " 个 Map Face 不一致。")
                )
                setLastMessage ("通道 " + (channelId as string) + " 已直接写入 Editable Poly 基础网格，没有生成临时修改器。")
                ok = true
            )
            else if isMeshBase src and isMeshBase dst then
            (
                local srcMesh = src.mesh
                local dstMesh = dst.mesh
                if not (meshop.getMapSupport srcMesh channelId) do throw ("FBX 目标模型没有通道 " + (channelId as string))
                local srcMapVerts = meshop.getNumMapVerts srcMesh channelId
                local srcMapFaces = meshop.getNumMapFaces srcMesh channelId
                if (getNumFaces dstMesh) != srcMapFaces do throw ("Max 源模型 Mesh 面数量与 FBX 目标通道面数量不一致，不能直接写入。")

                snapshotType = "mesh"
                originalSupport = meshop.getMapSupport dstMesh channelId
                if originalSupport then
                (
                    for i = 1 to (meshop.getNumMapVerts dstMesh channelId) do
                        append originalMapVerts (meshop.getMapVert dstMesh channelId i)
                    for f = 1 to (meshop.getNumMapFaces dstMesh channelId) do
                        append originalMapFaces (meshop.getMapFace dstMesh channelId f)
                )

                meshop.setMapSupport dstMesh channelId true
                meshop.setNumMapVerts dstMesh channelId srcMapVerts keep:false
                try(meshop.setNumMapFaces dstMesh channelId srcMapFaces keep:false)catch()

                for i = 1 to srcMapVerts do
                (
                    meshop.setMapVert dstMesh channelId i (meshop.getMapVert srcMesh channelId i)
                )
                for f = 1 to srcMapFaces do
                (
                    local sourceFace = mappedSourceFace faceMap f
                    if sourceFace < 1 or sourceFace > srcMapFaces do throw ("第 " + f as string + " 个 Max 源面映射到越界 FBX 目标面。")
                    local sourceValues = meshMapFaceToArray (meshop.getMapFace srcMesh channelId sourceFace)
                    local mappedFace = mappedCornerArray sourceValues cornerMaps f
                    if mappedFace.count != 3 do throw "Editable Mesh 的 Map Face 必须有 3 个角。"
                    meshop.setMapFace dstMesh channelId f [mappedFace[1], mappedFace[2], mappedFace[3]]
                )
                update dst
                if (meshop.getNumMapVerts dstMesh channelId) != srcMapVerts do throw "写后回读 Map Vert 数量不一致。"
                if (meshop.getNumMapFaces dstMesh channelId) != srcMapFaces do throw "写后回读 Map Face 数量不一致。"
                for i = 1 to srcMapVerts where (distance (meshop.getMapVert dstMesh channelId i) (meshop.getMapVert srcMesh channelId i)) > 0.000001 do
                    throw ("写后回读第 " + i as string + " 个 Map Vert 不一致。")
                for f = 1 to srcMapFaces do
                (
                    local sourceFace = mappedSourceFace faceMap f
                    local sourceValues = meshMapFaceToArray (meshop.getMapFace srcMesh channelId sourceFace)
                    local mappedFace = mappedCornerArray sourceValues cornerMaps f
                    local readback = meshMapFaceToArray (meshop.getMapFace dstMesh channelId f)
                    if not (intArrayEqual readback mappedFace) do
                        throw ("写后回读第 " + f as string + " 个 Map Face 不一致。")
                )
                setLastMessage ("通道 " + (channelId as string) + " 已直接写入 Editable Mesh 基础网格，没有生成临时修改器。")
                ok = true
            )
            else
            (
                setLastMessage "FBX 目标模型与 Max 源模型的基础类型不是同类 Editable Poly 或同类 Editable Mesh，改用 ChannelInfo。"
                ok = false
            )
        )
        catch
        (
            local writeError = getCurrentException()
            local rollbackOk = snapshotType == ""
            local rollbackError = ""
            try
            (
                if snapshotType == "poly" then
                (
                    if originalSupport then
                    (
                        polyop.setMapSupport dst channelId true
                        polyop.setNumMapVerts dst channelId originalMapVerts.count keep:false
                        polyop.setNumMapFaces dst channelId originalMapFaces.count keep:false
                        for i = 1 to originalMapVerts.count do polyop.setMapVert dst channelId i originalMapVerts[i]
                        for f = 1 to originalMapFaces.count do polyop.setMapFace dst channelId f originalMapFaces[f]
                    )
                    else
                    (
                        polyop.setMapSupport dst channelId false
                    )
                    update dst
                    rollbackOk = (polyop.getMapSupport dst channelId) == originalSupport
                    if rollbackOk and originalSupport then
                    (
                        rollbackOk = (polyop.getNumMapVerts dst channelId) == originalMapVerts.count and (polyop.getNumMapFaces dst channelId) == originalMapFaces.count
                        if rollbackOk do
                        (
                            for i = 1 to originalMapVerts.count where (distance (polyop.getMapVert dst channelId i) originalMapVerts[i]) > 0.000001 do rollbackOk = false
                            for f = 1 to originalMapFaces.count where not (intArrayEqual (polyop.getMapFace dst channelId f) originalMapFaces[f]) do rollbackOk = false
                        )
                    )
                )
                else if snapshotType == "mesh" then
                (
                    local dstMesh = dst.mesh
                    if originalSupport then
                    (
                        meshop.setMapSupport dstMesh channelId true
                        meshop.setNumMapVerts dstMesh channelId originalMapVerts.count keep:false
                        try(meshop.setNumMapFaces dstMesh channelId originalMapFaces.count keep:false)catch()
                        for i = 1 to originalMapVerts.count do meshop.setMapVert dstMesh channelId i originalMapVerts[i]
                        for f = 1 to originalMapFaces.count do meshop.setMapFace dstMesh channelId f originalMapFaces[f]
                    )
                    else
                    (
                        meshop.setMapSupport dstMesh channelId false
                    )
                    update dst
                    rollbackOk = (meshop.getMapSupport dstMesh channelId) == originalSupport
                    if rollbackOk and originalSupport then
                    (
                        rollbackOk = (meshop.getNumMapVerts dstMesh channelId) == originalMapVerts.count and (meshop.getNumMapFaces dstMesh channelId) == originalMapFaces.count
                        if rollbackOk do
                        (
                            for i = 1 to originalMapVerts.count where (distance (meshop.getMapVert dstMesh channelId i) originalMapVerts[i]) > 0.000001 do rollbackOk = false
                            for f = 1 to originalMapFaces.count where (meshop.getMapFace dstMesh channelId f) != originalMapFaces[f] do rollbackOk = false
                        )
                    )
                )
            )
            catch
            (
                rollbackError = getCurrentException()
                rollbackOk = false
            )
            if rollbackOk then
                setLastMessage ("直接写入通道失败：" + writeError + "；已回滚 Max 源模型原通道。")
            else
                setLastMessage ("直接写入通道失败：" + writeError + "；Max 源模型原通道回滚失败：" + rollbackError)
            ok = false
        )
        ok
    ),

    fn findNewModifier beforeMods afterMods =
    (
        for m in afterMods where (findItem beforeMods m) == 0 do return m
        undefined
    ),

    fn copyMapChannel src dst channelId =
    (
        local beforeMods = for m in dst.modifiers collect m
        ChannelInfo.CopyChannel src 3 channelId
        ChannelInfo.PasteChannel dst 3 channelId
        local afterMods = for m in dst.modifiers collect m
        local pastedMod = undefined
        try
        (
            pastedMod = findNewModifier beforeMods afterMods
            if pastedMod != undefined do pastedMod.name = ("F2M_粘贴贴图通道_" + (channelId as string))
        )
        catch()
        ChannelInfo.update()
        -- The comparison arrays are no longer needed.  They contain modifier
        -- wrappers, including the pasted modifier that may be collapsed below.
        beforeMods = #()
        afterMods = #()

        if pastedMod != undefined then
        (
            local collapseOk = collapseModifierSafely dst pastedMod
            pastedMod = undefined
            local collapseMessage = lastMessage as string
            if collapseOk then
            (
                setLastMessage ("ChannelInfo 通道 " + (channelId as string) + " 已粘贴并塌陷；" + collapseMessage)
            )
            else
            (
                setLastMessage ("ChannelInfo 通道 " + (channelId as string) + " 已粘贴，但未能安全塌陷；" + collapseMessage)
            )
            collapseOk
        )
        else
        (
            pastedMod = undefined
            setLastMessage ("ChannelInfo 通道 " + (channelId as string) + " 已执行复制/粘贴，但没有找到新增修改器。")
            false
        )
    ),

    fn activateModifier n modInst =
    (
        try
        (
            select n
            max modify mode
            modPanel.setCurrentObject modInst
            true
        )
        catch false
    ),

    fn rebuildEditNormalsStrict n modInst operationLabel =
    (
        local rebuildError = ""
        try
        (
            modInst.RebuildNormals node:n
        )
        catch
        (
            rebuildError = getCurrentException()
        )
        if rebuildError != "" do
            throw ((operationLabel as string) + "：" + rebuildError)
        true
    ),

    fn resetEditNormalsToSmoothingBaselineStrict n modInst =
    (
        local resetError = ""
        try
        (
            -- A newly added Edit Normals modifier can inherit Explicit /
            -- Specified state and, independently, the old normal vectors
            -- embedded in the base mesh.  Merely clearing the two state flags
            -- leaves those inherited vectors in GetNormal(), which can make a
            -- stale custom-normal field look like the SG baseline and produce
            -- a false zero-residual result.
            rebuildEditNormalsStrict n modInst "重建光滑组法线基线失败"
            local initialNormalCount = modInst.GetNumNormals node:n
            local initialFaceCount = modInst.GetNumFaces node:n
            if initialNormalCount < 1 or initialFaceCount < 1 do
                throw "Edit Normals 没有可重建的法线池或面。"

            local inheritedExplicit = 0
            local inheritedSpecified = 0
            for normalIndex = 1 to initialNormalCount where
                modInst.GetNormalExplicit normalIndex node:n do
                    inheritedExplicit += 1
            for faceIndex = 1 to initialFaceCount do
            (
                local degree = modInst.GetFaceDegree faceIndex node:n
                for cornerIndex = 1 to degree where
                    modInst.GetFaceNormalSpecified faceIndex cornerIndex node:n do
                        inheritedSpecified += 1
            )

            -- Max 2023 recipe D, verified with Skin above this stack-bottom
            -- modifier: Reset removes the inherited vector field, but its
            -- first rebuild can leave every corner ID at 0.  A second command
            -- panel activation followed by update/Rebuild restores a valid,
            -- purely SG-derived blue normal pool.
            if inheritedExplicit > 0 or inheritedSpecified > 0 then
            (
                local allNormals = #{}
                for normalIndex = 1 to initialNormalCount do
                    allNormals[normalIndex] = true
                if not (modInst.Reset selection:allNormals node:n) do
                    throw "Edit Normals Reset(all) 返回失败。"
                allNormals = undefined
                rebuildEditNormalsStrict n modInst "Reset 后第一次法线重建失败"
                update n
                if not (activateModifier n modInst) do
                    throw "Reset 后无法重新激活 Edit Normals。"
                update n
                rebuildEditNormalsStrict n modInst "Reset 后重新激活法线重建失败"
            )
            else
            (
                -- A receiver with no inherited custom-normal state is already
                -- a genuine SG baseline; Reset would be a no-op and returns
                -- false, so keep the valid rebuilt pool above.
                update n
            )

            local finalNormalCount = modInst.GetNumNormals node:n
            local finalFaceCount = modInst.GetNumFaces node:n
            if finalNormalCount < 1 or finalFaceCount != initialFaceCount do
                throw "纯光滑组法线基线的法线池或面数无效。"
            for normalIndex = 1 to finalNormalCount where
                modInst.GetNormalExplicit normalIndex node:n do
                    throw ("纯光滑组法线基线仍含 Explicit 法线 " +
                        (normalIndex as string) + "。")
            for faceIndex = 1 to finalFaceCount do
            (
                local degree = modInst.GetFaceDegree faceIndex node:n
                for cornerIndex = 1 to degree do
                (
                    local normalId =
                        modInst.GetNormalID faceIndex cornerIndex node:n
                    if normalId < 1 or normalId > finalNormalCount do
                        throw ("纯光滑组法线基线第 " +
                            (faceIndex as string) + " 面第 " +
                            (cornerIndex as string) + " 角的法线 ID 无效。")
                    if modInst.GetFaceNormalSpecified faceIndex cornerIndex node:n do
                        throw ("纯光滑组法线基线第 " +
                            (faceIndex as string) + " 面第 " +
                            (cornerIndex as string) +
                            " 角仍是 Specified。")
                )
            )
            update n
        )
        catch
        (
            resetError = getCurrentException()
        )
        if resetError != "" do
            throw ("无法建立纯光滑组法线基线：" + resetError)
        true
    ),

    fn findEditNormals n =
    (
        try
        (
            for m in n.modifiers where classof m == Edit_Normals do return m
        )
        catch()
        undefined
    ),

    fn editNormalsCustomCounts n reader =
    (
        local explicitCount = 0
        local specifiedCornerCount = 0
        try
        (
            for normalIndex = 1 to (reader.GetNumNormals node:n) where
                (reader.GetNormalExplicit normalIndex node:n) do explicitCount += 1
            for faceIndex = 1 to (reader.GetNumFaces node:n) do
            (
                local degree = reader.GetFaceDegree faceIndex node:n
                for cornerIndex = 1 to degree where
                    (reader.GetFaceNormalSpecified faceIndex cornerIndex node:n) do
                        specifiedCornerCount += 1
            )
        )
        catch()
        #(explicitCount, specifiedCornerCount)
    ),

    fn canReadExplicitNormals n =
    (
        setLastMessage ""
        local reader = undefined
        local readerIsTemp = false
        local ok = false
        local oldSelection = selection as array
        try
        (
            reader = findEditNormals n
            if reader == undefined then
            (
                reader = Edit_Normals()
                addModifier n reader
                reader.name = "F2M_检查 FBX 目标模型顶点法线"
                readerIsTemp = true
            )
            activateModifier n reader
            rebuildEditNormalsStrict n reader "检查 FBX 目标顶点法线时重建失败"
            local customCounts = editNormalsCustomCounts n reader
            ok = (reader.GetNumFaces node:n) > 0 and
                (reader.GetNumNormals node:n) > 0 and
                (customCounts[1] > 0 or customCounts[2] > 0)
            if ok then
                setLastMessage ("自定义法线可读取：面 " +
                    ((reader.GetNumFaces node:n) as string) + "，法线 " +
                    ((reader.GetNumNormals node:n) as string) + "，Explicit " +
                    (customCounts[1] as string) + "，Specified 面角 " +
                    (customCounts[2] as string) + "。")
            else
                setLastMessage "FBX 目标模型只有由光滑组计算的普通法线，没有可传递的 Specified / Explicit 自定义法线。"
        )
        catch
        (
            setLastMessage ("读取显式法线失败：" + getCurrentException())
            ok = false
        )
        if readerIsTemp and reader != undefined do
        (
            local readerHandle = undefined
            try(readerHandle = getHandleByAnim reader)catch()
            reader = undefined
            if readerHandle == undefined or
               not (F2M_Helper.removeModifierByAnimHandle n readerHandle) do
            (
                setLastMessage ("检查 FBX 目标顶点法线后无法安全删除临时 Edit Normals：" +
                    lastMessage)
                ok = false
            )
        )
        reader = undefined
        try(select oldSelection)catch()
        oldSelection = #()
        ok
    ),

    fn snapshotSmoothingInputFlat n =
    (
        setLastMessage ""
        local reader = undefined
        local readerIsTemp = false
        local result = undefined
        local oldSelection = selection as array
        try
        (
            reader = findEditNormals n
            if reader == undefined then
            (
                reader = Edit_Normals()
                addModifier n reader
                reader.name = "F2M_读取光滑法线扇区"
                readerIsTemp = true
            )
            if not (activateModifier n reader) do throw "无法激活 Edit Normals。"
            rebuildEditNormalsStrict n reader "读取光滑法线扇区时重建失败"
            local faceCount = reader.GetNumFaces node:n
            local normalCount = reader.GetNumNormals node:n
            if faceCount < 1 or normalCount < 1 do throw "Edit Normals 没有面/法线数据。"

            local faceDegrees = #()
            local vertexIds = #()
            local fanIds = #()
            local normalValues = #()
            for faceIndex = 1 to faceCount do
            (
                local degree = reader.GetFaceDegree faceIndex node:n
                if degree < 3 do throw ("第 " + (faceIndex as string) + " 面少于 3 个角。")
                append faceDegrees degree
                for cornerIndex = 1 to degree do
                (
                    local normalId = reader.GetNormalID faceIndex cornerIndex node:n
                    local normalValue = reader.GetNormal normalId node:n
                    append vertexIds (reader.GetVertexID faceIndex cornerIndex node:n)
                    append fanIds normalId
                    append normalValues normalValue.x
                    append normalValues normalValue.y
                    append normalValues normalValue.z
                )
            )
            local customCounts = editNormalsCustomCounts n reader
            result = #(
                faceDegrees,
                vertexIds,
                fanIds,
                normalValues,
                customCounts[1],
                customCounts[2]
            )
            setLastMessage ("已读取光滑求解输入：面 " + (faceCount as string) +
                "，法线扇区 " + (normalCount as string) + "，Explicit " +
                (customCounts[1] as string) + "，Specified 面角 " +
                (customCounts[2] as string) + "。")
        )
        catch
        (
            setLastMessage ("读取光滑求解输入失败：" + getCurrentException())
            result = undefined
        )
        if readerIsTemp and reader != undefined do
        (
            local readerHandle = undefined
            try(readerHandle = getHandleByAnim reader)catch()
            reader = undefined
            if readerHandle == undefined or
               not (F2M_Helper.removeModifierByAnimHandle n readerHandle) do
            (
                setLastMessage ("读取光滑求解输入后无法安全删除临时 Edit Normals：" +
                    lastMessage)
                result = undefined
            )
        )
        reader = undefined
        try(select oldSelection)catch()
        oldSelection = #()
        result
    ),

    fn removeF2MNormalModifiers n =
    (
        local removed = 0
        local m = undefined
        local modifierHandles = #()
        try
        (
            for i = n.modifiers.count to 1 by -1 do
            (
                m = n.modifiers[i]
                if classof m == Edit_Normals and matchPattern (m.name as string) pattern:"F2M_顶点法线*" ignoreCase:false do
                (
                    local modifierHandle = undefined
                    try(modifierHandle = getHandleByAnim m)catch()
                    if modifierHandle == undefined do
                        throw "旧 F2M 顶点法线修改器没有可解析的动画句柄。"
                    append modifierHandles modifierHandle
                )
                m = undefined
            )
            m = undefined
            for modifierHandle in modifierHandles do
            (
                if removed >= 0 do
                (
                    if F2M_Helper.removeModifierByAnimHandle n modifierHandle then
                        removed += 1
                    else
                    (
                        removed = -1
                        throw ("无法安全移除旧 F2M 顶点法线修改器：" + lastMessage)
                    )
                )
            )
        )
        catch
        (
            m = undefined
            setLastMessage ("清理旧 F2M 顶点法线修改器失败：" + getCurrentException())
            removed = -1
        )
        m = undefined
        modifierHandles = #()
        removed
    ),

    fn countF2MNormalModifiers n =
    (
        local count = 0
        try
        (
            for m in n.modifiers where
                classof m == Edit_Normals and
                matchPattern (m.name as string) pattern:"F2M_顶点法线*" ignoreCase:false do
                    count += 1
        )
        catch
        (
            setLastMessage ("核对旧 F2M 顶点法线修改器失败：" + getCurrentException())
            count = -1
        )
        count
    ),

    fn snapshotEditNormalsData srcNode srcMod =
    (
        try
        (
            local srcFaceCount = srcMod.GetNumFaces node:srcNode
            local srcNormalCount = srcMod.GetNumNormals node:srcNode
            local normalRows = #()
            local faceRows = #()
            for normalIndex = 1 to srcNormalCount do
            (
                append normalRows #(
                    srcMod.GetNormal normalIndex node:srcNode,
                    srcMod.GetNormalExplicit normalIndex node:srcNode,
                    srcMod.GetNormalExplicit normalIndex node:srcNode
                )
            )
            for faceIndex = 1 to srcFaceCount do
            (
                local cornerRows = #()
                local srcDegree = srcMod.GetFaceDegree faceIndex node:srcNode
                for cornerIndex = 1 to srcDegree do
                (
                    local normalId = srcMod.GetNormalID faceIndex cornerIndex node:srcNode
                    local specified = srcMod.GetFaceNormalSpecified faceIndex cornerIndex node:srcNode
                    if normalId < 1 or normalId > srcNormalCount do
                        throw ("第 " + (faceIndex as string) + " 面第 " +
                            (cornerIndex as string) + " 角的 normal ID 越界。")
                    append cornerRows #(
                        normalId,
                        specified
                    )
                    -- Only Explicit normals and normals referenced by a
                    -- Specified face corner carry authored vectors.  Max is
                    -- allowed to recompute every other normal from geometry
                    -- and smoothing groups.
                    if specified do normalRows[normalId][3] = true
                )
                append faceRows cornerRows
            )
            #(srcFaceCount, srcNormalCount, normalRows, faceRows)
        )
        catch
        (
            setLastMessage ("FBX 目标 Edit Normals 数据快照失败：" + getCurrentException())
            undefined
        )
    ),

    fn transposeLinearMatrix sourceMatrix =
    (
        matrix3 [sourceMatrix.row1.x, sourceMatrix.row2.x, sourceMatrix.row3.x] [sourceMatrix.row1.y, sourceMatrix.row2.y, sourceMatrix.row3.y] [sourceMatrix.row1.z, sourceMatrix.row2.z, sourceMatrix.row3.z] [0, 0, 0]
    ),

    fn transformEditNormalsSnapshot srcData srcNode dstNode =
    (
        try
        (
            if srcData == undefined or srcData.count != 4 do
                throw "FBX 目标 Edit Normals 快照无效。"
            local srcNormalMatrix = transposeLinearMatrix (inverse srcNode.objectTransform)
            local dstInverseNormalMatrix = transposeLinearMatrix dstNode.objectTransform
            local normalRows = #()
            for normalIndex = 1 to srcData[2] do
            (
                local transformed = srcData[3][normalIndex][1]
                local authored = srcData[3][normalIndex][3]
                if authored do
                (
                    transformed = transformed * srcNormalMatrix
                    transformed = transformed * dstInverseNormalMatrix
                    if (length transformed) <= 0.00000001 do
                        throw ("法线 " + (normalIndex as string) + " 的空间变换结果为零向量。")
                    transformed = normalize transformed
                )
                append normalRows #(
                    transformed,
                    srcData[3][normalIndex][2],
                    authored
                )
            )
            #(srcData[1], srcData[2], normalRows, srcData[4])
        )
        catch
        (
            setLastMessage ("Edit Normals 的 FBX 目标模型局部→世界→Max 源模型局部变换失败：" + getCurrentException())
            undefined
        )
    ),

    fn remapEditNormalsSnapshot srcData faceMap:#() cornerMaps:#() =
    (
        try
        (
            if srcData == undefined or srcData.count != 4 do throw "FBX 目标 Edit Normals 快照无效。"
            if faceMap == undefined or faceMap.count == 0 do return srcData
            if faceMap.count != srcData[1] or cornerMaps.count != srcData[1] do
                throw "Edit Normals 面/角映射数量与 FBX 目标面数不一致。"
            local mappedFaceRows = #()
            for targetFace = 1 to faceMap.count do
            (
                local sourceFace = mappedSourceFace faceMap targetFace
                if sourceFace < 1 or sourceFace > srcData[1] do
                    throw ("第 " + targetFace as string + " 个 Max 源面映射到越界 FBX 目标面。")
                local sourceRows = srcData[4][sourceFace]
                local cornerMap = cornerMaps[targetFace]
                if cornerMap.count != sourceRows.count do
                    throw ("第 " + targetFace as string + " 面法线角映射数量不一致。")
                local mappedRows = #()
                for targetCorner = 1 to cornerMap.count do
                (
                    local sourceCorner = cornerMap[targetCorner]
                    if sourceCorner < 1 or sourceCorner > sourceRows.count do
                        throw ("第 " + targetFace as string + " 面法线角映射越界。")
                    -- MAXScript's scene-object `copy` command returns OK for
                    -- these nested Array values instead of an Array clone.
                    -- Rebuild the two-field row explicitly so the mapped
                    -- normal ID / Specified flag survive into writeback.
                    append mappedRows #(
                        sourceRows[sourceCorner][1],
                        sourceRows[sourceCorner][2]
                    )
                )
                append mappedFaceRows mappedRows
            )
            #(srcData[1], srcData[2], srcData[3], mappedFaceRows)
        )
        catch
        (
            setLastMessage ("Edit Normals 面角映射失败：" + getCurrentException())
            undefined
        )
    ),

    fn editNormalsSnapshotMatches srcData dstNode dstMod tolerance:0.00001 =
    (
        try
        (
            if srcData == undefined or srcData.count != 4 do
            (
                setLastMessage "FBX 目标 Edit Normals 快照无效。"
                return false
            )
            local srcFaceCount = srcData[1]
            local srcNormalCount = srcData[2]
            local dstFaceCount = dstMod.GetNumFaces node:dstNode
            local dstNormalCount = dstMod.GetNumNormals node:dstNode
            if srcFaceCount != dstFaceCount or srcNormalCount != dstNormalCount do
            (
                setLastMessage ("Edit Normals 读回数量不一致：面 " +
                    (srcFaceCount as string) + "/" + (dstFaceCount as string) +
                    "，法线 " + (srcNormalCount as string) + "/" + (dstNormalCount as string) + "。")
                return false
            )

            for normalIndex = 1 to srcNormalCount do
            (
                if srcData[3][normalIndex][3] do
                (
                    local srcNormal = srcData[3][normalIndex][1]
                    local dstNormal = dstMod.GetNormal normalIndex node:dstNode
                    if (distance srcNormal dstNormal) > tolerance do
                    (
                        setLastMessage ("Edit Normals 自定义法线向量读回不一致，索引 " + (normalIndex as string) + "。")
                        return false
                    )
                )
                if srcData[3][normalIndex][2] !=
                   (dstMod.GetNormalExplicit normalIndex node:dstNode) do
                (
                    setLastMessage ("Edit Normals Explicit 状态读回不一致，索引 " + (normalIndex as string) + "。")
                    return false
                )
            )

            for faceIndex = 1 to srcFaceCount do
            (
                local srcDegree = srcData[4][faceIndex].count
                local dstDegree = dstMod.GetFaceDegree faceIndex node:dstNode
                if srcDegree != dstDegree do
                (
                    setLastMessage ("Edit Normals 面角数量读回不一致，面 " + (faceIndex as string) + "。")
                    return false
                )
                for cornerIndex = 1 to srcDegree do
                (
                    if srcData[4][faceIndex][cornerIndex][1] !=
                       (dstMod.GetNormalID faceIndex cornerIndex node:dstNode) do
                    (
                        setLastMessage ("Edit Normals 面角法线 ID 读回不一致，面/角 " +
                            (faceIndex as string) + "/" + (cornerIndex as string) + "。")
                        return false
                    )
                    if srcData[4][faceIndex][cornerIndex][2] !=
                       (dstMod.GetFaceNormalSpecified faceIndex cornerIndex node:dstNode) do
                    (
                        setLastMessage ("Edit Normals Specified 状态读回不一致，面/角 " +
                            (faceIndex as string) + "/" + (cornerIndex as string) + "。")
                        return false
                    )
                )
            )
            true
        )
        catch
        (
            setLastMessage ("Edit Normals 完整读回验证失败：" + getCurrentException())
            false
        )
    ),

    fn editNormalsSnapshotEquivalent srcData dstNode dstMod tolerance:0.00001 =
    (
        -- A newly evaluated Edit Normals modifier is allowed to renumber its
        -- normal pool according to the Max source face order.  Verify a
        -- one-to-one normal-fan mapping and all authored corner semantics
        -- instead of requiring the FBX target's numeric normal IDs to survive
        -- a legitimate face reorder.
        try
        (
            if srcData == undefined or srcData.count != 4 do
            (
                setLastMessage "FBX 目标 Edit Normals 快照无效。"
                return false
            )
            local srcFaceCount = srcData[1]
            local srcNormalCount = srcData[2]
            local dstFaceCount = dstMod.GetNumFaces node:dstNode
            local dstNormalCount = dstMod.GetNumNormals node:dstNode
            if srcFaceCount != dstFaceCount or srcNormalCount != dstNormalCount do
            (
                setLastMessage ("Edit Normals 最终评估数量不一致：面 " +
                    (srcFaceCount as string) + "/" + (dstFaceCount as string) +
                    "，法线 " + (srcNormalCount as string) + "/" +
                    (dstNormalCount as string) + "。")
                return false
            )

            local expectedToActual = for i = 1 to srcNormalCount collect 0
            local actualToExpected = for i = 1 to dstNormalCount collect 0
            for faceIndex = 1 to srcFaceCount do
            (
                local srcDegree = srcData[4][faceIndex].count
                local dstDegree = dstMod.GetFaceDegree faceIndex node:dstNode
                if srcDegree != dstDegree do
                (
                    setLastMessage ("Edit Normals 最终评估面角数量不一致，面 " +
                        (faceIndex as string) + "。")
                    return false
                )
                for cornerIndex = 1 to srcDegree do
                (
                    local expectedId = srcData[4][faceIndex][cornerIndex][1]
                    local actualId = dstMod.GetNormalID faceIndex cornerIndex node:dstNode
                    if expectedId < 1 or expectedId > srcNormalCount or
                       actualId < 1 or actualId > dstNormalCount do
                    (
                        setLastMessage ("Edit Normals 最终评估 normal ID 越界，面/角 " +
                            (faceIndex as string) + "/" +
                            (cornerIndex as string) + "。")
                        return false
                    )
                    if expectedToActual[expectedId] == 0 then
                        expectedToActual[expectedId] = actualId
                    else if expectedToActual[expectedId] != actualId do
                    (
                        setLastMessage ("Edit Normals 最终评估拆分了原法线扇区，面/角 " +
                            (faceIndex as string) + "/" +
                            (cornerIndex as string) + "。")
                        return false
                    )
                    if actualToExpected[actualId] == 0 then
                        actualToExpected[actualId] = expectedId
                    else if actualToExpected[actualId] != expectedId do
                    (
                        setLastMessage ("Edit Normals 最终评估合并了不同法线扇区，面/角 " +
                            (faceIndex as string) + "/" +
                            (cornerIndex as string) + "。")
                        return false
                    )

                    local expectedSpecified =
                        srcData[4][faceIndex][cornerIndex][2]
                    if expectedSpecified !=
                       (dstMod.GetFaceNormalSpecified faceIndex cornerIndex node:dstNode) do
                    (
                        setLastMessage ("Edit Normals 最终评估 Specified 状态不一致，面/角 " +
                            (faceIndex as string) + "/" +
                            (cornerIndex as string) + "。")
                        return false
                    )
                )
            )

            for expectedId = 1 to srcNormalCount do
            (
                local actualId = expectedToActual[expectedId]
                if actualId == 0 do
                (
                    setLastMessage ("Edit Normals 最终评估丢失法线扇区，索引 " +
                        (expectedId as string) + "。")
                    return false
                )
                if srcData[3][expectedId][2] !=
                   (dstMod.GetNormalExplicit actualId node:dstNode) do
                (
                    setLastMessage ("Edit Normals 最终评估 Explicit 状态不一致，索引 " +
                        (expectedId as string) + "。")
                    return false
                )
                if srcData[3][expectedId][3] do
                (
                    local expectedNormal = srcData[3][expectedId][1]
                    local actualNormal = dstMod.GetNormal actualId node:dstNode
                    if (distance expectedNormal actualNormal) > tolerance do
                    (
                        setLastMessage ("Edit Normals 最终评估自定义向量不一致，索引 " +
                            (expectedId as string) + "。")
                        return false
                    )
                )
            )
            true
        )
        catch
        (
            setLastMessage ("Edit Normals 最终评估等价验证失败：" +
                getCurrentException())
            false
        )
    ),

    fn evaluatedEditNormalsMatch srcData dstNode tolerance:0.00001 =
    (
        local verifier = undefined
        local ok = false
        local verifyMessage = ""
        local oldSelection = selection as array
        try
        (
            verifier = Edit_Normals()
            verifier.name = "F2M_最终评估法线验证"
            addModifier dstNode verifier
            if not (activateModifier dstNode verifier) do
                throw "无法激活最终评估验证修改器。"
            rebuildEditNormalsStrict dstNode verifier "最终评估法线验证重建失败"
            ok = editNormalsSnapshotEquivalent srcData dstNode verifier tolerance:tolerance
            if not ok do verifyMessage = lastMessage
        )
        catch
        (
            verifyMessage = getCurrentException()
            ok = false
        )
        if verifier != undefined do
        (
            local verifierHandle = undefined
            try(verifierHandle = getHandleByAnim verifier)catch()
            verifier = undefined
            if verifierHandle == undefined or
               not (F2M_Helper.removeModifierByAnimHandle dstNode verifierHandle) do
            (
                verifyMessage = "最终评估验证后无法安全删除临时 Edit Normals：" +
                    lastMessage
                ok = false
            )
        )
        verifier = undefined
        try(select oldSelection)catch()
        oldSelection = #()
        if not ok do setLastMessage ("最终评估法线不一致：" + verifyMessage)
        ok
    ),

    fn applyEditNormalsSnapshot srcData dstNode dstMod =
    (
        try
        (
            if srcData == undefined or srcData.count != 4 do throw "FBX 目标 Edit Normals 快照无效。"
            if (dstMod.GetNumFaces node:dstNode) != srcData[1] or
               (dstMod.GetNumNormals node:dstNode) != srcData[2] do
                throw "Max 源 Edit Normals 的面/法线数量与 FBX 目标快照不一致。"

            -- addModifierWithLocalData 建立相同的 normal pool 后，再显式写一遍
            -- ID、状态和向量，避免后续管线重新求值时把局部显式状态降回计算法线。
            for faceIndex = 1 to srcData[1] do
            (
                local cornerRows = srcData[4][faceIndex]
                if (dstMod.GetFaceDegree faceIndex node:dstNode) != cornerRows.count do
                    throw ("Max 源 Edit Normals 面角数量不一致，面 " + (faceIndex as string) + "。")
                for cornerIndex = 1 to cornerRows.count do
                (
                    dstMod.SetNormalID faceIndex cornerIndex cornerRows[cornerIndex][1] node:dstNode
                    dstMod.SetFaceNormalSpecified faceIndex cornerIndex specified:cornerRows[cornerIndex][2] node:dstNode
                )
            )
            local explicitNormals = #{}
            for normalIndex = 1 to srcData[2] do
            (
                -- Start from a deterministic non-explicit state.  Autodesk's
                -- MakeExplicit operation is used below for the persistent state;
                -- SetNormalExplicit alone can appear correct until the modifier is
                -- evaluated again.
                dstMod.SetNormalExplicit normalIndex explicit:false node:dstNode
                if srcData[3][normalIndex][2] do explicitNormals[normalIndex] = true
            )
            if explicitNormals.numberSet > 0 do
            (
                if not (dstMod.MakeExplicit selection:explicitNormals node:dstNode) do
                    throw "Edit Normals MakeExplicit 返回失败。"
            )
            -- MakeExplicit freezes the currently computed values, so restore the
            -- exact source vectors after the persistent explicit state exists.
            for normalIndex = 1 to srcData[2] do
            (
                if srcData[3][normalIndex][3] do
                (
                    local normalValue = srcData[3][normalIndex][1]
                    dstMod.SetNormal normalIndex &normalValue node:dstNode
                )
            )
            update dstNode
            true
        )
        catch
        (
            setLastMessage ("Edit Normals 快照写入失败：" + getCurrentException())
            false
        )
    ),

    -- Production Edit Normals snapshots deliberately use a flat, fixed-size
    -- container layout:
    -- #(
    --   faceCount, normalCount,
    --   normalXYZFloats, explicitNormalBits, authoredNormalBits,
    --   faceCornerStarts, cornerNormalIds, specifiedCornerBits
    -- )
    --
    -- The legacy snapshotEditNormalsData function above remains available for
    -- old diagnostic scripts.  It is not used by either production transfer
    -- path.  On real FBX assets its nested normal/face/corner rows retained
    -- tens of thousands of Array and Point3 values at once, which could leave
    -- Max's MAXScript heap in a bad state when imported nodes were deleted.
    fn isFlatEditNormalsSnapshot data =
    (
        data != undefined and data.count == 8
    ),

    fn flatEditNormalVector data normalIndex =
    (
        local valueOffset = ((normalIndex - 1) * 3) + 1
        [data[3][valueOffset], data[3][valueOffset + 1], data[3][valueOffset + 2]]
    ),

    fn snapshotEditNormalsDataFlat srcNode srcMod =
    (
        try
        (
            local srcFaceCount = srcMod.GetNumFaces node:srcNode
            local srcNormalCount = srcMod.GetNumNormals node:srcNode
            if srcFaceCount < 1 or srcNormalCount < 1 do
                throw "Edit Normals 没有面/法线数据。"

            local normalValues = #()
            local explicitNormals = #{}
            local authoredNormals = #{}
            local faceCornerStarts = #(1)
            local cornerNormalIds = #()
            local specifiedCorners = #{}

            for normalIndex = 1 to srcNormalCount do
            (
                local normalValue = srcMod.GetNormal normalIndex node:srcNode
                append normalValues normalValue.x
                append normalValues normalValue.y
                append normalValues normalValue.z
                if srcMod.GetNormalExplicit normalIndex node:srcNode do
                (
                    explicitNormals[normalIndex] = true
                    authoredNormals[normalIndex] = true
                )
                normalValue = undefined
            )

            for faceIndex = 1 to srcFaceCount do
            (
                local srcDegree = srcMod.GetFaceDegree faceIndex node:srcNode
                if srcDegree < 1 do
                    throw ("第 " + (faceIndex as string) + " 面没有法线角。")
                for cornerIndex = 1 to srcDegree do
                (
                    local normalId = srcMod.GetNormalID faceIndex cornerIndex node:srcNode
                    if normalId < 1 or normalId > srcNormalCount do
                        throw ("第 " + (faceIndex as string) + " 面第 " +
                            (cornerIndex as string) + " 角的 normal ID 越界。")
                    append cornerNormalIds normalId
                    if srcMod.GetFaceNormalSpecified faceIndex cornerIndex node:srcNode do
                    (
                        local flatCornerIndex = cornerNormalIds.count
                        specifiedCorners[flatCornerIndex] = true
                        authoredNormals[normalId] = true
                    )
                )
                append faceCornerStarts (cornerNormalIds.count + 1)
            )

            #(
                srcFaceCount,
                srcNormalCount,
                normalValues,
                explicitNormals,
                authoredNormals,
                faceCornerStarts,
                cornerNormalIds,
                specifiedCorners
            )
        )
        catch
        (
            setLastMessage ("FBX 目标 Edit Normals 扁平快照失败：" +
                getCurrentException())
            undefined
        )
    ),

    fn transformEditNormalsSnapshotFlat srcData srcNode dstNode includeAllReferenced:false =
    (
        try
        (
            if not (isFlatEditNormalsSnapshot srcData) do
                throw "FBX 目标 Edit Normals 扁平快照无效。"
            local srcNormalMatrix = transposeLinearMatrix (inverse srcNode.objectTransform)
            local dstInverseNormalMatrix = transposeLinearMatrix dstNode.objectTransform
            local normalsToTransform = copy srcData[5]
            if includeAllReferenced do
            (
                for flatCornerIndex = 1 to srcData[7].count do
                (
                    local referencedNormalId = srcData[7][flatCornerIndex]
                    if referencedNormalId < 1 or
                       referencedNormalId > srcData[2] do
                        throw ("第 " + (flatCornerIndex as string) +
                            " 个面角引用了越界法线 ID。")
                    normalsToTransform[referencedNormalId] = true
                )
            )
            for normalIndex = 1 to srcData[2] where
                normalsToTransform[normalIndex] do
            (
                local transformed = flatEditNormalVector srcData normalIndex
                transformed = transformed * srcNormalMatrix
                transformed = transformed * dstInverseNormalMatrix
                if (length transformed) <= 0.00000001 do
                    throw ("法线 " + (normalIndex as string) +
                        " 的空间变换结果为零向量。")
                transformed = normalize transformed
                local valueOffset = ((normalIndex - 1) * 3) + 1
                srcData[3][valueOffset] = transformed.x
                srcData[3][valueOffset + 1] = transformed.y
                srcData[3][valueOffset + 2] = transformed.z
                transformed = undefined
            )
            normalsToTransform = undefined
            srcNormalMatrix = undefined
            dstInverseNormalMatrix = undefined
            srcData
        )
        catch
        (
            setLastMessage ("Edit Normals 扁平快照的 FBX 目标模型局部→世界→" +
                "Max 源模型局部变换失败：" + getCurrentException())
            undefined
        )
    ),

    fn remapEditNormalsSnapshotFlat srcData faceMap:#() cornerMaps:#() cornerMapStarts:#() cornerMapFlat:#() =
    (
        try
        (
            if not (isFlatEditNormalsSnapshot srcData) do
                throw "FBX 目标 Edit Normals 扁平快照无效。"
            if faceMap == undefined or faceMap.count == 0 do return srcData
            if faceMap.count != srcData[1] do
                throw "Edit Normals 面映射数量与 FBX 目标面数不一致。"

            local useFlatCornerMap =
                cornerMapStarts != undefined and cornerMapFlat != undefined and
                cornerMapStarts.count == (srcData[1] + 1)
            if not useFlatCornerMap and
               (cornerMaps == undefined or cornerMaps.count != srcData[1]) do
                throw "Edit Normals 面角映射数量与 FBX 目标面数不一致。"

            local mappedFaceStarts = #(1)
            local mappedNormalIds = #()
            local mappedSpecified = #{}
            for targetFace = 1 to faceMap.count do
            (
                local sourceFace = mappedSourceFace faceMap targetFace
                if sourceFace < 1 or sourceFace > srcData[1] do
                    throw ("第 " + (targetFace as string) +
                        " 个 Max 源面映射到越界 FBX 目标面。")
                local sourceStart = srcData[6][sourceFace]
                local sourceDegree =
                    srcData[6][sourceFace + 1] - sourceStart
                local mappedDegree = 0
                local mappedStart = 0
                if useFlatCornerMap then
                (
                    mappedStart = cornerMapStarts[targetFace]
                    mappedDegree =
                        cornerMapStarts[targetFace + 1] - mappedStart
                )
                else
                    mappedDegree = cornerMaps[targetFace].count
                if mappedDegree != sourceDegree do
                    throw ("第 " + (targetFace as string) +
                        " 面法线角映射数量不一致。")

                for targetCorner = 1 to mappedDegree do
                (
                    local sourceCorner = if useFlatCornerMap then
                        cornerMapFlat[mappedStart + targetCorner - 1]
                    else
                        cornerMaps[targetFace][targetCorner]
                    if sourceCorner < 1 or sourceCorner > sourceDegree do
                        throw ("第 " + (targetFace as string) +
                            " 面法线角映射越界。")
                    local sourceFlatCorner =
                        sourceStart + sourceCorner - 1
                    append mappedNormalIds srcData[7][sourceFlatCorner]
                    if srcData[8][sourceFlatCorner] do
                        mappedSpecified[mappedNormalIds.count] = true
                )
                append mappedFaceStarts (mappedNormalIds.count + 1)
            )
            srcData[6] = mappedFaceStarts
            srcData[7] = mappedNormalIds
            srcData[8] = mappedSpecified
            srcData
        )
        catch
        (
            setLastMessage ("Edit Normals 扁平面角映射失败：" +
                getCurrentException())
            undefined
        )
    ),

    fn normalAngleDegrees firstNormal secondNormal =
    (
        local firstLength = length firstNormal
        local secondLength = length secondNormal
        if firstLength <= 0.00000001 or secondLength <= 0.00000001 then
            180.0
        else
        (
            local cosineValue = dot (firstNormal / firstLength) (secondNormal / secondLength)
            if cosineValue > 1.0 do cosineValue = 1.0
            if cosineValue < -1.0 do cosineValue = -1.0
            acos cosineValue
        )
    ),

    fn buildExternalSmoothingBaselineFlat faceDegrees fanIds cornerNormalValues =
    (
        try
        (
            if faceDegrees == undefined or fanIds == undefined or
               cornerNormalValues == undefined or faceDegrees.count < 1 do
                throw "外部纯 SG 法线基线为空。"
            local cornerCount = 0
            for faceIndex = 1 to faceDegrees.count do
            (
                local degree = faceDegrees[faceIndex] as integer
                if degree < 3 do
                    throw ("外部纯 SG 法线基线第 " +
                        (faceIndex as string) + " 面少于 3 个角。")
                cornerCount += degree
            )
            if fanIds.count != cornerCount or
               cornerNormalValues.count != (cornerCount * 3) do
                throw "外部纯 SG 法线基线的面角、扇区和方向数量不一致。"

            local normalCount = 0
            for fanId in fanIds do
            (
                local value = fanId as integer
                if value < 1 do throw "外部纯 SG 法线基线含无效扇区 ID。"
                if value > normalCount do normalCount = value
            )
            if normalCount < 1 do throw "外部纯 SG 法线基线没有法线扇区。"

            local normalValues = for valueIndex = 1 to (normalCount * 3) collect 0.0
            local seenNormals = #{}
            local faceStarts = #(1)
            local flatCorner = 1
            for faceIndex = 1 to faceDegrees.count do
            (
                local degree = faceDegrees[faceIndex] as integer
                for cornerIndex = 1 to degree do
                (
                    local fanId = fanIds[flatCorner] as integer
                    local inputOffset = ((flatCorner - 1) * 3) + 1
                    local inputNormal = [cornerNormalValues[inputOffset], cornerNormalValues[inputOffset + 1], cornerNormalValues[inputOffset + 2]]
                    if (length inputNormal) <= 0.00000001 do
                        throw ("外部纯 SG 法线基线第 " +
                            (faceIndex as string) + " 面第 " +
                            (cornerIndex as string) + " 角为零向量。")
                    inputNormal = normalize inputNormal
                    local outputOffset = ((fanId - 1) * 3) + 1
                    if seenNormals[fanId] then
                    (
                        local existingNormal = [normalValues[outputOffset], normalValues[outputOffset + 1], normalValues[outputOffset + 2]]
                        if normalAngleDegrees existingNormal inputNormal > 0.001 do
                            throw ("外部纯 SG 法线基线扇区 " +
                                (fanId as string) + " 含不一致方向。")
                        existingNormal = undefined
                    )
                    else
                    (
                        normalValues[outputOffset] = inputNormal.x
                        normalValues[outputOffset + 1] = inputNormal.y
                        normalValues[outputOffset + 2] = inputNormal.z
                        seenNormals[fanId] = true
                    )
                    inputNormal = undefined
                    flatCorner += 1
                )
                append faceStarts flatCorner
            )
            seenNormals = undefined
            #(
                faceDegrees.count,
                normalCount,
                normalValues,
                #{},
                #{},
                faceStarts,
                (for fanId in fanIds collect (fanId as integer)),
                #{}
            )
        )
        catch
        (
            setLastMessage ("构建外部纯 SG 法线基线失败：" +
                getCurrentException())
            undefined
        )
    ),

    fn editNormalsSnapshotFlatMatches srcData dstNode dstMod tolerance:0.00001 =
    (
        try
        (
            if not (isFlatEditNormalsSnapshot srcData) do
                throw "FBX 目标 Edit Normals 扁平快照无效。"
            local srcFaceCount = srcData[1]
            local srcNormalCount = srcData[2]
            local dstFaceCount = dstMod.GetNumFaces node:dstNode
            local dstNormalCount = dstMod.GetNumNormals node:dstNode
            if srcFaceCount != dstFaceCount or srcNormalCount != dstNormalCount do
                throw ("Edit Normals 读回数量不一致：面 " +
                    (srcFaceCount as string) + "/" +
                    (dstFaceCount as string) + "，法线 " +
                    (srcNormalCount as string) + "/" +
                    (dstNormalCount as string) + "。")

            for normalIndex = 1 to srcNormalCount do
            (
                if srcData[5][normalIndex] do
                (
                    local expectedNormal = flatEditNormalVector srcData normalIndex
                    local actualNormal = dstMod.GetNormal normalIndex node:dstNode
                    local vectorMatches =
                        (distance expectedNormal actualNormal) <= tolerance
                    expectedNormal = undefined
                    actualNormal = undefined
                    if not vectorMatches do
                        throw ("Edit Normals 自定义法线向量读回不一致，索引 " +
                            (normalIndex as string) + "。")
                )
                if srcData[4][normalIndex] !=
                   (dstMod.GetNormalExplicit normalIndex node:dstNode) do
                    throw ("Edit Normals Explicit 状态读回不一致，索引 " +
                        (normalIndex as string) + "。")
            )

            for faceIndex = 1 to srcFaceCount do
            (
                local sourceStart = srcData[6][faceIndex]
                local sourceDegree =
                    srcData[6][faceIndex + 1] - sourceStart
                if (dstMod.GetFaceDegree faceIndex node:dstNode) !=
                   sourceDegree do
                    throw ("Edit Normals 面角数量读回不一致，面 " +
                        (faceIndex as string) + "。")
                for cornerIndex = 1 to sourceDegree do
                (
                    local flatCornerIndex =
                        sourceStart + cornerIndex - 1
                    if srcData[7][flatCornerIndex] !=
                       (dstMod.GetNormalID faceIndex cornerIndex node:dstNode) do
                        throw ("Edit Normals 面角法线 ID 读回不一致，面/角 " +
                            (faceIndex as string) + "/" +
                            (cornerIndex as string) + "。")
                    if srcData[8][flatCornerIndex] !=
                       (dstMod.GetFaceNormalSpecified faceIndex cornerIndex node:dstNode) do
                        throw ("Edit Normals Specified 状态读回不一致，面/角 " +
                            (faceIndex as string) + "/" +
                            (cornerIndex as string) + "。")
                )
            )
            true
        )
        catch
        (
            setLastMessage ("Edit Normals 扁平快照完整读回验证失败：" +
                getCurrentException())
            false
        )
    ),

    fn applyEditNormalsSnapshotFlat srcData dstNode dstMod =
    (
        try
        (
            if not (isFlatEditNormalsSnapshot srcData) do
                throw "FBX 目标 Edit Normals 扁平快照无效。"
            if (dstMod.GetNumFaces node:dstNode) != srcData[1] or
               (dstMod.GetNumNormals node:dstNode) != srcData[2] do
                throw "Max 源 Edit Normals 的面/法线数量与 FBX 目标快照不一致。"

            for faceIndex = 1 to srcData[1] do
            (
                local sourceStart = srcData[6][faceIndex]
                local sourceDegree =
                    srcData[6][faceIndex + 1] - sourceStart
                if (dstMod.GetFaceDegree faceIndex node:dstNode) !=
                   sourceDegree do
                    throw ("Max 源 Edit Normals 面角数量不一致，面 " +
                        (faceIndex as string) + "。")
                for cornerIndex = 1 to sourceDegree do
                (
                    local flatCornerIndex =
                        sourceStart + cornerIndex - 1
                    dstMod.SetNormalID faceIndex cornerIndex (srcData[7][flatCornerIndex]) node:dstNode
                    dstMod.SetFaceNormalSpecified faceIndex cornerIndex specified:(srcData[8][flatCornerIndex]) node:dstNode
                )
            )

            local explicitNormals = #{}
            for normalIndex = 1 to srcData[2] do
            (
                dstMod.SetNormalExplicit normalIndex explicit:false node:dstNode
                if srcData[4][normalIndex] do
                    explicitNormals[normalIndex] = true
            )
            if explicitNormals.numberSet > 0 do
            (
                if not (dstMod.MakeExplicit selection:explicitNormals node:dstNode) do
                    throw "Edit Normals MakeExplicit 返回失败。"
            )
            -- Max 2023 may promote another normal record in the same smooth
            -- fan when MakeExplicit evaluates a partially explicit selection.
            -- The source snapshot remains authoritative: clear every record
            -- that it says is non-Explicit once more after MakeExplicit.
            -- This matters especially to the hybrid path, whose next step
            -- keeps only semantic residuals plus the minimum SG-fan guard
            -- closure.
            for normalIndex = 1 to srcData[2] where
                not srcData[4][normalIndex] do
                    dstMod.SetNormalExplicit normalIndex explicit:false node:dstNode
            for normalIndex = 1 to srcData[2] where
                srcData[5][normalIndex] do
            (
                local normalValue = flatEditNormalVector srcData normalIndex
                dstMod.SetNormal normalIndex &normalValue node:dstNode
                normalValue = undefined
            )
            -- MakeExplicit can also mark other corners in the same smooth fan
            -- as Specified.  Replay every per-corner state after all
            -- normal-record operations; the flat source snapshot, not Max's
            -- transient fan promotion, is authoritative.
            for faceIndex = 1 to srcData[1] do
            (
                local sourceStart = srcData[6][faceIndex]
                local sourceDegree =
                    srcData[6][faceIndex + 1] - sourceStart
                for cornerIndex = 1 to sourceDegree do
                (
                    local flatCornerIndex =
                        sourceStart + cornerIndex - 1
                    dstMod.SetFaceNormalSpecified faceIndex cornerIndex specified:(srcData[8][flatCornerIndex]) node:dstNode
                )
            )
            explicitNormals = undefined
            update dstNode
            true
        )
        catch
        (
            setLastMessage ("Edit Normals 扁平快照写入失败：" +
                getCurrentException())
            false
        )
    ),

    fn applyEditNormalsSnapshotFlatDifferential srcData dstNode dstMod tolerance:0.00001 =
    (
        try
        (
            if not (isFlatEditNormalsSnapshot srcData) do
                throw "FBX 目标 Edit Normals 扁平快照无效。"
            if (dstMod.GetNumFaces node:dstNode) != srcData[1] or
               (dstMod.GetNumNormals node:dstNode) != srcData[2] do
                throw "Max 源 Edit Normals 的面/法线数量与 FBX 目标快照不一致。"

            local changedIds = 0
            local changedExplicit = 0
            local changedVectors = 0
            local changedSpecified = 0
            for faceIndex = 1 to srcData[1] do
            (
                local sourceStart = srcData[6][faceIndex]
                local sourceDegree =
                    srcData[6][faceIndex + 1] - sourceStart
                if (dstMod.GetFaceDegree faceIndex node:dstNode) !=
                   sourceDegree do
                    throw ("Max 源 Edit Normals 面角数量不一致，面 " +
                        (faceIndex as string) + "。")
                for cornerIndex = 1 to sourceDegree do
                (
                    local flatCornerIndex =
                        sourceStart + cornerIndex - 1
                    local expectedId = srcData[7][flatCornerIndex]
                    local actualId =
                        dstMod.GetNormalID faceIndex cornerIndex node:dstNode
                    if actualId != expectedId do
                    (
                        dstMod.SetNormalID faceIndex cornerIndex expectedId node:dstNode
                        changedIds += 1
                    )
                )
            )

            -- addModifierWithLocalData normally gives the destination exactly
            -- these record flags.  Only touch a record if mapping/evaluation
            -- actually changed it; MakeExplicit on a huge selection can
            -- promote unrelated Max 2023 normal records.
            for normalIndex = 1 to srcData[2] do
            (
                local expectedExplicit = srcData[4][normalIndex]
                local actualExplicit =
                    dstMod.GetNormalExplicit normalIndex node:dstNode
                if expectedExplicit != actualExplicit do
                (
                    dstMod.SetNormalExplicit normalIndex explicit:expectedExplicit node:dstNode
                    changedExplicit += 1
                )
                if srcData[5][normalIndex] do
                (
                    local expectedNormal =
                        flatEditNormalVector srcData normalIndex
                    local actualNormal =
                        dstMod.GetNormal normalIndex node:dstNode
                    local vectorChanged =
                        (distance expectedNormal actualNormal) > tolerance
                    actualNormal = undefined
                    if vectorChanged do
                    (
                        dstMod.SetNormal normalIndex &expectedNormal node:dstNode
                        changedVectors += 1
                    )
                    expectedNormal = undefined
                )
            )

            -- Normal-record changes may promote face corners.  Replay only
            -- states that differ from the authoritative exact snapshot.
            for faceIndex = 1 to srcData[1] do
            (
                local sourceStart = srcData[6][faceIndex]
                local sourceDegree =
                    srcData[6][faceIndex + 1] - sourceStart
                for cornerIndex = 1 to sourceDegree do
                (
                    local flatCornerIndex =
                        sourceStart + cornerIndex - 1
                    local expectedSpecified =
                        srcData[8][flatCornerIndex]
                    local actualSpecified =
                        dstMod.GetFaceNormalSpecified faceIndex cornerIndex node:dstNode
                    if expectedSpecified != actualSpecified do
                    (
                        dstMod.SetFaceNormalSpecified faceIndex cornerIndex specified:expectedSpecified node:dstNode
                        changedSpecified += 1
                    )
                )
            )
            update dstNode
            setLastMessage ("Edit Normals 差异写入：ID " +
                (changedIds as string) + "，Explicit " +
                (changedExplicit as string) + "，向量 " +
                (changedVectors as string) + "，Specified 面角 " +
                (changedSpecified as string) + "。")
            true
        )
        catch
        (
            setLastMessage ("Edit Normals 扁平快照差异写入失败：" +
                getCurrentException())
            false
        )
    ),

    fn blockingNormalModifierNames n =
    (
        local out = #()
        try
        (
            for m in n.modifiers do
            (
                local modifierName = try(m.name as string)catch("")
                local className = try((classof m) as string)catch("")
                local isF2M = classof m == Edit_Normals and
                    matchPattern modifierName pattern:"F2M_顶点法线*" ignoreCase:false
                local changesNormals =
                    classof m == Edit_Normals or
                    matchPattern className pattern:"*Weighted*Normal*" ignoreCase:true or
                    className == "Normal" or className == "Normal_Modifier"
                if changesNormals and not isF2M do
                    append out (modifierName + " [" + className + "]")
            )
        )
        catch()
        out
    ),

    fn buildEditNormalResidualSnapshot srcData baselineData angleToleranceDegrees:0.1 =
    (
        try
        (
            if srcData == undefined or srcData.count != 4 or
               baselineData == undefined or baselineData.count != 4 do
                throw "法线残差快照无效。"
            if srcData[1] != baselineData[1] do
                throw "FBX 精确法线与光滑组基线面数不一致。"
            if angleToleranceDegrees < 0.0 or angleToleranceDegrees > 180.0 do
                throw "法线残差角度阈值超出 0–180°。"

            local residualNormalIds = #{}
            local originalSpecifiedCorners = 0
            local maxIgnoredAngle = 0.0
            local maxAngle = 0.0

            for faceIndex = 1 to srcData[1] do
            (
                local srcCorners = srcData[4][faceIndex]
                local baselineCorners = baselineData[4][faceIndex]
                if srcCorners.count != baselineCorners.count do
                    throw ("第 " + (faceIndex as string) + " 面的精确法线与光滑组基线角数不一致。")
                for cornerIndex = 1 to srcCorners.count do
                (
                    local srcNormalId = srcCorners[cornerIndex][1]
                    local baselineNormalId = baselineCorners[cornerIndex][1]
                    if srcNormalId < 1 or srcNormalId > srcData[2] or
                       baselineNormalId < 1 or baselineNormalId > baselineData[2] do
                        throw ("第 " + (faceIndex as string) + " 面第 " +
                            (cornerIndex as string) + " 角的法线 ID 越界。")
                    local authored = srcCorners[cornerIndex][2] or
                        srcData[3][srcNormalId][2] or srcData[3][srcNormalId][3]
                    if srcCorners[cornerIndex][2] do originalSpecifiedCorners += 1
                    if authored do
                    (
                        local angleValue = normalAngleDegrees srcData[3][srcNormalId][1] baselineData[3][baselineNormalId][1]
                        if angleValue > maxAngle do maxAngle = angleValue
                        if angleValue > angleToleranceDegrees then
                            residualNormalIds[srcNormalId] = true
                        else if angleValue > maxIgnoredAngle do
                            maxIgnoredAngle = angleValue
                    )
                )
            )

            local normalRows = #()
            for normalIndex = 1 to srcData[2] do
            (
                local keepResidual = residualNormalIds[normalIndex]
                append normalRows #(
                    srcData[3][normalIndex][1],
                    keepResidual,
                    keepResidual
                )
            )
            local faceRows = #()
            local residualCornerCount = 0
            for faceIndex = 1 to srcData[1] do
            (
                local cornerRows = #()
                for cornerIndex = 1 to srcData[4][faceIndex].count do
                (
                    local normalId = srcData[4][faceIndex][cornerIndex][1]
                    local keepResidual = residualNormalIds[normalId]
                    if keepResidual do residualCornerCount += 1
                    append cornerRows #(normalId, keepResidual)
                )
                append faceRows cornerRows
            )
            local residualData = #(srcData[1], srcData[2], normalRows, faceRows)
            #(
                residualData,
                residualNormalIds.numberSet,
                residualCornerCount,
                originalSpecifiedCorners,
                maxIgnoredAngle,
                maxAngle
            )
        )
        catch
        (
            setLastMessage ("光滑组/自定义法线残差分类失败：" + getCurrentException())
            undefined
        )
    ),

    fn editNormalResidualsMatch srcData dstNode dstMod tolerance:0.00001 =
    (
        try
        (
            if srcData == undefined or srcData.count != 4 do
                throw "自定义法线残差快照无效。"
            if (dstMod.GetNumFaces node:dstNode) != srcData[1] do
                throw "自定义法线残差读回面数不一致。"
            local dstNormalCount = dstMod.GetNumNormals node:dstNode
            for faceIndex = 1 to srcData[1] do
            (
                local expectedCorners = srcData[4][faceIndex]
                if (dstMod.GetFaceDegree faceIndex node:dstNode) != expectedCorners.count do
                    throw ("第 " + (faceIndex as string) + " 面的法线残差角数不一致。")
                for cornerIndex = 1 to expectedCorners.count do
                (
                    local expectedId = expectedCorners[cornerIndex][1]
                    local expectedSpecified = expectedCorners[cornerIndex][2]
                    local actualSpecified =
                        dstMod.GetFaceNormalSpecified faceIndex cornerIndex node:dstNode
                    if expectedSpecified != actualSpecified do
                        throw ("第 " + (faceIndex as string) + " 面第 " +
                            (cornerIndex as string) + " 角的蓝色/绿色法线状态不一致。")
                    if expectedSpecified then
                    (
                        local actualId = dstMod.GetNormalID faceIndex cornerIndex node:dstNode
                        if actualId < 1 or actualId > dstNormalCount do
                            throw "自定义法线残差读回 ID 越界。"
                        if not (dstMod.GetNormalExplicit actualId node:dstNode) do
                            throw "保留的自定义法线残差不是 Explicit。"
                        local expectedNormal = srcData[3][expectedId][1]
                        local actualNormal = dstMod.GetNormal actualId node:dstNode
                        if (distance expectedNormal actualNormal) > tolerance do
                            throw ("第 " + (faceIndex as string) + " 面第 " +
                                (cornerIndex as string) + " 角的自定义法线残差向量不一致。")
                    )
                )
            )
            true
        )
        catch
        (
            setLastMessage ("光滑组/自定义法线残差读回失败：" + getCurrentException())
            false
        )
    ),

    fn applyEditNormalResidualsFresh srcData dstNode dstMod =
    (
        try
        (
            if srcData == undefined or srcData.count != 4 do
                throw "自定义法线残差快照无效。"
            if (dstMod.GetNumFaces node:dstNode) != srcData[1] do
                throw "新建 Edit Normals 的面数与残差快照不一致。"

            -- 从光滑组计算出的全蓝色基线开始，只打断真正需要绿色覆盖的
            -- normal fan。不能复制 FBX 第二遍的全 Specified 本地数据，否则
            -- 即使把 Explicit 标志关掉，Max 仍可能保留整片青色法线。
            local breakNormals = #{}
            for faceIndex = 1 to srcData[1] do
            (
                local expectedCorners = srcData[4][faceIndex]
                for cornerIndex = 1 to expectedCorners.count where
                    expectedCorners[cornerIndex][2] do
                (
                    local actualId =
                        dstMod.GetNormalID faceIndex cornerIndex node:dstNode
                    breakNormals[actualId] = true
                )
            )
            if breakNormals.numberSet > 0 do
            (
                if not (dstMod.Break selection:breakNormals node:dstNode toAverage:false) do
                    throw "Edit Normals 无法打断需要覆盖的法线扇区。"
            )

            local resetNormals = #{}
            local residualNormals = #{}
            for faceIndex = 1 to srcData[1] do
            (
                local expectedCorners = srcData[4][faceIndex]
                if (dstMod.GetFaceDegree faceIndex node:dstNode) != expectedCorners.count do
                    throw ("第 " + (faceIndex as string) + " 面的残差角数不一致。")
                for cornerIndex = 1 to expectedCorners.count do
                (
                    local actualId =
                        dstMod.GetNormalID faceIndex cornerIndex node:dstNode
                    if expectedCorners[cornerIndex][2] then
                        residualNormals[actualId] = true
                    else
                        resetNormals[actualId] = true
                )
            )
            if (residualNormals * resetNormals).numberSet > 0 do
                throw "打断法线后仍有蓝色基线和绿色残差共用同一 normal ID。"
            if resetNormals.numberSet > 0 do
                try(dstMod.Reset selection:resetNormals node:dstNode)catch()

            -- Reset 可能重建 normal pool；按面角重新收集残差 ID。
            residualNormals = #{}
            for faceIndex = 1 to srcData[1] do
            (
                local expectedCorners = srcData[4][faceIndex]
                for cornerIndex = 1 to expectedCorners.count do
                (
                    local expectedSpecified = expectedCorners[cornerIndex][2]
                    dstMod.SetFaceNormalSpecified faceIndex cornerIndex specified:false node:dstNode
                    if expectedSpecified do
                    (
                        local actualId =
                            dstMod.GetNormalID faceIndex cornerIndex node:dstNode
                        residualNormals[actualId] = true
                    )
                )
            )
            if residualNormals.numberSet < 1 do
                throw "没有找到可写入的自定义法线残差 ID。"
            if not (dstMod.MakeExplicit selection:residualNormals node:dstNode) do
                throw "Edit Normals MakeExplicit 残差操作失败。"

            for faceIndex = 1 to srcData[1] do
            (
                local expectedCorners = srcData[4][faceIndex]
                for cornerIndex = 1 to expectedCorners.count where
                    expectedCorners[cornerIndex][2] do
                (
                    local expectedId = expectedCorners[cornerIndex][1]
                    local actualId =
                        dstMod.GetNormalID faceIndex cornerIndex node:dstNode
                    local normalValue = srcData[3][expectedId][1]
                    dstMod.SetNormal actualId &normalValue node:dstNode
                    dstMod.SetFaceNormalSpecified faceIndex cornerIndex specified:true node:dstNode
                )
            )
            update dstNode
            true
        )
        catch
        (
            setLastMessage ("光滑组/自定义法线残差写入失败：" + getCurrentException())
            false
        )
    ),

    fn buildEditNormalResidualSnapshotFlat srcData baselineData angleToleranceDegrees:0.1 =
    (
        try
        (
            if not (isFlatEditNormalsSnapshot srcData) or
               not (isFlatEditNormalsSnapshot baselineData) do
                throw "法线残差扁平快照无效。"
            if srcData[1] != baselineData[1] do
                throw "FBX 精确法线与光滑组基线面数不一致。"
            if angleToleranceDegrees < 0.0 or
               angleToleranceDegrees > 180.0 do
                throw "法线残差角度阈值超出 0–180°。"

            local residualNormalIds = #{}
            local residualSpecifiedCorners = #{}
            local residualBaselineNormalIds = #{}
            local residualCornerCount = 0
            local originalSpecifiedCorners = 0
            local sourceCornerCount = srcData[7].count
            local maxIgnoredAngle = 0.0
            local maxAngle = 0.0

            for faceIndex = 1 to srcData[1] do
            (
                local srcStart = srcData[6][faceIndex]
                local srcDegree =
                    srcData[6][faceIndex + 1] - srcStart
                local baselineStart = baselineData[6][faceIndex]
                local baselineDegree =
                    baselineData[6][faceIndex + 1] - baselineStart
                if srcDegree != baselineDegree do
                    throw ("第 " + (faceIndex as string) +
                        " 面的精确法线与光滑组基线角数不一致。")
                for cornerIndex = 1 to srcDegree do
                (
                    local srcFlatCorner = srcStart + cornerIndex - 1
                    local baselineFlatCorner =
                        baselineStart + cornerIndex - 1
                    local srcNormalId = srcData[7][srcFlatCorner]
                    local baselineNormalId =
                        baselineData[7][baselineFlatCorner]
                    if srcNormalId < 1 or srcNormalId > srcData[2] or
                       baselineNormalId < 1 or
                       baselineNormalId > baselineData[2] do
                        throw ("第 " + (faceIndex as string) + " 面第 " +
                            (cornerIndex as string) + " 角的法线 ID 越界。")
                    local sourceCornerSpecified =
                        srcData[8][srcFlatCorner]
                    if sourceCornerSpecified do
                        originalSpecifiedCorners += 1
                    -- 混合模式的目标不是复制“法线属性标签”，而是让每个
                    -- 面角的最终方向与 FBX 目标一致。即使某个源面角没有
                    -- Explicit/Specified 标志，也必须参与最终方向分类。
                    local sourceNormal =
                        flatEditNormalVector srcData srcNormalId
                    local baselineNormal =
                        flatEditNormalVector baselineData baselineNormalId
                    local angleValue =
                        normalAngleDegrees sourceNormal baselineNormal
                    sourceNormal = undefined
                    baselineNormal = undefined
                    if angleValue > maxAngle do maxAngle = angleValue
                    if angleValue > angleToleranceDegrees then
                    (
                        -- 面角才是最终着色的权威单位。同一个 FBX normal ID
                        -- 可能落在不同的 SG 基线 fan 上：一个角需要覆盖，
                        -- 另一个角已经由 SG 等价表达。只标记真正超阈值的角，
                        -- normal ID 仅用于向量来源和去重统计，不能反向扩散。
                        residualSpecifiedCorners[srcFlatCorner] = true
                        residualNormalIds[srcNormalId] = true
                        residualBaselineNormalIds[baselineNormalId] = true
                        residualCornerCount += 1
                    )
                    else if angleValue > maxIgnoredAngle do
                        maxIgnoredAngle = angleValue
                )
            )

            -- Edit Normals does not evaluate one Explicit corner in complete
            -- isolation.  If only one corner of an SG-soft fan stays
            -- Specified, Rebuild/update removes that face's contribution from
            -- its Unspecified siblings and changes their direction.  Preserve
            -- the smallest stable closure: every corner that shared the
            -- residual corner's *baseline* SG normal ID.  These companions are
            -- guards, not additional semantic/custom residuals.
            local retainedSpecifiedCorners = copy residualSpecifiedCorners
            local retainedNormalIds = copy residualNormalIds
            for flatCornerIndex = 1 to sourceCornerCount do
            (
                local baselineNormalId =
                    baselineData[7][flatCornerIndex]
                if residualBaselineNormalIds[baselineNormalId] do
                (
                    retainedSpecifiedCorners[flatCornerIndex] = true
                    retainedNormalIds[srcData[7][flatCornerIndex]] = true
                )
            )
            local guardCornerCount =
                retainedSpecifiedCorners.numberSet - residualCornerCount
            local residualExplicit = copy retainedNormalIds
            local residualAuthored = copy retainedNormalIds
            local residualData = #(
                srcData[1],
                srcData[2],
                srcData[3],
                residualExplicit,
                residualAuthored,
                srcData[6],
                srcData[7],
                retainedSpecifiedCorners
            )
            #(
                residualData,
                residualNormalIds.numberSet,
                residualCornerCount,
                originalSpecifiedCorners,
                maxIgnoredAngle,
                maxAngle,
                sourceCornerCount,
                retainedNormalIds.numberSet,
                guardCornerCount,
                retainedSpecifiedCorners.numberSet
            )
        )
        catch
        (
            setLastMessage ("光滑组/自定义法线扁平残差分类失败：" +
                getCurrentException())
            undefined
        )
    ),

    fn editNormalResidualsFlatMatch srcData dstNode dstMod tolerance:0.00001 =
    (
        try
        (
            if not (isFlatEditNormalsSnapshot srcData) do
                throw "自定义法线残差扁平快照无效。"
            if (dstMod.GetNumFaces node:dstNode) != srcData[1] do
                throw "自定义法线残差读回面数不一致。"
            local dstNormalCount = dstMod.GetNumNormals node:dstNode
            for faceIndex = 1 to srcData[1] do
            (
                local sourceStart = srcData[6][faceIndex]
                local sourceDegree =
                    srcData[6][faceIndex + 1] - sourceStart
                if (dstMod.GetFaceDegree faceIndex node:dstNode) !=
                   sourceDegree do
                    throw ("第 " + (faceIndex as string) +
                        " 面的法线残差角数不一致。")
                for cornerIndex = 1 to sourceDegree do
                (
                    local flatCornerIndex =
                        sourceStart + cornerIndex - 1
                    local expectedId = srcData[7][flatCornerIndex]
                    local expectedSpecified =
                        srcData[8][flatCornerIndex]
                    local actualId =
                        dstMod.GetNormalID faceIndex cornerIndex node:dstNode
                    if actualId < 1 or actualId > dstNormalCount do
                        throw "自定义法线残差读回 ID 越界。"
                    local actualSpecified = dstMod.GetFaceNormalSpecified faceIndex cornerIndex node:dstNode
                    if expectedSpecified != actualSpecified do
                        throw ("第 " + (faceIndex as string) + " 面第 " +
                            (cornerIndex as string) +
                            " 角的蓝色/绿色法线状态不一致：期望 " +
                            (if expectedSpecified then "绿色 Specified" else
                                "蓝色 Unspecified") + "，实际 " +
                            (if actualSpecified then "绿色 Specified" else
                                "蓝色 Unspecified") + "，法线 ID " +
                            (actualId as string) +
                            "。")
                    if expectedSpecified then
                    (
                        if not (dstMod.GetNormalExplicit actualId node:dstNode) do
                            throw "保留的自定义法线残差不是 Explicit。"
                        local expectedNormal = flatEditNormalVector srcData expectedId
                        local actualNormal = dstMod.GetNormal actualId node:dstNode
                        local vectorMatches =
                            (distance expectedNormal actualNormal) <= tolerance
                        expectedNormal = undefined
                        actualNormal = undefined
                        if not vectorMatches do
                            throw ("第 " + (faceIndex as string) + " 面第 " +
                                (cornerIndex as string) +
                                " 角的自定义法线残差向量不一致。")
                    )
                    else
                    (
                        if dstMod.GetNormalExplicit actualId node:dstNode do
                            throw ("第 " + (faceIndex as string) + " 面第 " +
                                (cornerIndex as string) +
                                " 角应由光滑组求值，但其法线 ID " +
                                (actualId as string) + " 仍是 Explicit。")
                    )
                )
            )
            true
        )
        catch
        (
            setLastMessage ("光滑组/自定义法线扁平残差读回失败：" +
                getCurrentException())
            false
        )
    ),

    fn finalFaceCornerNormalsFlatMatch expectedData dstNode dstMod angleToleranceDegrees:0.1 rebuildBeforeRead:true =
    (
        try
        (
            if not (isFlatEditNormalsSnapshot expectedData) do
                throw "最终面角法线目标快照无效。"
            if angleToleranceDegrees < 0.0 or
               angleToleranceDegrees > 180.0 do
                throw "最终面角法线角度阈值超出 0–180°。"
            if (dstMod.GetNumFaces node:dstNode) != expectedData[1] do
                throw "最终面角法线读回面数不一致。"

            -- Explicit 是对该面角最终法线的覆盖，不是与光滑组向量相加。
            -- 因此最终验收直接比较每个面角的求值方向；既覆盖绿色
            -- Explicit 角，也覆盖继续由光滑组计算的蓝色 Unspecified 角。
            if rebuildBeforeRead do
                rebuildEditNormalsStrict dstNode dstMod "最终逐面角法线验证重建失败"
            local actualNormalCount = dstMod.GetNumNormals node:dstNode
            local maxFinalAngle = 0.0
            for faceIndex = 1 to expectedData[1] do
            (
                local expectedStart = expectedData[6][faceIndex]
                local expectedDegree =
                    expectedData[6][faceIndex + 1] - expectedStart
                if (dstMod.GetFaceDegree faceIndex node:dstNode) !=
                   expectedDegree do
                    throw ("第 " + (faceIndex as string) +
                        " 面的最终法线角数不一致。")
                for cornerIndex = 1 to expectedDegree do
                (
                    local flatCornerIndex =
                        expectedStart + cornerIndex - 1
                    local expectedId =
                        expectedData[7][flatCornerIndex]
                    local actualId =
                        dstMod.GetNormalID faceIndex cornerIndex node:dstNode
                    if expectedId < 1 or expectedId > expectedData[2] or
                       actualId < 1 or actualId > actualNormalCount do
                        throw ("第 " + (faceIndex as string) + " 面第 " +
                            (cornerIndex as string) +
                            " 角的最终法线 ID 越界。")
                    local expectedNormal =
                        flatEditNormalVector expectedData expectedId
                    local actualNormal =
                        dstMod.GetNormal actualId node:dstNode
                    local angleValue =
                        normalAngleDegrees expectedNormal actualNormal
                    expectedNormal = undefined
                    actualNormal = undefined
                    if angleValue > maxFinalAngle do
                        maxFinalAngle = angleValue
                    if angleValue > angleToleranceDegrees do
                        throw ("第 " + (faceIndex as string) + " 面第 " +
                            (cornerIndex as string) +
                            " 角的最终法线方向与 FBX 目标不一致，角差 " +
                            (angleValue as string) + "°。")
                )
            )
            maxFinalAngle
        )
        catch
        (
            setLastMessage ("光滑组/顶点法线最终逐面角验证失败：" +
                getCurrentException())
            undefined
        )
    ),

    fn applyEditNormalResidualsFlatFromExact srcData dstNode dstMod =
    (
        try
        (
            if not (isFlatEditNormalsSnapshot srcData) do
                throw "自定义法线残差扁平快照无效。"
            if (dstMod.GetNumFaces node:dstNode) != srcData[1] do
                throw "新建 Edit Normals 的面数与残差快照不一致。"

            -- dstMod 是在实际接收模型、最终点位和最终光滑组之上新建并重建的。
            -- 此时每个 normal ID 都是 Max 自己生成的合法 SG fan。残差分类已经
            -- 对任何命中的 fan 做了最小完整闭包，因此只需打断这些完整 fan，
            -- 绝不从 FBX 的全 Explicit pool 反向“取消”蓝色法线。
            local retainedFans = #{}
            local baselineFans = #{}
            for faceIndex = 1 to srcData[1] do
            (
                local sourceStart = srcData[6][faceIndex]
                local sourceDegree =
                    srcData[6][faceIndex + 1] - sourceStart
                if (dstMod.GetFaceDegree faceIndex node:dstNode) !=
                   sourceDegree do
                    throw ("第 " + (faceIndex as string) +
                        " 面的残差角数不一致。")
                for cornerIndex = 1 to sourceDegree do
                (
                    local flatCornerIndex =
                        sourceStart + cornerIndex - 1
                    local actualId =
                        dstMod.GetNormalID faceIndex cornerIndex node:dstNode
                    if actualId < 1 do
                        throw "新建 Edit Normals 返回无效 SG normal ID。"
                    if srcData[8][flatCornerIndex] then
                        retainedFans[actualId] = true
                    else
                        baselineFans[actualId] = true
                    if dstMod.GetFaceNormalSpecified faceIndex cornerIndex node:dstNode do
                        throw "新建 Edit Normals 的 SG 基线意外含 Specified 面角。"
                )
            )
            if (retainedFans * baselineFans).numberSet > 0 do
                throw "残差 closure 没有覆盖完整的实际目标 SG fan。"
            local initialRetainedFanCount = retainedFans.numberSet
            if initialRetainedFanCount < 1 do
                throw "没有找到可写入的新建 Edit Normals 残差扇区。"
            if not (dstMod.Break selection:retainedFans node:dstNode toAverage:false) do
                throw "新建 Edit Normals 无法拆分完整残差扇区。"

            -- Break 会重建/重排 local normal pool；旧 ID 到此全部作废。
            -- 必须按最终目标的 face-corner 重新取得 actual normal ID。
            local residualNormals = #{}
            baselineFans = #{}
            local currentNormalCount = dstMod.GetNumNormals node:dstNode
            local expectedSourceIdByActual =
                for normalIndex = 1 to currentNormalCount collect 0
            for faceIndex = 1 to srcData[1] do
            (
                local sourceStart = srcData[6][faceIndex]
                local sourceDegree =
                    srcData[6][faceIndex + 1] - sourceStart
                if (dstMod.GetFaceDegree faceIndex node:dstNode) !=
                   sourceDegree do
                    throw ("第 " + (faceIndex as string) +
                        " 面的残差角数不一致。")
                for cornerIndex = 1 to sourceDegree do
                (
                    local flatCornerIndex =
                        sourceStart + cornerIndex - 1
                    local actualId =
                        dstMod.GetNormalID faceIndex cornerIndex node:dstNode
                    if actualId < 1 or actualId > currentNormalCount do
                        throw "Break 后的 actual normal ID 越界。"
                    if srcData[8][flatCornerIndex] then
                    (
                        residualNormals[actualId] = true
                        local expectedSourceId =
                            srcData[7][flatCornerIndex]
                        if expectedSourceIdByActual[actualId] == 0 then
                            expectedSourceIdByActual[actualId] =
                                expectedSourceId
                        else
                        (
                            local firstExpected = flatEditNormalVector srcData (
                                expectedSourceIdByActual[actualId])
                            local nextExpected =
                                flatEditNormalVector srcData expectedSourceId
                            local expectedAngle =
                                normalAngleDegrees firstExpected nextExpected
                            firstExpected = undefined
                            nextExpected = undefined
                            if expectedAngle > 0.001 do
                                throw ("Break 后的 residual normal ID " +
                                    (actualId as string) +
                                    " 仍对应多个不同 FBX 方向。")
                        )
                    )
                    else
                        baselineFans[actualId] = true
                )
            )
            if (residualNormals * baselineFans).numberSet > 0 do
                throw "Break 后仍有 SG 基线和残差共用 actual normal ID。"

            -- 只把重新取得的残差 ID 写成 FBX 的完整方向向量；这不是
            -- 向量差值相加。Break / MakeExplicit 会重排 normal pool，也可能
            -- 连带提升相邻状态，因此写完向量后必须把蓝色 baseline fan
            -- 明确恢复为非 Explicit，并逐面角重放最终 Specified 真/假状态。
            if not (dstMod.MakeExplicit selection:residualNormals node:dstNode) do
                throw "新建 Edit Normals MakeExplicit 残差失败。"
            for normalIndex in residualNormals do
            (
                local expectedSourceId = expectedSourceIdByActual[normalIndex]
                if expectedSourceId < 1 do
                    throw ("残差 actual normal ID " +
                        (normalIndex as string) + " 没有 FBX 权威方向。")
                local expectedNormal =
                    flatEditNormalVector srcData expectedSourceId
                dstMod.SetNormal normalIndex &expectedNormal node:dstNode
                expectedNormal = undefined
            )

            for normalIndex in baselineFans where
                dstMod.GetNormalExplicit normalIndex node:dstNode do
                    dstMod.SetNormalExplicit normalIndex explicit:false node:dstNode

            -- 重放全部角，而不只补 true。这样蓝色 SG 角明确保持
            -- Unspecified，绿色/黄色残差角明确保持 Specified；随后仍由
            -- editNormalResidualsFlatMatch 对两类结构逐角验收，不能掩盖错误。
            for faceIndex = 1 to srcData[1] do
            (
                local sourceStart = srcData[6][faceIndex]
                local sourceDegree =
                    srcData[6][faceIndex + 1] - sourceStart
                for cornerIndex = 1 to sourceDegree do
                (
                    local flatCornerIndex =
                        sourceStart + cornerIndex - 1
                    dstMod.SetFaceNormalSpecified faceIndex cornerIndex specified:(srcData[8][flatCornerIndex]) node:dstNode
                )
            )
            update dstNode
            setLastMessage ("实际目标 SG 基线残差写入完成：完整 SG fan " +
                (initialRetainedFanCount as string) +
                "，Break 后 Explicit actual ID " +
                (residualNormals.numberSet as string) +
                "，未触碰的蓝色 SG baseline actual ID " +
                (baselineFans.numberSet as string) + "。")
            expectedSourceIdByActual = undefined
            baselineFans = undefined
            retainedFans = undefined
            residualNormals = undefined
            true
        )
        catch
        (
            setLastMessage ("实际目标光滑组/自定义法线残差写入失败：" +
                getCurrentException())
            false
        )
    ),

    fn copyExplicitNormalResiduals src dst faceMap:#() cornerMaps:#() cornerMapStarts:#() cornerMapFlat:#() angleToleranceDegrees:0.1 =
    (
        setLastMessage ""
        local srcMod = undefined
        local dstMod = undefined
        local srcReaderIsTemp = false
        local oldSelection = selection as array
        local ok = false
        local srcData = undefined
        local baselineData = undefined
        local residualResult = undefined
        local residualData = undefined
        try
        (
            local blockers = blockingNormalModifierNames dst
            if blockers.count > 0 do
                throw ("Max 源模型存在用户法线修改器，会覆盖插件结果；为保护用户修改器已停止：" +
                    (blockers as string))

            -- Use a dedicated top-of-stack reader so an imported/user modifier
            -- is never reused and the FBX authority is its fully evaluated
            -- face-corner direction, including imported Skin.
            srcMod = Edit_Normals()
            srcMod.name = "F2M_读取 FBX 目标模型求值顶点法线"
            addModifier src srcMod
            srcReaderIsTemp = true
            if not (activateModifier src srcMod) do
                throw "无法激活 FBX 目标 Edit Normals 读取器。"
            rebuildEditNormalsStrict src srcMod "读取 FBX 目标顶点法线时重建失败"
            local customCounts = editNormalsCustomCounts src srcMod
            if customCounts[1] < 1 and customCounts[2] < 1 do
                throw "FBX 目标模型没有可传递的 Specified / Explicit 自定义法线。"
            customCounts = undefined

            srcData = snapshotEditNormalsDataFlat src srcMod
            if srcData == undefined do
                throw ("无法快照 FBX 目标 Edit Normals：" + lastMessage)
            srcData = transformEditNormalsSnapshotFlat srcData src dst includeAllReferenced:true
            if srcData == undefined do
                throw ("无法转换 FBX 目标自定义法线空间：" + lastMessage)
            srcData = remapEditNormalsSnapshotFlat srcData faceMap:faceMap cornerMaps:cornerMaps cornerMapStarts:cornerMapStarts cornerMapFlat:cornerMapFlat
            if srcData == undefined do
                throw ("无法映射 FBX 目标自定义法线面角：" + lastMessage)

            local removedOldDstMods = removeF2MNormalModifiers dst
            if (countF2MNormalModifiers dst) != 0 do
                throw "旧 F2M 顶点法线修改器未能完整移除，已停止以避免重复栈。"

            -- 残差基线必须来自实际接收模型，而不是第一次 FBX 临时导入。
            -- 此时外形（若勾选）与光滑组（若勾选）都已完成，且光滑组已经
            -- 逐面读回。新建的 Edit Normals 因而代表最终点位 + 最终 SG
            -- 所产生的蓝色 Unspecified 法线。
            dstMod = Edit_Normals()
            dstMod.name = "F2M_顶点法线"
            if dst.modifiers.count > 0 then
                addModifier dst dstMod before:(dst.modifiers.count + 1)
            else
                addModifier dst dstMod
            local dstIndex = modifierIndex dst dstMod
            if dstIndex == undefined or dstIndex != dst.modifiers.count do
                throw "新建 Edit Normals 没有位于 Max 源模型修改器栈底。"
            if not (activateModifier dst dstMod) do
                throw "无法激活新建 Max 源 Edit Normals。"
            resetEditNormalsToSmoothingBaselineStrict dst dstMod
            baselineData = snapshotEditNormalsDataFlat dst dstMod
            if baselineData == undefined do
                throw ("无法快照实际接收模型 SG 法线基线：" + lastMessage)
            if baselineData[4].numberSet != 0 or
               baselineData[8].numberSet != 0 do
                throw ("实际接收模型 SG 基线不是全蓝色 Unspecified 状态：" +
                    "Explicit=" + (baselineData[4].numberSet as string) +
                    "，Specified=" + (baselineData[8].numberSet as string) +
                    "。")
            update dst
            local stableBaselineMaxAngle =
                finalFaceCornerNormalsFlatMatch baselineData dst dstMod angleToleranceDegrees:angleToleranceDegrees rebuildBeforeRead:false
            if stableBaselineMaxAngle == undefined do
                throw ("实际接收模型 SG 法线基线重评估失败：" + lastMessage)

            residualResult = buildEditNormalResidualSnapshotFlat srcData baselineData angleToleranceDegrees:angleToleranceDegrees
            if residualResult == undefined do throw lastMessage
            residualData = residualResult[1]
            local residualNormalCount = residualResult[2]
            local residualCornerCount = residualResult[3]
            local originalSpecifiedCorners = residualResult[4]
            local maxIgnoredAngle = residualResult[5]
            local maxAngle = residualResult[6]
            local sourceCornerCount = residualResult[7]
            local retainedNormalCount = residualResult[8]
            local guardCornerCount = residualResult[9]
            local retainedCornerCount = residualResult[10]
            residualResult = undefined
            baselineData = undefined

            if retainedNormalCount == 0 then
            (
                -- 即使没有 > 阈值的 Explicit 残差，也必须保留这个全蓝色
                -- Unspecified 基线修改器。基础网格可能仍嵌有旧自定义法线；
                -- 删除基线会让它们重新暴露，使正式返回后的最终栈偏离 FBX。
                if not (editNormalResidualsFlatMatch residualData dst dstMod) do
                    throw ("零残差纯 SG 基线结构读回失败：" + lastMessage)
                local zeroFirstFinalMaxAngle =
                    finalFaceCornerNormalsFlatMatch srcData dst dstMod angleToleranceDegrees:angleToleranceDegrees rebuildBeforeRead:false
                if zeroFirstFinalMaxAngle == undefined do
                    throw ("零残差纯 SG 基线最终方向读回失败：" + lastMessage)
                update dst
                if not (editNormalResidualsFlatMatch residualData dst dstMod) do
                    throw ("零残差纯 SG 基线重评估失败：" + lastMessage)
                local zeroSecondFinalMaxAngle =
                    finalFaceCornerNormalsFlatMatch srcData dst dstMod angleToleranceDegrees:angleToleranceDegrees rebuildBeforeRead:false
                if zeroSecondFinalMaxAngle == undefined do
                    throw ("零残差纯 SG 基线最终方向重评估失败：" + lastMessage)
                if not (editNormalResidualsFlatMatch residualData dst dstMod) do
                    throw ("零残差最终方向读回后的基线结构复核失败：" +
                        lastMessage)
                local zeroFinalMaxAngle =
                    amax zeroFirstFinalMaxAngle zeroSecondFinalMaxAngle
                setLastMessage ("顶点法线完成：当前光滑组在 " +
                    ((angleToleranceDegrees as float) as string) +
                    "° 阈值内已等价表达全部 " +
                    (sourceCornerCount as string) +
                    " 个 FBX 面角方向；自定义法线残差为 0，保留一个全蓝色 " +
                    "Unspecified 的 F2M Edit Normals 基线，以隔离基础网格旧法线。" +
                    "原始 Specified 面角 " +
                    (originalSpecifiedCorners as string) + "，最大角差 " +
                    (maxAngle as string) + "°，最大最终角差 " +
                    (zeroFinalMaxAngle as string) + "°。")
                ok = true
            )
            else
            (
                -- dstMod 已经只包含实际接收模型的合法 SG local data。
                if not (applyEditNormalResidualsFlatFromExact residualData dst dstMod) do
                    throw ("Edit Normals 写入 SG 差异残差失败：" + lastMessage)
                if not (editNormalResidualsFlatMatch residualData dst dstMod) do
                    throw ("Edit Normals 残差结构读回失败：" + lastMessage)

                local firstFinalMaxAngle = finalFaceCornerNormalsFlatMatch srcData dst dstMod angleToleranceDegrees:angleToleranceDegrees rebuildBeforeRead:false
                if firstFinalMaxAngle == undefined do
                    throw ("Edit Normals 最终逐面角方向读回失败：" + lastMessage)
                update dst
                if not (editNormalResidualsFlatMatch residualData dst dstMod) do
                    throw ("Edit Normals 残差重评估失败：" + lastMessage)
                local secondFinalMaxAngle = finalFaceCornerNormalsFlatMatch srcData dst dstMod angleToleranceDegrees:angleToleranceDegrees rebuildBeforeRead:false
                if secondFinalMaxAngle == undefined do
                    throw ("Edit Normals 最终逐面角方向重评估失败：" + lastMessage)
                if not (editNormalResidualsFlatMatch residualData dst dstMod) do
                    throw ("Edit Normals 最终方向读回后的残差结构复核失败：" +
                        lastMessage)
                local finalMaxAngle =
                    amax firstFinalMaxAngle secondFinalMaxAngle
                setLastMessage ("顶点法线完成：先以实际接收模型最终点位和光滑组" +
                    "建立蓝色基线，再仅保留其不能等价表达的 FBX 自定义法线" +
                    "残差；语义残差法线记录 " +
                    (residualNormalCount as string) + "，面角 " +
                    (residualCornerCount as string) + "/" +
                    (sourceCornerCount as string) + "；最小保护面角 " +
                    (guardCornerCount as string) + "；最终 Explicit 法线记录 " +
                    (retainedNormalCount as string) + "，Specified 面角 " +
                    (retainedCornerCount as string) + "/" +
                    (sourceCornerCount as string) + "（原始 Specified " +
                    (originalSpecifiedCorners as string) + "）；阈值 " +
                    ((angleToleranceDegrees as float) as string) +
                    "°，最大省略角差 " + (maxIgnoredAngle as string) +
                    "°，最大残差 " + (maxAngle as string) +
                    "°，最大最终角差 " + (finalMaxAngle as string) +
                    "°；全部面角最终方向已完成两次读回。")
                ok = true
            )
        )
        catch
        (
            setLastMessage ("顶点法线残差传递失败：" + getCurrentException())
            ok = false
        )
        if srcReaderIsTemp and srcMod != undefined do
        (
            local srcReaderHandle = undefined
            try(srcReaderHandle = getHandleByAnim srcMod)catch()
            srcMod = undefined
            if srcReaderHandle == undefined or
               not (F2M_Helper.removeModifierByAnimHandle src srcReaderHandle) do
            (
                setLastMessage ("法线残差传递后无法安全删除 FBX 临时读取器：" +
                    lastMessage)
                ok = false
            )
        )
        srcMod = undefined
        if not ok do
        (
            dstMod = undefined
            try(removeF2MNormalModifiers dst)catch()
        )
        dstMod = undefined
        try(select oldSelection)catch()
        srcData = undefined
        baselineData = undefined
        residualResult = undefined
        residualData = undefined
        srcMod = undefined
        dstMod = undefined
        oldSelection = #()
        faceMap = #()
        cornerMaps = #()
        cornerMapStarts = #()
        cornerMapFlat = #()
        ok
    ),

    fn copyExplicitNormals src dst faceMap:#() cornerMaps:#() cornerMapStarts:#() cornerMapFlat:#() =
    (
        setLastMessage ""
        local srcMod = undefined
        local dstMod = undefined
        local ok = false
        local removedOldDstMods = 0
        local srcFaceCount = 0
        local srcNormalCount = 0
        local srcData = undefined
        local oldSelection = selection as array
        local srcReaderIsTemp = false

        try
        (
            local blockers = blockingNormalModifierNames dst
            if blockers.count > 0 do
                throw ("Max 源模型存在用户法线修改器，会覆盖插件结果；为保护用户修改器已停止：" +
                    (blockers as string))

            srcMod = Edit_Normals()
            srcMod.name = "F2M_读取 FBX 目标模型求值顶点法线"
            addModifier src srcMod
            srcReaderIsTemp = true
            try
            (
                activateModifier src srcMod
            )
            catch()

            rebuildEditNormalsStrict src srcMod "读取 FBX 目标显式法线时重建失败"
            srcFaceCount = srcMod.GetNumFaces node:src
            if srcFaceCount < 1 do throw "FBX 目标模型没有可读取的 Edit Normals 面数据。请确认 FBX/OBJ 导入时保留了自定义法线。"
            try(srcNormalCount = srcMod.GetNumNormals node:src)catch(srcNormalCount = 0)
            local customCounts = editNormalsCustomCounts src srcMod
            if customCounts[1] < 1 and customCounts[2] < 1 do
                throw "FBX 目标模型只有由光滑组计算的普通法线，没有可传递的 Specified / Explicit 自定义法线。"
            customCounts = undefined
            srcData = snapshotEditNormalsDataFlat src srcMod
            if srcData == undefined do throw ("无法快照 FBX 目标 Edit Normals：" + lastMessage)
            srcData = transformEditNormalsSnapshotFlat srcData src dst
            if srcData == undefined do throw ("无法转换 FBX 目标自定义法线空间：" + lastMessage)
            srcData = remapEditNormalsSnapshotFlat srcData faceMap:faceMap cornerMaps:cornerMaps cornerMapStarts:cornerMapStarts cornerMapFlat:cornerMapFlat
            if srcData == undefined do throw ("无法映射 FBX 目标自定义法线面角：" + lastMessage)

            removedOldDstMods = removeF2MNormalModifiers dst
            if (countF2MNormalModifiers dst) != 0 do
                throw "旧 F2M 顶点法线修改器未能完整移除，已停止以避免重复栈。"

            dstMod = copy srcMod
            dstMod.name = "F2M_顶点法线"
            local copyDataError = ""
            try
            (
                -- Edit Normals 不能塌陷到 Editable Poly；Autodesk 明确说明
                -- 这样会丢失显式法线。保留它作为栈底修改器，让 Skin/变形
                -- 和其它用户修改器继续位于其上方。
                if dst.modifiers.count > 0 then
                    addModifierWithLocalData dst dstMod src srcMod before:(dst.modifiers.count + 1)
                else
                    addModifierWithLocalData dst dstMod src srcMod
            )
            catch
            (
                copyDataError = getCurrentException()
            )
            if copyDataError != "" do throw ("复制 Edit Normals 本地数据失败：" + copyDataError)

            local dstIndex = modifierIndex dst dstMod
            if dstIndex == undefined or dstIndex != dst.modifiers.count do
                throw "Edit Normals 没有位于 Max 源模型修改器栈底，已停止以保护法线和用户修改器。"
            if not (activateModifier dst dstMod) do
                throw "无法激活 Max 源 Edit Normals 进行写后验证。"
            rebuildEditNormalsStrict dst dstMod "Max 源显式法线写前重建失败"
            if not (applyEditNormalsSnapshotFlat srcData dst dstMod) do
                throw ("Edit Normals 显式写入失败：" + lastMessage)
            if not (editNormalsSnapshotFlatMatches srcData dst dstMod) do
                throw ("Edit Normals 写后完整读回失败：" + lastMessage)
            -- Skin、变形器和对象空间变换会合法地改变最终评估法线方向，不能把
            -- 栈顶向量与栈底局部向量直接比较。阻断上方用户法线修改器后，强制
            -- 重评估并再次读取插件自己的持久局部数据才是正确的安全验证。
            update dst
            if not (editNormalsSnapshotFlatMatches srcData dst dstMod) do
                throw ("Edit Normals 重评估后完整读回失败：" + lastMessage)

            local extra = ""
            if removedOldDstMods > 0 do extra += ("；已移除旧 F2M 法线修改器 " + (removedOldDstMods as string) + " 个")
            if srcFaceCount > 0 do extra += ("；FBX 目标面数 " + (srcFaceCount as string))
            if srcNormalCount > 0 do extra += ("；FBX 目标法线数量 " + (srcNormalCount as string))
            setLastMessage ("顶点法线完成：已复制 Edit Normals 本地数据并保留为 Max 源模型栈底修改器；" +
                "法线向量、Explicit/Specified 状态和面角法线 ID 已两次完整读回" + extra + "。")
            ok = true
        )
        catch
        (
            setLastMessage ("顶点法线失败：" + getCurrentException())
            ok = false
        )

        if srcReaderIsTemp and srcMod != undefined do
        (
            local srcReaderHandle = undefined
            try(srcReaderHandle = getHandleByAnim srcMod)catch()
            srcMod = undefined
            if srcReaderHandle == undefined or
               not (F2M_Helper.removeModifierByAnimHandle src srcReaderHandle) do
            (
                setLastMessage ("显式法线传递后无法安全删除 FBX 临时读取器：" +
                    lastMessage)
                ok = false
            )
        )
        srcMod = undefined
        if not ok do
        (
            dstMod = undefined
            try(removeF2MNormalModifiers dst)catch()
        )
        dstMod = undefined
        try(select oldSelection)catch()
        srcData = undefined
        srcMod = undefined
        dstMod = undefined
        oldSelection = #()
        faceMap = #()
        cornerMaps = #()
        cornerMapStarts = #()
        cornerMapFlat = #()
        ok
    ),

    fn pointReadbackTolerance firstPoint secondPoint =
    (
        -- Point3 values are stored as 32-bit floats.  A fixed 1e-5 absolute
        -- tolerance is smaller than one ULP once a coordinate reaches roughly
        -- 128 units, so an exact setVert can legitimately read back about
        -- 1.52588e-5 away.  A world -> local -> world round trip also performs
        -- several float matrix operations and the final distance combines all
        -- three axes.  Keep a tight absolute floor for small models and allow
        -- two parts per million of coordinate scale (several ULPs, not a
        -- geometric approximation) for transformed scenes.
        local scale = 1.0
        for value in #(
            firstPoint.x, firstPoint.y, firstPoint.z,
            secondPoint.x, secondPoint.y, secondPoint.z
        ) do
        (
            local magnitude = abs value
            if magnitude > scale do scale = magnitude
        )
        0.000002 + (scale * 0.000002)
    ),

    fn pointsReadbackEqual firstPoint secondPoint =
    (
        (distance firstPoint secondPoint) <=
            (pointReadbackTolerance firstPoint secondPoint)
    ),

    -- polyop/getVert node overloads use Max's current reference coordinate
    -- system.  A user's World/Local/View toolbar state must never change the
    -- transferred geometry, so every node-level point operation is wrapped in
    -- an explicit world context.  Base-object reads below remain local and
    -- provide an independent second readback domain.
    fn setPolyVertWorld n vertexIndex value =
    (
        in coordsys world (polyop.setVert n vertexIndex value)
    ),

    fn getPolyVertWorld n vertexIndex =
    (
        in coordsys world (polyop.getVert n vertexIndex)
    ),

    fn setMeshVertWorld n vertexIndex value =
    (
        in coordsys world (setVert n vertexIndex value)
    ),

    fn getMeshVertWorld n vertexIndex =
    (
        in coordsys world (getVert n vertexIndex)
    ),

    fn copyBaseVertexPositions src dst =
    (
        local srcMesh = undefined
        local baseObj = undefined
        local baseName = ""
        local originalVerts = #()
        local originalMesh = undefined
        local workingMesh = undefined
        local readbackMesh = undefined
        local sourceCount = 0
        local writeStarted = false
        local ok = false
        try
        (
            -- The mature Mode-1 path transfers the FBX node's evaluated shape.
            -- The legacy helper wrote the destination-node-domain value through
            -- the node while Max was normally in #hybrid.  Explicit world node
            -- I/O is the verified deterministic equivalent for both skinned and
            -- unskinned receivers; it also removes dependence on the user's
            -- World/Local/View toolbar state.
            srcMesh = snapshotAsMesh src
            baseObj = dst.baseObject
            baseName = (classof baseObj) as string
            local srcTM = src.objectTransform
            local dstInvTM = inverse dst.objectTransform
            sourceCount = getNumVerts srcMesh
            if sourceCount < 1 do throw "无法读取 FBX 目标模型求值点位。"

            if baseName == "Editable_Poly" then
            (
                if (polyop.getNumVerts baseObj) != sourceCount do throw "点数不一致"
                for i = 1 to sourceCount do append originalVerts (polyop.getVert baseObj i)
                writeStarted = true
                for i = 1 to sourceCount do
                (
                    local expectedNode = ((meshop.getVert srcMesh i) * srcTM) * dstInvTM
                    setPolyVertWorld dst i expectedNode
                )
                update dst
                for i = 1 to sourceCount do
                (
                    local expectedNode = ((meshop.getVert srcMesh i) * srcTM) * dstInvTM
                    local actualNode = getPolyVertWorld dst i
                    local nodeDelta = distance actualNode expectedNode
                    local nodeTolerance = pointReadbackTolerance actualNode expectedNode
                    if nodeDelta > nodeTolerance do
                        throw (
                            "第 " + i as string + " 个点写后节点坐标域回读不一致；差值 " +
                            nodeDelta as string + "，允许 " + nodeTolerance as string +
                            "，期望 " + expectedNode as string +
                            "，实际 " + actualNode as string + "。"
                        )
                    local expectedLocal = expectedNode * dstInvTM
                    local actualLocal = polyop.getVert baseObj i
                    local localDelta = distance actualLocal expectedLocal
                    local localTolerance = pointReadbackTolerance actualLocal expectedLocal
                    if localDelta > localTolerance do
                        throw (
                            "第 " + i as string + " 个点写后基础局部空间回读不一致；差值 " +
                            localDelta as string + "，允许 " + localTolerance as string +
                            "，期望 " + expectedLocal as string +
                            "，实际 " + actualLocal as string + "。"
                        )
                )
                ok = true
            )
            else if baseName == "Editable_mesh" or baseName == "Editable Mesh" then
            (
                originalMesh = copy baseObj.mesh
                if (getNumVerts originalMesh) != sourceCount do throw "点数不一致"
                writeStarted = true
                for i = 1 to sourceCount do
                (
                    local expectedNode = ((meshop.getVert srcMesh i) * srcTM) * dstInvTM
                    setMeshVertWorld dst i expectedNode
                )
                update dst
                if (getNumVerts dst) != sourceCount do throw "写后回读点数不一致"
                readbackMesh = copy baseObj.mesh
                for i = 1 to sourceCount do
                (
                    local expectedNode = ((meshop.getVert srcMesh i) * srcTM) * dstInvTM
                    local actualNode = getMeshVertWorld dst i
                    local nodeDelta = distance actualNode expectedNode
                    local nodeTolerance = pointReadbackTolerance actualNode expectedNode
                    if nodeDelta > nodeTolerance do
                        throw (
                            "第 " + i as string + " 个点写后节点坐标域回读不一致；差值 " +
                            nodeDelta as string + "，允许 " + nodeTolerance as string +
                            "，期望 " + expectedNode as string +
                            "，实际 " + actualNode as string + "。"
                        )
                    local expectedLocal = expectedNode * dstInvTM
                    local actualLocal = meshop.getVert readbackMesh i
                    local localDelta = distance actualLocal expectedLocal
                    local localTolerance = pointReadbackTolerance actualLocal expectedLocal
                    if localDelta > localTolerance do
                        throw (
                            "第 " + i as string + " 个点写后基础局部空间回读不一致；差值 " +
                            localDelta as string + "，允许 " + localTolerance as string +
                            "，期望 " + expectedLocal as string +
                            "，实际 " + actualLocal as string + "。"
                        )
                )
                ok = true
            )
            else
            (
                throw ("Max 源模型基础对象不是 Editable Poly / Editable Mesh，而是 " + baseName)
            )
        )
        catch
        (
            local writeError = getCurrentException()
            local rollbackOk = false
            local rollbackError = ""
            if not writeStarted then
            (
                setLastMessage ("变形失败：" + writeError + "；尚未写入 Max 源模型基础对象。")
            )
            else
            (
                try
                (
                    local rollbackBaseObj = dst.baseObject
                    local rollbackBaseName = (classof rollbackBaseObj) as string
                    if rollbackBaseName != baseName do
                    (
                        rollbackError = "Max 源模型基础类型已改变。"
                        throw()
                    )
                    if baseName == "Editable_Poly" then
                    (
                        if originalVerts.count == 0 do
                        (
                            rollbackError = "没有可回滚的 Max 源模型点位快照。"
                            throw()
                        )
                        if (polyop.getNumVerts rollbackBaseObj) != originalVerts.count do
                        (
                            rollbackError = "回滚时点数已改变。"
                            throw()
                        )
                        for i = 1 to originalVerts.count do polyop.setVert rollbackBaseObj i originalVerts[i]
                        update dst
                        for i = 1 to originalVerts.count where not (pointsReadbackEqual (polyop.getVert rollbackBaseObj i) originalVerts[i]) do
                        (
                            local actual = polyop.getVert rollbackBaseObj i
                            local delta = distance actual originalVerts[i]
                            local tolerance = pointReadbackTolerance actual originalVerts[i]
                            rollbackError = (
                                "回滚后第 " + i as string + " 个点不一致；差值 " +
                                delta as string + "，允许 " + tolerance as string +
                                "，期望 " + originalVerts[i] as string +
                                "，实际 " + actual as string + "。"
                            )
                            throw()
                        )
                    )
                    else if baseName == "Editable_mesh" or baseName == "Editable Mesh" then
                    (
                        if originalMesh == undefined do
                        (
                            rollbackError = "没有可回滚的 Max 源模型基础 TriMesh 快照。"
                            throw()
                        )
                        rollbackBaseObj.mesh = originalMesh
                        update dst
                        try(if readbackMesh != undefined do free readbackMesh)catch()
                        readbackMesh = copy rollbackBaseObj.mesh
                        if (getNumVerts readbackMesh) != (getNumVerts originalMesh) do
                        (
                            rollbackError = "回滚后基础 TriMesh 点数不一致。"
                            throw()
                        )
                        for i = 1 to (getNumVerts originalMesh) where not
                            (pointsReadbackEqual (meshop.getVert readbackMesh i) (meshop.getVert originalMesh i)) do
                        (
                            local actual = meshop.getVert readbackMesh i
                            local expected = meshop.getVert originalMesh i
                            local delta = distance actual expected
                            local tolerance = pointReadbackTolerance actual expected
                            rollbackError = (
                                "回滚后第 " + i as string + " 个点不一致；差值 " +
                                delta as string + "，允许 " + tolerance as string +
                                "，期望 " + expected as string +
                                "，实际 " + actual as string + "。"
                            )
                            throw()
                        )
                    )
                    else
                    (
                        rollbackError = "Max 源模型基础类型已改变。"
                        throw()
                    )
                    rollbackBaseObj = undefined
                    rollbackOk = true
                )
                catch(if rollbackError == "" do rollbackError = getCurrentException())
                if rollbackOk then
                    setLastMessage ("变形失败：" + writeError + "；已完整回滚 Max 源模型原点位。")
                else
                    setLastMessage ("变形失败：" + writeError + "；Max 源模型点位回滚失败：" + rollbackError)
            )
            ok = false
        )
        if ok do setLastMessage ("变形完成：已写入并读回验证 " + (sourceCount as string) + " 个基础点。")
        try(if readbackMesh != undefined do free readbackMesh)catch()
        try(if workingMesh != undefined do free workingMesh)catch()
        try(if originalMesh != undefined do free originalMesh)catch()
        try(if srcMesh != undefined do free srcMesh)catch()
        baseObj = undefined
        ok
    ),

    fn captureBaseVertexPositions n =
    (
        local verts = #()
        local baseObj = undefined
        local copiedMesh = undefined
        local ok = false
        try
        (
            baseObj = n.baseObject
            local baseName = (classof baseObj) as string
            if baseName == "Editable_Poly" then
            (
                for i = 1 to (polyop.getNumVerts baseObj) do append verts (polyop.getVert baseObj i)
            )
            else if baseName == "Editable_mesh" or baseName == "Editable Mesh" then
            (
                copiedMesh = copy baseObj.mesh
                for i = 1 to (getNumVerts copiedMesh) do append verts (meshop.getVert copiedMesh i)
            )
            else
            (
                throw "基础对象类型不支持。"
            )
            ok = true
        )
        catch(ok = false)
        try(if copiedMesh != undefined do free copiedMesh)catch()
        baseObj = undefined
        if ok then verts else undefined
    ),

    fn restoreBaseVertexPositions n verts =
    (
        setLastMessage ""
        local baseObj = undefined
        local baseName = ""
        local originalVerts = #()
        local originalMesh = undefined
        local workingMesh = undefined
        local readbackMesh = undefined
        local writeStarted = false
        local ok = false
        try
        (
            if verts == undefined do throw "没有可恢复的 Max 源模型点位快照。"
            baseObj = n.baseObject
            baseName = (classof baseObj) as string
            if baseName == "Editable_Poly" then
            (
                if (polyop.getNumVerts baseObj) != verts.count do throw "Max 源模型点数已经变化，无法恢复原外形。"
                for i = 1 to verts.count do append originalVerts (polyop.getVert baseObj i)
                writeStarted = true
                for i = 1 to verts.count do polyop.setVert baseObj i verts[i]
                update n
                for i = 1 to verts.count where not (pointsReadbackEqual (polyop.getVert baseObj i) verts[i]) do
                    throw ("恢复后第 " + i as string + " 个基础点回读不一致。")
            )
            else if baseName == "Editable_mesh" or baseName == "Editable Mesh" then
            (
                originalMesh = copy baseObj.mesh
                if (getNumVerts originalMesh) != verts.count do throw "Max 源模型点数已经变化，无法恢复原外形。"
                workingMesh = copy originalMesh
                for i = 1 to verts.count do meshop.setVert workingMesh i verts[i]
                writeStarted = true
                baseObj.mesh = workingMesh
                try(free workingMesh)catch()
                workingMesh = undefined
                update n
                readbackMesh = copy baseObj.mesh
                if (getNumVerts readbackMesh) != verts.count do throw "恢复后基础 TriMesh 点数不一致。"
                for i = 1 to verts.count where not (pointsReadbackEqual (meshop.getVert readbackMesh i) verts[i]) do
                    throw ("恢复后第 " + i as string + " 个基础点回读不一致。")
            )
            else
            (
                throw ("Max 源模型基础对象不是 Editable Poly / Editable Mesh，而是 " + baseName)
            )
            ok = true
        )
        catch
        (
            local restoreError = getCurrentException()
            local rollbackOk = false
            local rollbackError = ""
            if writeStarted then
            (
                try
                (
                    local rollbackBaseObj = n.baseObject
                    local rollbackBaseName = (classof rollbackBaseObj) as string
                    if rollbackBaseName != baseName do
                    (
                        rollbackError = "基础对象类型已改变。"
                        throw()
                    )
                    if baseName == "Editable_Poly" then
                    (
                        if (polyop.getNumVerts rollbackBaseObj) != originalVerts.count do
                        (
                            rollbackError = "基础点数已改变。"
                            throw()
                        )
                        for i = 1 to originalVerts.count do polyop.setVert rollbackBaseObj i originalVerts[i]
                        update n
                        for i = 1 to originalVerts.count where not
                            (pointsReadbackEqual (polyop.getVert rollbackBaseObj i) originalVerts[i]) do
                        (
                            rollbackError = "基础点事务回滚读回不一致。"
                            throw()
                        )
                    )
                    else if baseName == "Editable_mesh" or baseName == "Editable Mesh" then
                    (
                        if originalMesh == undefined do
                        (
                            rollbackError = "没有基础 TriMesh 事务快照。"
                            throw()
                        )
                        rollbackBaseObj.mesh = originalMesh
                        update n
                        try(if readbackMesh != undefined do free readbackMesh)catch()
                        readbackMesh = copy rollbackBaseObj.mesh
                        if (getNumVerts readbackMesh) != (getNumVerts originalMesh) do
                        (
                            rollbackError = "基础 TriMesh 事务回滚点数不一致。"
                            throw()
                        )
                        for i = 1 to (getNumVerts originalMesh) where not
                            (pointsReadbackEqual (meshop.getVert readbackMesh i) (meshop.getVert originalMesh i)) do
                        (
                            rollbackError = "基础 TriMesh 事务回滚读回不一致。"
                            throw()
                        )
                    )
                    else
                    (
                        rollbackError = "基础对象类型已改变。"
                        throw()
                    )
                    rollbackBaseObj = undefined
                    rollbackOk = true
                )
                catch(if rollbackError == "" do rollbackError = getCurrentException())
            )
            if rollbackOk then
                setLastMessage ("恢复 Max 源模型外形失败：" + restoreError + "；已回滚本次恢复写入。")
            else if writeStarted then
                setLastMessage ("恢复 Max 源模型外形失败：" + restoreError + "；本次恢复写入回滚失败：" + rollbackError)
            else
                setLastMessage ("恢复 Max 源模型外形失败：" + restoreError + "；尚未写入基础对象。")
            ok = false
        )

        if ok do setLastMessage "已恢复 Max 源模型外形。"
        try(if readbackMesh != undefined do free readbackMesh)catch()
        try(if workingMesh != undefined do free workingMesh)catch()
        try(if originalMesh != undefined do free originalMesh)catch()
        baseObj = undefined
        ok
    ),

    fn copyMaterialIdsDirect src dst faceMap:#() =
    (
        setLastMessage ""
        local ok = false
        local snapshotType = ""
        local originalIds = #()
        try
        (
            if isPolyBase src and isPolyBase dst then
            (
                local faceCount = polyop.getNumFaces src
                if (polyop.getNumFaces dst) != faceCount do throw "FBX 目标与 Max 源的 Editable Poly 多边形数量不一致，不能直接写入材质 ID。"
                snapshotType = "poly"
                for f = 1 to faceCount do append originalIds (polyop.getFaceMatID dst f)
                local faceSet = #{}
                for f = 1 to faceCount do
                (
                    if f > 1 do faceSet[f - 1] = false
                    faceSet[f] = true
                    local sourceFace = mappedSourceFace faceMap f
                    if sourceFace < 1 or sourceFace > faceCount do throw ("第 " + f as string + " 个 Max 源面映射到越界 FBX 目标面。")
                    polyop.setFaceMatID dst faceSet (polyop.getFaceMatID src sourceFace)
                )
                update dst
                for f = 1 to faceCount do
                (
                    local sourceFace = mappedSourceFace faceMap f
                    if (polyop.getFaceMatID dst f) != (polyop.getFaceMatID src sourceFace) do
                        throw ("第 " + f as string + " 面材质 ID 写后回读不一致。")
                )
                setLastMessage ("材质 ID：已按 Editable Poly 多边形直接写入 Max 源模型的 " + (faceCount as string) + " 个面，没有改变外形。")
                ok = true
            )
            else if isMeshBase src and isMeshBase dst then
            (
                local srcMesh = src.mesh
                local faceCount = getNumFaces srcMesh
                if (getNumFaces dst) != faceCount do throw "FBX 目标与 Max 源的 Editable Mesh 面数量不一致，不能直接写入材质 ID。"
                snapshotType = "mesh"
                for f = 1 to faceCount do append originalIds (getFaceMatID dst f)
                for f = 1 to faceCount do
                (
                    local sourceFace = mappedSourceFace faceMap f
                    if sourceFace < 1 or sourceFace > faceCount do throw ("第 " + f as string + " 个 Max 源面映射到越界 FBX 目标面。")
                    setFaceMatID dst f (getFaceMatID srcMesh sourceFace)
                )
                update dst
                for f = 1 to faceCount do
                (
                    local sourceFace = mappedSourceFace faceMap f
                    if (getFaceMatID dst f) != (getFaceMatID srcMesh sourceFace) do
                        throw ("第 " + f as string + " 面材质 ID 写后回读不一致。")
                )
                setLastMessage ("材质 ID：已按 Editable Mesh 面直接写入 Max 源模型的 " + (faceCount as string) + " 个面，没有改变外形。")
                ok = true
            )
            else
            (
                throw "FBX 目标与 Max 源的基础类型不是同类 Editable Poly 或同类 Editable Mesh。"
            )
        )
        catch
        (
            local writeError = getCurrentException()
            local rollbackOk = snapshotType == ""
            local rollbackError = ""
            try
            (
                if snapshotType == "poly" then
                (
                    if (polyop.getNumFaces dst) != originalIds.count then
                    (
                        rollbackError = "回滚时 Max 源模型面数已改变。"
                        throw()
                    )
                    local faceSet = #{}
                    for f = 1 to originalIds.count do
                    (
                        if f > 1 do faceSet[f - 1] = false
                        faceSet[f] = true
                        polyop.setFaceMatID dst faceSet originalIds[f]
                    )
                    update dst
                    rollbackOk = true
                    for f = 1 to originalIds.count where (polyop.getFaceMatID dst f) != originalIds[f] do rollbackOk = false
                )
                else if snapshotType == "mesh" then
                (
                    if (getNumFaces dst) != originalIds.count then
                    (
                        rollbackError = "回滚时 Max 源模型面数已改变。"
                        throw()
                    )
                    for f = 1 to originalIds.count do setFaceMatID dst f originalIds[f]
                    update dst
                    rollbackOk = true
                    for f = 1 to originalIds.count where (getFaceMatID dst f) != originalIds[f] do rollbackOk = false
                )
            )
            catch
            (
                if rollbackError == "" do rollbackError = getCurrentException()
                rollbackOk = false
            )
            if rollbackOk then
                setLastMessage ("材质 ID：直接按面写入不可用：" + writeError + "；已回滚 Max 源模型原材质 ID。")
            else
                setLastMessage ("材质 ID：直接按面写入失败：" + writeError + "；Max 源模型原材质 ID 回滚失败：" + rollbackError)
            ok = false
        )
        ok
    ),

    fn copyMaterialIds src dst faceMap:#() =
    (
        local directOk = copyMaterialIdsDirect src dst faceMap:faceMap
        if directOk do return true

        local directMsg = lastMessage
        if faceMap != undefined and faceMap.count > 0 then
        (
            for targetFace = 1 to faceMap.count where faceMap[targetFace] != targetFace do
            (
                setLastMessage ("材质 ID：直接映射写入失败；" + directMsg + "；面序存在映射，不能退回到不支持面映射的 ChannelInfo。")
                return false
            )
        )
        local savedVerts = captureBaseVertexPositions dst
        if savedVerts == undefined do
        (
            setLastMessage ("材质 ID：直接写入失败；" + directMsg + "；Max 源模型基础对象无法记录原点位，已停止，避免模型变形。")
            return false
        )

        try
        (
            local beforeMods = for m in dst.modifiers collect m
            -- ChannelInfo 类型 1 对应多边形数据；用它复制面材质 ID，等同于手动通道信息工具复制 Polygon。
            ChannelInfo.CopyChannel src 1 0
            ChannelInfo.PasteChannel dst 1 0
            local afterMods = for m in dst.modifiers collect m
            local pastedMod = undefined
            try
            (
                pastedMod = findNewModifier beforeMods afterMods
                if pastedMod != undefined do pastedMod.name = "F2M_粘贴多边形材质ID"
            )
            catch()
            ChannelInfo.update()
            update dst

            if pastedMod != undefined then
            (
                local collapseOk = collapseModifierSafely dst pastedMod
                local collapseMsg = lastMessage
                if collapseOk then
                (
                    local restoreOk = restoreBaseVertexPositions dst savedVerts
                    local restoreMsg = lastMessage
                    if not restoreOk do throw restoreMsg
                    setLastMessage ("材质 ID：已通过 ChannelInfo 多边形通道复制并塌陷；" + collapseMsg + "；已恢复 Max 源模型外形。")
                )
                else
                (
                    try(deleteModifier dst pastedMod)catch()
                    local restoreOk = restoreBaseVertexPositions dst savedVerts
                    local restoreMsg = lastMessage
                    if restoreOk then
                    (
                        setLastMessage ("材质 ID：ChannelInfo 已粘贴，但未能安全塌陷，已删除临时修改器并恢复 Max 源模型外形；" + collapseMsg)
                    )
                    else
                    (
                        setLastMessage ("材质 ID：ChannelInfo 已粘贴，但未能安全塌陷；删除临时修改器后仍无法恢复外形：" + restoreMsg + "；" + collapseMsg)
                    )
                    return false
                )
            )
            else
            (
                local restoreOk = restoreBaseVertexPositions dst savedVerts
                local restoreMsg = lastMessage
                if not restoreOk do throw restoreMsg
                setLastMessage "材质 ID：已通过 ChannelInfo 多边形通道复制；已恢复 Max 源模型外形。"
            )
            true
        )
        catch
        (
            local err = getCurrentException()
            local restoreText = ""
            try
            (
                if restoreBaseVertexPositions dst savedVerts do restoreText = "；已恢复 Max 源模型外形"
            )
            catch()
            setLastMessage ("材质 ID：ChannelInfo 多边形通道复制失败：" + err + restoreText)
            false
        )
    ),

    fn commandPanelModeName =
    (
        try((getCommandPanelTaskMode()) as string)catch("")
    ),

    fn releaseModifierPanelReference =
    (
        try
        (
            try(subObjectLevel = 0)catch()
            local previousObject = undefined
            local previousHandle = undefined
            try(previousObject = modPanel.getCurrentObject())catch()
            if previousObject != undefined do
                try(previousHandle = getHandleByAnim previousObject)catch()
            previousObject = undefined
            setCommandPanelTaskMode #create
            local currentObject = undefined
            local currentHandle = undefined
            local queryOk = true
            try(currentObject = modPanel.getCurrentObject())catch(queryOk = false)
            if queryOk and currentObject != undefined do
                try(currentHandle = getHandleByAnim currentObject)catch(queryOk = false)
            currentObject = undefined
            queryOk and
                (getCommandPanelTaskMode()) == #create and
                (previousHandle == undefined or currentHandle != previousHandle)
        )
        catch false
    ),

    fn restoreCommandPanelMode modeText =
    (
        local cleanMode = toLower (modeText as string)
        local panelMode = case cleanMode of
        (
            "create": #create
            "modify": #modify
            "hierarchy": #hierarchy
            "motion": #motion
            "display": #display
            "utility": #utility
            default: undefined
        )
        if panelMode == undefined then false
        else try
        (
            setCommandPanelTaskMode panelMode
            (getCommandPanelTaskMode()) == panelMode
        )
        catch false
    ),

    fn detachModifierPanelFromNodeIfNeeded n =
    (
        try(subObjectLevel = 0)catch()
        local currentObject = undefined
        local belongsToNode = false
        local queryOk = true
        try(currentObject = modPanel.getCurrentObject())catch(queryOk = false)
        if not queryOk do
        (
            setLastMessage "无法读取 Modify 面板当前对象；已跳过节点删除。"
            return false
        )
        if currentObject == undefined then true
        else
        (
            local membershipOk = true
            try(
                local currentHandle = getHandleByAnim currentObject
                local baseHandle = getHandleByAnim n.baseObject
                belongsToNode =
                    (currentHandle != undefined and
                     baseHandle != undefined and
                     currentHandle == baseHandle) or
                    (modifierIndex n currentObject != undefined)
            )catch(membershipOk = false)
            currentObject = undefined
            if not membershipOk do
            (
                setLastMessage "无法确认 Modify 面板当前对象是否属于待删节点；已跳过节点删除。"
                return false
            )
            if not belongsToNode then true
            else
            (
                try(setCommandPanelTaskMode #create)catch()
                queryOk = true
                try(currentObject = modPanel.getCurrentObject())catch(queryOk = false)
                if not queryOk do
                (
                    setLastMessage "切换命令面板后无法验证当前对象；已跳过节点删除。"
                    return false
                )
                local stillOwned = false
                membershipOk = true
                if currentObject != undefined do
                    try(
                        local afterCurrentHandle = getHandleByAnim currentObject
                        local afterBaseHandle = getHandleByAnim n.baseObject
                        stillOwned =
                            (afterCurrentHandle != undefined and
                             afterBaseHandle != undefined and
                             afterCurrentHandle == afterBaseHandle) or
                            (modifierIndex n currentObject != undefined)
                    )catch(membershipOk = false)
                currentObject = undefined
                if not membershipOk then
                (
                    setLastMessage "切换命令面板后无法确认待删节点已经解绑；已跳过节点删除。"
                    false
                )
                else if stillOwned then false
                else true
            )
        )
    ),

    fn removeModifierByAnimHandle n modifierHandle =
    (
        try(subObjectLevel = 0)catch()
        local ok = false
        local modInst = undefined
        local stackIndex = undefined
        try(modInst = getAnimByHandle modifierHandle)catch(modInst = undefined)
        if modInst == undefined do
        (
            setLastMessage "无法按句柄重新解析待删除修改器；已停止删除。"
            return false
        )
        try(stackIndex = modifierIndex n modInst)catch(stackIndex = undefined)
        if stackIndex == undefined do
        (
            setLastMessage "按句柄解析到的修改器不属于目标节点；已停止删除。"
            modInst = undefined
            return false
        )
        local currentObject = undefined
        local currentQueryOk = true
        try(currentObject = modPanel.getCurrentObject())catch(currentQueryOk = false)
        if not currentQueryOk do
        (
            setLastMessage "无法读取 Modify 面板当前对象；已跳过修改器删除。"
            modInst = undefined
            return false
        )
        local currentHandle = undefined
        local currentHandleOk = true
        if currentObject != undefined do
            try(currentHandle = getHandleByAnim currentObject)catch(currentHandleOk = false)
        if not currentHandleOk do
        (
            setLastMessage "无法读取 Modify 面板当前对象句柄；已跳过修改器删除。"
            currentObject = undefined
            modInst = undefined
            return false
        )
        if currentHandle == modifierHandle do
        (
            -- Only detach the exact modifier that is about to die.  Prefer the
            -- same node's surviving base object so the user's Modify-panel
            -- context remains meaningful; #create is a narrow fallback.
            local survivor = undefined
            try(survivor = n.baseObject)catch(survivor = undefined)
            if survivor != undefined do
                try(modPanel.setCurrentObject survivor)catch()
            survivor = undefined
            currentObject = undefined
            currentHandle = undefined
            currentQueryOk = true
            try(currentObject = modPanel.getCurrentObject())catch(currentQueryOk = false)
            if not currentQueryOk do
            (
                setLastMessage "切换 Modify 面板对象后无法验证解绑；已跳过修改器删除。"
                modInst = undefined
                return false
            )
            currentHandleOk = true
            if currentObject != undefined do
                try(currentHandle = getHandleByAnim currentObject)catch(currentHandleOk = false)
            if not currentHandleOk do
            (
                setLastMessage "切换 Modify 面板对象后无法读取句柄；已跳过修改器删除。"
                currentObject = undefined
                modInst = undefined
                return false
            )
            if currentHandle == modifierHandle do
            (
                try(setCommandPanelTaskMode #create)catch()
                currentObject = undefined
                currentHandle = undefined
                currentQueryOk = true
                try(currentObject = modPanel.getCurrentObject())catch(currentQueryOk = false)
                if not currentQueryOk do
                (
                    setLastMessage "切换命令面板后无法验证修改器解绑；已跳过删除。"
                    modInst = undefined
                    return false
                )
                currentHandleOk = true
                if currentObject != undefined do
                    try(currentHandle = getHandleByAnim currentObject)catch(currentHandleOk = false)
                if not currentHandleOk do
                (
                    setLastMessage "切换命令面板后无法读取当前对象句柄；已跳过删除。"
                    currentObject = undefined
                    modInst = undefined
                    return false
                )
            )
            if currentHandle == modifierHandle do
            (
                setLastMessage "无法解除 Modify 面板对待删除修改器的当前引用；已停止删除。"
                currentObject = undefined
                modInst = undefined
                return false
            )
        )
        currentObject = undefined
        currentHandle = undefined
        local verifiedMod = undefined
        local verifiedIndex = undefined
        try(verifiedMod = getAnimByHandle modifierHandle)catch()
        try(verifiedIndex = modifierIndex n verifiedMod)catch()
        verifiedMod = undefined
        if verifiedIndex == undefined or verifiedIndex != stackIndex do
        (
            setLastMessage "待删修改器的栈位置在删除前发生变化；已停止删除。"
            modInst = undefined
            return false
        )
        -- The caller has already cleared its alias.  Delete by the stable stack
        -- index rather than passing a doomed wrapper.  Never force garbage
        -- collection in a user operation; Max may still be unwinding native
        -- modifier state.
        modInst = undefined
        try
        (
            deleteModifier n stackIndex
            ok = true
        )
        catch
        (
            ok = false
        )
        local leftoverMod = undefined
        local leftoverIndex = undefined
        try(leftoverMod = getAnimByHandle modifierHandle)catch()
        try(leftoverIndex = modifierIndex n leftoverMod)catch()
        leftoverMod = undefined
        if leftoverIndex != undefined do ok = false
        modInst = undefined
        stackIndex = undefined
        ok
    ),

    fn removeModifierInstance n modInst =
    (
        local modifierHandle = undefined
        try(modifierHandle = getHandleByAnim modInst)catch(modifierHandle = undefined)
        modInst = undefined
        if modifierHandle == undefined then false
        else removeModifierByAnimHandle n modifierHandle
    ),

    fn safeDeleteNodeArray nodes =
    (
        try(delete nodes)catch()
        true
    ),

    fn deleteNodesByHandles handles =
    (
        setLastMessage ""
        local failures = #()
        local parkedPanelHandle = undefined
        local panelObject = undefined
        local panelParkOk = true
        try(panelObject = modPanel.getCurrentObject())catch(panelParkOk = false)
        if panelParkOk and panelObject != undefined and
           classof panelObject == Edit_Normals do
        (
            try(parkedPanelHandle = getHandleByAnim panelObject)catch(panelParkOk = false)
            try(subObjectLevel = 0)catch()
            panelObject = undefined
            try(setCommandPanelTaskMode #create)catch(panelParkOk = false)
            if panelParkOk do
            (
                local afterParkObject = undefined
                local afterParkHandle = undefined
                try(afterParkObject = modPanel.getCurrentObject())catch(panelParkOk = false)
                if panelParkOk and afterParkObject != undefined do
                    try(afterParkHandle = getHandleByAnim afterParkObject)catch(panelParkOk = false)
                afterParkObject = undefined
                if afterParkHandle == parkedPanelHandle do panelParkOk = false
            )
        )
        panelObject = undefined
        if not panelParkOk do
            append failures "无法在批量删除临时节点前停靠 Edit Normals 面板对象"
        for handleValue in handles do
        (
            local nodeValue = undefined
            try(nodeValue = getAnimByHandle handleValue)catch()
            if nodeValue != undefined and isValidNode nodeValue do
            (
                local normalHandles = #()
                local normalScanOk = true
                local modifierValue = undefined
                try
                (
                    for modifierIndexValue = nodeValue.modifiers.count to 1 by -1 do
                    (
                        modifierValue = nodeValue.modifiers[modifierIndexValue]
                        if classof modifierValue == Edit_Normals do
                        (
                            local normalHandle = undefined
                            try(normalHandle = getHandleByAnim modifierValue)catch()
                            if normalHandle == undefined then
                                normalScanOk = false
                            else
                                append normalHandles normalHandle
                        )
                        modifierValue = undefined
                    )
                )
                catch
                (
                    modifierValue = undefined
                    normalScanOk = false
                )
                modifierValue = undefined
                local normalCleanupOk = normalScanOk
                for normalHandle in normalHandles do
                (
                    if normalCleanupOk and
                       not (removeModifierByAnimHandle nodeValue normalHandle) do
                        normalCleanupOk = false
                )
                normalHandles = #()
                if not normalCleanupOk then
                (
                    append failures (
                        (handleValue as string) +
                        "：无法在删除节点前安全移除 Edit Normals"
                    )
                )
                else if not (detachModifierPanelFromNodeIfNeeded nodeValue) then
                (
                    append failures (
                        (handleValue as string) +
                        "：无法解除 Modify 面板对待删节点的当前引用"
                    )
                )
                else try
                (
                    nodeValue = undefined
                    delete (getAnimByHandle handleValue)
                )
                catch
                (
                    append failures (
                        (handleValue as string) + "：" + getCurrentException()
                    )
                )
            )
            -- MAXScript has no finally clause.  This unconditional assignment
            -- is the finally-style release: never retain a deleted Node
            -- MAXWrapper while resolving or deleting the next handle.
            nodeValue = undefined
        )

        if parkedPanelHandle != undefined do
        (
            local restorePanelObject = undefined
            try(restorePanelObject = getAnimByHandle parkedPanelHandle)catch()
            if restorePanelObject != undefined do
            (
                local restored = false
                try
                (
                    setCommandPanelTaskMode #modify
                    modPanel.setCurrentObject restorePanelObject
                    restored = (getHandleByAnim (modPanel.getCurrentObject())) ==
                        parkedPanelHandle
                )
                catch(restored = false)
                if not restored do
                    append failures "临时节点删除后无法按句柄恢复原 Edit Normals 面板对象"
            )
            restorePanelObject = undefined
        )

        local leftovers = #()
        for handleValue in handles do
        (
            local nodeValue = undefined
            try(nodeValue = getAnimByHandle handleValue)catch()
            if nodeValue != undefined and isValidNode nodeValue do
                append leftovers handleValue
            nodeValue = undefined
        )
        if failures.count > 0 do
            setLastMessage ("逐句柄删除临时节点失败：" + (failures as string))
        leftovers
    ),

    fn nodeStateWarnings n =
    (
        local out = #()
        try
        (
            if isGroupHead n do append out "对象是组头：请先在 Group 菜单里 Open/Explode 或选择组内真实网格后再处理。"
        )
        catch()
        try
        (
            if isGroupMember n do append out "对象在组内：请先 Group > Open，或 Detach/Explode 后再处理。"
        )
        catch()
        try
        (
            if n.isFrozen do append out "对象被冻结：请先右键对象解除 Freeze/Unfreeze All 后再处理。"
        )
        catch()
        try
        (
            local vc = n.visibility.controller
            if vc != undefined then
            (
                local vcName = (classof vc) as string
                if matchPattern vcName pattern:"*LOD*" ignoreCase:true do append out "对象带有 LOD 可见性控制器：请先在 Utilities > Level Of Detail 中移除 LOD，必要时删除 Visibility 里的 LOD Controller。"
            )
        )
        catch()
        try
        (
            local instances = #()
            local instanceCount = InstanceMgr.GetInstances n &instances
            if instanceCount > 1 do append out ("对象是实例，共 " + instanceCount as string + " 个实例会共享基础对象；为避免改到未选实例，本次已阻断。")
        )
        catch()
        try
        (
            local baseName = (classof n.baseObject) as string
            if matchPattern baseName pattern:"*XRef*" ignoreCase:true do append out "对象来自 XRef/外部引用，不能安全直接改写基础网格。"
        )
        catch()
        try
        (
            if objXRefMgr.IsNodeXRefed n do
            (
                local xrefMessage = "对象来自 XRef/外部引用，不能安全直接改写基础网格。"
                if (findItem out xrefMessage) == 0 do append out xrefMessage
            )
        )
        catch()
        out
    )
)

F2M_TopologyHelper = F2M_TopologyHelperStruct()
F2M_Helper = F2M_TopologyHelper
'''


@dataclass
class SceneRecord:
    handle: int
    original_name: str
    temp_name: str
    node: Any
    renamed: bool = False
    skip_restore: bool = False


@dataclass
class TransferOptions:
    fbx_path: str
    mode: str = "auto"  # auto / topology_only / replace
    dry_run: bool = False
    transfer_shape: bool = True
    transfer_uv: bool = True
    uv_channels: List[int] = field(default_factory=lambda: [1])
    transfer_normals: bool = False
    transfer_smoothing_groups: bool = False
    transfer_vertex_color: bool = False
    transfer_alpha: bool = False
    transfer_material_ids: bool = False
    keep_imported: bool = False
    backup_old_mesh: bool = True
    include_hidden: bool = True
    keep_target_material_on_replace: bool = False
    limit_to_selection: bool = False
    show_ui: bool = True


@dataclass
class ObjectReport:
    name: str
    status: str
    messages: List[str] = field(default_factory=list)
    diagnostics: List[str] = field(default_factory=list)

    def add(self, text: str) -> None:
        self.messages.append(text)

    def add_exception(self, text: str, exc: BaseException) -> None:
        self.messages.append(text + visible_exception_text(exc))
        self.diagnostics.append(traceback.format_exc().strip() or repr(exc))


@dataclass(frozen=True)
class SmoothingNormalBaseline:
    """Pure-Python SG-evaluated corner-normal data from the first FBX import."""

    faces: Tuple[Tuple[int, ...], ...]
    fan_ids: Tuple[Tuple[int, ...], ...]
    corner_normals: Tuple[Tuple[Tuple[float, float, float], ...], ...]
    object_transform: Tuple[float, ...]
    explicit_count: int
    specified_count: int


@dataclass(frozen=True)
class IsolatedSmoothingMeshData:
    """Small, validated result returned by the out-of-process FBX resolver."""

    face_count: int
    corner_count: int
    topology_sha256: str
    masks: Tuple[int, ...]
    native: bool
    method: str
    solver_stats: Dict[str, Any]


@dataclass(frozen=True)
class TopologyMap:
    """FBX 目标模型面角到 Max 源模型面角的无歧义映射。

    数组均为 Python 0-based：第 ``max_face`` 个 Max 面从
    ``fbx_face_for_max_face[max_face]`` 读取；每个 Max 面角再从对应的
    ``fbx_corner_for_max_corner`` 读取 FBX 面角数据。
    """

    fbx_face_for_max_face: Tuple[int, ...]
    fbx_corner_for_max_corner: Tuple[Tuple[int, ...], ...]
    exact_face_count: int
    cyclic_corner_face_count: int
    reordered_face_count: int
    evaluated_triangle_difference_count: int = 0

    @property
    def face_count(self) -> int:
        return len(self.fbx_face_for_max_face)

    @property
    def has_non_identity_mapping(self) -> bool:
        if self.reordered_face_count or self.cyclic_corner_face_count:
            return True
        return any(
            source_face != max_face
            for max_face, source_face in enumerate(self.fbx_face_for_max_face)
        )

    @property
    def triangulation_warning(self) -> str:
        if self.evaluated_triangle_difference_count < 1:
            return ""
        return (
            "基础多边形及面角映射一致，但最终评估三角面有 "
            f"{self.evaluated_triangle_difference_count} 个索引结果不同；"
            "这通常表示 Editable Poly 隐藏对角线不同。模式一仍按顶点和"
            "多边形面角安全传递，Max 源模型会保留自身隐藏三角剖分。"
        )


class TransferLog:
    def __init__(self) -> None:
        self.lines: List[str] = []

    def add(self, text: str = "") -> None:
        self.lines.append(text)
        if rt is not None:
            try:
                rt.format("%\n", _display_text(text))
            except Exception:
                pass

    def extend(self, items: Iterable[str]) -> None:
        for item in items:
            self.add(item)

    def text(self) -> str:
        return "\n".join(self.lines)


class TransferContext:
    def __init__(self, options: TransferOptions, log: TransferLog) -> None:
        self.options = options
        self.log = log
        self.run_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        self.prefix = f"__F2M_SCENE_{self.run_id}_"
        self.import_prefix = f"__F2M_SRC_{self.run_id}_"
        self.scene_records: List[SceneRecord] = []
        self.scene_by_original: Dict[str, List[SceneRecord]] = {}
        self.pre_handles: Set[int] = set()
        self.imported_nodes: List[Any] = []
        self.keep_imported_nodes: Set[int] = set()
        self.replacement_nodes: Set[int] = set()
        self.imported_bone_names: Dict[int, str] = {}
        self.smoothing_masks_by_name: Dict[str, List[int]] = {}
        self.smoothing_faces_by_name: Dict[str, List[List[int]]] = {}
        self.smoothing_normal_baselines_by_name: Dict[
            str, SmoothingNormalBaseline
        ] = {}
        self.initial_smoothing_masks_by_handle: Dict[int, List[int]] = {}
        self.existing_smoothing_masks_by_handle: Dict[int, List[int]] = {}
        self.normal_residual_notice_objects: Set[str] = set()
        self.native_smoothing_by_name: Dict[str, bool] = {}
        self.fbx_mesh_data_by_name: Dict[str, Any] = {}
        self.smoothing_method_by_name: Dict[str, str] = {}
        self.resolver_topology_by_name: Dict[
            str, Tuple[int, int, str]
        ] = {}
        self.resolver_input_size: Optional[int] = None
        self.resolver_input_mtime_ns: Optional[int] = None
        self.resolver_input_sha256: str = ""
        self.missing_transfer_attrs: List[str] = []
        self.reports: List[ObjectReport] = []
        self.safety_errors: List[str] = []
        self.diagnostics: List[str] = []


def ensure_runtime() -> None:
    if rt is None:
        raise RuntimeError("这个脚本需要在 3ds Max 的 Python 环境中运行。")
    helper_ready = False
    try:
        helper = rt.F2M_TopologyHelper
        helper_ready = (
            str(helper.apiKind) == "topology"
            and str(helper.apiVersion) == TOOL_VERSION
        )
    except Exception:
        helper_ready = False
    if not helper_ready:
        rt.execute(HELPER_SCRIPT)
        try:
            helper = rt.F2M_TopologyHelper
            helper_ready = (
                str(helper.apiKind) == "topology"
                and str(helper.apiVersion) == TOOL_VERSION
            )
        except Exception:
            helper_ready = False
    if not helper_ready:
        raise RuntimeError("拓扑传递运行核心没有正确注册，请重新安装插件。")
    rt.globalVars.set(rt.Name("F2M_Helper"), helper)


def _load_local_runtime_module(filename: str, module_name: str) -> Any:
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), filename))
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    existing = sys.modules.get(module_name)
    if existing is not None:
        existing_path = os.path.abspath(str(getattr(existing, "__file__", "")))
        if (
            os.path.normcase(existing_path) == os.path.normcase(path)
            and str(getattr(existing, "TOOL_VERSION", "")) == TOOL_VERSION
            and getattr(existing, "_F2M_IMPORT_COMPLETE", False) is True
        ):
            return existing
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法创建运行模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if sys.modules.get(module_name) is module:
            sys.modules.pop(module_name, None)
        raise
    setattr(module, "_F2M_IMPORT_COMPLETE", True)
    return module


def node_handle(node: Any) -> int:
    return int(rt.getHandleByAnim(node))


def max_array(items: Sequence[Any]) -> Any:
    # pymxs 通常可以自动把 Python list 转为 MAXScript Array。
    # 单独封装，方便后续如果某个 Max 版本需要替换为 rt.Array。
    return list(items)


def all_scene_nodes() -> List[Any]:
    try:
        return list(rt.objects)
    except Exception:
        return []


def node_by_handle(handle: int) -> Optional[Any]:
    try:
        node = rt.getAnimByHandle(int(handle))
    except Exception:
        return None
    return node if is_valid_node(node) else None


def is_valid_node(node: Any) -> bool:
    if node is None:
        return False
    native_predicate = None
    try:
        native_predicate = getattr(rt, "isValidNode", None)
    except Exception:
        native_predicate = None
    if callable(native_predicate):
        try:
            # Max's native predicate is specifically designed to accept
            # wrappers whose scene object may already have been deleted.
            # Never dereference ``node.name`` after this predicate raises:
            # even a caught MXSWrapperBase access can poison Max.log and the
            # native MAXScript garbage collector.
            return bool(native_predicate(node))
        except Exception:
            return False
    try:
        # Compatibility fallback for ordinary-Python test doubles only.
        # Supported 3ds Max 2023+ hosts always use the native predicate above.
        _ = node.name
        return True
    except Exception:
        return False


def is_max_undefined(value: Any) -> bool:
    return value is None or str(value) == "undefined"


def is_geometry_node(node: Any) -> bool:
    try:
        return bool(rt.F2M_Helper.isGeometryNode(node))
    except Exception:
        return False


def find_skin(node: Any) -> Optional[Any]:
    try:
        skin = rt.F2M_Helper.findSkin(node)
        if skin is None or str(skin) == "undefined":
            return None
        return skin
    except Exception:
        return None


def mesh_counts(node: Any) -> Tuple[int, int, int]:
    values = list(rt.F2M_Helper.meshCounts(node))
    if len(values) < 3:
        raise RuntimeError(f"无法读取网格统计：{getattr(node, 'name', '<unknown>')}")
    counts = (int(values[0]), int(values[1]), int(values[2]))
    if counts[0] < 1 or counts[2] < 1:
        raise RuntimeError(
            f"网格统计无效：{getattr(node, 'name', '<unknown>')} "
            f"(点 {counts[0]} / 边 {counts[1]} / 面 {counts[2]})"
        )
    if counts[1] < 1:
        edges: Set[Tuple[int, int]] = set()
        for face in _base_topology_faces(node):
            for corner, first in enumerate(face):
                second = face[(corner + 1) % len(face)]
                edges.add(tuple(sorted((first, second))))
        counts = (counts[0], len(edges), counts[2])
    return counts


def normalize_name(name: str) -> str:
    text = str(name).strip()
    if "|" in text:
        text = text.split("|")[-1]
    if ":" in text:
        text = text.split(":")[-1]
    text = re.sub(r"\.\d{3}$", "", text)
    return text.lower()


def unique_temp_name(prefix: str, index: int, original: str) -> str:
    safe_original = str(original)
    return f"{prefix}{index:05d}__{safe_original}"


def register_record(ctx: TransferContext, record: SceneRecord) -> None:
    ctx.scene_records.append(record)
    ctx.scene_by_original.setdefault(record.original_name, []).append(record)


def prepare_scene_names(ctx: TransferContext) -> None:
    scene_nodes = [node for node in all_scene_nodes() if is_valid_node(node)]
    ctx.pre_handles = {node_handle(node) for node in scene_nodes}
    scene_nodes.clear()
    selected_nodes: List[Any] = []
    seen_handles: Set[int] = set()
    for node in list(rt.selection):
        if not is_valid_node(node) or not is_geometry_node(node):
            continue
        handle = node_handle(node)
        if handle in seen_handles:
            continue
        selected_nodes.append(node)
        seen_handles.add(handle)
    for index, node in enumerate(selected_nodes, start=1):
        handle = node_handle(node)
        original = str(node.name)
        temp = unique_temp_name(ctx.prefix, index, original)
        record = SceneRecord(handle=handle, original_name=original, temp_name=temp, node=node)
        register_record(ctx, record)
        try:
            node.name = temp
            record.renamed = True
        except Exception as exc:
            message = f"节点无法临时改名，不能安全隔离 FBX 同名导入：{original}；{exc}"
            ctx.safety_errors.append(message)
            raise RuntimeError(message) from exc


def restore_scene_names(ctx: TransferContext) -> bool:
    failures: List[str] = []
    for record in ctx.scene_records:
        if record.skip_restore:
            continue
        if not record.renamed:
            continue
        node = node_by_handle(record.handle)
        if node is None:
            failures.append(
                f"{record.temp_name} -> {record.original_name}（原节点已失效）"
            )
            continue
        try:
            node.name = record.original_name
            record.node = node
            if str(node.name) != record.original_name:
                failures.append(f"{record.temp_name} -> {record.original_name}（读回不一致）")
        except Exception as exc:
            failures.append(f"{record.temp_name} -> {record.original_name}（{exc}）")
    if failures:
        message = "无法完整恢复场景节点名：" + "；".join(failures)
        ctx.safety_errors.append(message)
        ctx.log.add("错误：" + message)
        return False
    return True


def _valid_importer_value(value: Any) -> bool:
    text = str(value).strip().lower()
    return value is not None and text not in {"undefined", "unsupplied", "none"}


_BOOLEAN_IMPORTER_PARAMS = {"Animation", "Skin", "SmoothingGroups"}


def _snapshot_importer_value(name: str, value: Any) -> Any:
    """Keep Boolean FBX settings Boolean when they later cross into MAXScript."""

    if name not in _BOOLEAN_IMPORTER_PARAMS:
        return value
    text = str(value).strip().lower().lstrip("#")
    if text in {"true", "1", "1.0"}:
        return True
    if text in {"false", "0", "0.0"}:
        return False
    raise RuntimeError(f"FBX 导入器布尔参数 {name} 返回无效值：{value}")


def _snapshot_fbx_importer(ctx: TransferContext) -> Dict[str, Any]:
    try:
        rt.execute("pluginManager.loadClass FbxImporter")
    except Exception:
        pass

    snapshot: Dict[str, Any] = {}
    failures: List[str] = []
    for name in ("Mode", "Animation", "Skin", "SmoothingGroups"):
        try:
            value = rt.F2M_Helper.fbxImporterGet(name)
            if _valid_importer_value(value):
                snapshot[name] = _snapshot_importer_value(name, value)
            else:
                failures.append(name)
        except Exception as exc:
            failures.append(f"{name} ({exc})")
    if failures:
        raise RuntimeError(
            "无法读取并快照即将修改的 FBX 导入器全局参数，已停止以保护用户设置："
            + ", ".join(failures)
        )
    return snapshot


def _set_fbx_importer_param(name: str, value: Any) -> None:
    result = rt.F2M_Helper.fbxImporterSet(name, value)
    if not _valid_importer_value(result):
        raise RuntimeError(f"FBX 导入器拒绝参数 {name}={value}")
    readback = rt.F2M_Helper.fbxImporterGet(name)
    if not _importer_values_equal(name, value, readback):
        raise RuntimeError(
            f"FBX 导入参数 {name} 读回不一致：期望 {value}，实际 {readback}"
        )


def _normalized_importer_value(value: Any) -> str:
    """Return a stable representation for FBXImporter parameter readback."""

    text = str(value).strip().lower()
    if text.startswith("#"):
        text = text[1:]
    return text


def _importer_values_equal(name: str, expected: Any, actual: Any) -> bool:
    if not _valid_importer_value(actual):
        return False
    if name in _BOOLEAN_IMPORTER_PARAMS:
        expected_text = _normalized_importer_value(expected)
        actual_text = _normalized_importer_value(actual)
        aliases = {
            "true": True,
            "1": True,
            "1.0": True,
            "false": False,
            "0": False,
            "0.0": False,
        }
        if expected_text in aliases and actual_text in aliases:
            return aliases[expected_text] == aliases[actual_text]
    return _normalized_importer_value(expected) == _normalized_importer_value(actual)


def configure_fbx_import(ctx: TransferContext, smoothing_groups: bool) -> Dict[str, Any]:
    snapshot = _snapshot_fbx_importer(ctx)
    try:
        _set_fbx_importer_param("Mode", rt.Name("create"))
        _set_fbx_importer_param("Animation", False)
        # Mode 1 needs the FBX target's evaluated Skin result when the Max
        # receiver already has Skin: the node-level writer lets Max preserve
        # its native bind-space pre-compensation.  Fix Skin=True explicitly so
        # this mature behavior never depends on a user's previous FBX setting.
        # A dedicated top-of-stack Edit_Normals reader captures those evaluated
        # FBX face-corner directions; the destination still owns its persistent
        # plug-in modifier and full readback verification.
        _set_fbx_importer_param("Skin", True)
        _set_fbx_importer_param("SmoothingGroups", bool(smoothing_groups))
    except Exception as exc:
        _restore_fbx_importer(ctx, snapshot)
        raise RuntimeError(f"无法建立隔离、无动画的 FBX 导入设置：{exc}") from exc

    ctx.log.add("FBX 导入设置：导入模式=创建，动画=关闭，蒙皮=开启（读取求值网格/法线）。")
    if smoothing_groups:
        ctx.log.add("FBX 导入设置：导入光滑组=开启，由 Autodesk FBX 导入器从 FBX 目标的平滑信息/法线生成 Max 光滑组。")
    else:
        ctx.log.add("FBX 导入设置：导入光滑组=关闭，保留 FBX 显式/自定义法线。")
    return snapshot


def _restore_fbx_importer(ctx: TransferContext, snapshot: Dict[str, Any]) -> None:
    failures: List[str] = []
    for name, value in snapshot.items():
        try:
            result = rt.F2M_Helper.fbxImporterSet(name, value)
            if not _valid_importer_value(result):
                failures.append(name)
                continue
            readback = rt.F2M_Helper.fbxImporterGet(name)
            if not _importer_values_equal(name, value, readback):
                failures.append(
                    f"{name}（期望 {value!s}，读回 {readback!s}）"
                )
        except Exception:
            failures.append(name)
    if failures:
        message = "无法恢复 FBX 导入器全局参数：" + ", ".join(failures)
        ctx.safety_errors.append(message)
        raise RuntimeError(message)


def _new_nodes_since(handles: Set[int]) -> List[Any]:
    result: List[Any] = []
    for node in all_scene_nodes():
        if not is_valid_node(node):
            continue
        try:
            if node_handle(node) not in handles:
                result.append(node)
        except Exception:
            continue
    return result


def _exception_text_and_release(exc: BaseException) -> str:
    """Convert an exception to plain text and drop traceback-held wrappers."""

    text = str(exc).strip() or repr(exc)
    pending: List[BaseException] = [exc]
    seen: Set[int] = set()
    while pending:
        current = pending.pop()
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        cause = current.__cause__
        context = current.__context__
        if cause is not None:
            pending.append(cause)
        if context is not None:
            pending.append(context)
        try:
            if current.__traceback__ is not None:
                traceback.clear_frames(current.__traceback__)
            current.__traceback__ = None
        except Exception:
            pass
        try:
            current.__cause__ = None
            current.__context__ = None
        except Exception:
            pass
    return text


def _delete_handles_strict(
    handle_names: Dict[int, str],
    label: str,
) -> None:
    if not handle_names:
        return
    handles = sorted(int(handle) for handle in handle_names)
    try:
        raw_leftovers = rt.F2M_Helper.deleteNodesByHandles(max_array(handles))
        raw_values = (
            []
            if raw_leftovers is None or str(raw_leftovers) == "undefined"
            else list(raw_leftovers)
        )
        leftovers = {
            int(handle)
            for handle in raw_values
        }
    except Exception as exc:
        leftovers = set(handles)
        helper_detail = helper_message()
        failure = f"{label}批量删除失败：{visible_exception_text(exc)}"
        if helper_detail:
            failure += f"；{helper_detail}"
    else:
        failure = ""

    live_handles = {
        node_handle(node)
        for node in all_scene_nodes()
        if is_valid_node(node)
    }
    remaining = [
        handle_names[handle]
        for handle in handles
        if handle in live_handles
    ]
    failures = [text for text in (failure,) if text]
    if remaining:
        failures.append("仍存在：" + ", ".join(remaining))
    if failures:
        raise RuntimeError(f"{label}清理失败；" + "；".join(failures))


def _delete_nodes_strict(nodes: Iterable[Any], label: str) -> None:
    handle_names: Dict[int, str] = {}
    for node in nodes:
        if not is_valid_node(node):
            continue
        handle_names[node_handle(node)] = str(node.name)
    node = None
    # All current callers pass a list.  Clearing it before deletion prevents
    # the caller from retaining wrappers whose scene nodes are about to die.
    clear = getattr(nodes, "clear", None)
    if callable(clear):
        clear()
    _delete_handles_strict(handle_names, label)


def _import_fbx_once(ctx: TransferContext, smoothing_groups: bool) -> List[Any]:
    path = os.path.abspath(ctx.options.fbx_path)
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    previous_panel_mode = command_panel_mode_name()
    if not release_modifier_panel_reference():
        raise RuntimeError(
            "无法在 FBX 导入前安全停靠 Modify 面板；已阻止调用原生 FBX "
            "导入器，避免活动修改器跨越导入边界。"
        )
    ctx.log.add(
        "FBX 原生导入安全边界：已解除 Modify 面板当前对象并切换到 Create；"
        f"此前面板模式={previous_panel_mode or '未知'}。"
    )

    before = {node_handle(node) for node in all_scene_nodes() if is_valid_node(node)}
    escaped = path.replace("\\", "\\\\").replace('"', '\\"')
    snapshot = configure_fbx_import(ctx, smoothing_groups)
    import_error = ""
    tracking_error = ""
    restore_error = ""
    new_nodes: List[Any] = []
    try:
        import_result = rt.execute(f'importFile "{escaped}" #noPrompt')
        if import_result is False or str(import_result).strip().lower() == "false":
            raise RuntimeError("3ds Max 导入命令明确返回失败状态。")
    except BaseException as exc:
        import_error = _exception_text_and_release(exc)
    finally:
        try:
            new_nodes = _new_nodes_since(before)
            known_handles = {
                node_handle(node)
                for node in ctx.imported_nodes
                if is_valid_node(node)
            }
            for node in new_nodes:
                handle = node_handle(node)
                if handle not in known_handles:
                    ctx.imported_nodes.append(node)
                    known_handles.add(handle)
        except BaseException as exc:
            tracking_error = _exception_text_and_release(exc)
        finally:
            try:
                _restore_fbx_importer(ctx, snapshot)
            except BaseException as exc:
                restore_error = _exception_text_and_release(exc)

    if import_error or tracking_error or restore_error:
        parts: List[str] = []
        if import_error:
            parts.append(f"FBX 导入失败：{import_error}")
        if tracking_error:
            parts.append(f"跟踪临时导入节点失败：{tracking_error}")
        if restore_error:
            parts.append(f"FBX 导入器设置恢复失败：{restore_error}")
        new_nodes.clear()
        raise RuntimeError("；".join(parts)) from None
    if not new_nodes:
        raise RuntimeError("FBX 导入没有创建任何节点。")

    ctx.log.add(f"已导入 FBX：{path}")
    ctx.log.add(f"本次导入节点数量：{len(new_nodes)}")
    return new_nodes


def _capture_smoothing_masks(ctx: TransferContext, nodes: Iterable[Any]) -> None:
    captured: Dict[str, List[int]] = {}
    captured_faces: Dict[str, List[List[int]]] = {}
    for node in nodes:
        if not is_valid_node(node) or not is_geometry_node(node):
            continue
        name = str(node.name)
        if name in captured:
            raise RuntimeError(f"FBX 内存在重复网格名，无法安全对应光滑组：{name}")
        values = rt.F2M_Helper.getFaceSmoothingGroups(node)
        if values is None or str(values) == "undefined":
            raise RuntimeError(f"无法读取 Autodesk 导入结果的光滑组：{name}；{helper_message()}")
        masks = [int(value) for value in list(values)]
        if not masks:
            raise RuntimeError(f"Autodesk 导入结果没有可用的逐面光滑组数据：{name}")
        # 第一遍只负责取得 Autodesk/原生光滑组。直接读取基础拓扑，不为
        # 即将删除的临时节点新建、重建再删除 Edit Normals；真实 Max 2023
        # 门禁证明该多余生命周期与第二遍导入组合时会造成间歇性 GC 错误。
        faces = [list(face) for face in _base_topology_faces(node)]
        if len(faces) != len(masks):
            raise RuntimeError(
                f"Autodesk 光滑组导入的面数与面角拓扑不一致：{name}，"
                f"{len(masks)} / {len(faces)}"
            )
        captured[name] = masks
        captured_faces[name] = faces
    if not captured:
        raise RuntimeError("FBX 中没有可读取光滑组的几何节点。")
    ctx.smoothing_masks_by_name = captured
    ctx.smoothing_faces_by_name = captured_faces


def _snapshot_smoothing_input(
    node: Any,
) -> Tuple[
    List[List[int]],
    List[List[int]],
    List[List[Tuple[float, float, float]]],
    int,
    int,
]:
    raw = rt.F2M_Helper.snapshotSmoothingInputFlat(node)
    if raw is None or str(raw) == "undefined":
        raise RuntimeError(helper_message() or "无法读取 Edit Normals 面角数据。")
    parts = list(raw)
    if len(parts) != 6:
        raise RuntimeError("Edit Normals 扁平面角数据结构不完整。")
    face_degrees = [int(value) for value in list(parts[0])]
    vertex_ids = [int(value) for value in list(parts[1])]
    flat_fan_ids = [int(value) for value in list(parts[2])]
    normal_values = [float(value) for value in list(parts[3])]
    corner_count = sum(face_degrees)
    if (
        not face_degrees
        or any(degree < 3 for degree in face_degrees)
        or len(vertex_ids) != corner_count
        or len(flat_fan_ids) != corner_count
        or len(normal_values) != corner_count * 3
    ):
        raise RuntimeError("Edit Normals 扁平面、扇区与法线向量数量不一致。")
    faces: List[List[int]] = []
    fan_ids: List[List[int]] = []
    corner_normals: List[List[Tuple[float, float, float]]] = []
    corner_offset = 0
    normal_offset = 0
    for degree in face_degrees:
        next_corner = corner_offset + degree
        next_normal = normal_offset + degree * 3
        faces.append(vertex_ids[corner_offset:next_corner])
        fan_ids.append(flat_fan_ids[corner_offset:next_corner])
        values = normal_values[normal_offset:next_normal]
        corner_normals.append(
            [
                (values[index], values[index + 1], values[index + 2])
                for index in range(0, len(values), 3)
            ]
        )
        corner_offset = next_corner
        normal_offset = next_normal
    return faces, fan_ids, corner_normals, int(parts[4]), int(parts[5])


def _make_smoothing_normal_baseline(
    node: Any,
    name: str,
    faces: Sequence[Sequence[int]],
    fan_ids: Sequence[Sequence[int]],
    corner_normals: Sequence[Sequence[Sequence[float]]],
    explicit_count: int,
    specified_count: int,
) -> SmoothingNormalBaseline:
    if explicit_count != 0 or specified_count != 0:
        raise RuntimeError(
            f"{name} 的 Autodesk 光滑组导入不是纯 SG 基线："
            f"Explicit={explicit_count}，Specified={specified_count}；"
            "已在写入 Max 源模型前阻断。"
        )
    transform_raw = rt.F2M_Helper.nodeObjectTransformBuffer(node)
    if transform_raw is None or str(transform_raw) == "undefined":
        raise RuntimeError(f"无法快照纯 SG 法线基线的对象变换：{name}")
    transform_values = tuple(float(value) for value in list(transform_raw))
    if len(transform_values) != 12:
        raise RuntimeError(f"纯 SG 法线基线的对象变换不完整：{name}")
    return SmoothingNormalBaseline(
        faces=tuple(tuple(int(value) for value in face) for face in faces),
        fan_ids=tuple(
            tuple(int(value) for value in row) for row in fan_ids
        ),
        corner_normals=tuple(
            tuple(
                tuple(float(component) for component in normal)
                for normal in row
            )
            for row in corner_normals
        ),
        object_transform=transform_values,
        explicit_count=int(explicit_count),
        specified_count=int(specified_count),
    )


def _source_order_masks(
    target_masks: Sequence[int],
    mapping: TopologyMap,
) -> List[int]:
    if len(target_masks) != mapping.face_count:
        raise RuntimeError(
            "Max 源模型现有光滑组数量与拓扑映射面数不一致："
            f"{len(target_masks)}/{mapping.face_count}。"
        )
    source_masks: List[Optional[int]] = [None] * mapping.face_count
    for target_face, source_face in enumerate(
        mapping.fbx_face_for_max_face
    ):
        if source_face < 0 or source_face >= len(source_masks):
            raise RuntimeError("现有光滑组映射到了越界 FBX 面。")
        if source_masks[source_face] is not None:
            raise RuntimeError("现有光滑组面映射不是一一对应。")
        source_masks[source_face] = int(target_masks[target_face])
    if any(value is None for value in source_masks):
        raise RuntimeError("现有光滑组没有覆盖全部 FBX 面。")
    return [int(value) for value in source_masks if value is not None]


def _capture_existing_target_smoothing_baselines(
    ctx: TransferContext,
    nodes: Iterable[Any],
) -> None:
    captured: Dict[str, SmoothingNormalBaseline] = {}
    expected_names = {
        record.original_name
        for record in ctx.scene_records
        if record.handle in ctx.existing_smoothing_masks_by_handle
    }
    for node in nodes:
        if not is_valid_node(node) or not is_geometry_node(node):
            continue
        name = str(node.name)
        target_record = target_record_by_name(ctx, name)
        if (
            target_record is None
            or target_record.handle
            not in ctx.existing_smoothing_masks_by_handle
        ):
            continue
        if name in captured:
            raise RuntimeError(
                f"FBX 内存在重复网格名，无法安全对应现有光滑组：{name}"
            )
        mapping = build_topology_map(node, target_record.node)
        source_masks = _source_order_masks(
            ctx.existing_smoothing_masks_by_handle[target_record.handle],
            mapping,
        )
        if not bool(
            rt.F2M_Helper.setFaceSmoothingGroups(
                node,
                rt.Array(*source_masks),
            )
        ):
            raise RuntimeError(
                f"无法在隔离的第一次 FBX 导入上重建 {name} 的现有光滑组基线："
                + helper_message()
            )
        faces, fan_ids, corner_normals, explicit_count, specified_count = (
            _snapshot_smoothing_input(node)
        )
        captured[name] = _make_smoothing_normal_baseline(
            node,
            name,
            faces,
            fan_ids,
            corner_normals,
            explicit_count,
            specified_count,
        )
        ctx.log.add(
            f"{name}：Max 源模型已有非零光滑组；已在隔离 FBX 网格上重建"
            "纯蓝色 SG 法线基线，后续只保留超过 0.1° 的自定义法线差异。"
        )
    if set(captured) != expected_names:
        missing = sorted(expected_names - set(captured))
        extra = sorted(set(captured) - expected_names)
        raise RuntimeError(
            "无法为全部已有光滑组的 Max 源模型建立法线基线；"
            f"缺少={missing[:8]}，新增={extra[:8]}。"
        )
    ctx.smoothing_normal_baselines_by_name = captured


def _validate_external_smoothing_baselines_against_second_import(
    ctx: TransferContext,
    nodes: Iterable[Any],
) -> None:
    validated: Set[str] = set()
    expected = set(ctx.smoothing_normal_baselines_by_name)
    for node in nodes:
        if not is_valid_node(node) or not is_geometry_node(node):
            continue
        name = str(node.name)
        baseline = ctx.smoothing_normal_baselines_by_name.get(name)
        if baseline is None:
            continue
        if name in validated:
            raise RuntimeError(
                f"第二次 FBX 导入含重复网格名，无法验证法线基线：{name}"
            )
        faces = _base_topology_faces(node)
        if faces != baseline.faces:
            raise RuntimeError(
                f"{name} 两次 FBX 导入与现有 SG 法线基线的面角拓扑不一致。"
            )
        current_transform_raw = rt.F2M_Helper.nodeObjectTransformBuffer(node)
        if (
            current_transform_raw is None
            or str(current_transform_raw) == "undefined"
        ):
            raise RuntimeError(f"无法读取第二次显式法线导入的对象变换：{name}")
        current_transform = tuple(
            float(value) for value in list(current_transform_raw)
        )
        if len(current_transform) != 12:
            raise RuntimeError(f"第二次显式法线导入的对象变换不完整：{name}")
        transform_delta = max(
            abs(first - second)
            for first, second in zip(
                baseline.object_transform,
                current_transform,
            )
        )
        if transform_delta > 0.000001:
            raise RuntimeError(
                f"{name} 两次 FBX 导入的对象变换不一致，"
                f"最大分量差 {transform_delta}；已在写入前阻断。"
            )
        validated.add(name)
    if validated != expected:
        raise RuntimeError(
            "第二次 FBX 导入缺少现有 SG 法线基线对应网格："
            + ", ".join(sorted(expected - validated)[:8])
        )


def _metadata_smoothing_for_name(ctx: TransferContext, name: str) -> bool:
    if name in ctx.native_smoothing_by_name:
        return bool(ctx.native_smoothing_by_name[name])
    normalized = normalize_name(name)
    matches = [
        bool(value)
        for key, value in ctx.native_smoothing_by_name.items()
        if normalize_name(key) == normalized
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"FBX 元数据无法唯一对应导入网格 {name}；候选数量 {len(matches)}。"
        )
    return matches[0]


def _inspect_native_smoothing_layers(ctx: TransferContext) -> None:
    metadata = _load_local_runtime_module(
        "f2m_fbx_metadata.py",
        "_f2m_fbx_metadata_runtime",
    )
    mapping = metadata.inspect_smoothing_layers(
        os.path.abspath(ctx.options.fbx_path)
    )
    if not isinstance(mapping, dict) or not mapping:
        raise RuntimeError("FBX 元数据没有返回任何 Mesh 的平滑层信息。")
    ctx.native_smoothing_by_name = {
        str(name): bool(value)
        for name, value in mapping.items()
    }
    native_count = sum(1 for value in ctx.native_smoothing_by_name.values() if value)
    ctx.log.add(
        f"FBX 平滑元数据：Mesh {len(ctx.native_smoothing_by_name)} 个，"
        f"其中 {native_count} 个含原生 LayerElementSmoothing。"
    )


def _resolver_file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _resolver_file_identity(path: str) -> Tuple[int, int]:
    stat_result = os.stat(path)
    mtime_ns = getattr(
        stat_result,
        "st_mtime_ns",
        int(stat_result.st_mtime * 1_000_000_000),
    )
    return int(stat_result.st_size), int(mtime_ns)


def _resolver_python_executable() -> str:
    candidates: List[str] = [
        os.path.join(str(sys.prefix), "python.exe"),
    ]
    executable = os.path.abspath(str(sys.executable or ""))
    if os.path.basename(executable).lower() == "python.exe":
        candidates.append(executable)
    candidates.append(
        os.path.join(os.path.dirname(executable), "Python", "python.exe")
    )
    base_prefix = os.path.abspath(str(getattr(sys, "base_prefix", "") or ""))
    if base_prefix:
        candidates.append(os.path.join(base_prefix, "python.exe"))

    seen: Set[str] = set()
    for candidate in candidates:
        absolute = os.path.abspath(candidate)
        normalized = os.path.normcase(absolute)
        if normalized in seen:
            continue
        seen.add(normalized)
        if os.path.isfile(absolute):
            return absolute
    raise RuntimeError(
        "找不到当前 3ds Max 自带的独立 Python 解释器；"
        "为避免在 Max 主进程内解析大量 FBX 法线数据，本次组合传递已停止。"
    )


def _resolver_reject_duplicate_json_pairs(
    pairs: Sequence[Tuple[str, Any]],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"resolver JSON 存在重复键：{key}")
        result[key] = value
    return result


def _resolver_canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _resolver_required_int(
    value: Any,
    label: str,
    minimum: int = 0,
    maximum: Optional[int] = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f"独立 FBX 解析响应的 {label} 不是整数。")
    result = int(value)
    if result < minimum or (maximum is not None and result > maximum):
        raise RuntimeError(f"独立 FBX 解析响应的 {label} 超出允许范围。")
    return result


def _resolver_required_sha256(value: Any, label: str) -> str:
    text = str(value)
    if re.fullmatch(r"[0-9a-f]{64}", text) is None:
        raise RuntimeError(f"独立 FBX 解析响应的 {label} 不是有效 SHA-256。")
    return text


def _validated_resolver_payload(
    payload: Any,
    *,
    fbx_path: str,
    metadata_path: str,
    smoothing_path: str,
    metadata_sha256: str,
    smoothing_sha256: str,
) -> Tuple[Dict[str, IsolatedSmoothingMeshData], int, int, str]:
    if not isinstance(payload, dict):
        raise RuntimeError("独立 FBX 解析响应不是 JSON 对象。")
    response_sha256 = _resolver_required_sha256(
        payload.get("response_sha256"),
        "response_sha256",
    )
    unhashed_payload = dict(payload)
    unhashed_payload.pop("response_sha256", None)
    actual_response_sha256 = hashlib.sha256(
        _resolver_canonical_json_bytes(unhashed_payload)
    ).hexdigest()
    if actual_response_sha256 != response_sha256:
        raise RuntimeError("独立 FBX 解析响应的内嵌 SHA-256 验证失败。")

    exact_requirements = {
        "schema": STRICT_RESOLVER_SCHEMA,
        "schema_version": STRICT_RESOLVER_SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "topology_hash_algorithm": "sha256",
        "topology_encoding": STRICT_RESOLVER_TOPOLOGY_ENCODING,
        "input_hash_algorithm": "sha256",
        "response_hash_algorithm": "sha256",
        "normal_angle_tolerance_degrees": 0.01,
        "max_smoothing_groups": 32,
    }
    for key, expected in exact_requirements.items():
        if payload.get(key) != expected:
            raise RuntimeError(
                f"独立 FBX 解析响应的 {key} 与当前插件协议不一致。"
            )

    if (
        _resolver_required_int(
            payload.get("interpreter_major"),
            "interpreter_major",
        )
        != int(sys.version_info.major)
        or _resolver_required_int(
            payload.get("interpreter_minor"),
            "interpreter_minor",
        )
        != int(sys.version_info.minor)
        or _resolver_required_int(
            payload.get("interpreter_bits"),
            "interpreter_bits",
        )
        != struct.calcsize("P") * 8
        or payload.get("interpreter_is_64bit") is not True
    ):
        raise RuntimeError(
            "独立 FBX 解析器与当前 3ds Max Python 的版本或位数不一致。"
        )

    returned_metadata_path = os.path.abspath(
        str(payload.get("metadata_module_file", ""))
    )
    returned_smoothing_path = os.path.abspath(
        str(payload.get("smoothing_module_file", ""))
    )
    if (
        os.path.normcase(returned_metadata_path)
        != os.path.normcase(metadata_path)
        or os.path.normcase(returned_smoothing_path)
        != os.path.normcase(smoothing_path)
    ):
        raise RuntimeError("独立 FBX 解析器加载的源码绝对路径不一致。")
    if (
        _resolver_required_sha256(
            payload.get("metadata_source_sha256"),
            "metadata_source_sha256",
        )
        != metadata_sha256
        or _resolver_required_sha256(
            payload.get("smoothing_source_sha256"),
            "smoothing_source_sha256",
        )
        != smoothing_sha256
    ):
        raise RuntimeError("独立 FBX 解析器加载的源码 SHA-256 不一致。")

    input_size = _resolver_required_int(
        payload.get("input_size"),
        "input_size",
    )
    input_mtime_ns = _resolver_required_int(
        payload.get("input_mtime_ns"),
        "input_mtime_ns",
    )
    input_sha256 = _resolver_required_sha256(
        payload.get("input_sha256"),
        "input_sha256",
    )
    current_identity = _resolver_file_identity(fbx_path)
    if current_identity != (input_size, input_mtime_ns):
        raise RuntimeError("FBX 文件在独立解析完成后发生了大小或时间漂移。")
    if _resolver_file_sha256(fbx_path) != input_sha256:
        raise RuntimeError("FBX 文件在独立解析完成后发生了内容漂移。")
    if _resolver_file_identity(fbx_path) != current_identity:
        raise RuntimeError("FBX 文件在主进程复核哈希时发生了漂移。")

    meshes = payload.get("meshes")
    if not isinstance(meshes, list) or not meshes:
        raise RuntimeError("独立 FBX 解析响应没有返回任何 Mesh。")
    mesh_count = _resolver_required_int(
        payload.get("mesh_count"),
        "mesh_count",
        minimum=1,
    )
    if mesh_count != len(meshes):
        raise RuntimeError("独立 FBX 解析响应的 Mesh 数量不一致。")

    resolved: Dict[str, IsolatedSmoothingMeshData] = {}
    for mesh_index, mesh in enumerate(meshes, start=1):
        if not isinstance(mesh, dict):
            raise RuntimeError(
                f"独立 FBX 解析响应第 {mesh_index} 个 Mesh 不是对象。"
            )
        name = str(mesh.get("name", ""))
        if not name or name in resolved:
            raise RuntimeError("独立 FBX 解析响应含空名称或重复 Mesh 名。")
        face_count = _resolver_required_int(
            mesh.get("face_count"),
            f"{name}.face_count",
            minimum=1,
        )
        corner_count = _resolver_required_int(
            mesh.get("corner_count"),
            f"{name}.corner_count",
            minimum=1,
        )
        topology_sha256 = _resolver_required_sha256(
            mesh.get("topology_sha256"),
            f"{name}.topology_sha256",
        )
        raw_masks = mesh.get("masks")
        if not isinstance(raw_masks, list) or len(raw_masks) != face_count:
            raise RuntimeError(f"{name} 的独立解析光滑组数量与面数不一致。")
        masks: List[int] = []
        for face_index, raw_mask in enumerate(raw_masks, start=1):
            masks.append(
                _resolver_required_int(
                    raw_mask,
                    f"{name}.masks[{face_index}]",
                    minimum=-0x80000000,
                    maximum=0x7FFFFFFF,
                )
            )
        native = mesh.get("native")
        if not isinstance(native, bool):
            raise RuntimeError(f"{name} 的独立解析 native 标记无效。")
        method = str(mesh.get("method", ""))
        if method not in (
            "native_by_polygon_direct",
            "computed_from_corner_normals",
        ):
            raise RuntimeError(f"{name} 的独立解析 method 无效。")
        if native != (method == "native_by_polygon_direct"):
            raise RuntimeError(f"{name} 的独立解析来源标记互相矛盾。")
        solver_stats = mesh.get("solver_stats")
        if not isinstance(solver_stats, dict):
            raise RuntimeError(f"{name} 的独立解析 solver_stats 无效。")
        resolved[name] = IsolatedSmoothingMeshData(
            face_count=face_count,
            corner_count=corner_count,
            topology_sha256=topology_sha256,
            masks=tuple(masks),
            native=native,
            method=method,
            solver_stats=dict(solver_stats),
        )
    return resolved, input_size, input_mtime_ns, input_sha256


def _cleanup_resolver_work_directory(
    work_directory: str,
    temp_root: str,
) -> None:
    absolute_work = os.path.abspath(work_directory)
    absolute_root = os.path.abspath(temp_root)
    if (
        os.path.dirname(absolute_work) != absolute_root
        or not os.path.basename(absolute_work).startswith("resolve_")
        or os.path.commonpath([absolute_root, absolute_work]) != absolute_root
    ):
        raise RuntimeError("拒绝清理不属于 FBXTo3dsMax 的解析临时目录。")
    shutil.rmtree(absolute_work)


def _inspect_smoothing_and_normal_data(ctx: TransferContext) -> None:
    fbx_path = os.path.abspath(ctx.options.fbx_path)
    metadata_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "f2m_fbx_metadata.py")
    )
    smoothing_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "f2m_smoothing.py")
    )
    for source_path in (metadata_path, smoothing_path):
        if not os.path.isfile(source_path):
            raise RuntimeError(f"组合传递缺少运行源码：{source_path}")
    metadata_sha256 = _resolver_file_sha256(metadata_path)
    smoothing_sha256 = _resolver_file_sha256(smoothing_path)
    python_executable = _resolver_python_executable()

    local_app_data = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    temp_root = os.path.abspath(
        os.path.join(local_app_data, "FBXTo3dsMax", "WorkerTemp")
    )
    os.makedirs(temp_root, exist_ok=True)
    work_directory = tempfile.mkdtemp(prefix="resolve_", dir=temp_root)
    output_path = os.path.join(work_directory, "response.json")
    try:
        command = [
            python_executable,
            "-I",
            "-S",
            "-B",
            metadata_path,
            "--input",
            fbx_path,
            "--output",
            output_path,
        ]
        creation_flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            completed = subprocess.run(
                command,
                cwd=work_directory,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                shell=False,
                timeout=STRICT_RESOLVER_TIMEOUT_SECONDS,
                creationflags=creation_flags,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "独立 FBX 解析超过 180 秒；已停止组合传递，"
                "不会回退到 Max 主进程内解析。"
            ) from exc
        if completed.returncode != 0:
            stderr_text = bytes(completed.stderr or b"")[-16384:].decode(
                "utf-8",
                errors="replace",
            ).strip()
            raise RuntimeError(
                "独立 FBX 解析失败（退出码 "
                f"{completed.returncode}）：{stderr_text or '没有错误文本'}"
            )
        if not os.path.isfile(output_path):
            raise RuntimeError("独立 FBX 解析没有生成完整响应文件。")
        response_size = os.path.getsize(output_path)
        if (
            response_size < 2
            or response_size > STRICT_RESOLVER_MAX_RESPONSE_BYTES
        ):
            raise RuntimeError("独立 FBX 解析响应大小超出安全范围。")
        with open(output_path, "r", encoding="utf-8", errors="strict") as stream:
            payload = json.load(
                stream,
                object_pairs_hook=_resolver_reject_duplicate_json_pairs,
            )
        (
            resolved,
            input_size,
            input_mtime_ns,
            input_sha256,
        ) = _validated_resolver_payload(
            payload,
            fbx_path=fbx_path,
            metadata_path=metadata_path,
            smoothing_path=smoothing_path,
            metadata_sha256=metadata_sha256,
            smoothing_sha256=smoothing_sha256,
        )
        if (
            _resolver_file_sha256(metadata_path) != metadata_sha256
            or _resolver_file_sha256(smoothing_path) != smoothing_sha256
        ):
            raise RuntimeError("独立解析期间插件源码发生了漂移。")
        ctx.fbx_mesh_data_by_name = dict(resolved)
        ctx.native_smoothing_by_name = {
            name: value.native
            for name, value in resolved.items()
        }
        ctx.resolver_input_size = input_size
        ctx.resolver_input_mtime_ns = input_mtime_ns
        ctx.resolver_input_sha256 = input_sha256
        native_count = sum(
            1 for value in ctx.native_smoothing_by_name.values() if value
        )
        ctx.log.add(
            f"FBX 严格解析已在 Max 自带独立 Python 子进程完成：Mesh "
            f"{len(resolved)} 个，其中 {native_count} 个含 "
            "ByPolygon/Direct 原生平滑层；Max 主进程只接收已验证的"
            "拓扑摘要、逐面 signed int32 掩码和求解统计。"
        )
    finally:
        try:
            _cleanup_resolver_work_directory(work_directory, temp_root)
        except Exception:
            ctx.diagnostics.append(
                "[独立解析临时目录清理]\n" + traceback.format_exc()
            )


def _mesh_data_entry_for_imported_name(
    ctx: TransferContext,
    name: str,
) -> Tuple[str, Any]:
    if name in ctx.fbx_mesh_data_by_name:
        return name, ctx.fbx_mesh_data_by_name[name]
    normalized = normalize_name(name)
    matches = [
        (key, value)
        for key, value in ctx.fbx_mesh_data_by_name.items()
        if normalize_name(key) == normalized
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"FBX 严格拓扑/法线数据无法唯一对应导入网格 {name}；"
            f"候选数量 {len(matches)}。"
        )
    return matches[0]


def _resolve_smoothing_masks_from_second_import(
    ctx: TransferContext,
    nodes: Iterable[Any],
) -> None:
    smoothing = _load_local_runtime_module(
        "f2m_smoothing.py",
        "_f2m_smoothing_runtime",
    )
    resolved_names: Set[str] = set()
    for node in nodes:
        if not is_valid_node(node) or not is_geometry_node(node):
            continue
        name = str(node.name)
        if name in resolved_names:
            raise RuntimeError(f"FBX 内存在重复网格名，无法安全求解光滑组：{name}")
        resolved_names.add(name)
        if name not in ctx.smoothing_faces_by_name:
            raise RuntimeError(f"第一次光滑组导入中没有找到网格：{name}")

        faces, fan_ids, corner_normals, explicit_count, specified_count = (
            _snapshot_smoothing_input(node)
        )
        first_faces = ctx.smoothing_faces_by_name[name]
        if faces != first_faces:
            raise RuntimeError(
                f"{name} 两次 FBX 导入的面/角/顶点顺序不一致，"
                "已在写入 Max 源模型前阻断。"
            )
        if _metadata_smoothing_for_name(ctx, name):
            # Native SG/hard-soft data is independent from custom normals.
            # Preserve Autodesk's native-layer conversion exactly; using normal
            # IDs here would incorrectly split "SG1 + local explicit normals".
            masks = ctx.smoothing_masks_by_name.get(name, [])
            if len(masks) != len(faces):
                raise RuntimeError(f"{name} 的原生光滑组数量与面数不一致。")
            for face_index, value in enumerate(masks, start=1):
                if value < -0x80000000 or value > 0x7FFFFFFF:
                    raise RuntimeError(
                        f"{name} 第 {face_index} 面的光滑组超出 int32。"
                    )
            ctx.smoothing_method_by_name[name] = "FBX 原生平滑层 / Autodesk 精确导入"
            ctx.log.add(
                f"{name}：检测到原生 LayerElementSmoothing；"
                "保留 Autodesk 导入的 32 位逐面掩码，自定义法线独立处理。"
            )
            continue

        if explicit_count < 1 and specified_count < 1:
            raise RuntimeError(
                f"{name} 没有原生平滑层，也没有 Specified / Explicit "
                "面角法线，无法可靠推导软硬边。"
            )

        # When an FBX has no native smoothing layer, Autodesk's importer still
        # generates a useful SG candidate from the explicit normals.  Prefer
        # that familiar Max result only when it exactly preserves every soft
        # edge, hard edge and vertex normal fan recovered from the second
        # import.  This keeps the broad regions artists expect without trusting
        # an importer approximation that can occasionally merge/split a fan.
        autodesk_signed = ctx.smoothing_masks_by_name.get(name, [])
        autodesk_unsigned = [
            smoothing.signed32_to_mask(int(value))
            for value in autodesk_signed
        ]
        try:
            native_validation = smoothing.validate_smoothing_masks(
                faces,
                autodesk_unsigned,
                corner_normals=corner_normals,
                normal_angle_tolerance_degrees=0.01,
                max_groups=32,
            )
        except smoothing.SmoothingError as exc:
            ctx.diagnostics.append(
                f"{name} Autodesk 自动光滑组候选未通过严格验证："
                f"{type(exc).__name__}: {exc.args!r}"
            )
        else:
            ctx.smoothing_method_by_name[name] = (
                "Autodesk 法线转光滑组候选 / 严格验证通过"
            )
            ctx.log.add(
                f"{name}：无原生平滑层；Autodesk 根据显式法线生成的候选"
                "已通过软边、硬边和顶点法线扇区严格验证，原样采用；"
                f"软边 {native_validation.soft_edge_count}，"
                f"硬边 {native_validation.hard_edge_count}，"
                f"使用 {native_validation.smoothing_group_count}/32 个光滑组。"
            )
            continue

        assignment = smoothing.compute_smoothing_assignment(
            faces,
            # Autodesk's FBX importer may allocate one Edit Normals ID per
            # face corner even when adjacent corners carry the same source
            # normal.  The vectors are therefore authoritative for an FBX
            # without LayerElementSmoothing; the importer-specific IDs are
            # retained only for diagnostics and must not manufacture hard
            # edges.
            corner_normals=corner_normals,
            normal_angle_tolerance_degrees=0.01,
            max_groups=32,
        )
        # The solver performs strict edge/fan validation before returning.
        ctx.smoothing_masks_by_name[name] = [
            int(value)
            for value in assignment.maxscript_masks
        ]
        if assignment.strategy == "coherent_soft_regions":
            method = "面角法线方向 / 连续软区优先 1–32"
            method_detail = "连续软区优先分配独立 ID"
        else:
            method = "面角法线方向 / 多位精确兜底 DSATUR 1–32"
            method_detail = "复杂扇区使用多位精确兜底"
        ctx.smoothing_method_by_name[name] = method
        ctx.log.add(
            f"{name}：无原生平滑层；Autodesk 自动候选未通过严格验证，"
            f"已从 {len(faces)} 个面的面角法线方向重新求解"
            "（0.01° 等向容差；不依赖导入器分配的法线 ID），"
            f"软边 {assignment.validation.soft_edge_count}，"
            f"硬边 {assignment.validation.hard_edge_count}，"
            f"{method_detail}，使用 {assignment.group_count}/32 个光滑组。"
        )

    expected = set(ctx.smoothing_masks_by_name)
    if resolved_names != expected:
        missing = sorted(expected - resolved_names)
        extra = sorted(resolved_names - expected)
        raise RuntimeError(
            "两次 FBX 导入的网格集合不一致；"
            f"缺少={missing[:8]}，新增={extra[:8]}。"
        )


def _imported_topology_sha256(
    faces: Sequence[Sequence[int]],
) -> Tuple[str, int]:
    digest = hashlib.sha256()
    corner_count = 0
    for face_index, face in enumerate(faces, start=1):
        degree = len(face)
        if degree < 1 or degree > 0xFFFFFFFF:
            raise RuntimeError(
                f"单次精确导入的第 {face_index} 面角数超出 uint32。"
            )
        digest.update(struct.pack("<I", degree))
        corner_count += degree
        zero_based: List[int] = []
        for value in face:
            vertex_id = int(value)
            if vertex_id < 1 or vertex_id > 0x100000000:
                raise RuntimeError(
                    f"单次精确导入的第 {face_index} 面含无效点 ID。"
                )
            zero_based.append(vertex_id - 1)
        for offset in range(0, degree, 4096):
            chunk = zero_based[offset : offset + 4096]
            if chunk:
                digest.update(
                    struct.pack(
                        f"<{len(chunk)}I",
                        *chunk,
                    )
                )
    return digest.hexdigest(), corner_count


def _verify_resolver_input_unchanged(ctx: TransferContext) -> None:
    if (
        ctx.resolver_input_size is None
        or ctx.resolver_input_mtime_ns is None
        or not ctx.resolver_input_sha256
    ):
        raise RuntimeError("组合传递缺少独立解析的 FBX 输入身份。")
    identity = _resolver_file_identity(os.path.abspath(ctx.options.fbx_path))
    if identity != (
        ctx.resolver_input_size,
        ctx.resolver_input_mtime_ns,
    ):
        raise RuntimeError("FBX 文件在独立解析与 Max 导入之间发生了漂移。")


def _resolve_smoothing_masks_from_single_exact_import(
    ctx: TransferContext,
    nodes: Iterable[Any],
) -> None:
    """Resolve SG without touching an Edit Normals reader before final copy."""

    masks_by_name: Dict[str, List[int]] = {}
    ctx.resolver_topology_by_name.clear()
    resolved_metadata_names: Set[str] = set()
    for node in nodes:
        if not is_valid_node(node) or not is_geometry_node(node):
            continue
        name = str(node.name)
        if name in masks_by_name:
            raise RuntimeError(f"FBX 内存在重复网格名，无法安全求解光滑组：{name}")
        metadata_name, mesh_data = _mesh_data_entry_for_imported_name(
            ctx,
            name,
        )
        if metadata_name in resolved_metadata_names:
            raise RuntimeError(
                f"多个导入网格映射到了同一 FBX 严格数据项：{metadata_name}"
            )
        resolved_metadata_names.add(metadata_name)

        masks = [int(value) for value in mesh_data.masks]
        if len(masks) != mesh_data.face_count:
            raise RuntimeError(
                f"{name} 的独立解析逐面光滑掩码数量与面数不一致。"
            )
        masks_by_name[name] = masks
        ctx.resolver_topology_by_name[name] = (
            int(mesh_data.face_count),
            int(mesh_data.corner_count),
            str(mesh_data.topology_sha256),
        )
        if mesh_data.native:
            ctx.smoothing_method_by_name[name] = (
                "FBX 原生 ByPolygon/Direct 平滑层 / 独立 Python 严格解析"
            )
            ctx.log.add(
                f"{name}：原生 LayerElementSmoothing 已从 FBX 文件直接"
                f"解析；其 {mesh_data.face_count} 面拓扑摘要将在正式拓扑映射"
                "已有的唯一读取中同步验证；未执行第二次 FBX 导入。"
            )
            continue

        strategy = str(mesh_data.solver_stats.get("strategy", ""))
        if strategy == "coherent_soft_regions":
            method = "FBX 文件角法线方向 / 连续软区优先 1–32"
            method_detail = "连续软区优先分配独立 ID"
        else:
            method = "FBX 文件角法线方向 / 多位精确兜底 DSATUR 1–32"
            method_detail = "复杂扇区使用多位精确兜底"
        ctx.smoothing_method_by_name[name] = method
        ctx.log.add(
            f"{name}：无原生平滑层；独立 Python 子进程已从 FBX 文件的"
            " ByPolygonVertex 精确角法线求解光滑组（0.01° 等向容差，"
            "Max 主进程不展开角法线，也不预建/删除法线读取器），"
            f"软边 {mesh_data.solver_stats.get('soft_edge_count')}，"
            f"硬边 {mesh_data.solver_stats.get('hard_edge_count')}，"
            f"使用 {mesh_data.solver_stats.get('group_count')}/32 个光滑组；"
            f"{method_detail}。"
        )
    if not masks_by_name:
        raise RuntimeError("FBX 中没有可解析光滑组的几何节点。")

    expected_metadata_names = set(ctx.fbx_mesh_data_by_name)
    if resolved_metadata_names != expected_metadata_names:
        missing = sorted(expected_metadata_names - resolved_metadata_names)
        extra = sorted(resolved_metadata_names - expected_metadata_names)
        raise RuntimeError(
            "FBX 严格数据与单次精确导入的网格集合不一致；"
            f"缺少={missing[:8]}，新增={extra[:8]}。"
        )
    ctx.smoothing_masks_by_name = masks_by_name


def import_fbx(ctx: TransferContext) -> None:
    if ctx.options.transfer_smoothing_groups:
        if ctx.options.transfer_normals:
            _inspect_smoothing_and_normal_data(ctx)
            ctx.log.add(
                "光滑组与显式法线同时启用：严格 FBX 解析/求解已在独立 "
                "Python 子进程完成；Max 主进程只执行一次 "
                "SmoothingGroups=false 精确导入。该路径不回退到主进程"
                "解析，不在密集 Edit Normals 残差前执行第二次导入或"
                "额外源法线读取器生命周期。"
            )
            exact_pass = _import_fbx_once(
                ctx,
                smoothing_groups=False,
            )
            try:
                _verify_resolver_input_unchanged(ctx)
                _resolve_smoothing_masks_from_single_exact_import(
                    ctx,
                    exact_pass,
                )
            except BaseException:
                exact_pass.clear()
                raise
            # The strict parser result contains all expanded corner vectors.
            # SG masks are now immutable Python ints, so release the bulky
            # parse/topology payload before entering Max's Edit Normals phase.
            ctx.fbx_mesh_data_by_name.clear()
            ctx.smoothing_faces_by_name.clear()
            ctx.imported_nodes = exact_pass
            return
        else:
            _inspect_native_smoothing_layers(ctx)
            ctx.log.add(
                "光滑组启用：执行双重隔离导入；第一次取得 Autodesk "
                "原生层结果，第二次保留面角法线供无原生层时的 DSATUR 求解。"
            )
        first_pass = _import_fbx_once(ctx, smoothing_groups=True)
        try:
            _capture_smoothing_masks(ctx, first_pass)
        except BaseException:
            first_pass.clear()
            raise
        first_pass_handle_names = {
            node_handle(node): str(node.name)
            for node in first_pass
            if is_valid_node(node)
        }
        # Convert every alias to immutable handle/name data before deletion.
        # Deleted MXSWrapper aliases surviving into the second import were the
        # primary trigger for Max's native garbage-collection error.
        ctx.imported_nodes.clear()
        first_pass.clear()
        _delete_handles_strict(first_pass_handle_names, "光滑组临时导入")
        second_pass = _import_fbx_once(ctx, smoothing_groups=False)
        try:
            _resolve_smoothing_masks_from_second_import(ctx, second_pass)
        except BaseException:
            second_pass.clear()
            raise
        ctx.imported_nodes = second_pass
    else:
        if (
            ctx.options.transfer_normals
            and ctx.existing_smoothing_masks_by_handle
        ):
            ctx.log.add(
                "仅传递顶点法线且 Max 源模型已有光滑组：只导入一次 FBX "
                "完整自定义法线；蓝色 SG 基线直接由实际接收模型的现有"
                "光滑组和点位生成。"
            )
        ctx.imported_nodes = _import_fbx_once(
            ctx,
            smoothing_groups=bool(ctx.options.transfer_smoothing_groups),
        )


def imported_geometry_by_name(ctx: TransferContext) -> Dict[str, List[Any]]:
    result: Dict[str, List[Any]] = {}
    for node in ctx.imported_nodes:
        if not is_valid_node(node) or not is_geometry_node(node):
            continue
        if not ctx.options.include_hidden:
            try:
                if bool(node.isHidden):
                    continue
            except Exception:
                pass
        result.setdefault(str(node.name), []).append(node)
    return result


def target_record_by_name(ctx: TransferContext, name: str) -> Optional[SceneRecord]:
    candidates = ctx.scene_by_original.get(name, [])
    geo_candidates = [r for r in candidates if is_valid_node(r.node) and is_geometry_node(r.node)]
    if ctx.options.limit_to_selection:
        selected_handles = {node_handle(n) for n in list(rt.selection)}
        geo_candidates = [r for r in geo_candidates if r.handle in selected_handles]
    if not ctx.options.include_hidden:
        filtered = []
        for record in geo_candidates:
            try:
                if not bool(record.node.isHidden):
                    filtered.append(record)
            except Exception:
                filtered.append(record)
        geo_candidates = filtered
    if not geo_candidates:
        return None
    return geo_candidates[0]


def selected_target_records(ctx: TransferContext) -> List[SceneRecord]:
    selected = []
    for node in list(rt.selection):
        if not is_valid_node(node) or not is_geometry_node(node):
            continue
        if not ctx.options.include_hidden:
            try:
                if bool(node.isHidden):
                    continue
            except Exception:
                pass
        selected.append(node)

    if not selected:
        raise RuntimeError("请在 Max 场景里选中至少 1 个 Max 源网格。")

    records_by_handle = {record.handle: record for record in ctx.scene_records}
    records: List[SceneRecord] = []
    missing = 0
    for node in selected:
        record = records_by_handle.get(node_handle(node))
        if record is None:
            missing += 1
            continue
        records.append(record)

    if missing:
        raise RuntimeError(f"有 {missing} 个选中网格无法定位场景记录。")
    return records


def _prepare_normals_only_smoothing_targets(
    ctx: TransferContext,
    target_records: Sequence[SceneRecord],
) -> None:
    ctx.initial_smoothing_masks_by_handle.clear()
    ctx.existing_smoothing_masks_by_handle.clear()
    if not ctx.options.transfer_normals:
        return
    if ctx.options.transfer_smoothing_groups:
        ctx.log.add(
            "组合路径不再批量预读接收端光滑组；将逐对象明确写入并读回 "
            "FBX 光滑组，再处理自定义法线。"
        )
    else:
        ctx.log.add(
            "仅法线路径不再批量预读接收端光滑组；将在处理每个对象前 "
            "即时读取当前对象，避免跨对象保留 MAXWrapper。"
        )


def _prepare_current_normals_only_smoothing_target(
    ctx: TransferContext,
    record: SceneRecord,
) -> None:
    if (
        not ctx.options.transfer_normals
        or ctx.options.transfer_smoothing_groups
    ):
        return
    if not is_valid_node(record.node):
        raise RuntimeError(
            f"读取现有光滑组前 Max 源模型已失效：{record.original_name}"
        )
    values: Any = None
    try:
        values = rt.F2M_Helper.getFaceSmoothingGroups(record.node)
        if values is None or str(values) == "undefined":
            raise RuntimeError(
                f"无法检查 Max 源模型现有光滑组：{record.original_name}；"
                + helper_message()
            )
        masks = [int(value) for value in list(values)]
    finally:
        values = None
    if not masks:
        raise RuntimeError(
            f"Max 源模型没有可读取的面：{record.original_name}"
        )
    ctx.initial_smoothing_masks_by_handle[record.handle] = masks
    if any(value != 0 for value in masks):
        ctx.existing_smoothing_masks_by_handle[record.handle] = masks
        ctx.log.add(
            f"{record.original_name}：仅传递顶点法线，即时检测到现有非零"
            "光滑组；将保留该光滑组，并只写入超过 0.1° 的法线差异。"
        )
    else:
        ctx.log.add(
            f"{record.original_name}：仅传递顶点法线，即时检测完成；"
            "现有光滑组全部为 0；将完整复制 FBX 自定义法线。"
        )


def imported_geometry_nodes(ctx: TransferContext) -> List[Any]:
    result = []
    for node in ctx.imported_nodes:
        if not is_valid_node(node) or not is_geometry_node(node):
            continue
        if not ctx.options.include_hidden:
            try:
                if bool(node.isHidden):
                    continue
            except Exception:
                pass
        result.append(node)
    return result


def match_selected_targets_to_sources(
    target_records: Sequence[SceneRecord],
    sources: Sequence[Any],
) -> Tuple[List[Tuple[Any, SceneRecord]], List[ObjectReport]]:
    if not sources:
        raise RuntimeError("FBX 中没有可处理的几何体。")

    if len(target_records) == 1 and len(sources) == 1:
        return [(sources[0], target_records[0])], []

    source_by_name: Dict[str, Any] = {}
    duplicate_names: Set[str] = set()
    for source in sources:
        name = str(source.name)
        if name in source_by_name:
            duplicate_names.add(name)
        else:
            source_by_name[name] = source

    pairs: List[Tuple[Any, SceneRecord]] = []
    reports: List[ObjectReport] = []
    used_source_names: Set[str] = set()

    for record in target_records:
        report_name = record.original_name
        if report_name in duplicate_names:
            report = ObjectReport(name=report_name, status="未匹配")
            report.add(f"FBX 中存在多个同名目标网格 `{report_name}`，无法安全匹配。")
            reports.append(report)
            continue

        source = source_by_name.get(report_name)
        if source is None:
            report = ObjectReport(name=report_name, status="未匹配")
            report.add("FBX 中没有与当前选中 Max 源模型同名的目标网格。")
            reports.append(report)
            continue

        if report_name in used_source_names:
            report = ObjectReport(name=report_name, status="未匹配")
            report.add("已有同名 Max 源模型使用了这个 FBX 目标网格，跳过重复匹配。")
            reports.append(report)
            continue

        used_source_names.add(report_name)
        pairs.append((source, record))

    return pairs, reports


def _set_topology_message(message: str) -> None:
    try:
        rt.F2M_Helper.setTopologyMessage(str(message))
    except Exception:
        pass


def _base_topology_faces(node: Any) -> Tuple[Tuple[int, ...], ...]:
    raw = rt.F2M_Helper.topologyFaceBuffer(node)
    if raw is None or str(raw) == "undefined":
        raise RuntimeError(helper_message() or "无法读取基础多边形拓扑。")
    values = [int(value) for value in list(raw)]
    if not values or values[0] < 1:
        raise RuntimeError("基础网格没有可映射的多边面。")
    face_count = values[0]
    offset = 1
    faces: List[Tuple[int, ...]] = []
    for face_index in range(1, face_count + 1):
        if offset >= len(values):
            raise RuntimeError(f"第 {face_index} 个基础面扁平数据缺失。")
        degree = values[offset]
        offset += 1
        if degree < 3 or offset + degree > len(values):
            raise RuntimeError(f"第 {face_index} 个基础面少于 3 个角。")
        face = tuple(values[offset : offset + degree])
        offset += degree
        if len(set(face)) != len(face):
            raise RuntimeError(
                f"第 {face_index} 个基础面重复使用同一顶点，面角映射存在歧义。"
            )
        faces.append(face)
    if offset != len(values):
        raise RuntimeError("基础多边形扁平数据存在无法解释的尾部内容。")
    return tuple(faces)


def _canonical_oriented_cycle(face: Sequence[int]) -> Tuple[int, ...]:
    values = tuple(int(value) for value in face)
    return min(values[offset:] + values[:offset] for offset in range(len(values)))


def _evaluated_triangle_difference_count(fbx_target: Any, max_source: Any) -> int:
    try:
        result = int(
            rt.F2M_Helper.evaluatedTriangleDifferenceCount(
                fbx_target,
                max_source,
            )
        )
        return max(0, result)
    except Exception:
        # This is a diagnostic warning only. The authoritative safety decision
        # is based on the Editable Poly/Mesh base topology captured above.
        return 0


def _build_topology_map_from_faces(
    fbx_faces: Sequence[Sequence[int]],
    max_faces: Sequence[Sequence[int]],
    vertex_count: int,
    evaluated_triangle_difference_count: int = 0,
) -> TopologyMap:
    normalized_fbx = tuple(tuple(int(value) for value in face) for face in fbx_faces)
    normalized_max = tuple(tuple(int(value) for value in face) for face in max_faces)
    if len(normalized_fbx) != len(normalized_max):
        raise RuntimeError("基础多边面快照数量不一致。")

    fbx_by_key: Dict[Tuple[int, ...], List[int]] = {}
    max_by_key: Dict[Tuple[int, ...], List[int]] = {}
    for label, faces, output in (
        ("FBX 目标模型", normalized_fbx, fbx_by_key),
        ("Max 源模型", normalized_max, max_by_key),
    ):
        for face_index, face in enumerate(faces):
            if len(face) < 3:
                raise RuntimeError(f"{label}第 {face_index + 1} 面少于 3 个角。")
            if len(set(face)) != len(face):
                raise RuntimeError(
                    f"{label}第 {face_index + 1} 面重复使用同一顶点。"
                )
            if min(face) < 1 or max(face) > vertex_count:
                raise RuntimeError(
                    f"{label}第 {face_index + 1} 面含越界顶点 ID。"
                )
            output.setdefault(_canonical_oriented_cycle(face), []).append(face_index)

    duplicate_keys = [
        key
        for key in set(fbx_by_key) | set(max_by_key)
        if len(fbx_by_key.get(key, [])) > 1
        or len(max_by_key.get(key, [])) > 1
    ]
    if duplicate_keys:
        key = min(duplicate_keys)
        raise RuntimeError(
            "检测到重复的同向多边面键，无法唯一决定逐面属性映射："
            f"顶点 {list(key)}。"
        )

    if set(fbx_by_key) != set(max_by_key):
        fbx_unordered = {tuple(sorted(face)) for face in normalized_fbx}
        max_unordered = {tuple(sorted(face)) for face in normalized_max}
        if fbx_unordered == max_unordered:
            raise RuntimeError(
                "基础多边形顶点集合相同，但至少一个面的绕序反向；"
                "为避免法线和面角通道翻转，模式一已阻断。"
            )
        raise RuntimeError(
            "基础多边形连接关系或顶点 ID 已变化，不能建立无损面角映射。"
        )

    fbx_face_for_max: List[int] = []
    fbx_corner_for_max: List[Tuple[int, ...]] = []
    exact_count = 0
    cyclic_count = 0
    reordered_count = 0
    for max_face_index, max_face in enumerate(normalized_max):
        fbx_face_index = fbx_by_key[_canonical_oriented_cycle(max_face)][0]
        fbx_face = normalized_fbx[fbx_face_index]
        if len(fbx_face) != len(max_face):
            raise RuntimeError(
                f"Max 源模型第 {max_face_index + 1} 面角数与映射的 "
                "FBX 目标面不同。"
            )
        fbx_corner_by_vertex = {
            vertex_id: corner_index
            for corner_index, vertex_id in enumerate(fbx_face)
        }
        corner_map = tuple(
            fbx_corner_by_vertex[vertex_id]
            for vertex_id in max_face
        )
        expected_cycle = tuple(
            (corner_map[0] + offset) % len(corner_map)
            for offset in range(len(corner_map))
        )
        if corner_map != expected_cycle:
            raise RuntimeError(
                f"Max 源模型第 {max_face_index + 1} 面不是 FBX 目标面的"
                "同向循环排列。"
            )
        fbx_face_for_max.append(fbx_face_index)
        fbx_corner_for_max.append(corner_map)
        if fbx_face_index != max_face_index:
            reordered_count += 1
        if corner_map == tuple(range(len(corner_map))):
            exact_count += 1
        else:
            cyclic_count += 1

    return TopologyMap(
        fbx_face_for_max_face=tuple(fbx_face_for_max),
        fbx_corner_for_max_corner=tuple(fbx_corner_for_max),
        exact_face_count=exact_count,
        cyclic_corner_face_count=cyclic_count,
        reordered_face_count=reordered_count,
        evaluated_triangle_difference_count=evaluated_triangle_difference_count,
    )


def build_topology_map(
    fbx_target: Any,
    max_source: Any,
    expected_fbx_topology: Optional[Tuple[int, int, str]] = None,
) -> TopologyMap:
    """Build a deterministic, orientation-preserving face/corner map.

    Cyclic changes to a polygon's starting corner are equivalent and accepted.
    Face reordering is accepted only when every oriented cyclic face key is
    unique. Reversed winding, changed vertex IDs and duplicate face ambiguity
    fail closed.
    """

    try:
        fbx_counts = mesh_counts(fbx_target)
        max_counts = mesh_counts(max_source)
        if fbx_counts[0] != max_counts[0]:
            raise RuntimeError(
                "FBX 目标模型与 Max 源模型的基础网格顶点数不同："
                f"{fbx_counts[0]}/{max_counts[0]}。"
            )
        if fbx_counts[2] != max_counts[2]:
            raise RuntimeError(
                "FBX 目标模型与 Max 源模型的基础多边面数不同："
                f"{fbx_counts[2]}/{max_counts[2]}。"
            )
        if fbx_counts[1] != max_counts[1]:
            raise RuntimeError(
                "FBX 目标模型与 Max 源模型的基础边数不同："
                f"{fbx_counts[1]}/{max_counts[1]}。"
            )

        fbx_faces = _base_topology_faces(fbx_target)
        if expected_fbx_topology is not None:
            expected_face_count, expected_corner_count, expected_digest = (
                expected_fbx_topology
            )
            actual_digest, actual_corner_count = _imported_topology_sha256(
                fbx_faces
            )
            if (
                len(fbx_faces) != int(expected_face_count)
                or actual_corner_count != int(expected_corner_count)
                or actual_digest != str(expected_digest)
            ):
                raise RuntimeError(
                    "独立解析的 FBX 拓扑摘要与单次精确导入不一致："
                    f"faces={len(fbx_faces)}/{expected_face_count}，"
                    f"corners={actual_corner_count}/{expected_corner_count}，"
                    f"sha256={actual_digest}/{expected_digest}。"
                )
        max_faces = _base_topology_faces(max_source)
        mapping = _build_topology_map_from_faces(
            fbx_faces,
            max_faces,
            fbx_counts[0],
            evaluated_triangle_difference_count=_evaluated_triangle_difference_count(
                fbx_target,
                max_source,
            ),
        )
        message = (
            "基础多边形拓扑可安全映射：点 "
            f"{fbx_counts[0]}，边 {fbx_counts[1]}，面 {mapping.face_count}；"
            f"逐角完全一致 {mapping.exact_face_count} 面，"
            f"同向循环换起点 {mapping.cyclic_corner_face_count} 面，"
            f"唯一面键重排 {mapping.reordered_face_count} 面。"
        )
        _set_topology_message(message)
        return mapping
    except Exception as exc:
        _set_topology_message(f"基础多边形拓扑无法安全映射：{exc}")
        raise


def topo_same_for_shape(src: Any, dst: Any) -> bool:
    return topo_same_for_channels(src, dst)


def topo_same_for_channels(src: Any, dst: Any) -> bool:
    try:
        build_topology_map(src, dst)
        return True
    except Exception:
        return False


def has_map_channel(node: Any, channel: int) -> bool:
    try:
        return bool(rt.F2M_Helper.hasMapChannel(node, int(channel)))
    except Exception:
        return False


def _base_mesh_type(node: Any) -> str:
    try:
        return str(rt.F2M_Helper.baseClassName(node))
    except Exception:
        return ""


def _direct_mapped_channel_type_issue(
    src: Any,
    dst: Any,
    options: TransferOptions,
    mapping: TopologyMap,
) -> str:
    """Explain a dry-run failure that production direct writers would reject."""

    if not mapping.has_non_identity_mapping:
        return ""
    requested: List[str] = []
    if options.transfer_uv:
        requested.extend(
            f"UV {channel}"
            for channel in options.uv_channels
            if has_map_channel(src, int(channel))
        )
    if options.transfer_vertex_color and has_map_channel(src, 0):
        requested.append("顶点色 RGB")
    if options.transfer_alpha and has_map_channel(src, -2):
        requested.append("顶点 Alpha")
    if options.transfer_material_ids:
        requested.append("材质 ID")
    if not requested:
        return ""

    src_type = _base_mesh_type(src)
    dst_type = _base_mesh_type(dst)
    both_poly = src_type == "Editable_Poly" and dst_type == "Editable_Poly"
    mesh_names = {"Editable_mesh", "Editable Mesh"}
    both_mesh = src_type in mesh_names and dst_type in mesh_names
    if both_poly or both_mesh:
        return ""
    return (
        "检查结果：当前存在非恒等面/角映射，且已请求现有通道 "
        f"{'、'.join(requested)}；FBX 目标基础类型为 {src_type or '未知'}，"
        f"Max 源基础类型为 {dst_type or '未知'}。直接映射写入只支持同类 "
        "Editable Poly 或同类 Editable Mesh，正式执行已被阻断。"
    )


def helper_message() -> str:
    try:
        return str(rt.F2M_Helper.lastMessage)
    except Exception:
        return ""


def activate_modifier(node: Any, modifier: Any) -> bool:
    try:
        return bool(rt.F2M_Helper.activateModifier(node, modifier))
    except Exception:
        return False


def command_panel_mode_name() -> str:
    """Return a plain mode name; never retain the MAXScript name wrapper."""

    try:
        value = str(rt.F2M_Helper.commandPanelModeName()).strip().lower()
    except Exception:
        return ""
    return value[1:] if value.startswith("#") else value


def release_modifier_panel_reference() -> bool:
    """Detach Modify-panel state before a current modifier can be destroyed."""

    try:
        return bool(rt.F2M_Helper.releaseModifierPanelReference())
    except Exception:
        return False


def restore_command_panel_mode(mode_name: str) -> bool:
    clean_mode = str(mode_name).strip().lower().lstrip("#")
    if clean_mode not in {
        "create",
        "modify",
        "hierarchy",
        "motion",
        "display",
        "utility",
    }:
        return False
    try:
        return bool(rt.F2M_Helper.restoreCommandPanelMode(clean_mode))
    except Exception:
        return False


def node_state_warnings(node: Any) -> List[str]:
    try:
        return [str(item) for item in list(rt.F2M_Helper.nodeStateWarnings(node))]
    except Exception:
        return []


def transform_pair_warnings(fbx_target: Any, max_source: Any) -> List[str]:
    try:
        return [
            str(item)
            for item in list(
                rt.F2M_Helper.transformPairWarnings(fbx_target, max_source)
            )
        ]
    except Exception:
        return []


def _maxscript_topology_arrays(mapping: TopologyMap) -> Tuple[Any, Any]:
    face_map = rt.Array(
        *[face_index + 1 for face_index in mapping.fbx_face_for_max_face]
    )
    corner_maps = rt.Array(
        *[
            rt.Array(*[corner_index + 1 for corner_index in corners])
            for corners in mapping.fbx_corner_for_max_corner
        ]
    )
    return face_map, corner_maps


def _maxscript_topology_flat_arrays(
    mapping: TopologyMap,
) -> Tuple[Any, Any, Any]:
    """Build a flat MAXScript topology map for the normal-transfer hot path.

    Other channel writers still consume the mature nested mapping contract.
    Exact-normal transfer uses this compact form so pymxs does not create one
    MAXScript Array wrapper per polygon just to remap face corners.
    """

    face_map = rt.Array(
        *[face_index + 1 for face_index in mapping.fbx_face_for_max_face]
    )
    corner_starts = [1]
    corner_values: List[int] = []
    for corners in mapping.fbx_corner_for_max_corner:
        corner_values.extend(corner_index + 1 for corner_index in corners)
        corner_starts.append(len(corner_values) + 1)
    return (
        face_map,
        rt.Array(*corner_starts),
        rt.Array(*corner_values),
    )


def _maxscript_smoothing_baseline_arrays(
    baseline: SmoothingNormalBaseline,
) -> Tuple[Any, Any, Any]:
    """Flatten a first-import SG baseline without nested pymxs wrappers."""

    if not baseline.faces:
        raise ValueError("纯 SG 法线基线没有面数据。")
    if (
        len(baseline.fan_ids) != len(baseline.faces)
        or len(baseline.corner_normals) != len(baseline.faces)
    ):
        raise ValueError("纯 SG 法线基线的面、扇区与方向行数不一致。")
    face_degrees: List[int] = []
    flat_fan_ids: List[int] = []
    flat_normal_values: List[float] = []
    for face_index, (face, fan_row, normal_row) in enumerate(
        zip(
            baseline.faces,
            baseline.fan_ids,
            baseline.corner_normals,
        ),
        start=1,
    ):
        degree = len(face)
        if degree < 3 or len(fan_row) != degree or len(normal_row) != degree:
            raise ValueError(f"纯 SG 法线基线第 {face_index} 面的角数据不完整。")
        face_degrees.append(degree)
        for fan_id, normal in zip(fan_row, normal_row):
            if int(fan_id) < 1 or len(normal) != 3:
                raise ValueError(
                    f"纯 SG 法线基线第 {face_index} 面含无效扇区或方向。"
                )
            flat_fan_ids.append(int(fan_id))
            flat_normal_values.extend(float(component) for component in normal)
    return (
        rt.Array(*face_degrees),
        rt.Array(*flat_fan_ids),
        rt.Array(*flat_normal_values),
    )


def remap_per_face_values(
    fbx_values: Sequence[Any],
    mapping: TopologyMap,
) -> List[Any]:
    if len(fbx_values) != mapping.face_count:
        raise ValueError(
            "FBX 逐面数据数量与拓扑映射面数不一致："
            f"{len(fbx_values)}/{mapping.face_count}。"
        )
    return [
        fbx_values[fbx_face]
        for fbx_face in mapping.fbx_face_for_max_face
    ]


def remap_per_corner_values(
    fbx_face_rows: Sequence[Sequence[Any]],
    mapping: TopologyMap,
) -> List[List[Any]]:
    if len(fbx_face_rows) != mapping.face_count:
        raise ValueError(
            "FBX 面角数据面数与拓扑映射面数不一致："
            f"{len(fbx_face_rows)}/{mapping.face_count}。"
        )
    result: List[List[Any]] = []
    for max_face, fbx_face in enumerate(mapping.fbx_face_for_max_face):
        source_row = fbx_face_rows[fbx_face]
        corner_map = mapping.fbx_corner_for_max_corner[max_face]
        if len(source_row) != len(corner_map):
            raise ValueError(
                f"FBX 第 {fbx_face + 1} 面角数据数量与 Max 第 "
                f"{max_face + 1} 面映射不一致。"
            )
        result.append([source_row[fbx_corner] for fbx_corner in corner_map])
    return result


def run_topology_mapping_selfcheck() -> str:
    """Installed self-check entry for cyclic/reordered topology mapping."""

    cyclic = _build_topology_map_from_faces(
        [(1, 2, 3, 4)],
        [(4, 1, 2, 3)],
        vertex_count=4,
    )
    if cyclic.fbx_corner_for_max_corner != ((3, 0, 1, 2),):
        raise AssertionError(
            "同向循环面角映射错误："
            f"{cyclic.fbx_corner_for_max_corner}"
        )
    mapped_face = remap_per_corner_values(
        [["角1", "角2", "角3", "角4"]],
        cyclic,
    )
    if mapped_face != [["角4", "角1", "角2", "角3"]]:
        raise AssertionError(f"Map Face 面角值映射错误：{mapped_face}")

    reordered = _build_topology_map_from_faces(
        [(1, 2, 3), (4, 5, 6)],
        [(4, 5, 6), (1, 2, 3)],
        vertex_count=6,
    )
    mapped_values = remap_per_face_values(["面A", "面B"], reordered)
    if mapped_values != ["面B", "面A"]:
        raise AssertionError(f"逐面值映射错误：{mapped_values}")

    try:
        _build_topology_map_from_faces(
            [(1, 2, 3, 4)],
            [(1, 4, 3, 2)],
            vertex_count=4,
        )
    except RuntimeError as exc:
        if "绕序反向" not in str(exc):
            raise AssertionError(f"反向绕序错误类型不准确：{exc}") from exc
    else:
        raise AssertionError("反向绕序没有被安全拒绝。")

    return (
        "拓扑映射自检通过：同向循环换起点、唯一面序重排、"
        "贴图面面角映射、逐面值映射及反向绕序阻断均正常。"
    )


def run_mapped_channel_selfcheck() -> str:
    """Exercise non-identity channel writers in a real 3ds Max scene."""

    ensure_runtime()
    original_selection = [
        node_handle(node)
        for node in list(rt.selection)
        if is_valid_node(node)
    ]
    created: List[Any] = []
    fbx_target: Any = None
    max_source: Any = None
    mixed_fbx: Any = None
    mixed_max: Any = None
    normal_mod: Any = None
    destination_mod: Any = None
    expected_normal: Any = None
    actual_normal: Any = None
    expected_positions: Tuple[Any, ...] = ()
    context: Optional[TransferContext] = None
    mixed_context: Optional[TransferContext] = None
    mixed_record: Optional[SceneRecord] = None

    def make_pair(prefix: str) -> Tuple[Any, Any]:
        vertices = rt.Array(
            rt.Point3(0, 0, 0),
            rt.Point3(10, 0, 0),
            rt.Point3(10, 10, 0),
            rt.Point3(0, 10, 0),
        )
        fbx_target = rt.mesh(
            name=f"{prefix}_FBX_Target",
            vertices=vertices,
            faces=rt.Array(
                rt.Point3(1, 2, 3),
                rt.Point3(1, 3, 4),
            ),
        )
        max_source = rt.mesh(
            name=f"{prefix}_Max_Source",
            vertices=vertices,
            faces=rt.Array(
                rt.Point3(3, 4, 1),
                rt.Point3(2, 3, 1),
            ),
        )
        created.extend((fbx_target, max_source))
        return fbx_target, max_source

    def map_face(node: Any, channel: int, face: int) -> List[int]:
        value = rt.meshop.getMapFace(node.mesh, channel, face)
        return [int(value.x), int(value.y), int(value.z)]

    rt.execute(
        r'''
        global F2M_MappedSC_seedChannel
        global F2M_MappedSC_seedExplicit
        global F2M_MappedSC_findNormals

        fn F2M_MappedSC_seedChannel n channelId =
        (
            local m = n.mesh
            meshop.setMapSupport m channelId true
            meshop.setNumMapVerts m channelId 6 keep:false
            try(meshop.setNumMapFaces m channelId 2 keep:false)catch()
            for i = 1 to 6 do
                meshop.setMapVert m channelId i [i / 10.0, channelId as float, 0]
            meshop.setMapFace m channelId 1 [1,2,3]
            meshop.setMapFace m channelId 2 [4,5,6]
            update n
            true
        )

        fn F2M_MappedSC_seedExplicit n =
        (
            local normalMod = Edit_Normals()
            addModifier n normalMod
            normalMod.name = "F2M_映射自检源显式法线"
            select n
            max modify mode
            modPanel.setCurrentObject normalMod
            normalMod.RebuildNormals node:n
            local normalId = normalMod.GetNormalID 1 1 node:n
            local selectionSet = #{}
            selectionSet[normalId] = true
            if not (normalMod.MakeExplicit selection:selectionSet node:n) do
                return undefined
            local value = normalize [0.2,0.4,0.8]
            normalMod.SetNormal normalId &value node:n
            normalMod.SetFaceNormalSpecified 1 1 specified:true node:n
            update n
            normalMod
        )

        fn F2M_MappedSC_findNormals n =
        (
            for m in n.modifiers where
                classof m == Edit_Normals and
                (m.name as string) == "F2M_顶点法线" do return m
            undefined
        )
        '''
    )

    try:
        fbx_target, max_source = make_pair("F2M_MappedSC")
        mapping = build_topology_map(fbx_target, max_source)
        if mapping.fbx_face_for_max_face != (1, 0):
            raise AssertionError(f"非恒等面映射错误：{mapping}")
        if mapping.fbx_corner_for_max_corner != ((1, 2, 0), (1, 2, 0)):
            raise AssertionError(f"非恒等面角映射错误：{mapping}")

        expected_positions = (
            rt.Point3(0, 0, 1),
            rt.Point3(12, 1, 3),
            rt.Point3(11, 14, -2),
            rt.Point3(-3, 9, 4),
        )
        for vertex_id, value in enumerate(expected_positions, start=1):
            rt.setVert(fbx_target, vertex_id, value)
        rt.update(fbx_target)
        shape_report = ObjectReport(name="映射变形", status="自检")
        if not copy_shape(
            fbx_target,
            max_source,
            shape_report,
            topology_map=mapping,
        ):
            raise AssertionError(" | ".join(shape_report.messages))
        for vertex_id, expected in enumerate(expected_positions, start=1):
            if float(rt.distance(rt.getVert(max_source, vertex_id), expected)) > 1.0e-5:
                raise AssertionError(f"映射变形顶点 {vertex_id} 读回不一致。")

        for channel, label in ((1, "UV"), (0, "顶点色 RGB"), (-2, "顶点 Alpha")):
            if not bool(rt.F2M_MappedSC_seedChannel(fbx_target, channel)):
                raise AssertionError(f"无法建立映射自检 {label} 通道。")
            report = ObjectReport(name=label, status="自检")
            if channel == 1:
                ok = copy_uv_channels(
                    fbx_target,
                    max_source,
                    [channel],
                    report,
                    topology_map=mapping,
                )
            else:
                ok = copy_vertex_channel(
                    fbx_target,
                    max_source,
                    channel,
                    label,
                    report,
                    topology_map=mapping,
                )
            if not ok:
                raise AssertionError(" | ".join(report.messages))
            actual = [map_face(max_source, channel, face) for face in (1, 2)]
            if actual != [[5, 6, 4], [2, 3, 1]]:
                raise AssertionError(f"{label} 面角映射读回不一致：{actual}")

        if not bool(
            rt.F2M_Helper.setFaceSmoothingGroups(
                fbx_target,
                rt.Array(1, 2),
            )
        ):
            raise AssertionError(helper_message())
        context = TransferContext(
            TransferOptions(
                fbx_path="",
                transfer_smoothing_groups=False,
                show_ui=False,
            ),
            TransferLog(),
        )
        smoothing_report = ObjectReport(name="光滑组", status="自检")
        if not copy_smoothing_groups(
            fbx_target,
            max_source,
            context,
            smoothing_report,
            topology_map=mapping,
        ):
            raise AssertionError(" | ".join(smoothing_report.messages))
        smoothing = [
            int(value)
            for value in list(rt.F2M_Helper.getFaceSmoothingGroups(max_source))
        ]
        if smoothing != [2, 1]:
            raise AssertionError(f"光滑组面映射读回不一致：{smoothing}")

        try:
            fbx_target.material = rt.StandardMaterial(
                name="F2M_MappedSC_Material"
            )
        except Exception:
            fbx_target.material = rt.PhysicalMaterial(
                name="F2M_MappedSC_Material"
            )
        rt.setFaceMatID(fbx_target, 1, 7)
        rt.setFaceMatID(fbx_target, 2, 9)
        material_report = ObjectReport(name="材质 ID", status="自检")
        if not copy_material_ids(
            fbx_target,
            max_source,
            material_report,
            topology_map=mapping,
        ):
            raise AssertionError(" | ".join(material_report.messages))
        material_ids = [
            int(rt.getFaceMatID(max_source, face))
            for face in (1, 2)
        ]
        if material_ids != [9, 7]:
            raise AssertionError(f"材质 ID 面映射读回不一致：{material_ids}")

        normal_mod = rt.F2M_MappedSC_seedExplicit(fbx_target)
        if normal_mod is None or str(normal_mod) == "undefined":
            raise AssertionError("无法建立映射自检源显式法线。")
        normal_report = ObjectReport(name="显式法线", status="自检")
        if not copy_normals(
            fbx_target,
            max_source,
            normal_report,
            topology_map=mapping,
        ):
            raise AssertionError(" | ".join(normal_report.messages))
        destination_mod = rt.F2M_MappedSC_findNormals(max_source)
        if destination_mod is None or str(destination_mod) == "undefined":
            raise AssertionError("映射自检没有生成 F2M_顶点法线。")
        if not activate_modifier(max_source, destination_mod):
            raise AssertionError("无法激活映射自检 F2M_顶点法线。")
        if not bool(
            destination_mod.GetFaceNormalSpecified(2, 3, node=max_source)
        ):
            raise AssertionError("显式法线没有映射到 Max 面 2 / 角 3。")
        destination_normal_id = int(
            destination_mod.GetNormalID(2, 3, node=max_source)
        )
        if not bool(
            destination_mod.GetNormalExplicit(
                destination_normal_id,
                node=max_source,
            )
        ):
            raise AssertionError("映射后的自定义法线不是 Explicit。")
        expected_normal = rt.normalize(rt.Point3(0.2, 0.4, 0.8))
        actual_normal = destination_mod.GetNormal(
            destination_normal_id,
            node=max_source,
        )
        if float(rt.distance(actual_normal, expected_normal)) > 1.0e-5:
            raise AssertionError("映射后的自定义法线向量读回不一致。")
        smoothing_after_normals = [
            int(value)
            for value in list(rt.F2M_Helper.getFaceSmoothingGroups(max_source))
        ]
        if smoothing_after_normals != [2, 1]:
            raise AssertionError(
                "显式法线写入覆盖了映射后的光滑组："
                f"{smoothing_after_normals}"
            )

        mixed_fbx, mixed_max = make_pair("F2M_MappedSC_Mixed")
        rt.convertToPoly(mixed_max)
        mixed_mapping = build_topology_map(mixed_fbx, mixed_max)
        if not mixed_mapping.has_non_identity_mapping:
            raise AssertionError("Mixed 基础类型自检没有形成非恒等映射。")
        if not bool(rt.F2M_MappedSC_seedChannel(mixed_fbx, 1)):
            raise AssertionError("Mixed 基础类型自检无法建立 UV 通道。")
        mixed_options = TransferOptions(
            fbx_path="",
            mode="topology_only",
            dry_run=True,
            transfer_shape=False,
            transfer_uv=True,
            uv_channels=[1],
            transfer_normals=False,
            transfer_smoothing_groups=False,
            transfer_vertex_color=False,
            transfer_alpha=False,
            transfer_material_ids=False,
            show_ui=False,
        )
        mixed_context = TransferContext(mixed_options, TransferLog())
        mixed_record = SceneRecord(
            handle=node_handle(mixed_max),
            original_name=str(mixed_max.name),
            temp_name=str(mixed_max.name),
            node=mixed_max,
        )
        mixed_report = process_pair(mixed_fbx, mixed_record, mixed_context)
        mixed_message = " | ".join(mixed_report.messages)
        if mixed_report.status == "已检查：可安全执行":
            raise AssertionError(
                "Mixed Editable Mesh/Poly 非恒等映射被预检误放行："
                + mixed_message
            )
        if (
            "Editable Mesh" not in mixed_message
            or "Editable Poly" not in mixed_message
            or "面/角映射" not in mixed_message
        ):
            raise AssertionError(
                "Mixed 基础类型预检阻断原因不准确："
                + mixed_message
            )

        return (
            "真实 Max 非恒等映射通道自检通过：变形、UV、顶点色 RGB、"
            "顶点 Alpha、光滑组、材质 ID、显式法线均按面/角映射读回；"
            "光滑组与局部显式法线共存；混合的可编辑网格/可编辑多边形"
            "写入预检已安全阻断。"
        )
    finally:
        cleanup_handles: Set[int] = set()
        cleanup_names: Dict[int, str] = {}
        cleanup_node: Any = None
        for cleanup_node in created:
            if not is_valid_node(cleanup_node):
                continue
            try:
                cleanup_handle = node_handle(cleanup_node)
                cleanup_handles.add(cleanup_handle)
                cleanup_names[cleanup_handle] = str(cleanup_node.name)
            except Exception:
                continue
        cleanup_node = None
        try:
            if context is not None:
                _release_context_node_references(context)
            if mixed_context is not None:
                _release_context_node_references(mixed_context)
        except Exception:
            pass
        if mixed_record is not None:
            mixed_record.node = None
        fbx_target = None
        max_source = None
        mixed_fbx = None
        mixed_max = None
        normal_mod = None
        destination_mod = None
        expected_normal = None
        actual_normal = None
        expected_positions = ()
        context = None
        mixed_context = None
        mixed_record = None
        created.clear()
        try:
            rt.clearSelection()
        except Exception:
            pass
        cleanup_error = ""
        try:
            _delete_handles_strict(
                cleanup_names,
                "映射通道自检临时节点",
            )
        except BaseException as exc:
            cleanup_error = _exception_text_and_release(exc)
        restore_selection_by_handle(original_selection)
        if cleanup_error:
            raise RuntimeError(
                "映射通道自检临时节点清理失败：" + cleanup_error
            ) from None


def _resolved_topology_map(
    fbx_target: Any,
    max_source: Any,
    mapping: Optional[TopologyMap],
) -> TopologyMap:
    return mapping if mapping is not None else build_topology_map(fbx_target, max_source)


def copy_shape(
    src: Any,
    dst: Any,
    report: ObjectReport,
    topology_verified: bool = False,
    topology_map: Optional[TopologyMap] = None,
) -> bool:
    try:
        _resolved_topology_map(src, dst, topology_map)
    except Exception:
        report.add(f"变形：跳过，严格拓扑不一致。{helper_message()}")
        return False
    ok = bool(rt.F2M_Helper.copyBaseVertexPositions(src, dst))
    if ok:
        report.add(f"变形：完成，按相同顶点 ID 写入 Max 源模型基础网格，Skin 修改器未删除。{helper_message()}")
    else:
        report.add(f"变形：失败。{helper_message()}")
    return ok


def copy_uv_channels(
    src: Any,
    dst: Any,
    channels: Sequence[int],
    report: ObjectReport,
    topology_verified: bool = False,
    topology_map: Optional[TopologyMap] = None,
) -> bool:
    all_existing_ok = True
    try:
        mapping = _resolved_topology_map(src, dst, topology_map)
    except Exception:
        report.add(f"UV：跳过，严格拓扑不一致。{helper_message()}")
        return False
    face_map, corner_maps = _maxscript_topology_arrays(mapping)
    for channel in channels:
        if not has_map_channel(src, channel):
            report.add(f"UV 通道 {channel}：跳过，FBX 目标模型没有这个通道。")
            continue
        try:
            direct_ok = bool(
                rt.F2M_Helper.copyMapChannelDirect(
                    src,
                    dst,
                    int(channel),
                    faceMap=face_map,
                    cornerMaps=corner_maps,
                )
            )
            msg = helper_message()
            if direct_ok:
                report.add(f"UV 通道 {channel}：完成。{msg}")
                continue

            if mapping.has_non_identity_mapping:
                report.add(
                    f"UV 通道 {channel}：失败。直接映射写入不可用，"
                    "当前面/角顺序存在映射，不能退回到不支持映射的 "
                    f"ChannelInfo。{msg}"
                )
                all_existing_ok = False
                continue
            report.add(f"UV 通道 {channel}：直接写入不可用，准备使用 ChannelInfo。{msg}")
            ok = bool(rt.F2M_Helper.copyMapChannel(src, dst, int(channel)))
            msg = helper_message()
            if ok:
                report.add(f"UV 通道 {channel}：完成。{msg}")
            else:
                report.add(f"UV 通道 {channel}：失败。{msg}")
                all_existing_ok = False
        except Exception as exc:
            report.add_exception(f"UV 通道 {channel}：失败。", exc)
            all_existing_ok = False
    return all_existing_ok


def report_missing_uv_channels(src: Any, channels: Sequence[int], report: ObjectReport) -> None:
    for channel in channels:
        if not has_map_channel(src, channel):
            report.add(f"检查警告：已勾选传递 UV {channel}，但 FBX 目标模型没有这个 UV 集；正式执行会跳过该通道。")


def record_missing_transfer_attr(ctx: TransferContext, report: ObjectReport, label: str) -> None:
    item = f"{report.name}：{label}"
    if item not in ctx.missing_transfer_attrs:
        ctx.missing_transfer_attrs.append(item)
    report.add(f"执行提醒：已勾选 {label}，但 FBX 目标模型没有该属性；已跳过对应传递。")


def record_missing_requested_attributes(src: Any, ctx: TransferContext, report: ObjectReport) -> None:
    if ctx.options.transfer_uv:
        for channel in ctx.options.uv_channels:
            if not has_map_channel(src, channel):
                record_missing_transfer_attr(ctx, report, f"传递 UV {channel}")
    if ctx.options.transfer_vertex_color and not has_map_channel(src, 0):
        record_missing_transfer_attr(ctx, report, "顶点色 RGB")
    if ctx.options.transfer_alpha and not has_map_channel(src, -2):
        record_missing_transfer_attr(ctx, report, "顶点 Alpha")


def copy_vertex_channel(
    src: Any,
    dst: Any,
    channel: int,
    label: str,
    report: ObjectReport,
    topology_verified: bool = False,
    topology_map: Optional[TopologyMap] = None,
) -> bool:
    try:
        mapping = _resolved_topology_map(src, dst, topology_map)
    except Exception:
        report.add(f"{label}：跳过，严格拓扑不一致。{helper_message()}")
        return False
    if not has_map_channel(src, channel):
        report.add(f"{label}：跳过，FBX 目标模型没有通道 {channel}。")
        return True
    face_map, corner_maps = _maxscript_topology_arrays(mapping)
    try:
        direct_ok = bool(
            rt.F2M_Helper.copyMapChannelDirect(
                src,
                dst,
                int(channel),
                faceMap=face_map,
                cornerMaps=corner_maps,
            )
        )
        msg = helper_message()
        if direct_ok:
            report.add(f"{label}：完成。{msg}")
            return True

        if mapping.has_non_identity_mapping:
            report.add(
                f"{label}：失败。直接映射写入不可用，当前面/角顺序存在"
                f"映射，不能退回到不支持映射的 ChannelInfo。{msg}"
            )
            return False
        report.add(f"{label}：直接写入不可用，准备使用 ChannelInfo。{msg}")
        ok = bool(rt.F2M_Helper.copyMapChannel(src, dst, int(channel)))
        msg = helper_message()
        if ok:
            report.add(f"{label}：完成。{msg}")
            return True
        report.add(f"{label}：失败。{msg}")
        return False
    except Exception as exc:
        report.add_exception(f"{label}：失败。", exc)
        return False


def copy_normals(
    src: Any,
    dst: Any,
    report: ObjectReport,
    topology_verified: bool = False,
    topology_map: Optional[TopologyMap] = None,
    smoothing_residual_only: bool = False,
) -> bool:
    try:
        mapping = _resolved_topology_map(src, dst, topology_map)
    except Exception:
        report.add(f"顶点法线：跳过，严格拓扑不一致。{helper_message()}")
        return False
    face_map, corner_map_starts, corner_map_flat = (
        _maxscript_topology_flat_arrays(mapping)
    )
    try:
        if smoothing_residual_only:
            ok = bool(
                rt.F2M_Helper.copyExplicitNormalResiduals(
                    src,
                    dst,
                    faceMap=face_map,
                    cornerMapStarts=corner_map_starts,
                    cornerMapFlat=corner_map_flat,
                    angleToleranceDegrees=0.1,
                )
            )
        else:
            ok = bool(
                rt.F2M_Helper.copyExplicitNormals(
                    src,
                    dst,
                    faceMap=face_map,
                    cornerMapStarts=corner_map_starts,
                    cornerMapFlat=corner_map_flat,
                )
            )
        msg = helper_message()
        if ok:
            report.add(msg or "顶点法线：完成。")
            return True
        report.add(msg or "顶点法线：失败。")
        return False
    except Exception as exc:
        report.add_exception("顶点法线：失败。", exc)
        return False


def smoothing_masks_for_source(src: Any, ctx: TransferContext) -> List[int]:
    name = str(src.name)
    if name in ctx.smoothing_masks_by_name:
        return list(ctx.smoothing_masks_by_name[name])
    if ctx.options.transfer_smoothing_groups and ctx.smoothing_masks_by_name:
        if name not in ctx.smoothing_masks_by_name:
            raise RuntimeError(f"双重导入/求解中没有找到 {name} 的光滑组结果。")

    values = rt.F2M_Helper.getFaceSmoothingGroups(src)
    if values is None or str(values) == "undefined":
        raise RuntimeError(helper_message() or "无法读取 FBX 目标模型光滑组。")
    return [int(value) for value in list(values)]


def base_face_count(node: Any) -> int:
    values = rt.F2M_Helper.getFaceSmoothingGroups(node)
    if values is None or str(values) == "undefined":
        raise RuntimeError(helper_message() or "无法读取基础网格面数。")
    return len(list(values))


def validate_smoothing_groups(
    src: Any,
    dst: Any,
    ctx: TransferContext,
    report: ObjectReport,
    topology_verified: bool = False,
    topology_map: Optional[TopologyMap] = None,
) -> bool:
    try:
        mapping = _resolved_topology_map(src, dst, topology_map)
    except Exception:
        report.add(f"检查结果：光滑组需要严格拓扑一致；{helper_message()}")
        return False
    try:
        masks = smoothing_masks_for_source(src, ctx)
        masks = remap_per_face_values(masks, mapping)
        face_count = len(masks)
        if not bool(rt.F2M_Helper.canSetFaceSmoothingGroups(dst, face_count)):
            report.add("检查结果：Max 源模型基础网格不支持逐面写入光滑组。")
            return False
        nonzero = sum(1 for value in masks if int(value) != 0)
        method = ctx.smoothing_method_by_name.get(
            str(src.name),
            "当前 FBX 目标网格逐面光滑组",
        )
        report.add(
            f"检查结果：可传递 {face_count} 个面的 32 位光滑组掩码，"
            f"其中 {nonzero} 个面使用非零掩码；来源：{method}；"
            "正式执行后会逐面读回验证。"
        )
        return True
    except Exception as exc:
        report.add_exception("检查结果：读取/验证光滑组失败。", exc)
        return False


def copy_smoothing_groups(
    src: Any,
    dst: Any,
    ctx: TransferContext,
    report: ObjectReport,
    topology_verified: bool = False,
    topology_map: Optional[TopologyMap] = None,
) -> bool:
    try:
        mapping = _resolved_topology_map(src, dst, topology_map)
    except Exception:
        report.add(f"光滑组：跳过，严格拓扑不一致。{helper_message()}")
        return False
    try:
        masks = smoothing_masks_for_source(src, ctx)
        masks = remap_per_face_values(masks, mapping)
        if not bool(
            rt.F2M_Helper.canSetFaceSmoothingGroups(dst, len(masks))
        ):
            report.add("光滑组：失败，FBX 目标光滑组面数与 Max 源模型面数不一致。")
            return False
        removed_old_normals = 0
        if not ctx.options.transfer_normals:
            # A previous plug-in run may have left an all-Explicit F2M modifier
            # above the base mesh.  It would visually override the newly
            # selected SG-only result.  Remove only our own named modifier;
            # user Edit Normals modifiers are never silently touched.
            removed_old_normals = int(
                rt.F2M_Helper.removeF2MNormalModifiers(dst)
            )
            remaining_old_normals = int(
                rt.F2M_Helper.countF2MNormalModifiers(dst)
            )
            if removed_old_normals < 0 or remaining_old_normals != 0:
                report.add(
                    "光滑组：失败，旧版插件自有顶点法线修改器未能完整清理；"
                    "为防止旧显式法线继续覆盖新光滑组，已在写入前停止。"
                    + (helper_message() or "")
                )
                return False
        max_array = rt.Array(*[int(value) for value in masks])
        ok = bool(rt.F2M_Helper.setFaceSmoothingGroups(dst, max_array))
        message = helper_message()
        if ok:
            method = ctx.smoothing_method_by_name.get(
                str(src.name),
                "当前 FBX 目标网格逐面光滑组",
            )
            report.add(
                (message or "光滑组：完成，已逐面写入并回读验证。")
                + f" 来源：{method}。"
                + (
                    f" 已清理旧版插件自有顶点法线修改器 "
                    f"{removed_old_normals} 个，避免覆盖本次光滑组显示。"
                    if removed_old_normals
                    else ""
                )
            )
            return True
        report.add(message or "光滑组：写入或读回验证失败。")
        return False
    except Exception as exc:
        report.add_exception("光滑组：失败。", exc)
        return False


def copy_material_ids(
    src: Any,
    dst: Any,
    report: ObjectReport,
    topology_verified: bool = False,
    topology_map: Optional[TopologyMap] = None,
) -> bool:
    try:
        mapping = _resolved_topology_map(src, dst, topology_map)
    except Exception:
        report.add(f"材质与 ID：跳过，严格拓扑不一致。{helper_message()}")
        return False

    material_ok = False
    try:
        original_material = dst.material
    except Exception:
        original_material = None
    try:
        material = src.material
        if is_max_undefined(material):
            report.add("材质：失败，FBX 目标模型没有可赋予的材质。")
        else:
            dst.material = material
            report.add("材质：完成，已将 FBX 目标模型材质赋予 Max 源模型。")
            material_ok = True
    except Exception as exc:
        report.add_exception(
            "材质：失败，无法把 FBX 目标模型材质赋予 Max 源模型。",
            exc,
        )

    face_map, _corner_maps = _maxscript_topology_arrays(mapping)
    ok = bool(rt.F2M_Helper.copyMaterialIds(src, dst, faceMap=face_map))
    msg = helper_message()
    if ok:
        report.add(msg or "材质 ID：完成，已通过 ChannelInfo 多边形通道复制。")
    else:
        report.add(msg or "材质 ID：失败，ChannelInfo 多边形通道复制没有成功。")
    success = material_ok and ok
    if not success:
        try:
            dst.material = original_material
            report.add("材质：因材质/ID 传递未完整成功，已恢复 Max 源模型原材质。")
        except Exception as exc:
            report.add_exception(
                "材质：传递失败后无法恢复 Max 源模型原材质。",
                exc,
            )
    return success


def gather_skin_bones(skin: Any) -> List[Any]:
    try:
        return list(rt.skinOps.GetBoneNodes(skin))
    except Exception:
        return []


def cache_imported_skin_bone_names(ctx: TransferContext, source_nodes: Iterable[Any]) -> None:
    for node in source_nodes:
        skin = find_skin(node)
        if skin is None:
            continue
        for bone in gather_skin_bones(skin):
            if not is_valid_node(bone):
                continue
            try:
                handle = node_handle(bone)
            except Exception:
                continue
            ctx.imported_bone_names.setdefault(handle, str(bone.name))


def source_bone_original_names(ctx: TransferContext, source_skin: Any, source_bones: Sequence[Any]) -> List[str]:
    names: List[str] = []
    for bone_id, bone in enumerate(source_bones, start=1):
        cached = None
        try:
            cached = ctx.imported_bone_names.get(node_handle(bone))
        except Exception:
            cached = None
        if cached:
            names.append(cached)
            continue
        try:
            name = str(rt.skinOps.GetBoneName(source_skin, int(bone_id), 0))
        except Exception:
            name = str(getattr(bone, "name", ""))
        names.append(name)
    return names


def build_scene_bone_lookup(ctx: TransferContext) -> Dict[str, SceneRecord]:
    lookup: Dict[str, SceneRecord] = {}
    for record in ctx.scene_records:
        if not is_valid_node(record.node):
            continue
        keys = {record.original_name, normalize_name(record.original_name)}
        for key in keys:
            if key and key not in lookup:
                lookup[key] = record
    return lookup


def match_scene_bone(source_bone_name: str, lookup: Dict[str, SceneRecord]) -> Optional[SceneRecord]:
    direct = lookup.get(source_bone_name)
    if direct is not None:
        return direct
    return lookup.get(normalize_name(source_bone_name))


def source_skin_weight_rows(source_skin: Any, vertex_count: int, source_bone_names: Sequence[str]) -> Tuple[List[List[Tuple[str, float]]], int]:
    rows: List[List[Tuple[str, float]]] = []
    skipped = 0
    for vertex_index in range(1, vertex_count + 1):
        influences: List[Tuple[str, float]] = []
        try:
            count = int(rt.skinOps.GetVertexWeightCount(source_skin, vertex_index))
            for influence_index in range(1, count + 1):
                bone_id = int(rt.skinOps.GetVertexWeightBoneID(source_skin, vertex_index, influence_index))
                weight = float(rt.skinOps.GetVertexWeight(source_skin, vertex_index, influence_index))
                if weight <= 0.000001:
                    continue
                if bone_id < 1 or bone_id > len(source_bone_names):
                    skipped += 1
                    continue
                bone_name = str(source_bone_names[bone_id - 1])
                influences.append((bone_name, weight))
        except Exception:
            skipped += 1
        rows.append(influences)
    return rows, skipped


def add_scene_bones_to_skin(dst_skin: Any, dst_node: Any, scene_bone_records: Sequence[SceneRecord]) -> Dict[str, int]:
    dst_bone_id_by_key: Dict[str, int] = {}
    activate_modifier(dst_node, dst_skin)
    for index, record in enumerate(scene_bone_records, start=1):
        update = -1 if index == len(scene_bone_records) else 0
        try:
            rt.skinOps.addbone(dst_skin, record.node, update, node=dst_node)
        except Exception:
            rt.skinOps.addbone(dst_skin, record.node, update)

    dst_bones = gather_skin_bones(dst_skin)
    for bone_id, bone_node in enumerate(dst_bones, start=1):
        # 当前骨骼仍是临时名，因此用记录表里的原始名来建立索引。
        handle = node_handle(bone_node)
        original_name = None
        for record in scene_bone_records:
            if record.handle == handle:
                original_name = record.original_name
                break
        if original_name is None:
            original_name = str(bone_node.name)
        dst_bone_id_by_key[original_name] = bone_id
        dst_bone_id_by_key[normalize_name(original_name)] = bone_id
    return dst_bone_id_by_key


def apply_weight_rows(dst_skin: Any, dst_node: Any, rows: List[List[Tuple[str, float]]], dst_bone_id_by_key: Dict[str, int]) -> Tuple[int, int]:
    applied_vertices = 0
    unmapped_influences = 0
    activate_modifier(dst_node, dst_skin)
    for vertex_index, influences in enumerate(rows, start=1):
        bone_ids: List[int] = []
        weights: List[float] = []
        for source_bone_name, weight in influences:
            bone_id = dst_bone_id_by_key.get(source_bone_name)
            if bone_id is None:
                bone_id = dst_bone_id_by_key.get(normalize_name(source_bone_name))
            if bone_id is None:
                unmapped_influences += 1
                continue
            bone_ids.append(int(bone_id))
            weights.append(float(weight))

        if not bone_ids:
            continue

        weight_sum = sum(weights)
        if weight_sum > 0.0:
            weights = [w / weight_sum for w in weights]

        try:
            rt.skinOps.ReplaceVertexWeights(
                dst_skin,
                int(vertex_index),
                max_array(bone_ids),
                max_array(weights),
                node=dst_node,
            )
        except Exception:
            rt.skinOps.ReplaceVertexWeights(
                dst_skin,
                int(vertex_index),
                max_array(bone_ids),
                max_array(weights),
            )
        applied_vertices += 1
    return applied_vertices, unmapped_influences


def mark_record_skip_restore(ctx: TransferContext, node: Any) -> None:
    handle = node_handle(node)
    for record in ctx.scene_records:
        if record.handle == handle:
            record.skip_restore = True
            return


def backup_or_delete_target(ctx: TransferContext, target_record: SceneRecord) -> None:
    target = target_record.node
    mark_record_skip_restore(ctx, target)
    if ctx.options.backup_old_mesh and is_valid_node(target):
        backup_name = f"{target_record.original_name}_F2M_旧网格_{ctx.run_id}"
        try:
            target.name = backup_name
        except Exception:
            pass
        try:
            target.isHidden = True
        except Exception:
            pass
    else:
        try:
            rt.delete(target)
        except Exception:
            pass


def replace_with_source_skin(src: Any, target_record: SceneRecord, ctx: TransferContext, report: ObjectReport) -> bool:
    source_skin = find_skin(src)
    if source_skin is None:
        report.add("整模替换：跳过，FBX 目标模型没有 Skin 修改器。")
        return False

    source_bones = gather_skin_bones(source_skin)
    if not source_bones:
        report.add("整模替换：跳过，FBX 目标模型的 Skin 没有骨骼。")
        return False

    source_original_names = source_bone_original_names(ctx, source_skin, source_bones)
    scene_lookup = build_scene_bone_lookup(ctx)
    required_records: List[SceneRecord] = []
    seen_handles: Set[int] = set()
    missing: List[str] = []
    for bone_name in source_original_names:
        record = match_scene_bone(bone_name, scene_lookup)
        if record is None or not is_valid_node(record.node):
            missing.append(bone_name)
            continue
        if record.handle not in seen_handles:
            required_records.append(record)
            seen_handles.add(record.handle)

    if missing:
        sample = "，".join(missing[:8])
        more = "" if len(missing) <= 8 else f" 等 {len(missing)} 个"
        report.add(f"整模替换：失败，场景里找不到这些骨骼：{sample}{more}")
        return False

    vertex_count = mesh_counts(src)[0]
    activate_modifier(src, source_skin)
    rows, read_skipped = source_skin_weight_rows(source_skin, vertex_count, source_original_names)

    if ctx.options.dry_run:
        report.add("整模替换：可执行。正式执行时会使用 Blender FBX 网格作为最终模型，导出/加载 Skin 蒙皮数据，只保留 Max 场景中的同名骨骼。")
        report.add(f"整模替换：FBX Skin 骨骼 {len(source_bones)} 个，顶点 {vertex_count} 个。")
        return True

    report.add("整模替换：自动模式不调用 Skin Load Envelope 弹窗，改用逐顶点权重写入，避免 Max 卡在匹配窗口。")

    old_target = target_record.node
    old_material = None
    old_transform = None
    try:
        old_material = old_target.material
    except Exception:
        pass
    try:
        old_transform = old_target.transform
    except Exception:
        pass

    # FBX 目标模型成为替换后的正式模型；先脱离导入层级，避免清理临时骨骼时被一起删除。
    try:
        src.parent = None
    except Exception:
        pass

    try:
        rt.F2M_Helper.removeModifierInstance(src, source_skin)
    except Exception:
        pass
    source_skin = None

    if ctx.options.keep_target_material_on_replace and old_material is not None:
        try:
            src.material = old_material
        except Exception:
            pass

    # 如果 FBX 目标模型没有有效变换，允许继承 Max 源模型变换。
    # 正常 FBX 流程下二者应已在同一坐标空间。
    try:
        if old_transform is not None and mesh_counts(src)[0] == 0:
            src.transform = old_transform
    except Exception:
        pass

    backup_or_delete_target(ctx, target_record)
    try:
        src.name = target_record.original_name
    except Exception:
        pass

    new_skin = rt.Skin()
    rt.addModifier(src, new_skin)
    dst_bone_id_by_key = add_scene_bones_to_skin(new_skin, src, required_records)
    applied_vertices, unmapped = apply_weight_rows(new_skin, src, rows, dst_bone_id_by_key)
    report.add(f"整模替换：已按骨骼名称写入 FBX Skin 权重 {applied_vertices}/{vertex_count} 个顶点。")

    ctx.keep_imported_nodes.add(node_handle(src))
    ctx.replacement_nodes.add(node_handle(src))
    report.add(f"整模替换：完成，使用 FBX 目标网格替换 Max 源网格，并按骨骼名称重建 Skin。骨骼 {len(required_records)} 个，写入权重点顶点 {applied_vertices}/{vertex_count}。")
    if read_skipped:
        report.add(f"整模替换：读取 FBX 目标权重时有 {read_skipped} 条影响被跳过。")
    if unmapped:
        report.add(f"整模替换：有 {unmapped} 条权重影响未能匹配到场景骨骼。")
    return True


def should_replace_after_fail(options: TransferOptions, shape_ok: bool, channel_ok: bool, channel_requested: bool, src: Any) -> bool:
    if options.mode == "replace":
        return True
    if options.mode == "topology_only":
        return False
    if find_skin(src) is None:
        return False
    if options.transfer_shape and not shape_ok:
        return True
    if channel_requested and not channel_ok:
        return True
    return False


def process_pair(src: Any, target_record: SceneRecord, ctx: TransferContext) -> ObjectReport:
    report = ObjectReport(name=target_record.original_name, status="处理中")
    dst = target_record.node
    src_counts = mesh_counts(src)
    dst_counts = mesh_counts(dst)
    report.add(f"FBX 目标模型统计：点 {src_counts[0]}，边 {src_counts[1]}，基础多边面 {src_counts[2]}")
    report.add(f"Max 源模型统计：点 {dst_counts[0]}，边 {dst_counts[1]}，基础多边面 {dst_counts[2]}")
    for warning in transform_pair_warnings(src, dst):
        report.add(f"成对变换警告：{warning}")

    warnings = node_state_warnings(dst)
    if warnings:
        for warning in warnings:
            report.add(f"状态提醒：{warning}")
        report.status = "跳过：需解除对象状态"
        return report

    channel_requested = (
        ctx.options.transfer_uv
        or ctx.options.transfer_normals
        or ctx.options.transfer_smoothing_groups
        or ctx.options.transfer_vertex_color
        or ctx.options.transfer_alpha
        or ctx.options.transfer_material_ids
    )
    topology_map: Optional[TopologyMap] = None
    try:
        expected_fbx_topology: Optional[Tuple[int, int, str]] = None
        if (
            ctx.options.transfer_smoothing_groups
            and ctx.options.transfer_normals
        ):
            expected_fbx_topology = ctx.resolver_topology_by_name.get(
                str(src.name)
            )
            if expected_fbx_topology is None:
                raise RuntimeError(
                    f"{src.name} 缺少独立解析拓扑摘要，不能执行组合传递。"
                )
        topology_map = build_topology_map(
            src,
            dst,
            expected_fbx_topology=expected_fbx_topology,
        )
        same_topology = True
    except Exception:
        same_topology = False
    topology_message = helper_message()
    if ctx.options.dry_run:
        check_ok = bool(same_topology)
        if same_topology:
            report.add(f"检查结果：{topology_message}")
            if topology_map is not None and topology_map.triangulation_warning:
                report.add(f"检查警告：{topology_map.triangulation_warning}")
            if topology_map is not None:
                type_issue = _direct_mapped_channel_type_issue(
                    src,
                    dst,
                    ctx.options,
                    topology_map,
                )
                if type_issue:
                    report.add(type_issue)
                    check_ok = False
            if ctx.options.transfer_uv:
                report_missing_uv_channels(src, ctx.options.uv_channels, report)
            if ctx.options.transfer_vertex_color and not has_map_channel(src, 0):
                report.add("检查警告：已勾选顶点色 RGB，但 FBX 目标模型没有通道 0；正式执行会跳过。")
            if ctx.options.transfer_alpha and not has_map_channel(src, -2):
                report.add("检查警告：已勾选顶点 Alpha，但 FBX 目标模型没有通道 -2；正式执行会跳过。")
            if ctx.options.transfer_normals:
                try:
                    normals_ok = bool(rt.F2M_Helper.canReadExplicitNormals(src))
                except Exception:
                    normals_ok = False
                if normals_ok:
                    report.add(f"检查结果：FBX 目标模型的面角显式法线可读取。{helper_message()}")
                else:
                    report.add(f"检查结果：无法读取 FBX 目标模型的显式法线，正式执行已被阻断。{helper_message()}")
                    check_ok = False
            if ctx.options.transfer_smoothing_groups:
                check_ok = validate_smoothing_groups(
                    src,
                    dst,
                    ctx,
                    report,
                    topology_verified=True,
                    topology_map=topology_map,
                ) and check_ok
            if ctx.options.transfer_material_ids:
                try:
                    if is_max_undefined(src.material):
                        report.add("检查结果：已勾选材质与 ID，但 FBX 目标模型没有可赋予的材质。")
                        check_ok = False
                    else:
                        report.add("检查结果：FBX 目标模型有材质；正式执行会赋予 Max 源模型，并按面映射复制材质 ID。")
                except Exception as exc:
                    report.add_exception(
                        "检查结果：读取 FBX 目标模型材质失败。",
                        exc,
                    )
                    check_ok = False
            report.status = "已检查：可安全执行" if check_ok else "失败：属性预检未通过"
        else:
            report.add(f"检查结果：模式一不能安全传递。{topology_message}")
            report.add("建议：如果这是改过拓扑的新模型，请改用模式二“替换网格并保留蒙皮”。")
            report.status = "失败：模型不一致"
        return report

    if not same_topology:
        report.add(f"模式一失败：FBX 目标模型与 Max 源模型无法建立安全拓扑映射，已停止传递。{topology_message}")
        report.add("建议：如果这是改过拓扑的新模型，请改用模式二“替换网格并保留蒙皮”。")
        report.status = "失败：模型不一致"
        return report

    if topology_map is not None and topology_map.triangulation_warning:
        report.add(f"执行警告：{topology_map.triangulation_warning}")

    record_missing_requested_attributes(src, ctx, report)

    shape_ok = True
    channel_ok = True
    smoothing_ok = True
    if ctx.options.transfer_shape:
        shape_ok = copy_shape(
            src,
            dst,
            report,
            topology_verified=True,
            topology_map=topology_map,
        )

    if ctx.options.transfer_material_ids:
        channel_ok = copy_material_ids(
            src,
            dst,
            report,
            topology_verified=True,
            topology_map=topology_map,
        ) and channel_ok

    if ctx.options.transfer_uv:
        channel_ok = copy_uv_channels(
            src,
            dst,
            ctx.options.uv_channels,
            report,
            topology_verified=True,
            topology_map=topology_map,
        ) and channel_ok

    if ctx.options.transfer_smoothing_groups:
        # Combined SG + normals is intentionally write-first.  Even when the
        # destination masks already equal the FBX masks, execute the real
        # base-object write and readback before building the residual-normal
        # baseline; an equality shortcut would create a different cache
        # lifecycle and violate the user's ordering contract.
        smoothing_ok = copy_smoothing_groups(
            src,
            dst,
            ctx,
            report,
            topology_verified=True,
            topology_map=topology_map,
        )
        channel_ok = smoothing_ok and channel_ok

    if ctx.options.transfer_vertex_color:
        channel_ok = copy_vertex_channel(
            src,
            dst,
            0,
            "顶点色 RGB",
            report,
            topology_verified=True,
            topology_map=topology_map,
        ) and channel_ok

    if ctx.options.transfer_alpha:
        channel_ok = copy_vertex_channel(
            src,
            dst,
            -2,
            "顶点 Alpha",
            report,
            topology_verified=True,
            topology_map=topology_map,
        ) and channel_ok

    # Explicit normals must be the final base-data operation.  Later polyop /
    # ChannelInfo changes can legitimately rebuild the normal pipeline.
    if ctx.options.transfer_normals:
        use_smoothing_residual = (
            ctx.options.transfer_smoothing_groups
            or target_record.handle
            in ctx.existing_smoothing_masks_by_handle
        )
        if ctx.options.transfer_smoothing_groups and not smoothing_ok:
            report.add(
                "顶点法线：跳过。组合策略要求先成功写入并逐面读回光滑组；"
                "本对象的光滑组阶段失败，已禁止在错误基线上继续写法线。"
            )
            normals_ok = False
        else:
            normals_ok = copy_normals(
                src,
                dst,
                report,
                topology_verified=True,
                topology_map=topology_map,
                smoothing_residual_only=use_smoothing_residual,
            )
        if normals_ok and use_smoothing_residual:
            if ctx.options.transfer_smoothing_groups:
                report.add(
                    "组合法线策略：光滑组数据已先行写入并读回；"
                    "随后只保留光滑组不能等价表达的自定义法线残差；"
                    "全部面角最终方向必须与 FBX 目标一致。"
                )
            else:
                report.add(
                    "仅法线差异策略：Max 源模型已有非零光滑组，本次不改写"
                    "这些光滑组；以现有蓝色 SG 法线为基线，只保留与 FBX "
                    "目标方向角差超过 0.1° 的自定义法线。"
                )
            try:
                if ctx.options.transfer_smoothing_groups:
                    expected_smoothing = remap_per_face_values(
                        smoothing_masks_for_source(src, ctx),
                        topology_map,
                    )
                else:
                    expected_smoothing = list(
                        ctx.existing_smoothing_masks_by_handle[
                            target_record.handle
                        ]
                    )
                actual_values = rt.F2M_Helper.getFaceSmoothingGroups(dst)
                if actual_values is None or str(actual_values) == "undefined":
                    raise RuntimeError(
                        helper_message()
                        or "顶点法线写入后无法读取 Max 源模型光滑组。"
                    )
                actual_smoothing = [
                    int(value) for value in list(actual_values)
                ]
                if actual_smoothing != expected_smoothing:
                    raise RuntimeError(
                        "顶点法线写入改变了光滑组："
                        f"{actual_smoothing}/{expected_smoothing}"
                    )
                report.add(
                    "残差验收：顶点法线写入后已再次逐面读取光滑组，"
                    "掩码保持不变。"
                )
            except Exception as exc:
                report.add_exception(
                    "残差验收：顶点法线写入后的光滑组回读失败。",
                    exc,
                )
                normals_ok = False
            if normals_ok:
                ctx.normal_residual_notice_objects.add(
                    target_record.original_name
                )
        elif normals_ok and not ctx.options.transfer_smoothing_groups:
            report.add(
                "仅法线完整复制策略：Max 源模型逐面光滑组全部为 0，"
                "已完整覆写 FBX 自定义法线。"
            )
        channel_ok = normals_ok and channel_ok

    if (shape_ok or not ctx.options.transfer_shape) and (channel_ok or not channel_requested):
        report.status = "完成：同拓扑传递"
    else:
        report.status = "部分完成/跳过"
    return report


def process_pair_transactional(src: Any, target_record: SceneRecord, ctx: TransferContext) -> ObjectReport:
    """Process one target atomically through the 3ds Max undo system."""

    if ctx.options.dry_run or pymxs is None:
        return process_pair(src, target_record, ctx)

    report: Optional[ObjectReport] = None
    process_error = ""
    rollback_requested = False
    block_completed = False
    label = f"FBXTo3dsMax v{TOOL_VERSION}: {target_record.original_name}"

    with pymxs.undo(True, label):
        try:
            report = process_pair(src, target_record, ctx)
            block_completed = True
            if not report.status.startswith("完成"):
                rollback_requested = True
                raise RuntimeError("对象没有完整完成，触发对象级回滚。")
        except Exception as exc:
            if not rollback_requested:
                process_error = visible_exception_text(exc)
                ctx.diagnostics.append(
                    f"[对象：{target_record.original_name}]\n"
                    + traceback.format_exc()
                )
            raise

    if block_completed and not rollback_requested and report is not None:
        return report

    if report is None:
        report = ObjectReport(name=target_record.original_name, status="失败：已回滚")
    else:
        report.status = "失败：已回滚"
    if process_error:
        report.add("对象处理发生异常：" + process_error)
    report.add("本对象在失败前产生的可撤销更改，已由 3ds Max 对象级 Undo 块自动回滚。")
    return report


def cleanup_imported_nodes(ctx: TransferContext) -> None:
    keep = set(ctx.keep_imported_nodes)
    tracked_by_handle = {
        node_handle(node): node
        for node in ctx.imported_nodes
        if is_valid_node(node)
    }
    for node in all_scene_nodes():
        if not is_valid_node(node):
            continue
        handle = node_handle(node)
        if handle not in ctx.pre_handles and handle not in keep:
            tracked_by_handle.setdefault(handle, node)

    if ctx.options.keep_imported:
        failures: List[str] = []
        for index, node in enumerate(tracked_by_handle.values(), start=1):
            if not is_valid_node(node):
                continue
            if node_handle(node) in keep:
                continue
            try:
                node.name = f"{ctx.import_prefix}{index:05d}__{node.name}"
            except Exception as exc:
                failures.append(f"{getattr(node, 'name', '<unknown>')}: {exc}")
        if failures:
            message = "保留导入节点时无法完成隔离改名：" + "；".join(failures)
            ctx.safety_errors.append(message)
            raise RuntimeError(message)
        return

    delete_handle_names = {
        handle: str(node.name)
        for handle, node in tracked_by_handle.items()
        if handle not in keep and is_valid_node(node)
    }
    # Drop every context/dictionary alias before Max deletes the nodes.  The
    # strict helper resolves fresh wrappers by handle only for the duration of
    # the one bulk operation.
    ctx.imported_nodes.clear()
    tracked_by_handle.clear()
    node = None
    try:
        _delete_handles_strict(delete_handle_names, "临时 FBX 节点")
    except Exception as exc:
        message = "临时 FBX 节点清理不完整：" + visible_exception_text(exc)
        ctx.safety_errors.append(message)
        raise RuntimeError(message)
    ctx.imported_nodes = [
        node
        for handle in keep
        for node in [node_by_handle(handle)]
        if node is not None
    ]


def summarize_reports(ctx: TransferContext) -> str:
    lines: List[str] = []
    lines.append(f"FBX 到 3ds Max 数据传递报告 v{TOOL_VERSION}")
    lines.append(f"作者：{TOOL_AUTHOR}")
    lines.append("=" * 40)
    for report in ctx.reports:
        lines.append(f"[{report.status}] {report.name}")
        for message in report.messages:
            lines.append(f"  - {message}")
        lines.append("")
    return "\n".join(lines).rstrip()


def unique_limited(items: Iterable[str], max_lines: int) -> List[str]:
    unique: List[str] = []
    seen: Set[str] = set()
    for item in items:
        clean = item.strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        unique.append(clean)

    if len(unique) > max_lines:
        return unique[:max_lines] + [f"...还有 {len(unique) - max_lines} 条，详见报告文件。"]
    return unique


def concise_popup_text(text: str) -> str:
    match = re.match(r"^(\[[^\]]+\])\s*(.*)$", text.strip())
    prefix = f"{match.group(1)} " if match else ""
    body = match.group(2) if match else text

    if "成对变换警告" in body:
        if "缩放" in body:
            issue = "缩放有问题"
        elif "旋转" in body or "轴向" in body or "矩阵" in body:
            issue = "旋转有问题"
        elif "轴心" in body or "坐标中心" in body:
            issue = "中心点有问题"
        elif "位置" in body or "位移" in body:
            issue = "位移有问题"
        else:
            issue = "变换有问题"
        return f"{prefix}FBX 目标模型与 Max 源模型：{issue}"

    if "状态提醒" in body or "需解除对象状态" in body:
        return f"{prefix}对象状态有问题"

    return text


def issue_sections(ctx: TransferContext, max_lines: int = 10) -> Tuple[List[str], List[str]]:
    error_keywords = ("失败", "错误", "报错", "未匹配", "无法安全匹配")
    warning_keywords = ("警告", "状态提醒", "跳过")
    errors: List[str] = []
    warnings: List[str] = []

    def add_issue(text: str) -> None:
        summary = concise_popup_text(text)
        if any(keyword in text for keyword in error_keywords):
            errors.append(summary)
        elif any(keyword in text for keyword in warning_keywords):
            warnings.append(summary)

    for item in ctx.log.lines:
        add_issue(item)

    for report in ctx.reports:
        add_issue(f"[{report.name}] {report.status}")
        for message in report.messages:
            add_issue(f"[{report.name}] {message}")

    return unique_limited(errors, max_lines), unique_limited(warnings, max_lines)


def write_log_file(text: str, run_id: str = "") -> str:
    unique_id = run_id or f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    roots = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        roots.append(local_app_data)
    roots.append(tempfile.gettempdir())

    failures: List[str] = []
    for root in roots:
        folder = os.path.join(root, "FBXTo3dsMax", "Reports", time.strftime("%Y-%m-%d"))
        path = os.path.join(folder, f"F2M_传递报告_{unique_id}.txt")
        try:
            os.makedirs(folder, exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(_display_text(text))
            return path
        except Exception as exc:
            failures.append(f"{path}: {exc}")
    raise RuntimeError("报告写入失败；" + "；".join(failures))


def write_log_file_safe(text: str, run_id: str = "") -> str:
    try:
        return write_log_file(text, run_id)
    except Exception:
        return ""


def write_diagnostic_file(diagnostics: Sequence[str], run_id: str) -> str:
    if not diagnostics:
        return ""
    roots: List[str] = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        roots.append(local_app_data)
    roots.append(tempfile.gettempdir())
    for root in roots:
        folder = os.path.join(
            root,
            "FBXTo3dsMax",
            "Reports",
            time.strftime("%Y-%m-%d"),
        )
        path = os.path.join(
            folder,
            f"F2M_传递报告_{run_id}_内部诊断.txt",
        )
        try:
            os.makedirs(folder, exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(
                    "FBXTo3dsMax 传递内部诊断\n"
                    "说明：此文件仅供定位程序错误，可能包含底层英文异常。\n"
                    + "=" * 72
                    + "\n"
                    + "\n\n".join(diagnostics).rstrip()
                    + "\n"
                )
            return path
        except Exception:
            continue
    return ""


def visible_exception_text(exc: BaseException) -> str:
    text = str(exc).strip()
    if _language_runtime().get_language() == "en":
        return text or "底层操作失败，未返回可读原因。"
    if not text:
        return "底层操作失败，未返回可读原因。"
    # Autodesk、Python、Qt 或第三方模块的异常经常中英混合。面向用户的
    # 报告只放行完全中文的原因；原始内容由调用方写入内部诊断文件。
    if not re.search(r"[A-Za-z]", text):
        return text
    return "底层操作失败，具体技术信息已写入内部诊断文件。"


def show_check_message(ctx: TransferContext, title: str, log_path: str) -> None:
    errors, warnings = issue_sections(ctx)
    sections: List[str] = []

    if errors:
        sections.append("错误：\n" + "\n".join(errors))
    if warnings:
        sections.append("警告：\n" + "\n".join(warnings))

    if sections:
        body = "检查完成。\n\n" + "\n\n".join(sections)
    else:
        body = "检查完成，未发现错误或警告。"

    body += f"\n\n更多内容：\n{log_path or '报告文件写入失败，请查看 MaxScript Listener。'}"

    try:
        rt.messageBox(_display_text(body), title=_display_text(title), beep=bool(errors or warnings))
    except Exception:
        pass


def show_missing_transfer_attributes(ctx: TransferContext, log_path: str) -> None:
    if ctx.options.dry_run or not ctx.missing_transfer_attrs:
        return
    items = unique_limited(ctx.missing_transfer_attrs, 12)
    body = "以下已勾选的属性在 FBX 目标模型中不存在，已自动跳过对应传递：\n\n"
    body += "\n".join(f"- {item}" for item in items)
    body += f"\n\n其它可用属性已继续执行。\n\n更多内容：\n{log_path or '报告文件写入失败，请查看 MaxScript Listener。'}"
    try:
        rt.messageBox(_display_text(body), title=_display_text("FBX 到 3ds Max 属性缺失提醒"), beep=True)
    except Exception:
        pass


def show_normal_residual_notice(ctx: TransferContext, log_path: str) -> None:
    if (
        ctx.options.dry_run
        or not ctx.normal_residual_notice_objects
    ):
        return
    names = unique_limited(
        sorted(ctx.normal_residual_notice_objects),
        12,
    )
    body = (
        "以下 Max 源模型使用了“光滑组基线 + 自定义法线差异”策略：\n\n"
        + "\n".join(f"- {name}" for name in names)
        + "\n\n插件已先确认最终光滑组：只勾选“顶点法线”时保留模型"
        "原有光滑组；同时勾选“光滑组”和“顶点法线”时先写入并读回"
        "目标光滑组。随后以实际接收模型最终点位产生的蓝色光滑组法线"
        "为基线，与 FBX 目标自定义法线逐面角比较：角差不超过 0.1° "
        "的方向继续保留为蓝色 SG 法线；只有超过 0.1° 的差异才写成"
        "绿色/黄色 Explicit 自定义法线。"
        "\n\n最终每个面角方向仍必须与 FBX 目标一致，否则本次对象会回滚。"
        f"\n\n详细报告：\n{log_path or '报告文件写入失败，请查看 MaxScript Listener。'}"
    )
    try:
        rt.messageBox(
            _display_text(body),
            title=_display_text("顶点法线差异传递说明"),
            beep=False,
        )
    except Exception:
        pass


def reports_succeeded(ctx: TransferContext) -> bool:
    if ctx.safety_errors or not ctx.reports:
        return False
    expected_prefix = "已检查" if ctx.options.dry_run else "完成"
    return all(report.status.startswith(expected_prefix) for report in ctx.reports)


def restore_selection_by_handle(handles: Sequence[int]) -> None:
    wanted = {int(handle) for handle in handles}
    live = [
        node
        for node in all_scene_nodes()
        if is_valid_node(node) and node_handle(node) in wanted
    ]
    if live:
        rt.select(live)
    else:
        rt.clearSelection()


def _release_completed_pair_boundary(
    ctx: TransferContext,
    object_name: str,
) -> None:
    # Edit_Normals is a command-panel plug-in.  Max 2023 can report a native
    # MAXScript collection error when light GC runs while that plug-in remains
    # the Modify panel's current object, even after every pymxs alias has been
    # released.  Park the panel first and fail closed if Max cannot confirm it.
    if not release_modifier_panel_reference():
        raise RuntimeError(
            f"{object_name} 对象完成后无法安全停靠 Modify 面板；"
            "已停止后续对象，避免活动 Edit Normals 引用跨越对象边界。"
        )
    ctx.log.add(
        f"{object_name} 对象完成：已释放当前对象代理并停靠 Modify 面板；"
        "未主动触发垃圾回收。"
    )


def ensure_maxscript_heap_reserve() -> Tuple[int, int]:
    """Reserve enough MAXScript heap for consecutive dense normal snapshots."""

    minimum = int(MAXSCRIPT_MIN_HEAP_BYTES)
    try:
        result = str(
            rt.execute(
                "("
                "local beforeValue = heapSize; "
                "local reserveOk = true; "
                f"try(if heapSize < {minimum}L do heapSize = {minimum}L)"
                "catch(reserveOk = false); "
                '((reserveOk as string) + "|" + '
                "(beforeValue as string) + \"|\" + "
                "(heapSize as string))"
                ")"
            )
        )
    except Exception as exc:
        raise RuntimeError(
            "无法检查或扩充 MaxScript 内存堆；已停止传递。"
        ) from exc
    parts = [part.strip() for part in result.split("|")]
    if len(parts) != 3 or parts[0].lower() != "true":
        raise RuntimeError(
            "MaxScript 内存堆扩充没有得到有效确认；已停止传递。"
        )
    try:
        before_value = int(parts[1].rstrip("Ll"))
        after_value = int(parts[2].rstrip("Ll"))
    except ValueError as exc:
        raise RuntimeError(
            "MaxScript 内存堆读回格式无效；已停止传递。"
        ) from exc
    if after_value < minimum:
        raise RuntimeError(
            "MaxScript 内存堆没有达到连续法线处理所需的安全下限；"
            "已停止传递。"
        )
    return before_value, after_value


def _process_imported_pairs(
    ctx: TransferContext,
    target_records: Sequence[SceneRecord],
) -> None:
    sources: List[Any] = imported_geometry_nodes(ctx)
    ctx.log.add(f"FBX 目标网格数量：{len(sources)}")
    pairs, unmatched_reports = match_selected_targets_to_sources(
        target_records,
        sources,
    )
    ctx.reports.extend(unmatched_reports)
    handle_queue = [
        (
            node_handle(source),
            int(record.handle),
            record,
        )
        for source, record in pairs
    ]

    # Keep only stable integers and Python metadata between objects.  Imported
    # nodes are rediscovered by handle during final cleanup.
    pairs.clear()
    sources.clear()
    ctx.imported_nodes.clear()
    for record in target_records:
        record.node = None

    source: Any = None
    target: Any = None
    record: Optional[SceneRecord] = None
    pair_report: Optional[ObjectReport] = None
    pair_completed = False
    try:
        for pair_index, (
            source_handle,
            target_handle,
            record,
        ) in enumerate(handle_queue):
            pair_completed = False
            try:
                source = node_by_handle(source_handle)
                target = node_by_handle(target_handle)
                if source is None or target is None:
                    raise RuntimeError(
                        "逐对象处理前无法按句柄重新解析当前源/目标节点。"
                    )
                record.node = target
                rt.select(target)
                _prepare_current_normals_only_smoothing_target(ctx, record)
                ctx.log.add(
                    f"传递方向：Max 源模型 {record.original_name} "
                    f"<- FBX 目标模型 {source.name}"
                )
                pair_report = process_pair_transactional(
                    source,
                    record,
                    ctx,
                )
                ctx.reports.append(pair_report)
                if pair_report.diagnostics:
                    ctx.diagnostics.append(
                        f"[对象：{record.original_name}]\n"
                        + "\n\n".join(pair_report.diagnostics)
                    )
                pair_completed = True
            finally:
                object_name = (
                    record.original_name
                    if record is not None
                    else "<unknown>"
                )
                if record is not None:
                    record.node = None
                source = None
                target = None
                pair_report = None
                if (
                    pair_completed
                    and not ctx.options.dry_run
                    and ctx.options.transfer_normals
                ):
                    _release_completed_pair_boundary(ctx, object_name)
    finally:
        if record is not None:
            record.node = None
        source = None
        target = None
        record = None
        pair_report = None
        pair_completed = False
        handle_queue.clear()


def _release_context_node_references(ctx: TransferContext) -> None:
    ctx.imported_nodes.clear()
    for record in ctx.scene_records:
        record.node = None
    ctx.scene_by_original.clear()
    ctx.scene_records.clear()
    ctx.keep_imported_nodes.clear()
    ctx.replacement_nodes.clear()
    ctx.imported_bone_names.clear()
    ctx.smoothing_masks_by_name.clear()
    ctx.smoothing_faces_by_name.clear()
    ctx.smoothing_normal_baselines_by_name.clear()
    ctx.initial_smoothing_masks_by_handle.clear()
    ctx.existing_smoothing_masks_by_handle.clear()
    ctx.native_smoothing_by_name.clear()
    ctx.fbx_mesh_data_by_name.clear()
    ctx.smoothing_method_by_name.clear()
    ctx.resolver_topology_by_name.clear()
    ctx.resolver_input_size = None
    ctx.resolver_input_mtime_ns = None
    ctx.resolver_input_sha256 = ""


def run_transfer(options: TransferOptions) -> str:
    global LAST_RUN_OK, LAST_RUN_REPORT_PATH, LAST_RUN_SUMMARY
    LAST_RUN_OK = False
    LAST_RUN_REPORT_PATH = ""
    LAST_RUN_SUMMARY = ""

    ensure_runtime()
    if options.mode != "topology_only":
        raise ValueError("f2m_topology_transfer 只接受 mode='topology_only'；整模替换必须调用 f2m_skin_replace。")
    original_selection_handles = [
        node_handle(node)
        for node in list(rt.selection)
        if is_valid_node(node)
    ]
    log = TransferLog()
    ctx = TransferContext(options, log)
    try:
        heap_before, heap_after = ensure_maxscript_heap_reserve()
        log.add(
            "MaxScript 内存堆安全下限已确认："
            f"{heap_before} -> {heap_after} 字节；"
            "仅扩充不足的会话，不主动垃圾回收。"
        )
        log.add(f"FBX 到 3ds Max 同拓扑数据传递开始 v{TOOL_VERSION} / 作者：{TOOL_AUTHOR}")
        log.add(
            "Max 源模型：当前选中网格；运行方式："
            + ("仅检查" if options.dry_run else "正式传递")
        )
        selected_geometry = [
            node
            for node in list(rt.selection)
            if is_valid_node(node) and is_geometry_node(node)
        ]
        if not selected_geometry:
            raise RuntimeError("请在 Max 场景里选中至少 1 个 Max 源网格。")
        selected_geometry.clear()
        # Large FBX files can trigger a viewport refresh for every rename,
        # modifier and channel write.  pymxs.redraw is the exception-safe
        # equivalent of MAXScript's preferred ``with redraw off`` context.
        with pymxs.redraw(False):
            prepare_scene_names(ctx)
            target_records = selected_target_records(ctx)
            log.add(f"选中 Max 源网格数量：{len(target_records)}")
            _prepare_normals_only_smoothing_targets(ctx, target_records)
            import_fbx(ctx)
            _process_imported_pairs(ctx, target_records)
            target_records = []
            cleanup_imported_nodes(ctx)
            if not restore_scene_names(ctx):
                raise RuntimeError("场景节点名称没有完整恢复，详见报告。")

        _release_context_node_references(ctx)
        summary = summarize_reports(ctx)
        log.add("")
        log.add(summary)
        diagnostic_path = write_diagnostic_file(ctx.diagnostics, ctx.run_id)
        if diagnostic_path:
            log.add("内部诊断文件：" + diagnostic_path)
        log_path = write_log_file(log.text(), ctx.run_id)
        log.add(f"报告文件：{log_path}")
        LAST_RUN_OK = reports_succeeded(ctx)
        LAST_RUN_REPORT_PATH = log_path
        LAST_RUN_SUMMARY = summary
        if options.dry_run and options.show_ui:
            show_check_message(ctx, "FBX 到 3ds Max 检查结果", log_path)
        elif (not options.dry_run) and options.show_ui:
            show_normal_residual_notice(ctx, log_path)
            show_missing_transfer_attributes(ctx, log_path)
        return summary
    except Exception as exc:
        ctx.diagnostics.append("[运行或收尾阶段]\n" + traceback.format_exc())
        failure_visible = visible_exception_text(exc)
        _exception_text_and_release(exc)
        recovery_errors: List[str] = []
        try:
            cleanup_imported_nodes(ctx)
        except Exception as cleanup_exc:
            ctx.diagnostics.append("[清理失败]\n" + traceback.format_exc())
            cleanup_visible = visible_exception_text(cleanup_exc)
            _exception_text_and_release(cleanup_exc)
            recovery_errors.append(
                "清理失败：" + cleanup_visible
            )
        try:
            if not restore_scene_names(ctx):
                recovery_errors.append("名称恢复失败")
        except Exception as restore_exc:
            ctx.diagnostics.append("[名称恢复失败]\n" + traceback.format_exc())
            restore_visible = visible_exception_text(restore_exc)
            _exception_text_and_release(restore_exc)
            recovery_errors.append(
                "名称恢复失败：" + restore_visible
            )
        _release_context_node_references(ctx)
        error_text = f"传递失败：{failure_visible}"
        if recovery_errors:
            error_text += "\n\n恢复阶段错误：\n" + "\n".join(recovery_errors)
        diagnostic_path = write_diagnostic_file(ctx.diagnostics, ctx.run_id)
        if diagnostic_path:
            error_text += "\n\n内部诊断文件：" + diagnostic_path
        log.add(error_text)
        log_path = write_log_file_safe(log.text(), ctx.run_id)
        LAST_RUN_REPORT_PATH = log_path
        LAST_RUN_SUMMARY = error_text
        if options.show_ui:
            try:
                rt.messageBox(
                    _display_text(f"{error_text}\n\n报告："
                    f"{log_path or '写入失败，请查看 MaxScript 侦听器。'}"),
                    title=_display_text("FBX 到 3ds Max 数据传递"),
                    beep=True,
                )
            except Exception:
                pass
        return error_text
    finally:
        try:
            restore_selection_by_handle(original_selection_handles)
        except Exception:
            pass


def parse_uv_channels(text: str) -> List[int]:
    result: List[int] = []
    for part in re.split(r"[,，;；\s]+", str(text).strip()):
        if not part:
            continue
        try:
            value = int(part)
        except ValueError:
            continue
        if value not in result:
            result.append(value)
    return result or [1]


def run_from_max(
    fbx_path: str,
    mode: str = "topology_only",
    dry_run: bool = False,
    transfer_shape: bool = True,
    transfer_uv: bool = True,
    uv_channels: str = "1",
    transfer_normals: bool = False,
    transfer_smoothing_groups: bool = False,
    transfer_vertex_color: bool = False,
    transfer_alpha: bool = False,
    transfer_material_ids: bool = False,
    keep_imported: bool = False,
    backup_old_mesh: bool = True,
    include_hidden: bool = True,
    keep_target_material_on_replace: bool = False,
    limit_to_selection: bool = False,
    show_ui: bool = True,
) -> str:
    if str(mode) != "topology_only":
        raise ValueError("同拓扑引擎只支持 topology_only 模式。")
    options = TransferOptions(
        fbx_path=fbx_path,
        mode=mode,
        dry_run=bool(dry_run),
        transfer_shape=bool(transfer_shape),
        transfer_uv=bool(transfer_uv),
        uv_channels=parse_uv_channels(uv_channels),
        transfer_normals=bool(transfer_normals),
        transfer_smoothing_groups=bool(transfer_smoothing_groups),
        transfer_vertex_color=bool(transfer_vertex_color),
        transfer_alpha=bool(transfer_alpha),
        transfer_material_ids=bool(transfer_material_ids),
        keep_imported=bool(keep_imported),
        backup_old_mesh=bool(backup_old_mesh),
        include_hidden=bool(include_hidden),
        keep_target_material_on_replace=bool(keep_target_material_on_replace),
        limit_to_selection=bool(limit_to_selection),
        show_ui=bool(show_ui),
    )
    return run_transfer(options)


if __name__ == "__main__":
    if rt is None:
        print("这个文件需要在 3ds Max 中运行。")
    else:
        rt.messageBox(_display_text("请通过 FBXTo3dsMax_UI.ms 启动中文界面。"), title=_display_text("FBX 到 3ds Max"))

