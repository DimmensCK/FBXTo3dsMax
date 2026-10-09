"""程序化验证面序/面角映射覆盖全部模式一通道。"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import os
import sys
import traceback
from types import SimpleNamespace
from typing import Any

import pymxs


rt = pymxs.runtime
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
RUNTIME_ROOT = os.path.join(ROOT, "contents") if os.path.isdir(os.path.join(ROOT, "contents")) else ROOT
os.makedirs(os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "FBXTo3dsMax", "Validation"), exist_ok=True)
RESULT = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "FBXTo3dsMax", "Validation", "_max_topology_mapping_channels_result.json")


def load_topology() -> Any:
    path = os.path.join(RUNTIME_ROOT, "f2m_topology_transfer.py")
    name = "_f2m_mapping_channels_runtime"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def make_pair():
    vertices = rt.Array(
        rt.Point3(0, 0, 0),
        rt.Point3(10, 0, 0),
        rt.Point3(10, 10, 0),
        rt.Point3(0, 10, 0),
    )
    fbx_target = rt.mesh(
        name="F2M_Map_FBX_Target",
        vertices=vertices,
        faces=rt.Array(
            rt.Point3(1, 2, 3),
            rt.Point3(1, 3, 4),
        ),
    )
    max_source = rt.mesh(
        name="F2M_Map_Max_Source",
        vertices=vertices,
        faces=rt.Array(
            rt.Point3(3, 4, 1),
            rt.Point3(2, 3, 1),
        ),
    )
    return fbx_target, max_source


def install_helpers() -> None:
    rt.execute(
        r"""
        global F2M_MAP_seedChannel
        global F2M_MAP_seedExplicit
        global F2M_MAP_findNormals

        fn F2M_MAP_seedChannel n channelId =
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

        fn F2M_MAP_seedExplicit n =
        (
            local normalMod = Edit_Normals()
            addModifier n normalMod
            normalMod.name = "F2M_MAP_源显式法线"
            select n
            max modify mode
            modPanel.setCurrentObject normalMod
            normalMod.RebuildNormals node:n
            local normalId = normalMod.GetNormalID 1 1 node:n
            local selectionSet = #{}
            selectionSet[normalId] = true
            if not (normalMod.MakeExplicit selection:selectionSet node:n) do return undefined
            local value = normalize [0.2,0.4,0.8]
            normalMod.SetNormal normalId &value node:n
            normalMod.SetFaceNormalSpecified 1 1 specified:true node:n
            update n
            #(normalMod, normalId, value)
        )

        fn F2M_MAP_findNormals n =
        (
            for m in n.modifiers where
                classof m == Edit_Normals and
                (m.name as string) == "F2M_顶点法线" do return m
            undefined
        )
        """
    )


def map_face(node, channel: int, face: int) -> list[int]:
    value = rt.meshop.getMapFace(node.mesh, channel, face)
    return [int(value.x), int(value.y), int(value.z)]


def point_values(value) -> list[float]:
    return [
        round(float(value.x), 6),
        round(float(value.y), 6),
        round(float(value.z), 6),
    ]


def verify_mixed_base_dry_run(topology) -> dict[str, Any]:
    fbx_target, max_source = make_pair()
    fbx_target.name = "F2M_Mixed_FBX_Target"
    max_source.name = "F2M_Mixed_Max_Source"
    rt.convertToPoly(max_source)
    mapping = topology.build_topology_map(fbx_target, max_source)
    if not mapping.has_non_identity_mapping:
        raise AssertionError("Mixed 基础类型夹具没有形成非恒等面/角映射。")
    if str(rt.classOf(fbx_target.baseObject)) != "Editable_mesh":
        raise AssertionError("Mixed 夹具的 FBX 目标模型不是 Editable Mesh。")
    if str(rt.classOf(max_source.baseObject)) != "Editable_Poly":
        raise AssertionError("Mixed 夹具的 Max 源模型不是 Editable Poly。")
    if not bool(rt.F2M_MAP_seedChannel(fbx_target, 1)):
        raise AssertionError("Mixed 夹具无法建立 UV 通道。")

    options = topology.TransferOptions(
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
    context = topology.TransferContext(options, topology.TransferLog())
    record = topology.SceneRecord(
        handle=int(rt.getHandleByAnim(max_source)),
        original_name=str(max_source.name),
        temp_name=str(max_source.name),
        node=max_source,
    )
    report = topology.process_pair(fbx_target, record, context)
    combined = " | ".join(report.messages)
    if report.status == "已检查：可安全执行":
        raise AssertionError(
            "Mixed Editable Mesh/Poly + 非恒等映射被 dry-run 误报为可安全执行："
            + combined
        )
    if (
        "Editable Mesh" not in combined
        or "Editable Poly" not in combined
        or "面/角映射" not in combined
    ):
        raise AssertionError(
            "Mixed 基础类型 dry-run 虽阻断，但原因不够明确："
            f"{report.status}；{combined}"
        )
    return {
        "blocked": True,
        "status": report.status,
        "fbx_base": str(rt.classOf(fbx_target.baseObject)),
        "max_base": str(rt.classOf(max_source.baseObject)),
        "message": combined,
    }


def main() -> None:
    payload = {"ok": False}
    try:
        rt.resetMaxFile(rt.Name("noPrompt"))
        topology = load_topology()
        topology.ensure_runtime()
        install_helpers()
        fbx_target, max_source = make_pair()
        mapping = topology.build_topology_map(fbx_target, max_source)
        if mapping.fbx_face_for_max_face != (1, 0):
            raise AssertionError(mapping)
        if mapping.fbx_corner_for_max_corner != ((1, 2, 0), (1, 2, 0)):
            raise AssertionError(mapping)

        # Deformation is keyed by the stable vertex ID, independent from the
        # face-order/cyclic-corner mapping used by per-face/per-corner data.
        expected_positions = (
            rt.Point3(0, 0, 1),
            rt.Point3(12, 1, 3),
            rt.Point3(11, 14, -2),
            rt.Point3(-3, 9, 4),
        )
        for vertex_id, value in enumerate(expected_positions, start=1):
            rt.setVert(fbx_target, vertex_id, value)
        rt.update(fbx_target)
        shape_report = topology.ObjectReport(name="变形", status="测试")
        if not topology.copy_shape(
            fbx_target,
            max_source,
            shape_report,
            topology_map=mapping,
        ):
            raise AssertionError(" | ".join(shape_report.messages))
        deformation_positions = []
        for vertex_id, expected in enumerate(expected_positions, start=1):
            actual = rt.getVert(max_source, vertex_id)
            if float(rt.distance(actual, expected)) > 1.0e-5:
                raise AssertionError(
                    f"变形：顶点 {vertex_id} 为 {actual}，应为 {expected}"
                )
            deformation_positions.append(point_values(actual))

        # UV / RGB / Alpha all use the same mapped MapChannel writer.
        channel_results = {}
        for channel, label in ((1, "UV"), (0, "顶点色"), (-2, "Alpha")):
            if not bool(rt.F2M_MAP_seedChannel(fbx_target, channel)):
                raise AssertionError(f"{label}: 无法建立源通道。")
            report = topology.ObjectReport(name=label, status="测试")
            if channel == 1:
                ok = topology.copy_uv_channels(
                    fbx_target,
                    max_source,
                    [channel],
                    report,
                    topology_map=mapping,
                )
            else:
                ok = topology.copy_vertex_channel(
                    fbx_target,
                    max_source,
                    channel,
                    label,
                    report,
                    topology_map=mapping,
                )
            if not ok:
                raise AssertionError(f"{label}: {' | '.join(report.messages)}")
            actual = [map_face(max_source, channel, face) for face in (1, 2)]
            expected = [[5, 6, 4], [2, 3, 1]]
            if actual != expected:
                raise AssertionError(f"{label}: {actual}/{expected}")
            channel_results[label] = actual

        # Per-face smoothing masks follow the face map.
        base_type_evidence = {
            "fbx_base": str(rt.classOf(fbx_target.baseObject)),
            "max_base": str(rt.classOf(max_source.baseObject)),
            "fbx_faces": int(rt.getNumFaces(fbx_target)),
            "max_faces": int(rt.getNumFaces(max_source)),
            "can_set_fbx": bool(
                rt.F2M_Helper.canSetFaceSmoothingGroups(fbx_target, 2)
            ),
            "can_set_max": bool(
                rt.F2M_Helper.canSetFaceSmoothingGroups(max_source, 2)
            ),
        }
        if not bool(
            rt.F2M_Helper.setFaceSmoothingGroups(
                fbx_target,
                rt.Array(1, 2),
            )
        ):
            raise AssertionError(str(rt.F2M_Helper.lastMessage))
        context = topology.TransferContext(
            topology.TransferOptions(
                fbx_path="",
                transfer_smoothing_groups=False,
                show_ui=False,
            ),
            topology.TransferLog(),
        )
        smoothing_report = topology.ObjectReport(name="光滑组", status="测试")
        if not topology.copy_smoothing_groups(
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
            raise AssertionError(f"光滑组：{smoothing}/[2, 1]")

        # Material ID is also per-face and must follow the face map.
        fbx_target.material = rt.StandardMaterial(name="F2M_Map_Material")
        rt.setFaceMatID(fbx_target, 1, 7)
        rt.setFaceMatID(fbx_target, 2, 9)
        material_report = topology.ObjectReport(name="材质ID", status="测试")
        if not topology.copy_material_ids(
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
            raise AssertionError(f"材质ID：{material_ids}/[9, 7]")

        # A custom normal authored on FBX face1/corner1 (vertex1) maps to
        # Max face2/corner3 after both face reorder and cyclic corner rotation.
        seeded = rt.F2M_MAP_seedExplicit(fbx_target)
        if seeded is None or str(seeded) == "undefined":
            raise AssertionError("无法建立源显式法线。")
        seeded_values = list(seeded)
        expected_normal = seeded_values[2]
        face_map_array, corner_map_arrays = topology._maxscript_topology_arrays(
            mapping
        )
        source_snapshot = rt.F2M_Helper.snapshotEditNormalsData(
            fbx_target,
            seeded_values[0],
        )
        mapped_snapshot = rt.F2M_Helper.remapEditNormalsSnapshot(
            source_snapshot,
            faceMap=face_map_array,
            cornerMaps=corner_map_arrays,
        )
        normal_snapshot_evidence = {
            "source": str(source_snapshot),
            "mapped": str(mapped_snapshot),
        }
        normal_report = topology.ObjectReport(name="显式法线", status="测试")
        if not topology.copy_normals(
            fbx_target,
            max_source,
            normal_report,
            topology_map=mapping,
        ):
            raise AssertionError(" | ".join(normal_report.messages))
        normal_mod = rt.F2M_MAP_findNormals(max_source)
        if normal_mod is None or str(normal_mod) == "undefined":
            raise AssertionError("目标没有 F2M_顶点法线。")
        if not topology.activate_modifier(max_source, normal_mod):
            raise AssertionError("无法激活 Max 源模型的 F2M_顶点法线。")
        if not bool(
            normal_mod.GetFaceNormalSpecified(2, 3, node=max_source)
        ):
            raise AssertionError("显式法线没有映射到 Max 面2/角3。")
        normal_id = int(normal_mod.GetNormalID(2, 3, node=max_source))
        if not bool(normal_mod.GetNormalExplicit(normal_id, node=max_source)):
            raise AssertionError("映射后的法线不是 Explicit。")
        actual_normal = normal_mod.GetNormal(normal_id, node=max_source)
        normal_delta = float(rt.distance(actual_normal, expected_normal))
        if normal_delta > 1.0e-5:
            raise AssertionError(
                f"映射后的法线向量不同：{actual_normal}/{expected_normal}"
            )
        smoothing_after_normals = [
            int(value)
            for value in list(
                rt.F2M_Helper.getFaceSmoothingGroups(max_source)
            )
        ]
        if smoothing_after_normals != [2, 1]:
            raise AssertionError(
                "显式法线写入覆盖了映射后的光滑组："
                f"{smoothing_after_normals}/[2, 1]"
            )
        mixed_base_dry_run = verify_mixed_base_dry_run(topology)

        payload.update(
            {
                "ok": True,
                "face_map": list(mapping.fbx_face_for_max_face),
                "corner_maps": [
                    list(row)
                    for row in mapping.fbx_corner_for_max_corner
                ],
                "deformation_positions": deformation_positions,
                "map_channels": channel_results,
                "smoothing_groups": smoothing,
                "smoothing_groups_after_explicit_normals": (
                    smoothing_after_normals
                ),
                "material_ids": material_ids,
                "explicit_normal_destination": [2, 3],
                "explicit_normal_delta": normal_delta,
                "coexistence_verified": True,
                "mixed_base_dry_run": mixed_base_dry_run,
                "base_type_evidence": base_type_evidence,
                "normal_snapshot_evidence": normal_snapshot_evidence,
            }
        )
    except Exception:
        payload["error"] = traceback.format_exc()
    finally:
        with open(RESULT, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        try:
            rt.resetMaxFile(rt.Name("noPrompt"))
        except Exception:
            pass


if __name__ == "__main__":
    main()
