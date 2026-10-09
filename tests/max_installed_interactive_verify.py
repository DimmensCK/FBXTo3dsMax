# -*- coding: utf-8 -*-
"""Interactive 3ds Max verification for the installed persistent toolbar."""

from __future__ import annotations

import json
import os
import tempfile
import traceback

from pymxs import runtime as rt

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

import qtmax


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULT = os.path.join(
    os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(),
    "FBXTo3dsMax", "Validation",
    "_max_installed_interactive_verify.json",
)
os.makedirs(os.path.dirname(RESULT), exist_ok=True)
MAIN_TOOLBAR_OBJECT_NAME = "Main Toolbar"
LEGACY_TOOLBAR_OBJECT_NAME = "FBXTo3dsMax.Toolbar"
FALLBACK_TOOLBAR_OBJECT_NAME = "FBXTo3dsMax.FallbackToolbar"
ACTION_OBJECT_NAME = "FBXTo3dsMax.OpenWidgetAction"
BUTTON_OBJECT_NAME = "FBXTo3dsMax.TopButton"
EXPECTED_VERSION = "1.4.24"


def _read_installed_version() -> str:
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        raise RuntimeError("无法定位 APPDATA，不能核对正式安装版本。")
    version_path = os.path.join(
        appdata,
        "Autodesk",
        "ApplicationPlugins",
        "FBXTo3dsMax",
        "contents",
        "FBXTo3dsMax.version",
    )
    if not os.path.isfile(version_path):
        raise RuntimeError(f"正式安装版本文件不存在：{version_path}")
    with open(version_path, "r", encoding="utf-8-sig") as handle:
        actual = handle.read().strip()
    if actual != EXPECTED_VERSION:
        raise RuntimeError(
            f"正式安装版本不一致：期望 {EXPECTED_VERSION}，实际 {actual or '空'}"
        )
    return actual


def _wait_for_delayed_installs() -> None:
    """Let every 0/250/1000 ms idempotent toolbar retry finish."""

    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(1600, loop.quit)
    execute = getattr(loop, "exec", None)
    if execute is None:
        execute = loop.exec_
    execute()


def _global_rect(widget):
    return QtCore.QRect(
        widget.mapToGlobal(QtCore.QPoint(0, 0)),
        widget.size(),
    )


def main() -> dict:
    installed_version = _read_installed_version()
    main_window = qtmax.GetQMaxMainWindow()
    if main_window is None:
        raise RuntimeError("3ds Max 主窗口不可用。")

    # The v1.3.16 regression happened in a zero-delay callback.  Waiting before
    # enumeration prevents a pre-callback action reference from hiding it.
    _wait_for_delayed_installs()
    toolbars = list(main_window.findChildren(QtWidgets.QToolBar))
    legacy_toolbars = [
        toolbar
        for toolbar in toolbars
        if toolbar.objectName() == LEGACY_TOOLBAR_OBJECT_NAME
    ]
    if legacy_toolbars:
        raise AssertionError(
            "仍存在 v1.3.16 遗留的独立空工具栏："
            f"{len(legacy_toolbars)} 个。"
        )

    matches = []
    for toolbar in toolbars:
        for action in toolbar.actions():
            if action.objectName() == ACTION_OBJECT_NAME:
                matches.append((toolbar, action))
    if len(matches) != 1:
        raise AssertionError(
            f"顶部按钮动作应恰好有 1 个，实际为 {len(matches)} 个。"
        )
    toolbar, action = matches[0]
    if toolbar.objectName() not in (
        MAIN_TOOLBAR_OBJECT_NAME,
        FALLBACK_TOOLBAR_OBJECT_NAME,
    ):
        raise AssertionError(
            f"顶部按钮位于未知宿主：{toolbar.objectName()!r}。"
        )

    button = toolbar.widgetForAction(action)
    if button is None or button.objectName() != BUTTON_OBJECT_NAME:
        raise AssertionError("顶部按钮控件不存在。")
    if not toolbar.isVisible() or not button.isVisibleTo(main_window):
        raise AssertionError("顶部按钮在重启 3ds Max 后不可见。")
    if not button.isEnabled():
        raise AssertionError("顶部按钮不可点击。")
    if button.width() < 100 or button.height() < 28:
        raise AssertionError(
            f"顶部按钮尺寸异常：{button.width()}×{button.height()}。"
        )
    if button.text() != "FBX 转 MAX":
        raise AssertionError(f"顶部按钮中文文字异常：{button.text()!r}。")
    if button.toolTip() != "打开 FBXTo3dsMax":
        raise AssertionError(f"顶部按钮提示异常：{button.toolTip()!r}。")
    if button.icon().isNull():
        raise AssertionError("顶部按钮图标无效。")

    button_rect = _global_rect(button)
    main_rect = _global_rect(main_window)
    if not button_rect.intersects(main_rect):
        raise AssertionError("顶部按钮位于 3ds Max 主窗口之外。")
    top_limit = main_rect.top() + max(180, int(main_rect.height() * 0.15))
    if button_rect.top() > top_limit:
        raise AssertionError("按钮没有位于 3ds Max 顶部区域。")

    center = button_rect.center()
    screen = QtGui.QGuiApplication.screenAt(center)
    if screen is None or not screen.availableGeometry().contains(center):
        raise AssertionError("顶部按钮不在任何可用屏幕内。")
    hit_widget = QtWidgets.QApplication.widgetAt(center)
    if hit_widget is None or (
        hit_widget is not button and not button.isAncestorOf(hit_widget)
    ):
        raise AssertionError("顶部按钮被其它界面遮挡，鼠标无法命中。")

    if toolbar.objectName() == FALLBACK_TOOLBAR_OBJECT_NAME:
        top_area = getattr(
            getattr(QtCore.Qt, "ToolBarArea", QtCore.Qt),
            "TopToolBarArea",
        )
        if main_window.toolBarArea(toolbar) != top_area:
            raise AssertionError("备用工具栏没有停靠在顶部。")

    # Exercise the real QToolButton signal path used by the user's mouse.
    button.click()
    QtWidgets.QApplication.processEvents()

    rollout = rt.execute("try(F2M_Transfer_Rollout)catch(undefined)")
    if rollout is None or str(rollout) == "undefined":
        raise AssertionError("点击顶部按钮后没有载入正式工具窗口。")
    open_state = rt.execute(
        "try(F2M_Transfer_Rollout.open)catch(false)"
    )
    if not bool(open_state):
        raise AssertionError("正式工具窗口存在，但没有打开。")

    return {
        "ok": True,
        "version": installed_version,
        "host": toolbar.objectName(),
        "action_count": len(matches),
        "button_visible": bool(button.isVisibleTo(main_window)),
        "button_enabled": bool(button.isEnabled()),
        "button_text": button.text(),
        "button_rect": [
            int(button_rect.x()),
            int(button_rect.y()),
            int(button_rect.width()),
            int(button_rect.height()),
        ],
        "toolbar_visible": bool(toolbar.isVisible()),
        "rollout_open": bool(open_state),
    }


try:
    result = main()
except BaseException:
    result = {
        "ok": False,
        "traceback": traceback.format_exc(),
    }

with open(RESULT, "w", encoding="utf-8") as handle:
    json.dump(result, handle, ensure_ascii=False, indent=2)

if not result.get("ok"):
    raise RuntimeError(result["traceback"])
