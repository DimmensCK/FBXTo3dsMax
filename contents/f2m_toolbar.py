# -*- coding: utf-8 -*-
"""在 3ds Max 顶部主工具栏中安装 FBXTo3dsMax 中文按钮。

本模块由 Bootstrap 使用绝对路径导入。脚本路径在同步导入阶段缓存到模块
常量中，任何 Qt 延迟回调都不会再读取 MAXScript ``python.ExecuteFile``
共享作用域中短暂存在的 ``__file__``。
"""

from __future__ import absolute_import

import builtins
import ctypes
import importlib.util
import os
import sys
import time

from pymxs import runtime as rt

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets

import qtmax


SCRIPT_FILE = os.path.abspath(__file__)
SCRIPT_DIR = os.path.dirname(SCRIPT_FILE)
TOOL_VERSION = "1.4.24"
ICON_PATH = os.path.join(SCRIPT_DIR, "icons", "FBXTo3dsMax.svg")

MAIN_TOOLBAR_OBJECT_NAME = "Main Toolbar"
LEGACY_TOOLBAR_OBJECT_NAME = "FBXTo3dsMax.Toolbar"
FALLBACK_TOOLBAR_OBJECT_NAME = "FBXTo3dsMax.FallbackToolbar"
ACTION_OBJECT_NAME = "FBXTo3dsMax.OpenWidgetAction"
BUTTON_OBJECT_NAME = "FBXTo3dsMax.TopButton"
BUTTON_TEXT = "FBX 转 MAX"
BUTTON_TOOLTIP = "打开 FBXTo3dsMax"
API_SLOT = "_FBXTO3DSMAX_TOOLBAR_API"


def _language_module():
    path = os.path.abspath(os.path.join(SCRIPT_DIR, "f2m_i18n.py"))
    name = "_fbx_to_3dsmax_i18n_runtime"
    module = sys.modules.get(name)
    if not (module is not None
            and os.path.normcase(os.path.abspath(getattr(module, "__file__", "") or "")) == os.path.normcase(path)
            and getattr(module, "TOOL_VERSION", None) == TOOL_VERSION
            and getattr(module, "_F2M_IMPORT_COMPLETE", False) is True
            and callable(getattr(module, "translate", None))
            and callable(getattr(module, "get_language", None))):
        sys.modules.pop(name, None)
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Cannot create the language module loader")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
            if (os.path.normcase(os.path.abspath(module.__file__)) != os.path.normcase(path)
                    or getattr(module, "TOOL_VERSION", None) != TOOL_VERSION
                    or getattr(module, "_F2M_IMPORT_COMPLETE", False) is not True
                    or not callable(getattr(module, "translate", None))
                    or not callable(getattr(module, "get_language", None))):
                raise RuntimeError("Language module identity/version/API mismatch")
        except BaseException:
            if sys.modules.get(name) is module:
                sys.modules.pop(name, None)
            raise
    return module


def _t(value):
    return _language_module().translate(value)


def _display_status(status):
    # Internal Chinese reasons still govern bounded layout retries.
    result = dict(status)
    for key in ("message", "host"):
        if key in result:
            result[key] = _t(result[key])
    return result


def _enum_value(scope, scoped_name, legacy_name):
    scoped = getattr(scope, scoped_name, None)
    if scoped is not None:
        return getattr(scoped, legacy_name)
    return getattr(scope, legacy_name)


def _top_toolbar_area():
    return _enum_value(QtCore.Qt, "ToolBarArea", "TopToolBarArea")


def _text_beside_icon():
    return _enum_value(QtCore.Qt, "ToolButtonStyle", "ToolButtonTextBesideIcon")


def _fit_button_size(button):
    """按当前文本、图标和已应用样式保留完整按钮所需的最小空间。"""

    button.ensurePolished()
    preferred = button.sizeHint()
    minimum = button.minimumSizeHint()
    button.setMinimumSize(
        QtCore.QSize(
            max(118, preferred.width(), minimum.width()),
            max(34, preferred.height(), minimum.height()),
        )
    )
    button.updateGeometry()


