# -*- coding: utf-8 -*-
"""
FBX 到 3ds Max 数据传递工具

运行环境：
- 3ds Max 2023 或更高版本
- 3ds Max 自带 Python / pymxs

这个文件是核心逻辑。中文界面在 FBXTo3dsMax_UI.ms 中。
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import os
import re
import math
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
LAST_WEIGHT_WRITE_METHOD = ""
LAST_WEIGHT_BULK_FALLBACK_REASON = ""
MAXSCRIPT_MIN_HEAP_BYTES = 512 * 1024 * 1024
# Max Point3/Matrix3/Skin evaluation is float32.  Keep the v1.3.22 absolute
# acceptance floor for ordinary assets, then scale only when the coordinate
# magnitude makes several ULPs larger than that floor.  Two parts per million
# is the same bounded precision budget used by the mature Mode-1 point
# read-back; it is a float round-trip allowance, not a geometric approximation.
MODE2_WORLD_POSITION_ABSOLUTE_FLOOR = 0.001
MODE2_WORLD_POSITION_ROUNDTRIP_FLOOR = 0.000002
MODE2_WORLD_POSITION_SCALE_FACTOR = 0.000002


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
global F2M_SkinHelper

struct F2M_SkinHelperStruct
(
    lastMessage = "",
    apiKind = "skin",
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

    fn countSkin n =
    (
        local skinCount = 0
        try(for m in n.modifiers where (classof m == Skin) do skinCount += 1)catch()
        skinCount
    ),

    fn coerceNodeBoolean value =
    (
        if (classof value) == BooleanClass then value
        else
        (
            try((value as float) != 0.0)catch undefined
        )
    ),

    fn setNodeHiddenFlag n hiddenFlag =
    (
        setLastMessage ""
        try
        (
            local hiddenValue = ((hiddenFlag as integer) != 0)
            n.isNodeHidden = hiddenValue
            local observedHidden = coerceNodeBoolean n.isNodeHidden
            if observedHidden == undefined or observedHidden != hiddenValue do
                throw "节点本地隐藏状态写后读回不一致。"
            true
        )
        catch
        (
            setLastMessage ("设置节点本地隐藏状态失败：" + getCurrentException())
            false
        )
    ),

    fn setNodePresentationFlags n hiddenFlag frozenFlag boxModeFlag renderableFlag visibilityFlag =
    (
        setLastMessage ""
        local writeStep = "准备"
        try
        (
            local hiddenValue = ((hiddenFlag as integer) != 0)
            local frozenValue = ((frozenFlag as integer) != 0)
            local boxModeValue = ((boxModeFlag as integer) != 0)
            local renderableValue = ((renderableFlag as integer) != 0)
            local visibilityValue = ((visibilityFlag as integer) != 0)
            writeStep = "isNodeHidden"
            n.isNodeHidden = hiddenValue
            writeStep = "isNodeFrozen"
            n.isNodeFrozen = frozenValue
            writeStep = "boxMode"
            n.boxMode = boxModeValue
            writeStep = "renderable"
            n.renderable = renderableValue
            writeStep = "visibility"
            n.visibility = visibilityValue
            writeStep = "读回 isNodeHidden"
            local observedHidden = coerceNodeBoolean n.isNodeHidden
            if observedHidden == undefined or observedHidden != hiddenValue do throw "节点本地隐藏状态读回不一致。"
            writeStep = "读回 isNodeFrozen"
            local observedFrozen = coerceNodeBoolean n.isNodeFrozen
            if observedFrozen == undefined or observedFrozen != frozenValue do throw "节点本地冻结状态读回不一致。"
            writeStep = "读回 boxMode"
            local observedBoxMode = coerceNodeBoolean n.boxMode
            if observedBoxMode == undefined or observedBoxMode != boxModeValue do throw "boxMode 读回不一致。"
            writeStep = "读回 renderable"
            local observedRenderable = coerceNodeBoolean n.renderable
            if observedRenderable == undefined or observedRenderable != renderableValue do throw "renderable 读回不一致。"
            writeStep = "读回 visibility"
            local observedVisibility = coerceNodeBoolean n.visibility
            if observedVisibility == undefined or observedVisibility != visibilityValue do throw "visibility 读回不一致。"
            true
        )
        catch
        (
            setLastMessage (
                "设置节点图层/显示状态失败（" + writeStep + "）：" +
                getCurrentException()
            )
            false
        )
    ),

    fn modifierIndex n modInst =
    (
        try(modPanel.getModifierIndex n modInst)catch(undefined)
    ),

    fn copySkinModifierToNode sourceNode sourceSkin targetNode stackIndex =
    (
        setLastMessage ""
        local copied = undefined
        local beforeSkinCount = countSkin targetNode
        local requestedIndex = stackIndex as integer
        try
        (
            local maxIndex = targetNode.modifiers.count + 1
            if requestedIndex < 1 or requestedIndex > maxIndex do
                throw (
                    "原 FBX Skin 栈位无效：" + requestedIndex as string +
                    "；当前可插入范围为 1-" + maxIndex as string + "。"
                )
            copied = copy sourceSkin
            try
            (
                -- Skin 的骨骼引用和绑定坐标系属于同一份 Max 本地数据。
                -- 普通 addModifier 会丢失这部分数据，因此失败时必须停止，
                -- 不能再降级到一个没有 local data 的副本。
                addModifierWithLocalData targetNode copied sourceNode sourceSkin before:requestedIndex
                setLastMessage (
                    "已把 Max 源模型 Skin 修改器和本地绑定数据复制到原 FBX Skin 栈位 " +
                    requestedIndex as string + "。"
                )
            )
            catch
            (
                local localDataError = getCurrentException()
                -- 某些版本会在抛错前挂上半成品；清理后直接失败关闭。
                if (modifierIndex targetNode copied) != undefined then
                (
                    try(deleteModifier targetNode copied)catch()
                )
                if (modifierIndex targetNode copied) != undefined then
                    setLastMessage ("Skin 本地数据复制失败，且半成品无法清理：" + localDataError)
                else
                    setLastMessage ("Skin 本地数据复制失败；半成品已清理，已停止提交：" + localDataError)
                copied = undefined
            )
            if copied != undefined then
            (
                if (modifierIndex targetNode copied) != requestedIndex or
                    (countSkin targetNode) != (beforeSkinCount + 1) then
                (
                    try(if (modifierIndex targetNode copied) != undefined do deleteModifier targetNode copied)catch()
                    setLastMessage "复制 Skin 后的栈位或数量读回不一致，已停止提交。"
                    copied = undefined
                )
            )
        )
        catch
        (
            local copyError = getCurrentException()
            try(if copied != undefined and (modifierIndex targetNode copied) != undefined do deleteModifier targetNode copied)catch()
            setLastMessage ("复制 Skin 修改器失败：" + copyError)
            copied = undefined
        )
        copied
    ),

    fn createFreshSkinAtIndex targetNode stackIndex =
    (
        setLastMessage ""
        local freshSkin = undefined
        local freshIndex = undefined
        local freshHandle = undefined
        local cleanupError = ""
        local helperError = ""
        local beforeSkinCount = countSkin targetNode
        try
        (
            freshSkin = Skin()
            local requestedIndex = stackIndex as integer
            local maxIndex = targetNode.modifiers.count + 1
            if requestedIndex < 1 or requestedIndex > maxIndex then
                requestedIndex = 1
            addModifier targetNode freshSkin before:requestedIndex
            if (modifierIndex targetNode freshSkin) != requestedIndex or
                (countSkin targetNode) != (beforeSkinCount + 1) then
            (
                freshIndex = undefined
                freshHandle = undefined
                try(freshIndex = modifierIndex targetNode freshSkin)catch()
                if freshIndex != undefined do
                    try(freshHandle = getHandleByAnim freshSkin)catch()
                freshSkin = undefined
                if freshIndex == undefined then
                    setLastMessage "新建 FBX 权威 Skin 后的堆栈位置或数量读回不一致。"
                else if freshHandle == undefined then
                    setLastMessage (
                        "新建 FBX 权威 Skin 后的堆栈位置或数量读回不一致，" +
                        "且无法取得半成品 Skin 的稳定句柄；已停止提交。"
                    )
                else if not (
                    F2M_Helper.removeModifierByAnimHandle targetNode freshHandle
                ) then
                (
                    cleanupError = ""
                    try(cleanupError = F2M_Helper.lastMessage as string)catch()
                    setLastMessage (
                        "新建 FBX 权威 Skin 后的堆栈位置或数量读回不一致，" +
                        "且半成品无法按句柄安全清理；已停止提交。" +
                        (if cleanupError == "" then "" else " " + cleanupError)
                    )
                )
                else
                    setLastMessage (
                        "新建 FBX 权威 Skin 后的堆栈位置或数量读回不一致；" +
                        "半成品已按句柄安全清理。"
                    )
            )
        )
        catch
        (
            local createError = getCurrentException()
            freshIndex = undefined
            freshHandle = undefined
            if freshSkin != undefined do
            (
                try(freshIndex = modifierIndex targetNode freshSkin)catch()
                if freshIndex != undefined do
                    try(freshHandle = getHandleByAnim freshSkin)catch()
            )
            freshSkin = undefined
            cleanupError = ""
            if freshIndex != undefined then
            (
                if freshHandle == undefined then
                    cleanupError =
                        "；半成品仍在修改器栈中，但无法取得稳定句柄；已停止提交"
                else if not (
                    F2M_Helper.removeModifierByAnimHandle targetNode freshHandle
                ) then
                (
                    helperError = ""
                    try(helperError = F2M_Helper.lastMessage as string)catch()
                    cleanupError =
                        "；半成品无法按句柄安全清理；已停止提交" +
                        (if helperError == "" then "" else "：" + helperError)
                )
                else
                    cleanupError = "；半成品已按句柄安全清理"
            )
            setLastMessage (
                "新建 FBX 权威 Skin 失败：" + createError + cleanupError
            )
        )
        freshSkin
    ),

    fn skinIndex n =
    (
        local sk = findSkin n
        if sk == undefined then undefined else modPanel.getModifierIndex n sk
    ),

    fn modifierCount n =
    (
        try(n.modifiers.count)catch(0)
    ),

    fn addModifierBelowSkinOrStack n modInst =
    (
        if n.modifiers.count > 0 then
        (
            -- modifiers[1] 是栈顶；count + 1 才是所有现有修改器之下。
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
        local idx = modifierIndex n modInst
        if idx == undefined do
        (
            setLastMessage "找不到要塌陷的 F2M 修改器。"
            return false
        )

        local sk = findSkin n
        local protectedModifiers = #()
        for existingMod in n.modifiers where existingMod != modInst do append protectedModifiers existingMod

        -- 把本次 F2M 修改器移到堆栈最底部再塌陷。
        -- CollapseNodeTo 会保留它上方的修改器，所以 Skin 和用户原有修改器不会被一起塌陷。
        if idx < n.modifiers.count then
        (
            local bottomIndex = n.modifiers.count + 1
            local newModNoSkin = copy modInst
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
                if (modifierIndex n modInst) != undefined then
                (
                    try(deleteModifier n newModNoSkin)catch()
                    setLastMessage "原 F2M 临时修改器无法移除，已停止塌陷，避免留下重复修改器。"
                    return false
                )
                modInst = newModNoSkin
                idx = modifierIndex n modInst
            )
            else
            (
                setLastMessage "无法把 F2M 修改器安全移动到堆栈最底部，因此没有自动塌陷。"
                return false
            )
        )

        if idx == undefined do
        (
            setLastMessage "移动 F2M 修改器后无法重新定位。"
            return false
        )

        -- 只允许塌陷真正位于栈底的本次临时修改器。
        if idx != n.modifiers.count do
        (
            setLastMessage "F2M 临时修改器没有位于栈底，已停止塌陷以保护原有修改器。"
            return false
        )

        try
        (
            local ok = maxOps.CollapseNodeTo n idx true
            if ok then
            (
                local protectedOk = true
                for protectedMod in protectedModifiers while protectedOk do
                (
                    if (modifierIndex n protectedMod) == undefined do protectedOk = false
                )
                local tempGone = ((modifierIndex n modInst) == undefined)
                local countOk = (n.modifiers.count == protectedModifiers.count)
                if not protectedOk or not tempGone or not countOk then
                (
                    setLastMessage "塌陷后的读回检查发现原有修改器丢失、临时修改器残留或堆栈数量异常；本次处理判定失败。"
                    return false
                )
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
            setLastMessage ("塌陷 F2M 修改器失败：" + getCurrentException())
            false
        )
    ),

    fn meshCounts n =
    (
        local out = #(0, 0, 0)
        local m = undefined
        try
        (
            m = snapshotAsMesh n
            out[1] = getNumVerts m
            out[3] = getNumFaces m
            try(out[2] = meshop.getNumEdges m)catch(out[2] = out[3] * 3)
        )
        catch()
        try(if m != undefined do free m)catch()
        out
    ),

    fn transformWarnings n label =
    (
        local out = #()
        try
        (
            local p = n.pos
            if (length p) > 0.001 do append out (label + "位置不是 0,0,0：" + (p as string) + "。请检查模型位移是否归零。")
        )
        catch()
        try
        (
            local pivot = n.pivot
            if (length pivot) > 0.001 do append out (label + "轴心/坐标中心不是 0,0,0：" + (pivot as string) + "。请检查模型中心是否在原点。")
        )
        catch()
        try
        (
            local s = n.scale
            if (abs(s.x - 1.0) > 0.0001) or (abs(s.y - 1.0) > 0.0001) or (abs(s.z - 1.0) > 0.0001) do
            (
                append out (label + "缩放不是 100,100,100：" + (((s.x * 100.0) as string) + "," + ((s.y * 100.0) as string) + "," + ((s.z * 100.0) as string)) + "。请先 Reset XForm / 冻结缩放。")
            )
        )
        catch()
        try
        (
            local e = quatToEuler n.rotation
            if (abs(e.x) > 0.01) or (abs(e.y) > 0.01) or (abs(e.z) > 0.01) do
            (
                append out (label + "旋转不是 0,0,0：" + ((e.x as string) + "," + (e.y as string) + "," + (e.z as string)) + "。Maya 等 DCC 导入常见 90 度轴向旋转，请先处理轴向/冻结旋转。")
            )
        )
        catch()
        try
        (
            local tm = n.transform
            local ax = normalize [tm.row1.x, tm.row1.y, tm.row1.z]
            local ay = normalize [tm.row2.x, tm.row2.y, tm.row2.z]
            local az = normalize [tm.row3.x, tm.row3.y, tm.row3.z]
            if (length (ax - [1,0,0]) > 0.001) or (length (ay - [0,1,0]) > 0.001) or (length (az - [0,0,1]) > 0.001) do
            (
                append out (label + "世界变换矩阵轴向不是默认方向。请检查是否存在 FBX/Maya 轴向转换、90 度旋转或未冻结变换。")
            )
        )
        catch()
        try
        (
            local op = n.objectOffsetPos
            if (length op) > 0.001 do append out (label + "Object Offset 位置不是 0,0,0：" + (op as string) + "。请检查导入轴心/几何偏移。")
        )
        catch()
        try
        (
            local os = n.objectOffsetScale
            if (abs(os.x - 1.0) > 0.0001) or (abs(os.y - 1.0) > 0.0001) or (abs(os.z - 1.0) > 0.0001) do
            (
                append out (label + "Object Offset 缩放不是 100,100,100：" + (((os.x * 100.0) as string) + "," + ((os.y * 100.0) as string) + "," + ((os.z * 100.0) as string)) + "。请检查导入轴向/冻结缩放。")
            )
        )
        catch()
        try
        (
            local oe = quatToEuler n.objectOffsetRot
            if (abs(oe.x) > 0.01) or (abs(oe.y) > 0.01) or (abs(oe.z) > 0.01) do
            (
                append out (label + "Object Offset 旋转不是 0,0,0：" + ((oe.x as string) + "," + (oe.y as string) + "," + (oe.z as string)) + "。这通常就是 FBX 轴向转换或 90 度旋转残留。")
            )
        )
        catch()
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

    fn point3ToMapArray p =
    (
        #((p.x as integer), (p.y as integer), (p.z as integer))
    ),

    fn copyMapChannelDirect src dst channelId =
    (
        setLastMessage ""
        local ok = false
        try
        (
            if isPolyBase src and isPolyBase dst then
            (
                if not (polyop.getMapSupport src channelId) do throw ("FBX 目标模型没有通道 " + (channelId as string))
                local srcMapVerts = polyop.getNumMapVerts src channelId
                local srcMapFaces = polyop.getNumMapFaces src channelId
                if (polyop.getNumFaces dst) != srcMapFaces do throw ("Max 源模型 Poly 面数量与 FBX 目标模型通道面数量不一致，不能直接写入。")

                polyop.setMapSupport dst channelId true
                polyop.setNumMapVerts dst channelId srcMapVerts keep:false
                polyop.setNumMapFaces dst channelId srcMapFaces keep:false

                for i = 1 to srcMapVerts do
                (
                    polyop.setMapVert dst channelId i (polyop.getMapVert src channelId i)
                )
                for f = 1 to srcMapFaces do
                (
                    polyop.setMapFace dst channelId f (polyop.getMapFace src channelId f)
                )
                update dst
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
                if (getNumFaces dstMesh) != srcMapFaces do throw ("Max 源模型 Mesh 面数量与 FBX 目标模型通道面数量不一致，不能直接写入。")

                meshop.setMapSupport dstMesh channelId true
                meshop.setNumMapVerts dstMesh channelId srcMapVerts keep:false
                try(meshop.setNumMapFaces dstMesh channelId srcMapFaces keep:false)catch()

                for i = 1 to srcMapVerts do
                (
                    meshop.setMapVert dstMesh channelId i (meshop.getMapVert srcMesh channelId i)
                )
                for f = 1 to srcMapFaces do
                (
                    meshop.setMapFace dstMesh channelId f (meshop.getMapFace srcMesh channelId f)
                )
                update dst
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
            setLastMessage ("直接写入通道失败：" + getCurrentException())
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

        if pastedMod != undefined then
        (
            local collapseOk = collapseModifierSafely dst pastedMod
            if collapseOk then
            (
                setLastMessage ("ChannelInfo 通道 " + (channelId as string) + " 已粘贴并塌陷；" + lastMessage)
            )
            else
            (
                setLastMessage ("ChannelInfo 通道 " + (channelId as string) + " 已粘贴，但未能安全塌陷；" + lastMessage)
            )
            true
        )
        else
        (
            setLastMessage ("ChannelInfo 通道 " + (channelId as string) + " 已执行复制/粘贴，但没有找到新增修改器。")
            true
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

    fn getVertexUnnormalized n skinMod vertexIndex =
    (
        try
        (
            try
            (
                skinOps.isUnNormalizeVertex skinMod vertexIndex node:n
            )
            catch
            (
                if not activateModifier n skinMod do return undefined
                skinOps.isUnNormalizeVertex skinMod vertexIndex
            )
        )
        catch undefined
    ),

    fn getVertexUnnormalizedStates n skinMod vertexCount =
    (
        setLastMessage ""
        try
        (
            if not activateModifier n skinMod then
            (
                setLastMessage "无法激活 Skin 修改器。"
                return undefined
            )
            local states = #()
            for vertexIndex = 1 to vertexCount do
                append states ((skinOps.isUnNormalizeVertex skinMod vertexIndex) != 0)
            states
        )
        catch
        (
            setLastMessage ("批量读取顶点归一化状态失败：" + getCurrentException())
            undefined
        )
    ),

    fn setVertexUnnormalized n skinMod vertexIndex state =
    (
        setLastMessage ""
        try
        (
            if not activateModifier n skinMod then
            (
                setLastMessage "无法激活 Skin 修改器。"
                return false
            )
            skinOps.unNormalizeVertex skinMod vertexIndex state
            try(skinOps.Invalidate skinMod 0)catch()
            local actual = skinOps.isUnNormalizeVertex skinMod vertexIndex
            if actual != state do
            (
                setLastMessage ("归一化状态读回不一致：期望 " + state as string + "，实际 " + actual as string)
                return false
            )
            true
        )
        catch
        (
            setLastMessage ("设置顶点归一化状态失败：" + getCurrentException())
            false
        )
    ),

    fn prepareVertexUnnormalizedStates n skinMod states =
    (
        setLastMessage ""
        try
        (
            if not activateModifier n skinMod then
            (
                setLastMessage "无法激活 Skin 修改器。"
                return false
            )
            for vertexIndex = 1 to states.count where states[vertexIndex] != 0 do
                skinOps.unNormalizeVertex skinMod vertexIndex true
            try(skinOps.Invalidate skinMod 0)catch()
            for vertexIndex = 1 to states.count where states[vertexIndex] != 0 do
            (
                local actual = (skinOps.isUnNormalizeVertex skinMod vertexIndex) != 0
                if actual == false do
                (
                    setLastMessage ("写入前无法把顶点 " + vertexIndex as string + " 标记为未归一化。")
                    return false
                )
            )
            true
        )
        catch
        (
            setLastMessage (getCurrentException())
            false
        )
    ),

    fn setVertexUnnormalizedStates n skinMod states =
    (
        setLastMessage ""
        try
        (
            if not activateModifier n skinMod then
            (
                setLastMessage "无法激活 Skin 修改器。"
                return false
            )
            for vertexIndex = 1 to states.count do
                skinOps.unNormalizeVertex skinMod vertexIndex (states[vertexIndex] != 0)
            try(skinOps.Invalidate skinMod 0)catch()
            for vertexIndex = 1 to states.count do
            (
                local actual = (skinOps.isUnNormalizeVertex skinMod vertexIndex) != 0
                local expected = states[vertexIndex] != 0
                if actual != expected do
                (
                    setLastMessage (
                        "顶点 " + vertexIndex as string + " 归一化状态读回不一致：期望 " +
                        expected as string + "，实际 " + actual as string
                    )
                    return false
                )
            )
            true
        )
        catch
        (
            setLastMessage ("批量设置顶点归一化状态失败：" + getCurrentException())
            false
        )
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

    fn removeF2MNormalModifiers n =
    (
        local removed = 0
        try
        (
            for i = n.modifiers.count to 1 by -1 do
            (
                local m = n.modifiers[i]
                if classof m == Edit_Normals and matchPattern (m.name as string) pattern:"F2M_顶点法线*" ignoreCase:false do
                (
                    deleteModifier n i
                    removed += 1
                )
            )
        )
        catch()
        removed
    ),

    fn copyExplicitNormals src dst =
    (
        setLastMessage ""
        local srcMod = undefined
        local dstMod = undefined
        local ok = false
        local removedOldDstMods = 0
        local srcFaceCount = 0
        local srcNormalCount = 0
        local oldSelection = selection as array
        local srcReaderIsTemp = false

        try
        (
            srcMod = findEditNormals src
            if srcMod == undefined then
            (
                srcMod = Edit_Normals()
                addModifier src srcMod
                srcMod.name = "F2M_读取 FBX 目标模型法线"
                srcReaderIsTemp = true
            )
            try
            (
                activateModifier src srcMod
            )
            catch()

            srcFaceCount = srcMod.GetNumFaces()
            if srcFaceCount < 1 do throw "FBX 目标模型没有可读取的 Edit Normals 面数据。请确认导出 FBX 时保留了自定义法线。"
            try(srcNormalCount = srcMod.GetNumNormals())catch(srcNormalCount = 0)

            removedOldDstMods = removeF2MNormalModifiers dst

            dstMod = copy srcMod
            dstMod.name = "F2M_顶点法线"
            local copyDataError = ""
            try
            (
                addModifierWithLocalData dst dstMod src srcMod
            )
            catch
            (
                copyDataError = getCurrentException()
            )
            if copyDataError != "" do throw ("复制 Edit Normals 本地数据失败：" + copyDataError)

            local collapseOk = collapseModifierSafely dst dstMod
            if not collapseOk do throw ("已复制 Edit Normals，但移动到底部/塌陷失败：" + lastMessage)

            local extra = ""
            if removedOldDstMods > 0 do extra += ("；已移除旧 F2M 法线修改器 " + (removedOldDstMods as string) + " 个")
            if srcFaceCount > 0 do extra += ("；FBX 目标模型面数 " + (srcFaceCount as string))
            if srcNormalCount > 0 do extra += ("；FBX 目标模型法线数量 " + (srcNormalCount as string))
            setLastMessage ("顶点法线完成：已从 FBX 目标模型读取 Edit Normals，将本地法线数据复制到 Max 源模型，并把修改器移动到堆栈底部" + extra + "。")
            ok = true
        )
        catch
        (
            setLastMessage ("顶点法线失败：" + getCurrentException())
            ok = false
        )

        try(if srcReaderIsTemp and srcMod != undefined do deleteModifier src srcMod)catch()
        if not ok do try(removeF2MNormalModifiers dst)catch()
        try(select oldSelection)catch()
        ok
    ),

    fn copyBaseVertexPositions src dst =
    (
        local srcMesh = undefined
        local baseName = ""
        local ok = false
        try
        (
            srcMesh = snapshotAsMesh src
            baseName = (classof dst.baseObject) as string
            local srcTM = src.objectTransform
            local dstInvTM = inverse dst.objectTransform

            if baseName == "Editable_Poly" then
            (
                if (polyop.getNumVerts dst) != (getNumVerts srcMesh) do throw "点数不一致"
                for i = 1 to (getNumVerts srcMesh) do
                (
                    local p = ((getVert srcMesh i) * srcTM) * dstInvTM
                    polyop.setVert dst i p
                )
                update dst
                ok = true
            )
            else if baseName == "Editable_mesh" or baseName == "Editable Mesh" then
            (
                if (getNumVerts dst) != (getNumVerts srcMesh) do throw "点数不一致"
                for i = 1 to (getNumVerts srcMesh) do
                (
                    local p = ((getVert srcMesh i) * srcTM) * dstInvTM
                    setVert dst i p
                )
                update dst
                ok = true
            )
            else
            (
                throw ("Max 源模型基础对象不是 Editable Poly / Editable Mesh，而是 " + baseName)
            )
        )
        catch
        (
            ok = false
        )
        try(if srcMesh != undefined do free srcMesh)catch()
        ok
    ),

    fn captureBaseVertexPositions n =
    (
        local verts = #()
        try
        (
            local baseName = baseClassName n
            if baseName == "Editable_Poly" then
            (
                for i = 1 to (polyop.getNumVerts n) do append verts (polyop.getVert n i)
                verts
            )
            else if baseName == "Editable_mesh" or baseName == "Editable Mesh" then
            (
                for i = 1 to (getNumVerts n) do append verts (getVert n i)
                verts
            )
            else
            (
                undefined
            )
        )
        catch(undefined)
    ),

    fn restoreBaseVertexPositions n verts =
    (
        setLastMessage ""
        local ok = false
        try
        (
            if verts == undefined do throw "没有可恢复的 Max 源模型点位快照。"
            local baseName = baseClassName n
            if baseName == "Editable_Poly" then
            (
                if (polyop.getNumVerts n) != verts.count do throw "Max 源模型点数已经变化，无法恢复原外形。"
                for i = 1 to verts.count do polyop.setVert n i verts[i]
                update n
                ok = true
            )
            else if baseName == "Editable_mesh" or baseName == "Editable Mesh" then
            (
                if (getNumVerts n) != verts.count do throw "Max 源模型点数已经变化，无法恢复原外形。"
                for i = 1 to verts.count do setVert n i verts[i]
                update n
                ok = true
            )
            else
            (
                throw ("Max 源模型基础对象不是 Editable Poly / Editable Mesh，而是 " + baseName)
            )
        )
        catch
        (
            setLastMessage ("恢复 Max 源模型外形失败：" + getCurrentException())
            ok = false
        )

        if ok do setLastMessage "已恢复 Max 源模型外形。"
        ok
    ),

    fn copyMaterialIdsDirect src dst =
    (
        setLastMessage ""
        local ok = false
        try
        (
            if isPolyBase src and isPolyBase dst then
            (
                local faceCount = polyop.getNumFaces src
                if (polyop.getNumFaces dst) != faceCount do throw "FBX 目标模型与 Max 源模型的 Editable Poly 多边形数量不一致，不能直接写入材质 ID。"
                for f = 1 to faceCount do
                (
                    local faceSet = #{}
                    faceSet[f] = true
                    polyop.setFaceMatID dst faceSet (polyop.getFaceMatID src f)
                )
                update dst
                setLastMessage ("材质 ID：已按 Editable Poly 多边形直接写入 " + (faceCount as string) + " 个面，没有改变 Max 源模型外形。")
                ok = true
            )
            else if isMeshBase src and isMeshBase dst then
            (
                local srcMesh = src.mesh
                local faceCount = getNumFaces srcMesh
                if (getNumFaces dst) != faceCount do throw "FBX 目标模型与 Max 源模型的 Editable Mesh 面数量不一致，不能直接写入材质 ID。"
                for f = 1 to faceCount do
                (
                    setFaceMatID dst f (getFaceMatID srcMesh f)
                )
                update dst
                setLastMessage ("材质 ID：已按 Editable Mesh 面直接写入 " + (faceCount as string) + " 个面，没有改变 Max 源模型外形。")
                ok = true
            )
            else
            (
                throw "FBX 目标模型与 Max 源模型的基础类型不是同类 Editable Poly 或同类 Editable Mesh。"
            )
        )
        catch
        (
            setLastMessage ("材质 ID：直接按面写入不可用：" + getCurrentException())
            ok = false
        )
        ok
    ),

    fn copyMaterialIds src dst =
    (
        local directOk = copyMaterialIdsDirect src dst
        if directOk do return true

        local directMsg = lastMessage
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
        for handleValue in handles do
        (
            local nodeValue = undefined
            try(nodeValue = getAnimByHandle handleValue)catch()
            if nodeValue != undefined and isValidNode nodeValue do
            (
                if not (detachModifierPanelFromNodeIfNeeded nodeValue) then
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

    fn fbxImporterGet name =
    (
        try(FBXImporterGetParam name)catch(undefined)
    ),

    fn fbxImporterSet name value =
    (
        try(FBXImporterSetParam name value)catch(undefined)
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
            local xrefItem = objXRefMgr.IsNodeXRefed n
            if xrefItem != undefined and (findItem out "对象来自 XRef/外部引用，不能安全直接改写基础网格。") == 0 do
                append out "对象来自 XRef/外部引用，不能安全直接改写基础网格。"
        )
        catch()
        out
    )
)

F2M_SkinHelper = F2M_SkinHelperStruct()
F2M_Helper = F2M_SkinHelper
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
    mode: str = "replace"
    dry_run: bool = False
    transfer_shape: bool = True
    transfer_uv: bool = True
    uv_channels: List[int] = field(default_factory=lambda: [1])
    transfer_normals: bool = False
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


@dataclass
class CommittedReplacement:
    target_record: SceneRecord
    candidate_handle: int
    candidate_name: str
    old_hidden: bool
    report: ObjectReport


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
        self.missing_transfer_attrs: List[str] = []
        self.reports: List[ObjectReport] = []
        self.safety_errors: List[str] = []
        self.committed_replacements: List[CommittedReplacement] = []
        self.diagnostics: List[str] = []


def ensure_runtime() -> None:
    if rt is None:
        raise RuntimeError("这个脚本需要在 3ds Max 的 Python 环境中运行。")
    helper_ready = False
    try:
        helper = rt.F2M_SkinHelper
        helper_ready = (
            str(helper.apiKind) == "skin"
            and str(helper.apiVersion) == TOOL_VERSION
        )
    except Exception:
        helper_ready = False
    if not helper_ready:
        rt.execute(HELPER_SCRIPT)
        try:
            helper = rt.F2M_SkinHelper
            helper_ready = (
                str(helper.apiKind) == "skin"
                and str(helper.apiVersion) == TOOL_VERSION
            )
        except Exception:
            helper_ready = False
    if not helper_ready:
        raise RuntimeError("蒙皮替换运行核心没有正确注册，请重新安装插件。")
    rt.globalVars.set(rt.Name("F2M_Helper"), helper)


def ensure_maxscript_heap_reserve() -> Tuple[int, int]:
    """Reserve the same session heap used by dense Mode 1 normal transfers."""

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
            "MaxScript 内存堆没有达到连续模型处理所需的安全下限；"
            "已停止传递。"
        )
    return before_value, after_value


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
            # 3ds Max 的原生谓词可以安全接收已经被删除的 MXSWrapper。
            # 不要用 node.name 探测这类 wrapper；即使 Python 捕获异常，
            # MaxScript Listener / Max.log 仍会先写入一次原生访问错误。
            return bool(native_predicate(node))
        except Exception:
            return False
    try:
        # 只给普通 Python 假对象/极旧宿主保留兼容兜底。正式支持的
        # 3ds Max 2023+ 始终走上面的 isValidNode，不会解引用已删除节点。
        _ = node.name
        return True
    except Exception:
        return False


def node_by_handle(handle: int) -> Optional[Any]:
    try:
        node = rt.getAnimByHandle(int(handle))
    except Exception:
        return None
    return node if is_valid_node(node) else None


def _live_nodes_by_handle(
    handles: Optional[Iterable[int]] = None,
) -> Dict[int, Any]:
    wanted = None if handles is None else {int(handle) for handle in handles}
    if wanted is not None:
        result: Dict[int, Any] = {}
        for handle in wanted:
            node = node_by_handle(handle)
            if node is not None:
                result[handle] = node
        return result
    result: Dict[int, Any] = {}
    for node in all_scene_nodes():
        if not is_valid_node(node):
            continue
        try:
            handle = node_handle(node)
        except Exception:
            continue
        if wanted is None or handle in wanted:
            result[handle] = node
    return result


def _delete_node_handles_strict(
    handles: Iterable[int],
    names_by_handle: Optional[Dict[int, str]] = None,
    label: str = "节点",
) -> Dict[int, Any]:
    """批量删除句柄对应节点，删除后只靠重新枚举场景进行读回。

    Autodesk 的 MAXScript ``delete`` 是 collection-mapped 操作。批量数组
    完全在 MAXScript helper 内按句柄解析和释放，Python 不持有待删 wrapper
    数组；只有批量调用报告节点仍存活时，才按句柄重新解析做兼容兜底。
    """

    wanted = {int(handle) for handle in handles}
    if not wanted:
        return {}
    labels = {
        int(handle): str(name)
        for handle, name in (names_by_handle or {}).items()
    }
    ordered_handles = sorted(wanted)
    failure = ""
    try:
        raw_leftovers = rt.F2M_Helper.deleteNodesByHandles(
            max_array(ordered_handles)
        )
        raw_values = (
            []
            if raw_leftovers is None or str(raw_leftovers) == "undefined"
            else list(raw_leftovers)
        )
        leftovers = {int(handle) for handle in raw_values}
    except Exception as exc:
        leftovers = set(ordered_handles)
        failure = f"{label}批量删除失败：{visible_exception_text(exc)}"
        detail = helper_message()
        if detail:
            failure += f"；{detail}"

    fallback_failures: List[str] = []
    for handle in sorted(leftovers):
        try:
            rt.F2M_Helper.deleteNodesByHandles(max_array([handle]))
        except Exception as exc:
            fallback_failures.append(
                f"{labels.get(handle, str(handle))}："
                f"{visible_exception_text(exc)}"
            )

    remaining = _live_nodes_by_handle(wanted)
    remaining_labels = [
        labels.get(handle, str(handle))
        for handle in sorted(remaining)
    ]
    failures = [text for text in (failure,) if text]
    failures.extend(fallback_failures)
    if remaining_labels:
        failures.append("删除后仍存在：" + "，".join(remaining_labels))
    remaining_after = dict(remaining)
    remaining.clear()
    if failures:
        raise RuntimeError(f"{label}清理失败；" + "；".join(failures))
    return remaining_after


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
    nodes = [node for node in all_scene_nodes() if is_valid_node(node)]
    # 必须先记住完整的原场景句柄；即使改名中途失败，清理也不能误删原节点。
    ctx.pre_handles = {node_handle(node) for node in nodes}
    for index, node in enumerate(nodes, start=1):
        handle = node_handle(node)
        original = str(node.name)
        temp = unique_temp_name(ctx.prefix, index, original)
        record = SceneRecord(handle=handle, original_name=original, temp_name=temp, node=node)
        register_record(ctx, record)
        try:
            node.name = temp
            if str(node.name) != temp:
                raise RuntimeError("临时名称读回不一致")
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
        if not is_valid_node(record.node):
            failures.append(f"{record.temp_name} -> {record.original_name}（节点已不存在）")
            continue
        try:
            record.node.name = record.original_name
            if str(record.node.name) != record.original_name:
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


def _importer_value_key(value: Any) -> str:
    return str(value).strip().lower().lstrip("#")


_BOOLEAN_IMPORTER_PARAMS = {"Animation", "Skin", "SmoothingGroups"}


def _snapshot_importer_value(name: str, value: Any) -> Any:
    """Keep Boolean FBX settings Boolean when they later cross into MAXScript."""

    if name not in _BOOLEAN_IMPORTER_PARAMS:
        return value
    text = _importer_value_key(value)
    if text in {"true", "1", "1.0"}:
        return True
    if text in {"false", "0", "0.0"}:
        return False
    raise RuntimeError(f"FBX 导入器布尔参数 {name} 返回无效值：{value}")


def _importer_values_equal(name: str, expected: Any, actual: Any) -> bool:
    if name in _BOOLEAN_IMPORTER_PARAMS:
        return _snapshot_importer_value(
            name,
            expected,
        ) == _snapshot_importer_value(name, actual)
    return _importer_value_key(actual) == _importer_value_key(expected)


def _snapshot_fbx_importer(ctx: TransferContext) -> Dict[str, Any]:
    try:
        rt.execute("pluginManager.loadClass FbxImporter")
    except Exception:
        pass

    snapshot: Dict[str, Any] = {}
    for name in ("Mode", "Animation", "Skin", "SmoothingGroups"):
        try:
            value = rt.F2M_Helper.fbxImporterGet(name)
            if not _valid_importer_value(value):
                raise RuntimeError("返回 undefined/unsupplied")
            snapshot[name] = _snapshot_importer_value(name, value)
        except Exception as exc:
            raise RuntimeError(f"无法读取 FBX 导入器参数 {name}，为避免污染用户全局预设已停止：{exc}") from exc
    return snapshot


def _set_fbx_importer_param(name: str, value: Any) -> None:
    result = rt.F2M_Helper.fbxImporterSet(name, value)
    if not _valid_importer_value(result):
        raise RuntimeError(f"FBX 导入器拒绝参数 {name}={value}")
    readback = rt.F2M_Helper.fbxImporterGet(name)
    if not _valid_importer_value(readback) or not _importer_values_equal(
        name,
        value,
        readback,
    ):
        raise RuntimeError(f"FBX 导入参数 {name} 读回不一致：期望 {value}，实际 {readback}")


def _restore_fbx_importer(ctx: TransferContext, snapshot: Dict[str, Any]) -> None:
    failures: List[str] = []
    for name, value in snapshot.items():
        try:
            result = rt.F2M_Helper.fbxImporterSet(name, value)
            readback = rt.F2M_Helper.fbxImporterGet(name)
            if (
                not _valid_importer_value(result)
                or not _valid_importer_value(readback)
                or not _importer_values_equal(name, value, readback)
            ):
                failures.append(f"{name}（读回 {readback}）")
        except Exception as exc:
            failures.append(f"{name}（{exc}）")
    if failures:
        message = "无法恢复 FBX 导入器全局参数：" + "，".join(failures)
        ctx.safety_errors.append(message)
        raise RuntimeError(message)


def configure_fbx_import(ctx: TransferContext) -> Dict[str, Any]:
    snapshot = _snapshot_fbx_importer(ctx)
    try:
        _set_fbx_importer_param("Mode", rt.Name("create"))
        _set_fbx_importer_param("Animation", False)
        _set_fbx_importer_param("Skin", True)
        # 模式二直接保留 FBX 导入节点作为最终网格。开启 SmoothingGroups
        # 会让导入器用 Max 光滑组重建着色，可能覆盖 Maya/Blender 写入的
        # 面角显式法线；沿用成熟版行为，关闭它以优先保留自定义法线。
        _set_fbx_importer_param("SmoothingGroups", False)
    except Exception as exc:
        try:
            _restore_fbx_importer(ctx, snapshot)
        except Exception as restore_exc:
            raise RuntimeError(f"FBX 导入设置失败且原设置恢复失败：{exc}；{restore_exc}") from exc
        raise RuntimeError(f"无法建立隔离的 FBX 蒙皮导入设置：{exc}") from exc

    ctx.log.add(
        "FBX 导入设置：导入模式=创建，动画=关闭，蒙皮=开启，"
        "光滑组导入=关闭（优先保留 FBX 显式/自定义法线）。"
    )
    return snapshot


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


def import_fbx(ctx: TransferContext) -> None:
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
    snapshot = configure_fbx_import(ctx)
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
        raise RuntimeError("；".join(parts)) from None
    if not new_nodes:
        raise RuntimeError("FBX 导入没有创建任何节点。")

    ctx.imported_nodes = list(new_nodes)
    ctx.log.add(f"已导入 FBX：{path}")
    ctx.log.add(f"导入节点数量：{len(new_nodes)}")


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
        raise RuntimeError("请在 Max 场景里选中至少 1 个要替换的 Max 源网格。")

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


def topo_same_for_shape(src: Any, dst: Any) -> bool:
    return mesh_counts(src)[0] == mesh_counts(dst)[0]


def topo_same_for_channels(src: Any, dst: Any) -> bool:
    return mesh_counts(src) == mesh_counts(dst)


def has_map_channel(node: Any, channel: int) -> bool:
    try:
        return bool(rt.F2M_Helper.hasMapChannel(node, int(channel)))
    except Exception:
        return False


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


def _reset_max_file_safely() -> None:
    """Detach the doomed panel object, then reset the isolated scene."""

    if not release_modifier_panel_reference():
        raise RuntimeError(
            "无法在重置场景前解除 Modify 面板原生对象引用；已停止重置。"
        )
    try:
        rt.clearSelection()
    except Exception:
        pass
    rt.resetMaxFile(rt.Name("noPrompt"))


def node_state_warnings(node: Any) -> List[str]:
    try:
        return [str(item) for item in list(rt.F2M_Helper.nodeStateWarnings(node))]
    except Exception:
        return []


def transform_warnings(node: Any, label: str) -> List[str]:
    try:
        return [str(item) for item in list(rt.F2M_Helper.transformWarnings(node, label))]
    except Exception:
        return []


def transform_pair_warnings(fbx_target: Any, max_source: Any) -> List[str]:
    """Warn only about a relative mismatch, not matching non-zero TRS."""

    try:
        fbx_values = _matrix3_tuple(
            fbx_target.objectTransform,
            "FBX 目标 ObjectTransform",
        )
        max_values = _matrix3_tuple(
            max_source.objectTransform,
            "Max 源 ObjectTransform",
        )
        delta = max(
            abs(float(left) - float(right))
            for left, right in zip(fbx_values, max_values)
        )
        if delta <= 0.001:
            return []
        return [
            "FBX 目标模型与 Max 源模型的对象空间变换不同"
            f"（矩阵最大分量差 {delta:.9f}）。模式二会保留 FBX 候选变换，"
            "并在提交前逐顶点验证启用 Skin 后的世界空间外观；验证失败会保留"
            "原 Max 源模型并停止提交。"
        ]
    except Exception as exc:
        return [f"无法成对比较 FBX/Max 对象空间变换：{exc}"]


def copy_shape(src: Any, dst: Any, report: ObjectReport) -> bool:
    if not topo_same_for_shape(src, dst):
        report.add("变形：跳过，点数不一致。")
        return False
    ok = bool(rt.F2M_Helper.copyBaseVertexPositions(src, dst))
    if ok:
        report.add("变形：完成，直接写入 Max 源模型基础网格，Skin 修改器未删除。")
    else:
        base_name = str(rt.F2M_Helper.baseClassName(dst))
        report.add(f"变形：失败，Max 源模型基础对象不是可直接写入的 Editable Poly / Editable Mesh（当前：{base_name}）。")
    return ok


def copy_uv_channels(src: Any, dst: Any, channels: Sequence[int], report: ObjectReport) -> bool:
    ok_any = False
    if not topo_same_for_channels(src, dst):
        report.add("UV：跳过，点/边/面数量不完全一致。")
        return False
    for channel in channels:
        if not has_map_channel(src, channel):
            report.add(f"UV 通道 {channel}：跳过，FBX 目标模型没有这个通道。")
            continue
        try:
            direct_ok = bool(rt.F2M_Helper.copyMapChannelDirect(src, dst, int(channel)))
            msg = helper_message()
            if direct_ok:
                report.add(f"UV 通道 {channel}：完成。{msg}")
                ok_any = True
                continue

            report.add(f"UV 通道 {channel}：直接写入不可用，准备使用 ChannelInfo。{msg}")
            ok = bool(rt.F2M_Helper.copyMapChannel(src, dst, int(channel)))
            msg = helper_message()
            if ok:
                report.add(f"UV 通道 {channel}：完成。{msg}")
                ok_any = True
            else:
                report.add(f"UV 通道 {channel}：失败。{msg}")
        except Exception as exc:
            report.add_exception(f"UV 通道 {channel}：失败。", exc)
    return ok_any


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
    if ctx.options.dry_run:
        return
    if ctx.options.transfer_uv:
        for channel in ctx.options.uv_channels:
            if not has_map_channel(src, channel):
                record_missing_transfer_attr(ctx, report, f"传递 UV {channel}")
    if ctx.options.transfer_vertex_color and not has_map_channel(src, 0):
        record_missing_transfer_attr(ctx, report, "顶点色 RGB")
    if ctx.options.transfer_alpha and not has_map_channel(src, -2):
        record_missing_transfer_attr(ctx, report, "顶点 Alpha")


def copy_vertex_channel(src: Any, dst: Any, channel: int, label: str, report: ObjectReport) -> bool:
    if not topo_same_for_channels(src, dst):
        report.add(f"{label}：跳过，点/边/面数量不完全一致。")
        return False
    if not has_map_channel(src, channel):
        report.add(f"{label}：跳过，FBX 目标模型没有通道 {channel}。")
        return False
    try:
        direct_ok = bool(rt.F2M_Helper.copyMapChannelDirect(src, dst, int(channel)))
        msg = helper_message()
        if direct_ok:
            report.add(f"{label}：完成。{msg}")
            return True

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


def copy_normals(src: Any, dst: Any, report: ObjectReport) -> bool:
    if not topo_same_for_channels(src, dst):
        report.add("顶点法线：跳过，点/边/面数量不完全一致。")
        return False
    try:
        ok = bool(rt.F2M_Helper.copyExplicitNormals(src, dst))
        msg = helper_message()
        if ok:
            report.add(msg or "顶点法线：完成。")
            return True
        report.add(msg or "顶点法线：失败。")
        return False
    except Exception as exc:
        report.add_exception("顶点法线：失败。", exc)
        return False


def copy_material_ids(src: Any, dst: Any, report: ObjectReport) -> bool:
    if not topo_same_for_channels(src, dst):
        report.add("材质与 ID：跳过，点/边/面数量不完全一致。")
        return False

    material_ok = False
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

    ok = bool(rt.F2M_Helper.copyMaterialIds(src, dst))
    msg = helper_message()
    if ok:
        report.add(msg or "材质 ID：完成，已通过 ChannelInfo 多边形通道复制。")
    else:
        report.add(msg or "材质 ID：失败，ChannelInfo 多边形通道复制没有成功。")
    return material_ok and ok


@dataclass(frozen=True)
class SkinBoneEntry:
    bone_id: int
    full_name: str
    node: Any


@dataclass
class SkinBoneLookup:
    entries: List[SkinBoneEntry]
    exact: Dict[str, List[SkinBoneEntry]]
    normalized: Dict[str, List[SkinBoneEntry]]


@dataclass(frozen=True)
class SkinVertexState:
    unnormalized: bool
    dq_weight: float


@dataclass(frozen=True)
class SkinModifierState:
    enable_dq: bool
    property_values: Tuple[Tuple[str, Any], ...] = ()
    mesh_bind_tm: Tuple[float, ...] = ()


@dataclass(frozen=True)
class SkinCrossSectionState:
    u: float
    inner_radius: float
    outer_radius: float


@dataclass(frozen=True)
class SkinBoneState:
    full_name: str
    falloff: int
    relative: int
    envelope_visible: int
    start_point: Tuple[float, float, float]
    end_point: Tuple[float, float, float]
    cross_sections: Tuple[SkinCrossSectionState, ...]
    bind_tm: Tuple[float, ...]
    stretch_tm: Tuple[float, ...]


@dataclass(frozen=True)
class CandidateAuthoritySnapshot:
    node_handle: int
    base_object_handle: int
    material_handle: Optional[int]
    mesh_counts: Tuple[int, int, int]
    object_transform: Tuple[float, ...]
    pivot: Tuple[float, float, float]
    non_skin_modifiers: Tuple[Tuple[int, str, str], ...]
    layer_name: str
    is_hidden: bool
    layer_is_hidden: bool
    is_frozen: bool
    box_mode: bool
    renderable: bool
    visibility: bool
    evaluated_world_positions: Tuple[Tuple[float, float, float], ...]
    evaluated_world_bbox: Tuple[float, float, float, float, float, float]


@dataclass(frozen=True)
class TargetPresentationState:
    """Scene-wrapper state that belongs to the Max target, not the FBX file."""

    layer_name: str
    is_node_hidden: bool
    is_node_frozen: bool
    box_mode: bool
    renderable: bool
    visibility: bool


# 这里只保存会改变实际蒙皮结果或 FBX Skin 语义的公开属性；纯界面选择、
# 画笔窗口位置、镜像预览等临时 UI 状态不应被写进最终资产。
SKIN_SEMANTIC_PROPERTY_SCHEMA: Tuple[Tuple[str, str], ...] = (
    ("ref_frame", "int"),
    ("always_deform", "bool"),
    ("backTransform", "bool"),
    ("bone_Limit", "int"),
    ("rigid_vertices", "bool"),
    ("rigid_handles", "bool"),
    ("weightAllVertices", "bool"),
    ("clearZeroLimit", "float"),
    ("ignoreBoneScale", "bool"),
    ("animatableEnvelopes", "bool"),
    ("initialStaticEnvelope", "bool"),
    ("initialInnerEnvelopePercent", "float"),
    ("initialOuterEnvelopePercent", "float"),
    ("initialEnvelopeInner", "float"),
    ("initialEnvelopeOuter", "float"),
)


def scene_record_for_node(ctx: TransferContext, node: Any) -> Optional[SceneRecord]:
    try:
        handle = node_handle(node)
    except Exception:
        return None
    for record in ctx.scene_records:
        if record.handle == handle:
            return record
    return None


def original_name_for_node(ctx: TransferContext, node: Any) -> str:
    record = scene_record_for_node(ctx, node)
    if record is not None:
        return record.original_name
    try:
        return str(node.name)
    except Exception:
        return ""


def _finite_float_tuple(values: Iterable[Any], label: str) -> Tuple[float, ...]:
    result = tuple(float(value) for value in values)
    if not result or any(not math.isfinite(value) for value in result):
        raise RuntimeError(f"{label} 含无效数值：{result}")
    return result


def _point3_tuple(value: Any, label: str) -> Tuple[float, float, float]:
    values = _finite_float_tuple(
        (value.x, value.y, value.z),
        label,
    )
    return (values[0], values[1], values[2])


def _matrix3_tuple(value: Any, label: str) -> Tuple[float, ...]:
    values: List[float] = []
    for row_name in ("row1", "row2", "row3", "row4"):
        row = getattr(value, row_name)
        values.extend(_point3_tuple(row, f"{label}.{row_name}"))
    return _finite_float_tuple(values, label)


def _point3_value(values: Sequence[float]) -> Any:
    if len(values) != 3:
        raise RuntimeError(f"Point3 快照长度错误：{len(values)}")
    return rt.Point3(float(values[0]), float(values[1]), float(values[2]))


def _matrix3_value(values: Sequence[float]) -> Any:
    if len(values) != 12:
        raise RuntimeError(f"Matrix3 快照长度错误：{len(values)}")
    return rt.Matrix3(
        _point3_value(values[0:3]),
        _point3_value(values[3:6]),
        _point3_value(values[6:9]),
        _point3_value(values[9:12]),
    )


def _evaluated_world_positions(
    node: Any,
) -> Tuple[Tuple[float, float, float], ...]:
    """Read the evaluated result independently from Skin table read-backs."""

    mesh = None
    try:
        mesh = rt.snapshotAsMesh(node)
        if mesh is None or is_max_undefined(mesh):
            raise RuntimeError("snapshotAsMesh 没有返回有效网格。")
        transform = node.objectTransform
        vertex_count = int(rt.getNumVerts(mesh))
        if vertex_count < 1:
            raise RuntimeError("评估后网格没有顶点。")
        return tuple(
            _point3_tuple(
                rt.getVert(mesh, vertex_index) * transform,
                f"评估后世界顶点 {vertex_index}",
            )
            for vertex_index in range(1, vertex_count + 1)
        )
    except Exception as exc:
        raise RuntimeError(f"读取 FBX 候选评估后世界顶点失败：{exc}") from exc
    finally:
        if mesh is not None and not is_max_undefined(mesh):
            try:
                rt.free(mesh)
            except Exception:
                pass


def _world_bbox(
    positions: Sequence[Sequence[float]],
) -> Tuple[float, float, float, float, float, float]:
    if not positions:
        raise RuntimeError("无法从空世界顶点集合计算包围盒。")
    values = tuple(
        min(float(point[axis]) for point in positions)
        for axis in range(3)
    ) + tuple(
        max(float(point[axis]) for point in positions)
        for axis in range(3)
    )
    return _finite_float_tuple(values, "评估后世界包围盒")  # type: ignore[return-value]


def mode2_world_position_tolerance(
    expected_point: Sequence[float],
    actual_point: Sequence[float],
) -> float:
    """Return the bounded float32 read-back tolerance for one world point.

    Mode 2 compares an FBX Skin evaluation with an equivalent Max-scene Skin
    rebuilt through ``addModifierWithLocalData``.  Both paths cross several
    Point3/Matrix3/Skin float32 operations.  A fixed tolerance becomes smaller
    than a few representable steps at large coordinates, so retain the former
    0.001 cm floor and add the same 2 ppm coordinate-scale budget used by the
    mature Mode-1 point read-back.  Invalid inputs never receive a tolerance.
    """

    if len(expected_point) != 3 or len(actual_point) != 3:
        raise ValueError("模式二世界点必须各自包含 3 个有限坐标。")
    values = tuple(float(value) for value in (*expected_point, *actual_point))
    if any(not math.isfinite(value) for value in values):
        raise ValueError("模式二世界点包含无效坐标。")
    coordinate_scale = max(1.0, *(abs(value) for value in values))
    scale_aware = (
        MODE2_WORLD_POSITION_ROUNDTRIP_FLOOR
        + coordinate_scale * MODE2_WORLD_POSITION_SCALE_FACTOR
    )
    return max(MODE2_WORLD_POSITION_ABSOLUTE_FLOOR, scale_aware)


def _mode2_world_point_metrics(
    expected_point: Sequence[float],
    actual_point: Sequence[float],
) -> Tuple[float, float, float]:
    tolerance = mode2_world_position_tolerance(expected_point, actual_point)
    delta = math.sqrt(
        sum(
            (float(expected) - float(actual)) ** 2
            for expected, actual in zip(expected_point, actual_point)
        )
    )
    coordinate_scale = max(
        1.0,
        *(abs(float(value)) for value in (*expected_point, *actual_point)),
    )
    return delta, tolerance, coordinate_scale


def _candidate_visibility_state(
    node: Any,
) -> Tuple[bool, bool, bool, bool, bool, bool]:
    try:
        layer = node.layer
        values = (
            bool(node.isHidden),
            bool(layer.isHidden),
            bool(node.isFrozen),
            bool(node.boxMode),
            bool(node.renderable),
            bool(node.visibility),
        )
    except Exception as exc:
        raise RuntimeError(f"读取 FBX 候选可见性状态失败：{exc}") from exc
    return values


def target_presentation_state(node: Any) -> TargetPresentationState:
    try:
        layer_name = str(node.layer.name)
        is_node_hidden = bool(node.isNodeHidden)
        is_node_frozen = bool(node.isNodeFrozen)
        box_mode = bool(node.boxMode)
        renderable = bool(node.renderable)
        visibility = bool(node.visibility)
    except Exception as exc:
        raise RuntimeError(f"读取 Max 源模型图层/显示状态失败：{exc}") from exc
    if not layer_name:
        raise RuntimeError("Max 源模型所在图层名称为空。")
    return TargetPresentationState(
        layer_name=layer_name,
        is_node_hidden=is_node_hidden,
        is_node_frozen=is_node_frozen,
        box_mode=box_mode,
        renderable=renderable,
        visibility=visibility,
    )


def apply_target_presentation_state(
    node: Any,
    state: TargetPresentationState,
) -> None:
    """Move the replacement into the target's scene presentation context."""

    try:
        layer = rt.LayerManager.getLayerFromName(state.layer_name)
        if layer is None or is_max_undefined(layer):
            raise RuntimeError(f"找不到原图层：{state.layer_name}")
        layer.addNode(node)
        # isHidden/isFrozen are aggregate node-or-layer properties.  Writing
        # them can mutate the whole layer; only copy the node-local flags.
        presentation_args = (
            int(state.is_node_hidden),
            int(state.is_node_frozen),
            int(state.box_mode),
            int(state.renderable),
            int(state.visibility),
        )
        if pymxs is None:
            ok = bool(
                rt.F2M_Helper.setNodePresentationFlags(
                    node,
                    *presentation_args,
                )
            )
        else:
            # Calling a MAXScript Boolean setter through pymxs can expose a
            # Python True as 1.0d0 in Max 2023.  Evaluate only validated
            # numeric literals in MAXScript so its own != operator creates the
            # native Boolean values without an FPValue conversion error.
            numeric_args = " ".join(str(value) for value in presentation_args)
            script = (
                "F2M_Helper.setNodePresentationFlags "
                f"(getAnimByHandle {node_handle(node)}) {numeric_args}"
            )
            ok = bool(rt.execute(script))
        if not ok:
            raise RuntimeError(helper_message() or "MAXScript 图层/显示状态写入失败。")
        actual = target_presentation_state(node)
    except Exception as exc:
        raise RuntimeError(f"应用 Max 源模型图层/显示状态失败：{exc}") from exc
    if actual != state:
        raise RuntimeError(
            "Max 源模型图层/显示状态写后读回不一致："
            f"期望 {state}，实际 {actual}"
        )


