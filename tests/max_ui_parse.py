# -*- coding: utf-8 -*-
"""Load the production rollout in 3ds Max Batch and confirm it parses."""

from __future__ import annotations

import tempfile
import os
import traceback

from pymxs import runtime as rt


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.makedirs(os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "FBXTo3dsMax", "Validation"), exist_ok=True)
RESULT = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "FBXTo3dsMax", "Validation", "_max_ui_parse_result.txt")
UI_FILE = os.path.join(ROOT, "FBXTo3dsMax_UI.ms")


try:
    rt.fileIn(UI_FILE)
    rollout = rt.execute("F2M_Transfer_Rollout")
    if rollout is None or str(rollout) == "undefined":
        raise RuntimeError("F2M_Transfer_Rollout was not created")
    diagnostic_path = str(
        rt.execute(
            'F2M_Transfer_Rollout.writeUiDiagnostic "F2M_UI_DIAGNOSTIC_PROBE"'
        )
    )
    if not os.path.isfile(diagnostic_path):
        raise RuntimeError("UI internal diagnostic writer did not create a file")
    with open(diagnostic_path, "r", encoding="utf-8-sig") as diagnostic_handle:
        diagnostic_text = diagnostic_handle.read()
    if "FBXTo3dsMax 界面内部诊断" not in diagnostic_text:
        raise RuntimeError("UI diagnostic header is missing")
    if "F2M_UI_DIAGNOSTIC_PROBE" not in diagnostic_text:
        raise RuntimeError("UI diagnostic did not preserve the technical detail")
    os.remove(diagnostic_path)
    rt.execute("try(destroyDialog F2M_Transfer_Rollout)catch()")
    with open(RESULT, "w", encoding="utf-8") as handle:
        handle.write("PASS\n")
        handle.write("界面内部诊断写入=通过\n")
except BaseException:
    with open(RESULT, "w", encoding="utf-8") as handle:
        handle.write("FAIL\n")
        handle.write(traceback.format_exc())
    raise