def _global_rect(widget):
    point = widget.mapToGlobal(QtCore.QPoint(0, 0))
    return QtCore.QRect(point, widget.size())


def _delete_qobject(obj):
    if obj is None:
        return
    try:
        obj.deleteLater()
    except RuntimeError:
        pass


def _run_macro(_checked=False):
    try:
        rt.macros.run("FBXTo3dsMax", "FBXTo3dsMax_Open")
    except Exception:
        rt.messageBox(
            _t("无法打开 FBXTo3dsMax。请重新安装插件；如果问题仍存在，请保留安装日志。"),
            title="FBXTo3dsMax",
        )


class _ToolbarManager(object):
    """管理一个原生主工具栏按钮，并在必要时使用安全备用工具栏。"""

    def __init__(self):
        self.suspended = False
        self.shutting_down = False
        self.last_error = ""
        self.host_toolbar = None
        self.widget_action = None
        self.button = None
        self.fallback_toolbar = None
        self._retry_generation = 0
        self._retry_timers = []

    @staticmethod
    def _main_window():
        window = qtmax.GetQMaxMainWindow()
        if window is None:
            raise RuntimeError("3ds Max 主窗口尚不可用。")
        return window

    @staticmethod
    def _toolbars(main_window):
        return list(main_window.findChildren(QtWidgets.QToolBar))

    def _find_main_toolbar(self, main_window):
        candidates = [
            toolbar
            for toolbar in self._toolbars(main_window)
            if toolbar.objectName() == MAIN_TOOLBAR_OBJECT_NAME
        ]
        for toolbar in candidates:
            if toolbar.isVisible():
                return toolbar
        return None

    def _remove_action_from_toolbar(self, toolbar):
        for action in list(toolbar.actions()):
            if action.objectName() != ACTION_OBJECT_NAME:
                continue
            try:
                widget = toolbar.widgetForAction(action)
            except (AttributeError, RuntimeError):
                widget = None
            try:
                toolbar.removeAction(action)
            except RuntimeError:
                pass
            _delete_qobject(widget)
            _delete_qobject(action)

    def _remove_all_injected_actions(self, main_window):
        for toolbar in self._toolbars(main_window):
            self._remove_action_from_toolbar(toolbar)

    def _remove_toolbar(self, main_window, toolbar):
        if toolbar is None:
            return
        try:
            self._remove_action_from_toolbar(toolbar)
            main_window.removeToolBar(toolbar)
            toolbar.hide()
            toolbar.setParent(None)
            toolbar.deleteLater()
        except RuntimeError:
            pass

    def _remove_legacy_toolbars(self, main_window):
        """清理 v1.3.16 遗留的独立空栏和重复备用栏。"""

        legacy = [
            toolbar
            for toolbar in self._toolbars(main_window)
            if toolbar.objectName() == LEGACY_TOOLBAR_OBJECT_NAME
        ]
        for toolbar in legacy:
            self._remove_toolbar(main_window, toolbar)

        fallbacks = [
            toolbar
            for toolbar in self._toolbars(main_window)
            if toolbar.objectName() == FALLBACK_TOOLBAR_OBJECT_NAME
        ]
        for toolbar in fallbacks[1:]:
            self._remove_toolbar(main_window, toolbar)
        self.fallback_toolbar = fallbacks[0] if fallbacks else None

    def _prepare_icon(self):
        if not os.path.isfile(ICON_PATH):
            raise RuntimeError("工具栏图标文件不存在：{0}".format(ICON_PATH))
        icon = QtGui.QIcon(ICON_PATH)
        if icon.isNull():
            raise RuntimeError("工具栏图标无法读取：{0}".format(ICON_PATH))
        return icon

    def _make_button_action(self, host_toolbar, icon):
        action = QtWidgets.QWidgetAction(host_toolbar)
        action.setObjectName(ACTION_OBJECT_NAME)

        button = QtWidgets.QToolButton(host_toolbar)
        button.setObjectName(BUTTON_OBJECT_NAME)
        button.setText(_t(BUTTON_TEXT))
        button.setToolTip(_t(BUTTON_TOOLTIP))
        button.setStatusTip(_t(BUTTON_TOOLTIP))
        button.setIcon(icon)
        button.setIconSize(QtCore.QSize(28, 28))
        button.setToolButtonStyle(_text_beside_icon())
        button.setAutoRaise(False)
        button.setMinimumSize(QtCore.QSize(118, 34))
        button.setAccessibleName(_t(BUTTON_TEXT))
        button.setStyleSheet(
            "QToolButton {"
            " background-color: #1379c4;"
            " color: white;"
            " border: 1px solid #f0a12a;"
            " border-radius: 3px;"
            " padding: 2px 8px;"
            " font-weight: 600;"
            "}"
            "QToolButton:hover {"
            " background-color: #e58b17;"
            " border-color: #ffe0a3;"
            "}"
            "QToolButton:pressed {"
            " background-color: #0b4e82;"
            "}"
        )
        _fit_button_size(button)
        button.clicked.connect(_run_macro)
        action.setDefaultWidget(button)
        return action, button

    def _ensure_fallback_toolbar(self, main_window):
        toolbar = self.fallback_toolbar
        if toolbar is None:
            toolbar = QtWidgets.QToolBar(_t("FBXTo3dsMax 工具"), main_window)
            toolbar.setObjectName(FALLBACK_TOOLBAR_OBJECT_NAME)
            toolbar.setWindowTitle(_t("FBXTo3dsMax 工具"))
            toolbar.setMovable(True)
            toolbar.setFloatable(False)
            toolbar.setAllowedAreas(_top_toolbar_area())
            toolbar.setMinimumWidth(126)
            main_window.addToolBar(_top_toolbar_area(), toolbar)
            self.fallback_toolbar = toolbar
        elif main_window.toolBarArea(toolbar) != _top_toolbar_area():
            main_window.addToolBar(_top_toolbar_area(), toolbar)
        toolbar.show()
        toolbar.raise_()
        return toolbar

    def _discard_fallback_if_unused(self, main_window, selected_host):
        toolbar = self.fallback_toolbar
        if toolbar is not None and toolbar is not selected_host:
            self._remove_toolbar(main_window, toolbar)
            self.fallback_toolbar = None

    def install(self):
        """幂等安装按钮；新控件准备完成后才替换旧控件。"""

        if self.shutting_down:
            return {
                "ok": True,
                "skipped": True,
                "message": "3ds Max 正在退出，已跳过顶部按钮恢复。",
            }
        self.suspended = False
        main_window = self._main_window()
        self._remove_legacy_toolbars(main_window)

        main_toolbar = self._find_main_toolbar(main_window)
        # 先完成所有可能失败的准备工作，避免像 v1.3.16 那样先删旧按钮，
        # 再因图标路径异常而留下空栏。
        icon = self._prepare_icon()

        def activate(host_toolbar):
            new_action, new_button = self._make_button_action(
                host_toolbar,
                icon,
            )
            self._remove_all_injected_actions(main_window)
            host_toolbar.addAction(new_action)
            host_toolbar.show()
            host_toolbar.raise_()
            self.host_toolbar = host_toolbar
            self.widget_action = new_action
            self.button = new_button
            QtWidgets.QApplication.processEvents()
            return self.verify()

        if main_toolbar is not None:
            status = activate(main_toolbar)
            if status["ok"]:
                self._discard_fallback_if_unused(main_window, main_toolbar)
                QtWidgets.QApplication.processEvents()
                status = self.verify()
            if not status["ok"]:
                # 主工具栏可能已塞满，Qt 会把末尾控件收进不可见的扩展
                # 菜单。此时改用顶部备用栏，仍须通过同一套真实点击验证。
                status = activate(self._ensure_fallback_toolbar(main_window))
        else:
            status = activate(self._ensure_fallback_toolbar(main_window))

        if not status["ok"]:
            self._remove_all_injected_actions(main_window)
            raise RuntimeError(status["message"])
        self.last_error = ""
        return status

    def _safe_install(self):
        if self.suspended or self.shutting_down:
            return
        try:
            active_modal = getattr(
                QtWidgets.QApplication,
                "activeModalWidget",
                None,
            )
            if callable(active_modal) and active_modal() is not None:
                # 安装成功对话框自身会运行 Qt 事件循环。此时主窗口因模态
                # 状态被禁用，不能把“暂时不可点击”误判为工具栏损坏。
                return
            status = self.verify()
            if status.get("ok", False):
                return
            self.install()
        except Exception as exc:
            self.last_error = str(exc)
            print(_t("[FBXTo3dsMax] 顶部按钮延迟恢复失败；技术信息已保留在运行状态中。"))

    def _cancel_scheduled_installs(self):
        """停止并失效所有延迟恢复，防止回调在 CUI/主窗口销毁后运行。"""

        self._retry_generation += 1
        timers = list(self._retry_timers)
        self._retry_timers = []
        for timer in timers:
            try:
                timer.stop()
            except RuntimeError:
                pass
            try:
                timer.timeout.disconnect()
            except (RuntimeError, TypeError):
                pass
            _delete_qobject(timer)

    def _schedule_safe_install(self, delay):
        generation = self._retry_generation
        timer = QtCore.QTimer()
        timer.setSingleShot(True)

        def run_if_current():
            try:
                if timer in self._retry_timers:
                    self._retry_timers.remove(timer)
                if generation != self._retry_generation:
                    return
                self._safe_install()
            finally:
                try:
                    timer.timeout.disconnect(run_if_current)
                except (RuntimeError, TypeError):
                    pass
                _delete_qobject(timer)

        timer.timeout.connect(run_if_current)
        self._retry_timers.append(timer)
        timer.start(delay)

    def install_and_schedule(self):
        if self.shutting_down:
            return {
                "ok": True,
                "skipped": True,
                "message": "3ds Max 正在退出，已跳过顶部按钮恢复。",
            }
        self._cancel_scheduled_installs()
        status = None
        last_error = None
        transient_tokens = (
            "主窗口尚不可用",
            "当前不可见",
            "尺寸异常",
            "可见范围之外",
            "顶部区域",
            "遮挡",
        )
        # -U MAXScript、工作区切换和欢迎界面关闭都可能让一个临时 Qt
        # 控件短暂盖住主工具栏。仅对这些布局/遮挡状态做最多约 3 秒的
        # 有界重试；图标缺失、脚本错误等确定性故障仍立即失败。
        for attempt in range(20):
            if attempt:
                time.sleep(0.15)
                QtWidgets.QApplication.processEvents()
                try:
                    main_window = self._main_window()
                    main_window.show()
                    main_window.raise_()
                    main_window.activateWindow()
                    # 从 PowerShell / -U MAXScript 启动时，Max 可能已完成布局，
                    # 但仍被启动它的窗口盖住；此时 QApplication.widgetAt()
                    # 会正确返回 None。只在一次真实命中失败后的有界重试中
                    # 恢复并前置 Max，不在普通验证快路径中抢占焦点。
                    hwnd = int(main_window.winId())
                    user32 = ctypes.windll.user32
                    user32.ShowWindow(hwnd, 9)
                    user32.BringWindowToTop(hwnd)
                    user32.SetForegroundWindow(hwnd)
                except (AttributeError, RuntimeError, TypeError, ValueError, OSError):
                    pass
                QtWidgets.QApplication.processEvents()
            try:
                status = self.install()
                break
            except RuntimeError as exc:
                last_error = exc
                if not any(token in str(exc) for token in transient_tokens):
                    raise
        if status is None:
            if last_error is not None:
                raise last_error
            raise RuntimeError("顶部按钮在限定重试时间内没有完成安装。")
        # 工作区和 CUI 恢复中可能还有后续 Qt 布局事件。延迟重试是幂等且
        # 事务式的；它不再依赖共享作用域中的 __file__。
        for delay in (0, 250, 1000):
            self._schedule_safe_install(delay)
        return status

    def suspend(self):
        """在 CUI 保存/加载期间临时移除自定义控件，防止污染 CUIX。"""

        self._cancel_scheduled_installs()
        self.suspended = True
        try:
            main_window = self._main_window()
        except RuntimeError:
            return 0

        self._remove_all_injected_actions(main_window)
        self._remove_legacy_toolbars(main_window)
        fallback = self.fallback_toolbar
        if fallback is not None:
            self._remove_toolbar(main_window, fallback)
        self.fallback_toolbar = None
        self.host_toolbar = None
        self.widget_action = None
        self.button = None
        return 1

    def begin_shutdown(self):
        """进入 Max 退出状态；取消定时器，且禁止任何后续界面重建。"""

        if self.shutting_down:
            return 1
        self.shutting_down = True
        return self.suspend()

    def cancel_shutdown(self):
        """用户取消退出后解除停用；实际重建仍由 Bootstrap 统一触发。"""

        was_shutting_down = self.shutting_down
        self.shutting_down = False
        self.suspended = False
        return 1 if was_shutting_down else 0

    def uninstall(self):
        return self.suspend()

    def verify(self):
        """验证按钮真实位于可见顶部区域，并能接收鼠标点击。"""

        if self.shutting_down:
            return {
                "ok": True,
                "skipped": True,
                "message": "3ds Max 正在退出，已跳过顶部按钮验证。",
            }
        try:
            main_window = self._main_window()
            matches = []
            for toolbar in self._toolbars(main_window):
                for action in toolbar.actions():
                    if action.objectName() == ACTION_OBJECT_NAME:
                        matches.append((toolbar, action))
            if len(matches) != 1:
                return {
                    "ok": False,
                    "message": "顶部按钮数量异常：应为 1，实际为 {0}。".format(
                        len(matches)
                    ),
                }

            toolbar, action = matches[0]
            if toolbar.objectName() not in (
                MAIN_TOOLBAR_OBJECT_NAME,
                FALLBACK_TOOLBAR_OBJECT_NAME,
            ):
                return {
                    "ok": False,
                    "message": "顶部按钮位于未知工具栏：{0}。".format(
                        toolbar.objectName()
                    ),
                }
            button = toolbar.widgetForAction(action)
            if button is None or button.objectName() != BUTTON_OBJECT_NAME:
                return {"ok": False, "message": "顶部按钮控件不存在。"}
            if not toolbar.isVisible() or not button.isVisibleTo(main_window):
                return {"ok": False, "message": "顶部按钮当前不可见。"}
            if not button.isEnabled():
                return {"ok": False, "message": "顶部按钮当前不可点击。"}
            if button.width() < 100 or button.height() < 28:
                return {
                    "ok": False,
                    "message": "顶部按钮尺寸异常：{0}×{1}。".format(
                        button.width(), button.height()
                    ),
                }
            if button.icon().isNull():
                return {"ok": False, "message": "顶部按钮图标无效。"}
            if button.text() != _t(BUTTON_TEXT):
                return {"ok": False, "message": "顶部按钮文字不正确。"}

            button_rect = _global_rect(button)
            main_rect = _global_rect(main_window)
            if not button_rect.intersects(main_rect):
                return {"ok": False, "message": "顶部按钮位于主窗口可见范围之外。"}
            top_limit = main_rect.top() + max(180, int(main_rect.height() * 0.15))
            if button_rect.top() > top_limit:
                return {"ok": False, "message": "按钮没有位于 3ds Max 顶部区域。"}

            center = button_rect.center()
            screen = QtGui.QGuiApplication.screenAt(center)
            if screen is None or not screen.availableGeometry().contains(center):
                return {"ok": False, "message": "顶部按钮不在任何可用屏幕内。"}
            hit_widget = QtWidgets.QApplication.widgetAt(center)
            if hit_widget is None or (
                hit_widget is not button and not button.isAncestorOf(hit_widget)
            ):
                hit_description = "无控件"
                if hit_widget is not None:
                    try:
                        hit_description = "{0}/{1}".format(
                            type(hit_widget).__name__,
                            hit_widget.objectName(),
                        )
                    except (AttributeError, RuntimeError):
                        hit_description = type(hit_widget).__name__
                return {
                    "ok": False,
                    "message": (
                        "顶部按钮被其它界面遮挡，无法点击；"
                        "当前位置命中：{0}。"
                    ).format(hit_description),
                }

            host_kind = (
                "主工具栏"
                if toolbar.objectName() == MAIN_TOOLBAR_OBJECT_NAME
                else "备用工具栏"
            )
            return {
                "ok": True,
                "message": "顶部按钮验证通过。",
                "host": host_kind,
                "x": int(button_rect.x()),
                "y": int(button_rect.y()),
                "width": int(button_rect.width()),
                "height": int(button_rect.height()),
            }
        except Exception as exc:
            self.last_error = str(exc)
            return {
                "ok": False,
                "message": "顶部按钮验证异常；技术信息已保留在运行状态中。",
            }