def _anim_handle_or_none(value: Any) -> Optional[int]:
    if value is None or is_max_undefined(value):
        return None
    try:
        return int(rt.getHandleByAnim(value))
    except Exception as exc:
        raise RuntimeError(f"无法读取 Animatable 句柄：{exc}") from exc


def candidate_authority_snapshot(
    node: Any,
    skin_to_exclude: Any,
) -> CandidateAuthoritySnapshot:
    if not is_valid_node(node):
        raise RuntimeError("FBX 目标候选节点已经无效。")
    skin_handle = _anim_handle_or_none(skin_to_exclude)
    try:
        base_handle = _anim_handle_or_none(node.baseObject)
    except Exception as exc:
        raise RuntimeError(f"无法读取 FBX 目标基础对象身份：{exc}") from exc
    if base_handle is None:
        raise RuntimeError("FBX 目标基础对象没有稳定句柄。")

    try:
        material_handle = _anim_handle_or_none(node.material)
    except Exception as exc:
        raise RuntimeError(f"无法读取 FBX 目标材质身份：{exc}") from exc

    non_skin_modifiers: List[Tuple[int, str, str]] = []
    try:
        modifiers = list(node.modifiers)
    except Exception as exc:
        raise RuntimeError(f"无法读取 FBX 目标修改器栈：{exc}") from exc
    for modifier in modifiers:
        modifier_handle = _anim_handle_or_none(modifier)
        if modifier_handle is None:
            raise RuntimeError("FBX 目标修改器没有稳定句柄。")
        if skin_handle is not None and modifier_handle == skin_handle:
            continue
        non_skin_modifiers.append(
            (
                modifier_handle,
                str(rt.classOf(modifier)),
                str(modifier.name),
            )
        )

    try:
        object_transform = _matrix3_tuple(
            node.objectTransform,
            "FBX 目标 ObjectTransform",
        )
        pivot = _point3_tuple(node.pivot, "FBX 目标 Pivot")
        layer_name = str(node.layer.name)
    except Exception as exc:
        raise RuntimeError(f"无法读取 FBX 目标对象变换/Pivot：{exc}") from exc
    (
        is_hidden,
        layer_is_hidden,
        is_frozen,
        box_mode,
        renderable,
        visibility,
    ) = _candidate_visibility_state(node)
    evaluated_world_positions = _evaluated_world_positions(node)
    return CandidateAuthoritySnapshot(
        node_handle=node_handle(node),
        base_object_handle=base_handle,
        material_handle=material_handle,
        mesh_counts=mesh_counts(node),
        object_transform=object_transform,
        pivot=pivot,
        non_skin_modifiers=tuple(non_skin_modifiers),
        layer_name=layer_name,
        is_hidden=is_hidden,
        layer_is_hidden=layer_is_hidden,
        is_frozen=is_frozen,
        box_mode=box_mode,
        renderable=renderable,
        visibility=visibility,
        evaluated_world_positions=evaluated_world_positions,
        evaluated_world_bbox=_world_bbox(evaluated_world_positions),
    )


