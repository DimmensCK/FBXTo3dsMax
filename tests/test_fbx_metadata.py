# -*- coding: utf-8 -*-
"""Regression tests for the read-only FBX smoothing metadata reader."""

from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from typing import Iterable, Optional, Sequence, Tuple

# Resolve runtime modules from the source distribution without a global PYTHONPATH.
import sys as _f2m_test_sys
from pathlib import Path as _F2MTestPath
_f2m_test_root = _F2MTestPath(__file__).resolve().parents[1]
_f2m_test_sys.path.insert(0, str(_f2m_test_root / "contents" if (_f2m_test_root / "contents").is_dir() else _f2m_test_root))

from f2m_test_fixtures import (
    CORNER_COUNT, FACE_COUNT, FACES, MESH_NAME, NATIVE_MASKS, get_fixture_paths,
)

from f2m_fbx_metadata import (
    TOOL_VERSION,
    FBXMetadataError,
    FbxAmbiguityError,
    FbxFormatError,
    FbxMetadataIOError,
    RESOLVER_SCHEMA,
    RESOLVER_SCHEMA_VERSION,
    RESOLVER_TOPOLOGY_ENCODING,
    build_strict_resolver_payload,
    inspect_fbx_smoothing,
    inspect_smoothing_layers,
    read_mesh_smoothing_and_normals,
    read_mesh_smoothing_data,
    read_native_smoothing_by_model,
    write_strict_resolver_json,
)


ROOT = Path(__file__).resolve().parents[1]
GENERATED_FIXTURES = get_fixture_paths()
TOPOLOGY_FIXTURE = Path(GENERATED_FIXTURES["topology"])
NATIVE_SMOOTHING_FIXTURE = Path(GENERATED_FIXTURES["native_smoothing"])
BINARY_MAGIC = b"Kaydara FBX Binary  \x00\x1a\x00"


def _p_scalar(type_code: bytes, fmt: str, value: object) -> bytes:
    return type_code + struct.pack(fmt, value)


def _p_string(value: bytes) -> bytes:
    return b"S" + struct.pack("<I", len(value)) + value


def _p_raw(value: bytes) -> bytes:
    return b"R" + struct.pack("<I", len(value)) + value


def _p_array(
    type_code: bytes,
    fmt: str,
    values: Sequence[object],
    compressed: bool = False,
) -> bytes:
    raw = struct.pack("<{}{}".format(len(values), fmt), *values)
    payload = zlib.compress(raw) if compressed else raw
    return (
        type_code
        + struct.pack("<III", len(values), 1 if compressed else 0, len(payload))
        + payload
    )


Node = Tuple[bytes, Sequence[bytes], Sequence["Node"]]


def _binary_node(node: Node, start: int, wide: bool) -> bytes:
    name, properties, children = node
    property_bytes = b"".join(properties)
    header_format = "<QQQB" if wide else "<IIIB"
    header_size = struct.calcsize(header_format)
    children_start = start + header_size + len(name) + len(property_bytes)
    child_blobs = []
    next_offset = children_start
    for child in children:
        blob = _binary_node(child, next_offset, wide)
        child_blobs.append(blob)
        next_offset += len(blob)
    if children:
        null_record = b"\x00" * (25 if wide else 13)
        child_blobs.append(null_record)
        next_offset += len(null_record)
    end_offset = next_offset
    header = struct.pack(
        header_format,
        end_offset,
        len(properties),
        len(property_bytes),
        len(name),
    )
    return header + name + property_bytes + b"".join(child_blobs)


def _binary_document(version: int, nodes: Iterable[Node]) -> bytes:
    wide = version >= 7500
    prefix = BINARY_MAGIC + struct.pack("<I", version)
    blobs = []
    next_offset = len(prefix)
    for node in nodes:
        blob = _binary_node(node, next_offset, wide)
        blobs.append(blob)
        next_offset += len(blob)
    blobs.append(b"\x00" * (25 if wide else 13))
    return prefix + b"".join(blobs)