_manager = _ToolbarManager()


def install():
    return _display_status(_manager.install())


def install_and_schedule():
    return _display_status(_manager.install_and_schedule())


def suspend():
    return _manager.suspend()


def begin_shutdown():
    return _manager.begin_shutdown()


def cancel_shutdown():
    return _manager.cancel_shutdown()


def uninstall():
    return _manager.uninstall()


def verify():
    return _display_status(_manager.verify())


def refresh_language():
    """Relabel existing widgets without creating actions, timers or scene work."""
    if not _manager.shutting_down:
        if _manager.button is not None:
            _manager.button.setText(_t(BUTTON_TEXT))
            _manager.button.setToolTip(_t(BUTTON_TOOLTIP))
            _manager.button.setStatusTip(_t(BUTTON_TOOLTIP))
            _manager.button.setAccessibleName(_t(BUTTON_TEXT))
            _fit_button_size(_manager.button)
        if _manager.fallback_toolbar is not None:
            _manager.fallback_toolbar.setWindowTitle(_t("FBXTo3dsMax 工具"))
    api = getattr(builtins, API_SLOT, None)
    if isinstance(api, dict):
        api["button_text"] = _t(BUTTON_TEXT)
        api["language"] = _language_module().get_language()
    return True


setattr(
    builtins,
    API_SLOT,
    {
        "install": install,
        "install_and_schedule": install_and_schedule,
        "suspend": suspend,
        "begin_shutdown": begin_shutdown,
        "cancel_shutdown": cancel_shutdown,
        "uninstall": uninstall,
        "verify": verify,
        "refresh_language": refresh_language,
        "script_file": SCRIPT_FILE,
        "main_toolbar_object_name": MAIN_TOOLBAR_OBJECT_NAME,
        "legacy_toolbar_object_name": LEGACY_TOOLBAR_OBJECT_NAME,
        "fallback_toolbar_object_name": FALLBACK_TOOLBAR_OBJECT_NAME,
        "action_object_name": ACTION_OBJECT_NAME,
        "button_object_name": BUTTON_OBJECT_NAME,
        "button_text": _t(BUTTON_TEXT),
        "language": _language_module().get_language(),
    },
)

_F2M_IMPORT_COMPLETE = True
