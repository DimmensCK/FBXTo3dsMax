# -*- coding: utf-8 -*-
"""Parse the installer layer in 3ds Max Batch without executing mutations."""

from __future__ import annotations

import os
import traceback
import tempfile
import uuid

from pymxs import runtime as rt


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.makedirs(os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "FBXTo3dsMax", "Validation"), exist_ok=True)
RESULT = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "FBXTo3dsMax", "Validation", "_max_install_parse_result.txt")
SCRIPT_FILES = (
    "Install_FBXTo3dsMax.ms",
    "Uninstall_FBXTo3dsMax.ms",
    os.path.join("Contents", "FBXTo3dsMax_Bootstrap.ms"),
    os.path.join("Contents", "FBXTo3dsMax.mcr"),
    os.path.join("tests", "max_install_v1319_harness.ms"),
)


def parse_without_running(path: str) -> None:
    with open(path, "r", encoding="utf-8-sig") as handle:
        source = handle.read()
    # MAXScript parses both branches before evaluating the false condition.
    # The extra block accepts each production file's top-level expression while
    # ensuring installer, uninstaller and bootstrap side effects never run.
    wrapped = "if false then\n(\n" + source + "\n)\nelse true"
    result = rt.execute(wrapped)
    if not bool(result):
        raise RuntimeError("parse wrapper did not return true: " + path)


def execute_installer_no_source(path: str) -> None:
    """Execute installer declarations while forcing the no-source safe branch."""

    with open(path, "r", encoding="utf-8-sig") as handle:
        source = handle.read()
    source_marker = "local installerPath = getSourceFileName()"
    dialog_marker = (
        "messageBox F2M_Installer_FinalDialogText "
        "title:F2M_Installer_FinalDialogTitle"
    )
    if source.count(source_marker) != 1 or source.count(dialog_marker) != 1:
        raise RuntimeError("installer safe-branch markers changed")
    source = source.replace(
        source_marker,
        'local installerPath = ""',
        1,
    )
    source = source.replace(dialog_marker, "true", 1)
    result = rt.execute(source)
    if not bool(result):
        raise RuntimeError("installer semantic safe branch did not return true")


def execute_package_lock_probe() -> None:
    """Exercise the same FileShare.None lock primitive used by both transactions."""

    lock_path = os.path.join(
        tempfile.gettempdir(),
        "FBXTo3dsMax-lock-probe-" + uuid.uuid4().hex + ".lock",
    )
    max_path = lock_path.replace("\\", "\\\\").replace('"', '\\"')
    source = f"""
(
    local fileClass = dotNetClass "System.IO.File"
    local fileMode = dotNetClass "System.IO.FileMode"
    local fileAccess = dotNetClass "System.IO.FileAccess"
    local fileShare = dotNetClass "System.IO.FileShare"
    local firstLock = undefined
    local secondLock = undefined
    local secondWasBlocked = false
    firstLock = fileClass.Open "{max_path}" fileMode.OpenOrCreate fileAccess.ReadWrite fileShare.None
    try
    (
        secondLock = fileClass.Open "{max_path}" fileMode.OpenOrCreate fileAccess.ReadWrite fileShare.None
    )
    catch
    (
        secondWasBlocked = true
    )
    try(if secondLock != undefined do secondLock.Dispose())catch()
    try(if firstLock != undefined do firstLock.Dispose())catch()
    if not secondWasBlocked do throw "FileShare.None 未阻止第二个安装事务。"
    true
)
"""
    try:
        if not bool(rt.execute(source)):
            raise RuntimeError("package lock probe did not return true")
    finally:
        try:
            os.unlink(lock_path)
        except OSError:
            pass


def execute_toolbar_shutdown_callback_probe() -> None:
    """Verify that every shutdown callback used by Bootstrap exists in Max 2023."""

    source = r"""
(
    local callbackId = #FBXTo3dsMax_ShutdownProbe
    local errorText = ""
    callbacks.removeScripts id:callbackId
    try
    (
        callbacks.addScript #systemShutdownCheck "true" id:callbackId persistent:false
        callbacks.addScript #systemShutdownCheckFailed "true" id:callbackId persistent:false
        callbacks.addScript #systemShutdownCheckPassed "true" id:callbackId persistent:false
        callbacks.addScript #preSystemShutdown "true" id:callbackId persistent:false
    )
    catch
    (
        errorText = getCurrentException()
    )
    callbacks.removeScripts id:callbackId
    if errorText != "" do throw errorText
    true
)
"""
    if not bool(rt.execute(source)):
        raise RuntimeError("toolbar shutdown callback probe did not return true")


try:
    for relative in SCRIPT_FILES:
        parse_without_running(os.path.join(ROOT, relative))
    execute_installer_no_source(
        os.path.join(ROOT, "Install_FBXTo3dsMax.ms")
    )
    execute_package_lock_probe()
    execute_toolbar_shutdown_callback_probe()
    with open(RESULT, "w", encoding="utf-8") as handle:
        handle.write("PASS\n")
        handle.write("Max 2023 shutdown callbacks: 4/4\n")
        handle.write("\n".join(SCRIPT_FILES))
except BaseException:
    with open(RESULT, "w", encoding="utf-8") as handle:
        handle.write("FAIL\n")
        handle.write(traceback.format_exc())
    raise
