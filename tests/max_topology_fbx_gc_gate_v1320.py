# -*- coding: utf-8 -*-
"""Isolated real-FBX topology gate with a safe final scene reset."""

from __future__ import annotations

import gc
import importlib.util
import json
import os
import sys
import time
import traceback
from typing import Any

from pymxs import runtime as rt


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULT = os.path.join(
    ROOT,
    "tests",
    "_max_topology_fbx_gc_gate_v1320_result.json",
)


def load_selfcheck() -> Any:
    path = os.path.join(ROOT, "f2m_selfcheck.py")
    name = "_f2m_topology_fbx_gc_gate_v1320"
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


payload = {
    "ok": False,
    "version": "1.3.20",
    "engine_pid": os.getpid(),
    "started_at_utc_epoch": time.time(),
    "finished_at_utc_epoch": 0.0,
    "detail": "",
    "heap_check_before": "",
    "heap_check_after": "",
    "error": "",
    "cleanup_error": "",
}
check = None
try:
    payload["heap_check_before"] = str(rt.execute("heapCheck() as string"))
    check = load_selfcheck()
    payload["detail"] = str(check._topology_fbx_check())
    payload["heap_check_after"] = str(rt.execute("heapCheck() as string"))
    if payload["heap_check_after"].strip().casefold() not in {"ok", "true"}:
        raise AssertionError(payload["heap_check_after"])
    payload["ok"] = True
except BaseException:
    payload["error"] = traceback.format_exc()
finally:
    try:
        if check is not None:
            check._reset_max_file_safely()
        else:
            rt.execute("(try(subObjectLevel = 0)catch())")
            rt.execute("(try(setCommandPanelTaskMode #create)catch())")
            rt.clearSelection()
            rt.resetMaxFile(rt.Name("noPrompt"))
    except BaseException:
        payload["cleanup_error"] = traceback.format_exc()
        payload["ok"] = False
    check = None
    gc.collect()
    payload["finished_at_utc_epoch"] = time.time()
    with open(RESULT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

if not payload["ok"]:
    raise RuntimeError("Topology FBX GC gate failed; inspect its JSON result.")