def verify_candidate_authority_snapshot(
    expected: CandidateAuthoritySnapshot,
    node: Any,
    skin_to_exclude: Any,
) -> None:
    actual = candidate_authority_snapshot(node, skin_to_exclude)
    differences: List[str] = []
    field_labels = {
        "node_handle": "候选节点身份",
        "base_object_handle": "基础对象身份",
        "material_handle": "材质身份",
        "mesh_counts": "网格统计",
        "object_transform": "对象变换矩阵",
        "pivot": "轴心",
        "non_skin_modifiers": "非蒙皮修改器栈",
        "layer_name": "图层",
        "is_hidden": "聚合隐藏状态",
        "layer_is_hidden": "图层隐藏状态",
        "is_frozen": "冻结状态",
        "box_mode": "盒状显示状态",
        "renderable": "可渲染状态",
        "visibility": "可见性",
    }
    for field_name in field_labels:
        if getattr(actual, field_name) != getattr(expected, field_name):
            differences.append(field_labels[field_name])
    if len(actual.evaluated_world_positions) != len(
        expected.evaluated_world_positions
    ):
        differences.append("评估后世界顶点数量")
    else:
        worst_ratio = -1.0
        worst_delta = 0.0
        worst_tolerance = MODE2_WORLD_POSITION_ABSOLUTE_FLOOR
        worst_coordinate_scale = 1.0
        worst_vertex = 0
        for vertex_index, (expected_point, actual_point) in enumerate(
            zip(
                expected.evaluated_world_positions,
                actual.evaluated_world_positions,
            ),
            start=1,
        ):
            delta, tolerance, coordinate_scale = _mode2_world_point_metrics(
                expected_point,
                actual_point,
            )
            ratio = delta / tolerance
            if ratio > worst_ratio:
                worst_ratio = ratio
                worst_delta = delta
                worst_tolerance = tolerance
                worst_coordinate_scale = coordinate_scale
                worst_vertex = vertex_index
        if worst_ratio > 1.0:
            differences.append(
                "评估后世界顶点"
                f"(顶点 {worst_vertex} 最大差 {worst_delta:.9f}，"
                f"允许 {worst_tolerance:.9f}，"
                f"坐标尺度 {worst_coordinate_scale:.9f})"
            )
    bbox_failures: List[Tuple[str, float, float, float]] = []
    for bbox_label, expected_point, actual_point in (
        (
            "最小角",
            expected.evaluated_world_bbox[:3],
            actual.evaluated_world_bbox[:3],
        ),
        (
            "最大角",
            expected.evaluated_world_bbox[3:],
            actual.evaluated_world_bbox[3:],
        ),
    ):
        delta, tolerance, coordinate_scale = _mode2_world_point_metrics(
            expected_point,
            actual_point,
        )
        if delta > tolerance:
            bbox_failures.append(
                (bbox_label, delta, tolerance, coordinate_scale)
            )
    if bbox_failures:
        bbox_label, delta, tolerance, coordinate_scale = max(
            bbox_failures,
            key=lambda item: item[1] / item[2],
        )
        differences.append(
            "评估后世界包围盒"
            f"({bbox_label}差 {delta:.9f}，允许 {tolerance:.9f}，"
            f"坐标尺度 {coordinate_scale:.9f})"
        )
    if differences:
        raise RuntimeError(
            "重建/提交改变了 FBX 目标权威数据或评估后世界外观："
            + "，".join(differences)
        )


def build_scene_bone_lookup(
    ctx: TransferContext,
    *,
    exclude_handles: Iterable[int] = (),
) -> SkinBoneLookup:
    excluded = {int(handle) for handle in exclude_handles}
    entries: List[SkinBoneEntry] = []
    for record in ctx.scene_records:
        if record.handle in excluded or not is_valid_node(record.node):
            continue
        if not record.original_name:
            continue
        entries.append(
            SkinBoneEntry(
                bone_id=int(record.handle),
                full_name=record.original_name,
                node=record.node,
            )
        )
    exact: Dict[str, List[SkinBoneEntry]] = {}
    normalized: Dict[str, List[SkinBoneEntry]] = {}
    for entry in entries:
        exact.setdefault(entry.full_name, []).append(entry)
        key = normalize_name(entry.full_name)
        if key:
            normalized.setdefault(key, []).append(entry)
    return SkinBoneLookup(entries=entries, exact=exact, normalized=normalized)


def _resolve_if_present(
    source_name: str,
    lookup: SkinBoneLookup,
) -> Optional[Tuple[SkinBoneEntry, bool]]:
    if lookup.exact.get(source_name):
        return resolve_target_bone(source_name, lookup)
    normalized_key = normalize_name(source_name)
    if normalized_key and lookup.normalized.get(normalized_key):
        return resolve_target_bone(source_name, lookup)
    return None


def resolve_complete_scene_bones(
    source_entries: Sequence[SkinBoneEntry],
    preferred_skin_lookup: SkinBoneLookup,
    scene_lookup: SkinBoneLookup,
) -> Tuple[List[Tuple[str, Any]], Set[str]]:
    mappings: List[Tuple[str, Any]] = []
    normalized_fallbacks: Set[str] = set()
    used_target_handles: Dict[int, str] = {}
    for source_entry in source_entries:
        resolved = _resolve_if_present(
            source_entry.full_name,
            preferred_skin_lookup,
        )
        if resolved is None:
            resolved = _resolve_if_present(source_entry.full_name, scene_lookup)
        if resolved is None:
            raise RuntimeError(
                f"FBX Skin 完整骨骼表中的骨骼在场景中不存在：{source_entry.full_name}"
            )
        target_entry, used_fallback = resolved
        if used_fallback:
            normalized_fallbacks.add(source_entry.full_name)
        target_handle = node_handle(target_entry.node)
        previous_source = used_target_handles.get(target_handle)
        if previous_source is not None and previous_source != source_entry.full_name:
            raise RuntimeError(
                "两个 FBX 骨骼被映射到同一个场景节点："
                f"{previous_source} / {source_entry.full_name}"
            )
        used_target_handles[target_handle] = source_entry.full_name
        mappings.append((source_entry.full_name, target_entry.node))
    if len(mappings) != len(source_entries):
        raise RuntimeError(
            f"FBX Skin 完整骨骼映射数量不一致：{len(mappings)}/{len(source_entries)}"
        )
    return mappings, normalized_fallbacks


def skin_bone_entries(
    ctx: TransferContext,
    skin: Any,
    *,
    use_scene_original_names: bool,
) -> List[SkinBoneEntry]:
    """读取 Skin 的实际 BoneID；绝不把 GetBoneNodes 的列表序号当作 BoneID。"""
    try:
        list_count = int(rt.skinOps.GetNumberBones(skin))
    except Exception as exc:
        raise RuntimeError(f"无法读取 Skin 骨骼数量：{exc}") from exc
    if list_count < 1:
        raise RuntimeError("Skin 没有可读取的骨骼。")

    entries: List[SkinBoneEntry] = []
    seen_ids: Set[int] = set()
    for list_id in range(1, list_count + 1):
        try:
            bone_id = int(rt.skinOps.GetBoneIDByListID(skin, int(list_id)))
        except Exception as exc:
            raise RuntimeError(f"无法把 Skin 列表序号 {list_id} 转换为实际 BoneID：{exc}") from exc
        if bone_id < 1 or bone_id in seen_ids:
            raise RuntimeError(f"Skin 返回无效或重复的实际 BoneID：{bone_id}")
        seen_ids.add(bone_id)

        try:
            direct_name = str(rt.skinOps.GetBoneName(skin, bone_id, 0))
        except Exception as exc:
            raise RuntimeError(f"无法按实际 BoneID {bone_id} 读取骨骼名：{exc}") from exc
        if not direct_name:
            raise RuntimeError(f"实际 BoneID {bone_id} 的骨骼名为空。")

        try:
            bone_node = rt.skinOps.GetBoneNode(skin, bone_id)
        except Exception as exc:
            raise RuntimeError(f"无法按实际 BoneID {bone_id} 读取骨骼节点：{exc}") from exc
        if not is_valid_node(bone_node):
            raise RuntimeError(f"实际 BoneID {bone_id} 对应的骨骼节点无效：{direct_name}")

        full_name = original_name_for_node(ctx, bone_node) if use_scene_original_names else direct_name
        if not full_name:
            raise RuntimeError(f"实际 BoneID {bone_id} 没有可用于匹配的完整名称。")
        entries.append(SkinBoneEntry(bone_id=bone_id, full_name=full_name, node=bone_node))
    return entries


def build_skin_bone_lookup(
    ctx: TransferContext,
    skin: Any,
    *,
    use_scene_original_names: bool = True,
) -> SkinBoneLookup:
    entries = skin_bone_entries(
        ctx,
        skin,
        use_scene_original_names=use_scene_original_names,
    )
    exact: Dict[str, List[SkinBoneEntry]] = {}
    normalized: Dict[str, List[SkinBoneEntry]] = {}
    for entry in entries:
        exact.setdefault(entry.full_name, []).append(entry)
        key = normalize_name(entry.full_name)
        if key:
            normalized.setdefault(key, []).append(entry)
    return SkinBoneLookup(entries=entries, exact=exact, normalized=normalized)


def resolve_target_bone(source_name: str, lookup: SkinBoneLookup) -> Tuple[SkinBoneEntry, bool]:
    exact_candidates = lookup.exact.get(source_name, [])
    if len(exact_candidates) == 1:
        return exact_candidates[0], False
    if len(exact_candidates) > 1:
        ids = ", ".join(str(item.bone_id) for item in exact_candidates)
        raise RuntimeError(f"骨骼完整名存在歧义：{source_name}（BoneID {ids}）")

    normalized_key = normalize_name(source_name)
    normalized_candidates = lookup.normalized.get(normalized_key, [])
    if len(normalized_candidates) == 1:
        return normalized_candidates[0], True
    if len(normalized_candidates) > 1:
        names = "，".join(
            f"{item.full_name}[{item.bone_id}]" for item in normalized_candidates
        )
        raise RuntimeError(f"骨骼规范化名称存在歧义：{source_name} -> {normalized_key}；候选：{names}")
    raise RuntimeError(f"找不到骨骼：{source_name}")


def used_bone_names_from_weight_rows(rows: Sequence[Sequence[Tuple[str, float]]]) -> List[str]:
    used: List[str] = []
    seen: Set[str] = set()
    for influences in rows:
        for bone_name, _weight in influences:
            if bone_name in seen:
                continue
            seen.add(bone_name)
            used.append(bone_name)
    return used


