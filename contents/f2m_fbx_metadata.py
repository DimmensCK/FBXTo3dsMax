# -*- coding: utf-8 -*-
"""Read-only FBX metadata inspection used by FBXTo3dsMax.

The module intentionally does not import the Autodesk FBX SDK or any third
party package.  It reads just enough of an FBX document to answer one narrow
question: for each visible Mesh/Model name, does its connected Mesh/Geometry
contain a native ``LayerElementSmoothing`` node?

Both binary FBX 7.x and ASCII FBX are supported.  Ambiguous object identities,
duplicate visible mesh names, broken node offsets, malformed properties, and
ambiguous Geometry-to-Model connections raise a typed exception instead of
silently guessing.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import math
import os
import struct
import sys
import tempfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Dict, Iterable, List, Optional, Sequence, Set, Tuple


TOOL_VERSION = "1.4.25"
RESOLVER_SCHEMA = "FBXTo3dsMax.strict_resolver"
RESOLVER_SCHEMA_VERSION = 1
RESOLVER_NORMAL_TOLERANCE_DEGREES = 0.01
RESOLVER_MAX_SMOOTHING_GROUPS = 32
RESOLVER_TOPOLOGY_ENCODING = (
    "little-endian uint32 face_degree followed by uint32 zero-based "
    "vertex IDs, repeated in FBX face order"
)

_BINARY_MAGIC = b"Kaydara FBX Binary  \x00\x1a\x00"
_MAX_DEPTH = 256
_MAX_PROPERTY_COUNT = 10_000_000
_MAX_NAME_BYTES = 1_048_576
_MAX_CAPTURED_INT32_ELEMENTS = 4_000_000
_MAX_CAPTURED_INT32_BYTES = _MAX_CAPTURED_INT32_ELEMENTS * 4
_MAX_CAPTURED_FLOAT64_ELEMENTS = 6_000_000
_MAX_CAPTURED_FLOAT64_BYTES = _MAX_CAPTURED_FLOAT64_ELEMENTS * 8
_MAX_CAPTURED_TOTAL_BYTES = 96 * 1024 * 1024
_MAX_CAPTURED_ARRAY_PAYLOAD_BYTES = 96 * 1024 * 1024
_MAX_ASCII_STRICT_BYTES = 128 * 1024 * 1024
_MAX_FACE_COUNT = 5_000_000
_MAX_FACE_DEGREE = 1_000_000


class FBXMetadataError(Exception):
    """Base class for every fail-closed metadata inspection failure."""

    def __str__(self) -> str:
        return "FBX 平滑元数据检查失败。"


class FbxMetadataIOError(FBXMetadataError):
    """The FBX file could not be opened or read."""

    def __str__(self) -> str:
        return "无法打开或读取 FBX 文件。"


class FbxFormatError(FBXMetadataError):
    """The FBX stream is truncated, malformed, or unsupported."""

    def __str__(self) -> str:
        return "FBX 文件已截断、格式损坏或当前版本不受支持。"


class FbxAmbiguityError(FBXMetadataError):
    """The FBX metadata cannot be mapped to unique visible mesh models."""

    def __str__(self) -> str:
        return "FBX 网格、模型名称或连接关系存在歧义，无法安全确定唯一对应项。"


@dataclass(frozen=True)
class FbxMeshSmoothingData:
    """Strict FBX polygon topology and optional native smoothing masks.

    ``faces`` contains decoded, zero-based FBX control-point indices in the
    exact ``PolygonVertexIndex`` face/corner order.  ``masks`` contains the
    signed int32 bit patterns stored by a unique native
    ``LayerElementSmoothing``.  A mesh without a native smoothing layer has
    ``masks=None`` and no layer/mapping/reference metadata.
    """

    faces: Tuple[Tuple[int, ...], ...]
    masks: Optional[Tuple[int, ...]]
    layer_index: Optional[int]
    smoothing_typed_index: Optional[int]
    mapping_information_type: Optional[str]
    reference_information_type: Optional[str]
    corner_normals: Optional[
        Tuple[Tuple[Tuple[float, float, float], ...], ...]
    ] = None
    normal_layer_index: Optional[int] = None
    normal_typed_index: Optional[int] = None
    normal_mapping_information_type: Optional[str] = None
    normal_reference_information_type: Optional[str] = None

    @property
    def has_native_smoothing(self) -> bool:
        return self.masks is not None

    @property
    def unsigned_masks(self) -> Optional[Tuple[int, ...]]:
        if self.masks is None:
            return None
        return tuple(value & 0xFFFFFFFF for value in self.masks)


@dataclass
class _SmoothingLayer:
    typed_index: int
    mapping_information_type: Optional[str] = None
    reference_information_type: Optional[str] = None
    masks: Optional[Tuple[int, ...]] = None


@dataclass
class _NormalLayer:
    typed_index: int
    mapping_information_type: Optional[str] = None
    reference_information_type: Optional[str] = None
    normals: Optional[Tuple[float, ...]] = None
    normal_indices: Optional[Tuple[int, ...]] = None


@dataclass
class _Geometry:
    object_id: int
    name: str
    is_mesh: bool
    has_native_smoothing: bool = False
    vertex_count: Optional[int] = None
    faces: Optional[Tuple[Tuple[int, ...], ...]] = None
    smoothing_layers: Dict[int, _SmoothingLayer] = field(default_factory=dict)
    normal_layers: Dict[int, _NormalLayer] = field(default_factory=dict)
    layer_indices: Set[int] = field(default_factory=set)
    layer_references: List[Tuple[int, str, int]] = field(default_factory=list)


@dataclass(frozen=True)
class _Model:
    object_id: int
    name: str
    is_mesh: bool


@dataclass(frozen=True)
class _Connection:
    kind: str
    child_id: int
    parent_id: int
    extra: Tuple[object, ...]


@dataclass(frozen=True)
class _ArrayProperty:
    type_code: str
    element_count: int
    encoding: int
    payload_size: int


@dataclass(frozen=True)
class _NumericArrayProperty:
    type_code: str
    values: Tuple[object, ...]
    encoding: int
    payload_size: int


class _MetadataCollector:
    def __init__(self) -> None:
        self.geometries: Dict[int, _Geometry] = {}
        self.models: Dict[int, _Model] = {}
        self.connections: List[_Connection] = []
        self._object_ids: Dict[int, str] = {}
        self._connection_keys = set()

    def _geometry(self, geometry_id: int, description: str) -> _Geometry:
        geometry = self.geometries.get(geometry_id)
        if geometry is None:
            raise FbxFormatError(
                "{} belongs to unknown Geometry ID {}.".format(
                    description, geometry_id
                )
            )
        return geometry

    def _claim_object_id(self, object_id: int, description: str) -> None:
        previous = self._object_ids.get(object_id)
        if previous is not None:
            raise FbxAmbiguityError(
                "Duplicate FBX object ID {} ({} and {}).".format(
                    object_id, previous, description
                )
            )
        self._object_ids[object_id] = description

    def add_geometry(
        self, object_id: int, encoded_name: object, object_kind: object
    ) -> None:
        name = _visible_object_name(encoded_name, "Geometry")
        kind = _property_text(object_kind, "Geometry object kind")
        self._claim_object_id(object_id, "Geometry {!r}".format(name))
        self.geometries[object_id] = _Geometry(
            object_id=object_id,
            name=name,
            is_mesh=(kind.casefold() == "mesh"),
        )

    def add_model(
        self, object_id: int, encoded_name: object, object_kind: object
    ) -> None:
        name = _visible_object_name(encoded_name, "Model")
        kind = _property_text(object_kind, "Model object kind")
        self._claim_object_id(object_id, "Model {!r}".format(name))
        self.models[object_id] = _Model(
            object_id=object_id,
            name=name,
            is_mesh=(kind.casefold() == "mesh"),
        )

    def mark_smoothing(self, geometry_id: int) -> None:
        geometry = self._geometry(geometry_id, "LayerElementSmoothing")
        geometry.has_native_smoothing = True

    def add_smoothing_layer(self, geometry_id: int, typed_index: int) -> None:
        geometry = self._geometry(geometry_id, "LayerElementSmoothing")
        if typed_index < 0:
            raise FbxFormatError(
                "LayerElementSmoothing typed index must be non-negative."
            )
        if typed_index in geometry.smoothing_layers:
            raise FbxAmbiguityError(
                "Geometry ID {} defines duplicate LayerElementSmoothing "
                "typed index {}.".format(geometry_id, typed_index)
            )
        geometry.smoothing_layers[typed_index] = _SmoothingLayer(typed_index)
        geometry.has_native_smoothing = True

    def add_normal_layer(self, geometry_id: int, typed_index: int) -> None:
        geometry = self._geometry(geometry_id, "LayerElementNormal")
        if typed_index < 0:
            raise FbxFormatError(
                "LayerElementNormal typed index must be non-negative."
            )
        if typed_index in geometry.normal_layers:
            raise FbxAmbiguityError(
                "Geometry ID {} defines duplicate LayerElementNormal typed "
                "index {}.".format(geometry_id, typed_index)
            )
        geometry.normal_layers[typed_index] = _NormalLayer(typed_index)

    def set_polygon_vertex_indices(
        self, geometry_id: int, values: Sequence[int]
    ) -> None:
        geometry = self._geometry(geometry_id, "PolygonVertexIndex")
        if geometry.faces is not None:
            raise FbxAmbiguityError(
                "Geometry ID {} contains duplicate PolygonVertexIndex arrays.".format(
                    geometry_id
                )
            )
        geometry.faces = _decode_polygon_vertex_indices(values)

    def set_vertex_component_count(
        self, geometry_id: int, component_count: int
    ) -> None:
        geometry = self._geometry(geometry_id, "Vertices")
        if geometry.vertex_count is not None:
            raise FbxAmbiguityError(
                "Geometry ID {} contains duplicate Vertices arrays.".format(
                    geometry_id
                )
            )
        if component_count < 3 or component_count % 3 != 0:
            raise FbxFormatError(
                "Geometry ID {} Vertices array count {} is not a positive "
                "multiple of three.".format(geometry_id, component_count)
            )
        geometry.vertex_count = component_count // 3

    def set_layer_mapping(
        self,
        geometry_id: int,
        layer_kind: str,
        typed_index: int,
        value: object,
    ) -> None:
        text = _property_text(value, "{} MappingInformationType".format(layer_kind))
        layer = self._layer(geometry_id, layer_kind, typed_index)
        if layer.mapping_information_type is not None:
            raise FbxAmbiguityError(
                "Geometry ID {} {} {} contains duplicate "
                "MappingInformationType records.".format(
                    geometry_id, layer_kind, typed_index
                )
            )
        layer.mapping_information_type = text

    def set_layer_reference_mode(
        self,
        geometry_id: int,
        layer_kind: str,
        typed_index: int,
        value: object,
    ) -> None:
        text = _property_text(
            value, "{} ReferenceInformationType".format(layer_kind)
        )
        layer = self._layer(geometry_id, layer_kind, typed_index)
        if layer.reference_information_type is not None:
            raise FbxAmbiguityError(
                "Geometry ID {} {} {} contains duplicate "
                "ReferenceInformationType records.".format(
                    geometry_id, layer_kind, typed_index
                )
            )
        layer.reference_information_type = text

    def _layer(
        self, geometry_id: int, layer_kind: str, typed_index: int
    ) -> object:
        geometry = self._geometry(geometry_id, layer_kind)
        if layer_kind == "LayerElementSmoothing":
            layer = geometry.smoothing_layers.get(typed_index)
        elif layer_kind == "LayerElementNormal":
            layer = geometry.normal_layers.get(typed_index)
        else:
            raise FbxFormatError("Unsupported strict layer kind {!r}.".format(layer_kind))
        if layer is None:
            raise FbxFormatError(
                "Geometry ID {} references unknown {} typed index {}.".format(
                    geometry_id, layer_kind, typed_index
                )
            )
        return layer

    def set_smoothing_masks(
        self, geometry_id: int, typed_index: int, values: Sequence[int]
    ) -> None:
        layer = self._layer(
            geometry_id, "LayerElementSmoothing", typed_index
        )
        assert isinstance(layer, _SmoothingLayer)
        if layer.masks is not None:
            raise FbxAmbiguityError(
                "Geometry ID {} LayerElementSmoothing {} contains duplicate "
                "Smoothing arrays.".format(geometry_id, typed_index)
            )
        layer.masks = tuple(_require_signed_int32(value, "Smoothing mask") for value in values)

    def set_normals(
        self, geometry_id: int, typed_index: int, values: Sequence[object]
    ) -> None:
        layer = self._layer(geometry_id, "LayerElementNormal", typed_index)
        assert isinstance(layer, _NormalLayer)
        if layer.normals is not None:
            raise FbxAmbiguityError(
                "Geometry ID {} LayerElementNormal {} contains duplicate "
                "Normals arrays.".format(geometry_id, typed_index)
            )
        normalized: List[float] = []
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise FbxFormatError("Normals array must contain numeric values.")
            numeric = float(value)
            if not math.isfinite(numeric):
                raise FbxFormatError("Normals array contains a non-finite value.")
            normalized.append(numeric)
        layer.normals = tuple(normalized)

    def set_normal_indices(
        self, geometry_id: int, typed_index: int, values: Sequence[int]
    ) -> None:
        layer = self._layer(geometry_id, "LayerElementNormal", typed_index)
        assert isinstance(layer, _NormalLayer)
        if layer.normal_indices is not None:
            raise FbxAmbiguityError(
                "Geometry ID {} LayerElementNormal {} contains duplicate "
                "NormalsIndex arrays.".format(geometry_id, typed_index)
            )
        layer.normal_indices = tuple(
            _require_signed_int32(value, "NormalsIndex") for value in values
        )

    def add_layer(self, geometry_id: int, layer_index: int) -> None:
        geometry = self._geometry(geometry_id, "Layer")
        if layer_index < 0:
            raise FbxFormatError("Layer index must be non-negative.")
        if layer_index in geometry.layer_indices:
            raise FbxAmbiguityError(
                "Geometry ID {} defines duplicate Layer index {}.".format(
                    geometry_id, layer_index
                )
            )
        geometry.layer_indices.add(layer_index)

    def add_layer_reference(
        self,
        geometry_id: int,
        layer_index: int,
        layer_kind: str,
        typed_index: int,
    ) -> None:
        geometry = self._geometry(geometry_id, "Layer/LayerElement")
        if layer_index not in geometry.layer_indices:
            raise FbxFormatError(
                "LayerElement belongs to unknown Layer index {} in Geometry "
                "ID {}.".format(layer_index, geometry_id)
            )
        if typed_index < 0:
            raise FbxFormatError("LayerElement TypedIndex must be non-negative.")
        key = (layer_index, layer_kind, typed_index)
        if key in geometry.layer_references:
            raise FbxAmbiguityError(
                "Geometry ID {} contains duplicate LayerElement reference "
                "{!r}.".format(geometry_id, key)
            )
        geometry.layer_references.append(key)

    def add_connection(self, properties: Sequence[object]) -> None:
        if len(properties) < 3:
            raise FbxFormatError(
                "A Connections/C record must contain type, child ID, and parent ID."
            )
        kind = _property_text(properties[0], "connection type")
        child_id = _property_int(properties[1], "connection child ID")
        parent_id = _property_int(properties[2], "connection parent ID")
        extra = tuple(_hashable_property(value) for value in properties[3:])
        key = (kind, child_id, parent_id, extra)
        if key in self._connection_keys:
            raise FbxAmbiguityError(
                "Duplicate FBX connection {!r}: {} -> {}.".format(
                    kind, child_id, parent_id
                )
            )
        self._connection_keys.add(key)
        self.connections.append(
            _Connection(
                kind=kind,
                child_id=child_id,
                parent_id=parent_id,
                extra=extra,
            )
        )

    def _resolved_mesh_models(self) -> List[Tuple[_Model, _Geometry]]:
        geometry_parents: Dict[int, List[int]] = {}
        model_geometries: Dict[int, List[int]] = {}

        for connection in self.connections:
            if connection.kind != "OO":
                continue
            if connection.child_id not in self.geometries:
                continue
            geometry_parents.setdefault(connection.child_id, []).append(
                connection.parent_id
            )
            if connection.parent_id in self.models:
                model_geometries.setdefault(connection.parent_id, []).append(
                    connection.child_id
                )

        resolved: List[Tuple[_Model, _Geometry]] = []
        visible_name_ids: Dict[str, int] = {}
        for model_id in sorted(self.models):
            model = self.models[model_id]
            if not model.is_mesh:
                continue
            geometry_ids = model_geometries.get(model_id, [])
            if len(geometry_ids) != 1:
                raise FbxAmbiguityError(
                    "Mesh Model {!r} (ID {}) has {} connected Geometry objects; "
                    "exactly one is required.".format(
                        model.name, model_id, len(geometry_ids)
                    )
                )
            geometry = self.geometries[geometry_ids[0]]
            if not geometry.is_mesh:
                raise FbxAmbiguityError(
                    "Mesh Model {!r} is connected to non-Mesh Geometry {!r}.".format(
                        model.name, geometry.name
                    )
                )
            previous_id = visible_name_ids.get(model.name)
            if previous_id is not None:
                raise FbxAmbiguityError(
                    "Duplicate visible Mesh/Model name {!r} (IDs {} and {}).".format(
                        model.name, previous_id, model_id
                    )
                )
            visible_name_ids[model.name] = model_id
            resolved.append((model, geometry))

        for geometry_id, geometry in self.geometries.items():
            if not geometry.is_mesh:
                continue
            mesh_model_parents = [
                parent_id
                for parent_id in geometry_parents.get(geometry_id, [])
                if parent_id in self.models and self.models[parent_id].is_mesh
            ]
            if not mesh_model_parents:
                raise FbxAmbiguityError(
                    "Mesh Geometry {!r} (ID {}) is not connected to a Mesh Model.".format(
                        geometry.name, geometry_id
                    )
                )

        return sorted(resolved, key=lambda item: item[0].name)

    def result(self) -> Dict[str, bool]:
        return {
            model.name: geometry.has_native_smoothing
            for model, geometry in self._resolved_mesh_models()
        }

    def smoothing_data_result(
        self, include_corner_normals: bool = False
    ) -> Dict[str, FbxMeshSmoothingData]:
        result: Dict[str, FbxMeshSmoothingData] = {}
        for model, geometry in self._resolved_mesh_models():
            if geometry.faces is None:
                raise FbxFormatError(
                    "Mesh Geometry {!r} has no unique PolygonVertexIndex "
                    "array.".format(geometry.name)
                )
            if geometry.vertex_count is None:
                raise FbxFormatError(
                    "Mesh Geometry {!r} has no unique Vertices array.".format(
                        geometry.name
                    )
                )
            for face_index, face in enumerate(geometry.faces):
                for vertex_index in face:
                    if vertex_index >= geometry.vertex_count:
                        raise FbxFormatError(
                            "Mesh Geometry {!r} face {} references control "
                            "point {}, but only {} exist.".format(
                                geometry.name,
                                face_index,
                                vertex_index,
                                geometry.vertex_count,
                            )
                        )

            smoothing_layer_index: Optional[int] = None
            smoothing_typed_index: Optional[int] = None
            smoothing_mapping: Optional[str] = None
            smoothing_reference: Optional[str] = None
            masks: Optional[Tuple[int, ...]] = None
            smoothing_refs = [
                reference
                for reference in geometry.layer_references
                if reference[1] == "LayerElementSmoothing"
            ]
            if geometry.smoothing_layers or smoothing_refs:
                if len(geometry.smoothing_layers) != 1:
                    raise FbxAmbiguityError(
                        "Mesh Geometry {!r} defines {} smoothing layers; "
                        "exactly one is required.".format(
                            geometry.name, len(geometry.smoothing_layers)
                        )
                    )
                if len(smoothing_refs) != 1:
                    raise FbxAmbiguityError(
                        "Mesh Geometry {!r} references {} smoothing layers; "
                        "exactly one is required.".format(
                            geometry.name, len(smoothing_refs)
                        )
                    )
                smoothing_typed_index, layer = next(
                    iter(geometry.smoothing_layers.items())
                )
                smoothing_layer_index, _, referenced_index = smoothing_refs[0]
                if referenced_index != smoothing_typed_index:
                    raise FbxAmbiguityError(
                        "Mesh Geometry {!r} smoothing TypedIndex reference {} "
                        "does not match definition {}.".format(
                            geometry.name,
                            referenced_index,
                            smoothing_typed_index,
                        )
                    )
                if layer.mapping_information_type != "ByPolygon":
                    raise FbxFormatError(
                        "Mesh Geometry {!r} smoothing mapping {!r} is not "
                        "strictly supported; ByPolygon is required.".format(
                            geometry.name, layer.mapping_information_type
                        )
                    )
                if layer.reference_information_type != "Direct":
                    raise FbxFormatError(
                        "Mesh Geometry {!r} smoothing reference {!r} is not "
                        "strictly supported; Direct is required.".format(
                            geometry.name, layer.reference_information_type
                        )
                    )
                if layer.masks is None:
                    raise FbxFormatError(
                        "Mesh Geometry {!r} smoothing layer has no Smoothing "
                        "int32 array.".format(geometry.name)
                    )
                if len(layer.masks) != len(geometry.faces):
                    raise FbxFormatError(
                        "Mesh Geometry {!r} has {} smoothing masks for {} "
                        "polygons.".format(
                            geometry.name,
                            len(layer.masks),
                            len(geometry.faces),
                        )
                    )
                smoothing_mapping = layer.mapping_information_type
                smoothing_reference = layer.reference_information_type
                masks = layer.masks

            if include_corner_normals:
                (
                    corner_normals,
                    normal_layer_index,
                    normal_typed_index,
                    normal_mapping,
                    normal_reference,
                ) = self._resolve_corner_normals(geometry)
            else:
                corner_normals = None
                normal_layer_index = None
                normal_typed_index = None
                normal_mapping = None
                normal_reference = None
            result[model.name] = FbxMeshSmoothingData(
                faces=geometry.faces,
                masks=masks,
                layer_index=smoothing_layer_index,
                smoothing_typed_index=smoothing_typed_index,
                mapping_information_type=smoothing_mapping,
                reference_information_type=smoothing_reference,
                corner_normals=corner_normals,
                normal_layer_index=normal_layer_index,
                normal_typed_index=normal_typed_index,
                normal_mapping_information_type=normal_mapping,
                normal_reference_information_type=normal_reference,
            )
        return result

    def _resolve_corner_normals(
        self, geometry: _Geometry
    ) -> Tuple[
        Optional[Tuple[Tuple[Tuple[float, float, float], ...], ...]],
        Optional[int],
        Optional[int],
        Optional[str],
        Optional[str],
    ]:
        normal_refs = [
            reference
            for reference in geometry.layer_references
            if reference[1] == "LayerElementNormal"
        ]
        if not geometry.normal_layers and not normal_refs:
            return None, None, None, None, None
        if len(geometry.normal_layers) != 1:
            raise FbxAmbiguityError(
                "Mesh Geometry {!r} defines {} normal layers; exactly one is "
                "required.".format(geometry.name, len(geometry.normal_layers))
            )
        if len(normal_refs) != 1:
            raise FbxAmbiguityError(
                "Mesh Geometry {!r} references {} normal layers; exactly one "
                "is required.".format(geometry.name, len(normal_refs))
            )
        typed_index, layer = next(iter(geometry.normal_layers.items()))
        layer_index, _, referenced_index = normal_refs[0]
        if referenced_index != typed_index:
            raise FbxAmbiguityError(
                "Mesh Geometry {!r} normal TypedIndex reference {} does not "
                "match definition {}.".format(
                    geometry.name, referenced_index, typed_index
                )
            )
        if layer.mapping_information_type != "ByPolygonVertex":
            raise FbxFormatError(
                "Mesh Geometry {!r} normal mapping {!r} is not strictly "
                "supported; ByPolygonVertex is required.".format(
                    geometry.name, layer.mapping_information_type
                )
            )
        if layer.reference_information_type not in ("Direct", "IndexToDirect"):
            raise FbxFormatError(
                "Mesh Geometry {!r} normal reference {!r} is not strictly "
                "supported.".format(
                    geometry.name, layer.reference_information_type
                )
            )
        if layer.normals is None or len(layer.normals) % 3 != 0:
            raise FbxFormatError(
                "Mesh Geometry {!r} Normals array is absent or not made of "
                "double triplets.".format(geometry.name)
            )
        assert geometry.faces is not None
        corner_count = sum(len(face) for face in geometry.faces)
        vectors = tuple(
            (
                layer.normals[offset],
                layer.normals[offset + 1],
                layer.normals[offset + 2],
            )
            for offset in range(0, len(layer.normals), 3)
        )
        if layer.reference_information_type == "Direct":
            if layer.normal_indices is not None:
                raise FbxFormatError(
                    "Mesh Geometry {!r} Direct normal layer unexpectedly "
                    "contains NormalsIndex.".format(geometry.name)
                )
            if len(vectors) != corner_count:
                raise FbxFormatError(
                    "Mesh Geometry {!r} has {} Direct normal vectors for {} "
                    "polygon corners.".format(
                        geometry.name, len(vectors), corner_count
                    )
                )
            flat_vectors = vectors
        else:
            if layer.normal_indices is None:
                raise FbxFormatError(
                    "Mesh Geometry {!r} IndexToDirect normal layer has no "
                    "NormalsIndex array.".format(geometry.name)
                )
            if len(layer.normal_indices) != corner_count:
                raise FbxFormatError(
                    "Mesh Geometry {!r} has {} NormalsIndex values for {} "
                    "polygon corners.".format(
                        geometry.name,
                        len(layer.normal_indices),
                        corner_count,
                    )
                )
            expanded: List[Tuple[float, float, float]] = []
            for corner_index, normal_index in enumerate(layer.normal_indices):
                if normal_index < 0 or normal_index >= len(vectors):
                    raise FbxFormatError(
                        "Mesh Geometry {!r} NormalsIndex {} at corner {} is "
                        "outside 0..{}.".format(
                            geometry.name,
                            normal_index,
                            corner_index,
                            len(vectors) - 1,
                        )
                    )
                expanded.append(vectors[normal_index])
            flat_vectors = tuple(expanded)

        rows: List[Tuple[Tuple[float, float, float], ...]] = []
        offset = 0
        for face in geometry.faces:
            next_offset = offset + len(face)
            rows.append(tuple(flat_vectors[offset:next_offset]))
            offset = next_offset
        return (
            tuple(rows),
            layer_index,
            typed_index,
            layer.mapping_information_type,
            layer.reference_information_type,
        )


def _hashable_property(value: object) -> object:
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, _ArrayProperty):
        return (
            value.type_code,
            value.element_count,
            value.encoding,
            value.payload_size,
        )
    if isinstance(value, _NumericArrayProperty):
        return (
            value.type_code,
            value.values,
            value.encoding,
            value.payload_size,
        )
    try:
        hash(value)
    except TypeError:
        return repr(value)
    return value


def _property_int(value: object, description: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FbxFormatError("{} must be an integer.".format(description))
    return value


def _single_property(
    properties: Sequence[object], description: str
) -> object:
    if len(properties) != 1:
        raise FbxFormatError(
            "{} must contain exactly one property.".format(description)
        )
    return properties[0]


def _require_signed_int32(value: object, description: str) -> int:
    integer = _property_int(value, description)
    if integer < -0x80000000 or integer > 0x7FFFFFFF:
        raise FbxFormatError(
            "{} is outside the signed int32 range: {!r}.".format(
                description, integer
            )
        )
    return integer


def _decode_polygon_vertex_indices(
    values: Sequence[int],
) -> Tuple[Tuple[int, ...], ...]:
    if not values:
        raise FbxFormatError("PolygonVertexIndex array is empty.")
    faces: List[Tuple[int, ...]] = []
    current: List[int] = []
    for array_index, raw_value in enumerate(values):
        value = _require_signed_int32(raw_value, "PolygonVertexIndex")
        terminates_face = value < 0
        vertex_index = -value - 1 if terminates_face else value
        current.append(vertex_index)
        if len(current) > _MAX_FACE_DEGREE:
            raise FbxFormatError(
                "PolygonVertexIndex face exceeds the safe degree limit of "
                "{}.".format(_MAX_FACE_DEGREE)
            )
        if not terminates_face:
            continue
        if len(current) < 3:
            raise FbxFormatError(
                "Polygon ending at PolygonVertexIndex element {} has fewer "
                "than three corners.".format(array_index)
            )
        if len(set(current)) != len(current):
            raise FbxFormatError(
                "Polygon ending at PolygonVertexIndex element {} repeats a "
                "control-point index.".format(array_index)
            )
        faces.append(tuple(current))
        current = []
        if len(faces) > _MAX_FACE_COUNT:
            raise FbxFormatError(
                "Polygon count exceeds the safe limit of {}.".format(
                    _MAX_FACE_COUNT
                )
            )
    if current:
        raise FbxFormatError(
            "PolygonVertexIndex ends without a negative polygon terminator."
        )
    if not faces:
        raise FbxFormatError("PolygonVertexIndex contains no polygons.")
    return tuple(faces)


def _decompress_array_payload(
    payload: bytes, expected_size: int, description: str
) -> bytes:
    if expected_size < 0:
        raise FbxFormatError("{} has an invalid decoded size.".format(description))
    decompressor = zlib.decompressobj()
    try:
        decoded = decompressor.decompress(payload, expected_size + 1)
        if len(decoded) > expected_size:
            raise FbxFormatError(
                "{} expands beyond its declared decoded size.".format(description)
            )
        tail = decompressor.flush(expected_size + 1 - len(decoded))
    except zlib.error as exc:
        raise FbxFormatError(
            "{} contains an invalid zlib payload.".format(description)
        ) from exc
    decoded += tail
    if (
        len(decoded) != expected_size
        or not decompressor.eof
        or decompressor.unused_data
        or decompressor.unconsumed_tail
    ):
        raise FbxFormatError(
            "{} decoded length/stream boundary does not match its array "
            "header.".format(description)
        )
    return decoded


def _decode_utf8(value: bytes, description: str) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FbxFormatError("{} is not valid UTF-8.".format(description)) from exc


def _property_text(value: object, description: str) -> str:
    if isinstance(value, bytes):
        text = _decode_utf8(value, description)
    elif isinstance(value, str):
        text = value
    else:
        raise FbxFormatError("{} must be a string.".format(description))
    if "\x00" in text and "\x00\x01" not in text:
        raise FbxFormatError("{} contains an unexpected NUL byte.".format(description))
    return text


def _finish_layer_element_reference(
    builder: _LayerElementReferenceBuilder,
    *,
    capture_corner_normals: bool,
) -> Optional[Tuple[str, int]]:
    """Resolve one requested LayerElement reference without parsing others.

    Smoothing-only reads deliberately ignore malformed normal/material/etc.
    references.  A record is validated only when one of its raw ``Type``
    values identifies a layer requested by the current public API.
    """

    requested_kinds = {"LayerElementSmoothing"}
    if capture_corner_normals:
        requested_kinds.add("LayerElementNormal")

    matched_kind: Optional[str] = None
    for record in builder.type_records:
        for raw_value in record:
            try:
                candidate = _property_text(raw_value, "LayerElement Type")
            except FbxFormatError:
                continue
            if candidate not in requested_kinds:
                continue
            if matched_kind is not None and candidate != matched_kind:
                raise FbxAmbiguityError(
                    "LayerElement mixes multiple requested Type values."
                )
            matched_kind = candidate

    if matched_kind is None:
        return None
    if len(builder.type_records) != 1 or len(builder.type_records[0]) != 1:
        raise FbxAmbiguityError(
            "{} LayerElement must contain exactly one direct Type record.".format(
                matched_kind
            )
        )
    layer_kind = _property_text(
        builder.type_records[0][0], "LayerElement Type"
    )
    if layer_kind != matched_kind:
        raise FbxAmbiguityError(
            "LayerElement requested Type resolution is inconsistent."
        )
    if (
        len(builder.typed_index_records) != 1
        or len(builder.typed_index_records[0]) != 1
    ):
        raise FbxAmbiguityError(
            "{} LayerElement must contain exactly one direct TypedIndex "
            "record.".format(layer_kind)
        )
    typed_index = _property_int(
        builder.typed_index_records[0][0],
        "{} LayerElement TypedIndex".format(layer_kind),
    )
    if typed_index < 0:
        raise FbxFormatError(
            "{} LayerElement TypedIndex must be non-negative.".format(
                layer_kind
            )
        )
    return layer_kind, typed_index


def _visible_object_name(value: object, expected_class: str) -> str:
    text = _property_text(value, "{} object name".format(expected_class))

    # Binary FBX stores "VisibleName<NUL><SOH>Model", while ASCII FBX normally
    # stores "Model::VisibleName".
    binary_separator = "\x00\x01"
    if binary_separator in text:
        parts = text.split(binary_separator)
        if len(parts) != 2:
            raise FbxFormatError(
                "Malformed binary FBX object name {!r}.".format(text)
            )
        suffix = parts[1]
        if suffix and suffix.casefold() != expected_class.casefold():
            raise FbxFormatError(
                "Object name {!r} has class suffix {!r}, expected {!r}.".format(
                    parts[0], suffix, expected_class
                )
            )
        visible = parts[0]
        # Autodesk exporters can emit an unnamed Geometry as
        # ``NUL SOH Geometry`` and rely on the connected Model for the visible
        # scene name.  Geometry names are not used for the public result, so
        # accept this interoperable form while continuing to reject unnamed
        # Models (which would make name matching ambiguous).
        if not visible and expected_class.casefold() != "geometry":
            raise FbxFormatError(
                "Malformed binary FBX object name {!r}.".format(text)
            )
    else:
        prefix = expected_class + "::"
        if text.startswith(prefix):
            visible = text[len(prefix) :]
        else:
            visible = text

    if (not visible and expected_class.casefold() != "geometry") or "\x00" in visible:
        raise FbxFormatError(
            "{} has an empty or malformed visible name.".format(expected_class)
        )
    return visible


def _record_object(
    collector: _MetadataCollector, node_name: str, properties: Sequence[object]
) -> Optional[int]:
    if node_name not in ("Geometry", "Model"):
        return None
    if len(properties) < 3:
        raise FbxFormatError(
            "{} record must contain object ID, name, and kind.".format(node_name)
        )
    object_id = _property_int(properties[0], "{} object ID".format(node_name))
    if node_name == "Geometry":
        collector.add_geometry(object_id, properties[1], properties[2])
        return object_id
    collector.add_model(object_id, properties[1], properties[2])
    return None


@dataclass
class _LayerElementReferenceBuilder:
    type_records: List[Tuple[object, ...]] = field(default_factory=list)
    typed_index_records: List[Tuple[object, ...]] = field(default_factory=list)


class _BinaryParser:
    _SCALAR_FORMATS = {
        b"Y": "<h",
        b"C": "<B",
        b"I": "<i",
        b"F": "<f",
        b"D": "<d",
        b"L": "<q",
    }
    _ARRAY_ELEMENT_SIZES = {
        b"f": 4,
        b"d": 8,
        b"l": 8,
        b"i": 4,
        b"b": 1,
        b"c": 1,
        b"y": 2,
    }

    def __init__(
        self,
        stream: BinaryIO,
        file_size: int,
        version: int,
        collector: _MetadataCollector,
        strict_data: bool = False,
        capture_corner_normals: bool = False,
    ) -> None:
        self.stream = stream
        self.file_size = file_size
        self.version = version
        self.collector = collector
        self.is_wide = version >= 7500
        self.null_record_size = 25 if self.is_wide else 13
        self.node_count = 0
        self.strict_data = strict_data
        self.capture_corner_normals = capture_corner_normals
        self.captured_decoded_bytes = 0

    def _read_exact(self, size: int, description: str) -> bytes:
        if size < 0 or self.stream.tell() + size > self.file_size:
            raise FbxFormatError(
                "Truncated binary FBX while reading {}.".format(description)
            )
        data = self.stream.read(size)
        if len(data) != size:
            raise FbxFormatError(
                "Truncated binary FBX while reading {}.".format(description)
            )
        return data

    def _skip_exact(self, size: int, description: str) -> None:
        if size < 0 or self.stream.tell() + size > self.file_size:
            raise FbxFormatError(
                "Truncated binary FBX while skipping {}.".format(description)
            )
        self.stream.seek(size, os.SEEK_CUR)

    def _validate_compressed_array_stream(
        self,
        payload_size: int,
        expected_size: int,
        description: str,
    ) -> None:
        decompressor = zlib.decompressobj()
        remaining_payload = payload_size
        decoded_size = 0
        try:
            while remaining_payload:
                chunk = self._read_exact(
                    min(64 * 1024, remaining_payload),
                    "{} compressed payload".format(description),
                )
                remaining_payload -= len(chunk)
                pending = chunk
                while pending:
                    allowance = max(1, expected_size - decoded_size + 1)
                    decoded = decompressor.decompress(pending, allowance)
                    decoded_size += len(decoded)
                    if decoded_size > expected_size:
                        raise FbxFormatError(
                            "{} expands beyond its declared decoded size.".format(
                                description
                            )
                        )
                    if decompressor.unused_data:
                        raise FbxFormatError(
                            "{} contains trailing compressed-stream data.".format(
                                description
                            )
                        )
                    next_pending = decompressor.unconsumed_tail
                    if (
                        next_pending
                        and len(next_pending) == len(pending)
                        and not decoded
                    ):
                        raise FbxFormatError(
                            "{} compressed decoder made no progress.".format(
                                description
                            )
                        )
                    pending = next_pending
                if decompressor.eof and remaining_payload:
                    raise FbxFormatError(
                        "{} contains bytes after its zlib stream.".format(
                            description
                        )
                    )
            tail = decompressor.flush(
                max(1, expected_size - decoded_size + 1)
            )
        except zlib.error as exc:
            raise FbxFormatError(
                "{} contains an invalid zlib payload.".format(description)
            ) from exc
        decoded_size += len(tail)
        if (
            decoded_size != expected_size
            or not decompressor.eof
            or decompressor.unused_data
            or decompressor.unconsumed_tail
        ):
            raise FbxFormatError(
                "{} decoded length/stream boundary does not match its array "
                "header.".format(description)
            )

    def _read_property(
        self,
        capture_strings: bool,
        capture_array_type: Optional[bytes] = None,
        capture_array_values: bool = True,
    ) -> object:
        type_code = self._read_exact(1, "property type")
        scalar_format = self._SCALAR_FORMATS.get(type_code)
        if scalar_format is not None:
            size = struct.calcsize(scalar_format)
            value = struct.unpack(
                scalar_format,
                self._read_exact(size, "scalar property {!r}".format(type_code)),
            )[0]
            if type_code == b"C":
                # Autodesk FBX writers exist in both numeric (0/1) and ASCII
                # (F/T) boolean variants.  Values are only metadata scalars
                # here, but validate the known encodings instead of accepting
                # arbitrary bytes.
                boolean_values = {
                    0: False,
                    1: True,
                    ord("F"): False,
                    ord("T"): True,
                }
                if value not in boolean_values:
                    raise FbxFormatError(
                        "Binary FBX boolean property must be 0/1/F/T, got {}.".format(
                            value
                        )
                    )
                return boolean_values[value]
            return value

        if type_code in (b"S", b"R"):
            length = struct.unpack(
                "<I", self._read_exact(4, "string/raw property length")
            )[0]
            if (
                capture_strings
                and length > _MAX_NAME_BYTES
                and type_code == b"S"
            ):
                raise FbxFormatError(
                    "Binary FBX string property is unreasonably large ({} bytes).".format(
                        length
                    )
                )
            if type_code == b"S" and capture_strings:
                return self._read_exact(length, "string property")
            self._skip_exact(
                length,
                "string property" if type_code == b"S" else "raw property",
            )
            return (
                "<string>" if type_code == b"S" else "<raw>",
                length,
            )

        element_size = self._ARRAY_ELEMENT_SIZES.get(type_code)
        if element_size is not None:
            element_count, encoding, payload_size = struct.unpack(
                "<III", self._read_exact(12, "array property header")
            )
            if encoding not in (0, 1):
                raise FbxFormatError(
                    "Unsupported FBX array encoding {}.".format(encoding)
                )
            expected_raw_size = element_count * element_size
            if encoding == 0 and payload_size != expected_raw_size:
                raise FbxFormatError(
                    "Raw FBX array size mismatch: {} elements of {} bytes use {} "
                    "payload bytes.".format(
                        element_count, element_size, payload_size
                    )
                )
            if capture_array_type is not None:
                if type_code != capture_array_type:
                    raise FbxFormatError(
                        "Strict FBX array expected type {!r}, got {!r}.".format(
                            capture_array_type.decode("ascii"),
                            type_code.decode("ascii"),
                        )
                    )
                if type_code == b"i":
                    if (
                        element_count > _MAX_CAPTURED_INT32_ELEMENTS
                        or expected_raw_size > _MAX_CAPTURED_INT32_BYTES
                    ):
                        raise FbxFormatError(
                            "Strict int32 FBX array exceeds the safe capture "
                            "limit."
                        )
                    unpack_format = "<i"
                elif type_code == b"d":
                    if (
                        element_count > _MAX_CAPTURED_FLOAT64_ELEMENTS
                        or expected_raw_size > _MAX_CAPTURED_FLOAT64_BYTES
                    ):
                        raise FbxFormatError(
                            "Strict float64 FBX array exceeds the safe capture "
                            "limit."
                        )
                    unpack_format = "<d"
                else:
                    raise FbxFormatError(
                        "Strict numeric FBX array type {!r} is unsupported.".format(
                            type_code.decode("ascii")
                        )
                    )
                if (
                    self.captured_decoded_bytes + expected_raw_size
                    > _MAX_CAPTURED_TOTAL_BYTES
                ):
                    raise FbxFormatError(
                        "Strict FBX numeric arrays exceed the total decoded "
                        "capture budget."
                    )
                if payload_size > _MAX_CAPTURED_ARRAY_PAYLOAD_BYTES:
                    raise FbxFormatError(
                        "Captured FBX array payload exceeds the safe input "
                        "budget."
                    )
                if not capture_array_values:
                    if encoding == 0:
                        self._skip_exact(
                            payload_size,
                            "validated raw array property payload",
                        )
                    else:
                        self._validate_compressed_array_stream(
                            payload_size,
                            expected_raw_size,
                            "Validated binary FBX array",
                        )
                    self.captured_decoded_bytes += expected_raw_size
                    return _ArrayProperty(
                        type_code=type_code.decode("ascii"),
                        element_count=element_count,
                        encoding=encoding,
                        payload_size=payload_size,
                    )
                payload = self._read_exact(
                    payload_size, "captured array property payload"
                )
                if encoding == 0:
                    raw = payload
                else:
                    raw = _decompress_array_payload(
                        payload,
                        expected_raw_size,
                        "Captured binary FBX array",
                    )
                self.captured_decoded_bytes += expected_raw_size
                values = tuple(
                    item[0] for item in struct.iter_unpack(unpack_format, raw)
                )
                if len(values) != element_count:
                    raise FbxFormatError(
                        "Captured binary FBX array element count mismatch."
                    )
                return _NumericArrayProperty(
                    type_code=type_code.decode("ascii"),
                    values=values,
                    encoding=encoding,
                    payload_size=payload_size,
                )
            self._skip_exact(payload_size, "array property payload")
            return _ArrayProperty(
                type_code=type_code.decode("ascii"),
                element_count=element_count,
                encoding=encoding,
                payload_size=payload_size,
            )

        raise FbxFormatError(
            "Unsupported binary FBX property type byte 0x{}.".format(
                type_code.hex()
            )
        )

    def _read_node_header(
        self,
    ) -> Optional[Tuple[int, int, int, bytes, int]]:
        start = self.stream.tell()
        header_format = "<QQQB" if self.is_wide else "<IIIB"
        header_size = struct.calcsize(header_format)
        raw = self._read_exact(header_size, "node header")
        fields = struct.unpack(header_format, raw)
        end_offset, property_count, property_list_size, name_length = fields
        if (
            end_offset == 0
            and property_count == 0
            and property_list_size == 0
            and name_length == 0
        ):
            return None
        if end_offset <= start or end_offset > self.file_size:
            raise FbxFormatError(
                "Binary FBX node at offset {} has invalid endOffset {}.".format(
                    start, end_offset
                )
            )
        if property_count > _MAX_PROPERTY_COUNT:
            raise FbxFormatError(
                "Binary FBX node declares too many properties ({}).".format(
                    property_count
                )
            )
        name = self._read_exact(name_length, "node name")
        if not name:
            raise FbxFormatError(
                "Binary FBX node at offset {} has an empty name.".format(start)
            )
        return end_offset, property_count, property_list_size, name, start

    def _parse_node(
        self,
        depth: int,
        inherited_geometry_id: Optional[int],
        in_connections: bool,
        parent_node_name: Optional[str] = None,
        inherited_layer_kind: Optional[str] = None,
        inherited_typed_index: Optional[int] = None,
        inherited_layer_index: Optional[int] = None,
        layer_reference_builder: Optional[
            _LayerElementReferenceBuilder
        ] = None,
    ) -> bool:
        if depth > _MAX_DEPTH:
            raise FbxFormatError(
                "Binary FBX node nesting exceeds {} levels.".format(_MAX_DEPTH)
            )
        header = self._read_node_header()
        if header is None:
            return False
        end_offset, property_count, property_list_size, name_bytes, start = header
        self.node_count += 1
        try:
            node_name = name_bytes.decode("ascii")
        except UnicodeDecodeError as exc:
            raise FbxFormatError(
                "Binary FBX node name at offset {} is not ASCII.".format(start)
            ) from exc

        properties_start = self.stream.tell()
        properties_end = properties_start + property_list_size
        if properties_end > end_offset:
            raise FbxFormatError(
                "Binary FBX node {!r} property list crosses its endOffset.".format(
                    node_name
                )
            )
        capture_strings = (
            node_name in ("Geometry", "Model")
            or (node_name == "C" and in_connections)
            or (
                self.strict_data
                and node_name
                in (
                    "MappingInformationType",
                    "ReferenceInformationType",
                    "Type",
                )
            )
        )
        capture_array_type: Optional[bytes] = None
        if self.strict_data:
            if node_name == "Vertices" and parent_node_name == "Geometry":
                capture_array_type = b"d"
            elif (
                node_name == "PolygonVertexIndex"
                and parent_node_name == "Geometry"
            ):
                capture_array_type = b"i"
            elif (
                node_name == "Smoothing"
                and parent_node_name == "LayerElementSmoothing"
            ):
                capture_array_type = b"i"
            elif (
                self.capture_corner_normals
                and
                node_name == "Normals"
                and parent_node_name == "LayerElementNormal"
            ):
                capture_array_type = b"d"
            elif (
                self.capture_corner_normals
                and
                node_name == "NormalsIndex"
                and parent_node_name == "LayerElementNormal"
            ):
                capture_array_type = b"i"
        capture_array_values = not (
            self.strict_data
            and node_name == "Vertices"
            and parent_node_name == "Geometry"
        )
        properties = [
            self._read_property(
                capture_strings,
                capture_array_type,
                capture_array_values=capture_array_values,
            )
            for _ in range(property_count)
        ]
        if self.stream.tell() != properties_end:
            raise FbxFormatError(
                "Binary FBX node {!r} propertyListLen mismatch.".format(node_name)
            )

        geometry_id = inherited_geometry_id
        recorded_geometry_id = _record_object(
            self.collector, node_name, properties
        )
        if recorded_geometry_id is not None:
            geometry_id = recorded_geometry_id
        layer_kind = inherited_layer_kind
        typed_index = inherited_typed_index
        layer_index = inherited_layer_index
        current_reference_builder = layer_reference_builder

        if node_name == "LayerElementSmoothing":
            if geometry_id is None:
                raise FbxFormatError(
                    "LayerElementSmoothing appears outside a Geometry record."
                )
            if self.strict_data:
                if parent_node_name != "Geometry":
                    raise FbxFormatError(
                        "LayerElementSmoothing must be a direct Geometry child."
                    )
                typed_index = _property_int(
                    _single_property(
                        properties, "LayerElementSmoothing"
                    ),
                    "LayerElementSmoothing typed index",
                )
                self.collector.add_smoothing_layer(
                    geometry_id, typed_index
                )
                layer_kind = "LayerElementSmoothing"
            else:
                self.collector.mark_smoothing(geometry_id)
        elif (
            node_name == "LayerElementNormal"
            and self.strict_data
            and self.capture_corner_normals
        ):
            if geometry_id is None or parent_node_name != "Geometry":
                raise FbxFormatError(
                    "LayerElementNormal must be a direct Geometry child."
                )
            typed_index = _property_int(
                _single_property(properties, "LayerElementNormal"),
                "LayerElementNormal typed index",
            )
            self.collector.add_normal_layer(geometry_id, typed_index)
            layer_kind = "LayerElementNormal"
        elif (
            self.strict_data
            and node_name == "Vertices"
            and parent_node_name == "Geometry"
        ):
            if geometry_id is None:
                raise FbxFormatError("Vertices appears outside Geometry.")
            value = _single_property(properties, "Vertices")
            if not isinstance(value, _ArrayProperty) or value.type_code != "d":
                raise FbxFormatError(
                    "Vertices must be one validated float64 FBX array."
                )
            self.collector.set_vertex_component_count(
                geometry_id, value.element_count
            )
        elif (
            self.strict_data
            and node_name == "PolygonVertexIndex"
            and parent_node_name == "Geometry"
        ):
            if geometry_id is None:
                raise FbxFormatError(
                    "PolygonVertexIndex appears outside Geometry."
                )
            value = _single_property(properties, "PolygonVertexIndex")
            if not isinstance(value, _NumericArrayProperty):
                raise FbxFormatError(
                    "PolygonVertexIndex must be one captured int32 array."
                )
            self.collector.set_polygon_vertex_indices(
                geometry_id, value.values
            )
        elif (
            self.strict_data
            and node_name
            in ("MappingInformationType", "ReferenceInformationType")
            and parent_node_name
            in ("LayerElementSmoothing", "LayerElementNormal")
            and (
                parent_node_name == "LayerElementSmoothing"
                or self.capture_corner_normals
            )
        ):
            if (
                geometry_id is None
                or layer_kind != parent_node_name
                or typed_index is None
            ):
                raise FbxFormatError(
                    "{} appears without an active layer definition.".format(
                        node_name
                    )
                )
            value = _single_property(properties, node_name)
            if node_name == "MappingInformationType":
                self.collector.set_layer_mapping(
                    geometry_id, layer_kind, typed_index, value
                )
            else:
                self.collector.set_layer_reference_mode(
                    geometry_id, layer_kind, typed_index, value
                )
        elif (
            self.strict_data
            and node_name == "Smoothing"
            and parent_node_name == "LayerElementSmoothing"
        ):
            if geometry_id is None or typed_index is None:
                raise FbxFormatError(
                    "Smoothing appears without an active smoothing layer."
                )
            value = _single_property(properties, "Smoothing")
            if not isinstance(value, _NumericArrayProperty):
                raise FbxFormatError(
                    "Smoothing must be one captured int32 array."
                )
            self.collector.set_smoothing_masks(
                geometry_id, typed_index, value.values
            )
        elif (
            self.strict_data
            and self.capture_corner_normals
            and node_name == "Normals"
            and parent_node_name == "LayerElementNormal"
        ):
            if geometry_id is None or typed_index is None:
                raise FbxFormatError(
                    "Normals appears without an active normal layer."
                )
            value = _single_property(properties, "Normals")
            if not isinstance(value, _NumericArrayProperty):
                raise FbxFormatError(
                    "Normals must be one captured float64 array."
                )
            self.collector.set_normals(
                geometry_id, typed_index, value.values
            )
        elif (
            self.strict_data
            and self.capture_corner_normals
            and node_name == "NormalsIndex"
            and parent_node_name == "LayerElementNormal"
        ):
            if geometry_id is None or typed_index is None:
                raise FbxFormatError(
                    "NormalsIndex appears without an active normal layer."
                )
            value = _single_property(properties, "NormalsIndex")
            if not isinstance(value, _NumericArrayProperty):
                raise FbxFormatError(
                    "NormalsIndex must be one captured int32 array."
                )
            self.collector.set_normal_indices(
                geometry_id, typed_index, value.values
            )
        elif (
            self.strict_data
            and node_name == "Layer"
            and parent_node_name == "Geometry"
        ):
            if geometry_id is None:
                raise FbxFormatError("Layer appears outside Geometry.")
            layer_index = _property_int(
                _single_property(properties, "Layer"),
                "Layer index",
            )
            self.collector.add_layer(geometry_id, layer_index)
        elif (
            self.strict_data
            and node_name == "LayerElement"
            and parent_node_name == "Layer"
        ):
            if geometry_id is None or layer_index is None:
                raise FbxFormatError(
                    "LayerElement appears without an active Layer."
                )
            if properties:
                raise FbxFormatError(
                    "Layer/LayerElement must not contain properties."
                )
            current_reference_builder = _LayerElementReferenceBuilder()
        elif (
            self.strict_data
            and node_name in ("Type", "TypedIndex")
            and parent_node_name == "LayerElement"
        ):
            if layer_reference_builder is None:
                raise FbxFormatError(
                    "{} appears without an active LayerElement.".format(
                        node_name
                    )
                )
            if node_name == "Type":
                layer_reference_builder.type_records.append(
                    tuple(properties)
                )
            else:
                layer_reference_builder.typed_index_records.append(
                    tuple(properties)
                )

        child_in_connections = in_connections or node_name == "Connections"
        if node_name == "C" and child_in_connections:
            self.collector.add_connection(properties)

        child_count = 0
        saw_null_record = False
        while self.stream.tell() < end_offset:
            remaining = end_offset - self.stream.tell()
            if remaining < self.null_record_size:
                raise FbxFormatError(
                    "Binary FBX node {!r} ends with an incomplete child/null "
                    "record.".format(node_name)
                )
            child_start = self.stream.tell()
            if not self._parse_node(
                depth + 1,
                geometry_id,
                child_in_connections,
                parent_node_name=node_name,
                inherited_layer_kind=layer_kind,
                inherited_typed_index=typed_index,
                inherited_layer_index=layer_index,
                layer_reference_builder=current_reference_builder,
            ):
                saw_null_record = True
                if self.stream.tell() != end_offset:
                    raise FbxFormatError(
                        "Binary FBX node {!r} has data after its null child "
                        "record.".format(node_name)
                    )
                break
            child_count += 1
            if self.stream.tell() <= child_start:
                raise FbxFormatError(
                    "Binary FBX parser made no progress below node {!r}.".format(
                        node_name
                    )
                )
        if self.stream.tell() != end_offset:
            raise FbxFormatError(
                "Binary FBX node {!r} did not end at its endOffset.".format(
                    node_name
                )
            )
        if child_count and not saw_null_record:
            raise FbxFormatError(
                "Binary FBX node {!r} has children but no null terminator.".format(
                    node_name
                )
            )
        if (
            self.strict_data
            and node_name == "LayerElement"
            and parent_node_name == "Layer"
        ):
            assert current_reference_builder is not None
            resolved_reference = _finish_layer_element_reference(
                current_reference_builder,
                capture_corner_normals=self.capture_corner_normals,
            )
            if resolved_reference is not None:
                referenced_kind, referenced_typed_index = resolved_reference
                assert geometry_id is not None
                assert layer_index is not None
                self.collector.add_layer_reference(
                    geometry_id,
                    layer_index,
                    referenced_kind,
                    referenced_typed_index,
                )
        return True

    def parse(self) -> None:
        saw_root_null = False
        while self.stream.tell() < self.file_size:
            if self.file_size - self.stream.tell() < self.null_record_size:
                break
            if not self._parse_node(0, None, False):
                saw_root_null = True
                break
        if not saw_root_null:
            raise FbxFormatError(
                "Binary FBX does not contain the required root null record."
            )


@dataclass(frozen=True)
class _AsciiToken:
    kind: str
    value: str
    line: int
    column: int


def _ascii_tokens(text: str) -> Iterable[_AsciiToken]:
    index = 0
    line = 1
    column = 1
    length = len(text)

    while index < length:
        char = text[index]
        if char in " \t\f\v":
            index += 1
            column += 1
            continue
        if char == "\r" or char == "\n":
            token_line, token_column = line, column
            if char == "\r" and index + 1 < length and text[index + 1] == "\n":
                index += 2
            else:
                index += 1
            line += 1
            column = 1
            yield _AsciiToken("newline", "\n", token_line, token_column)
            continue
        if char == ";":
            while index < length and text[index] not in "\r\n":
                index += 1
                column += 1
            continue
        if char in "{}:,":
            yield _AsciiToken(char, char, line, column)
            index += 1
            column += 1
            continue
        if char == '"':
            start_line, start_column = line, column
            index += 1
            column += 1
            value: List[str] = []
            while index < length:
                current = text[index]
                if current == '"':
                    index += 1
                    column += 1
                    yield _AsciiToken(
                        "string", "".join(value), start_line, start_column
                    )
                    break
                if current in "\r\n":
                    raise FbxFormatError(
                        "ASCII FBX has an unterminated string at line {}, "
                        "column {}.".format(start_line, start_column)
                    )
                if current == "\\":
                    if index + 1 >= length:
                        raise FbxFormatError(
                            "ASCII FBX has a dangling string escape at line {}, "
                            "column {}.".format(start_line, start_column)
                        )
                    escaped = text[index + 1]
                    replacements = {
                        '"': '"',
                        "\\": "\\",
                        "n": "\n",
                        "r": "\r",
                        "t": "\t",
                    }
                    replacement = replacements.get(escaped)
                    if replacement is None:
                        value.append("\\")
                        value.append(escaped)
                    else:
                        value.append(replacement)
                    index += 2
                    column += 2
                    continue
                value.append(current)
                index += 1
                column += 1
            else:
                raise FbxFormatError(
                    "ASCII FBX has an unterminated string at line {}, column "
                    "{}.".format(start_line, start_column)
                )
            continue

        start = index
        start_column = column
        while (
            index < length
            and text[index] not in " \t\f\v\r\n{}:,;\""
        ):
            index += 1
            column += 1
        if start == index:
            raise FbxFormatError(
                "Unexpected ASCII FBX character at line {}, column {}.".format(
                    line, column
                )
            )
        yield _AsciiToken("atom", text[start:index], line, start_column)


@dataclass(frozen=True)
class _AsciiContext:
    node_name: str
    geometry_id: Optional[int]
    in_connections: bool


@dataclass
class _AsciiStrictContext:
    node_name: str
    geometry_id: Optional[int]
    in_connections: bool
    layer_kind: Optional[str] = None
    typed_index: Optional[int] = None
    layer_index: Optional[int] = None
    layer_reference_builder: Optional[_LayerElementReferenceBuilder] = None
    array_value_type: Optional[str] = None
    array_declared_count: Optional[int] = None
    array_store_values: bool = False
    array_values: List[object] = field(default_factory=list)
    array_values_seen: int = 0
    array_started: bool = False
    array_prefix_state: int = 0
    array_expect_value: bool = True


def _ascii_property(token: _AsciiToken) -> object:
    if token.kind == "string":
        return token.value
    if token.kind != "atom":
        raise FbxFormatError(
            "Unexpected token {!r} in ASCII FBX property list at line {}.".format(
                token.value, token.line
            )
        )
    value = token.value
    try:
        return int(value, 10)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def _ascii_header(
    tokens: Sequence[_AsciiToken],
    parse_properties: bool = True,
) -> Optional[Tuple[str, List[object]]]:
    if not tokens:
        return None
    if (
        len(tokens) < 2
        or tokens[0].kind != "atom"
        or tokens[1].kind != ":"
    ):
        return None
    node_name = tokens[0].value
    if not parse_properties:
        return node_name, []
    properties: List[object] = []
    expect_property = True
    for token in tokens[2:]:
        if token.kind == ",":
            if expect_property and properties:
                raise FbxFormatError(
                    "Empty ASCII FBX property in node {!r} at line {}.".format(
                        node_name, token.line
                    )
                )
            expect_property = True
            continue
        if token.kind in (":", "{", "}"):
            raise FbxFormatError(
                "Unexpected {!r} in ASCII FBX node {!r} at line {}.".format(
                    token.value, node_name, token.line
                )
            )
        if not expect_property:
            raise FbxFormatError(
                "Missing comma in ASCII FBX node {!r} at line {}.".format(
                    node_name, token.line
                )
            )
        properties.append(_ascii_property(token))
        expect_property = False
    if expect_property and properties:
        raise FbxFormatError(
            "Trailing comma in ASCII FBX node {!r} at line {}.".format(
                node_name, tokens[-1].line
            )
        )
    return node_name, properties


def _parse_ascii(text: str, collector: _MetadataCollector) -> None:
    stack: List[_AsciiContext] = []
    line_tokens: List[_AsciiToken] = []
    saw_structured_node = False
    skip_array_line_values = False

    def process_line(has_block: bool) -> Optional[_AsciiContext]:
        nonlocal saw_structured_node
        shallow = _ascii_header(line_tokens, parse_properties=False)
        inherited_connections = (
            stack[-1].in_connections if stack else False
        )
        parse_properties = bool(
            shallow
            and (
                shallow[0] in ("Geometry", "Model")
                or (shallow[0] == "C" and inherited_connections)
            )
        )
        parsed = _ascii_header(
            line_tokens, parse_properties=parse_properties
        )
        line_tokens.clear()
        if parsed is None:
            if has_block:
                raise FbxFormatError(
                    "ASCII FBX opening brace is not preceded by a node header."
                )
            return None
        node_name, properties = parsed
        saw_structured_node = True
        inherited_geometry_id = (
            stack[-1].geometry_id if stack else None
        )
        geometry_id = inherited_geometry_id
        recorded_geometry_id = _record_object(
            collector, node_name, properties
        )
        if recorded_geometry_id is not None:
            geometry_id = recorded_geometry_id
        if node_name == "LayerElementSmoothing":
            if geometry_id is None:
                raise FbxFormatError(
                    "LayerElementSmoothing appears outside a Geometry record."
                )
            collector.mark_smoothing(geometry_id)
        in_connections = inherited_connections or node_name == "Connections"
        if node_name == "C" and in_connections:
            collector.add_connection(properties)
        if node_name in ("Geometry", "Model", "Connections") and not has_block:
            raise FbxFormatError(
                "ASCII FBX {} record must own a brace-delimited block.".format(
                    node_name
                )
            )
        if has_block:
            return _AsciiContext(
                node_name=node_name,
                geometry_id=geometry_id,
                in_connections=in_connections,
            )
        return None

    for token in _ascii_tokens(text):
        if token.kind == "newline":
            if line_tokens:
                process_line(False)
            skip_array_line_values = False
            continue
        if token.kind == "{":
            context = process_line(True)
            skip_array_line_values = False
            if context is None:
                raise FbxFormatError(
                    "ASCII FBX opening brace at line {} has no context.".format(
                        token.line
                    )
                )
            if len(stack) >= _MAX_DEPTH:
                raise FbxFormatError(
                    "ASCII FBX node nesting exceeds {} levels.".format(_MAX_DEPTH)
                )
            stack.append(context)
            continue
        if token.kind == "}":
            if line_tokens:
                process_line(False)
            skip_array_line_values = False
            if not stack:
                raise FbxFormatError(
                    "Unmatched ASCII FBX closing brace at line {}.".format(
                        token.line
                    )
                )
            stack.pop()
            continue
        if skip_array_line_values:
            continue
        line_tokens.append(token)
        if (
            len(line_tokens) == 2
            and line_tokens[0].kind == "atom"
            and line_tokens[0].value == "a"
            and line_tokens[1].kind == ":"
        ):
            # ASCII FBX numeric arrays can put millions of values on one line.
            # Their contents are irrelevant metadata; retain only the ``a:``
            # header so memory use stays bounded by structural lines.
            skip_array_line_values = True

    if line_tokens:
        process_line(False)
    if stack:
        raise FbxFormatError(
            "ASCII FBX ended with {} unclosed brace block(s).".format(len(stack))
        )
    if not saw_structured_node:
        raise FbxFormatError("File is not a recognizable ASCII FBX document.")


def _ascii_array_count(
    properties: Sequence[object], description: str
) -> int:
    value = _single_property(properties, description)
    if (
        not isinstance(value, str)
        or not value.startswith("*")
        or not value[1:].isdigit()
    ):
        raise FbxFormatError(
            "{} must declare its element count as *N.".format(description)
        )
    count = int(value[1:], 10)
    if count > _MAX_PROPERTY_COUNT:
        raise FbxFormatError(
            "{} element count exceeds the safe limit.".format(description)
        )
    return count


def _parse_ascii_strict(
    text: str,
    collector: _MetadataCollector,
    *,
    capture_corner_normals: bool = False,
) -> None:
    """Parse topology/layer arrays from an ASCII FBX without token buffering.

    The file text itself is bounded before this function is called.  Numeric
    array values are consumed incrementally, and only arrays needed by the
    requested public API are retained.
    """

    stack: List[_AsciiStrictContext] = []
    line_tokens: List[_AsciiToken] = []
    saw_structured_node = False
    captured_decoded_bytes = 0

    def parent_context() -> Optional[_AsciiStrictContext]:
        return stack[-1] if stack else None

    def make_array_context(
        node_name: str,
        geometry_id: Optional[int],
        inherited_connections: bool,
        properties: Sequence[object],
        value_type: str,
        store_values: bool,
        layer_kind: Optional[str] = None,
        typed_index: Optional[int] = None,
    ) -> _AsciiStrictContext:
        nonlocal captured_decoded_bytes
        count = _ascii_array_count(
            properties, "ASCII FBX {} array".format(node_name)
        )
        if value_type == "i":
            if count > _MAX_CAPTURED_INT32_ELEMENTS:
                raise FbxFormatError(
                    "Strict ASCII int32 array exceeds the safe element limit."
                )
            decoded_bytes = count * 4
        elif value_type == "d":
            if count > _MAX_CAPTURED_FLOAT64_ELEMENTS:
                raise FbxFormatError(
                    "Strict ASCII float64 array exceeds the safe element limit."
                )
            decoded_bytes = count * 8
        elif value_type == "skip":
            decoded_bytes = 0
        else:
            raise FbxFormatError(
                "Unsupported strict ASCII array type {!r}.".format(value_type)
            )
        if store_values:
            if captured_decoded_bytes + decoded_bytes > _MAX_CAPTURED_TOTAL_BYTES:
                raise FbxFormatError(
                    "Strict ASCII numeric arrays exceed the total decoded "
                    "capture budget."
                )
            captured_decoded_bytes += decoded_bytes
        return _AsciiStrictContext(
            node_name=node_name,
            geometry_id=geometry_id,
            in_connections=inherited_connections,
            layer_kind=layer_kind,
            typed_index=typed_index,
            array_value_type=value_type,
            array_declared_count=count,
            array_store_values=store_values,
        )

    def array_context() -> Optional[_AsciiStrictContext]:
        current = parent_context()
        if current is None or current.array_value_type is None:
            return None
        return current

    def consume_array_token(
        context: _AsciiStrictContext, token: _AsciiToken
    ) -> None:
        if context.array_value_type == "skip":
            return
        if not context.array_started:
            if context.array_prefix_state == 0:
                if token.kind == "atom" and token.value == "a":
                    context.array_prefix_state = 1
                    return
                raise FbxFormatError(
                    "ASCII FBX {} array must begin with a direct a: record "
                    "(line {}).".format(context.node_name, token.line)
                )
            if token.kind != ":":
                raise FbxFormatError(
                    "ASCII FBX {} array a record is missing ':' at line "
                    "{}.".format(context.node_name, token.line)
                )
            context.array_started = True
            context.array_prefix_state = 2
            return

        if token.kind == ",":
            if context.array_expect_value:
                raise FbxFormatError(
                    "ASCII FBX {} array contains an empty value at line "
                    "{}.".format(context.node_name, token.line)
                )
            context.array_expect_value = True
            return
        if token.kind != "atom":
            raise FbxFormatError(
                "ASCII FBX {} array contains non-numeric data at line "
                "{}.".format(context.node_name, token.line)
            )
        if not context.array_expect_value:
            raise FbxFormatError(
                "ASCII FBX {} array is missing a comma at line {}.".format(
                    context.node_name, token.line
                )
            )
        if (
            context.array_declared_count is not None
            and context.array_values_seen >= context.array_declared_count
        ):
            raise FbxFormatError(
                "ASCII FBX {} array contains more values than declared.".format(
                    context.node_name
                )
            )
        if context.array_value_type == "i":
            try:
                value: object = int(token.value, 10)
            except ValueError as exc:
                raise FbxFormatError(
                    "ASCII FBX {} array requires signed int32 values.".format(
                        context.node_name
                    )
                ) from exc
            value = _require_signed_int32(
                value, "ASCII FBX {} array value".format(context.node_name)
            )
        else:
            try:
                value = float(token.value)
            except ValueError as exc:
                raise FbxFormatError(
                    "ASCII FBX {} array requires float64 values.".format(
                        context.node_name
                    )
                ) from exc
            if not math.isfinite(value):
                raise FbxFormatError(
                    "ASCII FBX {} array contains a non-finite value.".format(
                        context.node_name
                    )
                )
        if context.array_store_values:
            context.array_values.append(value)
        context.array_values_seen += 1
        context.array_expect_value = False

    def finish_array(context: _AsciiStrictContext) -> None:
        if context.array_value_type == "skip":
            return
        if not context.array_started:
            raise FbxFormatError(
                "ASCII FBX {} array has no a: value record.".format(
                    context.node_name
                )
            )
        if context.array_declared_count != context.array_values_seen:
            raise FbxFormatError(
                "ASCII FBX {} array declares {} values but contains {}.".format(
                    context.node_name,
                    context.array_declared_count,
                    context.array_values_seen,
                )
            )
        if context.geometry_id is None:
            raise FbxFormatError(
                "ASCII FBX {} array appears outside a Geometry.".format(
                    context.node_name
                )
            )
        if context.node_name == "Vertices":
            assert context.array_declared_count is not None
            collector.set_vertex_component_count(
                context.geometry_id, context.array_declared_count
            )
        elif context.node_name == "PolygonVertexIndex":
            collector.set_polygon_vertex_indices(
                context.geometry_id, context.array_values
            )
        elif context.node_name == "Smoothing":
            if context.typed_index is None:
                raise FbxFormatError(
                    "ASCII FBX Smoothing array has no owning typed index."
                )
            collector.set_smoothing_masks(
                context.geometry_id,
                context.typed_index,
                context.array_values,
            )
        elif context.node_name == "Normals":
            if context.typed_index is None:
                raise FbxFormatError(
                    "ASCII FBX Normals array has no owning typed index."
                )
            collector.set_normals(
                context.geometry_id,
                context.typed_index,
                context.array_values,
            )
        elif context.node_name == "NormalsIndex":
            if context.typed_index is None:
                raise FbxFormatError(
                    "ASCII FBX NormalsIndex array has no owning typed index."
                )
            collector.set_normal_indices(
                context.geometry_id,
                context.typed_index,
                context.array_values,
            )

    def finish_context(context: _AsciiStrictContext) -> None:
        if context.array_value_type is not None:
            finish_array(context)
        if (
            context.node_name == "LayerElement"
            and context.layer_reference_builder is not None
        ):
            builder = context.layer_reference_builder
            resolved_reference = _finish_layer_element_reference(
                builder,
                capture_corner_normals=capture_corner_normals,
            )
            if resolved_reference is not None:
                referenced_kind, referenced_typed_index = resolved_reference
                if context.geometry_id is None or context.layer_index is None:
                    raise FbxFormatError(
                        "ASCII FBX LayerElement has no owning Geometry/Layer."
                    )
                collector.add_layer_reference(
                    context.geometry_id,
                    context.layer_index,
                    referenced_kind,
                    referenced_typed_index,
                )

    def process_line(has_block: bool) -> Optional[_AsciiStrictContext]:
        nonlocal saw_structured_node
        shallow = _ascii_header(line_tokens, parse_properties=False)
        if shallow is None:
            if has_block:
                raise FbxFormatError(
                    "ASCII FBX opening brace is not preceded by a node header."
                )
            line_tokens.clear()
            return None
        node_name = shallow[0]
        parsed = _ascii_header(line_tokens, parse_properties=True)
        line_tokens.clear()
        assert parsed is not None
        _, properties = parsed
        saw_structured_node = True

        parent = parent_context()
        inherited_geometry_id = parent.geometry_id if parent else None
        inherited_connections = parent.in_connections if parent else False
        geometry_id = inherited_geometry_id
        recorded_geometry_id = _record_object(
            collector, node_name, properties
        )
        if recorded_geometry_id is not None:
            geometry_id = recorded_geometry_id
        in_connections = inherited_connections or node_name == "Connections"

        if node_name == "C" and inherited_connections:
            if has_block:
                raise FbxFormatError(
                    "ASCII FBX Connections/C record cannot own a block."
                )
            collector.add_connection(properties)

        if node_name in ("Geometry", "Model", "Connections") and not has_block:
            raise FbxFormatError(
                "ASCII FBX {} record must own a brace-delimited block.".format(
                    node_name
                )
            )

        layer_kind: Optional[str] = None
        typed_index: Optional[int] = None
        layer_index: Optional[int] = None
        reference_builder: Optional[_LayerElementReferenceBuilder] = None

        if node_name == "LayerElementSmoothing":
            if (
                parent is None
                or parent.node_name != "Geometry"
                or geometry_id is None
            ):
                raise FbxFormatError(
                    "LayerElementSmoothing must be a direct Geometry child."
                )
            if not has_block:
                raise FbxFormatError(
                    "LayerElementSmoothing must own a block."
                )
            typed_index = _property_int(
                _single_property(properties, "LayerElementSmoothing"),
                "LayerElementSmoothing typed index",
            )
            collector.add_smoothing_layer(geometry_id, typed_index)
            layer_kind = node_name
        elif node_name == "LayerElementNormal" and capture_corner_normals:
            if (
                parent is None
                or parent.node_name != "Geometry"
                or geometry_id is None
            ):
                raise FbxFormatError(
                    "LayerElementNormal must be a direct Geometry child."
                )
            if not has_block:
                raise FbxFormatError("LayerElementNormal must own a block.")
            typed_index = _property_int(
                _single_property(properties, "LayerElementNormal"),
                "LayerElementNormal typed index",
            )
            collector.add_normal_layer(geometry_id, typed_index)
            layer_kind = node_name
        elif (
            node_name == "Layer"
            and parent is not None
            and parent.node_name == "Geometry"
        ):
            if geometry_id is None or not has_block:
                raise FbxFormatError(
                    "ASCII FBX Layer must own a Geometry block."
                )
            layer_index = _property_int(
                _single_property(properties, "Layer"),
                "Layer index",
            )
            collector.add_layer(geometry_id, layer_index)
        elif (
            node_name == "LayerElement"
            and parent is not None
            and parent.node_name == "Layer"
        ):
            if properties or not has_block:
                raise FbxFormatError(
                    "ASCII FBX Layer/LayerElement must have no properties and "
                    "must own a block."
                )
            layer_index = parent.layer_index
            reference_builder = _LayerElementReferenceBuilder()

        if (
            parent is not None
            and parent.node_name in (
                "LayerElementSmoothing",
                "LayerElementNormal",
            )
            and parent.layer_kind is not None
            and node_name in (
                "MappingInformationType",
                "ReferenceInformationType",
            )
        ):
            if has_block or geometry_id is None or parent.typed_index is None:
                raise FbxFormatError(
                    "ASCII FBX {} must be a scalar layer child.".format(
                        node_name
                    )
                )
            value = _single_property(properties, node_name)
            if node_name == "MappingInformationType":
                collector.set_layer_mapping(
                    geometry_id,
                    parent.layer_kind,
                    parent.typed_index,
                    value,
                )
            else:
                collector.set_layer_reference_mode(
                    geometry_id,
                    parent.layer_kind,
                    parent.typed_index,
                    value,
                )

        if (
            parent is not None
            and parent.node_name == "LayerElement"
            and parent.layer_reference_builder is not None
            and node_name in ("Type", "TypedIndex")
        ):
            if has_block:
                raise FbxFormatError(
                    "ASCII FBX LayerElement/{} cannot own a block.".format(
                        node_name
                    )
                )
            builder = parent.layer_reference_builder
            if node_name == "Type":
                builder.type_records.append(tuple(properties))
            else:
                builder.typed_index_records.append(tuple(properties))

        if has_block and parent is not None:
            if node_name == "Vertices" and parent.node_name == "Geometry":
                return make_array_context(
                    node_name,
                    geometry_id,
                    in_connections,
                    properties,
                    "d",
                    False,
                )
            if (
                node_name == "PolygonVertexIndex"
                and parent.node_name == "Geometry"
            ):
                return make_array_context(
                    node_name,
                    geometry_id,
                    in_connections,
                    properties,
                    "i",
                    True,
                )
            if (
                node_name == "Smoothing"
                and parent.node_name == "LayerElementSmoothing"
                and parent.layer_kind == "LayerElementSmoothing"
            ):
                return make_array_context(
                    node_name,
                    geometry_id,
                    in_connections,
                    properties,
                    "i",
                    True,
                    parent.layer_kind,
                    parent.typed_index,
                )
            if (
                capture_corner_normals
                and node_name in ("Normals", "NormalsIndex")
                and parent.node_name == "LayerElementNormal"
                and parent.layer_kind == "LayerElementNormal"
            ):
                return make_array_context(
                    node_name,
                    geometry_id,
                    in_connections,
                    properties,
                    "d" if node_name == "Normals" else "i",
                    True,
                    parent.layer_kind,
                    parent.typed_index,
                )

        # Known but unrequested normal arrays, and all unrelated FBX arrays,
        # are consumed without retaining their potentially huge value lists.
        if (
            has_block
            and len(properties) == 1
            and isinstance(properties[0], str)
            and properties[0].startswith("*")
            and properties[0][1:].isdigit()
        ):
            return _AsciiStrictContext(
                node_name=node_name,
                geometry_id=geometry_id,
                in_connections=in_connections,
                array_value_type="skip",
            )

        if node_name in (
            "Vertices",
            "PolygonVertexIndex",
            "Smoothing",
            "Normals",
            "NormalsIndex",
        ) and not has_block:
            raise FbxFormatError(
                "ASCII FBX {} array must own a block.".format(node_name)
            )

        if not has_block:
            return None
        return _AsciiStrictContext(
            node_name=node_name,
            geometry_id=geometry_id,
            in_connections=in_connections,
            layer_kind=layer_kind,
            typed_index=typed_index,
            layer_index=layer_index,
            layer_reference_builder=reference_builder,
        )

    for token in _ascii_tokens(text):
        active_array = array_context()
        if active_array is not None:
            if token.kind == "newline":
                continue
            if token.kind == "{":
                raise FbxFormatError(
                    "ASCII FBX array cannot contain a nested block."
                )
            if token.kind == "}":
                if not stack:
                    raise FbxFormatError(
                        "Unmatched ASCII FBX closing brace at line {}.".format(
                            token.line
                        )
                    )
                finish_context(stack.pop())
                continue
            consume_array_token(active_array, token)
            continue
        if token.kind == "newline":
            if line_tokens:
                process_line(False)
            continue
        if token.kind == "{":
            context = process_line(True)
            if context is None:
                raise FbxFormatError(
                    "ASCII FBX opening brace at line {} has no context.".format(
                        token.line
                    )
                )
            if len(stack) >= _MAX_DEPTH:
                raise FbxFormatError(
                    "ASCII FBX node nesting exceeds {} levels.".format(_MAX_DEPTH)
                )
            stack.append(context)
            continue
        if token.kind == "}":
            if line_tokens:
                process_line(False)
            if not stack:
                raise FbxFormatError(
                    "Unmatched ASCII FBX closing brace at line {}.".format(
                        token.line
                    )
                )
            finish_context(stack.pop())
            continue
        line_tokens.append(token)

    if line_tokens:
        process_line(False)
    if stack:
        raise FbxFormatError(
            "ASCII FBX ended with {} unclosed brace block(s).".format(len(stack))
        )
    if not saw_structured_node:
        raise FbxFormatError("File is not a recognizable ASCII FBX document.")


def _read_binary(
    stream: BinaryIO,
    file_size: int,
    collector: _MetadataCollector,
    strict_data: bool = False,
    capture_corner_normals: bool = False,
) -> None:
    magic = stream.read(len(_BINARY_MAGIC))
    if magic != _BINARY_MAGIC:
        raise FbxFormatError("Binary FBX magic header is invalid.")
    version_bytes = stream.read(4)
    if len(version_bytes) != 4:
        raise FbxFormatError("Binary FBX version field is truncated.")
    version = struct.unpack("<I", version_bytes)[0]
    if version < 7000 or version >= 8000:
        raise FbxFormatError(
            "Unsupported binary FBX version {}; only FBX 7.x is supported.".format(
                version
            )
        )
    _BinaryParser(
        stream,
        file_size,
        version,
        collector,
        strict_data=strict_data,
        capture_corner_normals=capture_corner_normals,
    ).parse()


def _read_metadata_collector(
    path: object,
    *,
    strict_data: bool = False,
    capture_corner_normals: bool = False,
) -> _MetadataCollector:
    try:
        file_path = Path(path)
    except (TypeError, ValueError, OSError) as exc:
        raise FbxMetadataIOError("Invalid FBX path {!r}.".format(path)) from exc

    collector = _MetadataCollector()
    try:
        with file_path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            file_size = stream.tell()
            stream.seek(0)
            if file_size == 0:
                raise FbxFormatError("FBX file is empty.")
            if strict_data and file_size > _MAX_ASCII_STRICT_BYTES:
                # Binary files are streamed and have their own per-array/global
                # capture limits.  This provisional check is revisited after
                # inspecting the magic so large binary files remain supported.
                prefix = stream.read(len(_BINARY_MAGIC))
                stream.seek(0)
                if prefix != _BINARY_MAGIC:
                    raise FbxFormatError(
                        "ASCII FBX exceeds the strict {} byte read limit.".format(
                            _MAX_ASCII_STRICT_BYTES
                        )
                    )
            prefix = stream.read(len(_BINARY_MAGIC))
            stream.seek(0)
            if prefix == _BINARY_MAGIC:
                _read_binary(
                    stream,
                    file_size,
                    collector,
                    strict_data=strict_data,
                    capture_corner_normals=capture_corner_normals,
                )
            else:
                wrapper = io.TextIOWrapper(
                    stream,
                    encoding="utf-8-sig",
                    errors="strict",
                    newline="",
                )
                try:
                    text = wrapper.read()
                except UnicodeDecodeError as exc:
                    raise FbxFormatError(
                        "ASCII FBX is not valid UTF-8."
                    ) from exc
                finally:
                    # The outer context manager owns the binary stream.
                    wrapper.detach()
                if "\x00" in text:
                    raise FbxFormatError(
                        "File is neither binary FBX nor valid NUL-free ASCII FBX."
                    )
                if strict_data:
                    _parse_ascii_strict(
                        text,
                        collector,
                        capture_corner_normals=capture_corner_normals,
                    )
                else:
                    _parse_ascii(text, collector)
    except FBXMetadataError:
        raise
    except OSError as exc:
        raise FbxMetadataIOError(
            "Could not read FBX file {!s}: {}".format(file_path, exc)
        ) from exc

    return collector


def read_native_smoothing_by_model(path: object) -> Dict[str, bool]:
    """Return ``{visible_mesh_model_name: has_native_smoothing}``.

    ``True`` means the connected Mesh/Geometry contains at least one native
    ``LayerElementSmoothing`` node.  ``False`` means no such native node exists,
    so a caller may choose a separately validated corner-normal/soft-edge
    inference path.

    The function never writes the FBX.  It raises :class:`FBXMetadataError`
    subclasses for I/O, malformed data, duplicates, or ambiguous mappings.
    """

    return _read_metadata_collector(path).result()


def read_mesh_smoothing_data(
    path: object,
) -> Dict[str, FbxMeshSmoothingData]:
    """Read exact FBX polygon faces and unique native smoothing masks.

    This strict API decodes ``PolygonVertexIndex`` into zero-based faces in
    file order.  If a native smoothing layer exists, it must be uniquely
    referenced by a unique ``Layer`` and use ``ByPolygon`` + ``Direct`` with
    exactly one signed int32 mask per face.  A mesh with no native smoothing
    layer is valid and returns ``masks=None``.
    """

    return _read_metadata_collector(
        path,
        strict_data=True,
    ).smoothing_data_result(include_corner_normals=False)


def read_mesh_smoothing_and_normals(
    path: object,
) -> Dict[str, FbxMeshSmoothingData]:
    """Read strict smoothing data plus exact per-face-corner normal vectors.

    The active normal layer must be uniquely referenced, mapped
    ``ByPolygonVertex``, and use either ``Direct`` or ``IndexToDirect``.
    """

    return _read_metadata_collector(
        path,
        strict_data=True,
        capture_corner_normals=True,
    ).smoothing_data_result(include_corner_normals=True)


def _file_identity(file_path: Path) -> Tuple[int, int]:
    try:
        status = file_path.stat()
    except OSError as exc:
        raise FbxMetadataIOError(
            "Could not stat FBX input {!s}.".format(file_path)
        ) from exc
    return int(status.st_size), int(status.st_mtime_ns)


def _stream_file_sha256(file_path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with file_path.open("rb") as stream:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as exc:
        raise FbxMetadataIOError(
            "Could not hash FBX input {!s}.".format(file_path)
        ) from exc
    return digest.hexdigest()


def _topology_sha256(
    faces: Sequence[Sequence[int]],
) -> Tuple[str, int]:
    digest = hashlib.sha256()
    corner_count = 0
    for face_index, face in enumerate(faces):
        degree = len(face)
        if degree < 0 or degree > 0xFFFFFFFF:
            raise FbxFormatError(
                "Face {} degree is outside uint32 range.".format(face_index)
            )
        digest.update(struct.pack("<I", degree))
        corner_count += degree
        for offset in range(0, degree, 4096):
            chunk = face[offset : offset + 4096]
            for vertex_index in chunk:
                if (
                    isinstance(vertex_index, bool)
                    or not isinstance(vertex_index, int)
                    or vertex_index < 0
                    or vertex_index > 0xFFFFFFFF
                ):
                    raise FbxFormatError(
                        "Face {} contains a vertex ID outside uint32 "
                        "range.".format(face_index)
                    )
            if chunk:
                digest.update(
                    struct.pack(
                        "<{}I".format(len(chunk)),
                        *chunk,
                    )
                )
    return digest.hexdigest(), corner_count


def _load_local_smoothing_module() -> object:
    module_path = Path(__file__).resolve().with_name("f2m_smoothing.py")
    module_name = "_fbx_to_3dsmax_resolver_smoothing"
    existing = sys.modules.get(module_name)
    if existing is not None:
        existing_path = Path(
            getattr(existing, "__file__", "")
        ).resolve()
        if existing_path != module_path:
            raise FbxMetadataIOError(
                "Cached smoothing module path does not match the project file."
            )
        return existing
    spec = importlib.util.spec_from_file_location(
        module_name, str(module_path)
    )
    if spec is None or spec.loader is None:
        raise FbxMetadataIOError(
            "Could not create an absolute-path smoothing module spec."
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    loaded_path = Path(getattr(module, "__file__", "")).resolve()
    if loaded_path != module_path:
        sys.modules.pop(module_name, None)
        raise FbxMetadataIOError(
            "Loaded smoothing module path does not match the project file."
        )
    return module


def _native_solver_stats(masks: Sequence[int]) -> Dict[str, object]:
    used_mask = 0
    for mask in masks:
        used_mask |= mask & 0xFFFFFFFF
    return {
        "strategy": "native",
        "group_count": bin(used_mask).count("1"),
        "soft_edge_count": None,
        "hard_edge_count": None,
        "requirement_count": None,
    }


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def build_strict_resolver_payload(path: object) -> Dict[str, object]:
    """Build the bounded subprocess resolver result for one stable FBX file."""

    try:
        file_path = Path(path).resolve(strict=True)
    except (TypeError, ValueError, OSError) as exc:
        raise FbxMetadataIOError(
            "Invalid strict resolver FBX path {!r}.".format(path)
        ) from exc

    identity_before = _file_identity(file_path)
    input_sha256 = _stream_file_sha256(file_path)
    if _file_identity(file_path) != identity_before:
        raise FbxMetadataIOError(
            "FBX input changed while its initial hash was read."
        )

    mesh_data = read_mesh_smoothing_and_normals(file_path)
    if _file_identity(file_path) != identity_before:
        raise FbxMetadataIOError(
            "FBX input changed while metadata was parsed."
        )
    final_sha256 = _stream_file_sha256(file_path)
    if (
        final_sha256 != input_sha256
        or _file_identity(file_path) != identity_before
    ):
        raise FbxMetadataIOError(
            "FBX input changed during strict resolver execution."
        )

    metadata_module_path = Path(__file__).resolve()
    smoothing_module = _load_local_smoothing_module()
    smoothing_module_path = Path(
        getattr(smoothing_module, "__file__", "")
    ).resolve()
    mesh_payloads: List[Dict[str, object]] = []
    for name, item in mesh_data.items():
        topology_digest, corner_count = _topology_sha256(item.faces)
        if item.masks is not None:
            signed_masks = item.masks
            native = True
            method = "native_by_polygon_direct"
            solver_stats = _native_solver_stats(signed_masks)
        else:
            if item.corner_normals is None:
                raise FbxFormatError(
                    "Mesh {!r} has neither native smoothing masks nor exact "
                    "face-corner normals.".format(name)
                )
            assignment = smoothing_module.compute_smoothing_assignment(
                item.faces,
                corner_normals=item.corner_normals,
                normal_angle_tolerance_degrees=(
                    RESOLVER_NORMAL_TOLERANCE_DEGREES
                ),
                max_groups=RESOLVER_MAX_SMOOTHING_GROUPS,
            )
            signed_masks = assignment.maxscript_masks
            native = False
            method = "computed_from_corner_normals"
            validation = assignment.validation
            solver_stats = {
                "strategy": assignment.strategy,
                "group_count": assignment.group_count,
                "soft_edge_count": validation.soft_edge_count,
                "hard_edge_count": validation.hard_edge_count,
                "requirement_count": len(assignment.requirement_colors),
            }
        if len(signed_masks) != len(item.faces):
            raise FbxFormatError(
                "Mesh {!r} resolver mask count does not match face count.".format(
                    name
                )
            )
        normalized_masks = tuple(
            _require_signed_int32(mask, "Resolver smoothing mask")
            for mask in signed_masks
        )
        mesh_payloads.append(
            {
                "name": name,
                "face_count": len(item.faces),
                "corner_count": corner_count,
                "topology_sha256": topology_digest,
                "masks": normalized_masks,
                "native": native,
                "method": method,
                "solver_stats": solver_stats,
            }
        )

    payload: Dict[str, object] = {
        "schema": RESOLVER_SCHEMA,
        "schema_version": RESOLVER_SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "interpreter_major": int(sys.version_info.major),
        "interpreter_minor": int(sys.version_info.minor),
        "interpreter_bits": struct.calcsize("P") * 8,
        "interpreter_is_64bit": struct.calcsize("P") == 8,
        "metadata_module_file": str(metadata_module_path),
        "metadata_source_sha256": _stream_file_sha256(
            metadata_module_path
        ),
        "smoothing_module_file": str(smoothing_module_path),
        "smoothing_source_sha256": _stream_file_sha256(
            smoothing_module_path
        ),
        "input_size": identity_before[0],
        "input_mtime_ns": identity_before[1],
        "input_sha256": input_sha256,
        "input_hash_algorithm": "sha256",
        "topology_hash_algorithm": "sha256",
        "topology_encoding": RESOLVER_TOPOLOGY_ENCODING,
        "normal_angle_tolerance_degrees": (
            RESOLVER_NORMAL_TOLERANCE_DEGREES
        ),
        "max_smoothing_groups": RESOLVER_MAX_SMOOTHING_GROUPS,
        "mesh_count": len(mesh_payloads),
        "meshes": mesh_payloads,
        "response_hash_algorithm": "sha256",
        "response_hash_encoding": (
            "canonical UTF-8 JSON with sorted keys and compact separators"
        ),
        "response_hash_scope": "all members except response_sha256",
    }
    payload["response_sha256"] = hashlib.sha256(
        _canonical_json_bytes(payload)
    ).hexdigest()
    return payload


def write_strict_resolver_json(
    input_path: object, output_path: object
) -> None:
    """Atomically replace ``output_path`` with one strict resolver JSON."""

    try:
        source = Path(input_path).resolve(strict=True)
        destination = Path(output_path).resolve(strict=False)
    except (TypeError, ValueError, OSError) as exc:
        raise FbxMetadataIOError("Invalid resolver input/output path.") from exc
    if os.path.normcase(str(source)) == os.path.normcase(str(destination)):
        raise FbxMetadataIOError(
            "Resolver output path must differ from the FBX input path."
        )
    if destination.exists():
        try:
            if os.path.samefile(str(source), str(destination)):
                raise FbxMetadataIOError(
                    "Resolver output aliases the FBX input file."
                )
        except OSError as exc:
            raise FbxMetadataIOError(
                "Could not validate resolver output identity."
            ) from exc
    if not destination.parent.is_dir():
        raise FbxMetadataIOError(
            "Resolver output parent directory does not exist."
        )

    payload = build_strict_resolver_payload(source)
    descriptor: Optional[int] = None
    temporary_path: Optional[Path] = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".f2m-resolver-",
            suffix=".tmp",
            dir=str(destination.parent),
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
            errors="strict",
            newline="\n",
        ) as stream:
            descriptor = None
            json.dump(
                payload,
                stream,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary_path), str(destination))
        temporary_path = None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def _strict_resolver_cli(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve strict FBX topology and smoothing metadata."
    )
    parser.add_argument("--input", required=True, help="Input FBX path")
    parser.add_argument(
        "--output", required=True, help="Atomic resolver JSON output path"
    )
    arguments = parser.parse_args(argv)
    try:
        write_strict_resolver_json(arguments.input, arguments.output)
    except Exception as exc:
        sys.stderr.write(
            "strict resolver failed: {}: {}\n".format(
                type(exc).__name__, str(exc)
            )
        )
        return 1
    return 0


def inspect_fbx_smoothing(path: object) -> Dict[str, bool]:
    """Compatibility-friendly public alias for metadata inspection."""

    return read_native_smoothing_by_model(path)


def inspect_smoothing_layers(path: str) -> Dict[str, bool]:
    """Return native smoothing-layer presence by visible Mesh/Model name.

    This is the canonical public API.  Every parsing, duplicate, and mapping
    failure derives from :class:`FBXMetadataError`.
    """

    return read_native_smoothing_by_model(path)


# Earlier development callers used conventional mixed-case spelling.  Keep it
# as an exception alias while exposing FBXMetadataError as the canonical API.
FbxMetadataError = FBXMetadataError


__all__ = [
    "TOOL_VERSION",
    "FBXMetadataError",
    "FbxMetadataError",
    "FbxMetadataIOError",
    "FbxFormatError",
    "FbxAmbiguityError",
    "FbxMeshSmoothingData",
    "read_native_smoothing_by_model",
    "read_mesh_smoothing_data",
    "read_mesh_smoothing_and_normals",
    "RESOLVER_SCHEMA",
    "RESOLVER_SCHEMA_VERSION",
    "RESOLVER_NORMAL_TOLERANCE_DEGREES",
    "RESOLVER_MAX_SMOOTHING_GROUPS",
    "RESOLVER_TOPOLOGY_ENCODING",
    "build_strict_resolver_payload",
    "write_strict_resolver_json",
    "inspect_fbx_smoothing",
    "inspect_smoothing_layers",
]


if __name__ == "__main__":
    raise SystemExit(_strict_resolver_cli())