def _binary_metadata_document(version: int) -> bytes:
    # The Irrelevant node deliberately exercises every scalar property and all
    # standard FBX array encodings.  The metadata reader must skip them without
    # losing the recursive endOffset boundary.
    irrelevant: Node = (
        b"Irrelevant",
        (
            _p_scalar(b"Y", "<h", -2),
            _p_scalar(b"C", "<B", 1),
            _p_scalar(b"I", "<i", -3),
            _p_scalar(b"F", "<f", 1.5),
            _p_scalar(b"D", "<d", 2.5),
            _p_scalar(b"L", "<q", 999),
            _p_string(b"skip me"),
            _p_raw(b"\x00\x01\x02"),
            _p_array(b"f", "f", (1.0, 2.0)),
            _p_array(b"d", "d", (1.0,), compressed=True),
            _p_array(b"l", "q", (1, 2)),
            _p_array(b"i", "i", (1, 2, 3)),
            _p_array(b"b", "B", (0, 1)),
            _p_array(b"c", "B", (4, 5)),
        ),
        (),
    )
    geometry_true: Node = (
        b"Geometry",
        (
            _p_scalar(b"L", "<q", 1001),
            _p_string(b"Native\x00\x01Geometry"),
            _p_string(b"Mesh"),
        ),
        ((b"LayerElementSmoothing", (_p_scalar(b"I", "<i", 0),), ()),),
    )
    geometry_false: Node = (
        b"Geometry",
        (
            _p_scalar(b"L", "<q", 1002),
            _p_string(b"Inferred\x00\x01Geometry"),
            _p_string(b"Mesh"),
        ),
        (),
    )
    model_true: Node = (
        b"Model",
        (
            _p_scalar(b"L", "<q", 2001),
            _p_string(b"Native\x00\x01Model"),
            _p_string(b"Mesh"),
        ),
        (),
    )
    model_false: Node = (
        b"Model",
        (
            _p_scalar(b"L", "<q", 2002),
            _p_string(b"Inferred\x00\x01Model"),
            _p_string(b"Mesh"),
        ),
        (),
    )
    objects: Node = (
        b"Objects",
        (),
        (irrelevant, geometry_true, geometry_false, model_true, model_false),
    )
    connections: Node = (
        b"Connections",
        (),
        (
            (
                b"C",
                (
                    _p_string(b"OO"),
                    _p_scalar(b"L", "<q", 1001),
                    _p_scalar(b"L", "<q", 2001),
                ),
                (),
            ),
            (
                b"C",
                (
                    _p_string(b"OO"),
                    _p_scalar(b"L", "<q", 1002),
                    _p_scalar(b"L", "<q", 2002),
                ),
                (),
            ),
        ),
    )
    return _binary_document(version, (objects, connections))


def _autodesk_unnamed_geometry_document(version: int) -> bytes:
    geometry: Node = (
        b"Geometry",
        (
            _p_scalar(b"L", "<q", 1001),
            _p_string(b"\x00\x01Geometry"),
            _p_string(b"Mesh"),
        ),
        ((b"LayerElementSmoothing", (_p_scalar(b"I", "<i", 0),), ()),),
    )
    model: Node = (
        b"Model",
        (
            _p_scalar(b"L", "<q", 2001),
            _p_string(b"VisibleMesh\x00\x01Model"),
            _p_string(b"Mesh"),
        ),
        # Max-exported binary FBX files use ASCII T/F for some C properties.
        ((b"Show", (_p_scalar(b"C", "<B", ord("T")),), ()),),
    )
    objects: Node = (b"Objects", (), (geometry, model))
    connections: Node = (
        b"Connections",
        (),
        (
            (
                b"C",
                (
                    _p_string(b"OO"),
                    _p_scalar(b"L", "<q", 1001),
                    _p_scalar(b"L", "<q", 2001),
                ),
                (),
            ),
        ),
    )
    return _binary_document(version, (objects, connections))