def source_skin_weight_rows(
    source_skin: Any,
    vertex_count: int,
    source_entries: Sequence[SkinBoneEntry],
) -> List[List[Tuple[str, float]]]:
    if vertex_count < 1:
        raise RuntimeError("FBX 目标网格没有可写入的顶点。")
    source_name_by_id = {entry.bone_id: entry.full_name for entry in source_entries}
    rows: List[List[Tuple[str, float]]] = []
    for vertex_index in range(1, vertex_count + 1):
        influences: List[Tuple[str, float]] = []
        try:
            count = int(rt.skinOps.GetVertexWeightCount(source_skin, vertex_index))
        except Exception as exc:
            raise RuntimeError(f"读取 FBX Skin 顶点 {vertex_index} 的权重数量失败：{exc}") from exc
        if count < 1:
            raise RuntimeError(f"FBX Skin 顶点 {vertex_index} 没有任何权重。")

        for influence_index in range(1, count + 1):
            try:
                bone_id = int(rt.skinOps.GetVertexWeightBoneID(source_skin, vertex_index, influence_index))
                weight = float(rt.skinOps.GetVertexWeight(source_skin, vertex_index, influence_index))
            except Exception as exc:
                raise RuntimeError(
                    f"读取 FBX Skin 顶点 {vertex_index} 的第 {influence_index} 条权重失败：{exc}"
                ) from exc
            if not math.isfinite(weight) or weight < 0.0:
                raise RuntimeError(
                    f"FBX Skin 顶点 {vertex_index} 的第 {influence_index} 条权重无效：{weight}"
                )
            if weight == 0.0:
                continue
            bone_name = source_name_by_id.get(bone_id)
            if bone_name is None:
                raise RuntimeError(
                    f"FBX Skin 顶点 {vertex_index} 使用了无法按实际 BoneID 解析的影响：{bone_id}"
                )
            influences.append((bone_name, weight))

        if not influences:
            raise RuntimeError(f"FBX Skin 顶点 {vertex_index} 没有正的有效权重。")
        rows.append(influences)
    if len(rows) != vertex_count:
        raise RuntimeError(f"FBX 目标模型权重读取数量不完整：{len(rows)}/{vertex_count}")
    return rows


def _is_vertex_unnormalized(skin: Any, node: Any, vertex_index: int) -> bool:
    try:
        value = rt.F2M_Helper.getVertexUnnormalized(
            node,
            skin,
            int(vertex_index),
        )
        if not is_max_undefined(value):
            return bool(value)
    except Exception:
        pass
    try:
        return bool(
            rt.skinOps.isUnNormalizeVertex(
                skin,
                int(vertex_index),
                node=node,
            )
        )
    except Exception as exc:
        raise RuntimeError("无法读取顶点归一化状态") from exc


def read_vertex_unnormalized_states(
    skin: Any,
    node: Any,
    vertex_count: int,
) -> List[bool]:
    try:
        values = rt.F2M_Helper.getVertexUnnormalizedStates(
            node,
            skin,
            int(vertex_count),
        )
    except Exception as exc:
        raise RuntimeError(f"批量读取顶点归一化状态失败：{exc}") from exc
    if is_max_undefined(values):
        detail = maxscript_helper_message()
        raise RuntimeError(detail or "批量读取顶点归一化状态失败。")
    states = [bool(value) for value in values]
    if len(states) != vertex_count:
        raise RuntimeError(
            f"顶点归一化状态读取数量不完整：{len(states)}/{vertex_count}"
        )
    return states


def source_skin_vertex_states(
    source_skin: Any,
    source_node: Any,
    vertex_count: int,
) -> List[SkinVertexState]:
    unnormalized_states = read_vertex_unnormalized_states(
        source_skin,
        source_node,
        vertex_count,
    )
    states: List[SkinVertexState] = []
    for vertex_index in range(1, vertex_count + 1):
        unnormalized = unnormalized_states[vertex_index - 1]
        try:
            dq_weight = float(rt.skinOps.getVertexDQWeight(source_skin, int(vertex_index)))
        except Exception as exc:
            raise RuntimeError(f"读取 FBX Skin 顶点 {vertex_index} 的 DQ 权重失败：{exc}") from exc
        if not math.isfinite(dq_weight) or dq_weight < 0.0 or dq_weight > 1.0:
            raise RuntimeError(f"FBX Skin 顶点 {vertex_index} 的 DQ 权重无效：{dq_weight}")
        states.append(
            SkinVertexState(
                unnormalized=unnormalized,
                dq_weight=dq_weight,
            )
        )
    if len(states) != vertex_count:
        raise RuntimeError(f"FBX 目标模型顶点状态读取数量不完整：{len(states)}/{vertex_count}")
    return states


def _coerce_skin_property(value: Any, kind: str) -> Any:
    if kind == "bool":
        return bool(value)
    if kind == "int":
        return int(value)
    if kind == "float":
        result = float(value)
        if not math.isfinite(result):
            raise RuntimeError(f"Skin 属性含无效浮点数：{result}")
        return result
    raise RuntimeError(f"未知 Skin 属性类型：{kind}")


def source_skin_modifier_state(
    source_skin: Any,
    source_node: Optional[Any] = None,
) -> SkinModifierState:
    try:
        enable_dq = bool(source_skin.enableDQ)
    except Exception as exc:
        raise RuntimeError(
            f"读取 FBX Skin 的全局 DQ Skinning Toggle 失败：{exc}"
        ) from exc
    property_values: List[Tuple[str, Any]] = []
    for property_name, kind in SKIN_SEMANTIC_PROPERTY_SCHEMA:
        try:
            raw_value = getattr(source_skin, property_name)
            value = _coerce_skin_property(raw_value, kind)
        except Exception as exc:
            raise RuntimeError(
                f"读取 FBX Skin 语义属性 {property_name} 失败：{exc}"
            ) from exc
        property_values.append((property_name, value))

    mesh_bind_tm: Tuple[float, ...] = ()
    if source_node is not None:
        try:
            mesh_bind_tm = _matrix3_tuple(
                rt.skinUtils.GetMeshBindTM(source_node),
                "FBX Skin Mesh Bind TM",
            )
        except Exception as exc:
            raise RuntimeError(f"读取 FBX Skin Mesh Bind TM 失败：{exc}") from exc
    return SkinModifierState(
        enable_dq=enable_dq,
        property_values=tuple(property_values),
        mesh_bind_tm=mesh_bind_tm,
    )


def source_skin_bone_states(
    skin: Any,
    skin_node: Any,
    entries: Sequence[SkinBoneEntry],
) -> List[SkinBoneState]:
    states: List[SkinBoneState] = []
    for entry in entries:
        bone_id = int(entry.bone_id)
        try:
            falloff = int(rt.skinOps.getBonePropFalloff(skin, bone_id))
            relative = int(rt.skinOps.getBonePropRelative(skin, bone_id))
            envelope_visible = int(
                rt.skinOps.getBonePropEnvelopeVisible(skin, bone_id)
            )
            start_point = _point3_tuple(
                rt.skinOps.GetStartPoint(skin, bone_id),
                f"{entry.full_name} StartPoint",
            )
            end_point = _point3_tuple(
                rt.skinOps.GetEndPoint(skin, bone_id),
                f"{entry.full_name} EndPoint",
            )
            cross_count = int(
                rt.skinOps.getNumberCrossSections(skin, bone_id)
            )
            if cross_count < 0:
                raise RuntimeError(f"横截面数量为 {cross_count}")
            cross_sections: List[SkinCrossSectionState] = []
            for cross_id in range(1, cross_count + 1):
                u = float(rt.skinOps.GetCrossSectionU(skin, bone_id, cross_id))
                inner = float(rt.skinOps.GetInnerRadius(skin, bone_id, cross_id))
                outer = float(rt.skinOps.GetOuterRadius(skin, bone_id, cross_id))
                if any(
                    not math.isfinite(value)
                    for value in (u, inner, outer)
                ):
                    raise RuntimeError(
                        f"第 {cross_id} 个横截面含无效数值：{u}/{inner}/{outer}"
                    )
                cross_sections.append(
                    SkinCrossSectionState(
                        u=u,
                        inner_radius=inner,
                        outer_radius=outer,
                    )
                )
            bind_tm = _matrix3_tuple(
                rt.skinUtils.GetBoneBindTM(skin_node, entry.node),
                f"{entry.full_name} Bone Bind TM",
            )
            stretch_tm = _matrix3_tuple(
                rt.skinUtils.GetBoneStretchTM(skin_node, entry.node),
                f"{entry.full_name} Bone Stretch TM",
            )
        except Exception as exc:
            raise RuntimeError(
                f"读取 FBX Skin 骨骼完整状态失败：{entry.full_name}；{exc}"
            ) from exc
        states.append(
            SkinBoneState(
                full_name=entry.full_name,
                falloff=falloff,
                relative=relative,
                envelope_visible=envelope_visible,
                start_point=start_point,
                end_point=end_point,
                cross_sections=tuple(cross_sections),
                bind_tm=bind_tm,
                stretch_tm=stretch_tm,
            )
        )
    if len(states) != len(entries):
        raise RuntimeError(
            f"FBX Skin 骨骼状态读取数量不完整：{len(states)}/{len(entries)}"
        )
    return states


def _float_sequences_close(
    expected: Sequence[float],
    actual: Sequence[float],
    tolerance: float = 0.0001,
) -> bool:
    return len(expected) == len(actual) and all(
        math.isfinite(float(right))
        and abs(float(left) - float(right)) <= tolerance
        for left, right in zip(expected, actual)
    )


def verify_skin_bone_states(
    expected: Sequence[SkinBoneState],
    actual: Sequence[SkinBoneState],
) -> None:
    if len(expected) != len(actual):
        raise RuntimeError(
            f"Skin 骨骼状态读回数量不一致：{len(expected)}/{len(actual)}"
        )
    expected_by_name = {state.full_name: state for state in expected}
    actual_by_name = {state.full_name: state for state in actual}
    if set(expected_by_name) != set(actual_by_name):
        raise RuntimeError(
            "Skin 骨骼状态读回名称集合不一致："
            f"{sorted(expected_by_name)}/{sorted(actual_by_name)}"
        )
    for name, expected_state in expected_by_name.items():
        actual_state = actual_by_name[name]
        if (
            expected_state.falloff != actual_state.falloff
            or expected_state.relative != actual_state.relative
            or expected_state.envelope_visible
            != actual_state.envelope_visible
            or not _float_sequences_close(
                expected_state.start_point,
                actual_state.start_point,
            )
            or not _float_sequences_close(
                expected_state.end_point,
                actual_state.end_point,
            )
            or not _float_sequences_close(
                expected_state.bind_tm,
                actual_state.bind_tm,
            )
            or not _float_sequences_close(
                expected_state.stretch_tm,
                actual_state.stretch_tm,
            )
            or len(expected_state.cross_sections)
            != len(actual_state.cross_sections)
        ):
            raise RuntimeError(f"Skin 骨骼状态读回不一致：{name}")
        for cross_index, (expected_cross, actual_cross) in enumerate(
            zip(
                expected_state.cross_sections,
                actual_state.cross_sections,
            ),
            start=1,
        ):
            if not _float_sequences_close(
                (
                    expected_cross.u,
                    expected_cross.inner_radius,
                    expected_cross.outer_radius,
                ),
                (
                    actual_cross.u,
                    actual_cross.inner_radius,
                    actual_cross.outer_radius,
                ),
            ):
                raise RuntimeError(
                    f"Skin 骨骼 {name} 第 {cross_index} 个横截面读回不一致"
                )


def verify_scene_bound_skin(
    ctx: TransferContext,
    skin: Any,
    skin_node: Any,
    expected_bones: Sequence[Tuple[str, int]],
    expected_states: Sequence[SkinBoneState],
) -> None:
    """Verify that copied Skin still uses the Max scene skeleton/bind space."""

    lookup = build_skin_bone_lookup(
        ctx,
        skin,
        use_scene_original_names=True,
    )
    expected_names = [name for name, _handle in expected_bones]
    actual_names = [entry.full_name for entry in lookup.entries]
    if actual_names != expected_names:
        raise RuntimeError(
            "复制后的 Skin 骨骼表或顺序与 Max 源 Skin 不一致："
            f"期望 {expected_names}，实际 {actual_names}"
        )
    expected_handle_by_name = dict(expected_bones)
    for entry in lookup.entries:
        actual_handle = node_handle(entry.node)
        expected_handle = expected_handle_by_name[entry.full_name]
        if actual_handle != expected_handle:
            raise RuntimeError(
                f"复制后的 Skin 骨骼节点身份不一致：{entry.full_name}；"
                f"期望 {expected_handle}，实际 {actual_handle}"
            )
    verify_skin_bone_states(
        expected_states,
        source_skin_bone_states(
            skin,
            skin_node,
            lookup.entries,
        ),
    )


def map_weight_rows(
    rows: Sequence[Sequence[Tuple[str, float]]],
    lookup: SkinBoneLookup,
    vertex_states: Optional[Sequence[SkinVertexState]] = None,
) -> Tuple[List[List[Tuple[int, float]]], Set[str]]:
    if vertex_states is not None and len(vertex_states) != len(rows):
        raise RuntimeError(f"权重行与顶点状态数量不一致：{len(rows)}/{len(vertex_states)}")
    mapped_rows: List[List[Tuple[int, float]]] = []
    normalized_fallbacks: Set[str] = set()
    for vertex_index, influences in enumerate(rows, start=1):
        combined: Dict[int, float] = {}
        for source_bone_name, weight in influences:
            try:
                target_entry, used_fallback = resolve_target_bone(source_bone_name, lookup)
            except Exception as exc:
                raise RuntimeError(
                    f"顶点 {vertex_index} 的骨骼影响无法安全匹配：{source_bone_name}；{exc}"
                ) from exc
            if used_fallback:
                normalized_fallbacks.add(source_bone_name)
            combined[target_entry.bone_id] = combined.get(target_entry.bone_id, 0.0) + float(weight)

        if not combined:
            raise RuntimeError(f"顶点 {vertex_index} 的所有权重影响均未映射。")
        total = sum(combined.values())
        if not math.isfinite(total) or total <= 0.0:
            raise RuntimeError(f"顶点 {vertex_index} 的映射权重总和无效：{total}")
        preserve_raw_sum = (
            vertex_states is not None
            and vertex_states[vertex_index - 1].unnormalized
        )
        mapped_rows.append(
            [
                (bone_id, weight if preserve_raw_sum else weight / total)
                for bone_id, weight in sorted(combined.items())
            ]
        )
    if len(mapped_rows) != len(rows):
        raise RuntimeError(f"权重映射数量不完整：{len(mapped_rows)}/{len(rows)}")
    return mapped_rows, normalized_fallbacks


def copy_target_skin_to_node(
    target_node: Any,
    target_skin: Any,
    dst_node: Any,
    stack_index: int,
    report: ObjectReport,
) -> Optional[Any]:
    try:
        copied = rt.F2M_Helper.copySkinModifierToNode(
            target_node,
            target_skin,
            dst_node,
            int(stack_index),
        )
    except Exception as exc:
        report.add_exception(
            "整模替换：复制 Max 源模型蒙皮到新网格失败。",
            exc,
        )
        return None

    msg = helper_message()
    if msg:
        report.add(f"整模替换：{msg}")

    if copied is None or str(copied) == "undefined":
        report.add("整模替换：复制 Max 源模型 Skin 到新网格失败，未得到有效 Skin 修改器。")
        return None

    copied_skin = find_skin(dst_node)
    if copied_skin is None:
        report.add("整模替换：复制后在新网格上没有找到 Skin 修改器。")
        return None
    copied_index_value = rt.F2M_Helper.modifierIndex(dst_node, copied_skin)
    if is_max_undefined(copied_index_value) or int(copied_index_value) != int(stack_index):
        report.add(
            "整模替换：复制后的 Max Skin 没有位于原 FBX Skin 栈位，已停止提交。"
        )
        return None
    return copied_skin


def create_fbx_authority_skin(
    ctx: TransferContext,
    dst_node: Any,
    stack_index: int,
    scene_bone_mappings: Sequence[Tuple[str, Any]],
    bone_states: Sequence[SkinBoneState],
    rows: Sequence[Sequence[Tuple[str, float]]],
    vertex_states: Sequence[SkinVertexState],
    modifier_state: SkinModifierState,
) -> Tuple[
    Any,
    List[List[Tuple[int, float]]],
    int,
    Set[str],
]:
    try:
        fresh_skin = rt.F2M_Helper.createFreshSkinAtIndex(
            dst_node,
            int(stack_index),
        )
    except Exception as exc:
        raise RuntimeError(f"新建 FBX 权威 Skin 失败：{exc}") from exc
    if fresh_skin is None or is_max_undefined(fresh_skin):
        raise RuntimeError(
            helper_message() or "新建 FBX 权威 Skin 没有返回有效修改器。"
        )
    if not activate_modifier(dst_node, fresh_skin):
        raise RuntimeError("无法激活新建的 FBX 权威 Skin。")

    for index, (source_name, scene_bone) in enumerate(
        scene_bone_mappings,
        start=1,
    ):
        if not is_valid_node(scene_bone):
            raise RuntimeError(f"场景骨骼在写入前已经无效：{source_name}")
        update_value = 1 if index == len(scene_bone_mappings) else 0
        try:
            rt.skinOps.addBone(
                fresh_skin,
                scene_bone,
                update_value,
                node=dst_node,
            )
        except Exception as exc:
            raise RuntimeError(
                f"把场景骨骼加入 FBX 权威 Skin 失败：{source_name}；{exc}"
            ) from exc

    fresh_lookup = build_skin_bone_lookup(
        ctx,
        fresh_skin,
        use_scene_original_names=True,
    )
    expected_names = [name for name, _node in scene_bone_mappings]
    actual_names = [entry.full_name for entry in fresh_lookup.entries]
    if len(actual_names) != len(expected_names) or set(actual_names) != set(
        expected_names
    ):
        raise RuntimeError(
            "新建 Skin 的完整骨骼表与 FBX 不一致："
            f"期望 {len(expected_names)} 个，实际 {len(actual_names)} 个。"
        )
    mapped_handle_by_name = {
        name: node_handle(scene_bone)
        for name, scene_bone in scene_bone_mappings
    }
    for entry in fresh_lookup.entries:
        expected_handle = mapped_handle_by_name.get(entry.full_name)
        actual_handle = node_handle(entry.node)
        if expected_handle != actual_handle:
            raise RuntimeError(
                f"Skin 骨骼节点身份读回不一致：{entry.full_name}；"
                f"期望 {expected_handle}，实际 {actual_handle}"
            )

    mapped_rows, normalized_fallbacks = map_weight_rows(
        rows,
        fresh_lookup,
        vertex_states,
    )
    _set_skin_modifier_state(fresh_skin, modifier_state, dst_node)
    _set_skin_bone_states(
        fresh_skin,
        dst_node,
        fresh_lookup,
        bone_states,
    )
    applied_vertices = apply_weight_rows(
        fresh_skin,
        dst_node,
        mapped_rows,
        vertex_states,
        modifier_state,
    )
    final_lookup = build_skin_bone_lookup(
        ctx,
        fresh_skin,
        use_scene_original_names=True,
    )
    if len(final_lookup.entries) != len(expected_names):
        raise RuntimeError(
            "权重写入后 Skin 完整骨骼表数量发生变化："
            f"{len(final_lookup.entries)}/{len(expected_names)}"
        )
    verify_skin_bone_states(
        bone_states,
        source_skin_bone_states(
            fresh_skin,
            dst_node,
            final_lookup.entries,
        ),
    )
    verify_weight_rows(
        fresh_skin,
        dst_node,
        mapped_rows,
        vertex_states,
        modifier_state,
    )
    return (
        fresh_skin,
        mapped_rows,
        applied_vertices,
        normalized_fallbacks,
    )


def _read_vertex_weight_map(skin: Any, vertex_index: int) -> Dict[int, float]:
    try:
        count = int(rt.skinOps.GetVertexWeightCount(skin, int(vertex_index)))
    except Exception as exc:
        raise RuntimeError(f"读回顶点 {vertex_index} 的权重数量失败：{exc}") from exc
    if count < 1:
        raise RuntimeError(f"读回顶点 {vertex_index} 时没有任何权重。")

    result: Dict[int, float] = {}
    for influence_index in range(1, count + 1):
        try:
            bone_id = int(rt.skinOps.GetVertexWeightBoneID(skin, int(vertex_index), influence_index))
            weight = float(rt.skinOps.GetVertexWeight(skin, int(vertex_index), influence_index))
        except Exception as exc:
            raise RuntimeError(
                f"读回顶点 {vertex_index} 的第 {influence_index} 条权重失败：{exc}"
            ) from exc
        if not math.isfinite(weight) or weight < 0.0:
            raise RuntimeError(f"读回顶点 {vertex_index} 得到无效权重：{weight}")
        if weight == 0.0:
            continue
        result[bone_id] = result.get(bone_id, 0.0) + weight
    if not result:
        raise RuntimeError(f"读回顶点 {vertex_index} 时没有正的有效权重。")
    return result


def _set_vertex_unnormalized(
    skin: Any,
    node: Any,
    vertex_index: int,
    value: bool,
) -> None:
    try:
        ok = bool(
            rt.F2M_Helper.setVertexUnnormalized(
                node,
                skin,
                int(vertex_index),
                bool(value),
            )
        )
        if not ok:
            raise RuntimeError(helper_message() or "MAXScript 辅助函数返回失败状态")
    except Exception as helper_exc:
        helper_error_text = _exception_text_and_release(helper_exc)
        try:
            rt.skinOps.unNormalizeVertex(skin, int(vertex_index), bool(value))
        except BaseException:
            rt.skinOps.unNormalizeVertex(
                skin,
                int(vertex_index),
                bool(value),
                node=node,
            )
        try:
            rt.skinOps.Invalidate(skin, 0)
        except Exception:
            pass
        actual = _is_vertex_unnormalized(skin, node, vertex_index)
        if actual != bool(value):
            raise RuntimeError(
                f"MAXScript helper {helper_error_text}；兼容调用后仍为 {actual}"
            ) from None
    actual = _is_vertex_unnormalized(skin, node, vertex_index)
    if actual != bool(value):
        raise RuntimeError(
            f"顶点 {vertex_index} 归一化状态读回不一致：期望 {value}，实际 {actual}"
        )


def _prepare_vertex_unnormalized_states(
    skin: Any,
    node: Any,
    vertex_states: Sequence[SkinVertexState],
) -> None:
    flags = [bool(state.unnormalized) for state in vertex_states]
    if not any(flags):
        return
    try:
        ok = bool(
            rt.F2M_Helper.prepareVertexUnnormalizedStates(
                node,
                skin,
                max_array(flags),
            )
        )
    except Exception as exc:
        raise RuntimeError(f"批量预设未归一化顶点失败：{exc}") from exc
    if not ok:
        detail = helper_message()
        raise RuntimeError(
            detail or "批量预设未归一化顶点返回失败状态"
        )


def _set_all_vertex_unnormalized_states(
    skin: Any,
    node: Any,
    vertex_states: Sequence[SkinVertexState],
) -> None:
    flags = [bool(state.unnormalized) for state in vertex_states]
    try:
        ok = bool(
            rt.F2M_Helper.setVertexUnnormalizedStates(
                node,
                skin,
                max_array(flags),
            )
        )
    except Exception as exc:
        raise RuntimeError(f"批量恢复顶点归一化状态失败：{exc}") from exc
    if not ok:
        raise RuntimeError(
            helper_message() or "批量恢复顶点归一化状态返回失败状态"
        )


