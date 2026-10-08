# -*- coding: utf-8 -*-
"""Procedural FBX integration test for the topology engine in 3ds Max Batch."""

from __future__ import annotations

import importlib.util
import tempfile
import os
import sys
import traceback

from pymxs import runtime as rt


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = ""
NATIVE_FIXTURE = ""
os.makedirs(os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "FBXTo3dsMax", "Validation"), exist_ok=True)
RESULT = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "FBXTo3dsMax", "Validation", "_max_fbx_integration_result.txt")


def load_module(filename: str, module_name: str):
    path = os.path.join(ROOT, filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _select_handles(module, handles) -> None:
    """Resolve wrappers only for the immediate select call, then release them."""

    nodes = [
        node
        for handle in handles
        for node in [module.node_by_handle(handle)]
        if node is not None
    ]
    try:
        if not nodes:
            raise AssertionError("saved target handles no longer resolve")
        rt.select(nodes)
    finally:
        nodes.clear()


def _release_setup_import(module, context, imported, targets) -> None:
    """Drop every pymxs node alias while the imported target scene is valid."""

    context.imported_nodes.clear()
    module._release_context_node_references(context)
    imported.clear()
    targets.clear()


def _run_native_smoothing_case(module) -> str:
    rt.resetMaxFile(rt.Name("noPrompt"))
    setup_options = module.TransferOptions(
        fbx_path=NATIVE_FIXTURE,
        mode="topology_only",
        dry_run=True,
        transfer_shape=False,
        transfer_smoothing_groups=True,
    )
    setup_context = module.TransferContext(
        setup_options,
        module.TransferLog(),
    )
    imported = module._import_fbx_once(
        setup_context,
        smoothing_groups=True,
    )
    targets = [
        node for node in imported
        if module.is_geometry_node(node)
    ]
    if len(targets) != 1:
        raise AssertionError(
            f"native fixture geometry count mismatch: {len(targets)}"
        )
    target_handle = module.node_handle(targets[0])
    expected_masks = module.smoothing_masks_for_source(
        targets[0],
        setup_context,
    )

    _release_setup_import(module, setup_context, imported, targets)
    setup_context = None
    _select_handles(module, [target_handle])
    module.run_from_max(
        fbx_path=NATIVE_FIXTURE,
        mode="topology_only",
        dry_run=False,
        transfer_shape=False,
        transfer_uv=False,
        uv_channels="",
        transfer_normals=False,
        transfer_smoothing_groups=True,
        transfer_vertex_color=False,
        transfer_alpha=False,
        transfer_material_ids=False,
        keep_imported=False,
        include_hidden=True,
        show_ui=False,
    )
    if not module.LAST_RUN_OK:
        raise AssertionError(
            "native smoothing execution failed: "
            + module.LAST_RUN_SUMMARY
        )
    target_node = module.node_by_handle(target_handle)
    if target_node is None:
        raise AssertionError("native smoothing target no longer resolves")
    try:
        actual_masks = [
            int(value)
            for value in list(
                rt.F2M_Helper.getFaceSmoothingGroups(target_node)
            )
        ]
    finally:
        target_node = None
    if actual_masks != expected_masks:
        raise AssertionError("native smoothing masks changed")
    with open(
        module.LAST_RUN_REPORT_PATH,
        "r",
        encoding="utf-8",
    ) as handle:
        report = handle.read()
    if "FBX 原生平滑层 / Autodesk 精确导入" not in report:
        raise AssertionError(
            "native smoothing production branch was not reported"
        )
    return module.LAST_RUN_REPORT_PATH


def main() -> str:
    global FIXTURE, NATIVE_FIXTURE
    fixtures = load_module("f2m_test_fixtures.py", "_f2m_integration_fixtures")
    paths = fixtures.get_fixture_paths()
    FIXTURE = paths["topology"]
    NATIVE_FIXTURE = paths["native_smoothing"]
    module = load_module("f2m_topology_transfer.py", "_f2m_topology_integration")
    module.ensure_runtime()
    rt.resetMaxFile(rt.Name("noPrompt"))
    channel_case = os.environ.get("F2M_INTEGRATION_CHANNEL_CASE", "mixed")
    channel_options = {
        "mixed": (True, True, True, True),
        "sg_only": (False, False, False, True),
        "normals_only": (False, False, True, False),
        "shape_uv": (True, True, False, False),
    }
    if channel_case not in channel_options:
        raise ValueError(f"unknown integration channel case: {channel_case}")
    transfer_shape, transfer_uv, transfer_normals, transfer_smoothing = (
        channel_options[channel_case]
    )

    setup_options = module.TransferOptions(
        fbx_path=FIXTURE,
        mode="topology_only",
        dry_run=True,
        transfer_shape=True,
        transfer_uv=True,
        transfer_smoothing_groups=True,
    )
    setup_context = module.TransferContext(setup_options, module.TransferLog())
    imported = module._import_fbx_once(setup_context, smoothing_groups=True)
    targets = [node for node in imported if module.is_geometry_node(node)]
    if not targets:
        raise AssertionError("fixture imported no geometry")
    for node in targets:
        masks = module.smoothing_masks_for_source(node, setup_context)
        if len(masks) != module.base_face_count(node):
            raise AssertionError(f"smoothing mask count mismatch: {node.name}")
    node = None

    target_handles = [module.node_handle(node) for node in targets]
    _release_setup_import(module, setup_context, imported, targets)
    setup_context = None
    if os.environ.get("F2M_INTEGRATION_SKIP_DRY_RUN") != "1":
        _select_handles(module, target_handles)
        module.run_from_max(
            fbx_path=FIXTURE,
            mode="topology_only",
            dry_run=True,
            transfer_shape=transfer_shape,
            transfer_uv=transfer_uv,
            uv_channels="1",
            transfer_normals=transfer_normals,
            transfer_smoothing_groups=transfer_smoothing,
            transfer_vertex_color=False,
            transfer_alpha=False,
            transfer_material_ids=False,
            keep_imported=False,
            include_hidden=True,
            show_ui=False,
        )
        if not module.LAST_RUN_OK:
            raise AssertionError(f"dry-run failed: {module.LAST_RUN_SUMMARY}")

    _select_handles(module, target_handles)
    module.run_from_max(
        fbx_path=FIXTURE,
        mode="topology_only",
        dry_run=False,
        transfer_shape=transfer_shape,
        transfer_uv=transfer_uv,
        uv_channels="1",
        transfer_normals=transfer_normals,
        transfer_smoothing_groups=transfer_smoothing,
        transfer_vertex_color=False,
        transfer_alpha=False,
        transfer_material_ids=False,
        keep_imported=False,
        include_hidden=True,
        show_ui=False,
    )
    if not module.LAST_RUN_OK:
        raise AssertionError(f"execution failed: {module.LAST_RUN_SUMMARY}")
    inferred_report = module.LAST_RUN_REPORT_PATH
    if os.environ.get("F2M_INTEGRATION_FIRST_ONLY") == "1":
        return inferred_report
    native_report = _run_native_smoothing_case(module)
    return inferred_report + "\n" + native_report


try:
    report_path = main()
    with open(RESULT, "w", encoding="utf-8") as handle:
        handle.write("PASS\n")
        handle.write(report_path + "\n")
except BaseException:
    with open(RESULT, "w", encoding="utf-8") as handle:
        handle.write("FAIL\n")
        handle.write(traceback.format_exc())
    raise
finally:
    try:
        rt.resetMaxFile(rt.Name("noPrompt"))
    except Exception:
        pass