STRICT_FACES = ((0, 1, 2), (0, 2, 3), (0, 3, 4))
STRICT_POLYGON_VERTEX_INDEX = (0, 1, -3, 0, 2, -4, 0, 3, -5)
STRICT_MASKS = (0, 1, -2147483648)
STRICT_NORMAL_VECTORS = (
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
    (-1.0, 0.0, 0.0),
    (0.0, -1.0, 0.0),
    (0.0, 0.0, -1.0),
    (0.5, 0.5, 0.0),
    (0.0, 0.5, 0.5),
    (0.5, 0.0, 0.5),
)


def _flatten_vectors(
    vectors: Sequence[Sequence[float]],
) -> Tuple[float, ...]:
    return tuple(component for vector in vectors for component in vector)


def _strict_binary_document(
    version: int,
    *,
    compressed: bool = False,
    smoothing_mapping: bytes = b"ByPolygon",
    smoothing_reference: bytes = b"Direct",
    smoothing_masks: Sequence[int] = STRICT_MASKS,
    include_smoothing: bool = True,
    include_smoothing_reference: bool = True,
    normal_reference: bytes = b"Direct",
    normal_vectors: Sequence[Sequence[float]] = STRICT_NORMAL_VECTORS,
    normal_indices: Optional[Sequence[int]] = None,
    polygon_vertex_index: Sequence[int] = STRICT_POLYGON_VERTEX_INDEX,
    malformed_normal_reference: bool = False,
    corrupt_vertices_zlib: bool = False,
) -> bytes:
    vertices = (
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        1.0,
        1.0,
        0.0,
        0.0,
        1.0,
        0.0,
        -1.0,
        0.0,
        0.0,
    )
    vertices_property = _p_array(b"d", "d", vertices, compressed)
    if corrupt_vertices_zlib:
        if not compressed:
            raise ValueError("corrupt_vertices_zlib requires compression")
        corrupted = bytearray(vertices_property)
        corrupted[-1] ^= 0xFF
        vertices_property = bytes(corrupted)
    normal_children = [
        (b"MappingInformationType", (_p_string(b"ByPolygonVertex"),), ()),
        (b"ReferenceInformationType", (_p_string(normal_reference),), ()),
        (
            b"Normals",
            (_p_array(b"d", "d", _flatten_vectors(normal_vectors), compressed),),
            (),
        ),
    ]
    if normal_indices is not None:
        normal_children.append(
            (
                b"NormalsIndex",
                (_p_array(b"i", "i", normal_indices, compressed),),
                (),
            )
        )
    normal_layer: Node = (
        b"LayerElementNormal",
        (_p_scalar(b"I", "<i", 0),),
        tuple(normal_children),
    )
    geometry_children = [
        (b"Vertices", (vertices_property,), ()),
        (
            b"PolygonVertexIndex",
            (_p_array(b"i", "i", polygon_vertex_index, compressed),),
            (),
        ),
        normal_layer,
    ]
    if include_smoothing:
        geometry_children.append(
            (
                b"LayerElementSmoothing",
                (_p_scalar(b"I", "<i", 0),),
                (
                    (
                        b"MappingInformationType",
                        (_p_string(smoothing_mapping),),
                        (),
                    ),
                    (
                        b"ReferenceInformationType",
                        (_p_string(smoothing_reference),),
                        (),
                    ),
                    (
                        b"Smoothing",
                        (_p_array(b"i", "i", smoothing_masks, compressed),),
                        (),
                    ),
                ),
            )
        )
    if malformed_normal_reference:
        normal_reference_children = (
            (b"Type", (_p_string(b"LayerElementNormal"),), ()),
            (b"Type", (_p_string(b"LayerElementNormal"),), ()),
            (b"TypedIndex", (_p_string(b"bogus"),), ()),
        )
    else:
        normal_reference_children = (
            (b"Type", (_p_string(b"LayerElementNormal"),), ()),
            (b"TypedIndex", (_p_scalar(b"I", "<i", 0),), ()),
        )
    layer_references = [
        (b"LayerElement", (), normal_reference_children)
    ]
    if include_smoothing_reference:
        layer_references.append(
            (
                b"LayerElement",
                (),
                (
                    (b"Type", (_p_string(b"LayerElementSmoothing"),), ()),
                    (b"TypedIndex", (_p_scalar(b"I", "<i", 0),), ()),
                ),
            )
        )
    geometry_children.append(
        (b"Layer", (_p_scalar(b"I", "<i", 0),), tuple(layer_references))
    )
    geometry: Node = (
        b"Geometry",
        (
            _p_scalar(b"L", "<q", 1001),
            _p_string(b"Strict\x00\x01Geometry"),
            _p_string(b"Mesh"),
        ),
        tuple(geometry_children),
    )
    model: Node = (
        b"Model",
        (
            _p_scalar(b"L", "<q", 2001),
            _p_string(b"StrictMesh\x00\x01Model"),
            _p_string(b"Mesh"),
        ),
        (),
    )
    objects: Node = (b"Objects", (), (geometry, model))
    connections: Node = (
        b"Connections",
        (),
        (
            (
                b"C",
                (
                    _p_string(b"OO"),
                    _p_scalar(b"L", "<q", 1001),
                    _p_scalar(b"L", "<q", 2001),
                ),
                (),
            ),
        ),
    )
    return _binary_document(version, (objects, connections))