def _set_skin_modifier_state(
    skin: Any,
    state: SkinModifierState,
    node: Optional[Any] = None,
    *,
    write_mesh_bind_tm: bool = True,
) -> None:
    try:
        skin.enableDQ = bool(state.enable_dq)
        actual = bool(skin.enableDQ)
    except Exception as exc:
        raise RuntimeError(
            f"设置 Skin 的全局 DQ Skinning Toggle 失败：{exc}"
        ) from exc
    if actual != state.enable_dq:
        raise RuntimeError(
            "Skin 全局 DQ Skinning Toggle 读回不一致："
            f"期望 {state.enable_dq}，实际 {actual}"
        )
    schema_by_name = dict(SKIN_SEMANTIC_PROPERTY_SCHEMA)
    for property_name, expected in state.property_values:
        kind = schema_by_name.get(property_name)
        if kind is None:
            raise RuntimeError(f"Skin 快照含未知语义属性：{property_name}")
        try:
            setattr(skin, property_name, expected)
            actual_value = _coerce_skin_property(
                getattr(skin, property_name),
                kind,
            )
        except Exception as exc:
            raise RuntimeError(
                f"设置 Skin 语义属性 {property_name} 失败：{exc}"
            ) from exc
        if kind == "float":
            matches = abs(float(actual_value) - float(expected)) <= 0.0001
        else:
            matches = actual_value == expected
        if not matches:
            raise RuntimeError(
                f"Skin 语义属性 {property_name} 读回不一致："
                f"期望 {expected}，实际 {actual_value}"
            )

    if state.mesh_bind_tm and write_mesh_bind_tm:
        if node is None:
            raise RuntimeError("恢复 Mesh Bind TM 时没有提供候选节点。")
        try:
            rt.skinUtils.SetMeshBindTM(
                node,
                _matrix3_value(state.mesh_bind_tm),
            )
            actual_tm = _matrix3_tuple(
                rt.skinUtils.GetMeshBindTM(node),
                "候选 Skin Mesh Bind TM",
            )
        except Exception as exc:
            raise RuntimeError(f"设置 Skin Mesh Bind TM 失败：{exc}") from exc
        if not _float_sequences_close(state.mesh_bind_tm, actual_tm):
            raise RuntimeError("Skin Mesh Bind TM 写后读回不一致。")


def _set_skin_bone_states(
    skin: Any,
    skin_node: Any,
    lookup: SkinBoneLookup,
    states: Sequence[SkinBoneState],
) -> None:
    state_by_name = {state.full_name: state for state in states}
    entry_by_name = {entry.full_name: entry for entry in lookup.entries}
    if set(state_by_name) != set(entry_by_name):
        raise RuntimeError(
            "写入 Skin 骨骼状态前名称集合不一致："
            f"{sorted(state_by_name)}/{sorted(entry_by_name)}"
        )
    if not activate_modifier(skin_node, skin):
        raise RuntimeError("无法激活候选 Skin 以恢复完整骨骼状态。")

    for name, state in state_by_name.items():
        entry = entry_by_name[name]
        bone_id = int(entry.bone_id)
        try:
            rt.skinUtils.SetBoneBindTM(
                skin_node,
                entry.node,
                _matrix3_value(state.bind_tm),
            )
            rt.skinUtils.SetBoneStretchTM(
                skin_node,
                entry.node,
                _matrix3_value(state.stretch_tm),
            )
            rt.skinOps.setBonePropFalloff(skin, bone_id, int(state.falloff))
            rt.skinOps.setBonePropRelative(skin, bone_id, int(state.relative))
            rt.skinOps.setBonePropEnvelopeVisible(
                skin,
                bone_id,
                int(state.envelope_visible),
            )
            rt.skinOps.SetStartPoint(
                skin,
                bone_id,
                _point3_value(state.start_point),
            )
            rt.skinOps.SetEndPoint(
                skin,
                bone_id,
                _point3_value(state.end_point),
            )

            current_cross_count = int(
                rt.skinOps.getNumberCrossSections(skin, bone_id)
            )
            desired_cross_count = len(state.cross_sections)
            while current_cross_count > desired_cross_count:
                rt.skinOps.RemoveCrossSection(
                    skin,
                    bone_id,
                    current_cross_count,
                )
                current_cross_count -= 1
            while current_cross_count < desired_cross_count:
                cross = state.cross_sections[current_cross_count]
                rt.skinOps.addCrossSection(
                    skin,
                    bone_id,
                    float(cross.u),
                    float(cross.inner_radius),
                    float(cross.outer_radius),
                    node=skin_node,
                )
                current_cross_count += 1
            for cross_id, cross in enumerate(state.cross_sections, start=1):
                rt.skinOps.SetCrossSectionU(
                    skin,
                    bone_id,
                    cross_id,
                    float(cross.u),
                )
                rt.skinOps.SetInnerRadius(
                    skin,
                    bone_id,
                    cross_id,
                    float(cross.inner_radius),
                )
                rt.skinOps.SetOuterRadius(
                    skin,
                    bone_id,
                    cross_id,
                    float(cross.outer_radius),
                )
        except Exception as exc:
            raise RuntimeError(
                f"恢复 FBX Skin 骨骼完整状态失败：{name}；{exc}"
            ) from exc

    actual_states = source_skin_bone_states(
        skin,
        skin_node,
        lookup.entries,
    )
    verify_skin_bone_states(states, actual_states)


def verify_weight_rows(
    dst_skin: Any,
    dst_node: Any,
    rows: Sequence[Sequence[Tuple[int, float]]],
    vertex_states: Optional[Sequence[SkinVertexState]] = None,
    modifier_state: Optional[SkinModifierState] = None,
) -> None:
    if not activate_modifier(dst_node, dst_skin):
        raise RuntimeError("无法激活候选节点的 Skin 修改器进行权重读回。")
    vertex_count = mesh_counts(dst_node)[0]
    if vertex_count != len(rows):
        raise RuntimeError(f"权重读回前顶点数量不一致：网格 {vertex_count}，权重 {len(rows)}")
    if vertex_states is not None and len(vertex_states) != len(rows):
        raise RuntimeError(f"权重读回时顶点状态数量不一致：{len(vertex_states)}/{len(rows)}")
    if modifier_state is not None:
        actual_modifier_state = source_skin_modifier_state(
            dst_skin,
            dst_node if modifier_state.mesh_bind_tm else None,
        )
        if actual_modifier_state.enable_dq != modifier_state.enable_dq:
            raise RuntimeError(
                "Skin 全局 DQ Skinning Toggle 读回不一致："
                f"期望 {modifier_state.enable_dq}，"
                f"实际 {actual_modifier_state.enable_dq}"
            )
        expected_properties = dict(modifier_state.property_values)
        actual_properties = dict(actual_modifier_state.property_values)
        schema_by_name = dict(SKIN_SEMANTIC_PROPERTY_SCHEMA)
        for property_name, expected_value in expected_properties.items():
            actual_value = actual_properties.get(property_name)
            if schema_by_name[property_name] == "float":
                matches = (
                    actual_value is not None
                    and abs(float(actual_value) - float(expected_value))
                    <= 0.0001
                )
            else:
                matches = actual_value == expected_value
            if not matches:
                raise RuntimeError(
                    f"Skin 语义属性 {property_name} 读回不一致："
                    f"期望 {expected_value}，实际 {actual_value}"
                )
        if modifier_state.mesh_bind_tm and not _float_sequences_close(
            modifier_state.mesh_bind_tm,
            actual_modifier_state.mesh_bind_tm,
        ):
            raise RuntimeError("Skin Mesh Bind TM 最终读回不一致。")

    actual_unnormalized_states: Optional[List[bool]] = None
    if vertex_states is not None:
        actual_unnormalized_states = read_vertex_unnormalized_states(
            dst_skin,
            dst_node,
            vertex_count,
        )

    for vertex_index, influences in enumerate(rows, start=1):
        expected: Dict[int, float] = {
            int(bone_id): float(weight) for bone_id, weight in influences
        }
        actual = _read_vertex_weight_map(dst_skin, vertex_index)
        if set(actual) != set(expected):
            raise RuntimeError(
                f"顶点 {vertex_index} 权重骨骼读回不一致："
                f"期望 {sorted(expected)}，实际 {sorted(actual)}"
            )
        for bone_id, expected_weight in expected.items():
            actual_weight = actual[bone_id]
            tolerance = max(0.0001, abs(expected_weight) * 0.0001)
            if abs(actual_weight - expected_weight) > tolerance:
                raise RuntimeError(
                    f"顶点 {vertex_index} / BoneID {bone_id} 权重读回不一致："
                    f"期望 {expected_weight:.8f}，实际 {actual_weight:.8f}"
                )
        if vertex_states is not None:
            expected_state = vertex_states[vertex_index - 1]
            assert actual_unnormalized_states is not None
            actual_unnormalized = actual_unnormalized_states[vertex_index - 1]
            if actual_unnormalized != expected_state.unnormalized:
                raise RuntimeError(
                    f"顶点 {vertex_index} 归一化状态读回不一致："
                    f"期望 {expected_state.unnormalized}，实际 {actual_unnormalized}"
                )
            try:
                actual_dq = float(
                    rt.skinOps.getVertexDQWeight(dst_skin, int(vertex_index))
                )
            except Exception as exc:
                raise RuntimeError(f"读回顶点 {vertex_index} 的 DQ 权重失败：{exc}") from exc
            if (
                not math.isfinite(actual_dq)
                or abs(actual_dq - expected_state.dq_weight) > 0.0001
            ):
                raise RuntimeError(
                    f"顶点 {vertex_index} DQ 权重读回不一致："
                    f"期望 {expected_state.dq_weight:.8f}，实际 {actual_dq:.8f}"
                )


def _skin_bone_ids(skin: Any) -> List[int]:
    try:
        list_count = int(rt.skinOps.GetNumberBones(skin))
    except Exception as exc:
        raise RuntimeError(f"读取候选 Skin 骨骼数量失败：{exc}") from exc
    if list_count < 1:
        raise RuntimeError("候选 Skin 没有可写入的骨骼。")

    bone_ids: List[int] = []
    seen: Set[int] = set()
    for list_id in range(1, list_count + 1):
        try:
            bone_id = int(rt.skinOps.GetBoneIDByListID(skin, int(list_id)))
        except Exception as exc:
            raise RuntimeError(
                f"读取候选 Skin 第 {list_id} 个列表骨骼的实际 BoneID 失败：{exc}"
            ) from exc
        if bone_id in seen:
            raise RuntimeError(f"候选 Skin 返回了重复 BoneID：{bone_id}")
        seen.add(bone_id)
        bone_ids.append(bone_id)
    return bone_ids


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


def _apply_weight_rows_per_vertex(
    dst_skin: Any,
    dst_node: Any,
    rows: Sequence[Sequence[Tuple[int, float]]],
) -> int:
    # The candidate Skin is created fresh for exactly one destination node.
    # The Max 2023-compatible positional signature is therefore sufficient;
    # probing the optional node: keyword inside this loop would manufacture
    # thousands of exception tracebacks containing pymxs wrappers.
    del dst_node
    applied_vertices = 0
    for vertex_index, influences in enumerate(rows, start=1):
        if not influences:
            raise RuntimeError(f"顶点 {vertex_index} 的映射权重为空。")
        bone_ids = [int(bone_id) for bone_id, _weight in influences]
        weights = [float(weight) for _bone_id, weight in influences]

        try:
            rt.skinOps.ReplaceVertexWeights(
                dst_skin,
                int(vertex_index),
                max_array(bone_ids),
                max_array(weights),
            )
        except BaseException as exc:
            detail = _exception_text_and_release(exc)
            raise RuntimeError(
                f"写入顶点 {vertex_index} 权重失败：{detail}"
            ) from None
        applied_vertices += 1
    return applied_vertices


def _write_dq_and_verify_weight_rows(
    dst_skin: Any,
    dst_node: Any,
    rows: Sequence[Sequence[Tuple[int, float]]],
    vertex_states: Sequence[SkinVertexState],
    modifier_state: SkinModifierState,
) -> None:
    for vertex_index, expected_state in enumerate(vertex_states, start=1):
        try:
            rt.skinOps.setVertexDQWeight(
                dst_skin,
                int(vertex_index),
                float(expected_state.dq_weight),
            )
        except Exception as exc:
            raise RuntimeError(f"写入顶点 {vertex_index} DQ 权重失败：{exc}") from exc
    _set_all_vertex_unnormalized_states(
        dst_skin,
        dst_node,
        vertex_states,
    )
    verify_weight_rows(
        dst_skin,
        dst_node,
        rows,
        vertex_states,
        modifier_state,
    )


def apply_weight_rows(
    dst_skin: Any,
    dst_node: Any,
    rows: Sequence[Sequence[Tuple[int, float]]],
    vertex_states: Sequence[SkinVertexState],
    modifier_state: SkinModifierState,
    *,
    write_mesh_bind_tm: bool = True,
) -> int:
    global LAST_WEIGHT_BULK_FALLBACK_REASON, LAST_WEIGHT_WRITE_METHOD
    LAST_WEIGHT_WRITE_METHOD = ""
    LAST_WEIGHT_BULK_FALLBACK_REASON = ""
    if not rows:
        raise RuntimeError("没有可写入的权重行。")
    if len(vertex_states) != len(rows):
        raise RuntimeError(f"权重写入时顶点状态数量不一致：{len(vertex_states)}/{len(rows)}")
    if not activate_modifier(dst_node, dst_skin):
        raise RuntimeError("无法激活候选节点的 Skin 修改器进行权重写入。")
    _set_skin_modifier_state(
        dst_skin,
        modifier_state,
        dst_node,
        write_mesh_bind_tm=write_mesh_bind_tm,
    )
    try:
        rt.skinOps.enableDQOverrideWeighting(
            dst_skin,
            any(state.dq_weight > 0.0 for state in vertex_states),
        )
    except Exception as exc:
        raise RuntimeError(f"设置候选 Skin 的 DQ Override 状态失败：{exc}") from exc
    _prepare_vertex_unnormalized_states(
        dst_skin,
        dst_node,
        vertex_states,
    )

    # Mode 2 treats each FBX vertex row as authoritative.  ReplaceVertexWeights
    # exactly expresses that contract: influences omitted from one row are
    # removed.  Do not first write a dense bone-by-vertex matrix; on normalized
    # skins that column-wise path can alter earlier columns, fail readback, and
    # force the entire 399-bone asset to be written twice.
    try:
        applied_vertices = _apply_weight_rows_per_vertex(
            dst_skin,
            dst_node,
            rows,
        )
        if applied_vertices != len(rows):
            raise RuntimeError(
                f"权重写入数量不完整：{applied_vertices}/{len(rows)}"
            )
        _write_dq_and_verify_weight_rows(
            dst_skin,
            dst_node,
            rows,
            vertex_states,
            modifier_state,
        )
        LAST_WEIGHT_WRITE_METHOD = "逐顶点权威写入"
        return applied_vertices
    except BaseException as exc:
        error_text = _exception_text_and_release(exc)
        raise RuntimeError(
            "Skin 逐顶点权威权重写入或读回失败："
            + error_text
        ) from None


def _set_node_name_exact(node: Any, name: str) -> None:
    node.name = name
    actual = str(node.name)
    if actual != name:
        raise RuntimeError(f"节点名称读回不一致：期望 {name}，实际 {actual}")


def _set_node_hidden_exact(node: Any, hidden: bool) -> None:
    hidden_flag = int(bool(hidden))
    if pymxs is None:
        ok = bool(rt.F2M_Helper.setNodeHiddenFlag(node, hidden_flag))
    else:
        ok = bool(
            rt.execute(
                "F2M_Helper.setNodeHiddenFlag "
                f"(getAnimByHandle {node_handle(node)}) {hidden_flag}"
            )
        )
    if not ok:
        raise RuntimeError(helper_message() or "MAXScript 节点本地隐藏状态写入失败。")
    if bool(node.isNodeHidden) != bool(hidden):
        raise RuntimeError(
            "节点本地隐藏状态读回不一致："
            f"期望 {hidden}，实际 {node.isNodeHidden}"
        )


def _rollback_old_target(
    target_record: SceneRecord,
    old_name: str,
    old_hidden: bool,
) -> List[str]:
    failures: List[str] = []
    target = node_by_handle(target_record.handle)
    target_record.node = target
    if target is None:
        return ["原 Max 源模型已不存在，无法回滚"]
    try:
        _set_node_name_exact(target, old_name)
    except Exception as exc:
        failures.append(f"Max 源模型名称回滚失败：{exc}")
    try:
        _set_node_hidden_exact(target, old_hidden)
    except Exception as exc:
        failures.append(f"Max 源模型可见性回滚失败：{exc}")
    return failures


def _forget_imported_node_handle(ctx: TransferContext, handle: int) -> None:
    """删除前清掉上下文中指定句柄的 pymxs 节点 wrapper。"""

    tracked_nodes = getattr(ctx, "imported_nodes", None)
    if tracked_nodes is None:
        return
    retained_nodes: List[Any] = []
    tracked_node: Any = None
    for tracked_node in tracked_nodes:
        try:
            tracked_handle = node_handle(tracked_node)
        except Exception:
            retained_nodes.append(tracked_node)
            continue
        if tracked_handle != int(handle):
            retained_nodes.append(tracked_node)
    tracked_nodes[:] = retained_nodes
    retained_nodes.clear()
    tracked_node = None
    tracked_nodes = None


def rollback_committed_replacements(
    ctx: TransferContext,
    reason: str,
) -> List[str]:
    """逆序撤销已经提交的备份式替换，保证批处理不会留下部分成功。"""
    entries = list(reversed(ctx.committed_replacements))
    if not entries:
        return []
    ctx.committed_replacements = []

    failures: List[str] = []
    for entry in entries:
        local_failures: List[str] = []
        candidate_handle = int(entry.candidate_handle)
        candidate_name = str(entry.candidate_name or entry.report.name)
        ctx.keep_imported_nodes.discard(candidate_handle)
        ctx.replacement_nodes.discard(candidate_handle)

        # 删除前两端都只留下句柄/名称；删除后需要继续处理时必须重新解析。
        entry.target_record.node = None
        _forget_imported_node_handle(ctx, candidate_handle)
        try:
            _delete_node_handles_strict(
                {candidate_handle},
                {candidate_handle: candidate_name},
                label="回滚新候选",
            )
        except Exception as exc:
            local_failures.append(f"删除新候选失败：{exc}")
            live_candidate = node_by_handle(candidate_handle)
            if live_candidate is not None:
                try:
                    isolated_name = (
                        f"{ctx.import_prefix}ROLLBACK_{candidate_handle}__"
                        f"{live_candidate.name}"
                    )
                    _set_node_name_exact(live_candidate, isolated_name)
                except Exception as isolate_exc:
                    local_failures.append(
                        f"隔离未删除的新候选失败：{isolate_exc}"
                    )
        finally:
            live_candidate = None

        entry.target_record.skip_restore = False
        local_failures.extend(
            _rollback_old_target(
                entry.target_record,
                entry.target_record.temp_name,
                entry.old_hidden,
            )
        )

        if local_failures:
            entry.report.status = "失败：批次回滚不完整"
            entry.report.add(
                f"后续对象失败，已尝试回滚本对象；回滚仍有问题：{'；'.join(local_failures)}"
            )
            failures.extend(
                f"{entry.report.name}：{message}" for message in local_failures
            )
        else:
            entry.report.status = "失败：批次已回滚"
            entry.report.add(f"后续对象或收尾步骤失败，本对象已完整回滚：{reason}")

    if failures:
        message = "已提交对象的批次回滚不完整：" + "；".join(failures)
        ctx.safety_errors.append(message)
        ctx.log.add("错误：" + message)
    else:
        ctx.log.add(f"批次事务已回滚 {len(entries)} 个已提交对象：{reason}")
    return failures


def commit_replacement(
    ctx: TransferContext,
    src: Any,
    target_record: SceneRecord,
    copied_skin: Any,
    authority_snapshot: CandidateAuthoritySnapshot,
    mapped_rows: Sequence[Sequence[Tuple[int, float]]],
    vertex_states: Sequence[SkinVertexState],
    modifier_state: SkinModifierState,
    expected_scene_bones: Sequence[Tuple[str, int]],
    expected_bone_states: Sequence[SkinBoneState],
    report: ObjectReport,
) -> None:
    old_target = target_record.node
    if not is_valid_node(old_target) or not is_valid_node(src):
        raise RuntimeError("提交前 Max 源模型或新候选节点已经无效。")
    old_name = str(old_target.name)
    if old_name != target_record.temp_name:
        raise RuntimeError(
            f"提交前 Max 源模型临时名称异常：期望 {target_record.temp_name}，实际 {old_name}"
        )
    try:
        old_hidden = bool(old_target.isNodeHidden)
    except Exception as exc:
        raise RuntimeError(f"提交前无法读取 Max 源模型隐藏状态：{exc}") from exc

    candidate_name = str(src.name)
    candidate_handle = node_handle(src)
    target_name = target_record.original_name
    verify_weight_rows(
        copied_skin,
        src,
        mapped_rows,
        vertex_states,
        modifier_state,
    )
    verify_scene_bound_skin(
        ctx,
        copied_skin,
        src,
        expected_scene_bones,
        expected_bone_states,
    )
    verify_candidate_authority_snapshot(authority_snapshot, src, copied_skin)

    if ctx.options.backup_old_mesh:
        backup_name = f"{target_name}_F2M_旧网格_{ctx.run_id}"
        try:
            _set_node_name_exact(old_target, backup_name)
            _set_node_hidden_exact(old_target, True)
            _set_node_name_exact(src, target_name)
            if find_skin(src) is None:
                raise RuntimeError("新候选节点在提交时没有 Skin 修改器。")
            verify_weight_rows(
                copied_skin,
                src,
                mapped_rows,
                vertex_states,
                modifier_state,
            )
            verify_scene_bound_skin(
                ctx,
                copied_skin,
                src,
                expected_scene_bones,
                expected_bone_states,
            )
            verify_candidate_authority_snapshot(
                authority_snapshot,
                src,
                copied_skin,
            )
        except Exception as exc:
            rollback_errors = _rollback_old_target(target_record, old_name, old_hidden)
            try:
                _set_node_name_exact(src, candidate_name)
            except Exception as rollback_exc:
                rollback_errors.append(f"新候选名称回滚失败：{rollback_exc}")
            detail = "" if not rollback_errors else "；回滚问题：" + "；".join(rollback_errors)
            raise RuntimeError(f"备份式提交失败：{exc}{detail}") from exc

        target_record.skip_restore = True
        ctx.keep_imported_nodes.add(candidate_handle)
        ctx.replacement_nodes.add(candidate_handle)
        ctx.committed_replacements.append(
            CommittedReplacement(
                target_record=target_record,
                candidate_handle=candidate_handle,
                candidate_name=target_name,
                old_hidden=old_hidden,
                report=report,
            )
        )
        return

    # 不保留旧网格时，先让新节点通过名称/Skin/全顶点权重读回，再把删除作为最后一步。
    ctx.keep_imported_nodes.add(candidate_handle)
    target_handle = int(target_record.handle)
    target_record.node = None
    old_target = None
    try:
        _set_node_name_exact(src, target_name)
        if find_skin(src) is None:
            raise RuntimeError("新候选节点在提交时没有 Skin 修改器。")
        verify_weight_rows(
            copied_skin,
            src,
            mapped_rows,
            vertex_states,
            modifier_state,
        )
        verify_scene_bound_skin(
            ctx,
            copied_skin,
            src,
            expected_scene_bones,
            expected_bone_states,
        )
        verify_candidate_authority_snapshot(authority_snapshot, src, copied_skin)
        try:
            _delete_node_handles_strict(
                {target_handle},
                {target_handle: old_name},
                label="Max 源模型",
            )
        except Exception as exc:
            raise RuntimeError(f"删除 Max 源模型失败：{exc}") from exc
        target_record.skip_restore = True
        ctx.replacement_nodes.add(candidate_handle)
        # 删除旧目标不应改变候选 Skin；再次读回，失败时也绝不误报完成。
        if find_skin(src) is None:
            raise RuntimeError("删除 Max 源模型后新节点的 Skin 丢失。")
        verify_weight_rows(
            copied_skin,
            src,
            mapped_rows,
            vertex_states,
            modifier_state,
        )
        verify_scene_bound_skin(
            ctx,
            copied_skin,
            src,
            expected_scene_bones,
            expected_bone_states,
        )
        verify_candidate_authority_snapshot(authority_snapshot, src, copied_skin)
    except Exception as exc:
        live_old_target = node_by_handle(target_handle)
        target_record.node = live_old_target
        live_old_target = None
        if target_record.node is not None:
            ctx.keep_imported_nodes.discard(candidate_handle)
            rollback_errors = _rollback_old_target(target_record, old_name, old_hidden)
            try:
                _set_node_name_exact(src, candidate_name)
            except Exception as rollback_exc:
                rollback_errors.append(f"新候选名称回滚失败：{rollback_exc}")
            detail = "" if not rollback_errors else "；回滚问题：" + "；".join(rollback_errors)
            raise RuntimeError(f"删除式提交失败：{exc}{detail}") from exc
        # 旧目标已删除时无法无损回滚；保留通过提交前检查的新候选，明确返回失败。
        target_record.skip_restore = True
        ctx.keep_imported_nodes.add(candidate_handle)
        raise RuntimeError(f"删除 Max 源模型后最终读回失败；已保留新候选以避免数据丢失：{exc}") from exc


