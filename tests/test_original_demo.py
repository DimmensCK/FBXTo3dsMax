"""Check the published exercise through its real FBX consumer and safety entry."""
import copy
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


DEMO = load_file("_f2m_original_demo_test", ROOT / "docs/examples/create_demo_scene.py")
METADATA = load_file("_f2m_original_demo_metadata", ROOT / "contents/f2m_fbx_metadata.py")


class OriginalDemoTests(unittest.TestCase):
    def test_authored_fbx_is_accepted_by_real_metadata_consumer(self):
        local = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
        parent = local / "FBXTo3dsMax/Validation"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="original_demo_", dir=parent) as folder:
            path = Path(folder) / "edited.fbx"
            path.write_bytes(DEMO.fbx_bytes())
            parsed = METADATA.read_mesh_smoothing_and_normals(path)
        self.assertEqual(set(parsed), {"F2M_Demo_Canopy"})
        geometry = parsed["F2M_Demo_Canopy"]
        self.assertEqual(len(geometry.faces), 144)
        self.assertEqual(set(index for face in geometry.faces for index in face), set(range(91)))
        self.assertTrue(all(len(face) == 3 for face in geometry.faces))
        self.assertEqual(geometry.masks, (1,) * 144)
        self.assertTrue(all(abs(sum(c * c for c in normal) - 1) < 1e-12
                            for face in geometry.corner_normals for normal in face))

    @staticmethod
    def _assert_sdk_observed_ascii_block_layout(payload):
        # Conservative contract for this generator's actual SDK-read layout,
        # not a general FBX grammar or a substitute for real Max import.
        depth = 0
        for number, line in enumerate(payload.decode("ascii").splitlines(), 1):
            code, quoted, escaped = [], False, False
            for char in line:
                if quoted:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == '"':
                        quoted = False
                elif char == '"':
                    quoted = True
                elif char == ";":
                    break
                else:
                    code.append(char)
            if quoted:
                raise AssertionError("Unterminated ASCII quote at line {}".format(number))
            text = "".join(code).strip()
            if "{" in text:
                if text.count("{") != 1 or not text.endswith("{") or "}" in text or ":" not in text:
                    raise AssertionError("Multiline block layout required at line {}".format(number))
                depth += 1
            elif "}" in text:
                if text != "}" or depth <= 0:
                    raise AssertionError("Multiline block layout required at line {}".format(number))
                depth -= 1
        if depth:
            raise AssertionError("Unclosed ASCII block")

    def test_authored_ascii_uses_sdk_observed_multiline_blocks(self):
        payload = DEMO.fbx_bytes()
        self._assert_sdk_observed_ascii_block_layout(payload)
        # Quoted braces/semicolons and comments do not change block structure.
        quoted = payload.replace(
            b'Creator: "FBXTo3dsMax original canopy exercise"',
            b'Creator: "literal { } ; \\" text" ; ignored { }')
        self.assertNotEqual(quoted, payload)
        self._assert_sdk_observed_ascii_block_layout(quoted)

    def test_inline_block_regressions_are_refused_by_layout_contract(self):
        payload = DEMO.fbx_bytes()
        # Each counterexample preserves data and changes only block whitespace.
        cases = (
            (b'ObjectType: "Geometry" {\n        Count: 1\n    }',
             b'ObjectType: "Geometry" { Count: 1 }'),
            (b'LayerElement: {\n                Type: "LayerElementNormal"\n                TypedIndex: 0\n            }',
             b'LayerElement: { Type: "LayerElementNormal"\n                TypedIndex: 0 }'),
            (b'References: {\n}', b'References: { }'),
            (b'Takes: {\n    Current: ""\n}', b'Takes: { Current: "" }'),
        )
        for before, after in cases:
            with self.subTest(block=before.split(b":", 1)[0]):
                self.assertEqual(payload.count(before), 1)
                mutated = payload.replace(before, after)
                self.assertEqual(b"".join(mutated.split()), b"".join(payload.split()))
                with self.assertRaisesRegex(AssertionError, "Multiline block layout"):
                    self._assert_sdk_observed_ascii_block_layout(mutated)


    def test_shape_and_uv_change_without_connectivity_change(self):
        before, after = DEMO.mesh_data(False), DEMO.mesh_data(True)
        self.assertEqual(before["faces"], after["faces"])
        self.assertEqual(len(before["vertices_cm"]), 91)
        self.assertGreater(max(point[2] for point in after["vertices_cm"]), 15)
        self.assertLessEqual(max(point[2] for point in before["vertices_cm"]), 4)
        self.assertNotEqual(before["vertices_cm"], after["vertices_cm"])
        self.assertEqual(max(u for u, v in before["uv1"]), 0.6)
        self.assertEqual(max(u for u, v in after["uv1"]), 1.0)
        self.assertTrue(all(math.isfinite(value) for data in (before, after)
                            for point in data["vertices_cm"] for value in point))

    def test_populated_scene_refused_before_output_or_native_mutation(self):
        native = SimpleNamespace(objects=[object()])
        with patch.dict(sys.modules, {"pymxs": SimpleNamespace(runtime=native)}):
            with patch.object(DEMO, "_new_output_directory") as output:
                with self.assertRaisesRegex(RuntimeError, "empty scene"):
                    DEMO.create_demo_scene()
                output.assert_not_called()

    def test_incomplete_scene_enumeration_refused_before_output(self):
        def broken():
            yield object()
            raise RuntimeError("incomplete native enumeration")
        native = SimpleNamespace(objects=broken())
        with patch.dict(sys.modules, {"pymxs": SimpleNamespace(runtime=native)}):
            with patch.object(DEMO, "_new_output_directory") as output:
                with self.assertRaisesRegex(RuntimeError, "incomplete native"):
                    DEMO.create_demo_scene()
                output.assert_not_called()

    def test_output_redirect_into_source_refused(self):
        with patch.dict(os.environ, {"LOCALAPPDATA": str(ROOT)}):
            with self.assertRaisesRegex(RuntimeError, "outside the source"):
                DEMO._new_output_directory()

    def test_created_node_is_owned_when_handle_read_fails(self):
        self._exercise_handle_failure(False)

    def test_failure_receipt_error_preserves_primary_error(self):
        self._exercise_handle_failure(True)

    def _exercise_handle_failure(self, fail_receipt):
        local = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
        parent = local / "FBXTo3dsMax/Validation"
        parent.mkdir(parents=True, exist_ok=True)
        node = SimpleNamespace(valid=True)
        deleted = []

        def failed_handle(_node):
            raise RuntimeError("original handle read failure")

        def delete(owned):
            self.assertIs(owned, node)
            deleted.append(owned)
            owned.valid = False

        native = SimpleNamespace(
            objects=[], units=SimpleNamespace(decodeValue=lambda value: 1.0),
            mesh=lambda **kwargs: node, point3=lambda *values: values,
            getHandleByAnim=failed_handle, isValidNode=lambda owned: owned.valid,
            delete=delete)
        original_open = Path.open

        def file_open(path, *args, **kwargs):
            if fail_receipt and path.name == "failed.json":
                raise PermissionError("receipt write failure")
            return original_open(path, *args, **kwargs)

        with tempfile.TemporaryDirectory(prefix="demo_failure_", dir=parent) as folder:
            with patch.dict(sys.modules, {"pymxs": SimpleNamespace(runtime=native)}):
                with patch.object(DEMO, "_new_output_directory", return_value=Path(folder)):
                    with patch.object(Path, "open", file_open):
                        with self.assertRaisesRegex(RuntimeError, "original handle read failure") as result:
                            DEMO.create_demo_scene()
            self.assertEqual(deleted, [node])
            self.assertFalse(node.valid)
            if fail_receipt:
                self.assertIn("receipt write failure", str(result.exception))
                self.assertIn("original handle read failure", str(result.exception.__cause__))
            else:
                self.assertTrue((Path(folder) / "failed.json").is_file())

    def test_zero_uv_constructor_is_repaired_before_prepared_commit(self):
        self._exercise_final_native_uv("success")

    def test_meshvalue_assignment_loss_is_avoided_before_prepared_commit(self):
        self._exercise_final_native_uv("assignment_boundary")

    def test_lost_uv_writes_refuse_prepared_commit_and_cleanup_owned_node(self):
        self._exercise_final_native_uv("lost_writes")

    def test_bad_native_tvface_index_refuses_prepared_commit(self):
        self._exercise_final_native_uv("bad_index")

    def test_nonfinite_native_uv_refuses_prepared_commit(self):
        self._exercise_final_native_uv("nonfinite")

    def _exercise_final_native_uv(self, fault):
        # Complete generator through fake native APIs, not native Max acceptance.
        # The assignment model reflects the observed held-wrapper/node UV loss:
        # node.mesh returns a wrapper; assigning it back empties both UV arrays,
        # while snapshotAsMesh recreates zero UVs. Other cases deliberately start
        # with zero constructor UVs as robustness faults, not a native ctor claim.
        class MeshAlias:
            def __init__(self, data):
                self.data = data

            def __getattr__(self, name):
                return getattr(self.data, name)

        class FakeNode:
            valid = True

            @property
            def mesh(self):
                return MeshAlias(self.data)

            @mesh.setter
            def mesh(self, value):
                self.data = mesh_value(value)
                self.data.uv = []

        node = FakeNode()

        def mesh_value(value):
            return value.data if value is node or isinstance(value, MeshAlias) else value
        writes, snapshots, deleted, constructor_uv = [], [], [], []
        point = lambda x, y, z: SimpleNamespace(x=x, y=y, z=z)

        def make_mesh(**kwargs):
            node.data = SimpleNamespace(
                vertices=copy.deepcopy(kwargs["vertices"]),
                faces=copy.deepcopy(kwargs["faces"]),
                uv=(copy.deepcopy(kwargs["tverts"]) if fault == "assignment_boundary" else
                    [point(0.0, 0.0, 0.0) for _ in kwargs["tverts"]]),
                uv_faces=[])
            constructor_uv.extend((value.x, value.y) for value in node.data.uv)
            return node

        def build_tv_faces(mesh):
            mesh = mesh_value(mesh)
            mesh.uv_faces = [point(1, 1, 1) for _ in mesh.faces]

        def set_tv_vert(mesh, index, value):
            mesh = mesh_value(mesh)
            writes.append(index)
            if fault != "lost_writes":
                mesh.uv[index - 1] = copy.deepcopy(value)

        def take_snapshot(owned):
            self.assertIs(owned, node)
            mesh = copy.deepcopy(owned.data)
            if not mesh.uv:
                mesh.uv = [point(0.0, 0.0, 0.0) for _ in constructor_uv]
            mesh.released = False
            if fault == "bad_index":
                mesh.uv_faces[0].x = 0
            if fault == "nonfinite":
                mesh.uv[0].x = float("nan")
            snapshots.append(mesh)
            return mesh

        def free_snapshot(mesh):
            self.assertFalse(mesh.released)
            mesh.released = True

        def delete(owned):
            self.assertIs(owned, node)
            deleted.append(owned)
            owned.valid = False
            native.selection = []

        native = SimpleNamespace(
            objects=[], selection=[], units=SimpleNamespace(decodeValue=lambda value: 1.0),
            mesh=make_mesh, point3=point, buildTVFaces=build_tv_faces,
            setTVert=set_tv_vert,
            setTVFace=lambda mesh, index, value: mesh_value(mesh).uv_faces.__setitem__(index - 1, value),
            setFaceSmoothGroup=lambda mesh, index, value: None,
            getHandleByAnim=lambda owned: 70191,
            update=lambda owned: None, color=lambda *values: values,
            StandardMaterial=lambda **kwargs: SimpleNamespace(**kwargs),
            select=lambda owned: setattr(native, "selection", [owned]),
            getNumVerts=lambda value: len(mesh_value(value).vertices),
            getNumFaces=lambda value: len(mesh_value(value).faces),
            snapshotAsMesh=take_snapshot, getNumTVerts=lambda mesh: len(mesh.uv),
            getTVFace=lambda mesh, index: mesh.uv_faces[index - 1],
            getTVert=lambda mesh, index: mesh.uv[index - 1], free=free_snapshot,
            # AnimHandle and INode handle are separate ID spaces.
            getAnimByHandle=lambda handle: node if handle == 70191 and node.valid else None,
            maxOps=SimpleNamespace(getNodeByHandle=lambda handle: node if handle == 13 and node.valid else None),
            isValidNode=lambda owned: owned.valid, delete=delete)
        local = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
        parent = local / "FBXTo3dsMax/Validation"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="demo_uv_fake_", dir=parent) as folder:
            output = Path(folder)
            with patch.dict(sys.modules, {"pymxs": SimpleNamespace(runtime=native)}):
                with patch.object(DEMO, "_new_output_directory", return_value=output):
                    if fault in ("success", "assignment_boundary"):
                        receipt = DEMO.create_demo_scene()
                        self.assertEqual(receipt["state"], "SCENE_PREPARED_NOT_TRANSFERRED")
                    else:
                        expected = {"lost_writes": "UV1 corner readback differs",
                                    "bad_index": "UV1 corner index is out of range",
                                    "nonfinite": "UV1 is non-finite"}[fault]
                        with self.assertRaisesRegex(RuntimeError, expected):
                            DEMO.create_demo_scene()
            self.assertEqual(constructor_uv, DEMO.mesh_data(False)["uv1"] if fault == "assignment_boundary" else [(0.0, 0.0)] * 91)
            self.assertEqual(writes, list(range(1, 92)))
            self.assertEqual(len(snapshots), 1)
            self.assertTrue(snapshots[0].released)
            self.assertFalse((output / ".prepared.json.tmp").exists())
            if fault in ("success", "assignment_boundary"):
                self.assertTrue((output / "prepared.json").is_file())
                self.assertEqual(json.loads((output / "prepared.json").read_text("utf-8")), receipt)
                self.assertEqual(deleted, [])
                self.assertTrue(node.valid)
                # Validate the final owned-node face corners, not just setter calls.
                data = DEMO.mesh_data(False)
                for number, face in enumerate(data["faces"]):
                    tv = node.mesh.uv_faces[number]
                    for actual_index, wanted_index in zip((tv.x, tv.y, tv.z), face):
                        uv = node.mesh.uv[int(actual_index) - 1]
                        self.assertEqual((uv.x, uv.y), data["uv1"][wanted_index])
            else:
                self.assertFalse((output / "prepared.json").exists())
                self.assertTrue((output / "failed.json").is_file())
                self.assertEqual(deleted, [node])
                self.assertFalse(node.valid)


if __name__ == "__main__":
    unittest.main()