ASCII_MINIMAL = """\
; FBX 7.4.0 project file
Objects: {
    Geometry: 101, "Geometry::NativeMesh", "Mesh" {
        Vertices: *6 {
            a: 0, 1, 2,
               3, 4, 5
        }
        LayerElementSmoothing: 0 {
        }
    }
    Geometry: 102, "Geometry::NormalsOnly", "Mesh" {
    }
    Model: 201, "Model::ShownNative", "Mesh" {
    }
    Model: 202, "Model::ShownInferred", "Mesh" {
    }
}
Connections: {
    C: "OO", 101, 201
    C: "OO", 102, 202
}
"""


STRICT_ASCII = """\
; FBX 7.4.0 project file
Objects: {
    Geometry: 1001, "Geometry::Strict", "Mesh" {
        Vertices: *15 {
            a: 0, 0, 0, 1, 0,
               0, 1, 1, 0, 0,
               1, 0, -1, 0, 0,
        }
        PolygonVertexIndex: *9 {
            a: 0, 1, -3,
               0, 2, -4,
               0, 3, -5
        }
        LayerElementNormal: 0 {
            MappingInformationType: "ByPolygonVertex"
            ReferenceInformationType: "Direct"
            Normals: *27 {
                a: 1, 0, 0, 0, 1, 0, 0, 0, 1,
                   -1, 0, 0, 0, -1, 0, 0, 0, -1,
                   0.5, 0.5, 0, 0, 0.5, 0.5, 0.5, 0, 0.5
            }
        }
        LayerElementSmoothing: 0 {
            MappingInformationType: "ByPolygon"
            ReferenceInformationType: "Direct"
            Smoothing: *3 {
                a: 0,
                   1,
                   -2147483648,
            }
        }
        Layer: 0 {
            LayerElement: {
                Type: "LayerElementNormal"
                TypedIndex: 0
            }
            LayerElement: {
                Type: "LayerElementSmoothing"
                TypedIndex: 0
            }
        }
    }
    Model: 2001, "Model::StrictMesh", "Mesh" {
    }
}
Connections: {
    C: "OO", 1001, 2001
}
"""