def replace_with_source_skin(src: Any, target_record: SceneRecord, ctx: TransferContext, report: ObjectReport) -> bool:
    try:
        source_skin_count = int(rt.F2M_Helper.countSkin(src))
    except Exception as exc:
        report.add_exception(
            "替换失败：无法读取 FBX 目标模型蒙皮数量。",
            exc,
        )
        return False
    if source_skin_count != 1:
        report.add(f"替换失败：FBX 目标模型必须恰好有 1 个 Skin，实际为 {source_skin_count} 个。")
        return False

    source_skin = find_skin(src)
    if source_skin is None:
        report.add("替换失败：FBX 目标模型没有 Skin 修改器；模式二要求 FBX 目标模型必须带骨骼蒙皮。")
        return False

    old_target = target_record.node
    try:
        target_skin_count = int(rt.F2M_Helper.countSkin(old_target))
    except Exception as exc:
        report.add_exception(
            "替换失败：无法读取 Max 源模型蒙皮数量。",
            exc,
        )
        return False
    if target_skin_count != 1:
        report.add(f"替换失败：Max 源模型必须恰好有 1 个 Skin，实际为 {target_skin_count} 个。")
        return False

    target_skin = find_skin(old_target)
    if target_skin is None:
        report.add("替换失败：Max 源模型没有 Skin 修改器；模式二需要从它确认场景骨架。")
        return False

    try:
        target_presentation = target_presentation_state(old_target)
        if not activate_modifier(src, source_skin):
            raise RuntimeError("无法激活 FBX 目标网格的 Skin 修改器。")
        source_lookup = build_skin_bone_lookup(
            ctx,
            source_skin,
            use_scene_original_names=False,
        )
        duplicate_source_names = [
            name for name, candidates in source_lookup.exact.items() if len(candidates) > 1
        ]
        if duplicate_source_names:
            raise RuntimeError(
                "FBX 目标模型的 Skin 存在重复完整骨骼名，无法区分权重身份："
                + "，".join(sorted(duplicate_source_names))
            )
        if not activate_modifier(old_target, target_skin):
            raise RuntimeError("无法激活 Max 源模型的 Skin 修改器。")
        target_lookup = build_skin_bone_lookup(
            ctx,
            target_skin,
            use_scene_original_names=True,
        )
        duplicate_target_names = [
            name for name, candidates in target_lookup.exact.items() if len(candidates) > 1
        ]
        if duplicate_target_names:
            raise RuntimeError(
                "Max 源模型 Skin 存在重复完整骨骼名，无法安全复制绑定："
                + "，".join(sorted(duplicate_target_names))
            )
        target_modifier_state = source_skin_modifier_state(target_skin, old_target)
        target_bone_states = source_skin_bone_states(
            target_skin,
            old_target,
            target_lookup.entries,
        )
        expected_scene_bones = tuple(
            (entry.full_name, node_handle(entry.node))
            for entry in target_lookup.entries
        )
        vertex_count = mesh_counts(src)[0]
        if not activate_modifier(src, source_skin):
            raise RuntimeError("无法重新激活 FBX 目标网格的 Skin 修改器以读取权重。")
        rows = source_skin_weight_rows(source_skin, vertex_count, source_lookup.entries)
        vertex_states = source_skin_vertex_states(
            source_skin,
            src,
            vertex_count,
        )
        source_modifier_state = source_skin_modifier_state(source_skin, src)
        mapped_before_copy, normalized_fallbacks = map_weight_rows(
            rows,
            target_lookup,
            vertex_states,
        )
        if len(mapped_before_copy) != vertex_count:
            raise RuntimeError(
                f"提交前权重映射数量不完整：{len(mapped_before_copy)}/{vertex_count}"
            )
        modifier_state = SkinModifierState(
            enable_dq=source_modifier_state.enable_dq,
            property_values=target_modifier_state.property_values,
            # addModifierWithLocalData must establish the Mesh Bind TM for the
            # new FBX candidate node.  The exact candidate-adapted value is not
            # available until after the copy; never pre-seed it with the old
            # Max mesh's bind matrix.
            mesh_bind_tm=(),
        )
        source_skin_index_value = rt.F2M_Helper.modifierIndex(src, source_skin)
        if is_max_undefined(source_skin_index_value):
            raise RuntimeError("无法读取 FBX Skin 在修改器栈中的位置。")
        source_skin_index = int(source_skin_index_value)
        if source_skin_index < 1:
            raise RuntimeError(f"FBX Skin 修改器栈位置无效：{source_skin_index}")
        used_source_names = used_bone_names_from_weight_rows(rows)
        source_bone_count = len(source_lookup.entries)
        target_skin_bone_count = len(target_lookup.entries)
    except Exception as exc:
        report.add_exception(
            "整模替换：失败，FBX 权重或 Max 源 Skin 的场景骨架/本地绑定"
            "没有通过只读检查。",
            exc,
        )
        return False

    if ctx.options.dry_run:
        report.add(
            "整模替换：可执行。已读取 FBX 全部逐顶点权重/归一化/DQ，"
            "且每条实际权重影响都能唯一映射到 Max 源 Skin；正式执行时会把 "
            "Max Skin 及本地绑定数据复制到 FBX 网格原 Skin 栈位，再写入 FBX 权重。"
        )
        report.add(
            f"整模替换：FBX Skin 完整骨骼 {source_bone_count} 个，"
            f"本网格权重实际使用 {len(used_source_names)} 个，"
            f"Max 源模型 Skin 骨骼 {target_skin_bone_count} 个，"
            f"最终保留 Max Skin 的 {target_skin_bone_count} 个场景骨骼槽和绑定坐标系；"
            f"顶点 {vertex_count} 个。"
        )
        report.add(
            "整模替换：正式提交时会继承 Max 源模型的图层、隐藏/冻结、"
            "Box Mode、Renderable 与当前 Visibility，避免临时 FBX 导入层"
            "决定最终可见性。"
        )
        if normalized_fallbacks:
            report.add(
                "整模替换：以下骨骼未命中完整名，已确认规范化后各自只有一个候选："
                + "，".join(sorted(normalized_fallbacks))
            )
        unnormalized_count = sum(
            1 for state in vertex_states if state.unnormalized
        )
        dq_count = sum(1 for state in vertex_states if state.dq_weight > 0.0)
        report.add(
            f"整模替换：顶点附加状态已完整读取；未归一化顶点 {unnormalized_count} 个，"
            f"非零 DQ 权重顶点 {dq_count} 个，全局 DQ 开关为 {modifier_state.enable_dq}；"
            f"Max Skin 语义参数 {len(modifier_state.property_values)} 项、"
            f"Max 逐骨绑定状态 {len(target_bone_states)} 项。"
        )
        return True

    report.add(
        "整模替换：不调用 Skin Load Envelope 弹窗；保留 FBX 网格/材质/通道/法线，"
        "复制 Max 源 Skin 的场景骨骼与 local data；候选 Mesh Bind TM 采用 "
        "addModifierWithLocalData 为新 FBX 节点建立的实际值，仅按名称写入 FBX 顶点权重状态。"
    )

    old_material = None
    if ctx.options.keep_target_material_on_replace:
        try:
            old_material = old_target.material
        except Exception as exc:
            report.add_exception(
                "整模替换：读取 Max 源模型材质失败，已在修改候选前停止。",
                exc,
            )
            return False

    # FBX 目标模型成为替换后的正式模型；先脱离导入层级，避免清理临时骨骼时被一起删除。
    try:
        src.parent = None
        if not is_max_undefined(src.parent):
            raise RuntimeError(f"父节点读回仍为 {src.parent}")
        apply_target_presentation_state(src, target_presentation)
    except Exception as exc:
        report.add_exception(
            "整模替换：无法把新候选从 FBX 临时层级安全分离，或无法继承 "
            "Max 源模型图层/显示状态。",
            exc,
        )
        return False

    report.add(
        "整模替换：新候选已继承 Max 源模型图层/显示状态；"
        "临时 FBX 导入层的隐藏状态不会进入最终节点。"
    )

    try:
        authority_snapshot = candidate_authority_snapshot(src, source_skin)
    except Exception as exc:
        report.add_exception(
            "整模替换：无法建立 FBX 目标网格权威快照，已停止。",
            exc,
        )
        return False

    try:
        source_skin_handle = _anim_handle_or_none(source_skin)
        if source_skin_handle is None:
            raise RuntimeError("无法取得 FBX 目标 Skin 的稳定修改器句柄。")
        # Move the panel to a surviving object before releasing the doomed
        # wrapper.  The helper then resolves the modifier from its handle,
        # verifies that no panel reference remains, and deletes by stack index.
        # Never force Python/MAXScript GC while Max may still be unwinding
        # native modifier-local data.
        if not activate_modifier(old_target, target_skin):
            raise RuntimeError(
                "无法在删除 FBX 目标 Skin 前把 Modify 面板切换到仍会保留的 Max 源 Skin。"
            )
        source_skin = None
        removed = bool(
            rt.F2M_Helper.removeModifierByAnimHandle(
                src,
                int(source_skin_handle),
            )
        )
        if not removed:
            raise RuntimeError(helper_message() or "移除修改器实例返回失败状态")
    except Exception as exc:
        source_skin = None
        report.add_exception(
            "整模替换：删除 FBX 目标模型自带蒙皮失败。",
            exc,
        )
        return False
    if find_skin(src) is not None:
        report.add("整模替换：删除 FBX 目标模型自带 Skin 失败，已停止，避免新网格堆栈里残留多个 Skin。")
        return False

    source_lookup = None
    target_lookup = None
    try:
        copied_skin = copy_target_skin_to_node(
            old_target,
            target_skin,
            src,
            source_skin_index,
            report,
        )
        if copied_skin is None:
            raise RuntimeError("复制 Max 源 Skin 及本地绑定数据失败。")
        copied_lookup = build_skin_bone_lookup(
            ctx,
            copied_skin,
            use_scene_original_names=True,
        )
        mapped_rows, rebuilt_fallbacks = map_weight_rows(
            rows,
            copied_lookup,
            vertex_states,
        )
        if len(mapped_rows) != vertex_count:
            raise RuntimeError(
                f"复制后权重映射数量不完整：{len(mapped_rows)}/{vertex_count}"
            )
        verify_scene_bound_skin(
            ctx,
            copied_skin,
            src,
            expected_scene_bones,
            target_bone_states,
        )
        copied_modifier_state = source_skin_modifier_state(copied_skin, src)
        if not copied_modifier_state.mesh_bind_tm:
            raise RuntimeError(
                "addModifierWithLocalData 后无法读取候选自适应 Mesh Bind TM。"
            )
        modifier_state = SkinModifierState(
            enable_dq=source_modifier_state.enable_dq,
            property_values=target_modifier_state.property_values,
            mesh_bind_tm=copied_modifier_state.mesh_bind_tm,
        )
        applied_vertices = apply_weight_rows(
            copied_skin,
            src,
            mapped_rows,
            vertex_states,
            modifier_state,
            write_mesh_bind_tm=False,
        )
        verify_scene_bound_skin(
            ctx,
            copied_skin,
            src,
            expected_scene_bones,
            target_bone_states,
        )
        verify_candidate_authority_snapshot(
            authority_snapshot,
            src,
            copied_skin,
        )
    except Exception as exc:
        report.add_exception(
            "整模替换：复制 Max Skin 本地绑定数据、映射/写入 FBX 权重或"
            "目标网格身份读回失败，"
            "Max 源模型尚未提交变更。",
            exc,
        )
        return False

    write_method = LAST_WEIGHT_WRITE_METHOD or "未记录"
    if write_method != "逐顶点权威写入":
        report.add(
            "整模替换：Skin 权重没有使用唯一允许的逐顶点权威写入路径，"
            "候选不会提交。"
        )
        return False
    report.add(
        f"整模替换：已保留 Max Skin 场景骨骼表和本地绑定状态 {target_skin_bone_count} 个，"
        f"并读回验证骨骼节点身份、绑定矩阵、逐骨包络、全局参数及 "
        f"{applied_vertices}/{vertex_count} 个顶点权重；写入路径：{write_method}。"
    )
    if LAST_WEIGHT_BULK_FALLBACK_REASON:
        report.add(
            "整模替换：检测到已废止的批量首写/回退状态，候选不会提交。"
        )
        report.diagnostics.append(
            "[Skin 写入路径状态异常]\n"
            + LAST_WEIGHT_BULK_FALLBACK_REASON
        )
        return False
    all_fallbacks = normalized_fallbacks | rebuilt_fallbacks
    if all_fallbacks:
        report.add(
            "整模替换：以下骨骼使用了唯一候选的规范化名称回退："
            + "，".join(sorted(all_fallbacks))
        )

    if ctx.options.keep_target_material_on_replace:
        try:
            src.material = old_material
            material_readback = src.material
            if is_max_undefined(old_material):
                if not is_max_undefined(material_readback):
                    raise RuntimeError("Max 源模型无材质，但候选材质没有被清空")
            elif is_max_undefined(material_readback) or material_readback != old_material:
                raise RuntimeError("材质赋值后读回不一致")
        except Exception as exc:
            report.add_exception(
                "整模替换：复制 Max 源模型材质到候选失败，"
                "Max 源模型尚未提交变更。",
                exc,
            )
            return False
        report.add("整模替换：已按显式兼容选项改用 Max 源模型材质。")
    else:
        report.add(
            "整模替换：FBX 目标候选的节点、基础对象、材质对象、网格统计、"
            "对象变换、Pivot、目标图层/显示状态、非 Skin 修改器身份以及评估后全部世界"
            "顶点/包围盒已在 Skin 重建后读回不变；"
            "材质 ID、UV、顶点色、Alpha 与锁定法线没有进入复制路径，"
            "继续保留在同一个 FBX 候选基础对象中。"
        )

    try:
        # The optional material compatibility switch is an intentional change,
        # so establish the exact post-option state that every commit stage must
        # preserve.  The original FBX world-geometry/visibility state has
        # already been compared above before this fresh snapshot is accepted.
        commit_authority_snapshot = candidate_authority_snapshot(
            src,
            copied_skin,
        )
    except Exception as exc:
        report.add_exception(
            "整模替换：提交前无法建立最终候选权威快照，Max 源模型尚未变更。",
            exc,
        )
        return False

    # commit 可能删除 Max 源模型；进入提交前释放本层持有的旧节点/修改器 wrapper。
    copied_lookup = None
    target_skin = None
    old_target = None
    try:
        commit_replacement(
            ctx,
            src,
            target_record,
            copied_skin,
            commit_authority_snapshot,
            mapped_rows,
            vertex_states,
            modifier_state,
            expected_scene_bones,
            target_bone_states,
            report,
        )
    except Exception as exc:
        report.add_exception("整模替换：提交失败，未报告完成。", exc)
        return False

    report.add(
        f"整模替换：完成。最终节点就是 FBX 目标网格；材质/通道/锁定法线与 "
        f"FBX 一致，全部 {applied_vertices}/{vertex_count} 个顶点权重/归一化/DQ "
        "来自 FBX；Skin 场景骨骼、Bone Bind/Stretch/包络来自 Max 源模型，"
        "Mesh Bind 使用候选自适应 local data；评估后世界顶点、包围盒与可见性"
        "均已在提交前后完整读回。"
    )
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
    report.add(f"FBX 目标模型统计：点 {src_counts[0]}，边 {src_counts[1]}，面 {src_counts[2]}")
    report.add(f"Max 源模型统计：点 {dst_counts[0]}，边 {dst_counts[1]}，面 {dst_counts[2]}")
    for warning in transform_pair_warnings(src, dst):
        report.add(f"成对变换警告：{warning}")

    warnings = node_state_warnings(dst)
    if warnings:
        for warning in warnings:
            report.add(f"状态提醒：{warning}")
        report.status = "跳过：需解除对象状态"
        return report

    if ctx.options.dry_run:
        same_vertex = src_counts[0] == dst_counts[0]
        same_topology = src_counts == dst_counts
        if ctx.options.mode == "replace":
            report.add("检查结果：当前是替换网格并保留蒙皮模式，通道勾选不会参与判断。正式执行会以 FBX 目标网格数据为准，复制 Max 源模型 Skin，并按骨骼名称写入 FBX Skin 权重。")
            can_replace = replace_with_source_skin(src, target_record, ctx, report)
            report.status = "已检查：可替换" if can_replace else "失败：整模替换"
            return report
        report.add("检查结果：" + ("点数一致，可传外形。" if same_vertex else "点数不一致，不能用点序外形传递。"))
        report.add("检查结果：" + ("拓扑统计一致，可尝试 UV/顶点色/Alpha/材质与ID/顶点法线。" if same_topology else "拓扑统计不完全一致，不能安全复制通道或顶点法线。"))
        if same_topology and ctx.options.transfer_uv:
            report_missing_uv_channels(src, ctx.options.uv_channels, report)
        if same_topology and ctx.options.transfer_material_ids:
            try:
                if is_max_undefined(src.material):
                    report.add("检查结果：已勾选材质与 ID，但 FBX 目标模型没有可赋予的材质。")
                    report.status = "失败：FBX 目标模型无材质"
                    return report
                report.add("检查结果：FBX 目标模型有材质；正式执行会赋予 Max 源模型，并通过 ChannelInfo 多边形通道复制材质 ID。")
            except Exception as exc:
                report.add_exception(
                    "检查结果：读取 FBX 目标模型材质失败。",
                    exc,
                )
                report.status = "失败：读取材质"
                return report
        if find_skin(src) is not None:
            report.add("检查结果：FBX 目标模型带 Skin，可尝试整模替换并按骨骼名称重建 Max 源模型的 Skin。")
        else:
            report.add("检查结果：FBX 目标模型没有 Skin，不能走整模替换保留蒙皮。")
        report.status = "已检查"
        return report

    shape_ok = True
    channel_ok = True
    channel_requested = (
        ctx.options.transfer_uv
        or ctx.options.transfer_normals
        or ctx.options.transfer_vertex_color
        or ctx.options.transfer_alpha
        or ctx.options.transfer_material_ids
    )

    if ctx.options.mode != "replace":
        if topo_same_for_channels(src, dst):
            record_missing_requested_attributes(src, ctx, report)

        if ctx.options.transfer_shape:
            shape_ok = copy_shape(src, dst, report)

        if ctx.options.transfer_material_ids:
            channel_ok = copy_material_ids(src, dst, report) and channel_ok

        if ctx.options.transfer_uv:
            channel_ok = copy_uv_channels(src, dst, ctx.options.uv_channels, report) and channel_ok

        if ctx.options.transfer_normals:
            channel_ok = copy_normals(src, dst, report) and channel_ok

        if ctx.options.transfer_vertex_color:
            channel_ok = copy_vertex_channel(src, dst, 0, "顶点色 RGB", report) and channel_ok

        if ctx.options.transfer_alpha:
            channel_ok = copy_vertex_channel(src, dst, -2, "顶点 Alpha", report) and channel_ok

    replaced = False
    if should_replace_after_fail(ctx.options, shape_ok, channel_ok, channel_requested, src):
        dst = None
        replaced = replace_with_source_skin(src, target_record, ctx, report)

    if replaced:
        report.status = "完成：整模替换"
    elif ctx.options.mode == "replace":
        report.status = "失败：整模替换"
    elif (shape_ok or not ctx.options.transfer_shape) and (channel_ok or not channel_requested):
        report.status = "完成：同拓扑传递"
    else:
        report.status = "部分完成/跳过"
    return report


