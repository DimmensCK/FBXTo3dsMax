# -*- coding: utf-8 -*-
"""Shared display language. This module never changes scene or business state.

F2M_LANGUAGE is an initial, process-local override for tests and child processes.
An explicit UI choice wins for the current process and can be saved atomically.
Only zh-CN and en are accepted; arbitrary native exception text stays diagnostic.
"""
from __future__ import annotations

import importlib.util
import os
import re
import string
import sys
import tempfile
from pathlib import Path
from typing import Dict, Optional, Tuple

TOOL_VERSION = "1.4.24"
SUPPORTED_LOCALES = ("zh-CN", "en")
MODULE_NAME = "_fbx_to_3dsmax_i18n_runtime"
REPORT_MODULE_NAME = "_f2m_report_i18n_runtime"
_session_locale: Optional[str] = None

# Stable keys and identical format fields allow UI strings to be checked without Max.
UI_TEXT: Dict[str, Tuple[str, str]] = {
    "ui.title": ("FBX 到 3ds Max 数据传递", "FBX to 3ds Max Data Transfer"),
    "ui.short_title": ("FBX 到 3ds Max", "FBX to 3ds Max"),
    "ui.language": ("语言 / Language", "语言 / Language"),
    "ui.mode": ("选择模式", "Choose Mode"),
    "ui.matching": ("模型完全一致", "Matching Models"),
    "ui.transfer": ("传递数据", "Transfer Data"),
    "ui.different": ("模型不一致", "Different Models"),
    "ui.replace": ("替换并保留蒙皮", "Replace / Keep Skin"),
    "ui.fbx": ("FBX 文件", "FBX File"),
    "ui.fbx_caption": ("FBX 文件：", "FBX file:"),
    "ui.browse": ("选择...", "Browse..."),
    "ui.check_hint": ("传递数据前优先检查 FBX", "Check the FBX before transferring"),
    "ui.check": ("检查 FBX/匹配", "Check FBX / Match"),
    "ui.shape": ("变形", "Shape"),
    "ui.material": ("材质与 ID", "Material / ID"),
    "ui.normals": ("顶点法线", "Vertex Normals"),
    "ui.uv1": ("传递 UV 1", "Transfer UV 1"),
    "ui.uv2": ("传递 UV 2", "Transfer UV 2"),
    "ui.uv3": ("传递 UV 3", "Transfer UV 3"),
    "ui.rgb": ("顶点色 RGB", "Vertex RGB"),
    "ui.alpha": ("顶点 Alpha", "Vertex Alpha"),
    "ui.smoothing": ("光滑组", "Smoothing Groups"),
    "ui.replace_group": ("替换网格并保留蒙皮", "Replace Mesh / Keep Skin"),
    "ui.replace_info": ("使用 FBX 目标网格替换所选 Max 源模型；一对一可直接匹配，其它情况按同名匹配。", "Replace the selected Max source with the FBX target mesh. A single pair matches directly; other meshes match by name."),
    "ui.skin_info": ("双方必须带 Skin。Max 源 Skin 提供场景骨骼与绑定数据；FBX 提供逐顶点权重、Unnormalized 和 DQ 数据。", "Both meshes need Skin. Max source Skin supplies scene bones and binding data; FBX supplies per-vertex weights, Unnormalized and DQ data."),
    "ui.advanced": ("高级选项...", "Advanced..."),
    "ui.hide_advanced": ("隐藏高级选项", "Hide Advanced"),
    "ui.advanced_group": ("高级选项", "Advanced Options"),
    "ui.selfcheck": ("运行插件自检", "Run Self-check"),
    "ui.backup": ("替换时隐藏备份旧网格", "Hide old mesh as backup"),
    "ui.max_material": ("兼容：改用 Max 源材质", "Use Max source material"),
    "ui.keep_import": ("保留临时导入节点用于排查", "Keep import for debug"),
    "ui.hidden": ("允许处理隐藏对象", "Include hidden objects"),
    "ui.run": ("开始执行", "Run Transfer"),
    "ui.meta": ("作者：{author}    版本：{version}", "Author: {author}    Version: {version}"),
    "ui.author_prefix": ("作者：", "Author: "),
    "ui.version_prefix": ("版本：", "Version: "),
    "ui.need_check": ("传递数据前优先检查 FBX，报告无异常后再执行；正式执行前建议保存 Max 文件。", "Check the FBX and review the report before transferring. Save your Max scene first."),
    "ui.options_changed": ("已检查当前 FBX/选择；只改变传递数据选项时可直接执行。", "This FBX and selection were checked. Transfer options can be changed without another check."),
    "ui.no_cache": ("无法取得所选节点的稳定句柄，本次检查结果不会缓存。", "Stable handles could not be read. This check will not be cached."),
    "ui.checked": ("已执行检查。请确认报告没有严重错误，再开始执行。", "Check complete. Review the report for serious errors before transferring."),
    "ui.changed": ("FBX、模式、选中对象或隐藏处理设置变化后需要重新检查。", "Check again after changing the FBX, mode, selection or hidden-object setting."),
    "ui.running": ("正在传递数据，请等待；复杂模型会在完成安全写入和回读后返回。", "Transferring data. Complex models may take time to finish writing and verification."),
    "ui.replaced": ("替换完成。Max 源模型节点已经变化；再次运行前请重新检查。", "Replacement complete. The Max source node changed; check again before another transfer."),
    "ui.transferred": ("传递完成。当前 FBX、模式和 Max 源模型未变化时，可调整传递选项后直接再次执行。", "Transfer complete. If the FBX, mode and Max source are unchanged, you may change options and run again."),
    "ui.failed": ("传递未完成。请查看报告或内部诊断；若 FBX、模式、Max 源模型和隐藏设置未变化，可修正选项后直接重试。", "Transfer did not finish. Read the report or diagnostics. If inputs are unchanged, correct the options and retry."),
    "ui.selection_failed": ("无法取得所选节点的稳定句柄。请重新选择 Max 源模型后再试。", "Stable selection handles could not be read. Select the Max source meshes again."),
    "ui.save_confirmation": ("开始执行前请确认当前 Max 文件已经保存或另存备份。\n\n同一组选中 Max 源模型只会提示一次；更换选中对象后会再次提示。\n\n是否继续？", "Save the current Max scene or a backup before transferring.\n\nThis prompt appears once per selected set of Max source models. It appears again when the selection changes.\n\nContinue?"),
    "ui.select_mesh": ("请先在 Max 场景里选中至少 1 个 Max 源模型网格。", "Select at least one Max source mesh in the scene first."),
    "ui.missing_python": ("找不到 Python 文件：\n", "Python file not found:\n"),
    "ui.select_fbx": ("请先选择一个有效的 FBX 文件。", "Choose a valid FBX file first."),
    "ui.bridge_failed": ("插件执行失败。请查看本次传递报告或内部诊断文件；如果没有生成报告，请重新安装插件。", "The plug-in could not run. Read the transfer report or diagnostics. If no report was created, reinstall the plug-in."),
    "ui.diagnostic_path": ("\n\n内部诊断文件：\n", "\n\nDiagnostic file:\n"),
    "ui.missing_selfcheck": ("找不到自检文件：\n", "Self-check file not found:\n"),
    "ui.selfcheck_title": ("FBXTo3dsMax 自检", "FBXTo3dsMax Self-check"),
    "ui.selfcheck_failed": ("无法启动插件自检。请重新安装插件；如果问题仍存在，请保留安装日志。", "The self-check could not start. Reinstall the plug-in and keep the installation log if the problem continues."),
    "ui.pick_fbx": ("选择 Maya / Blender / 其它软件导出的 FBX", "Choose an FBX exported from Maya, Blender or another application"),
    "ui.file_filter": ("FBX (*.fbx)|*.fbx|所有文件 (*.*)|*.*|", "FBX (*.fbx)|*.fbx|All files (*.*)|*.*|"),
    "ui.check_first": ("请先点击“检查 FBX/匹配”。只改变传递数据选项不需要重新检查；如果换了 FBX、模式、选中对象或隐藏处理设置，需要重新检查。", "Click Check FBX / Match first. Changing only transfer options does not need another check; changing the FBX, mode, selection or hidden-object setting does."),
    "ui.language_failed": ("无法保存或切换语言。请保留内部诊断文件。", "The language could not be saved or changed. Keep the diagnostic file."),
    "toolbar.button": ("FBX 转 MAX", "FBX to MAX"),
    "toolbar.tooltip": ("打开 FBXTo3dsMax", "Open FBXTo3dsMax"),
    "toolbar.title": ("FBXTo3dsMax 工具", "FBXTo3dsMax Tools"),
    "toolbar.open_failed": ("无法打开 FBXTo3dsMax。请重新安装插件；如果问题仍存在，请保留安装日志。", "FBXTo3dsMax could not open. Reinstall the plug-in and keep the installation log if the problem continues."),
    "toolbar.delayed_failed": ("[FBXTo3dsMax] 顶部按钮延迟恢复失败；技术信息已保留在运行状态中。", "[FBXTo3dsMax] Toolbar recovery failed; diagnostic details are retained in runtime state."),
    "toolbar.shutdown_restore": ("3ds Max 正在退出，已跳过顶部按钮恢复。", "3ds Max is shutting down; toolbar recovery was skipped."),
    "toolbar.shutdown_verify": ("3ds Max 正在退出，已跳过顶部按钮验证。", "3ds Max is shutting down; toolbar verification was skipped."),
    "toolbar.main_unavailable": ("3ds Max 主窗口尚不可用。", "The 3ds Max main window is not available yet."),
    "toolbar.main_missing": ("找不到 3ds Max 主工具栏。", "The 3ds Max main toolbar could not be found."),
    "toolbar.button_missing": ("顶部按钮控件不存在。", "The toolbar button widget is missing."),
    "toolbar.invisible": ("顶部按钮当前不可见。", "The toolbar button is not currently visible."),
    "toolbar.disabled": ("顶部按钮当前不可点击。", "The toolbar button is currently disabled."),
    "toolbar.icon_invalid": ("顶部按钮图标无效。", "The toolbar button icon is invalid."),
    "toolbar.text_invalid": ("顶部按钮文字不正确。", "The toolbar button text is incorrect."),
    "toolbar.outside": ("顶部按钮位于主窗口可见范围之外。", "The toolbar button is outside the visible main window."),
    "toolbar.not_top": ("按钮没有位于 3ds Max 顶部区域。", "The button is outside the top area of 3ds Max."),
    "toolbar.offscreen": ("顶部按钮不在任何可用屏幕内。", "The toolbar button is outside the available screens."),
    "toolbar.main_host": ("主工具栏", "Main Toolbar"),
    "toolbar.fallback_host": ("备用工具栏", "Fallback Toolbar"),
    "toolbar.verified": ("顶部按钮验证通过。", "Toolbar button verified."),
    "toolbar.verify_exception": ("顶部按钮验证异常；技术信息已保留在运行状态中。", "Toolbar verification failed; diagnostic details are retained in runtime state."),
    "toolbar.icon_missing": ("工具栏图标文件不存在：{path}", "Toolbar icon file is missing: {path}"),
    "toolbar.icon_unreadable": ("工具栏图标无法读取：{path}", "Toolbar icon could not be read: {path}"),
    "toolbar.retry_failed": ("顶部按钮在限定重试时间内没有完成安装。", "The toolbar button could not be installed within the bounded retry period."),
    "toolbar.count": ("顶部按钮数量异常：应为 1，实际为 {count}。", "Toolbar button count is incorrect: expected 1, found {count}."),
    "toolbar.host": ("顶部按钮位于未知工具栏：{host}。", "The button is on an unknown toolbar: {host}."),
    "toolbar.size": ("顶部按钮尺寸异常：{width}×{height}。", "Toolbar button size is incorrect: {width} x {height}."),
    "toolbar.occluded": ("顶部按钮被其它界面遮挡，无法点击；当前位置命中：{widget}。", "The toolbar button is covered and cannot be clicked; the current hit is {widget}."),
    "macro.missing": ("FBXTo3dsMax 安装不完整。\n\n缺少文件：\n{path}\n\n请重新运行 Install_FBXTo3dsMax.ms。", "The FBXTo3dsMax installation is incomplete.\n\nMissing file:\n{path}\n\nRun Install_FBXTo3dsMax.ms again."),
}
CATALOG = {source: target for source, target in UI_TEXT.values()}


