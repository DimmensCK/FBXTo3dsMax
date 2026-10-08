# -*- coding: utf-8 -*-
"""Original test data must be procedural and stay outside the public repository."""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from f2m_fbx_metadata import read_mesh_smoothing_and_normals
from f2m_test_fixtures import FACES, MESH_NAME, NATIVE_MASKS, fixture_bytes, get_fixture_paths


ROOT = Path(__file__).resolve().parents[1]

class FixturePrivacyTests(unittest.TestCase):
    def test_repository_has_no_bundled_private_fbx_assets(self) -> None:
        self.assertEqual(list((ROOT / "tests").rglob("*.fbx")), [])
        self.assertNotIn("tests\\fixtures\\", (ROOT / "Contents/FBXTo3dsMax.files").read_text("utf-8-sig"))

    def test_generated_bytes_are_original_numeric_data_without_external_paths(self) -> None:
        for native in (False, True):
            payload = fixture_bytes(native)
            self.assertEqual(payload, fixture_bytes(native))
            self.assertIn(b"FBXTo3dsMax procedural fixture generator", payload)
            self.assertIn(b"LayerElementUV", payload)
            for marker in (b"avatar", b"c:\\", b"c:/", b"e:\\", b"e:/",
                           b"texture:", b"filename:", b"relativefilename:"):
                self.assertNotIn(marker, payload.lower())

    def test_generated_paths_are_external_and_have_real_corner_residual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict("os.environ", {"LOCALAPPDATA": directory}):
                paths = get_fixture_paths()
                self.assertIsNone(paths["skin"])
                for key in ("topology", "native_smoothing"):
                    path = Path(paths[key])
                    self.assertTrue(path.is_absolute())
                    self.assertIn(Path(directory), path.parents)
                    self.assertNotIn(ROOT, path.parents)
                    native = key == "native_smoothing"
                    self.assertEqual(path.read_bytes(), fixture_bytes(native))
                    mesh = read_mesh_smoothing_and_normals(path)[MESH_NAME]
                    self.assertEqual(mesh.faces, FACES)
                    self.assertEqual(mesh.masks, NATIVE_MASKS if native else None)
                    corners = [normal for face in mesh.corner_normals for normal in face]
                    self.assertEqual(len(corners), 6)
                    self.assertGreater(math.degrees(math.acos(corners[1][2])), 0.1)
                    for index in (0, 2, 3, 4):
                        self.assertEqual(corners[index], (0.0, 0.0, 1.0))
                self.assertEqual(get_fixture_paths(), paths)


if __name__ == "__main__":
    unittest.main()
