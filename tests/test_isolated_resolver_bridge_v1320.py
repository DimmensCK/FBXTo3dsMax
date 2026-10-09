# -*- coding: utf-8 -*-
"""Regression contracts for the out-of-process combo SG resolver."""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import os
import sys
import unittest
from pathlib import Path

# Resolve runtime modules from the source distribution without a global PYTHONPATH.
import sys as _f2m_test_sys
from pathlib import Path as _F2MTestPath
_f2m_test_root = _F2MTestPath(__file__).resolve().parents[1]
_f2m_test_sys.path.insert(0, str(_f2m_test_root / "contents" if (_f2m_test_root / "contents").is_dir() else _f2m_test_root))

from f2m_test_fixtures import CORNER_COUNT, FACE_COUNT, get_fixture_paths


ROOT = Path(__file__).resolve().parents[1]


def _load(filename: str, module_name: str):
    path = ROOT / "contents" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


topology = _load(
    "f2m_topology_transfer.py",
    "_f2m_test_isolated_resolver_topology",
)
metadata = _load(
    "f2m_fbx_metadata.py",
    "_f2m_test_isolated_resolver_metadata",
)


class IsolatedResolverBridgeV1320Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = Path(get_fixture_paths()["topology"])
        self.metadata_path = ROOT / "contents" / "f2m_fbx_metadata.py"
        self.smoothing_path = ROOT / "contents" / "f2m_smoothing.py"

    def test_combo_bridge_never_imports_heavy_parser_in_host_process(self):
        bridge = inspect.getsource(topology._inspect_smoothing_and_normal_data)
        resolver = inspect.getsource(
            topology._resolve_smoothing_masks_from_single_exact_import
        )
        for required in (
            "subprocess.run(",
            '"-I"',
            '"-S"',
            '"-B"',
            "stdout=subprocess.DEVNULL",
            "shell=False",
            "_validated_resolver_payload(",
        ):
            self.assertIn(required, bridge)
        for forbidden in (
            "_load_local_runtime_module(",
            "read_mesh_smoothing_and_normals",
            "compute_smoothing_assignment(",
            "faces_by_name",
            "_base_topology_faces(",
            "_imported_topology_sha256(",
        ):
            self.assertNotIn(forbidden, bridge)
            self.assertNotIn(forbidden, resolver)
        topology_map = inspect.getsource(topology.build_topology_map)
        self.assertEqual(
            topology_map.count("_base_topology_faces(fbx_target)"),
            1,
        )
        self.assertIn("_imported_topology_sha256(", topology_map)
        self.assertIn("fbx_faces", topology_map)
        self.assertIn("actual_digest != str(expected_digest)", topology_map)

    def test_bridge_consumes_real_worker_response_and_cleans_temp(self):
        options = topology.TransferOptions(
            fbx_path=str(self.fixture),
            transfer_normals=True,
            transfer_smoothing_groups=True,
            show_ui=False,
        )
        context = topology.TransferContext(options, topology.TransferLog())
        topology._inspect_smoothing_and_normal_data(context)
        self.assertEqual(len(context.fbx_mesh_data_by_name), 1)
        mesh = next(iter(context.fbx_mesh_data_by_name.values()))
        self.assertEqual(mesh.face_count, FACE_COUNT)
        self.assertEqual(mesh.corner_count, CORNER_COUNT)
        self.assertEqual(len(mesh.masks), FACE_COUNT)
        self.assertFalse(mesh.native)
        self.assertEqual(mesh.method, "computed_from_corner_normals")
        self.assertRegex(context.resolver_input_sha256, r"^[0-9a-f]{64}$")

    def test_imported_topology_digest_matches_worker_contract(self):
        payload = metadata.build_strict_resolver_payload(self.fixture)
        strict = metadata.read_mesh_smoothing_and_normals(self.fixture)
        parsed = next(iter(strict.values()))
        imported_style_faces = [
            [vertex_id + 1 for vertex_id in face]
            for face in parsed.faces
        ]
        digest, corner_count = topology._imported_topology_sha256(
            imported_style_faces
        )
        mesh_payload = payload["meshes"][0]
        self.assertEqual(digest, mesh_payload["topology_sha256"])
        self.assertEqual(corner_count, mesh_payload["corner_count"])

    def test_tampered_response_hash_is_rejected_before_use(self):
        payload = metadata.build_strict_resolver_payload(self.fixture)
        payload["mesh_count"] = 999
        with self.assertRaisesRegex(RuntimeError, "内嵌 SHA-256"):
            topology._validated_resolver_payload(
                payload,
                fbx_path=str(self.fixture),
                metadata_path=str(self.metadata_path),
                smoothing_path=str(self.smoothing_path),
                metadata_sha256=hashlib.sha256(
                    self.metadata_path.read_bytes()
                ).hexdigest(),
                smoothing_sha256=hashlib.sha256(
                    self.smoothing_path.read_bytes()
                ).hexdigest(),
            )

    def test_duplicate_json_members_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "重复键"):
            topology._resolver_reject_duplicate_json_pairs(
                [("schema", "first"), ("schema", "second")]
            )

    def test_context_release_drops_resolver_payload(self):
        options = topology.TransferOptions(fbx_path=str(self.fixture))
        context = topology.TransferContext(options, topology.TransferLog())
        context.fbx_mesh_data_by_name["mesh"] = object()
        context.initial_smoothing_masks_by_handle[1] = [1]
        context.resolver_topology_by_name["mesh"] = (1, 3, "a" * 64)
        context.resolver_input_size = 1
        context.resolver_input_mtime_ns = 2
        context.resolver_input_sha256 = "a" * 64
        topology._release_context_node_references(context)
        self.assertEqual(context.fbx_mesh_data_by_name, {})
        self.assertEqual(context.initial_smoothing_masks_by_handle, {})
        self.assertEqual(context.resolver_topology_by_name, {})
        self.assertIsNone(context.resolver_input_size)
        self.assertIsNone(context.resolver_input_mtime_ns)
        self.assertEqual(context.resolver_input_sha256, "")


if __name__ == "__main__":
    unittest.main()
