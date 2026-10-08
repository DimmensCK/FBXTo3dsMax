# -*- coding: utf-8 -*-
"""Focused 3ds Max Batch regressions for explicit-normal safety contracts."""

from __future__ import annotations

import importlib.util
import gc
import os
import sys
import tempfile
import traceback
import uuid

from pymxs import runtime as rt


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.makedirs(os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "FBXTo3dsMax", "Validation"), exist_ok=True)
RESULT = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "FBXTo3dsMax", "Validation", "_max_normals_safety_result.txt")


def reset_max_file_safely() -> None:
    """Collect live wrappers before destroying the isolated test scene."""

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
        raise RuntimeError("MAXScript wrapper collection failed before reset.")
    try:
        rt.clearSelection()
    except Exception:
        pass
    rt.resetMaxFile(rt.Name("noPrompt"))


def load_module(filename: str, module_name: str):
    path = os.path.join(ROOT, filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    if os.path.normcase(os.path.abspath(module.__file__)) != os.path.normcase(path):
        raise RuntimeError(f"module origin mismatch: {module.__file__}")
    return module


def install_test_helpers() -> None:
    rt.execute(
        r"""
        global F2M_NS_seedExplicit
        global F2M_NS_seedExplicitCurrent
        global F2M_NS_findF2M
        global F2M_NS_findByName
        global F2M_NS_countF2M
        global F2M_NS_firstNormal
        global F2M_NS_firstExplicit
        global F2M_NS_firstSpecified
        global F2M_NS_linearMatrix
        global F2M_NS_expectedNormal

        fn F2M_NS_seedExplicit n normalValue modName =
        (
            local normalMod = Edit_Normals()
            addModifier n normalMod
            normalMod.name = modName
            select n
            max modify mode
            modPanel.setCurrentObject normalMod
            normalMod.RebuildNormals node:n
            if (normalMod.GetNumFaces node:n) < 1 or
               (normalMod.GetFaceDegree 1 node:n) < 1 then return undefined
            local normalId = normalMod.GetNormalID 1 1 node:n
            local normalSelection = #{}
            normalSelection[normalId] = true
            if not (normalMod.MakeExplicit selection:normalSelection node:n) then
                return undefined
            local normalizedValue = normalize normalValue
            normalMod.SetNormal normalId &normalizedValue node:n
            normalMod.SetFaceNormalSpecified 1 1 specified:true node:n
            update n
            if not (normalMod.GetNormalExplicit normalId node:n) then return undefined
            if not (normalMod.GetFaceNormalSpecified 1 1 node:n) then return undefined
            if (distance (normalMod.GetNormal normalId node:n) normalizedValue) >= 0.00001 then
                return undefined
            normalMod
        )

        fn F2M_NS_seedExplicitCurrent n modName =
        (
            local normalMod = Edit_Normals()
            addModifier n normalMod
            normalMod.name = modName
            select n
            max modify mode
            modPanel.setCurrentObject normalMod
            normalMod.RebuildNormals node:n
            if (normalMod.GetNumFaces node:n) < 1 or
               (normalMod.GetFaceDegree 1 node:n) < 1 then return undefined
            local normalId = normalMod.GetNormalID 1 1 node:n
            local normalSelection = #{}
            normalSelection[normalId] = true
            if not (normalMod.MakeExplicit selection:normalSelection node:n) then
                return undefined
            normalMod.SetFaceNormalSpecified 1 1 specified:true node:n
            update n
            if not (normalMod.GetNormalExplicit normalId node:n) then return undefined
            if not (normalMod.GetFaceNormalSpecified 1 1 node:n) then return undefined
            normalMod
        )

        fn F2M_NS_findF2M n =
        (
            for m in n.modifiers where
                classof m == Edit_Normals and
                matchPattern (m.name as string) pattern:"F2M_*" ignoreCase:false do
                    return m
            undefined
        )

        fn F2M_NS_findByName n wanted =
        (
            for m in n.modifiers where (m.name as string) == wanted do return m
            undefined
        )

        fn F2M_NS_countF2M n =
        (
            local count = 0
            for m in n.modifiers where
                classof m == Edit_Normals and
                matchPattern (m.name as string) pattern:"F2M_*" ignoreCase:false do
                    count += 1
            count
        )

        fn F2M_NS_firstNormal n modInst =
        (
            local normalId = modInst.GetNormalID 1 1 node:n
            modInst.GetNormal normalId node:n
        )

        fn F2M_NS_firstExplicit n modInst =
        (
            local normalId = modInst.GetNormalID 1 1 node:n
            modInst.GetNormalExplicit normalId node:n
        )

        fn F2M_NS_firstSpecified n modInst =
        (
            modInst.GetFaceNormalSpecified 1 1 node:n
        )

        fn F2M_NS_linearMatrix sourceMatrix =
        (
            matrix3 sourceMatrix.row1 sourceMatrix.row2 sourceMatrix.row3 [0, 0, 0]
        )

        -- Independent geometric construction: transform two tangents from the
        -- source local plane into target local space and cross them.
        fn F2M_NS_expectedNormal src dst =
        (
            local sourceNormal = normalize [1.0, 2.0, 3.0]
            local helperAxis = if (abs (dot sourceNormal [0, 0, 1])) < 0.9 then
                [0, 0, 1]
            else
                [0, 1, 0]
            local tangentA = normalize (cross helperAxis sourceNormal)
            local tangentB = normalize (cross sourceNormal tangentA)
            local srcLinear = F2M_NS_linearMatrix src.objectTransform
            local dstInverseLinear = F2M_NS_linearMatrix (inverse dst.objectTransform)
            local targetTangentA = (tangentA * srcLinear) * dstInverseLinear
            local targetTangentB = (tangentB * srcLinear) * dstInverseLinear
            normalize (cross targetTangentA targetTangentB)
        )
        """
    )


def selection_handles() -> list[int]:
    return sorted(int(rt.getHandleByAnim(node)) for node in list(rt.selection))


def create_pair(prefix: str):
    source = rt.Box(name=f"{prefix}_Source", length=10, width=10, height=10)
    target = rt.copy(source)
    target.name = f"{prefix}_Target"
    rt.convertToPoly(source)
    rt.convertToPoly(target)
    sentinel = rt.Sphere(name=f"{prefix}_Sentinel", radius=1)
    sentinel.position = rt.Point3(100, 100, 100)
    return source, target, sentinel


def require_seed(node, vector, name: str):
    modifier = rt.F2M_NS_seedExplicit(node, vector, name)
    if modifier is None or str(modifier) == "undefined":
        raise AssertionError(f"unable to seed explicit normal on {node.name}")
    return modifier


def require_current_seed(node, name: str):
    modifier = rt.F2M_NS_seedExplicitCurrent(node, name)
    if modifier is None or str(modifier) == "undefined":
        raise AssertionError(f"unable to seed current explicit normal on {node.name}")
    return modifier


def assert_selection_restored(expected: list[int], label: str) -> None:
    actual = selection_handles()
    if actual != expected:
        raise AssertionError(f"{label}: selection changed {expected} -> {actual}")


def read_first_normal(node, modifier):
    if not bool(rt.F2M_Helper.activateModifier(node, modifier)):
        raise AssertionError(f"unable to activate Edit Normals on {node.name}")
    normal_id = modifier.GetNormalID(1, 1, node=node)
    return (
        modifier.GetNormal(normal_id, node=node),
        bool(modifier.GetNormalExplicit(normal_id, node=node)),
        bool(modifier.GetFaceNormalSpecified(1, 1, node=node)),
    )


def case_plain_mesh_rejected(module) -> str:
    reset_max_file_safely()
    source, target, sentinel = create_pair("F2M_NS_Plain")
    rt.select(sentinel)
    selected = selection_handles()

    if bool(rt.F2M_Helper.canReadExplicitNormals(source)):
        raise AssertionError("plain mesh was reported as having custom normals")
    assert_selection_restored(selected, "plain preflight")
    if int(source.modifiers.count) != 0:
        raise AssertionError("temporary source Edit Normals was not removed")

    if bool(rt.F2M_Helper.copyExplicitNormals(source, target)):
        raise AssertionError("plain mesh custom-normal copy unexpectedly succeeded")
    assert_selection_restored(selected, "plain copy")
    if int(rt.F2M_NS_countF2M(target)) != 0:
        raise AssertionError("failed plain copy left an F2M Edit Normals modifier")
    if int(source.modifiers.count) != 0:
        raise AssertionError("failed plain copy left its temporary source reader")
    return "plain mesh rejected; selection and temporary stack restored"


def case_inverse_transpose(module) -> str:
    reset_max_file_safely()
    source, target, sentinel = create_pair("F2M_NS_XForm")
    source.transform = rt.execute(
        "(scaleMatrix [2.0,0.75,3.0]) * "
        "(rotateXMatrix 23.0) * (rotateZMatrix -31.0) * "
        "(transMatrix [10.0,-5.0,3.0])"
    )
    target.transform = rt.execute(
        "(scaleMatrix [0.6,2.5,1.4]) * "
        "(rotateYMatrix -17.0) * (rotateZMatrix 28.0) * "
        "(transMatrix [-4.0,8.0,1.0])"
    )
    require_seed(source, rt.Point3(1, 2, 3), "Source_Custom_Normal")
    expected = rt.F2M_NS_expectedNormal(source, target)

    rt.select(sentinel)
    selected = selection_handles()
    if not bool(rt.F2M_Helper.copyExplicitNormals(source, target)):
        raise AssertionError(
            "inverse-transpose copy failed: " + str(rt.F2M_Helper.lastMessage)
        )
    assert_selection_restored(selected, "inverse-transpose copy")
    modifier = rt.F2M_NS_findF2M(target)
    if modifier is None or str(modifier) == "undefined":
        raise AssertionError("inverse-transpose copy did not leave the F2M modifier")
    actual, is_explicit, is_specified = read_first_normal(target, modifier)
    if (
        actual is None
        or expected is None
        or str(actual) == "undefined"
        or str(expected) == "undefined"
    ):
        raise AssertionError(
            f"inverse-transpose probe returned undefined: "
            f"expected={expected!r}, actual={actual!r}, modifier={modifier!r}"
        )
    delta = float(rt.distance(actual, expected))
    if delta >= 1.0e-5:
        raise AssertionError(
            f"inverse-transpose normal mismatch: delta={delta}, "
            f"expected={expected}, actual={actual}"
        )
    if not is_explicit:
        raise AssertionError("transformed custom normal is not Explicit")
    if not is_specified:
        raise AssertionError("transformed custom face corner is not Specified")
    return f"inverse-transpose rotation/non-uniform-scale delta={delta:.8f}"


def case_upper_override_fails_closed(module) -> str:
    reset_max_file_safely()
    source, target, sentinel = create_pair("F2M_NS_Override")
    require_seed(source, rt.Point3(1, 2, 3), "Source_Custom_Normal")
    user_modifier = require_seed(
        target, rt.Point3(-2, 1, 0.5), "User_Edit_Normals_Override"
    )
    user_before, _, _ = read_first_normal(target, user_modifier)

    rt.select(sentinel)
    selected = selection_handles()
    if bool(rt.F2M_Helper.copyExplicitNormals(source, target)):
        raise AssertionError("upper user Edit Normals override was not blocked")
    message = str(rt.F2M_Helper.lastMessage)
    assert_selection_restored(selected, "upper override")
    if int(rt.F2M_NS_countF2M(target)) != 0:
        raise AssertionError("failed override copy left an F2M modifier")
    user_after = rt.F2M_NS_findByName(target, "User_Edit_Normals_Override")
    if user_after is None or str(user_after) == "undefined":
        raise AssertionError("failed override copy removed the user modifier")
    user_after_normal, _, _ = read_first_normal(target, user_after)
    if float(rt.distance(user_before, user_after_normal)) >= 1.0e-5:
        raise AssertionError("failed override copy changed the user normal")
    if "用户法线修改器" not in message and "覆盖插件结果" not in message:
        raise AssertionError(
            "override failure was not attributed to the user normal modifier: "
            f"{message}"
        )
    return "user Edit Normals interference detected; F2M state rolled back"


def case_zero_residual_uses_smoothing_only(module) -> str:
    reset_max_file_safely()
    source, target, sentinel = create_pair("F2M_NS_ZeroResidual")
    face_count = module.base_face_count(source)
    all_one = [1] * face_count
    if not bool(rt.F2M_Helper.setFaceSmoothingGroups(source, rt.Array(*all_one))):
        raise AssertionError(str(rt.F2M_Helper.lastMessage))
    if not bool(rt.F2M_Helper.setFaceSmoothingGroups(target, rt.Array(*all_one))):
        raise AssertionError(str(rt.F2M_Helper.lastMessage))
    require_current_seed(source, "Source_Zero_Residual_Normal")
    rt.select(sentinel)
    selected = selection_handles()
    if not bool(
        rt.F2M_Helper.copyExplicitNormalResiduals(
            source,
            target,
            angleToleranceDegrees=0.1,
        )
    ):
        raise AssertionError(str(rt.F2M_Helper.lastMessage))
    assert_selection_restored(selected, "zero residual")
    if int(rt.F2M_NS_countF2M(target)) != 1:
        raise AssertionError("zero residual did not retain one safe F2M baseline")
    final_mod = rt.F2M_NS_findByName(target, "F2M_顶点法线")
    if final_mod is None or str(final_mod) == "undefined":
        raise AssertionError("zero residual safe F2M baseline is missing")
    custom_counts = [
        int(value)
        for value in list(
            rt.F2M_Helper.editNormalsCustomCounts(target, final_mod)
        )
    ]
    final_mod = None
    if custom_counts != [0, 0]:
        raise AssertionError(
            f"zero residual baseline is not fully SG-driven: {custom_counts}"
        )
    return "all normals represented by SG; one non-Explicit F2M safety baseline"


def case_sg_only_removes_stale_f2m_normals(module) -> str:
    reset_max_file_safely()
    source, target, sentinel = create_pair("F2M_NS_SGOnly")
    face_count = module.base_face_count(source)
    source_masks = [2] * face_count
    if not bool(
        rt.F2M_Helper.setFaceSmoothingGroups(
            source, rt.Array(*source_masks)
        )
    ):
        raise AssertionError(str(rt.F2M_Helper.lastMessage))
    require_seed(
        target,
        rt.Point3(1, 2, 3),
        "F2M_顶点法线_旧版残留",
    )
    if int(rt.F2M_Helper.countF2MNormalModifiers(target)) != 1:
        raise AssertionError("failed to seed one stale F2M normal modifier")

    rt.select(sentinel)
    selected = selection_handles()
    context = module.TransferContext(
        module.TransferOptions(
            fbx_path="",
            transfer_smoothing_groups=True,
            transfer_normals=False,
            show_ui=False,
        ),
        module.TransferLog(),
    )
    report = module.ObjectReport(name=str(target.name), status="test")
    if not module.copy_smoothing_groups(source, target, context, report):
        raise AssertionError("\n".join(report.messages))
    assert_selection_restored(selected, "SG-only stale-normal cleanup")
    if int(rt.F2M_Helper.countF2MNormalModifiers(target)) != 0:
        raise AssertionError("SG-only transfer left a stale F2M normal modifier")
    readback = [
        int(value)
        for value in list(rt.F2M_Helper.getFaceSmoothingGroups(target))
    ]
    if readback != source_masks:
        raise AssertionError(f"SG-only masks changed: {readback}")
    if not any("已清理旧版插件自有顶点法线修改器 1 个" in text for text in report.messages):
        raise AssertionError(
            "SG-only cleanup was not reported clearly: "
            + " | ".join(report.messages)
        )
    return "stale plug-in Edit Normals removed before SG-only write/readback"


def case_sg_and_explicit_coexist(module) -> str:
    reset_max_file_safely()
    source, target, sentinel = create_pair("F2M_NS_Hybrid")
    face_count = module.base_face_count(source)
    all_one = [1] * face_count
    all_two = [2] * face_count
    if not bool(rt.F2M_Helper.setFaceSmoothingGroups(source, rt.Array(*all_one))):
        raise AssertionError(str(rt.F2M_Helper.lastMessage))
    if not bool(rt.F2M_Helper.setFaceSmoothingGroups(target, rt.Array(*all_two))):
        raise AssertionError(str(rt.F2M_Helper.lastMessage))
    require_seed(source, rt.Point3(1, 2, 3), "Source_Local_Explicit")

    context = module.TransferContext(
        module.TransferOptions(
            fbx_path="",
            transfer_smoothing_groups=True,
            show_ui=False,
        ),
        module.TransferLog(),
    )
    report = module.ObjectReport(name=str(target.name), status="test")
    if not module.copy_smoothing_groups(source, target, context, report):
        raise AssertionError("\n".join(report.messages))

    rt.select(sentinel)
    selected = selection_handles()
    if not module.copy_normals(
        source,
        target,
        report,
        smoothing_residual_only=True,
    ):
        raise AssertionError("\n".join(report.messages))
    assert_selection_restored(selected, "hybrid copy")
    readback = [
        int(value)
        for value in list(rt.F2M_Helper.getFaceSmoothingGroups(target))
    ]
    if readback != all_one:
        raise AssertionError(f"custom normals changed SG1 masks: {readback}")
    modifier = rt.F2M_NS_findF2M(target)
    if modifier is None or str(modifier) == "undefined":
        raise AssertionError("hybrid copy lost the F2M Edit Normals modifier")
    _, is_explicit, _ = read_first_normal(target, modifier)
    if not is_explicit:
        raise AssertionError("hybrid custom normal is not Explicit")

    persistence_path = os.path.join(
        tempfile.gettempdir(), f"FBXTo3dsMax_normals_safety_{uuid.uuid4().hex}.max"
    )
    persisted = None
    persisted_modifier = None
    try:
        if not bool(rt.saveMaxFile(persistence_path, useNewFile=False, quiet=True)):
            raise AssertionError("unable to save hybrid persistence fixture")
        try:
            module._release_context_node_references(context)
        except Exception:
            pass
        source = None
        target = None
        sentinel = None
        modifier = None
        context = None
        try:
            rt.clearSelection()
        except Exception:
            pass
        reset_max_file_safely()
        if not bool(rt.loadMaxFile(persistence_path, quiet=True, useFileUnits=True)):
            raise AssertionError("unable to reload hybrid persistence fixture")
        persisted = rt.getNodeByName("F2M_NS_Hybrid_Target")
        if persisted is None or str(persisted) == "undefined":
            raise AssertionError("persisted hybrid target was not found")
        persisted_masks = [
            int(value)
            for value in list(rt.F2M_Helper.getFaceSmoothingGroups(persisted))
        ]
        if persisted_masks != all_one:
            raise AssertionError(f"persisted SG1 masks changed: {persisted_masks}")
        persisted_modifier = rt.F2M_NS_findF2M(persisted)
        if persisted_modifier is None or str(persisted_modifier) == "undefined":
            raise AssertionError("persisted F2M Edit Normals modifier was not found")
        _, persisted_explicit, _ = read_first_normal(
            persisted, persisted_modifier
        )
        if not persisted_explicit:
            raise AssertionError("persisted custom normal is no longer Explicit")
    finally:
        persisted_modifier = None
        persisted = None
        source = None
        target = None
        sentinel = None
        modifier = None
        try:
            rt.clearSelection()
        except Exception:
            pass
        try:
            reset_max_file_safely()
        except Exception:
            pass
        try:
            if os.path.exists(persistence_path):
                os.remove(persistence_path)
        except Exception:
            pass
    return "SG1 + local Explicit normal coexist and survive save/reload"


def main() -> list[str]:
    module = load_module("f2m_topology_transfer.py", "_f2m_normals_safety")
    module.ensure_runtime()
    install_test_helpers()
    cases = [
        ("plain", case_plain_mesh_rejected),
        ("inverse_transpose", case_inverse_transpose),
        ("upper_override", case_upper_override_fails_closed),
        ("zero_residual", case_zero_residual_uses_smoothing_only),
        ("sg_only_cleanup", case_sg_only_removes_stale_f2m_normals),
        ("hybrid", case_sg_and_explicit_coexist),
    ]
    details = []
    failures = 0
    for name, callback in cases:
        try:
            detail = callback(module)
            details.append(f"{name}: PASS - {detail}")
        except BaseException:
            failures += 1
            details.append(f"{name}: FAIL\n{traceback.format_exc()}")
    if failures:
        raise AssertionError(
            f"{failures}/{len(cases)} focused normal-safety cases failed\n"
            + "\n".join(details)
        )
    return details


def _script_entry() -> None:
    try:
        lines = main()
        text = "PASS\n" + "\n".join(lines)
    except BaseException:
        text = "FAIL\n" + traceback.format_exc()
    finally:
        try:
            reset_max_file_safely()
        except Exception:
            pass

    with open(RESULT, "w", encoding="utf-8") as handle:
        handle.write(text + "\n")

    if not text.startswith("PASS"):
        raise RuntimeError(text)


if __name__ == "__main__":
    _script_entry()
