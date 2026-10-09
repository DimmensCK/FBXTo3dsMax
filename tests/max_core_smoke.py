# -*- coding: utf-8 -*-
"""3ds Max Batch smoke test for the pymxs/MAXScript bridge."""

from __future__ import annotations

import importlib.util
import tempfile
import os
import sys
import traceback

from pymxs import runtime as rt


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_ROOT = os.path.join(ROOT, "contents") if os.path.isdir(os.path.join(ROOT, "contents")) else ROOT
os.makedirs(os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "FBXTo3dsMax", "Validation"), exist_ok=True)
RESULT = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "FBXTo3dsMax", "Validation", "_max_core_smoke_result.txt")


def load_module(filename: str, module_name: str):
    path = os.path.join(RUNTIME_ROOT, filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    if os.path.normcase(os.path.abspath(module.__file__)) != os.path.normcase(path):
        raise RuntimeError(f"module origin mismatch: {module.__file__}")
    return module


def main() -> None:
    module = load_module("f2m_topology_transfer.py", "_f2m_topology_smoke")
    module.ensure_runtime()
    rt.F2M_Helper.setLastMessage("拓扑核心复用哨兵")
    skin_module = load_module("f2m_skin_replace.py", "_f2m_skin_smoke")
    skin_module.ensure_runtime()
    rt.F2M_Helper.setLastMessage("蒙皮核心复用哨兵")
    module.ensure_runtime()
    if module.helper_message() != "拓扑核心复用哨兵":
        raise AssertionError("切换模式后拓扑 Helper 被重复编译。")
    skin_module.ensure_runtime()
    if skin_module.helper_message() != "蒙皮核心复用哨兵":
        raise AssertionError("切换模式后蒙皮 Helper 被重复编译。")
    module.ensure_runtime()

    rt.resetMaxFile(rt.Name("noPrompt"))
    source = rt.Box(name="F2M_Source", length=10, width=10, height=10)
    target = rt.copy(source)
    target.name = "F2M_Target"
    rt.convertToPoly(source)
    rt.convertToPoly(target)

    if not module.topo_same_for_channels(source, target):
        raise AssertionError(module.helper_message())

    masks = [1 if index % 2 else 2 for index in range(1, module.base_face_count(source) + 1)]
    max_masks = rt.Array(*masks)
    if not bool(rt.F2M_Helper.setFaceSmoothingGroups(target, max_masks)):
        raise AssertionError(
            f"{module.helper_message()} | base={rt.classOf(target.baseObject)} "
            f"faces={rt.polyop.getNumFaces(target)} py={len(masks)} max={len(max_masks)}"
        )
    readback = [int(value) for value in list(rt.F2M_Helper.getFaceSmoothingGroups(target))]
    if readback != masks:
        raise AssertionError(f"smoothing readback mismatch: {readback} != {masks}")

    with open(RESULT, "w", encoding="utf-8") as handle:
        handle.write("PASS\n")
        handle.write(module.helper_message() + "\n")


try:
    main()
except BaseException:
    with open(RESULT, "w", encoding="utf-8") as handle:
        handle.write("FAIL\n")
        handle.write(traceback.format_exc())
    raise
