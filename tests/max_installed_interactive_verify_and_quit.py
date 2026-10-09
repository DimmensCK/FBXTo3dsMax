"""在带单次令牌的专用 Max 子进程中验收已安装工具栏，然后退出该子进程。"""

from __future__ import annotations

import ctypes
import json
import os
import tempfile
import re
import runpy
import tempfile
import traceback

from pymxs import runtime as rt


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
VERIFY = os.path.join(ROOT, "tests", "max_installed_interactive_verify.py")
RESULT = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "FBXTo3dsMax", "Validation", "_max_installed_interactive_verify.json")
os.makedirs(os.path.dirname(RESULT), exist_ok=True)
TOKEN_ENV = "F2M_INSTALLED_VERIFY_TOKEN"


def _process_command_line_args() -> list[str]:
    get_command_line = ctypes.windll.kernel32.GetCommandLineW
    get_command_line.restype = ctypes.c_wchar_p
    command_line_to_argv = ctypes.windll.shell32.CommandLineToArgvW
    command_line_to_argv.argtypes = (
        ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_int),
    )
    command_line_to_argv.restype = ctypes.POINTER(ctypes.c_wchar_p)
    local_free = ctypes.windll.kernel32.LocalFree
    local_free.argtypes = (ctypes.c_void_p,)
    local_free.restype = ctypes.c_void_p

    count = ctypes.c_int(0)
    argv = command_line_to_argv(str(get_command_line() or ""), ctypes.byref(count))
    if not argv:
        raise RuntimeError("无法解析当前 3ds Max 子进程命令行。")
    try:
        return [str(argv[index]) for index in range(int(count.value))]
    finally:
        local_free(ctypes.cast(argv, ctypes.c_void_p))


def _normalized_path(path: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.normpath(path)))


def _has_exact_python_host_identity(args: list[str]) -> bool:
    expected = _normalized_path(__file__)
    matches = 0
    for index in range(max(0, len(args) - 2)):
        if (
            args[index].lower() == "-u"
            and args[index + 1].lower() == "pythonhost"
            and _normalized_path(args[index + 2]) == expected
        ):
            matches += 1
    return matches == 1


def _write_status(payload: dict) -> None:
    directory = os.path.dirname(RESULT)
    os.makedirs(directory, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix="._f2m_installed_verify_",
        suffix=".json",
        dir=directory,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, RESULT)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


run_token = str(os.environ.get(TOKEN_ENV, ""))
command_line_args = _process_command_line_args()
if not re.fullmatch(r"v1\.4\.24-[0-9a-fA-F]{32}", run_token):
    raise RuntimeError("拒绝运行安装后验收：缺少专用子进程令牌。")
if not _has_exact_python_host_identity(command_line_args):
    raise RuntimeError("拒绝运行安装后验收：当前进程不是指定的验收子进程。")

os.environ.pop(TOKEN_ENV, None)
process_id = int(os.getpid())
_write_status(
    {
        "ok": None,
        "state": "started",
        "token": run_token,
        "pid": process_id,
    }
)

try:
    runpy.run_path(VERIFY, run_name="__main__")
    with open(RESULT, "r", encoding="utf-8") as handle:
        result = json.load(handle)
    result["state"] = "finished"
    result["token"] = run_token
    result["pid"] = process_id
    _write_status(result)
except BaseException:
    try:
        with open(RESULT, "r", encoding="utf-8") as handle:
            result = json.load(handle)
        if not isinstance(result, dict):
            result = {}
    except BaseException:
        result = {}
    result.update(
        {
            "ok": False,
            "state": "failed",
            "token": run_token,
            "pid": process_id,
            "wrapper_traceback": traceback.format_exc(),
        }
    )
    _write_status(result)
finally:
    # 只有通过上方令牌和命令行双重身份检查的专用进程才能到达这里。
    rt.quitMax(rt.Name("noPrompt"))