class FbxMetadataTests(unittest.TestCase):
    def _read_temp(self, payload: bytes) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.fbx"
            path.write_bytes(payload)
            return read_native_smoothing_by_model(path)

    def _read_strict_temp(self, payload: bytes, normals: bool = False) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "strict.fbx"
            path.write_bytes(payload)
            reader = (
                read_mesh_smoothing_and_normals
                if normals
                else read_mesh_smoothing_data
            )
            return reader(path)

    def test_version_matches_release(self) -> None:
        self.assertEqual(TOOL_VERSION, "1.4.24")

    def test_existing_topology_fixture_has_no_native_smoothing(self) -> None:
        self.assertEqual(
            inspect_smoothing_layers(str(TOPOLOGY_FIXTURE)),
            {MESH_NAME: False},
        )

    def test_native_smoothing_fixture_has_layer(self) -> None:
        self.assertEqual(
            inspect_smoothing_layers(str(NATIVE_SMOOTHING_FIXTURE)),
            {MESH_NAME: True},
        )

    def test_existing_fixtures_expose_exact_faces_and_masks(self) -> None:
        topology = read_mesh_smoothing_data(TOPOLOGY_FIXTURE)
        topology_mesh = topology[MESH_NAME]
        self.assertEqual(topology_mesh.faces, FACES)
        self.assertEqual(len(topology_mesh.faces), FACE_COUNT)
        self.assertEqual(sum(map(len, topology_mesh.faces)), CORNER_COUNT)
        self.assertIsNone(topology_mesh.masks)

        native = read_mesh_smoothing_data(NATIVE_SMOOTHING_FIXTURE)
        native_mesh = native[MESH_NAME]
        self.assertEqual(native_mesh.faces, FACES)
        self.assertEqual(len(native_mesh.faces), FACE_COUNT)
        self.assertEqual(sum(map(len, native_mesh.faces)), CORNER_COUNT)
        self.assertEqual(native_mesh.masks, NATIVE_MASKS)
        self.assertEqual(native_mesh.layer_index, 0)
        self.assertEqual(native_mesh.smoothing_typed_index, 0)
        self.assertEqual(native_mesh.mapping_information_type, "ByPolygon")
        self.assertEqual(native_mesh.reference_information_type, "Direct")

    def test_strict_binary_raw_and_zlib_7400_and_7500(self) -> None:
        for version in (7400, 7500):
            for compressed in (False, True):
                with self.subTest(version=version, compressed=compressed):
                    item = self._read_strict_temp(
                        _strict_binary_document(
                            version, compressed=compressed
                        )
                    )["StrictMesh"]
                    self.assertEqual(item.faces, STRICT_FACES)
                    self.assertEqual(item.masks, STRICT_MASKS)
                    self.assertEqual(
                        item.unsigned_masks, (0, 1, 0x80000000)
                    )
                    self.assertEqual(item.layer_index, 0)
                    self.assertEqual(item.smoothing_typed_index, 0)

    def test_strict_binary_direct_corner_normals(self) -> None:
        item = self._read_strict_temp(
            _strict_binary_document(7400),
            normals=True,
        )["StrictMesh"]
        self.assertEqual(
            item.corner_normals,
            (
                STRICT_NORMAL_VECTORS[0:3],
                STRICT_NORMAL_VECTORS[3:6],
                STRICT_NORMAL_VECTORS[6:9],
            ),
        )
        self.assertEqual(item.normal_layer_index, 0)
        self.assertEqual(item.normal_typed_index, 0)
        self.assertEqual(
            item.normal_mapping_information_type, "ByPolygonVertex"
        )
        self.assertEqual(item.normal_reference_information_type, "Direct")

    def test_strict_binary_index_to_direct_corner_normals(self) -> None:
        pool = STRICT_NORMAL_VECTORS[:5]
        indices = (0, 1, 2, 0, 2, 3, 0, 3, 4)
        item = self._read_strict_temp(
            _strict_binary_document(
                7400,
                compressed=True,
                normal_reference=b"IndexToDirect",
                normal_vectors=pool,
                normal_indices=indices,
            ),
            normals=True,
        )["StrictMesh"]
        expected = tuple(pool[index] for index in indices)
        self.assertEqual(
            item.corner_normals,
            (expected[0:3], expected[3:6], expected[6:9]),
        )
        self.assertEqual(
            item.normal_reference_information_type, "IndexToDirect"
        )

    def test_strict_ascii_multiline_arrays(self) -> None:
        item = self._read_strict_temp(
            STRICT_ASCII.encode("utf-8"),
            normals=True,
        )["StrictMesh"]
        self.assertEqual(item.faces, STRICT_FACES)
        self.assertEqual(item.masks, STRICT_MASKS)
        self.assertEqual(item.unsigned_masks, (0, 1, 0x80000000))
        self.assertEqual(
            item.corner_normals,
            (
                STRICT_NORMAL_VECTORS[0:3],
                STRICT_NORMAL_VECTORS[3:6],
                STRICT_NORMAL_VECTORS[6:9],
            ),
        )

    def test_strict_rejects_non_polygon_direct_smoothing(self) -> None:
        for mapping, reference in (
            (b"ByEdge", b"Direct"),
            (b"ByPolygon", b"IndexToDirect"),
        ):
            with self.subTest(mapping=mapping, reference=reference):
                with self.assertRaises(FbxFormatError):
                    self._read_strict_temp(
                        _strict_binary_document(
                            7400,
                            smoothing_mapping=mapping,
                            smoothing_reference=reference,
                        )
                    )

    def test_strict_rejects_bad_counts_and_layer_references(self) -> None:
        bad_payloads = (
            _strict_binary_document(7400, smoothing_masks=(0, 1)),
            _strict_binary_document(
                7400,
                polygon_vertex_index=(0, 1, -3, 0, 2, -4, 0, 3),
            ),
            _strict_binary_document(
                7400,
                include_smoothing_reference=False,
            ),
        )
        for payload in bad_payloads:
            with self.subTest(payload_size=len(payload)):
                with self.assertRaises(FBXMetadataError):
                    self._read_strict_temp(payload)

    def test_smoothing_only_ignores_malformed_normal_references(self) -> None:
        binary_payload = _strict_binary_document(
            7400,
            malformed_normal_reference=True,
        )
        binary_item = self._read_strict_temp(binary_payload)["StrictMesh"]
        self.assertEqual(binary_item.masks, STRICT_MASKS)
        with self.assertRaises(FBXMetadataError):
            self._read_strict_temp(binary_payload, normals=True)

        duplicate_type = STRICT_ASCII.replace(
            '                Type: "LayerElementNormal"\n'
            "                TypedIndex: 0",
            '                Type: "LayerElementNormal"\n'
            '                Type: "LayerElementNormal"\n'
            "                TypedIndex: bogus",
        )
        ascii_item = self._read_strict_temp(
            duplicate_type.encode("utf-8")
        )["StrictMesh"]
        self.assertEqual(ascii_item.masks, STRICT_MASKS)
        with self.assertRaises(FBXMetadataError):
            self._read_strict_temp(
                duplicate_type.encode("utf-8"),
                normals=True,
            )

    def test_smoothing_only_ignores_bad_normal_vector_count(self) -> None:
        payload = _strict_binary_document(
            7400,
            normal_vectors=STRICT_NORMAL_VECTORS[:-1],
        )
        self.assertEqual(
            self._read_strict_temp(payload)["StrictMesh"].masks,
            STRICT_MASKS,
        )
        with self.assertRaises(FbxFormatError):
            self._read_strict_temp(payload, normals=True)

    def test_strict_normals_reject_missing_and_out_of_range_indices(self) -> None:
        payloads = (
            _strict_binary_document(
                7400,
                normal_reference=b"IndexToDirect",
                normal_vectors=STRICT_NORMAL_VECTORS[:5],
            ),
            _strict_binary_document(
                7400,
                normal_reference=b"IndexToDirect",
                normal_vectors=STRICT_NORMAL_VECTORS[:5],
                normal_indices=(0, 1, 2, 0, 2, 3, 0, 3, 99),
            ),
            _strict_binary_document(
                7400,
                normal_reference=b"Direct",
                normal_indices=tuple(range(9)),
            ),
        )
        for payload in payloads:
            with self.subTest(payload_size=len(payload)):
                with self.assertRaises(FBXMetadataError):
                    self._read_strict_temp(payload, normals=True)

    def test_binary_vertices_count_only_validates_zlib_stream(self) -> None:
        with self.assertRaises(FbxFormatError):
            self._read_strict_temp(
                _strict_binary_document(
                    7400,
                    compressed=True,
                    corrupt_vertices_zlib=True,
                )
            )

    def test_strict_ascii_accepts_single_line_target_array(self) -> None:
        single_line = STRICT_ASCII.replace(
            "                a: 0,\n"
            "                   1,\n"
            "                   -2147483648,",
            "                a: 0, 1, -2147483648,",
        )
        item = self._read_strict_temp(
            single_line.encode("utf-8")
        )["StrictMesh"]
        self.assertEqual(item.masks, STRICT_MASKS)

    def test_resolver_payload_is_compact_hashed_and_reproducible(self) -> None:
        native = build_strict_resolver_payload(
            NATIVE_SMOOTHING_FIXTURE
        )
        computed = build_strict_resolver_payload(TOPOLOGY_FIXTURE)
        self.assertEqual(native["schema"], RESOLVER_SCHEMA)
        self.assertEqual(
            native["schema_version"], RESOLVER_SCHEMA_VERSION
        )
        self.assertEqual(
            native["topology_encoding"], RESOLVER_TOPOLOGY_ENCODING
        )
        self.assertEqual(native["mesh_count"], 1)
        native_mesh = native["meshes"][0]
        computed_mesh = computed["meshes"][0]
        self.assertNotIn("faces", native_mesh)
        self.assertEqual(native_mesh["face_count"], FACE_COUNT)
        self.assertEqual(native_mesh["corner_count"], CORNER_COUNT)
        self.assertEqual(len(native_mesh["masks"]), FACE_COUNT)
        self.assertTrue(native_mesh["native"])
        self.assertFalse(computed_mesh["native"])
        self.assertEqual(
            native_mesh["topology_sha256"],
            computed_mesh["topology_sha256"],
        )
        self.assertEqual(
            native["input_sha256"],
            hashlib.sha256(
                NATIVE_SMOOTHING_FIXTURE.read_bytes()
            ).hexdigest(),
        )
        self.assertEqual(native["interpreter_major"], sys.version_info.major)
        self.assertEqual(native["interpreter_minor"], sys.version_info.minor)
        self.assertEqual(native["interpreter_bits"], struct.calcsize("P") * 8)
        self.assertTrue(Path(native["metadata_module_file"]).is_absolute())
        self.assertTrue(Path(native["smoothing_module_file"]).is_absolute())
        self.assertEqual(len(native["metadata_source_sha256"]), 64)
        self.assertEqual(len(native["smoothing_source_sha256"]), 64)

        response_digest = native["response_sha256"]
        unhashed = dict(native)
        del unhashed["response_sha256"]
        canonical = json.dumps(
            unhashed,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(
            response_digest, hashlib.sha256(canonical).hexdigest()
        )

    def test_resolver_atomic_write_and_failure_preserves_old_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "response.json"
            write_strict_resolver_json(
                NATIVE_SMOOTHING_FIXTURE,
                output,
            )
            raw = output.read_bytes()
            self.assertTrue(raw.endswith(b"\n"))
            payload = json.loads(raw.decode("utf-8"))
            self.assertEqual(payload["schema"], RESOLVER_SCHEMA)
            self.assertEqual(
                list(Path(directory).glob(".f2m-resolver-*.tmp")),
                [],
            )

            sentinel = b"previous-complete-response\n"
            output.write_bytes(sentinel)
            with self.assertRaises(FbxMetadataIOError):
                write_strict_resolver_json(
                    Path(directory) / "missing.fbx",
                    output,
                )
            self.assertEqual(output.read_bytes(), sentinel)
            self.assertEqual(
                list(Path(directory).glob(".f2m-resolver-*.tmp")),
                [],
            )

    def test_resolver_cli_success_and_nonzero_failure(self) -> None:
        script = ROOT / "contents" / "f2m_fbx_metadata.py"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "cli.json"
            environment = dict(os.environ)
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            environment["PYTHONIOENCODING"] = "utf-8"
            success = subprocess.run(
                (
                    sys.executable,
                    str(script),
                    "--input",
                    str(NATIVE_SMOOTHING_FIXTURE),
                    "--output",
                    str(output),
                ),
                cwd=str(ROOT),
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(success.returncode, 0, success.stderr)
            self.assertEqual(success.stdout, "")
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8"))["schema"],
                RESOLVER_SCHEMA,
            )

            missing_output = Path(directory) / "missing.json"
            failure = subprocess.run(
                (
                    sys.executable,
                    str(script),
                    "--input",
                    str(Path(directory) / "missing.fbx"),
                    "--output",
                    str(missing_output),
                ),
                cwd=str(ROOT),
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertNotEqual(failure.returncode, 0)
            self.assertEqual(failure.stdout, "")
            self.assertIn("strict resolver failed:", failure.stderr)
            self.assertFalse(missing_output.exists())

    def test_autodesk_unnamed_geometry_and_ascii_boolean(self) -> None:
        self.assertEqual(
            self._read_temp(_autodesk_unnamed_geometry_document(7400)),
            {"VisibleMesh": True},
        )

    def test_minimal_ascii_true_false_and_geometry_model_connections(self) -> None:
        self.assertEqual(
            self._read_temp(ASCII_MINIMAL.encode("utf-8")),
            {
                "ShownInferred": False,
                "ShownNative": True,
            },
        )

    def test_binary_7400_uses_32_bit_headers_and_skips_all_properties(self) -> None:
        self.assertEqual(
            self._read_temp(_binary_metadata_document(7400)),
            {"Inferred": False, "Native": True},
        )

    def test_binary_7500_uses_64_bit_headers(self) -> None:
        self.assertEqual(
            self._read_temp(_binary_metadata_document(7500)),
            {"Inferred": False, "Native": True},
        )

    def test_duplicate_visible_mesh_model_name_fails_closed(self) -> None:
        duplicate = ASCII_MINIMAL.replace(
            '"Model::ShownInferred"', '"Model::ShownNative"'
        )
        with self.assertRaises(FbxAmbiguityError):
            self._read_temp(duplicate.encode("utf-8"))

    def test_ambiguous_model_with_two_geometries_fails_closed(self) -> None:
        ambiguous = ASCII_MINIMAL.replace(
            'C: "OO", 102, 202', 'C: "OO", 102, 201'
        )
        with self.assertRaises(FbxAmbiguityError):
            self._read_temp(ambiguous.encode("utf-8"))

    def test_malformed_ascii_braces_raise_typed_format_error(self) -> None:
        with self.assertRaises(FBXMetadataError):
            self._read_temp(ASCII_MINIMAL.rsplit("}", 1)[0].encode("utf-8"))

    def test_duplicate_connection_fails_closed(self) -> None:
        duplicate = ASCII_MINIMAL.replace(
            '    C: "OO", 102, 202\n',
            '    C: "OO", 102, 202\n    C: "OO", 102, 202\n',
        )
        with self.assertRaises(FbxAmbiguityError):
            self._read_temp(duplicate.encode("utf-8"))

    def test_nonexistent_path_raises_typed_io_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.fbx"
            with self.assertRaises(FbxMetadataIOError):
                inspect_fbx_smoothing(missing)


if __name__ == "__main__":
    unittest.main()
