# -*- coding: utf-8 -*-
"""Run only the procedural Max portion of the FBXTo3dsMax self-check."""

import importlib.util
import gc
import os
import tempfile
import sys
import traceback

from pymxs import runtime as rt


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULT = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "FBXTo3dsMax", "Validation", "_max_procedural_selfcheck_result.txt")
os.makedirs(os.path.dirname(RESULT), exist_ok=True)


def load_selfcheck():
    path = os.path.join(ROOT, "f2m_selfcheck.py")
    spec = importlib.util.spec_from_file_location("_f2m_max_procedural_selfcheck", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to create self-check module spec.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


check = None
try:
    check = load_selfcheck()
    detail = check._procedural_max_check()
    text = "PASS\n" + str(detail)
except BaseException:
    text = "FAIL\n" + traceback.format_exc()
finally:
    try:
        if check is not None:
            check._reset_max_file_safely()
        else:
            gc.collect()
            rt.execute("(try(gc light:true; true)catch(false))")
            rt.clearSelection()
            rt.resetMaxFile(rt.Name("noPrompt"))
    except Exception:
        pass
    check = None
    gc.collect()

with open(RESULT, "w", encoding="utf-8") as handle:
    handle.write(text + f"\nENGINE_PID={os.getpid()}\n")

if not text.startswith("PASS"):
    raise RuntimeError(text)
