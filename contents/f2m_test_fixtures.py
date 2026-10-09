# -*- coding: utf-8 -*-
"""Original procedural FBX test data; no bundled character or company assets.

Python 3.9, standard library only. Generated files live in the current user's
LOCALAPPDATA (or the OS temporary directory), never beside the installed code.
Skin fixtures need real Max APIs and are generated separately by the self-check.
"""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import tempfile
from typing import Dict, Optional


TOOL_VERSION = "1.4.26"
MESH_NAME = "F2M_ProceduralMesh"
FACES = ((0, 1, 2), (0, 2, 3))
FACE_COUNT = 2
CORNER_COUNT = 6
NATIVE_MASKS = (1, 1)


def fixture_bytes(native_smoothing: bool = False) -> bytes:
    """One 10 cm square, two triangles, UV1 and one authored tilted normal.

    The two shared vertices have equal corner directions, so their common edge
    is soft. The unique vertex 1 has a tilted normal which no smoothing group
    can reproduce on this planar mesh; this exercises the explicit residual.
    """
    tilt_x = 0.2 / math.sqrt(1.04)
    tilt_z = 1.0 / math.sqrt(1.04)
    normals = "0,0,1,{:.17g},0,{:.17g},0,0,1,0,0,1,0,0,1,0,0,1".format(
        tilt_x, tilt_z
    )
    smoothing = ""
    smoothing_reference = ""
    if native_smoothing:
        smoothing = '''
        LayerElementSmoothing: 0 {
            Version: 102
            Name: ""
            MappingInformationType: "ByPolygon"
            ReferenceInformationType: "Direct"
            Smoothing: *2 {
                a: 1,1
            }
        }
'''
        smoothing_reference = '''
            LayerElement: {
                Type: "LayerElementSmoothing"
                TypedIndex: 0
            }
'''
    # FBX text is authored here entirely from elementary numeric data. In
    # particular it contains no external paths, textures, or private metadata.
    payload = '''; FBX 7.4.0 project file
; Original FBXTo3dsMax procedural regression fixture.
FBXHeaderExtension: {
    FBXHeaderVersion: 1003
    FBXVersion: 7400
    EncryptionType: 0
    Creator: "FBXTo3dsMax procedural fixture generator"
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
    Geometry: 1001, "Geometry::F2M_ProceduralMesh", "Mesh" {
        GeometryVersion: 124
        Vertices: *12 {
            a: 0,0,0,10,0,0,10,10,0,0,10,0
        }
        PolygonVertexIndex: *6 {
            a: 0,1,-3,0,2,-4
        }
        LayerElementNormal: 0 {
            Version: 101
            Name: ""
            MappingInformationType: "ByPolygonVertex"
            ReferenceInformationType: "Direct"
            Normals: *18 {
                a: __NORMALS__
            }
        }
        LayerElementUV: 0 {
            Version: 101
            Name: "UV1"
            MappingInformationType: "ByPolygonVertex"
            ReferenceInformationType: "IndexToDirect"
            UV: *8 {
                a: 0,0,1,0,1,1,0,1
            }
            UVIndex: *6 {
                a: 0,1,2,0,2,3
            }
        }
__SMOOTHING__
        Layer: 0 {
            Version: 100
            LayerElement: {
                Type: "LayerElementNormal"
                TypedIndex: 0
            }
            LayerElement: {
                Type: "LayerElementUV"
                TypedIndex: 0
            }
__SMOOTHING_REFERENCE__
        }
    }
    Model: 1002, "Model::F2M_ProceduralMesh", "Mesh" {
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
    return payload.replace("__NORMALS__", normals).replace(
        "__SMOOTHING__", smoothing
    ).replace("__SMOOTHING_REFERENCE__", smoothing_reference).encode("ascii")


def _write_generated(path: Path, payload: bytes) -> str:
    if path.exists():
        if not path.is_file() or path.is_symlink() or path.read_bytes() != payload:
            raise RuntimeError("Generated fixture path contains unexpected content: " + str(path))
        return str(path)
    # Create-new avoids overwriting an existing object. A concurrent generator
    # can win the race only when its complete read-back equals our own bytes.
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        if path.read_bytes() != payload:
            raise RuntimeError("Concurrent fixture generator produced different bytes")
    if path.read_bytes() != payload:
        raise RuntimeError("Generated fixture read-back differs from authored content")
    return str(path)


def get_fixture_paths() -> Dict[str, Optional[str]]:
    topology = fixture_bytes(False)
    native = fixture_bytes(True)
    identity = hashlib.sha256(topology + native).hexdigest()[:16]
    local = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    destination = (Path(local) / "FBXTo3dsMax" / "TestFixtures"
                   / ("source-v" + TOOL_VERSION + "-" + identity)).resolve()
    source_root = Path(__file__).resolve().parent
    if source_root == destination or source_root in destination.parents:
        raise RuntimeError("Generated fixtures must stay outside source/installed code")
    destination.mkdir(parents=True, exist_ok=True)
    return {
        "topology": _write_generated(destination / "topology_source.fbx", topology),
        "native_smoothing": _write_generated(destination / "native_smoothing_source.fbx", native),
        "skin": None,  # Real-Max self-check authors this with the current host APIs.
    }


__all__ = [
    "TOOL_VERSION", "MESH_NAME", "FACES", "FACE_COUNT", "CORNER_COUNT",
    "NATIVE_MASKS", "fixture_bytes", "get_fixture_paths",
]
