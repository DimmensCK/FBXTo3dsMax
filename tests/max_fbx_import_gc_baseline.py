# -*- coding: utf-8 -*-
"""Measure native FBX retention using explicitly supplied private test data.

This historical gate ships no scene or FBX assets. Set F2M_PRIVATE_MAX_FIXTURE,
F2M_PRIVATE_FBX_VARIANT1/2 and their matching SHA256 variables before running.
The scene must contain the configured F2M_PRIVATE_NODE_A/B mesh names.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
import traceback
from datetime import datetime, timezone

from pymxs import runtime as rt


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _required_private_path(variable):
    path = os.environ.get(variable, "").strip()
    if not path or not os.path.isabs(path) or not os.path.isfile(path):
        raise RuntimeError(f"Provide an existing absolute private fixture: {variable}")
    path = os.path.abspath(path)
    try:
        inside_source = os.path.commonpath((ROOT, path)) == ROOT
    except ValueError:
        inside_source = False
    if inside_source:
        raise RuntimeError(f"Private fixtures must be outside the source tree: {variable}")
    return path


def _required_private_sha256(variable):
    value = os.environ.get(variable, "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise RuntimeError(f"Provide the expected private fixture SHA-256: {variable}")
    return value


MAX_PATH = _required_private_path("F2M_PRIVATE_MAX_FIXTURE")
FBX_PATHS = (
    _required_private_path("F2M_PRIVATE_FBX_VARIANT1"),
    _required_private_path("F2M_PRIVATE_FBX_VARIANT2"),
)
SOURCE_NAMES = (
    os.environ.get("F2M_PRIVATE_NODE_A", "ExampleMeshA"),
    os.environ.get("F2M_PRIVATE_NODE_B", "ExampleMeshB"),
)
ASSET_PATHS = (MAX_PATH,) + FBX_PATHS
EXPECTED_ASSET_HASHES = {
    MAX_PATH: _required_private_sha256("F2M_PRIVATE_MAX_SHA256"),
    FBX_PATHS[0]: _required_private_sha256("F2M_PRIVATE_FBX_VARIANT1_SHA256"),
    FBX_PATHS[1]: _required_private_sha256("F2M_PRIVATE_FBX_VARIANT2_SHA256"),
}
PRODUCTION_MODULE_FILES = {
    "f2m_topology_transfer.py",
    "f2m_skin_replace.py",
    "f2m_fbx_metadata.py",
    "f2m_smoothing.py",
}
RESULT = os.path.abspath(os.environ.get(
    "F2M_FBX_GC_BASELINE_RESULT",
    os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(),
                 "FBXTo3dsMax", "Validation", "_max_fbx_import_gc_baseline.json"),
))
os.makedirs(os.path.dirname(RESULT), exist_ok=True)
ITERATIONS = int(os.environ.get("F2M_FBX_GC_BASELINE_ITERATIONS", "16"))
LOG_PREFIX = "F2M_RAW_FBX_GC_BASELINE"


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def log_marker(kind, ok=None):
    parts = [
        f"{LOG_PREFIX}_{kind}",
        f"PID={os.getpid()}",
        f"UTC={utc_now()}",
    ]
    if ok is not None:
        parts.append(f"OK={str(bool(ok)).lower()}")
    message = " ".join(parts)
    rt.logsystem.logEntry(message, broadcast=True)
    print(message, flush=True)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def asset_hashes():
    return {path: sha256(path) for path in ASSET_PATHS}


def load_memory_probe():
    """Load only the test-owned Win32 memory probe; its main() is not called."""

    path = os.path.join(ROOT, "tests", "max_selection_switch_gc_stress.py")
    spec = importlib.util.spec_from_file_location("_f2m_raw_memory_probe", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def heap_sample(memory_probe):
    status = str(rt.execute("heapCheck() as string")).strip()
    if status.casefold() not in {"ok", "true"}:
        raise RuntimeError(f"heapCheck failed: {status}")
    result = {
        "heap_check": status,
        "heap_size": int(rt.execute("heapSize")),
        "heap_free": int(rt.execute("heapFree")),
    }
    result.update(memory_probe._process_memory())
    return result


def valid_importer_value(value):
    return value is not None and str(value).strip().casefold() not in {
        "undefined",
        "unsupplied",
        "none",
    }


def normalized_importer_value(value):
    text = str(value).strip().casefold()
    return text[1:] if text.startswith("#") else text


def importer_values_equal(name, expected, actual):
    if not valid_importer_value(actual):
        return False
    expected_text = normalized_importer_value(expected)
    actual_text = normalized_importer_value(actual)
    if name in {"Animation", "SmoothingGroups"}:
        aliases = {
            "true": True,
            "1": True,
            "false": False,
            "0": False,
        }
        if expected_text in aliases and actual_text in aliases:
            return aliases[expected_text] == aliases[actual_text]
    return expected_text == actual_text


def get_import_option(name):
    value = rt.FBXImporterGetParam(rt.Name(name))
    if not valid_importer_value(value):
        raise RuntimeError(f"FBXImporterGetParam rejected {name}")
    return value


def set_import_option(name, value):
    result = rt.FBXImporterSetParam(rt.Name(name), value)
    if not valid_importer_value(result):
        raise RuntimeError(f"FBXImporterSetParam rejected {name}={value}")
    readback = get_import_option(name)
    if not importer_values_equal(name, value, readback):
        raise RuntimeError(
            f"FBX importer readback mismatch for {name}: "
            f"{value} != {readback}"
        )


def snapshot_import_options():
    return {
        name: get_import_option(name)
        for name in ("Mode", "Animation", "SmoothingGroups")
    }


def restore_import_options(snapshot):
    failures = []
    for name, value in snapshot.items():
        try:
            set_import_option(name, value)
        except Exception as exc:
            failures.append(f"{name}: {exc}")
    if failures:
        raise RuntimeError(
            "failed to restore Autodesk FBX importer settings: "
            + "; ".join(failures)
        )


def valid_nodes(nodes):
    result = []
    for node in nodes:
        try:
            if bool(rt.isValidNode(node)):
                result.append(node)
        except Exception:
            continue
    return result


def node_handles(nodes):
    return sorted(
        int(rt.getHandleByAnim(node))
        for node in valid_nodes(nodes)
    )


def scene_snapshot():
    identities = sorted(
        (
            int(rt.getHandleByAnim(node)),
            str(node.name),
            str(rt.classOf(node)),
        )
        for node in valid_nodes(list(rt.objects))
    )
    encoded = json.dumps(
        identities,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "node_count": len(identities),
        "node_identity_sha256": hashlib.sha256(encoded).hexdigest(),
        "node_handles": [identity[0] for identity in identities],
        "selection_handles": node_handles(list(rt.selection)),
    }


def loaded_production_modules():
    loaded = []
    for name, module in tuple(sys.modules.items()):
        path = str(getattr(module, "__file__", "") or "")
        if os.path.basename(path).casefold() in PRODUCTION_MODULE_FILES:
            loaded.append(
                {
                    "name": str(name),
                    "file": os.path.abspath(path),
                }
            )
    return loaded


def scenario(index):
    matrix = (
        (0, 0, False),
        (0, 1, False),
        (1, 0, False),
        (1, 1, False),
        (0, 0, True),
        (0, 1, True),
        (1, 0, True),
        (1, 1, True),
    )
    fbx_index, source_index, mixed = matrix[index % len(matrix)]
    return {
        "fbx_path": FBX_PATHS[fbx_index],
        "source_name": SOURCE_NAMES[source_index],
        "mixed_normals_smoothing": mixed,
        "import_passes": 2 if mixed else 1,
    }


def delete_handles(handles):
    leftovers = list(
        rt.execute(
            """
            (
                fn F2M_RawBaselineDeleteHandles handleValues =
                (
                    -- Match production cleanup without importing it: resolve
                    -- one wrapper, delete immediately, release, then continue.
                    for handleValue in handleValues do
                    (
                        local n = try(getAnimByHandle handleValue)catch(undefined)
                        if n != undefined and isValidNode n do
                        (
                            try(delete n)catch()
                        )
                        n = undefined
                    )
                    local remaining = #()
                    for handleValue in handleValues do
                    (
                        local n = try(getAnimByHandle handleValue)catch(undefined)
                        if n != undefined and isValidNode n do
                            append remaining handleValue
                        n = undefined
                    )
                    remaining
                )
                F2M_RawBaselineDeleteHandles
            )
            """
        )(list(handles))
    )
    if leftovers:
        raise RuntimeError(f"raw delete left handles: {leftovers}")


def import_native_once(fbx_path, smoothing_groups):
    snapshot = snapshot_import_options()
    try:
        set_import_option("Mode", rt.Name("create"))
        set_import_option("Animation", False)
        set_import_option("SmoothingGroups", smoothing_groups)
        before = set(node_handles(list(rt.objects)))
        escaped = fbx_path.replace("\\", "\\\\").replace('"', '\\"')
        result = rt.execute(f'importFile "{escaped}" #noPrompt')
        if result is False or str(result).strip().casefold() == "false":
            raise RuntimeError("Autodesk FBX import returned false")
        handles = [
            handle
            for handle in node_handles(list(rt.objects))
            if handle not in before
        ]
        if not handles:
            raise AssertionError("Autodesk FBX import created no nodes")
        return handles
    finally:
        restore_import_options(snapshot)


def assert_scene_restored(baseline_scene, current_scene, selected_handle, index):
    if current_scene["node_identity_sha256"] != baseline_scene["node_identity_sha256"]:
        raise AssertionError(
            f"iteration {index} changed scene node identity"
        )
    if current_scene["node_handles"] != baseline_scene["node_handles"]:
        raise AssertionError(
            f"iteration {index} left temporary node handles"
        )
    if current_scene["selection_handles"] != [selected_handle]:
        raise AssertionError(
            f"iteration {index} did not restore selected source"
        )


def main():
    started_at = utc_now()
    hashes_before = asset_hashes()
    if hashes_before != EXPECTED_ASSET_HASHES:
        raise AssertionError(
            f"frozen asset hashes do not match: {hashes_before}"
        )

    run_result = None
    try:
        rt.resetMaxFile(rt.Name("noPrompt"))
        rt.execute("pluginManager.loadClass FbxImporter")
        if not bool(rt.loadMaxFile(MAX_PATH, useFileUnits=True, quiet=True)):
            raise RuntimeError(f"failed to load {MAX_PATH}")
        log_marker("BEGIN")

        memory_probe = load_memory_probe()
        production_modules = loaded_production_modules()
        if production_modules:
            raise AssertionError(
                "raw baseline loaded F2M production modules: "
                f"{production_modules}"
            )

        sources = {
            name: rt.getNodeByName(name)
            for name in SOURCE_NAMES
        }
        if len(valid_nodes(sources.values())) != len(SOURCE_NAMES):
            raise RuntimeError("PrivateFixture scene is missing the configured source nodes")

        baseline_scene = scene_snapshot()
        samples = [
            {
                "phase": "baseline",
                "scene": baseline_scene,
                **heap_sample(memory_probe),
            }
        ]
        imported_total = 0
        for index in range(ITERATIONS):
            iteration = index + 1
            current_scenario = scenario(index)
            selected = sources[current_scenario["source_name"]]
            rt.select(selected)
            selected_handle = int(rt.getHandleByAnim(selected))
            passes = (
                (True, False)
                if current_scenario["mixed_normals_smoothing"]
                else (False,)
            )
            imported_handles = []
            for smoothing_groups in passes:
                handles = import_native_once(
                    current_scenario["fbx_path"],
                    smoothing_groups,
                )
                imported_total += 1
                imported_handles.extend(handles)
                rt.clearSelection()
                delete_handles(handles)

            rt.select(selected)
            current_scene = scene_snapshot()
            assert_scene_restored(
                baseline_scene,
                current_scene,
                selected_handle,
                iteration,
            )
            production_modules = loaded_production_modules()
            if production_modules:
                raise AssertionError(
                    f"iteration {iteration} loaded production modules: "
                    f"{production_modules}"
                )
            samples.append(
                {
                    "phase": "iteration",
                    "index": iteration,
                    "scenario": current_scenario,
                    "import_passes": len(passes),
                    "imported_node_count": len(imported_handles),
                    "scene": current_scene,
                    **heap_sample(memory_probe),
                }
            )

        baseline_private = int(samples[0]["private_usage"])
        max_private = max(int(sample["private_usage"]) for sample in samples)
        run_result = {
            "schema_version": 2,
            "test": "Autodesk native FBX import GC baseline",
            "ok": True,
            "iterations": ITERATIONS,
            "imported_total": imported_total,
            "heavy_mixed_iterations": sum(
                1
                for index in range(ITERATIONS)
                if scenario(index)["mixed_normals_smoothing"]
            ),
            "delete_strategy": "single_node_by_handle_immediate_release",
            "assets": {
                "max_path": MAX_PATH,
                "fbx_paths": list(FBX_PATHS),
                "expected_sha256": EXPECTED_ASSET_HASHES,
                "sha256_before": hashes_before,
            },
            "baseline_scene": baseline_scene,
            "production_modules_loaded": loaded_production_modules(),
            "samples": samples,
            "baseline_private_usage": baseline_private,
            "max_private_usage": max_private,
            "private_usage_growth": max_private - baseline_private,
            "pid": os.getpid(),
            "started_at_utc": started_at,
        }
    finally:
        rt.resetMaxFile(rt.Name("noPrompt"))

    hashes_after = asset_hashes()
    if hashes_after != hashes_before or hashes_after != EXPECTED_ASSET_HASHES:
        raise AssertionError(
            f"raw baseline changed frozen assets: {hashes_after}"
        )
    run_result["assets"]["sha256_after"] = hashes_after
    run_result["assets"]["unchanged"] = True
    run_result["finished_at_utc"] = utc_now()
    return run_result


try:
    payload = main()
except BaseException:
    payload = {
        "ok": False,
        "iterations": ITERATIONS,
        "pid": os.getpid(),
        "traceback": traceback.format_exc(),
    }
    raise
finally:
    try:
        log_marker("END", payload.get("ok", False))
    except Exception:
        pass
    with open(RESULT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