def _locale(value: str) -> str:
    if value not in SUPPORTED_LOCALES:
        raise ValueError("Unsupported FBXTo3dsMax language: " + repr(value))
    return value


def language_file() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise RuntimeError("LOCALAPPDATA is required for language preferences")
    return Path(base).resolve() / "FBXTo3dsMax" / "language.txt"


def get_language() -> str:
    if _session_locale is not None:
        return _session_locale
    override = os.environ.get("F2M_LANGUAGE")
    if override is not None:
        return _locale(override)
    try:
        with language_file().open("rb") as handle:
            data = handle.read(65)
        if len(data) > 64:
            return "zh-CN"
        return _locale(data.decode("utf-8-sig").strip())
    except (OSError, UnicodeError, ValueError):
        return "zh-CN"


def set_language(locale: str, persist: bool = True) -> str:
    global _session_locale
    chosen = _locale(locale)
    if persist:
        destination = language_file()
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".language-", suffix=".tmp", dir=str(destination.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(chosen + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, str(destination))
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    _session_locale = chosen
    return chosen


def text(key: str, locale: Optional[str] = None, **values: object) -> str:
    chosen = _locale(locale) if locale is not None else get_language()
    source, target = UI_TEXT[key]
    return (target if chosen == "en" else source).format(**values)


def ui_catalog_sources() -> Tuple[str, ...]:
    return tuple(CATALOG)


def ui_catalog_english() -> Tuple[str, ...]:
    return tuple(CATALOG.values())


def _template_translation(value: str) -> Optional[str]:
    formatter = string.Formatter()
    for source, target in UI_TEXT.values():
        fields = [name for _, name, _, _ in formatter.parse(source) if name is not None]
        if not fields:
            continue
        chunks = []
        for literal, name, _, _ in formatter.parse(source):
            chunks.append(re.escape(literal))
            if name is not None:
                chunks.append("(?P<" + name + ">.*?)")
        match = re.fullmatch("".join(chunks), value, re.DOTALL)
        if match:
            return target.format(**match.groupdict())
    return None


def _report_translator():
    path = Path(__file__).resolve().with_name("f2m_report_i18n.py")
    if not path.is_file():
        return None
    module = sys.modules.get(REPORT_MODULE_NAME)
    expected = os.path.normcase(str(path))
    if not (module is not None
            and os.path.normcase(os.path.abspath(getattr(module, "__file__", "") or "")) == expected
            and getattr(module, "TOOL_VERSION", None) == TOOL_VERSION
            and getattr(module, "_F2M_IMPORT_COMPLETE", False) is True
            and callable(getattr(module, "translate_english", None))):
        sys.modules.pop(REPORT_MODULE_NAME, None)
        spec = importlib.util.spec_from_file_location(REPORT_MODULE_NAME, str(path))
        if spec is None or spec.loader is None:
            raise RuntimeError("Cannot create the report language loader")
        module = importlib.util.module_from_spec(spec)
        sys.modules[REPORT_MODULE_NAME] = module
        try:
            spec.loader.exec_module(module)
            if (os.path.normcase(os.path.abspath(module.__file__)) != expected
                    or getattr(module, "TOOL_VERSION", None) != TOOL_VERSION
                    or getattr(module, "_F2M_IMPORT_COMPLETE", False) is not True
                    or not callable(getattr(module, "translate_english", None))):
                raise RuntimeError("Report language module identity/version/API mismatch")
        except BaseException:
            if sys.modules.get(REPORT_MODULE_NAME) is module:
                sys.modules.pop(REPORT_MODULE_NAME, None)
            raise
    return module.translate_english


def translate(value: object, locale: Optional[str] = None) -> str:
    """Translate display text only; callers retain their original business values."""
    chosen = _locale(locale) if locale is not None else get_language()
    value = str(value)
    if chosen == "zh-CN":
        return value
    if value in CATALOG:
        return CATALOG[value]
    rendered = _template_translation(value)
    if rendered is not None:
        return rendered
    render_report = _report_translator()
    return str(render_report(value)) if render_report is not None else value


_F2M_IMPORT_COMPLETE = True
