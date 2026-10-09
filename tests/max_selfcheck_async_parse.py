# -*- coding: utf-8 -*-
"""Parse the asynchronous self-check controller in Max's embedded Python."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import traceback


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_ROOT = os.path.join(ROOT, "contents") if os.path.isdir(os.path.join(ROOT, "contents")) else ROOT
SOURCE = os.path.join(RUNTIME_ROOT, "f2m_selfcheck.py")
os.makedirs(os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "FBXTo3dsMax", "Validation"), exist_ok=True)
RESULT = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "FBXTo3dsMax", "Validation", "_max_selfcheck_async_parse_result.txt")


try:
    module_name = "_f2m_max_selfcheck_async_parse"
    spec = importlib.util.spec_from_file_location(module_name, SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法创建自检模块加载器。")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    if not callable(getattr(module, "start_from_max", None)):
        raise RuntimeError("缺少异步自检启动入口。")
    if "subprocess.Popen" not in open(SOURCE, "r", encoding="utf-8-sig").read():
        raise RuntimeError("异步自检没有使用 Popen。")

    child_keys = (
        module.CHILD_ENV,
        module.RESULT_ENV,
        module.PROGRESS_ENV,
        module.CANCEL_ENV,
    )
    saved = {key: os.environ.get(key) for key in child_keys}
    entered_isolated_runner = [False]

    def forbidden_runner(*_args, **_kwargs):
        entered_isolated_runner[0] = True
        raise AssertionError("错误上下文进入了场景自检。")

    try:
        for key in child_keys:
            os.environ.pop(key, None)
        module._run_isolated = forbidden_runner
        try:
            module._child_entry()
            raise AssertionError("错误上下文没有被拒绝。")
        except RuntimeError as exc:
            if "已拒绝" not in str(exc):
                raise
        if entered_isolated_runner[0]:
            raise AssertionError("错误上下文触发了场景自检。")
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    probe = os.path.join(
        tempfile.gettempdir(),
        "FBXTo3dsMax_max_async_probe_{0}.json".format(os.getpid()),
    )
    module._atomic_write_json(probe, {"状态": "通过"})
    with open(probe, "r", encoding="utf-8") as handle:
        if json.load(handle).get("状态") != "通过":
            raise AssertionError("原子 JSON 读回失败。")
    os.remove(probe)

    with open(RESULT, "w", encoding="utf-8") as handle:
        handle.write("PASS\n")
except BaseException:
    with open(RESULT, "w", encoding="utf-8") as handle:
        handle.write("FAIL\n")
        handle.write(traceback.format_exc())
    raise
