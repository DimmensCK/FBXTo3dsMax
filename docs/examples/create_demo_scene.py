# -*- coding: utf-8 -*-
"""Original canopy exercise: one receiving mesh and an authored numeric FBX.

Run create_demo_scene() explicitly inside an empty 3ds Max scene. This module
does not run the plug-in, reset a scene, change units or touch FBX preferences.
Generated FBX/receipts stay in a fresh local-user-data directory, outside Git.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import uuid


DEMO_SCHEMA = "f2m-original-canopy-1"
MESH_NAME = "F2M_Demo_Canopy"
COLUMNS = 13
ROWS = 7


def mesh_data(edited=False):
    """Return original centimetre coordinates, zero-based triangles and UV1."""
    vertices, uv = [], []
    for row in range(ROWS):
        v = row / (ROWS - 1)
        for column in range(COLUMNS):
            u = column / (COLUMNS - 1)
            x, y = (u - 0.5) * 100.0, (v - 0.5) * 60.0
            if edited:
                z = (18.0 * math.sin(math.pi * u) ** 1.25
                     * (0.6 + 0.4 * math.cos(2.0 * math.pi * v))
                     + 6.0 * math.sin(2.0 * math.pi * u) * math.sin(math.pi * v))
                y *= 0.85 + 0.25 * math.sin(math.pi * u)
            else:
                z = 4.0 * math.sin(math.pi * u) * math.sin(math.pi * v)
            vertices.append((x, y, z))
            scale = 1.0 if edited else 0.6
            uv.append((u * scale, v * scale))
    faces = []
    for row in range(ROWS - 1):
        for column in range(COLUMNS - 1):
            a = row * COLUMNS + column
            b, d = a + 1, a + COLUMNS
            c = d + 1
            faces.extend(((a, b, c), (a, c, d)))
    return {"vertices_cm": vertices, "faces": faces, "uv1": uv}


def _numbers(values):
    return ",".join(format(value, ".17g") for value in values)


def _array(name, values):
    return "        {}: *{} {{\n            a: {}\n        }}".format(
        name, len(values), _numbers(values))


def fbx_bytes():
    """Author numeric FBX 7.4, without external media, paths or private assets."""
    data = mesh_data(True)
    vertices, faces, uv = data["vertices_cm"], data["faces"], data["uv1"]
    indices, normals = [], []
    for a, b, c in faces:
        indices.extend((a, b, -c - 1))
        ab = [vertices[b][i] - vertices[a][i] for i in range(3)]
        ac = [vertices[c][i] - vertices[a][i] for i in range(3)]
        normal = (ab[1] * ac[2] - ab[2] * ac[1],
                  ab[2] * ac[0] - ab[0] * ac[2],
                  ab[0] * ac[1] - ab[1] * ac[0])
        length = math.sqrt(sum(value * value for value in normal))
        if length <= 0 or not math.isfinite(length):
            raise ValueError("Invalid original demo triangle")
        normals.extend([value / length for value in normal] * 3)
    geometry = "\n".join((
        _array("Vertices", [v for point in vertices for v in point]),
        _array("PolygonVertexIndex", indices),
        '''        LayerElementNormal: 0 {
            Version: 101
            Name: ""
            MappingInformationType: "ByPolygonVertex"
            ReferenceInformationType: "Direct"''',
        _array("Normals", normals), "        }",
        '''        LayerElementUV: 0 {
            Version: 101
            Name: "UV1"
            MappingInformationType: "ByPolygonVertex"
            ReferenceInformationType: "IndexToDirect"''',
        _array("UV", [value for point in uv for value in point]),
        _array("UVIndex", [index for face in faces for index in face]), "        }",
        '''        LayerElementSmoothing: 0 {
            Version: 102
            Name: ""
            MappingInformationType: "ByPolygon"
            ReferenceInformationType: "Direct"''',
        _array("Smoothing", [1] * len(faces)), "        }",
        '''        Layer: 0 {
            Version: 100
            LayerElement: {
                Type: "LayerElementNormal"
                TypedIndex: 0
            }
            LayerElement: {
                Type: "LayerElementUV"
                TypedIndex: 0
            }
            LayerElement: {
                Type: "LayerElementSmoothing"
                TypedIndex: 0
            }
        }''',
    ))
    template = '''; FBX 7.4.0 project file
; Original FBXTo3dsMax canopy exercise, authored from numeric data.
FBXHeaderExtension: {
    FBXHeaderVersion: 1003
    FBXVersion: 7400
    EncryptionType: 0
    Creator: "FBXTo3dsMax original canopy exercise"
}
GlobalSettings: {
    Version: 1000
    Properties70: {
        P: "UpAxis", "int", "Integer", "",2
        P: "UpAxisSign", "int", "Integer", "",1
        P: "FrontAxis", "int", "Integer", "",1
        P: "FrontAxisSign", "int", "Integer", "",-1
        P: "CoordAxis", "int", "Integer", "",0
        P: "CoordAxisSign", "int", "Integer", "",1
        P: "OriginalUpAxis", "int", "Integer", "",2
        P: "OriginalUpAxisSign", "int", "Integer", "",1
        P: "UnitScaleFactor", "double", "Number", "",1
        P: "OriginalUnitScaleFactor", "double", "Number", "",1
    }
}
Documents: {
    Count: 1
    Document: 1000, "Scene", "Scene" {
        Properties70: {
            P: "SourceObject", "object", "", ""
            P: "ActiveAnimStackName", "KString", "", "", ""
        }
        RootNode: 0
    }
}
References: {
}
Definitions: {
    Version: 100
    Count: 2
    ObjectType: "Geometry" {
        Count: 1
    }
    ObjectType: "Model" {
        Count: 1
    }
}
Objects: {
    Geometry: 1001, "Geometry::__NAME__", "Mesh" {
        GeometryVersion: 124
__GEOMETRY__
    }
    Model: 1002, "Model::__NAME__", "Mesh" {
        Version: 232
        Properties70: {
            P: "DefaultAttributeIndex", "int", "Integer", "",0
            P: "Lcl Translation", "Lcl Translation", "", "A",0,0,0
            P: "Lcl Rotation", "Lcl Rotation", "", "A",0,0,0
            P: "Lcl Scaling", "Lcl Scaling", "", "A",1,1,1
            P: "Visibility", "Visibility", "", "A",1
        }
        Shading: T
        Culling: "CullingOff"
    }
}
Connections: {
    C: "OO",1001,1002
    C: "OO",1002,0
}
Takes: {
    Current: ""
}
'''
    return template.replace("__NAME__", MESH_NAME).replace(
        "__GEOMETRY__", geometry).encode("ascii")


def _new_output_directory():
    local = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir())
    if not local.is_absolute():
        raise RuntimeError("Local demo output directory must be absolute")
    source_root = Path(__file__).resolve().parents[2]
    root = (local / "FBXTo3dsMax" / "Demos" / uuid.uuid4().hex).resolve()
    if root == source_root or source_root in root.parents:
        raise RuntimeError("Demo outputs must stay outside the source repository")
    root.mkdir(parents=True, exist_ok=False)
    return root


def create_demo_scene():
    """Prepare one original mesh; refuse a populated scene and never reset it."""
    from pymxs import runtime as rt

    if list(rt.objects):
        raise RuntimeError("Open a new empty scene before running the canopy exercise.")
    factor = float(rt.units.decodeValue("1cm"))
    if not math.isfinite(factor) or factor <= 0:
        raise RuntimeError("Cannot read the scene's centimetre conversion")
    data = mesh_data(False)
    root = _new_output_directory()
    payload = fbx_bytes()
    fbx_path = root / "edited_canopy.fbx"
    with fbx_path.open("xb") as stream:
        stream.write(payload)
    if fbx_path.read_bytes() != payload:
        raise RuntimeError("Demo FBX readback differs from authored data")
    recipe = {"schema": DEMO_SCHEMA, "name": MESH_NAME,
              "vertices": len(data["vertices_cm"]), "triangles": len(data["faces"]),
              "units": "cm", "native_units_per_cm": factor,
              "fbx_sha256": hashlib.sha256(payload).hexdigest(),
              "settings": {"mode": "topology_only", "transfer_shape": True,
                           "transfer_uv": True, "uv_channels": [1]},
              "base": data, "edited": mesh_data(True)}
    with (root / "recipe.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(recipe, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    node = None
    mesh = None
    material = None
    created_handle = None
    try:
        node = rt.mesh(
            vertices=[rt.point3(*(value * factor for value in point))
                      for point in data["vertices_cm"]],
            faces=[rt.point3(*(index + 1 for index in face)) for face in data["faces"]],
            tverts=[rt.point3(u, v, 0) for u, v in data["uv1"]])
        created_handle = int(rt.getHandleByAnim(node))
        node.name = MESH_NAME
        # Build the missing TV faces and edit the tracked Editable Mesh node
        # directly. Replacing it from an extracted MeshValue can discard UVs.
        # The final node snapshot below verifies persistence before publication.
        rt.buildTVFaces(node)
        for number, (u, v) in enumerate(data["uv1"], 1):
            rt.setTVert(node, number, rt.point3(u, v, 0))
        for number, face in enumerate(data["faces"], 1):
            rt.setTVFace(node, number, rt.point3(*(index + 1 for index in face)))
            rt.setFaceSmoothGroup(node, number, 1)
        rt.update(node)
        node.wirecolor = rt.color(48, 204, 190)
        material = rt.StandardMaterial(name="F2M_Demo_Teal", diffuse=rt.color(48, 204, 190))
        material.twoSided = True
        node.material = material
        rt.select(node)
        selected = [int(rt.getHandleByAnim(item)) for item in list(rt.selection)]
        if selected != [created_handle]:
            raise RuntimeError("Demo receiving mesh selection did not read back")
        if int(rt.getNumVerts(node)) != len(data["vertices_cm"]):
            raise RuntimeError("Demo receiving mesh vertex count differs")
        if int(rt.getNumFaces(node)) != len(data["faces"]):
            raise RuntimeError("Demo receiving mesh face count differs")
        mesh = rt.snapshotAsMesh(node)
        native_face = None
        native_uv = None
        try:
            uv_count = int(rt.getNumTVerts(mesh))
            if uv_count != len(data["uv1"]) or int(rt.getNumFaces(mesh)) != len(data["faces"]):
                raise RuntimeError("Demo receiving mesh UV1 counts differ")
            largest_uv_error = 0.0
            for number, face in enumerate(data["faces"], 1):
                native_face = rt.getTVFace(mesh, number)
                indices = (int(native_face.x), int(native_face.y), int(native_face.z))
                for actual_index, wanted_index in zip(indices, face):
                    if actual_index < 1 or actual_index > uv_count:
                        raise RuntimeError("Demo receiving mesh UV1 corner index is out of range")
                    native_uv = rt.getTVert(mesh, actual_index)
                    for actual, wanted in zip((float(native_uv.x), float(native_uv.y)), data["uv1"][wanted_index]):
                        if not math.isfinite(actual):
                            raise RuntimeError("Demo receiving mesh UV1 is non-finite")
                        largest_uv_error = max(largest_uv_error, abs(actual - wanted))
            if largest_uv_error > 0.00001:
                raise RuntimeError("Demo receiving mesh UV1 corner readback differs: " + str(largest_uv_error))
        finally:
            native_uv = None
            native_face = None
            rt.free(mesh)
            mesh = None
        receipt = {"schema": DEMO_SCHEMA, "state": "SCENE_PREPARED_NOT_TRANSFERRED",
                   "node_handle": created_handle, "fbx": str(fbx_path),
                   "recipe": str(root / "recipe.json")}
        print("FBXTo3dsMax original canopy ready. Select Shape + UV 1 in Mode 1.")
        print("FBX: " + str(fbx_path))
        with (root / ".prepared.json.tmp").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(receipt, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Final commit: no fallible output or cleanup after atomic publication.
        os.replace(str(root / ".prepared.json.tmp"), str(root / "prepared.json"))
        return receipt
    except Exception as error:
        # The constructor's returned reference is owned even if obtaining its
        # handle fails. Never widen this fallback to an untracked scene scan.
        created_node = node
        node = None
        mesh = None
        material = None
        cleanup_error = None
        if created_node is not None or created_handle is not None:
            try:
                owned = (rt.getAnimByHandle(created_handle)
                         if created_handle is not None else created_node)
                created_node = None
                if owned is not None and bool(rt.isValidNode(owned)):
                    rt.delete(owned)
                if owned is not None and bool(rt.isValidNode(owned)):
                    raise RuntimeError("Created demo mesh remains after cleanup")
                owned = None
                if created_handle is not None:
                    remaining = rt.getAnimByHandle(created_handle)
                    if remaining is not None and bool(rt.isValidNode(remaining)):
                        raise RuntimeError("Created demo mesh handle remains after cleanup")
                    remaining = None
            except Exception as cleanup:
                cleanup_error = str(cleanup)
        receipt_error = None
        try:
            with (root / "failed.json").open("x", encoding="utf-8", newline="\n") as stream:
                json.dump({"schema": DEMO_SCHEMA, "error": str(error),
                           "cleanup_error": cleanup_error}, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        except Exception as receipt_failure:
            receipt_error = str(receipt_failure)
        recovery_errors = []
        if cleanup_error:
            recovery_errors.append("demo cleanup failed: " + cleanup_error)
        if receipt_error:
            recovery_errors.append("failure receipt could not be written: " + receipt_error)
        if recovery_errors:
            raise RuntimeError(str(error) + "; " + "; ".join(recovery_errors)) from error
        raise


if __name__ == "__main__":
    create_demo_scene()