def cleanup_imported_nodes(ctx: TransferContext) -> None:
    keep = set(ctx.keep_imported_nodes)
    tracked_by_handle: Dict[int, Any] = {}
    for node in ctx.imported_nodes:
        if not is_valid_node(node):
            continue
        try:
            tracked_by_handle[node_handle(node)] = node
        except Exception:
            continue
    # 导入器可能在抛错前只创建了一部分节点；按原场景句柄重新扫描，不能只信成功返回列表。
    for node in all_scene_nodes():
        if not is_valid_node(node):
            continue
        try:
            handle = node_handle(node)
        except Exception:
            continue
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
                isolated_name = f"{ctx.import_prefix}{index:05d}__{node.name}"
                _set_node_name_exact(node, isolated_name)
            except Exception as exc:
                failures.append(f"{getattr(node, 'name', '<unknown>')}：{exc}")
        if failures:
            message = "保留导入节点时无法完成隔离改名：" + "；".join(failures)
            ctx.safety_errors.append(message)
            raise RuntimeError(message)
        return

    names_by_handle: Dict[int, str] = {}
    delete_handles: Set[int] = set()
    for handle, node in tracked_by_handle.items():
        if handle in keep or not is_valid_node(node):
            continue
        try:
            names_by_handle[handle] = str(node.name)
        except Exception:
            names_by_handle[handle] = str(handle)
        delete_handles.add(handle)

    # 先清掉上下文和局部容器对待删 wrapper 的强引用，再按句柄重新解析并
    # 一次批量删除。删除后的确认也只重新枚举场景，不再触碰旧 wrapper。
    tracked_handles = set(tracked_by_handle)
    ctx.imported_nodes = [
        node
        for handle, node in tracked_by_handle.items()
        if handle in keep and is_valid_node(node)
    ]
    tracked_by_handle.clear()
    node = None
    try:
        _delete_node_handles_strict(
            delete_handles,
            names_by_handle,
            label="临时 FBX 节点",
        )
    except Exception as exc:
        # 若删除不完整，重新枚举仍存活节点放回上下文，便于外层恢复阶段
        # 再次处理；不要把已经删除的 MXSWrapper 放回来。
        live_tracked = _live_nodes_by_handle(tracked_handles)
        ctx.imported_nodes = [
            live_tracked[handle]
            for handle in tracked_handles
            if handle in live_tracked
        ]
        message = str(exc)
        ctx.safety_errors.append(message)
        raise RuntimeError(message)

    live_kept = _live_nodes_by_handle(keep)
    ctx.imported_nodes = [
        live_kept[handle]
        for handle in keep
        if handle in live_kept
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

    if "FBX 目标模型变换警告" in body or "Max 源模型变换警告" in body:
        subject = (
            "FBX 目标模型"
            if "FBX 目标模型变换警告" in body or "FBX 目标网格" in body
            else "Max 源模型"
        )
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
        return f"{prefix}{subject}：{issue}"

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
    roots: List[str] = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        roots.append(local_app_data)
    temp_root = tempfile.gettempdir()
    if temp_root not in roots:
        roots.append(temp_root)

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
            failures.append(f"{path}：{exc}")
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
    temp_root = tempfile.gettempdir()
    if temp_root not in roots:
        roots.append(temp_root)
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


def show_execution_failure(ctx: TransferContext, log_path: str) -> None:
    """Show a clear result for handled failures that did not raise an exception."""

    if ctx.options.dry_run or reports_succeeded(ctx):
        return
    errors, warnings = issue_sections(ctx, max_lines=8)
    if errors:
        details = "\n".join(errors)
    else:
        failed_reports = [
            f"[{report.name}] {report.status}"
            for report in ctx.reports
            if not report.status.startswith("完成")
        ]
        details = "\n".join(unique_limited(failed_reports, 8)) or "正式传递没有成功完成。"
    body = (
        "传递未完成，失败结果没有提交。\n\n"
        + details
    )
    if warnings:
        body += "\n\n提醒：\n" + "\n".join(warnings)
    body += (
        "\n\n完整报告：\n"
        + (log_path or "报告文件写入失败，请查看 MaxScript Listener。")
    )
    try:
        rt.messageBox(
            _display_text(body),
            title=_display_text("FBX 到 3ds Max 传递未完成"),
            beep=True,
        )
    except Exception:
        pass


def reports_succeeded(ctx: TransferContext) -> bool:
    if ctx.safety_errors or not ctx.reports:
        return False
    expected_prefix = "已检查" if ctx.options.dry_run else "完成"
    return all(report.status.startswith(expected_prefix) for report in ctx.reports)


def _release_context_node_references(ctx: TransferContext) -> None:
    """在报告/对话框/返回前主动释放上下文中的 pymxs 节点 wrapper。"""

    ctx.imported_nodes.clear()
    ctx.committed_replacements.clear()
    for record in ctx.scene_records:
        record.node = None
    ctx.scene_by_original.clear()
    ctx.scene_records.clear()
    ctx.keep_imported_nodes.clear()
    ctx.replacement_nodes.clear()
    ctx.imported_bone_names.clear()


def _run_transfer_impl(options: TransferOptions) -> str:
    global LAST_RUN_OK, LAST_RUN_REPORT_PATH, LAST_RUN_SUMMARY
    LAST_RUN_OK = False
    LAST_RUN_REPORT_PATH = ""
    LAST_RUN_SUMMARY = ""

    try:
        ensure_runtime()
    except Exception as exc:
        LAST_RUN_SUMMARY = f"运行环境初始化失败：{exc}"
        raise
    if options.mode != "replace":
        LAST_RUN_SUMMARY = "f2m_skin_replace 只接受 mode='replace'；同拓扑传递必须调用 f2m_topology_transfer。"
        raise ValueError(LAST_RUN_SUMMARY)
    log = TransferLog()
    ctx = TransferContext(options, log)
    selected_geometry: List[Any] = []
    target_records: List[SceneRecord] = []
    sources: List[Any] = []
    pairs: List[Tuple[Any, SceneRecord]] = []
    src: Any = None
    target_record: Optional[SceneRecord] = None
    try:
        heap_before, heap_after = ensure_maxscript_heap_reserve()
        log.add(
            "MaxScript 内存堆安全下限已确认："
            f"{heap_before} -> {heap_after} 字节；"
            "仅扩充不足的会话，不主动垃圾回收。"
        )
        log.add(f"FBX 到 3ds Max 替换网格并保留蒙皮开始 v{TOOL_VERSION} / 作者：{TOOL_AUTHOR}")
        log.add(
            "数据方向：Max 源模型 <- FBX 目标模型；运行方式："
            + ("仅检查" if options.dry_run else "正式替换")
        )
        selected_geometry = [
            node
            for node in list(rt.selection)
            if is_valid_node(node) and is_geometry_node(node)
        ]
        if not selected_geometry:
            raise RuntimeError("请在 Max 场景里选中至少 1 个 Max 源网格。")
        if (
            not options.dry_run
            and len(selected_geometry) > 1
            and not options.backup_old_mesh
        ):
            raise RuntimeError(
                "多个 Max 源模型同时替换时必须启用“备份旧网格”，否则删除后的源节点无法保证批次级无损回滚。"
            )
        prepare_scene_names(ctx)
        target_records = selected_target_records(ctx)
        selected_geometry.clear()
        log.add(f"选中 Max 源网格数量：{len(target_records)}")
        import_fbx(ctx)

        sources = imported_geometry_nodes(ctx)
        log.add(f"FBX 目标网格数量：{len(sources)}")
        pairs, unmatched_reports = match_selected_targets_to_sources(target_records, sources)
        ctx.reports.extend(unmatched_reports)

        for src, target_record in pairs:
            log.add(f"匹配：Max 源模型 {target_record.original_name} <- FBX 目标模型 {src.name}")
            report = ObjectReport(name=target_record.original_name, status="处理中")
            src_counts = mesh_counts(src)
            dst_counts = mesh_counts(target_record.node)
            report.add(f"FBX 目标模型统计：点 {src_counts[0]}，边 {src_counts[1]}，面 {src_counts[2]}")
            report.add(f"Max 源模型统计：点 {dst_counts[0]}，边 {dst_counts[1]}，面 {dst_counts[2]}")
            for warning in transform_pair_warnings(src, target_record.node):
                report.add(f"成对变换警告：{warning}")
            warnings = [
                f"FBX 目标网格：{warning}"
                for warning in node_state_warnings(src)
            ]
            warnings.extend(
                f"Max 源模型：{warning}"
                for warning in node_state_warnings(target_record.node)
            )
            if warnings:
                for warning in warnings:
                    report.add(f"状态提醒：{warning}")
                report.status = "失败：需解除对象状态"
            else:
                replaced = replace_with_source_skin(src, target_record, ctx, report)
                if options.dry_run and replaced:
                    report.status = "已检查：可替换"
                elif replaced:
                    report.status = "完成：替换网格并保留蒙皮"
                else:
                    report.status = "失败：替换网格并保留蒙皮"
            ctx.reports.append(report)
            if report.diagnostics:
                ctx.diagnostics.append(
                    f"[对象：{target_record.original_name}]\n"
                    + "\n\n".join(report.diagnostics)
                )

        if ctx.committed_replacements and not reports_succeeded(ctx):
            pairs.clear()
            sources.clear()
            selected_geometry.clear()
            src = None
            target_record = None
            rollback_failures = rollback_committed_replacements(
                ctx,
                "同一批次中存在未匹配、状态阻断或替换失败的对象",
            )
            if rollback_failures:
                raise RuntimeError(
                    "批次中存在失败对象，且此前已提交对象的回滚不完整："
                    + "；".join(rollback_failures)
                )

        pairs.clear()
        sources.clear()
        selected_geometry.clear()
        target_records.clear()
        src = None
        target_record = None
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
        if options.show_ui:
            if options.dry_run:
                show_check_message(ctx, "FBX 到 3ds Max 检查结果", log_path)
            elif not LAST_RUN_OK:
                show_execution_failure(ctx, log_path)
            else:
                show_missing_transfer_attributes(ctx, log_path)
        ctx.committed_replacements = []
        return summary
    except Exception as exc:
        ctx.diagnostics.append("[运行或收尾阶段]\n" + traceback.format_exc())
        failure_visible = visible_exception_text(exc)
        failure_detail = _exception_text_and_release(exc)
        pairs.clear()
        sources.clear()
        selected_geometry.clear()
        target_records.clear()
        src = None
        target_record = None
        recovery_errors: List[str] = []
        try:
            rollback_errors = rollback_committed_replacements(
                ctx,
                f"运行或收尾阶段失败：{failure_detail}",
            )
            if rollback_errors:
                ctx.diagnostics.append(
                    "[批次回滚失败]\n" + "\n".join(str(item) for item in rollback_errors)
                )
            recovery_errors.extend(
                "批次回滚失败："
                + visible_exception_text(RuntimeError(str(item)))
                for item in rollback_errors
            )
        except Exception as rollback_exc:
            ctx.diagnostics.append("[批次回滚异常]\n" + traceback.format_exc())
            rollback_visible = visible_exception_text(rollback_exc)
            _exception_text_and_release(rollback_exc)
            recovery_errors.append(
                "批次回滚异常：" + rollback_visible
            )
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


def _restore_selection_after_replace(
    original_selection: Sequence[Tuple[int, str]],
) -> None:
    live_nodes = [node for node in all_scene_nodes() if is_valid_node(node)]
    by_handle = {node_handle(node): node for node in live_nodes}
    by_name: Dict[str, List[Any]] = {}
    for node in live_nodes:
        by_name.setdefault(str(node.name), []).append(node)

    restored: List[Any] = []
    seen: Set[int] = set()
    for original_handle, original_name in original_selection:
        chosen = None
        original_node = by_handle.get(int(original_handle))
        same_name = by_name.get(str(original_name), [])
        if (
            original_node is not None
            and str(original_node.name) == str(original_name)
        ):
            chosen = original_node
        elif len(same_name) == 1:
            # A committed replacement keeps the old target's original name,
            # while a backup (if enabled) is hidden and renamed.
            chosen = same_name[0]
        elif original_node is not None:
            chosen = original_node
        if chosen is None:
            continue
        handle = node_handle(chosen)
        if handle not in seen:
            restored.append(chosen)
            seen.add(handle)

    if restored:
        rt.select(restored)
    else:
        rt.clearSelection()


def run_transfer(options: TransferOptions) -> str:
    """Run replacement without viewport churn and always restore selection."""

    ensure_runtime()
    original_selection = [
        (node_handle(node), str(node.name))
        for node in list(rt.selection)
        if is_valid_node(node)
    ]
    try:
        with pymxs.redraw(False):
            return _run_transfer_impl(options)
    finally:
        try:
            _restore_selection_after_replace(original_selection)
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
    mode: str = "replace",
    dry_run: bool = False,
    transfer_shape: bool = True,
    transfer_uv: bool = True,
    uv_channels: str = "1",
    transfer_normals: bool = False,
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
    global LAST_RUN_OK, LAST_RUN_REPORT_PATH, LAST_RUN_SUMMARY
    if str(mode) != "replace":
        LAST_RUN_OK = False
        LAST_RUN_REPORT_PATH = ""
        LAST_RUN_SUMMARY = "整模替换引擎只支持 replace 模式。"
        raise ValueError(LAST_RUN_SUMMARY)
    options = TransferOptions(
        fbx_path=fbx_path,
        mode=mode,
        dry_run=bool(dry_run),
        transfer_shape=bool(transfer_shape),
        transfer_uv=bool(transfer_uv),
        uv_channels=parse_uv_channels(uv_channels),
        transfer_normals=bool(transfer_normals),
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


def _assert_selfcheck_weight_rows(
    expected: Sequence[Sequence[Tuple[str, float]]],
    actual: Sequence[Sequence[Tuple[str, float]]],
    label: str,
) -> None:
    if len(expected) != len(actual):
        raise AssertionError(f"{label} 权重顶点数不一致：{len(expected)}/{len(actual)}")
    for vertex_index, (expected_row, actual_row) in enumerate(
        zip(expected, actual),
        start=1,
    ):
        expected_map = {name: float(weight) for name, weight in expected_row}
        actual_map = {name: float(weight) for name, weight in actual_row}
        if set(expected_map) != set(actual_map):
            raise AssertionError(
                f"{label} 顶点 {vertex_index} 骨骼集合不一致："
                f"{sorted(expected_map)}/{sorted(actual_map)}"
            )
        for name, expected_weight in expected_map.items():
            actual_weight = actual_map[name]
            tolerance = max(0.0001, abs(expected_weight) * 0.0001)
            if abs(expected_weight - actual_weight) > tolerance:
                raise AssertionError(
                    f"{label} 顶点 {vertex_index} / {name} 权重不一致："
                    f"{expected_weight:.8f}/{actual_weight:.8f}"
                )


def _selfcheck_authority_content_snapshot(node: Any) -> Dict[str, Any]:
    """Return a primitive-only semantic digest for the isolated mode-2 gate.

    This deliberately lives outside the normal transfer path.  It evaluates the
    complete candidate mesh and streams geometry, oriented triangles, face
    material/smoothing data, supported map channels and render-corner normals
    into one digest, then frees the temporary TriMesh before returning.
    """

    if not is_valid_node(node):
        raise AssertionError("模式二内容快照目标已经无效。")

    digest = hashlib.sha256()
    component_digests = {
        name: hashlib.sha256()
        for name in (
            "object",
            "material",
            "modifiers",
            "geometry",
            "faces",
            "maps",
            "normals",
        )
    }

    def feed(label: str, *values: Any) -> None:
        if label.startswith("material-"):
            component = "material"
        elif label.startswith("non-skin-"):
            component = "modifiers"
        elif label in {"base-class", "object-transform"}:
            component = "object"
        elif label in {"mesh-counts", "vertex"}:
            component = "geometry"
        elif label == "face":
            component = "faces"
        elif label.startswith("map-"):
            component = "maps"
        elif label == "render-normal":
            component = "normals"
        else:
            raise AssertionError(f"模式二内容快照存在未分类字段：{label}")
        record = bytearray()
        record.extend(str(label).encode("utf-8"))
        record.extend(b"\x1f")
        for value in values:
            if isinstance(value, float):
                text = f"{value:.6f}"
                if text == "-0.000000":
                    text = "0.000000"
            else:
                text = str(value)
            record.extend(text.encode("utf-8"))
            record.extend(b"\x1e")
        record.extend(b"\n")
        digest.update(record)
        component_digests[component].update(record)

    def feed_point(label: str, value: Any) -> None:
        feed(
            label,
            float(value.x),
            float(value.y),
            float(value.z),
        )

    def feed_material(value: Any, path: str, depth: int = 0) -> None:
        if value is None or is_max_undefined(value):
            feed("material-none", path)
            return
        if depth > 8:
            raise AssertionError("模式二材质树深度异常。")
        feed("material-class", path, str(rt.classOf(value)))
        for property_name in ("diffuse", "ambient", "specular"):
            try:
                property_value = getattr(value, property_name)
                feed(
                    "material-color",
                    path,
                    property_name,
                    float(property_value.r),
                    float(property_value.g),
                    float(property_value.b),
                )
            except Exception:
                continue
        for property_name in ("opacity", "selfIllumAmount"):
            try:
                feed(
                    "material-scalar",
                    path,
                    property_name,
                    float(getattr(value, property_name)),
                )
            except Exception:
                continue
        try:
            sub_count = max(0, int(rt.getNumSubMtls(value)))
        except Exception:
            sub_count = 0
        feed("material-sub-count", path, sub_count)
        for sub_index in range(1, sub_count + 1):
            try:
                sub_material = rt.getSubMtl(value, sub_index)
            except Exception as exc:
                raise AssertionError(
                    f"模式二材质子项 {path}/{sub_index} 无法读取：{exc}"
                ) from exc
            try:
                feed_material(
                    sub_material,
                    f"{path}/{sub_index}",
                    depth + 1,
                )
            finally:
                sub_material = None

    feed("base-class", str(rt.classOf(node.baseObject)))
    feed_material(node.material, "root")
    feed("object-transform", *_matrix3_tuple(node.objectTransform, "模式二内容快照变换"))

    non_skin_modifiers: List[Tuple[str, str]] = []
    modifier: Any = None
    try:
        for modifier in list(node.modifiers):
            modifier_class = str(rt.classOf(modifier))
            if modifier_class.casefold() == "skin":
                continue
            non_skin_modifiers.append((modifier_class, str(modifier.name)))
    finally:
        modifier = None
    feed("non-skin-modifier-count", len(non_skin_modifiers))
    for modifier_class, modifier_name in non_skin_modifiers:
        feed("non-skin-modifier", modifier_class, modifier_name)

    mesh: Any = None
    skin_modifier: Any = None
    skin_was_enabled: Optional[bool] = None
    supported_channels: List[int] = []
    map_vertex_count = 0
    map_face_count = 0
    render_normal_corners = 0
    mesh_free_error = ""
    try:
        skin_modifier = find_skin(node)
        if skin_modifier is None:
            raise AssertionError("模式二内容快照找不到唯一 Skin。")
        try:
            skin_was_enabled = bool(skin_modifier.enabled)
            skin_modifier.enabled = False
            if bool(skin_modifier.enabled):
                raise AssertionError("模式二内容快照无法临时停用 Skin。")
            rt.update(node)
        except Exception as exc:
            raise AssertionError(
                f"模式二内容快照无法隔离基础对象：{exc}"
            ) from exc
        mesh = rt.snapshotAsMesh(node)
        vertex_count = int(rt.getNumVerts(mesh))
        face_count = int(rt.getNumFaces(mesh))
        if vertex_count < 1 or face_count < 1:
            raise AssertionError(
                f"模式二内容快照网格为空：{vertex_count}/{face_count}"
            )
        feed("mesh-counts", vertex_count, face_count)
        for vertex_index in range(1, vertex_count + 1):
            feed_point("vertex", rt.getVert(mesh, vertex_index))
        for face_index in range(1, face_count + 1):
            face = rt.getFace(mesh, face_index)
            feed(
                "face",
                int(face.x),
                int(face.y),
                int(face.z),
                int(rt.getFaceMatID(mesh, face_index)),
                int(rt.getFaceSmoothGroup(mesh, face_index)),
            )

        for channel_id in range(-2, 100):
            try:
                supported = bool(rt.meshop.getMapSupport(mesh, channel_id))
            except Exception as exc:
                raise AssertionError(
                    f"模式二内容快照无法读取 Map 通道 {channel_id}：{exc}"
                ) from exc
            if not supported:
                continue
            supported_channels.append(channel_id)
            channel_vertices = int(
                rt.meshop.getNumMapVerts(mesh, channel_id)
            )
            channel_faces = int(
                rt.meshop.getNumMapFaces(mesh, channel_id)
            )
            map_vertex_count += channel_vertices
            map_face_count += channel_faces
            feed(
                "map-channel",
                channel_id,
                channel_vertices,
                channel_faces,
            )
            for map_vertex_index in range(1, channel_vertices + 1):
                feed_point(
                    "map-vertex",
                    rt.meshop.getMapVert(
                        mesh,
                        channel_id,
                        map_vertex_index,
                    ),
                )
            for map_face_index in range(1, channel_faces + 1):
                map_face = rt.meshop.getMapFace(
                    mesh,
                    channel_id,
                    map_face_index,
                )
                feed(
                    "map-face",
                    int(map_face.x),
                    int(map_face.y),
                    int(map_face.z),
                )

        for face_index in range(1, face_count + 1):
            normal_values = list(
                rt.meshop.getFaceRNormals(mesh, face_index)
            )
            if len(normal_values) != 3:
                raise AssertionError(
                    f"模式二内容快照面 {face_index} 的渲染法线数量异常："
                    f"{len(normal_values)}/3"
                )
            for normal_value in normal_values:
                feed_point("render-normal", normal_value)
                render_normal_corners += 1
    finally:
        if mesh is not None:
            try:
                rt.free(mesh)
            except Exception as exc:
                mesh_free_error = visible_exception_text(exc)
        mesh = None
        if skin_modifier is not None and skin_was_enabled is not None:
            try:
                skin_modifier.enabled = bool(skin_was_enabled)
                if bool(skin_modifier.enabled) != bool(skin_was_enabled):
                    raise AssertionError("模式二内容快照没有恢复 Skin 启用状态。")
                rt.update(node)
            except Exception as exc:
                raise AssertionError(
                    f"模式二内容快照恢复 Skin 失败：{exc}"
                ) from exc
        skin_modifier = None
        if mesh_free_error:
            raise AssertionError(
                "模式二内容快照无法释放临时 TriMesh："
                + mesh_free_error
            )

    return {
        "sha256": digest.hexdigest().upper(),
        "vertex_count": vertex_count,
        "face_count": face_count,
        "map_channels": supported_channels,
        "map_vertex_count": map_vertex_count,
        "map_face_count": map_face_count,
        "render_normal_corners": render_normal_corners,
        "component_sha256": {
            name: value.hexdigest().upper()
            for name, value in component_digests.items()
        },
    }


def _mutate_selfcheck_source_authority_sentinel(
    node: Any,
    skin: Any,
    lookup: SkinBoneLookup,
    expected_rows: Sequence[Sequence[Tuple[str, float]]],
    expected_vertex_states: Sequence[SkinVertexState],
    expected_modifier_state: SkinModifierState,
    expected_content: Dict[str, Any],
) -> Dict[str, Any]:
    """Make the Max-side source visibly different before importing the target.

    The final node must return to the untouched FBX snapshot, not this sentinel.
    This prevents a same-file double import from making a reversed data flow
    appear green.
    """

    helper_ok = bool(
        rt.execute(
            r'''
            (
                global F2M_Mode2SelfcheckMutateSource
                fn F2M_Mode2SelfcheckMutateSource nodeHandle =
                (
                    local nodeValue = getAnimByHandle nodeHandle
                    if nodeValue == undefined or not isValidNode nodeValue do
                        throw "找不到模式二 Max 源哨兵节点。"
                    -- Keep the source stack structurally compatible with a normal
                    -- scene Skin.  Extra modifiers around Skin make Max 2023's
                    -- addModifierWithLocalData return a half-valid bone table and
                    -- are not representative of the user contract under test.
                    local sentinelMaterial = standardMaterial name:(
                        "__F2M_MODE2_SOURCE_SENTINEL__" +
                        (nodeHandle as string)
                    )
                    sentinelMaterial.diffuse = color 17 83 191
                    sentinelMaterial.opacity = 37.0
                    nodeValue.material = sentinelMaterial
                    update nodeValue
                    sentinelMaterial = undefined
                    nodeValue = undefined
                    #(true, 1)
                )
                true
            )
            '''
        )
    )
    if not helper_ok:
        raise AssertionError("无法安装模式二 Max 源内容哨兵。")

    mutation_result = rt.F2M_Mode2SelfcheckMutateSource(node_handle(node))
    mutation_values = list(mutation_result)
    mutation_result = None
    if len(mutation_values) != 2 or not bool(mutation_values[0]):
        raise AssertionError(
            f"模式二 Max 源内容哨兵返回异常：{mutation_values}"
        )
    changed_map_channels = int(mutation_values[1])
    mutation_values.clear()

    if not activate_modifier(node, skin):
        raise AssertionError("模式二 Max 源哨兵无法重新激活 Skin。")
    sentinel_vertex_index = 1
    expected_dq = float(expected_vertex_states[0].dq_weight)
    sentinel_dq = 0.733 if abs(expected_dq - 0.733) > 0.0001 else 0.411
    rt.skinOps.enableDQOverrideWeighting(
        skin,
        not bool(expected_modifier_state.enable_dq),
    )
    rt.skinOps.setVertexDQWeight(
        skin,
        sentinel_vertex_index,
        sentinel_dq,
    )
    try:
        old_bone_limit = int(skin.bone_Limit)
        skin.bone_Limit = 7 if old_bone_limit != 7 else 6
    except Exception as exc:
        raise AssertionError(
            f"模式二 Max 源哨兵无法修改 bone_Limit：{exc}"
        ) from exc
    try:
        rt.skinOps.Invalidate(skin, 0)
    except Exception:
        pass

    actual_rows = source_skin_weight_rows(
        skin,
        len(expected_rows),
        lookup.entries,
    )
    actual_states = source_skin_vertex_states(
        skin,
        node,
        len(expected_vertex_states),
    )
    actual_modifier_state = source_skin_modifier_state(skin, node)
    actual_content = _selfcheck_authority_content_snapshot(node)
    if (
        actual_rows == list(expected_rows)
        and actual_states == list(expected_vertex_states)
        and actual_modifier_state == expected_modifier_state
    ):
        raise AssertionError("模式二 Max 源 Skin 哨兵没有形成可观察差异。")
    if actual_content["sha256"] == expected_content["sha256"]:
        raise AssertionError("模式二 Max 源内容哨兵没有形成可观察差异。")
    return {
        "content_sha256": actual_content["sha256"],
        "map_sentinel_configured": changed_map_channels == 1,
        "skin_changed": True,
    }


def _selfcheck_used_skin_rebuild_plan(
    ctx: TransferContext,
    node: Any,
    skin: Any,
    lookup: SkinBoneLookup,
    rows: Sequence[Sequence[Tuple[str, float]]],
) -> Optional[Dict[str, Any]]:
    """Plan a clean used-bone Skin for the built-in Max-source fixture.

    Removing hundreds of FBX-only zero-weight slots leaves sparse internal BoneID
    storage that ``addModifierWithLocalData`` cannot safely clone in Max 2023.
    The real user scene contains a normal compact Skin, so the fixture rebuilds
    that same shape instead of using a deletion-damaged modifier.
    """

    used_names = set(used_bone_names_from_weight_rows(rows))
    used_entries = [
        entry for entry in lookup.entries if entry.full_name in used_names
    ]
    expected_names = tuple(entry.full_name for entry in used_entries)
    if set(expected_names) != used_names:
        raise AssertionError(
            "模式二自检无法从完整 FBX 骨骼表解析全部实际权重骨骼。"
        )
    if len(used_entries) == len(lookup.entries):
        return None
    stack_index_value = rt.F2M_Helper.modifierIndex(node, skin)
    if is_max_undefined(stack_index_value) or int(stack_index_value) < 1:
        raise AssertionError("模式二自检无法读取 Max 源 Skin 栈位。")
    skin_handle = _anim_handle_or_none(skin)
    if skin_handle is None:
        raise AssertionError("模式二自检无法读取 Max 源 Skin 稳定句柄。")
    return {
        "stack_index": int(stack_index_value),
        "skin_handle": int(skin_handle),
        "scene_bone_mappings": tuple(
            (entry.full_name, entry.node) for entry in used_entries
        ),
        "bone_states": tuple(
            source_skin_bone_states(skin, node, used_entries)
        ),
        "expected_names": expected_names,
    }


def run_selfcheck_fixture(fixture_path: str) -> Dict[str, Any]:
    """在自检子进程的空场景里验证真实 FBX Skin 预检、替换与全量读回。"""
    global LAST_RUN_OK, LAST_RUN_REPORT_PATH, LAST_RUN_SUMMARY
    setup_ctx: Optional[TransferContext] = None
    targets: List[Any] = []
    node: Any = None
    skin: Any = None
    lookup: Optional[SkinBoneLookup] = None
    save_reload_path = ""
    source_materialize_path = ""
    source_sentinel_count = 0
    authority_verification_count = 0
    scene_bone_handle_verification_count = 0
    saved_and_reloaded = False
    try:
        ensure_runtime()
        path = os.path.abspath(str(fixture_path))
        if not os.path.isfile(path):
            raise FileNotFoundError(path)

        # 该入口只由独立 3ds Max Batch 自检调用；无论成败都在 finally 清空夹具。
        _reset_max_file_safely()
        setup_options = TransferOptions(
            fbx_path=path,
            dry_run=True,
            keep_imported=True,
            backup_old_mesh=True,
            show_ui=False,
        )
        setup_ctx = TransferContext(setup_options, TransferLog())
        import_fbx(setup_ctx)
        targets = [
            node
            for node in imported_geometry_nodes(setup_ctx)
            if int(rt.F2M_Helper.countSkin(node)) == 1
        ]
        if not targets:
            raise AssertionError("内置蒙皮 FBX 没有恰好带一个 Skin 的网格。")

        expected: Dict[str, Dict[str, Any]] = {}
        target_identities: List[Tuple[int, str]] = []
        for node in targets:
            name = str(node.name)
            if name in expected:
                raise AssertionError(f"内置蒙皮 FBX 存在重复网格名：{name}")
            skin = find_skin(node)
            if skin is None or not activate_modifier(node, skin):
                raise AssertionError(f"无法激活夹具目标 Skin：{name}")
            counts = mesh_counts(node)
            lookup = build_skin_bone_lookup(
                setup_ctx,
                skin,
                use_scene_original_names=False,
            )
            rows = source_skin_weight_rows(skin, counts[0], lookup.entries)
            states = source_skin_vertex_states(skin, node, counts[0])
            fbx_modifier_state = source_skin_modifier_state(skin, node)
            authority_content = _selfcheck_authority_content_snapshot(node)
            rebuild_plan = _selfcheck_used_skin_rebuild_plan(
                setup_ctx,
                node,
                skin,
                lookup,
                rows,
            )
            if rebuild_plan is not None:
                stack_index = int(rebuild_plan["stack_index"])
                skin_handle = int(rebuild_plan["skin_handle"])
                scene_bone_mappings = rebuild_plan["scene_bone_mappings"]
                bone_states = rebuild_plan["bone_states"]
                expected_bone_names = rebuild_plan["expected_names"]
                lookup = None
                skin = None
                if not bool(
                    rt.F2M_Helper.removeModifierByAnimHandle(
                        node,
                        skin_handle,
                    )
                ):
                    raise AssertionError(
                        helper_message()
                        or "模式二自检无法移除原始完整 FBX Skin。"
                    )
                (
                    skin,
                    _selfcheck_mapped_rows,
                    rebuilt_vertices,
                    _selfcheck_fallbacks,
                ) = create_fbx_authority_skin(
                    setup_ctx,
                    node,
                    stack_index,
                    scene_bone_mappings,
                    bone_states,
                    rows,
                    states,
                    fbx_modifier_state,
                )
                if rebuilt_vertices != counts[0]:
                    raise AssertionError(
                        "模式二自检重建 Max 源 Skin 的顶点数不完整："
                        f"{rebuilt_vertices}/{counts[0]}"
                    )
                lookup = build_skin_bone_lookup(
                    setup_ctx,
                    skin,
                    use_scene_original_names=False,
                )
                if tuple(entry.full_name for entry in lookup.entries) != tuple(
                    expected_bone_names
                ):
                    raise AssertionError(
                        "模式二自检重建的紧凑 Max Skin 骨骼表不一致。"
                    )
                _assert_selfcheck_weight_rows(
                    rows,
                    source_skin_weight_rows(
                        skin,
                        counts[0],
                        lookup.entries,
                    ),
                    name,
                )
                rebuild_plan = None
                scene_bone_mappings = ()
            else:
                bone_states = source_skin_bone_states(
                    skin,
                    node,
                    lookup.entries,
                )
            scene_bone_handles = tuple(
                (
                    entry.full_name,
                    node_handle(entry.node),
                )
                for entry in lookup.entries
            )
            target_identities.append((node_handle(node), name))
            sentinel_result = _mutate_selfcheck_source_authority_sentinel(
                node,
                skin,
                lookup,
                rows,
                states,
                fbx_modifier_state,
                authority_content,
            )
            if not bool(sentinel_result.get("skin_changed")):
                raise AssertionError(f"模式二 Max 源 Skin 哨兵失败：{name}")
            if not bool(sentinel_result.get("map_sentinel_configured")):
                raise AssertionError(f"模式二 Max 源 Map 哨兵失败：{name}")
            max_modifier_state = source_skin_modifier_state(skin, node)
            expected[name] = {
                "counts": counts,
                "rows": rows,
                "vertex_states": states,
                "modifier_state": SkinModifierState(
                    enable_dq=fbx_modifier_state.enable_dq,
                    property_values=max_modifier_state.property_values,
                    mesh_bind_tm=max_modifier_state.mesh_bind_tm,
                ),
                "bone_states": bone_states,
                "authority_content": authority_content,
                "scene_bone_handles": scene_bone_handles,
            }
            source_sentinel_count += 1
            # lookup.entries contains one pymxs node wrapper for every Skin
            # bone.  None of those wrappers may survive into a later import,
            # node deletion, or resetMaxFile boundary.
            lookup = None
            skin = None
            node = None

        targets.clear()
        _release_context_node_references(setup_ctx)
        source_materialize_path = os.path.join(
            tempfile.gettempdir(),
            f"F2M_Mode2_MaxSource_{uuid.uuid4().hex}.max",
        )
        rt.clearSelection()
        if not bool(
            rt.saveMaxFile(
                source_materialize_path,
                useNewFile=True,
                quiet=True,
            )
        ):
            raise AssertionError("模式二自检无法保存紧凑 Max 源 Skin 夹具。")
        if not bool(
            rt.loadMaxFile(
                source_materialize_path,
                useFileUnits=True,
                quiet=True,
            )
        ):
            raise AssertionError("模式二自检无法重载紧凑 Max 源 Skin 夹具。")
        materialized_scene_nodes = all_scene_nodes()
        materialized_target_identities: List[Tuple[int, str]] = []
        for expected_name, expected_state in expected.items():
            mesh_candidates = [
                candidate
                for candidate in materialized_scene_nodes
                if is_valid_node(candidate)
                and is_geometry_node(candidate)
                and str(candidate.name) == expected_name
            ]
            if len(mesh_candidates) != 1:
                raise AssertionError(
                    "模式二自检重载后的 Max 源网格身份不唯一："
                    f"{expected_name}/{len(mesh_candidates)}"
                )
            materialized_target_identities.append(
                (node_handle(mesh_candidates[0]), expected_name)
            )
            refreshed_bone_handles: List[Tuple[str, int]] = []
            for bone_name, _old_handle in expected_state["scene_bone_handles"]:
                bone_candidates = [
                    candidate
                    for candidate in materialized_scene_nodes
                    if is_valid_node(candidate) and str(candidate.name) == bone_name
                ]
                if len(bone_candidates) != 1:
                    raise AssertionError(
                        "模式二自检重载后的 Max 场景骨骼身份不唯一："
                        f"{bone_name}/{len(bone_candidates)}"
                    )
                refreshed_bone_handles.append(
                    (bone_name, node_handle(bone_candidates[0]))
                )
                bone_candidates.clear()
            expected_state["scene_bone_handles"] = tuple(refreshed_bone_handles)
            mesh_candidates.clear()
        target_identities = materialized_target_identities
        materialized_scene_nodes.clear()

        def select_identities(
            identities: Sequence[Tuple[int, str]],
            label: str,
        ) -> None:
            selected: List[Any] = []
            current: Any = None
            try:
                for handle, expected_name in identities:
                    current = node_by_handle(handle)
                    if current is None or str(current.name) != expected_name:
                        raise AssertionError(
                            f"{label}目标身份失效：{expected_name}[{handle}]"
                        )
                    selected.append(current)
                    current = None
                rt.select(selected)
            finally:
                current = None
                selected.clear()

        select_identities(target_identities, "预检前")
        run_from_max(
            fbx_path=path,
            mode="replace",
            dry_run=True,
            keep_imported=False,
            backup_old_mesh=True,
            include_hidden=True,
            show_ui=False,
        )
        if not LAST_RUN_OK:
            raise AssertionError("内置蒙皮 FBX 预检失败：\n" + LAST_RUN_SUMMARY)

        for handle, expected_name in target_identities:
            node = node_by_handle(handle)
            if node is None or str(node.name) != expected_name:
                raise AssertionError("预检修改或删除了夹具目标。")
            node = None
        select_identities(target_identities, "备份式替换前")
        run_from_max(
            fbx_path=path,
            mode="replace",
            dry_run=False,
            keep_imported=False,
            backup_old_mesh=True,
            include_hidden=True,
            show_ui=False,
        )
        if not LAST_RUN_OK:
            raise AssertionError("内置蒙皮 FBX 实际替换失败：\n" + LAST_RUN_SUMMARY)

        def verify_current_targets(
            label: str,
            *,
            require_same_bone_handles: bool = True,
        ) -> Tuple[List[Tuple[int, str]], int, int]:
            nonlocal authority_verification_count
            nonlocal scene_bone_handle_verification_count
            scene_nodes = all_scene_nodes()
            verified_identities: List[Tuple[int, str]] = []
            verified_vertices = 0
            verified_bones = 0
            for name, expected_state in expected.items():
                counts = expected_state["counts"]
                rows = expected_state["rows"]
                states = expected_state["vertex_states"]
                modifier_state = expected_state["modifier_state"]
                bone_states = expected_state["bone_states"]
                authority_content = expected_state["authority_content"]
                scene_bone_handles = expected_state["scene_bone_handles"]
                candidates = [
                    node
                    for node in scene_nodes
                    if is_valid_node(node)
                    and is_geometry_node(node)
                    and str(node.name) == name
                ]
                if len(candidates) != 1:
                    raise AssertionError(
                        f"{label}后目标 {name} 数量异常：{len(candidates)}"
                    )
                node = candidates[0]
                if mesh_counts(node) != counts:
                    raise AssertionError(
                        f"{label}后目标 {name} 网格统计不一致："
                        f"{mesh_counts(node)}/{counts}"
                    )
                if int(rt.F2M_Helper.countSkin(node)) != 1:
                    raise AssertionError(
                        f"{label}后目标 {name} 不再恰好有一个 Skin。"
                    )
                skin = find_skin(node)
                if skin is None or not activate_modifier(node, skin):
                    raise AssertionError(
                        f"{label}后无法激活目标 Skin：{name}"
                    )
                lookup = build_skin_bone_lookup(
                    setup_ctx,
                    skin,
                    use_scene_original_names=False,
                )
                if len(lookup.entries) != len(bone_states):
                    raise AssertionError(
                        f"{label}后目标 {name} 的完整骨骼表数量不一致："
                        f"{len(lookup.entries)}/{len(bone_states)}"
                    )
                actual_scene_bone_handles = tuple(
                    (
                        entry.full_name,
                        node_handle(entry.node),
                    )
                    for entry in lookup.entries
                )
                if (
                    require_same_bone_handles
                    and actual_scene_bone_handles != scene_bone_handles
                ):
                    raise AssertionError(
                        f"{label}后目标 {name} 没有继续使用原 Max 场景骨骼节点。"
                    )
                if require_same_bone_handles:
                    scene_bone_handle_verification_count += 1
                actual_rows = source_skin_weight_rows(
                    skin,
                    counts[0],
                    lookup.entries,
                )
                _assert_selfcheck_weight_rows(rows, actual_rows, name)
                if source_skin_vertex_states(skin, node, counts[0]) != states:
                    raise AssertionError(
                        f"{label}后目标 {name} 的归一化/DQ 顶点状态不一致。"
                    )
                actual_modifier_state = source_skin_modifier_state(skin, node)
                if actual_modifier_state != modifier_state:
                    raise AssertionError(
                        f"{label}后目标 {name} 的 Skin 全局参数或 Mesh Bind TM 不一致。"
                    )
                verify_skin_bone_states(
                    bone_states,
                    source_skin_bone_states(
                        skin,
                        node,
                        lookup.entries,
                    ),
                )
                actual_authority_content = (
                    _selfcheck_authority_content_snapshot(node)
                )
                if (
                    actual_authority_content["sha256"]
                    != authority_content["sha256"]
                ):
                    expected_components = authority_content[
                        "component_sha256"
                    ]
                    actual_components = actual_authority_content[
                        "component_sha256"
                    ]
                    differing_components = [
                        component
                        for component in expected_components
                        if actual_components.get(component)
                        != expected_components[component]
                    ]
                    raise AssertionError(
                        f"{label}后目标 {name} 的 FBX 权威几何、材质 ID、"
                        "Map 通道、光滑组或渲染面角法线内容不一致："
                        f"差异分量 {differing_components}；"
                        f"{actual_authority_content['sha256']}/"
                        f"{authority_content['sha256']}"
                    )
                authority_verification_count += 1
                verified_identities.append((node_handle(node), name))
                verified_vertices += counts[0]
                verified_bones += len(bone_states)
                # Do not let the nested verification frame retain a Skin,
                # node, or per-bone wrapper after it returns to a deletion
                # boundary.
                lookup = None
                skin = None
                node = None
                candidates.clear()
            scene_nodes.clear()
            return verified_identities, verified_vertices, verified_bones

        final_target_identities, verified_vertices, verified_bones = (
            verify_current_targets("备份式替换")
        )

        # 再覆盖一次无备份删除式提交，专门验证删除前 wrapper 释放与句柄回读。
        select_identities(final_target_identities, "删除式替换前")
        run_from_max(
            fbx_path=path,
            mode="replace",
            dry_run=False,
            keep_imported=False,
            backup_old_mesh=False,
            include_hidden=True,
            show_ui=False,
        )
        if not LAST_RUN_OK:
            raise AssertionError(
                "内置蒙皮 FBX 无备份删除式替换失败：\n"
                + LAST_RUN_SUMMARY
            )
        (
            final_verified_identities,
            deleted_verified_vertices,
            deleted_verified_bones,
        ) = (
            verify_current_targets("删除式替换")
        )
        final_verified_identities.clear()
        if (
            deleted_verified_vertices != verified_vertices
            or deleted_verified_bones != verified_bones
        ):
            raise AssertionError("两种提交方式的最终读回覆盖数量不一致。")

        save_reload_path = os.path.join(
            tempfile.gettempdir(),
            f"F2M_Mode2_Authority_{uuid.uuid4().hex}.max",
        )
        rt.clearSelection()
        if not bool(
            rt.saveMaxFile(
                save_reload_path,
                useNewFile=True,
                quiet=True,
            )
        ):
            raise AssertionError("模式二删除式结果无法保存到隔离 MAX 场景。")
        if not os.path.isfile(save_reload_path):
            raise AssertionError("模式二保存重载场景没有落盘。")
        if not bool(
            rt.loadMaxFile(
                save_reload_path,
                useFileUnits=True,
                quiet=True,
            )
        ):
            raise AssertionError("模式二隔离 MAX 场景无法重载。")
        (
            reloaded_verified_identities,
            reloaded_verified_vertices,
            reloaded_verified_bones,
        ) = verify_current_targets(
            "保存重载",
            require_same_bone_handles=False,
        )
        reloaded_verified_identities.clear()
        if (
            reloaded_verified_vertices != verified_vertices
            or reloaded_verified_bones != verified_bones
        ):
            raise AssertionError("保存重载后的模式二读回覆盖数量不一致。")
        saved_and_reloaded = True
        if LAST_WEIGHT_WRITE_METHOD != "逐顶点权威写入":
            raise AssertionError(
                "模式二集成自检没有使用逐顶点权威写入："
                + (LAST_WEIGHT_WRITE_METHOD or "未记录")
            )
        if LAST_WEIGHT_BULK_FALLBACK_REASON:
            raise AssertionError(
                "模式二集成自检检测到已废止的批量首写/回退："
                + LAST_WEIGHT_BULK_FALLBACK_REASON
            )
        expected_verifications = len(expected) * 3
        source_sentinel_verified = source_sentinel_count == len(expected)
        authority_content_verified = (
            authority_verification_count == expected_verifications
        )
        scene_bone_handles_preserved = (
            scene_bone_handle_verification_count
            == len(expected) * 2
        )
        if not source_sentinel_verified:
            raise AssertionError("模式二 Max 源差异哨兵覆盖不完整。")
        if not authority_content_verified:
            raise AssertionError("模式二 FBX 内容指纹复验覆盖不完整。")
        if not scene_bone_handles_preserved:
            raise AssertionError("模式二场景骨骼句柄复验覆盖不完整。")

        summary = (
            f"内置蒙皮 FBX 的差异源哨兵、预检、备份式与删除式实际替换、"
            "保存重载、FBX 内容指纹、完整骨骼名称/场景句柄映射、"
            f"{len(expected)} 个网格/{verified_vertices} 个顶点权重、"
            f"{verified_bones} 个骨骼槽的 Bind TM/Stretch TM/包络、"
            "全局 Skin 参数、归一化与 DQ 状态全量读回通过。"
        )
        return {
            "ok": True,
            "summary": summary,
            "mesh_count": len(expected),
            "verified_vertices": verified_vertices,
            "verified_bone_slots": verified_bones,
            "weight_write_method": LAST_WEIGHT_WRITE_METHOD,
            "bulk_fallback_reason": LAST_WEIGHT_BULK_FALLBACK_REASON,
            "source_sentinel_verified": source_sentinel_verified,
            "authority_content_verified": authority_content_verified,
            "saved_and_reloaded": saved_and_reloaded,
            "scene_bone_handles_preserved": scene_bone_handles_preserved,
            "authority_content_coverage": {
                name: dict(state["authority_content"])
                for name, state in expected.items()
            },
        }
    except BaseException as exc:
        LAST_RUN_OK = False
        diagnostic = traceback.format_exc().strip()
        summary = "蒙皮替换集成自检失败：" + visible_exception_text(exc)
        _exception_text_and_release(exc)
        LAST_RUN_SUMMARY = summary
        return {
            "ok": False,
            "summary": summary,
            "diagnostic": diagnostic,
        }
    finally:
        lookup = None
        skin = None
        node = None
        targets.clear()
        try:
            if setup_ctx is not None:
                _release_context_node_references(setup_ctx)
        except Exception:
            pass
        try:
            rt.clearSelection()
        except Exception:
            pass
        try:
            _reset_max_file_safely()
        except Exception:
            pass
        try:
            if save_reload_path and os.path.isfile(save_reload_path):
                os.remove(save_reload_path)
        except Exception:
            pass
        try:
            if source_materialize_path and os.path.isfile(source_materialize_path):
                os.remove(source_materialize_path)
        except Exception:
            pass


def _validate_skin_runtime_fixture() -> None:
    """仅供隔离的 3ds Max Batch 验证；不会由插件正常入口调用。"""
    ensure_runtime()
    fixture = rt.execute(
        """
        (
            local testMesh = mesh \
                vertices:#([0,0,0], [10,0,0], [0,10,0]) \
                faces:#([1,2,3])
            testMesh.name = "__F2M_RUNTIME_SKIN_FIXTURE__"
            local boneA = dummy name:"__F2M_RUNTIME_BONE_A__" boxsize:[1,1,1]
            local boneB = dummy name:"__F2M_RUNTIME_BONE_B__" boxsize:[1,1,1]
            local testSkin = Skin()
            addModifier testMesh testSkin
            select testMesh
            max modify mode
            modPanel.setCurrentObject testSkin
            skinOps.addBone testSkin boneA 0
            skinOps.addBone testSkin boneB 1
            #(testMesh, testSkin, boneA, boneB)
        )
        """
    )
    items = list(fixture)
    if len(items) != 4:
        raise RuntimeError(f"Skin 运行夹具创建数量异常：{len(items)}")
    test_mesh, test_skin, bone_a, bone_b = items
    try:
        bone_id_a = int(rt.skinOps.GetBoneIDByListID(test_skin, 1))
        bone_id_b = int(rt.skinOps.GetBoneIDByListID(test_skin, 2))
        rows = [
            [(bone_id_a, 0.2), (bone_id_b, 0.3)],
            [(bone_id_a, 0.25), (bone_id_b, 0.75)],
            [(bone_id_b, 1.0)],
        ]
        vertex_states = [
            SkinVertexState(unnormalized=True, dq_weight=0.25),
            SkinVertexState(unnormalized=False, dq_weight=0.0),
            SkinVertexState(unnormalized=False, dq_weight=1.0),
        ]
        modifier_state = SkinModifierState(enable_dq=True)
        applied = apply_weight_rows(
            test_skin,
            test_mesh,
            rows,
            vertex_states,
            modifier_state,
        )
        if applied != 3:
            raise RuntimeError(f"Skin 运行夹具写入数量不完整：{applied}/3")
        if LAST_WEIGHT_WRITE_METHOD != "逐顶点权威写入":
            raise RuntimeError(
                "Skin 运行夹具没有使用预期的逐顶点权威写入路径："
                + (LAST_WEIGHT_WRITE_METHOD or "未记录")
            )
        if LAST_WEIGHT_BULK_FALLBACK_REASON:
            raise RuntimeError(
                "Skin 运行夹具不应先执行批量写入再回退："
                + LAST_WEIGHT_BULK_FALLBACK_REASON
            )
        if source_skin_vertex_states(test_skin, test_mesh, 3) != vertex_states:
            raise RuntimeError("Skin 运行夹具的逐顶点归一化/DQ 状态读回不一致")
        if source_skin_modifier_state(test_skin) != modifier_state:
            raise RuntimeError("Skin 运行夹具的全局 DQ 状态读回不一致")
    finally:
        cleanup_handles: Set[int] = set()
        cleanup_names: Dict[int, str] = {}
        cleanup_node: Any = None
        for cleanup_node in (test_mesh, bone_a, bone_b):
            if not is_valid_node(cleanup_node):
                continue
            try:
                handle = node_handle(cleanup_node)
                cleanup_handles.add(handle)
                cleanup_names[handle] = str(cleanup_node.name)
            except Exception:
                continue
        cleanup_node = None
        test_skin = None
        test_mesh = None
        bone_a = None
        bone_b = None
        items.clear()
        fixture = None
        try:
            rt.clearSelection()
        except Exception:
            pass
        try:
            _delete_node_handles_strict(
                cleanup_handles,
                cleanup_names,
                label="Skin 运行夹具临时节点",
            )
        except Exception:
            pass


if __name__ == "__main__":
    if rt is None:
        print("这个文件需要在 3ds Max 中运行。")
    elif os.environ.get("F2M_VALIDATE_SELFCHECK_FIXTURE"):
        _selfcheck_result = run_selfcheck_fixture(
            os.environ["F2M_VALIDATE_SELFCHECK_FIXTURE"]
        )
        if not bool(_selfcheck_result.get("ok", False)):
            raise RuntimeError(str(_selfcheck_result.get("summary", _selfcheck_result)))
        print("F2M_SKIN_SELFCHECK_FIXTURE_OK")
    elif os.environ.get("F2M_VALIDATE_SKIN_FIXTURE") == "1":
        _validate_skin_runtime_fixture()
        print("F2M_SKIN_RUNTIME_FIXTURE_OK")
    elif os.environ.get("F2M_VALIDATE_HELPER") == "1":
        ensure_runtime()
        print("F2M_HELPER_OK")
    else:
        rt.messageBox(_display_text("请通过 FBXTo3dsMax_UI.ms 启动中文界面。"), title=_display_text("FBX 到 3ds Max"))

