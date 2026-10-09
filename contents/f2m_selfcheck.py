# -*- coding: utf-8 -*-
"""FBXTo3dsMax 的隔离式自检运行器。

交互插件会启动独立的 3dsmaxbatch.exe，确保自检不会重置或修改用户当前
打开的场景。
"""

from __future__ import annotations

import gc
import hashlib
import importlib.util
import json
import os
import re
import glob
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
import builtins
import atexit
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional

try:
    import pymxs  # type: ignore

    rt = pymxs.runtime
except Exception:
    rt = None


TOOL_VERSION = "1.4.25"
ROOT = os.path.dirname(os.path.abspath(__file__))
CHILD_ENV = "F2M_SELFCHECK_CHILD"
RESULT_ENV = "F2M_SELFCHECK_RESULT"
PROGRESS_ENV = "F2M_SELFCHECK_PROGRESS"
CANCEL_ENV = "F2M_SELFCHECK_CANCEL"
CONTROLLER_SLOT = "_FBXTO3DSMAX_SELFCHECK_CONTROLLER"
SELF_CHECK_TIMEOUT_SECONDS = 300
SELF_CHECK_EXIT_GRACE_SECONDS = 5
EXPECTED_INSTALL_MANIFEST_COUNT = 32
MAX_LOG_PATH_ENV = "F2M_SELFCHECK_MAX_LOG"
MAX_LOG_TIME_SLOP_SECONDS = 3.0
MAX_LOG_TAIL_FINGERPRINT_BYTES = 256
MAX_LOG_RETAINED_ERROR_LINES = 20
MAX_LOG_GC_MARKERS = (
    "maxscript 内存收集错误",
    "maxscript garbage collection error",
    "maxscript garbage collector error",
    "maxscript gc error",
)
MAX_LOG_PREFIX = re.compile(
    r"^(?P<stamp>\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})"
    r"\s+\S+:\s+\[(?P<pid>\d+)\]"
)


def _language_runtime() -> Any:
    """Load the exact sibling presentation module; reject stale/foreign copies."""
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "f2m_i18n.py"))
    name = "_fbx_to_3dsmax_i18n_runtime"
    module = sys.modules.get(name)
    def valid(value: Any) -> bool:
        return bool(value is not None
            and os.path.normcase(os.path.abspath(str(getattr(value, "__file__", "")))) == os.path.normcase(path)
            and str(getattr(value, "TOOL_VERSION", "")) == TOOL_VERSION
            and getattr(value, "_F2M_IMPORT_COMPLETE", False) is True
            and callable(getattr(value, "translate", None))
            and callable(getattr(value, "get_language", None)))
    if not valid(module):
        sys.modules.pop(name, None)
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Cannot load the plug-in language module: " + path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
            if not valid(module):
                raise RuntimeError("Plug-in language module identity/version/API mismatch: " + path)
        except BaseException:
            if sys.modules.get(name) is module:
                sys.modules.pop(name, None)
            raise
    return module


def _display_text(text: Any) -> str:
    return str(_language_runtime().translate(str(text or "")))


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    elapsed_ms: int
    diagnostic: str = ""


class SelfCheckCancelled(RuntimeError):
    """只在隔离子进程收到协作式取消请求后抛出。"""


class SelfCheckCaseFailure(RuntimeError):
    """携带只写内部诊断报告的原始自检技术信息。"""

    def __init__(self, message: str, diagnostic: str = "") -> None:
        super().__init__(message)
        self.diagnostic = str(diagnostic or "")


def _localize_visible_text(value: Any) -> str:
    """在已知回归标签进入用户报告前将其转换为中文。"""

    text = str(value or "").strip()
    if _language_runtime().get_language() == "en":
        return _display_text(text)
    replacements = (
        ("plain:", "普通自动法线："),
        ("inverse_transpose:", "法线逆转置："),
        ("upper_override:", "上层法线覆盖："),
        ("hybrid:", "光滑组与显式法线共存："),
        ("plain mesh rejected; selection and temporary stack restored", "普通自动法线已正确拒绝；选择与临时修改器栈均已恢复"),
        ("inverse-transpose rotation/non-uniform-scale delta=", "逆转置旋转/非均匀缩放误差="),
        ("user Edit Normals interference detected; F2M state rolled back", "已检测用户的“编辑法线”修改器干扰；F2M 状态已回滚"),
        ("SG1 + local Explicit normal coexist and survive save/reload", "光滑组 1 与局部显式法线可共存，并在保存/重新载入后保持"),
        ("soft-edge", "软边"),
        ("hard-edge", "硬边"),
        ("bit-32", "第 32 位"),
        ("deterministic", "确定性"),
        ("group-overflow-fail-closed", "组数溢出时安全停止"),
        ("non-manifold-fail-closed", "非流形时安全停止"),
        ("Binary FBX", "二进制 FBX"),
        (": PASS - ", "：通过——"),
        (": FAIL", "：失败"),
        ("PASS", "通过"),
        ("FAIL", "失败"),
    )
    for source, target in replacements:
        text = text.replace(source, target)
    # 允许品牌、格式、通道及程序标识；其它连续英文单词视为未本地化的
    # 底层信息，不进入普通报告。完整原文仍在 Check.diagnostic 中。
    allowed = (
        "FBXTo3dsMax",
        "F2M",
        "LayerElementSmoothing",
        "inverse_transpose",
        "upper_override",
        "ChannelInfo",
        "Editable",
        "MAXScript",
        "BoneID",
        "Explicit",
        "Specified",
        "Normals",
        "Normal",
        "Blender",
        "Autodesk",
        "Python",
        "DSATUR",
        "Binary",
        "Mesh",
        "Poly",
        "Skin",
        "Alpha",
        "RGB",
        "SHA",
        "FBX",
        "Max",
        "UV",
        "DQ",
        "ID",
    )
    residual = text
    for token in allowed:
        residual = re.sub(re.escape(token), "", residual, flags=re.IGNORECASE)
    # 路径和 Python 文件名是技术标识，不属于界面语言。
    residual = re.sub(r"[A-Za-z]:[\\/][^\r\n]*", "", residual)
    residual = re.sub(r"\b[\w.-]+\.py\b", "", residual, flags=re.IGNORECASE)
    if re.search(r"[A-Za-z]{2,}", residual):
        return text
    return text


def _atomic_write_json(path: str, value: Dict[str, Any]) -> None:
    """原子写入进程交接状态，不暴露未写完的 JSON。"""

    destination = os.path.abspath(path)
    parent = os.path.dirname(destination)
    if not parent:
        raise ValueError("进度文件必须具有父目录。")
    os.makedirs(parent, exist_ok=True)
    temporary = destination + ".tmp-" + uuid.uuid4().hex
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        try:
            if os.path.exists(temporary):
                os.remove(temporary)
        except OSError:
            pass


def _read_json_if_ready(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def _atomic_write_text(path: str, value: str) -> None:
    """原子写入父控制器追加的最终自检判定。"""

    destination = os.path.abspath(path)
    parent = os.path.dirname(destination)
    if not parent:
        raise ValueError("报告文件必须具有父目录。")
    os.makedirs(parent, exist_ok=True)
    temporary = destination + ".tmp-" + uuid.uuid4().hex
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        try:
            if os.path.exists(temporary):
                os.remove(temporary)
        except OSError:
            pass


def _find_max_log_path() -> str:
    """定位与当前 3ds Max 用户配置对应的共享原生日志。"""

    override = str(os.environ.get(MAX_LOG_PATH_ENV, "") or "").strip()
    if override:
        return os.path.abspath(override)

    if rt is not None:
        try:
            max_data = str(rt.getDir(rt.Name("maxData")))
            if max_data:
                return os.path.abspath(os.path.join(max_data, "Network", "Max.log"))
        except Exception:
            pass

    local_root = str(os.environ.get("LOCALAPPDATA", "") or "").strip()
    if not local_root:
        return ""
    pattern = os.path.join(
        local_root,
        "Autodesk",
        "3dsMax",
        "*",
        "*",
        "Network",
        "Max.log",
    )
    candidates = [
        os.path.abspath(path)
        for path in glob.glob(pattern)
        if os.path.isfile(path)
    ]
    if not candidates:
        return ""
    return max(candidates, key=lambda path: os.path.getmtime(path))


def _capture_max_log_checkpoint(path: str = "") -> Dict[str, Any]:
    """在启动 Batch 前记录日志边界，避免把历史错误算入本次自检。"""

    candidate = path or _find_max_log_path()
    resolved = os.path.abspath(candidate) if candidate else ""
    checkpoint: Dict[str, Any] = {
        "path": resolved,
        "captured_at": time.time(),
        "existed": False,
        "offset": 0,
        "identity": [],
        "tail_start": 0,
        "tail_sha256": "",
        "capture_error": "",
    }
    if not resolved:
        checkpoint["capture_error"] = "无法定位 3ds Max 原生日志。"
        return checkpoint

    try:
        stat_result = os.stat(resolved)
    except FileNotFoundError:
        return checkpoint
    except OSError as exc:
        checkpoint["capture_error"] = f"无法读取原生日志启动边界：{exc}"
        return checkpoint

    offset = max(0, int(stat_result.st_size))
    tail_start = max(0, offset - MAX_LOG_TAIL_FINGERPRINT_BYTES)
    try:
        with open(resolved, "rb") as handle:
            handle.seek(tail_start)
            tail = handle.read(offset - tail_start)
    except OSError as exc:
        checkpoint["capture_error"] = f"无法读取原生日志启动边界：{exc}"
        return checkpoint

    checkpoint.update(
        {
            "existed": True,
            "offset": offset,
            "identity": [
                int(getattr(stat_result, "st_dev", 0)),
                int(getattr(stat_result, "st_ino", 0)),
            ],
            "tail_start": tail_start,
            "tail_sha256": hashlib.sha256(tail).hexdigest(),
        }
    )
    return checkpoint


def _decode_max_log(data: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _max_log_line_epoch(stamp: str) -> Optional[float]:
    try:
        return time.mktime(time.strptime(stamp, "%Y/%m/%d %H:%M:%S"))
    except (OverflowError, ValueError):
        return None


def _inspect_max_log_since(
    checkpoint: Dict[str, Any],
    *,
    child_pid: int,
    process_started_at: float,
    process_finished_at: float,
) -> Dict[str, Any]:
    """只检查本次 Batch PID 在启动边界之后、退出完成之前写入的日志。"""

    path = os.path.abspath(str(checkpoint.get("path", "") or "")) if checkpoint else ""
    audit: Dict[str, Any] = {
        "checked": False,
        "path": path,
        "child_pid": int(child_pid),
        "checkpoint_captured_at": float(
            checkpoint.get("captured_at", 0.0) or 0.0
        ),
        "process_started_at": float(process_started_at),
        "process_finished_at": float(process_finished_at),
        "time_slop_seconds": MAX_LOG_TIME_SLOP_SECONDS,
        "captured_offset": int(checkpoint.get("offset", 0) or 0),
        "effective_offset": 0,
        "end_offset": 0,
        "pid_line_count": 0,
        "gc_error_count": 0,
        "gc_error_lines": [],
        "error": "",
    }
    if not path:
        audit["error"] = "无法定位 3ds Max 原生日志。"
        return audit
    if int(child_pid) <= 0:
        audit["error"] = "自检子进程 PID 无效。"
        return audit

    try:
        stat_result = os.stat(path)
        end_offset = max(0, int(stat_result.st_size))
        effective_offset = 0
        if bool(checkpoint.get("existed", False)):
            captured_offset = max(0, int(checkpoint.get("offset", 0) or 0))
            captured_identity = tuple(int(value) for value in checkpoint.get("identity", []))
            current_identity = (
                int(getattr(stat_result, "st_dev", 0)),
                int(getattr(stat_result, "st_ino", 0)),
            )
            identity_matches = (
                len(captured_identity) == 2
                and captured_identity == current_identity
            )
            if identity_matches and end_offset >= captured_offset:
                tail_start = max(0, int(checkpoint.get("tail_start", 0) or 0))
                with open(path, "rb") as handle:
                    handle.seek(tail_start)
                    previous_tail = handle.read(captured_offset - tail_start)
                if (
                    hashlib.sha256(previous_tail).hexdigest()
                    == str(checkpoint.get("tail_sha256", ""))
                ):
                    effective_offset = captured_offset

        with open(path, "rb") as handle:
            handle.seek(effective_offset)
            new_bytes = handle.read()
    except OSError as exc:
        audit["error"] = f"无法读取 3ds Max 原生日志：{exc}"
        return audit

    audit["effective_offset"] = effective_offset
    audit["end_offset"] = end_offset
    lower_bound = float(process_started_at) - MAX_LOG_TIME_SLOP_SECONDS
    upper_bound = float(process_finished_at) + MAX_LOG_TIME_SLOP_SECONDS
    gc_lines: List[str] = []
    gc_error_count = 0
    pid_line_count = 0
    for raw_line in _decode_max_log(new_bytes).splitlines():
        match = MAX_LOG_PREFIX.match(raw_line.strip())
        if match is None or int(match.group("pid")) != int(child_pid):
            continue
        line_epoch = _max_log_line_epoch(match.group("stamp"))
        if line_epoch is not None and not (lower_bound <= line_epoch <= upper_bound):
            continue
        pid_line_count += 1
        folded = raw_line.casefold()
        if any(marker in folded for marker in MAX_LOG_GC_MARKERS):
            gc_error_count += 1
            if len(gc_lines) < MAX_LOG_RETAINED_ERROR_LINES:
                gc_lines.append(raw_line.strip())

    audit["pid_line_count"] = pid_line_count
    audit["gc_error_count"] = gc_error_count
    audit["gc_error_lines"] = gc_lines
    if pid_line_count < 1:
        audit["error"] = (
            "本次新增日志中没有找到该自检子进程的 PID，"
            "无法确认读取的是正确原生日志。"
        )
        return audit
    audit["checked"] = True
    return audit


def _prepend_native_log_failure_to_report(
    result: Dict[str, Any],
    audit: Dict[str, Any],
) -> str:
    """让子进程先写出的业务报告同步反映父控制器的最终失败判定。"""

    report_path = os.path.abspath(str(result.get("report_path", "") or ""))
    if not report_path or not os.path.isfile(report_path):
        return ""
    marker = "【父控制器最终判定】"
    display_marker = _display_text(marker)
    english_marker = str(_language_runtime().translate(marker, locale="en"))
    with open(report_path, "r", encoding="utf-8-sig") as handle:
        original = handle.read()
    if original.startswith((marker, english_marker)):
        return report_path

    if bool(audit.get("checked", False)):
        reason = (
            "独立 3ds Max 子进程完全退出后，在本次新增的原生日志中发现 "
            f"{int(audit.get('gc_error_count', 0))} 条 MAXScript 内存收集错误。"
        )
    else:
        reason = (
            "无法核验本次独立 3ds Max 子进程的原生日志，"
            "不能确认没有 MAXScript 内存收集错误。"
        )
    prefix = (
        display_marker
        + "\n"
        + _display_text("自检失败：")
        + _display_text(str(reason))
        + "\n"
        + _display_text("原生日志：")
        + (str(audit.get("path", "")) if audit.get("path") else _display_text("未找到"))
        + "\n"
        + _display_text("说明：下方六项业务检查结果不能覆盖上述原生进程错误。")
        + "\n"
        + "=" * 72
        + "\n\n"
    )
    _atomic_write_text(report_path, prefix + original)
    return report_path


def _apply_native_max_log_gate(
    result: Dict[str, Any],
    audit: Dict[str, Any],
) -> Dict[str, Any]:
    """原生日志不可核验或出现 GC 错误时，不允许业务 JSON 保持绿色。"""

    final = dict(result)
    business_ok = bool(final.get("ok", False))
    final["business_result_ok"] = business_ok
    final["native_max_log_audit"] = dict(audit)
    final["native_max_log_path"] = str(audit.get("path", "") or "")
    final["native_max_log_checked"] = bool(audit.get("checked", False))
    final["native_max_log_gc_error_count"] = int(
        audit.get("gc_error_count", 0) or 0
    )

    native_summary = ""
    if bool(audit.get("checked", False)) and int(audit.get("gc_error_count", 0)) > 0:
        native_summary = (
            "独立 3ds Max 子进程完全退出后，在本次新增的原生日志中发现 "
            f"{int(audit.get('gc_error_count', 0))} 条 MAXScript 内存收集错误。"
        )
    elif not bool(audit.get("checked", False)) and business_ok:
        native_summary = (
            "无法核验本次独立 3ds Max 子进程的原生日志，"
            "不能确认没有 MAXScript 内存收集错误。"
        )

    if native_summary:
        prior_summary = str(final.get("summary", "") or "").strip()
        final["ok"] = False
        final["summary"] = (
            "自检失败："
            + native_summary
            + (
                "\n原业务检查摘要：" + _localize_visible_text(prior_summary)
                if prior_summary
                else ""
            )
        )
        final["native_max_log_failure"] = True
        try:
            _prepend_native_log_failure_to_report(final, audit)
        except Exception as exc:
            final["native_max_log_report_update_error"] = str(exc)
    else:
        final["native_max_log_failure"] = False
    return final


def _prepend_process_exit_failure_to_report(
    result: Dict[str, Any],
    reason: str,
) -> str:
    """Prepend the parent process-exit verdict without discarding the child report."""

    report_path = os.path.abspath(str(result.get("report_path", "") or ""))
    if not report_path or not os.path.isfile(report_path):
        return ""
    marker = "【父控制器进程退出门禁】"
    display_marker = _display_text(marker)
    english_marker = str(_language_runtime().translate(marker, locale="en"))
    with open(report_path, "r", encoding="utf-8-sig") as handle:
        original = handle.read()
    if original.startswith((marker, english_marker)):
        return report_path
    prefix = (
        display_marker
        + "\n"
        + _display_text("自检失败：")
        + _display_text(str(reason))
        + "\n"
        + _display_text("说明：下方保留子进程原始业务报告及其它父控制器门禁信息。")
        + "\n"
        + "=" * 72
        + "\n\n"
    )
    _atomic_write_text(report_path, prefix + original)
    return report_path


def _apply_process_exit_gate(
    result: Dict[str, Any],
    *,
    return_code: Optional[int],
    completion_stop_requested: bool,
) -> Dict[str, Any]:
    """Require a natural, zero-code Batch exit before any result can stay green."""

    final = dict(result)
    forced_after_result = bool(completion_stop_requested)
    exit_observed = return_code is not None
    exit_code = int(return_code) if exit_observed else None
    natural_exit = bool(exit_observed and not forced_after_result)
    gate_passed = bool(natural_exit and exit_code == 0)

    final["child_process_exit_observed"] = exit_observed
    final["child_process_exit_code"] = exit_code
    final["child_process_completion_stop_requested"] = forced_after_result
    final["child_process_natural_exit"] = natural_exit
    final["child_process_exit_gate_passed"] = gate_passed
    final["child_process_exit_failure"] = not gate_passed
    if gate_passed:
        return final

    if forced_after_result:
        reason = (
            "独立 3ds Max Batch 在业务结果生成后触发了强制结束，"
            "不能把该业务结果视为真实完成。"
        )
    elif not exit_observed:
        reason = "没有观察到独立 3ds Max Batch 完全退出。"
    else:
        reason = (
            "独立 3ds Max Batch 未以退出代码 0 完成"
            f"（实际退出代码 {exit_code}）。"
        )

    prior_summary = str(final.get("summary", "") or "").strip()
    final["ok"] = False
    final["summary"] = (
        "自检失败："
        + reason
        + (
            "\n原业务检查摘要：" + _localize_visible_text(prior_summary)
            if prior_summary
            else ""
        )
    )
    try:
        _prepend_process_exit_failure_to_report(final, reason)
    except Exception as exc:
        final["child_process_exit_report_update_error"] = str(exc)
    return final


def _publish_progress(
    path: str,
    *,
    state: str,
    completed: int,
    total: int,
    current_name: str,
    started_at: float,
    last_detail: str = "",
) -> None:
    _atomic_write_json(
        path,
        {
            "state": state,
            "completed": int(completed),
            "total": int(total),
            "current_name": str(current_name),
            "last_detail": _localize_visible_text(last_detail),
            "elapsed_seconds": max(0, int(time.time() - started_at)),
            "child_pid": os.getpid(),
            "updated_at": time.time(),
        },
    )


def _write_framework_diagnostic(result_path: str, diagnostic: str) -> str:
    """Persist an uncaught framework traceback before the result JSON is consumed."""

    stem, _extension = os.path.splitext(os.path.abspath(result_path))
    path = stem + "_内部诊断.txt"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(
            "FBXTo3dsMax 自检框架内部诊断\n"
            "说明：此文件供定位自检框架错误使用。\n"
            + "=" * 72
            + "\n"
            + str(diagnostic).rstrip()
            + "\n"
        )
    return path


def _validate_child_environment() -> Dict[str, str]:
    """拒绝在用户的交互式 Max 进程中误执行完整自检。"""

    if os.environ.get(CHILD_ENV) != "1":
        raise RuntimeError("已拒绝在当前交互式 3ds Max 场景中直接运行完整自检。")
    result_path = os.environ.get(RESULT_ENV, "")
    if not result_path or not os.path.isabs(result_path):
        raise RuntimeError("自检子进程缺少有效的绝对结果文件路径。")
    values = {
        "result": result_path,
        # Keep command-line release verification compatible while the
        # interactive controller always provides explicit unique paths.
        "progress": os.environ.get(PROGRESS_ENV) or result_path + ".progress.json",
        "cancel": os.environ.get(CANCEL_ENV) or result_path + ".cancel.json",
    }
    for label, value in values.items():
        if not value or not os.path.isabs(value):
            raise RuntimeError(f"自检子进程缺少有效的绝对路径参数：{label}。")
    return values


def _load_local(filename: str, module_name: str) -> Any:
    path = os.path.abspath(os.path.join(ROOT, filename))
    # Source tests live beside contents; installed tests live inside contents.
    # Only that fixed test subtree may use the repository parent.
    if (not os.path.isfile(path)
            and filename.replace("\\", "/").startswith("tests/")):
        path = os.path.abspath(os.path.join(os.path.dirname(ROOT), filename))
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法为 {path} 创建模块加载器。")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if sys.modules.get(module_name) is module:
            sys.modules.pop(module_name, None)
        raise
    setattr(module, "_F2M_IMPORT_COMPLETE", True)
    actual = os.path.normcase(os.path.abspath(module.__file__))
    if actual != os.path.normcase(path):
        raise RuntimeError(f"模块来源不一致：{actual} != {path}")
    return module


def _report_folder() -> str:
    root = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    folder = os.path.join(root, "FBXTo3dsMax", "SelfCheck", time.strftime("%Y-%m-%d"))
    os.makedirs(folder, exist_ok=True)
    return folder


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_installed_manifest() -> str:
    manifest = os.path.join(ROOT, "FBXTo3dsMax.install-manifest.sha256")
    if not os.path.isfile(manifest):
        return "源码运行：未发现安装后 SHA-256 清单，跳过该项。"

    package_root = os.path.abspath(os.path.dirname(ROOT))
    source_manifest = os.path.join(ROOT, "FBXTo3dsMax.files")
    if not os.path.isfile(source_manifest):
        raise RuntimeError("安装清单验证失败：缺少 FBXTo3dsMax.files。")

    expected_targets: Dict[str, str] = {}
    mismatches: List[str] = []
    with open(source_manifest, "r", encoding="utf-8-sig") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|", 1)
            if len(parts) != 2:
                mismatches.append(
                    f"源清单第 {line_number} 行格式错误"
                )
                continue
            relative = parts[1].strip().replace("/", "\\")
            key = os.path.normcase(os.path.normpath(relative))
            if (
                not relative
                or os.path.isabs(relative)
                or key == os.pardir
                or key.startswith(os.pardir + os.sep)
            ):
                mismatches.append(
                    f"源清单第 {line_number} 行目标路径无效：{relative}"
                )
                continue
            if key in expected_targets:
                mismatches.append(f"源清单目标路径重复：{relative}")
                continue
            expected_targets[key] = relative

    if len(expected_targets) != EXPECTED_INSTALL_MANIFEST_COUNT:
        mismatches.append(
            "源清单目标数量错误："
            f"期望 {EXPECTED_INSTALL_MANIFEST_COUNT}，"
            f"实际 {len(expected_targets)}"
        )

    records: Dict[str, str] = {}
    with open(manifest, "r", encoding="utf-8-sig") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split("|", 1)
            if len(parts) != 2:
                mismatches.append(f"第 {line_number} 行格式错误")
                continue
            relative = parts[0].strip().replace("/", "\\")
            expected = parts[1].strip().lower()
            key = os.path.normcase(os.path.normpath(relative))
            if key in records:
                mismatches.append(f"目标路径重复：{relative}")
                continue
            records[key] = relative
            if re.fullmatch(r"[0-9a-f]{64}", expected) is None:
                mismatches.append(f"第 {line_number} 行 SHA-256 格式错误")
                continue
            path = os.path.abspath(os.path.join(package_root, relative.replace("\\", os.sep)))
            try:
                if os.path.normcase(
                    os.path.commonpath((package_root, path))
                ) != os.path.normcase(package_root):
                    mismatches.append(f"越界路径：{relative}")
                    continue
            except ValueError:
                mismatches.append(f"无效路径：{relative}")
                continue
            if not os.path.isfile(path):
                mismatches.append(f"缺失：{relative}")
            elif _sha256(path).lower() != expected:
                mismatches.append(f"哈希不一致：{relative}")

    if len(records) != EXPECTED_INSTALL_MANIFEST_COUNT:
        mismatches.append(
            "安装后清单记录数量错误："
            f"期望 {EXPECTED_INSTALL_MANIFEST_COUNT}，实际 {len(records)}"
        )
    missing_targets = sorted(set(expected_targets) - set(records))
    extra_targets = sorted(set(records) - set(expected_targets))
    if missing_targets:
        mismatches.append(
            "安装后清单缺少目标："
            + ", ".join(expected_targets[key] for key in missing_targets[:6])
        )
    if extra_targets:
        mismatches.append(
            "安装后清单包含未知目标："
            + ", ".join(records[key] for key in extra_targets[:6])
        )
    if mismatches:
        raise RuntimeError("安装清单验证失败：" + "；".join(mismatches[:12]))
    return (
        "安装后哈希清单 "
        f"{EXPECTED_INSTALL_MANIFEST_COUNT} 项全部匹配，"
        "目标集合与安装源清单完全一致。"
    )


def _run_case(name: str, callback: Callable[[], str]) -> Check:
    started = time.perf_counter()
    try:
        detail = _localize_visible_text(callback() or "通过")
        return Check(name=name, ok=True, detail=detail, elapsed_ms=int((time.perf_counter() - started) * 1000))
    except BaseException as exc:
        diagnostic = str(getattr(exc, "diagnostic", "") or "").strip()
        current_traceback = traceback.format_exc().strip()
        if diagnostic:
            diagnostic = diagnostic + "\n\n[自检调用位置]\n" + current_traceback
        else:
            diagnostic = current_traceback
        return Check(
            name=name,
            ok=False,
            detail=_localize_visible_text(str(exc) or "发生未说明的异常。"),
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            diagnostic=diagnostic,
        )


def _require_runtime() -> None:
    if rt is None:
        raise RuntimeError("自检必须由 3ds Max / 3ds Max Batch 运行。")


def _reset_max_file_safely() -> None:
    """Reset the isolated scene without dismantling live modifier stacks."""

    _require_runtime()
    try:
        rt.clearSelection()
    except Exception:
        pass
    rt.resetMaxFile(rt.Name("noPrompt"))
    if len(rt.objects) != 0:
        raise RuntimeError("自检场景重置后仍有节点残留。")


def _validate_ui_bridge_source(ui_text: str) -> None:
    """锁定 MAXScript/Python 三态桥及中文内部诊断的生产语义。"""

    if re.search(r"\bpython\.eval\b", ui_text, flags=re.IGNORECASE):
        raise RuntimeError(
            "界面使用了 3ds Max Python 核心接口不支持的 Eval 方法。"
        )

    bridge_requirements = {
        "三态全局变量声明": "global F2M_UI_RunStatus",
        "业务结果读取": (
            "__f2m_run_ok = bool(getattr(_f2m_module, "
            "'LAST_RUN_OK', False))"
        ),
        "严格的 1/0 回写": (
            "globalVars.set(_f2m_bridge_rt.Name('F2M_UI_RunStatus'), "
            "1 if __f2m_run_ok else 0)"
        ),
        "成功状态读回": "succeeded = (F2M_UI_RunStatus == 1)",
        "界面诊断函数": "fn writeUiDiagnostic errorText",
        "异常详情传入诊断函数": (
            "local uiDiagnostic = writeUiDiagnostic uiException"
        ),
        "中文诊断标题": "FBXTo3dsMax 界面内部诊断",
        "用户诊断目录": "FBXTo3dsMax\\\\Diagnostics\\\\",
        "中文诊断文件名": "_内部诊断.txt",
        "UTF-8 编码器": 'dotNetObject "System.Text.UTF8Encoding" false',
        "UTF-8 诊断写入": (
            "fileClass.WriteAllText diagnosticPath diagnosticText utf8NoBom"
        ),
    }
    missing_bridge = [
        description
        for description, token in bridge_requirements.items()
        if token not in ui_text
    ]
    if missing_bridge:
        raise RuntimeError(
            "界面的 Python 三态回传或中文内部诊断链不完整："
            + "；".join(missing_bridge)
        )

    status_assignments = re.findall(
        r"(?m)^\s*F2M_UI_RunStatus\s*=\s*([^\r\n]+?)\s*$",
        ui_text,
    )
    if status_assignments != ["-1"]:
        raise RuntimeError(
            "界面每次运行前必须且只能把三态结果重置为 -1；"
            f"当前赋值为 {status_assignments!r}。"
        )

    protected_execute = (
        "python.Execute code throwOnError:true clearUndoBuffer:false"
    )
    protected_commit = (
        "python.Execute commitCode throwOnError:true clearUndoBuffer:false"
    )
    execute_lines = [line for line in ui_text.splitlines()
                     if re.search(r"\bpython\s*\.\s*execute\b", line, flags=re.IGNORECASE)
                     and not line.lstrip().startswith("--")]
    if (ui_text.count(protected_execute) != 3
            or ui_text.count(protected_commit) != 1
            or len(execute_lines) != 4
            or any(line.strip() not in (protected_execute, protected_commit)
                   for line in execute_lines)):
        raise RuntimeError(
            "界面的传递或自检入口可能清空用户撤销栈，或异常传播选项不完整。"
        )

    reset_index = ui_text.index("F2M_UI_RunStatus = -1")
    transfer_execute_index = ui_text.index(protected_execute, reset_index)
    readback_index = ui_text.index(
        "succeeded = (F2M_UI_RunStatus == 1)",
        transfer_execute_index,
    )
    if not reset_index < transfer_execute_index < readback_index:
        raise RuntimeError(
            "界面三态桥顺序错误：必须先重置为 -1，再执行 Python，最后读取 1。"
        )

    if any(
        forbidden in ui_text
        for forbidden in ("nodeStateFingerprint", "snapshotAsMesh", "sha256Text")
    ):
        raise RuntimeError(
            "界面重新引入了逐面拓扑字符串指纹，会造成复杂模型重复扫描和"
            "MAXScript 内存压力。"
        )
    if re.search(r"(?i)\bselection\s+as\s+array\b", ui_text):
        raise RuntimeError(
            "界面重新跨 Python 调用保存了 MAXWrapper 选择数组；"
            "必须只保存节点句柄和名称。"
        )
    for required_selection_guard in (
        "fn captureSelectionHandlesAndNames",
        "fn restoreSelectionByHandlesOrNames",
        "getAnimByHandle",
    ):
        if required_selection_guard not in ui_text:
            raise RuntimeError(
                "界面缺少选择生命周期保护：" + required_selection_guard
            )
    key_start = ui_text.index("fn currentCheckKey")
    key_end = ui_text.index("fn markNeedCheck", key_start)
    key_source = ui_text[key_start:key_end]
    for required in (
        "fbxFileFingerprint()",
        "chk_hidden.checked",
        "selectedTargetsKey()",
    ):
        if required not in key_source:
            raise RuntimeError("检查缓存键缺少必要状态：" + required)
    for forbidden_option in (
        "chk_shape",
        "chk_matid",
        "chk_normals",
        "chk_smoothing",
        "chk_uv1",
        "chk_uv2",
        "chk_uv3",
        "chk_vc",
        "chk_alpha",
        "chk_backup",
        "chk_keep_mat",
        "chk_keep_imported",
    ):
        if forbidden_option in key_source:
            raise RuntimeError(
                "只改变传递选项不应让 FBX/拓扑检查失效："
                + forbidden_option
            )
    option_start = ui_text.index("fn markOptionsChanged")
    option_end = ui_text.index("fn markChecked", option_start)
    if "markNeedCheck()" in ui_text[option_start:option_end]:
        raise RuntimeError("传递选项变化错误地清空了检查结果。")
    if "_f2m_module = sys.modules.get(_f2m_module_name)" not in ui_text or (
        "if not _f2m_reuse:" not in ui_text
    ):
        raise RuntimeError("界面没有按路径和版本复用已加载的 Python 运行模块。")
    for required_loader_guard in (
        "_F2M_IMPORT_COMPLETE",
        "callable(getattr(_f2m_module, 'run_from_max', None))",
        "if sys.modules.get(_f2m_module_name) is _f2m_module:",
        "sys.modules.pop(_f2m_module_name, None)",
    ):
        if required_loader_guard not in ui_text:
            raise RuntimeError(
                "界面模块加载器缺少半初始化模块清理保护："
                + required_loader_guard
            )


def _maxscript_function_source(source: str, name: str) -> str:
    marker = f"    fn {name} "
    start = source.find(marker)
    if start < 0:
        raise RuntimeError("MAXScript Helper 缺少函数：" + name)
    end = source.find("\n    fn ", start + len(marker))
    return source[start:] if end < 0 else source[start:end]


def _validate_transfer_release_source(
    topology_source: str,
    skin_source: str,
) -> None:
    topology_requirements = (
        "fn topologyFaceBuffer",
        "fn evaluatedTriangleDifferenceCount",
        "fn snapshotSmoothingInputFlat",
        "fn nodeObjectTransformBuffer",
        "fn deleteNodesByHandles",
        "fn snapshotEditNormalsDataFlat",
        "fn transformEditNormalsSnapshotFlat",
        "fn remapEditNormalsSnapshotFlat",
        "fn applyEditNormalsSnapshotFlat",
        "fn applyEditNormalsSnapshotFlatDifferential",
        "fn buildEditNormalResidualSnapshotFlat",
        "fn editNormalResidualsFlatMatch",
        "fn applyEditNormalResidualsFlatFromExact",
        "_maxscript_topology_flat_arrays(mapping)",
        "def _prepare_normals_only_smoothing_targets",
        "def _resolve_smoothing_masks_from_single_exact_import",
        "def _inspect_smoothing_and_normal_data",
        "subprocess.run(",
        "stdout=subprocess.DEVNULL",
        "shell=False",
        "_validated_resolver_payload(",
        "_verify_resolver_input_unchanged(ctx)",
        "ctx.initial_smoothing_masks_by_handle",
        "def show_normal_residual_notice",
        "cornerMapStarts=corner_map_starts",
        "cornerMapFlat=corner_map_flat",
        "baselineData = snapshotEditNormalsDataFlat dst dstMod",
        "rebuildEditNormalsStrict dst dstMod",
        "if baselineData[4].numberSet != 0",
        "baselineData[8].numberSet != 0",
        "def _release_context_node_references",
        "objXRefMgr.IsNodeXRefed",
    )
    missing_topology = [
        token for token in topology_requirements
        if token not in topology_source
    ]
    if missing_topology:
        raise RuntimeError(
            "模式一缺少发布级内存/生命周期保护："
            + "，".join(missing_topology)
        )

    for function_name in (
        "copyExplicitNormalResiduals",
        "copyExplicitNormals",
    ):
        production_source = _maxscript_function_source(
            topology_source,
            function_name,
        )
        for legacy_call in (
            "snapshotEditNormalsData",
            "transformEditNormalsSnapshot",
            "remapEditNormalsSnapshot",
            "applyEditNormalsSnapshot",
            "buildEditNormalResidualSnapshot",
            "editNormalResidualsMatch",
            "applyEditNormalResidualsFresh",
        ):
            if re.search(
                rf"\b{re.escape(legacy_call)}\s",
                production_source,
            ):
                raise RuntimeError(
                    f"{function_name} 重新调用了深层嵌套法线快照："
                    + legacy_call
                )

    stable_baseline_source = _maxscript_function_source(
        topology_source,
        "copyExplicitNormalResiduals",
    )
    stable_baseline_requirements = (
        "dstMod = Edit_Normals()",
        'dstMod.name = "F2M_顶点法线"',
        "addModifier dst dstMod",
        "resetEditNormalsToSmoothingBaselineStrict dst dstMod",
        "baselineData = snapshotEditNormalsDataFlat dst dstMod",
        "if baselineData[4].numberSet != 0",
        "baselineData[8].numberSet != 0",
        "buildEditNormalResidualSnapshotFlat srcData baselineData",
        "applyEditNormalResidualsFlatFromExact residualData dst dstMod",
        "editNormalResidualsFlatMatch residualData dst dstMod",
        "rebuildBeforeRead:false",
        "if retainedNormalCount == 0 then",
        "保留一个全蓝色 ",
    )
    missing_stable_baseline = [
        token for token in stable_baseline_requirements
        if token not in stable_baseline_source
    ]
    if missing_stable_baseline:
        raise RuntimeError(
            "模式一没有用同一个栈底 Edit Normals 完成基线与最终法线："
            + "，".join(missing_stable_baseline)
        )
    if (
        stable_baseline_source.count(
            "editNormalResidualsFlatMatch residualData dst dstMod"
        ) != 6
        or stable_baseline_source.count(
            "finalFaceCornerNormalsFlatMatch srcData dst dstMod"
        ) != 4
        or "emptyModifierHandle" in stable_baseline_source
    ):
        raise RuntimeError(
            "模式一零残差没有保留并复核纯 SG 基线，"
            "或残差两路没有各自完成两次最终方向读回。"
        )

    smoothing_reset_source = _maxscript_function_source(
        topology_source,
        "resetEditNormalsToSmoothingBaselineStrict",
    )
    smoothing_reset_requirements = (
        "rebuildEditNormalsStrict n modInst",
        "local inheritedExplicit = 0",
        "local inheritedSpecified = 0",
        "modInst.Reset selection:allNormals node:n",
        "if not (activateModifier n modInst) do",
        "local finalNormalCount = modInst.GetNumNormals node:n",
        "local normalId =",
        "if normalId < 1 or normalId > finalNormalCount do",
        "if modInst.GetFaceNormalSpecified faceIndex cornerIndex node:n do",
        "resetError = getCurrentException()",
        'if resetError != "" do',
    )
    missing_smoothing_reset = [
        token for token in smoothing_reset_requirements
        if token not in smoothing_reset_source
    ]
    if (
        missing_smoothing_reset
        or smoothing_reset_source.count(
            "rebuildEditNormalsStrict n modInst"
        ) != 3
    ):
        raise RuntimeError(
            "模式一没有用 Reset→重新激活→重建配方移除继承向量，"
            "再验证纯光滑组基线的有效法线 ID 与蓝色状态："
            + "，".join(missing_smoothing_reset)
        )

    resolver_bridge_start = topology_source.index(
        "def _inspect_smoothing_and_normal_data("
    )
    resolver_bridge_end = topology_source.index(
        "\ndef _mesh_data_entry_for_imported_name(",
        resolver_bridge_start,
    )
    resolver_bridge_source = topology_source[
        resolver_bridge_start:resolver_bridge_end
    ]
    for required in (
        "_resolver_python_executable()",
        '"-I"',
        '"-S"',
        '"-B"',
        "subprocess.run(",
        "stdin=subprocess.DEVNULL",
        "stdout=subprocess.DEVNULL",
        "stderr=subprocess.PIPE",
        "shell=False",
        "timeout=STRICT_RESOLVER_TIMEOUT_SECONDS",
        "_validated_resolver_payload(",
        "_cleanup_resolver_work_directory(",
    ):
        if required not in resolver_bridge_source:
            raise RuntimeError(
                "组合路径的独立 FBX 解析桥缺少：" + required
            )
    if (
        "_load_local_runtime_module(" in resolver_bridge_source
        or "read_mesh_smoothing_and_normals" in resolver_bridge_source
        or "compute_smoothing_assignment(" in resolver_bridge_source
    ):
        raise RuntimeError(
            "组合路径的解析桥仍会在 Max 主进程加载或求解完整 FBX 法线数据。"
        )

    single_resolver_start = topology_source.index(
        "def _resolve_smoothing_masks_from_single_exact_import("
    )
    single_resolver_end = topology_source.index(
        "\ndef import_fbx(",
        single_resolver_start,
    )
    single_resolver_source = topology_source[
        single_resolver_start:single_resolver_end
    ]
    for required in (
        "mesh_data.face_count",
        "mesh_data.corner_count",
        "mesh_data.topology_sha256",
        "mesh_data.masks",
        "ctx.resolver_topology_by_name[name]",
    ):
        if required not in single_resolver_source:
            raise RuntimeError(
                "组合路径缺少独立解析结果与单次导入的严格对齐：" + required
            )
    if (
        "_snapshot_smoothing_input(" in single_resolver_source
        or "_base_topology_faces(" in single_resolver_source
        or "_imported_topology_sha256(" in single_resolver_source
        or "read_mesh_smoothing_and_normals" in single_resolver_source
        or "compute_smoothing_assignment(" in single_resolver_source
        or "_load_local_runtime_module(" in single_resolver_source
    ):
        raise RuntimeError(
            "组合路径仍在 Max 主进程内读取/求解 FBX 角法线，或预建了 "
            "Edit Normals 读取器。"
        )

    topology_map_start = topology_source.index("def build_topology_map(")
    topology_map_end = topology_source.index(
        "\ndef topo_same_for_shape(",
        topology_map_start,
    )
    topology_map_source = topology_source[
        topology_map_start:topology_map_end
    ]
    for required in (
        "expected_fbx_topology:",
        "fbx_faces = _base_topology_faces(fbx_target)",
        "_imported_topology_sha256(",
        "len(fbx_faces) != int(expected_face_count)",
        "actual_corner_count != int(expected_corner_count)",
        "actual_digest != str(expected_digest)",
    ):
        if required not in topology_map_source:
            raise RuntimeError(
                "严格拓扑映射没有复用唯一的 FBX 拓扑读取验证 resolver 摘要："
                + required
            )
    if (
        "snapshotSmoothingBaselineFlatTransient" in stable_baseline_source
        or "F2M_光滑组法线基线_临时" in stable_baseline_source
        or "buildExternalSmoothingBaselineFlat" in stable_baseline_source
        or "dstMod = copy srcMod" in stable_baseline_source
        or "addModifierWithLocalData dst dstMod" in stable_baseline_source
        or "useDenseExactFallback" in stable_baseline_source
        or "clearUndoBuffer" in stable_baseline_source
    ):
        raise RuntimeError(
            "模式一残差路径仍依赖外部/完整 FBX local data，或回退到完整覆盖。"
        )

    process_pair_start = topology_source.index("def process_pair(")
    process_pair_end = topology_source.index(
        "def process_pair_transactional(",
        process_pair_start,
    )
    process_pair_source = topology_source[process_pair_start:process_pair_end]
    smoothing_at = process_pair_source.find(
        "smoothing_ok = copy_smoothing_groups("
    )
    normals_at = process_pair_source.find("normals_ok = copy_normals(")
    if (
        smoothing_at < 0
        or normals_at < 0
        or smoothing_at >= normals_at
        or "smoothing_residual_only=use_smoothing_residual"
        not in process_pair_source
        or "ctx.options.transfer_smoothing_groups and not smoothing_ok"
        not in process_pair_source
        or "target_record.handle"
        not in process_pair_source
        or "ctx.existing_smoothing_masks_by_handle"
        not in process_pair_source
        or "ctx.resolver_topology_by_name.get("
        not in process_pair_source
        or "expected_fbx_topology=expected_fbx_topology"
        not in process_pair_source
        or "smoothing_residual_only=False" in process_pair_source
    ):
        raise RuntimeError(
            "生产组合路径没有严格执行“先光滑组、再纯 SG 基线残差法线”。"
        )
    if (
        "随后只保留光滑组不能等价表达的自定义法线残差"
        not in process_pair_source
        or "Max 源模型已有非零光滑组"
        not in process_pair_source
        or "Max 源模型逐面光滑组全部为 0"
        not in process_pair_source
    ):
        raise RuntimeError(
            "生产组合路径没有向报告明确残差法线策略。"
        )

    skin_requirements = (
        f'apiVersion = "{TOOL_VERSION}"',
        "fn deleteNodesByHandles",
        '_set_fbx_importer_param("SmoothingGroups", False)',
        "def _release_context_node_references",
        "def _exception_text_and_release",
        "traceback.clear_frames(current.__traceback__)",
        'LAST_WEIGHT_WRITE_METHOD = "逐顶点权威写入"',
        "activate_modifier(old_target, target_skin)",
        "removeModifierByAnimHandle(",
        "F2M_Helper.removeModifierByAnimHandle targetNode freshHandle",
        "if not release_modifier_panel_reference():",
        "target_identities: List[Tuple[int, str]]",
    )
    missing_skin = [
        token for token in skin_requirements
        if token not in skin_source
    ]
    if missing_skin:
        raise RuntimeError(
            "模式二缺少发布级导入/删除生命周期保护："
            + "，".join(missing_skin)
        )

    skin_node_delete_source = _maxscript_function_source(
        skin_source,
        "deleteNodesByHandles",
    )
    if "delete nodeValue" in skin_node_delete_source:
        raise RuntimeError(
            "模式二节点删除仍把待删 wrapper 直接传给原生 delete。"
        )
    node_delete_at = skin_node_delete_source.find(
        "delete (getAnimByHandle handleValue)"
    )
    node_release_at = skin_node_delete_source.rfind(
        "nodeValue = undefined",
        0,
        node_delete_at,
    )
    if node_delete_at < 0 or node_release_at < 0:
        raise RuntimeError(
            "模式二节点删除没有在原生删除前释放 wrapper 并按 handle 重新解析。"
        )

    fresh_skin_source = _maxscript_function_source(
        skin_source,
        "createFreshSkinAtIndex",
    )
    if "deleteModifier targetNode freshSkin" in fresh_skin_source:
        raise RuntimeError(
            "模式二新建 Skin 的失败清理仍把待删 wrapper 直接传给 deleteModifier。"
        )
    if (
        fresh_skin_source.count(
            "F2M_Helper.removeModifierByAnimHandle targetNode freshHandle"
        )
        < 2
    ):
        raise RuntimeError(
            "模式二新建 Skin 的两个失败分支没有完整接入 handle-only 清理。"
        )

    forced_gc_patterns = (
        (r"\bgc\s*\.\s*collect\s*\(", "Python gc.collect"),
        (r"\bgc\s+light\s*:\s*true\b", "MAXScript gc light:true"),
        (r"\bgc\s*\(\s*\)", "MAXScript gc()"),
        (
            r"\bcollect_wrappers_before_native_destruction\s*\(",
            "包装器强制回收入口",
        ),
    )
    forced_gc_hits = [
        label
        for pattern, label in forced_gc_patterns
        if re.search(pattern, skin_source, flags=re.IGNORECASE)
    ]
    if forced_gc_hits:
        raise RuntimeError(
            "模式二生产源码仍含主动强制垃圾回收："
            + "，".join(forced_gc_hits)
        )


def _module_check() -> str:
    required = (
        "FBXTo3dsMax_UI.ms",
        "f2m_topology_transfer.py",
        "f2m_skin_replace.py",
        "f2m_smoothing.py",
        "f2m_fbx_metadata.py",
        "f2m_selfcheck.py",
        "f2m_test_fixtures.py",
        "f2m_i18n.py",
        "f2m_report_i18n.py",
    )
    missing = [name for name in required if not os.path.isfile(os.path.join(ROOT, name))]
    if missing:
        raise RuntimeError("缺少运行文件：" + ", ".join(missing))

    topology = _load_local("f2m_topology_transfer.py", "_f2m_sc_topology_integrity")
    skin = _load_local("f2m_skin_replace.py", "_f2m_sc_skin_integrity")
    smoothing = _load_local("f2m_smoothing.py", "_f2m_sc_smoothing_integrity")
    metadata = _load_local("f2m_fbx_metadata.py", "_f2m_sc_fbx_metadata_integrity")
    fixtures = _load_local("f2m_test_fixtures.py", "_f2m_sc_fixture_integrity")
    i18n = _language_runtime()
    report_i18n = _load_local("f2m_report_i18n.py", "_f2m_sc_report_i18n_integrity")
    versions = {
        "topology": str(getattr(topology, "TOOL_VERSION", "")),
        "skin": str(getattr(skin, "TOOL_VERSION", "")),
        "smoothing": str(getattr(smoothing, "TOOL_VERSION", "")),
        "metadata": str(getattr(metadata, "TOOL_VERSION", "")),
        "fixtures": str(getattr(fixtures, "TOOL_VERSION", "")),
        "i18n": str(getattr(i18n, "TOOL_VERSION", "")),
        "report_i18n": str(getattr(report_i18n, "TOOL_VERSION", "")),
    }
    if any(value != TOOL_VERSION for value in versions.values()):
        raise RuntimeError(f"版本不同步：{versions}")
    if not hasattr(smoothing, "run_self_check"):
        raise RuntimeError("f2m_smoothing.py 缺少 run_self_check()。")
    for metadata_api in (
        "inspect_smoothing_layers",
        "read_mesh_smoothing_data",
        "read_mesh_smoothing_and_normals",
        "build_strict_resolver_payload",
        "write_strict_resolver_json",
    ):
        if not hasattr(metadata, metadata_api):
            raise RuntimeError(
                "f2m_fbx_metadata.py 缺少 " + metadata_api + "()。"
            )
    with open(os.path.join(ROOT, "VERSION.txt"), "r", encoding="utf-8-sig") as handle:
        version_text = handle.read().strip()
    if version_text != TOOL_VERSION:
        raise RuntimeError(f"VERSION.txt 不同步：{version_text!r}")
    with open(os.path.join(ROOT, "FBXTo3dsMax_UI.ms"), "r", encoding="utf-8-sig") as handle:
        ui_text = handle.read()
    if f'local toolVersion = "{TOOL_VERSION}"' not in ui_text:
        raise RuntimeError("界面版本号与 Python 不同步。")
    _validate_ui_bridge_source(ui_text)
    helper_sources: Dict[str, str] = {}
    for filename, helper_kind in (
        ("f2m_topology_transfer.py", "topology"),
        ("f2m_skin_replace.py", "skin"),
    ):
        with open(
            os.path.join(ROOT, filename),
            "r",
            encoding="utf-8-sig",
        ) as handle:
            helper_source = handle.read()
        helper_sources[filename] = helper_source
        if (
            f'apiKind = "{helper_kind}"' not in helper_source
            or f'apiVersion = "{TOOL_VERSION}"' not in helper_source
            or "if not helper_ready:" not in helper_source
        ):
            raise RuntimeError(
                f"{filename} 没有版本化、幂等注册 MAXScript Helper。"
            )
    _validate_transfer_release_source(
        helper_sources["f2m_topology_transfer.py"],
        helper_sources["f2m_skin_replace.py"],
    )
    bootstrap_path = os.path.join(ROOT, "FBXTo3dsMax_Bootstrap.ms")
    toolbar_path = os.path.join(ROOT, "f2m_toolbar.py")
    if os.path.isfile(bootstrap_path) and os.path.isfile(toolbar_path):
        with open(bootstrap_path, "r", encoding="utf-8-sig") as handle:
            bootstrap_source = handle.read()
        with open(toolbar_path, "r", encoding="utf-8-sig") as handle:
            toolbar_source = handle.read()
        for callback_name in (
            "#systemShutdownCheck",
            "#systemShutdownCheckFailed",
            "#systemShutdownCheckPassed",
            "#preSystemShutdown",
        ):
            if callback_name not in bootstrap_source:
                raise RuntimeError("工具栏缺少退出保护回调：" + callback_name)
        if "restoreToolbarAfterCui" not in bootstrap_source or (
            "if shutdownInProgress then true else ensureToolbar()"
            not in bootstrap_source
        ):
            raise RuntimeError("退出保存 CUI 时仍可能重新创建工具栏。")
        if "QTimer.singleShot" in toolbar_source or (
            "def begin_shutdown" not in toolbar_source
        ):
            raise RuntimeError("工具栏延迟定时器没有可取消的退出生命周期。")
    mode_one_defaults = {
        "chk_shape": "true",
        "chk_matid": "false",
        "chk_normals": "false",
        "chk_uv1": "false",
        "chk_uv2": "false",
        "chk_uv3": "false",
        "chk_vc": "false",
        "chk_alpha": "false",
        "chk_smoothing": "false",
    }
    checkbox_positions: Dict[str, tuple] = {}
    for control_name, expected_checked in mode_one_defaults.items():
        match = re.search(
            rf"(?m)^\s*checkbox\s+{re.escape(control_name)}\s+\"[^\"]+\""
            rf"\s+pos:\[(\d+),(\d+)\][^\r\n]*\bchecked:(true|false)\b",
            ui_text,
        )
        if match is None:
            raise RuntimeError(f"无法解析模式一选项：{control_name}")
        checkbox_positions[control_name] = (int(match.group(1)), int(match.group(2)))
        if match.group(3) != expected_checked:
            raise RuntimeError(
                f"模式一默认勾选错误：{control_name}={match.group(3)}，"
                f"应为 {expected_checked}。"
            )
    alpha_x, alpha_y = checkbox_positions["chk_alpha"]
    smoothing_x, smoothing_y = checkbox_positions["chk_smoothing"]
    if smoothing_y != alpha_y or smoothing_x <= alpha_x:
        raise RuntimeError("“光滑组”必须位于模式一第三行、“顶点 Alpha”右侧。")
    manifest_result = _verify_installed_manifest()
    return (
        f"运行文件齐全，绝对路径加载、v{TOOL_VERSION} 版本、界面结果回传、模式一布局和"
        "仅默认勾选“变形”均通过；" + manifest_result
    )


def _algorithm_check() -> str:
    smoothing = _load_local("f2m_smoothing.py", "_f2m_sc_smoothing_runtime")
    metadata = _load_local("f2m_fbx_metadata.py", "_f2m_sc_fbx_metadata_runtime")
    topology = _load_local(
        "f2m_topology_transfer.py",
        "_f2m_sc_topology_resolver_runtime",
    )
    result = smoothing.run_self_check()
    if isinstance(result, dict):
        if not bool(result.get("ok", False)):
            raise RuntimeError(str(result))
        smoothing_summary = str(result.get("summary", "光滑组算法测试通过。"))
    elif result is True:
        smoothing_summary = "光滑组 DSATUR、32 位与间接泄漏测试通过。"
    else:
        raise RuntimeError(f"光滑组算法自检返回异常：{result!r}")

    fixtures = _load_local("f2m_test_fixtures.py", "_f2m_sc_fixture_algorithm")
    fixture = fixtures.get_fixture_paths()["topology"]
    inspected = metadata.inspect_smoothing_layers(fixture)
    if len(inspected) != 1 or any(bool(value) for value in inspected.values()):
        raise RuntimeError(
            "程序生成的 FBX 元数据预期为一个无原生 LayerElementSmoothing 的 Mesh，"
            f"实际为 {inspected!r}"
        )
    resolver_options = topology.TransferOptions(
        fbx_path=fixture,
        transfer_normals=True,
        transfer_smoothing_groups=True,
        show_ui=False,
    )
    resolver_context = topology.TransferContext(
        resolver_options,
        topology.TransferLog(),
    )
    topology._inspect_smoothing_and_normal_data(resolver_context)
    strict_data = resolver_context.fbx_mesh_data_by_name
    if len(strict_data) != 1:
        raise RuntimeError(
            f"内置 FBX 独立解析预期为一个 Mesh，实际为 {strict_data!r}"
        )
    mesh_data = next(iter(strict_data.values()))
    face_count = int(mesh_data.face_count)
    corner_count = int(mesh_data.corner_count)
    mask_count = len(mesh_data.masks)
    if (
        face_count != 2
        or corner_count != 6
        or mask_count != face_count
        or mesh_data.native
    ):
        raise RuntimeError(
            "内置 FBX 独立解析/光滑组求解不符合发布基线："
            f"faces={face_count}，corners={corner_count}，"
            f"masks={mask_count}，native={mesh_data.native!r}"
        )
    topology._release_context_node_references(resolver_context)
    return (
        smoothing_summary
        + "；程序生成的 FBX 平滑元数据、独立子进程拓扑摘要与光滑组求解通过。"
    )


def _procedural_max_check() -> str:
    _require_runtime()
    topology = _load_local("f2m_topology_transfer.py", "_f2m_sc_topology_procedural")
    topology.ensure_runtime()
    topology_mapping_summary = topology.run_topology_mapping_selfcheck()
    _reset_max_file_safely()
    mapped_channel_summary = topology.run_mapped_channel_selfcheck()
    _reset_max_file_safely()

    source = rt.Box(name="F2M_SC_Source", length=10, width=10, height=10)
    target = rt.copy(source)
    target.name = "F2M_SC_Target"
    rt.convertToPoly(source)
    rt.convertToPoly(target)
    if not topology.topo_same_for_channels(source, target):
        raise AssertionError(topology.helper_message())

    face_count = topology.base_face_count(source)
    masks = [1 if index % 2 else 2 for index in range(1, face_count + 1)]
    if not bool(rt.F2M_Helper.setFaceSmoothingGroups(target, rt.Array(*masks))):
        raise AssertionError(topology.helper_message())
    readback = [int(value) for value in list(rt.F2M_Helper.getFaceSmoothingGroups(target))]
    if readback != masks:
        raise AssertionError(f"普通光滑组读回不一致：{readback} != {masks}")

    bit32_masks = [-2147483648 for _ in range(face_count)]
    if not bool(rt.F2M_Helper.setFaceSmoothingGroups(target, rt.Array(*bit32_masks))):
        raise AssertionError(topology.helper_message())
    bit32_readback = [int(value) for value in list(rt.F2M_Helper.getFaceSmoothingGroups(target))]
    if bit32_readback != bit32_masks:
        raise AssertionError(f"第 32 位光滑组读回不一致：{bit32_readback}")

    # Editable Mesh 节点一旦带 Skin，节点级 Mesh set 操作会被 Max 拒绝。
    # 生产代码必须改写基础 TriMesh 而不塌陷修改器栈；这个小夹具确保用户
    # 点击自检时也能覆盖新光滑组最关键的真实 Max 路径。
    mesh_skin_node = rt.mesh(
        name="F2M_SC_MeshSkin",
        vertices=rt.Array(
            rt.Point3(0, 0, 0),
            rt.Point3(10, 0, 0),
            rt.Point3(10, 10, 0),
            rt.Point3(0, 10, 0),
        ),
        faces=rt.Array(
            rt.Point3(1, 2, 3),
            rt.Point3(1, 3, 4),
        ),
    )
    mesh_skin = rt.Skin()
    mesh_skin.name = "F2M_SC_MeshSkin_Skin"
    rt.addModifier(mesh_skin_node, mesh_skin)
    mesh_skin_bone = rt.Dummy(name="F2M_SC_MeshSkin_Bone")
    if not topology.activate_modifier(mesh_skin_node, mesh_skin):
        raise AssertionError("无法激活 Editable Mesh + Skin 光滑组夹具。")
    rt.skinOps.addBone(mesh_skin, mesh_skin_bone, 1, node=mesh_skin_node)
    mesh_skin_bone_id = int(rt.skinOps.GetBoneIDByListID(mesh_skin, 1))
    for vertex_index in range(1, 5):
        rt.skinOps.ReplaceVertexWeights(
            mesh_skin,
            vertex_index,
            rt.Array(mesh_skin_bone_id),
            rt.Array(1.0),
            node=mesh_skin_node,
        )
    mesh_skin_modifier_signature = tuple(
        (
            str(rt.classOf(modifier)),
            str(modifier.name),
            int(rt.getHandleByAnim(modifier)),
        )
        for modifier in list(mesh_skin_node.modifiers)
    )
    mesh_skin_weights_before = tuple(
        (
            int(rt.skinOps.GetVertexWeightBoneID(mesh_skin, vertex_index, 1)),
            float(rt.skinOps.GetVertexWeight(mesh_skin, vertex_index, 1)),
        )
        for vertex_index in range(1, 5)
    )
    mesh_skin_masks = [-2147483648, -1]
    if not bool(
        rt.F2M_Helper.setFaceSmoothingGroups(
            mesh_skin_node,
            rt.Array(*mesh_skin_masks),
        )
    ):
        raise AssertionError(
            "Editable Mesh + Skin 光滑组事务写回失败："
            + topology.helper_message()
        )
    mesh_skin_readback = [
        int(value)
        for value in list(rt.F2M_Helper.getFaceSmoothingGroups(mesh_skin_node))
    ]
    if mesh_skin_readback != mesh_skin_masks:
        raise AssertionError(
            f"Editable Mesh + Skin 光滑组读回不一致：{mesh_skin_readback}"
        )
    mesh_skin_modifier_after = tuple(
        (
            str(rt.classOf(modifier)),
            str(modifier.name),
            int(rt.getHandleByAnim(modifier)),
        )
        for modifier in list(mesh_skin_node.modifiers)
    )
    mesh_skin_weights_after = tuple(
        (
            int(rt.skinOps.GetVertexWeightBoneID(mesh_skin, vertex_index, 1)),
            float(rt.skinOps.GetVertexWeight(mesh_skin, vertex_index, 1)),
        )
        for vertex_index in range(1, 5)
    )
    if mesh_skin_modifier_after != mesh_skin_modifier_signature:
        raise AssertionError("Editable Mesh 光滑组写入改变了 Skin 修改器栈。")
    if mesh_skin_weights_after != mesh_skin_weights_before:
        raise AssertionError("Editable Mesh 光滑组写入改变了 Skin 权重。")

    rt.execute(
        r'''
        global F2M_SC_seedMapChannel
        global F2M_SC_seedMaterialIds
        global F2M_SC_hybridMessage
        fn F2M_SC_seedMapChannel n channelId =
        (
            polyop.setMapSupport n channelId true
            local vertCount = polyop.getNumVerts n
            local faceCount = polyop.getNumFaces n
            polyop.setNumMapVerts n channelId vertCount keep:false
            polyop.setNumMapFaces n channelId faceCount keep:false
            for i = 1 to vertCount do
                polyop.setMapVert n channelId i [(mod (i * 17) 255) / 255.0, (mod (i * 37) 255) / 255.0, (mod (i * 67) 255) / 255.0]
            for f = 1 to faceCount do
                polyop.setMapFace n channelId f (polyop.getFaceVerts n f)
            update n
            true
        )
        fn F2M_SC_seedMaterialIds n =
        (
            for f = 1 to (polyop.getNumFaces n) do
            (
                local faceSet = #{}
                faceSet[f] = true
                polyop.setFaceMatID n faceSet (1 + mod f 3)
            )
            update n
            true
        )
        fn F2M_SC_seedHybridNormal n =
        (
            local normalMod = Edit_Normals()
            addModifier n normalMod
            normalMod.name = "F2M_SC_源局部显式法线"
            select n
            max modify mode
            modPanel.setCurrentObject normalMod
            normalMod.RebuildNormals node:n
            if (normalMod.GetNumFaces node:n) < 1 or
               (normalMod.GetFaceDegree 1 node:n) < 1 then return false
            local normalId = normalMod.GetNormalID 1 1 node:n
            local normalValue = normalize [0.267261, 0.534522, 0.801784]
            local normalSelection = #{}
            normalSelection[normalId] = true
            if not (normalMod.MakeExplicit selection:normalSelection node:n) then return false
            normalMod.SetNormal normalId &normalValue node:n
            normalMod.SetFaceNormalSpecified 1 1 specified:true node:n
            update n
            normalMod.GetNormalExplicit normalId node:n and
                normalMod.GetFaceNormalSpecified 1 1 node:n and
                (distance (normalMod.GetNormal normalId node:n) normalValue) < 0.00001
        )
        fn F2M_SC_verifyHybridNormal n =
        (
            F2M_SC_hybridMessage = ""
            local normalMod = undefined
            for m in n.modifiers where
                classof m == Edit_Normals and
                (m.name as string) == "F2M_顶点法线" do normalMod = m
            if normalMod == undefined then
            (
                F2M_SC_hybridMessage = "找不到 F2M_顶点法线 修改器。"
                return false
            )
            local normalIndex = modPanel.getModifierIndex n normalMod
            if normalIndex != n.modifiers.count then
            (
                F2M_SC_hybridMessage = ("修改器不在栈底：" + (normalIndex as string) +
                    "/" + (n.modifiers.count as string))
                return false
            )
            local normalId = normalMod.GetNormalID 1 1 node:n
            local expected = normalize [0.267261, 0.534522, 0.801784]
            local explicitBeforeActivation = normalMod.GetNormalExplicit normalId node:n
            select n
            max modify mode
            modPanel.setCurrentObject normalMod
            local explicitAfterActivation = normalMod.GetNormalExplicit normalId node:n
            if not explicitAfterActivation then
            (
                local explicitIds = #()
                for i = 1 to (normalMod.GetNumNormals node:n) where
                    (normalMod.GetNormalExplicit i node:n) do append explicitIds i
                F2M_SC_hybridMessage = ("法线 " + (normalId as string) +
                    " 不是 Explicit；激活前=" + (explicitBeforeActivation as string) +
                    "，激活后=" + (explicitAfterActivation as string) +
                    "，当前 Explicit IDs=" + (explicitIds as string) + "。")
                return false
            )
            if not (normalMod.GetFaceNormalSpecified 1 1 node:n) then
            (
                F2M_SC_hybridMessage = "面 1 / 角 1 不是 Specified。"
                return false
            )
            local delta = distance (normalMod.GetNormal normalId node:n) expected
            if delta >= 0.00001 then
            (
                F2M_SC_hybridMessage = ("显式法线向量差异：" + (delta as string) +
                    "，实际 " + ((normalMod.GetNormal normalId node:n) as string))
                return false
            )
            true
        )
        '''
    )
    for channel, label in ((0, "顶点色 RGB"), (-2, "顶点 Alpha")):
        if not bool(rt.F2M_SC_seedMapChannel(source, channel)):
            raise AssertionError(f"无法创建过程 {label} 通道。")
        channel_report = topology.ObjectReport(name=str(target.name), status="test")
        if not topology.copy_vertex_channel(source, target, channel, label, channel_report):
            raise AssertionError("\n".join(channel_report.messages))

    try:
        source.material = rt.StandardMaterial(name="F2M_SC_Material")
    except Exception:
        source.material = rt.PhysicalMaterial(name="F2M_SC_Material")
    rt.F2M_SC_seedMaterialIds(source)
    material_report = topology.ObjectReport(name=str(target.name), status="test")
    if not topology.copy_material_ids(source, target, material_report):
        raise AssertionError("\n".join(material_report.messages))

    original_target_vertex = rt.polyop.getVert(target, 1)
    rt.polyop.setVert(source, 1, original_target_vertex + rt.Point3(1.25, -0.5, 0.75))
    shape_report = topology.ObjectReport(name=str(target.name), status="test")
    if not topology.copy_shape(source, target, shape_report):
        raise AssertionError("\n".join(shape_report.messages))
    if rt.distance(rt.polyop.getVert(target, 1), rt.polyop.getVert(source, 1)) > 0.00001:
        raise AssertionError("变形通道写后读回不一致。")

    # Match production ordering: all base mesh/map writes happen first;
    # smoothing groups are written next and Edit Normals is the final channel.
    all_one_masks = [1 for _ in range(face_count)]
    all_two_masks = [2 for _ in range(face_count)]
    if not bool(rt.F2M_Helper.setFaceSmoothingGroups(source, rt.Array(*all_one_masks))):
        raise AssertionError(topology.helper_message())
    if not bool(rt.F2M_Helper.setFaceSmoothingGroups(target, rt.Array(*all_two_masks))):
        raise AssertionError(topology.helper_message())
    if not bool(rt.F2M_SC_seedHybridNormal(source)):
        raise AssertionError("无法创建“同一光滑组 + 局部显式法线”混合夹具。")
    hybrid_options = topology.TransferOptions(
        fbx_path="",
        transfer_smoothing_groups=True,
        transfer_normals=False,
        show_ui=False,
    )
    hybrid_context = topology.TransferContext(hybrid_options, topology.TransferLog())
    hybrid_report = topology.ObjectReport(name=str(target.name), status="test")
    if not topology.copy_smoothing_groups(source, target, hybrid_context, hybrid_report):
        raise AssertionError("\n".join(hybrid_report.messages))
    if not topology.copy_normals(source, target, hybrid_report):
        raise AssertionError("\n".join(hybrid_report.messages))
    hybrid_masks = [int(value) for value in list(rt.F2M_Helper.getFaceSmoothingGroups(target))]
    if hybrid_masks != all_one_masks:
        raise AssertionError(f"显式法线写入覆盖了光滑组：{hybrid_masks}")
    if not bool(rt.F2M_SC_verifyHybridNormal(target)):
        raise AssertionError(
            "光滑组与局部显式法线同时传递后，显式向量/状态或栈位置不一致："
            + str(rt.F2M_SC_hybridMessage)
        )

    # A same-session readback can be satisfied by Max's evaluated-object cache.
    # Saving and loading the isolated scene proves that smoothing masks and the
    # Edit Normals local data are actually serialized and survive a fresh eval.
    persistence_path = os.path.join(
        tempfile.gettempdir(), f"FBXTo3dsMax_hybrid_{uuid.uuid4().hex}.max"
    )
    persisted_target: Any = None
    try:
        if not bool(rt.saveMaxFile(persistence_path, useNewFile=False, quiet=True)):
            raise AssertionError("无法保存光滑组/显式法线持久化夹具。")
        # A reset is a deletion boundary.  Release every pymxs scene/modifier/
        # Point3 wrapper from this frame before asking Max to destroy the scene.
        try:
            topology._release_context_node_references(hybrid_context)
        except Exception:
            pass
        source = None
        target = None
        mesh_skin_node = None
        mesh_skin = None
        mesh_skin_bone = None
        original_target_vertex = None
        hybrid_context = None
        try:
            rt.clearSelection()
        except Exception:
            pass
        _reset_max_file_safely()
        if not bool(rt.loadMaxFile(persistence_path, quiet=True, useFileUnits=True)):
            raise AssertionError("无法重新载入光滑组/显式法线持久化夹具。")
        persisted_target = rt.getNodeByName("F2M_SC_Target")
        if persisted_target is None:
            raise AssertionError("重新载入后找不到混合传递目标。")
        persisted_masks = [
            int(value)
            for value in list(rt.F2M_Helper.getFaceSmoothingGroups(persisted_target))
        ]
        if persisted_masks != all_one_masks:
            raise AssertionError(f"重新载入后光滑组不一致：{persisted_masks}")
        if not bool(rt.F2M_SC_verifyHybridNormal(persisted_target)):
            raise AssertionError(
                "重新载入后显式法线未持久化："
                + str(rt.F2M_SC_hybridMessage)
            )
        persisted_target = None
        try:
            rt.clearSelection()
        except Exception:
            pass
    finally:
        try:
            if os.path.isfile(persistence_path):
                os.remove(persistence_path)
        except OSError:
            pass

    verts = rt.Array(
        rt.Point3(0, 0, 0),
        rt.Point3(10, 0, 0),
        rt.Point3(10, 10, 0),
        rt.Point3(0, 10, 0),
    )
    mesh_a = rt.mesh(
        name="F2M_SC_MeshA",
        vertices=verts,
        faces=rt.Array(rt.Point3(1, 2, 3), rt.Point3(1, 3, 4)),
    )
    mesh_b = rt.mesh(
        name="F2M_SC_MeshB",
        vertices=verts,
        faces=rt.Array(rt.Point3(1, 2, 4), rt.Point3(2, 3, 4)),
    )
    if topology.mesh_counts(mesh_a) != topology.mesh_counts(mesh_b):
        raise AssertionError("同数量异拓扑测试模型的统计不一致。")
    if topology.topo_same_for_channels(mesh_a, mesh_b):
        raise AssertionError("严格拓扑校验没有拦截同数量但面索引不同的网格。")

    stack_node = rt.Box(name="F2M_SC_Stack", length=10, width=10, height=10)
    rt.convertToPoly(stack_node)
    original_modifier = rt.Bend()
    rt.addModifier(stack_node, original_modifier)
    transfer_modifier = rt.Edit_Poly()
    rt.F2M_Helper.addModifierBelowSkinOrStack(stack_node, transfer_modifier)
    transfer_index = int(rt.F2M_Helper.modifierIndex(stack_node, transfer_modifier))
    if transfer_index != int(stack_node.modifiers.count):
        raise AssertionError(f"F2M 修改器没有处在栈底：{transfer_index}/{stack_node.modifiers.count}")
    if not bool(rt.F2M_Helper.collapseModifierSafely(stack_node, transfer_modifier)):
        raise AssertionError(rt.F2M_Helper.lastMessage)
    if not any(item == original_modifier for item in list(stack_node.modifiers)):
        raise AssertionError("安全塌陷吞掉了用户原有修改器。")

    return (
        "严格拓扑、变形、顶点色/Alpha、材质ID、普通/第32位光滑组读回、"
        "Editable Mesh+Skin 基础 TriMesh 事务写回、"
        "同一光滑组+局部显式法线共存及保存重载、同数量异拓扑阻断、"
        "修改器栈保护均通过；" + topology_mapping_summary + "；" +
        mapped_channel_summary
    )


def _assert_native_smoothing_report(native_report: str, raw_summary: str) -> None:
    """Require the actual native-source message in its raw or displayed form.

    The engine's summary is untranslated. A full technical report message can
    remain in its original language, so translating only its method fragment
    does not describe what the report writer actually saved.
    """
    source_field = " 来源：FBX 原生平滑层 / Autodesk 精确导入。"
    report_lines = native_report.splitlines()
    for message in raw_summary.splitlines():
        if not message.startswith("  - ") or source_field not in message:
            continue
        rendered_lines = _display_text(message).splitlines()
        if message in report_lines or any(
            report_lines[index:index + len(rendered_lines)] == rendered_lines
            for index in range(len(report_lines))
        ):
            return
    raise AssertionError("原生 LayerElementSmoothing 生产分支没有进入报告。")


def _topology_fbx_check() -> str:
    _require_runtime()
    transfer_normals_enabled = (
        os.environ.get("F2M_TOPOLOGY_GATE_DISABLE_NORMALS", "") != "1"
    )
    transfer_smoothing_enabled = (
        os.environ.get("F2M_TOPOLOGY_GATE_DISABLE_SMOOTHING", "") != "1"
    )
    repeat_combined = max(
        1,
        int(os.environ.get("F2M_TOPOLOGY_GATE_REPEAT_COMBINED", "1")),
    )

    def stage(label: str) -> None:
        clean_label = re.sub(r"[^A-Z0-9_]", "", str(label).upper())
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            rt.execute(
                'format "F2M_TOPOLOGY_STAGE '
                + clean_label
                + " LOCAL="
                + stamp
                + " PID="
                + str(int(os.getpid()))
                + '\\n"'
            )
        except Exception:
            pass

    stage("BEGIN")
    topology = _load_local("f2m_topology_transfer.py", "_f2m_sc_topology_fbx")
    topology.ensure_runtime()
    fixtures = _load_local("f2m_test_fixtures.py", "_f2m_sc_fixture_topology")
    fixture_paths = fixtures.get_fixture_paths()
    fixture = fixture_paths["topology"]
    native_fixture = fixture_paths["native_smoothing"]
    if not os.path.isfile(fixture):
        raise FileNotFoundError(fixture)
    if not os.path.isfile(native_fixture):
        raise FileNotFoundError(native_fixture)
    _reset_max_file_safely()
    stage("INITIAL_RESET_DONE")

    setup_options = topology.TransferOptions(
        fbx_path=fixture,
        mode="topology_only",
        dry_run=True,
        transfer_shape=True,
        transfer_uv=True,
        transfer_normals=transfer_normals_enabled,
        transfer_smoothing_groups=transfer_smoothing_enabled,
        show_ui=False,
    )
    setup_context = topology.TransferContext(setup_options, topology.TransferLog())
    imported = topology._import_fbx_once(setup_context, smoothing_groups=True)
    stage("SETUP_IMPORT_DONE")
    targets = [node for node in imported if topology.is_geometry_node(node)]
    if not targets:
        raise AssertionError("内置同拓扑 FBX 没有导入网格。")

    rt.select(targets)
    topology.run_from_max(
        fbx_path=fixture,
        mode="topology_only",
        dry_run=True,
        transfer_shape=True,
        transfer_uv=True,
        uv_channels="1",
        transfer_normals=transfer_normals_enabled,
        transfer_smoothing_groups=transfer_smoothing_enabled,
        transfer_vertex_color=False,
        transfer_alpha=False,
        transfer_material_ids=False,
        keep_imported=False,
        include_hidden=True,
        show_ui=False,
    )
    if not topology.LAST_RUN_OK:
        raise AssertionError("内置 FBX 预检失败：\n" + topology.LAST_RUN_SUMMARY)
    stage("PREFLIGHT_DONE")

    for repeat_index in range(1, repeat_combined + 1):
        rt.select(targets)
        topology.run_from_max(
            fbx_path=fixture,
            mode="topology_only",
            dry_run=False,
            transfer_shape=True,
            transfer_uv=True,
            uv_channels="1",
            transfer_normals=transfer_normals_enabled,
            transfer_smoothing_groups=transfer_smoothing_enabled,
            transfer_vertex_color=False,
            transfer_alpha=False,
            transfer_material_ids=False,
            keep_imported=False,
            include_hidden=True,
            show_ui=False,
        )
        if not topology.LAST_RUN_OK:
            raise AssertionError(
                f"内置 FBX 第 {repeat_index}/{repeat_combined} 次实际传递失败：\n"
                + topology.LAST_RUN_SUMMARY
            )
        stage(f"TRANSFER_REPEAT_{repeat_index}_DONE")
    stage("TRANSFER_DONE")

    try:
        rt.clearSelection()
    except Exception:
        pass
    targets.clear()
    imported.clear()
    try:
        topology._release_context_node_references(setup_context)
    except Exception:
        pass
    setup_context = None
    _reset_max_file_safely()
    stage("FIRST_RESET_DONE")
    native_setup_options = topology.TransferOptions(
        fbx_path=native_fixture,
        mode="topology_only",
        dry_run=True,
        transfer_shape=False,
        transfer_smoothing_groups=True,
        show_ui=False,
    )
    native_setup_context = topology.TransferContext(
        native_setup_options,
        topology.TransferLog(),
    )
    native_imported = topology._import_fbx_once(
        native_setup_context,
        smoothing_groups=True,
    )
    stage("NATIVE_SETUP_IMPORT_DONE")
    native_targets = [
        node
        for node in native_imported
        if topology.is_geometry_node(node)
    ]
    if len(native_targets) != 1:
        raise AssertionError(
            f"内置原生平滑层 FBX 网格数量异常：{len(native_targets)}"
        )
    expected_masks = topology.smoothing_masks_for_source(
        native_targets[0],
        native_setup_context,
    )
    rt.select(native_targets)
    topology.run_from_max(
        fbx_path=native_fixture,
        mode="topology_only",
        dry_run=False,
        transfer_shape=False,
        transfer_uv=False,
        uv_channels="",
        transfer_normals=False,
        transfer_smoothing_groups=True,
        transfer_vertex_color=False,
        transfer_alpha=False,
        transfer_material_ids=False,
        keep_imported=False,
        include_hidden=True,
        show_ui=False,
    )
    if not topology.LAST_RUN_OK:
        raise AssertionError(
            "内置原生平滑层 FBX 传递失败：\n"
            + topology.LAST_RUN_SUMMARY
        )
    stage("NATIVE_TRANSFER_DONE")
    actual_masks = [
        int(value)
        for value in list(
            rt.F2M_Helper.getFaceSmoothingGroups(native_targets[0])
        )
    ]
    if actual_masks != expected_masks:
        raise AssertionError("内置原生平滑层 FBX 的逐面掩码读回不一致。")
    with open(
        topology.LAST_RUN_REPORT_PATH,
        "r",
        encoding="utf-8",
    ) as handle:
        native_report = handle.read()
    _assert_native_smoothing_report(native_report, topology.LAST_RUN_SUMMARY)
    stage("END")
    return (
        "程序生成的 FBX 的无原生层 DSATUR、预检、UV"
        + ("/光滑组" if transfer_smoothing_enabled else "（诊断关闭光滑组）")
        + ("/显式法线" if transfer_normals_enabled else "（诊断关闭显式法线）")
        + "实际写入，以及程序生成的 FBX 的原生 LayerElementSmoothing 精确保留、"
        "清理与恢复均通过。"
    )


def _normal_safety_check() -> str:
    _require_runtime()
    module = _load_local(
        os.path.join("tests", "max_normals_safety.py"),
        "_f2m_sc_normals_safety",
    )
    details = module.main()
    if not isinstance(details, list) or len(details) != 6:
        raise RuntimeError(
            f"显式法线安全回归返回异常：{details!r}"
        )
    if not all(": PASS" in str(item) for item in details):
        raise RuntimeError("显式法线安全回归没有全部通过：" + "；".join(details))
    return "；".join(str(item) for item in details)


def _synthetic_skin_fixture() -> str:
    """Create an original box/two-bone FBX only inside the dedicated child.

    No external model is read.  All exporter settings touched here are saved,
    set/read back, then restored/read back even when generation fails.
    """
    _validate_child_environment()
    _require_runtime()
    local_root = str(os.environ.get("LOCALAPPDATA", "") or "").strip()
    if not local_root:
        raise RuntimeError("程序生成的蒙皮自检需要 LOCALAPPDATA。")
    fixture_directory = os.path.join(
        local_root, "FBXTo3dsMax", "TestFixtures", "skin_" + uuid.uuid4().hex,
    )
    os.makedirs(fixture_directory, exist_ok=False)
    fixture_path = os.path.join(fixture_directory, "synthetic_skin.fbx")
    rt.execute("pluginManager.loadClass FbxExporter")
    parameter_names = ("Animation", "BakeAnimation", "Skin", "SmoothingGroups", "ASCII")
    # Max's FBX exporter places Skin/Deformations under the Animation master
    # switch. Enable that category for static Skin data, with no baking and no
    # animation keys in this original fixture.
    desired = {"Animation": True, "BakeAnimation": False, "Skin": True,
               "SmoothingGroups": True, "ASCII": False}

    def exporter_boolean(name: str, value: Any) -> bool:
        text = str(value).strip().lower().lstrip("#")
        if text in {"true", "1", "1.0"}:
            return True
        if text in {"false", "0", "0.0"}:
            return False
        raise RuntimeError(f"FBX 导出参数 {name} 不是可验证的 Boolean：{value}")

    def exporter_state_command(name: str) -> None:
        # The 3ds Max 2023 FBX plug-in returns Boolean true for these commands;
        # other supported FBX plug-ins expose the documented OK name instead.
        value = rt.FBXExporterSetParam(name)
        token = str(value).strip().lower().lstrip("#")
        if token not in {"ok", "true"}:
            raise RuntimeError(f"FBX 导出设置操作 {name} 未成功：{value!r}。")

    snapshot = {
        name: exporter_boolean(name, rt.FBXExporterGetParam(name))
        for name in parameter_names
    }
    generation_error = ""
    restoration_errors: List[str] = []
    exporter_settings_pushed = False
    try:
        # The exporter's master deformation/include switches can inherit a user
        # preset beyond the named Skin flag. Its documented full-state stack
        # isolates those switches as well, then restores that exact prior state.
        exporter_state_command("PushSettings")
        exporter_settings_pushed = True
        exporter_state_command("ResetExport")
        for name, value in desired.items():
            rt.FBXExporterSetParam(name, value)
            if exporter_boolean(name, rt.FBXExporterGetParam(name)) != value:
                raise RuntimeError(f"FBX 导出参数 {name} 设置后读回不一致。")
        _reset_max_file_safely()
        escaped_path = fixture_path.replace("\\", "\\\\").replace('"', '\\"')
        fixture_handles = rt.execute(
            r'''
            (
                local generatedMesh = undefined
                local boneA = undefined
                local boneB = undefined
                local generatedSkin = undefined
                try
                (
                    generatedMesh = box name:"F2M_SyntheticSkinMesh" \
                        length:10 width:8 height:12 mapcoords:true
                    convertToMesh generatedMesh
                    generatedMesh.material = standardMaterial name:"F2M_SyntheticMaterial"
                    generatedMesh.material.diffuse = color 45 150 210
                    boneA = BoneSys.createBone [0,0,0] [0,0,6] [0,1,0]
                    boneA.name = "F2M_SyntheticBoneA"
                    boneB = BoneSys.createBone [0,0,6] [0,0,12] [0,1,0]
                    boneB.name = "F2M_SyntheticBoneB"
                    boneB.parent = boneA
                    generatedSkin = Skin()
                    addModifier generatedMesh generatedSkin
                    select generatedMesh
                    max modify mode
                    subObjectLevel = 0
                    modPanel.setCurrentObject generatedSkin
                    skinOps.addBone generatedSkin boneA 0
                    skinOps.addBone generatedSkin boneB 1
                    generatedSkin.enableDQ = true
                    skinOps.enableDQOverrideWeighting generatedSkin true
                    update generatedMesh
                )
                catch
                (
                    generatedSkin = undefined
                    generatedMesh = undefined
                    boneA = undefined
                    boneB = undefined
                    throw()
                )
                local handles = #(getHandleByAnim generatedMesh, getHandleByAnim generatedSkin, \
                    getHandleByAnim boneA, getHandleByAnim boneB)
                generatedSkin = undefined
                generatedMesh = undefined
                boneA = undefined
                boneB = undefined
                handles
            )
            '''
        )
        handle_values = [int(value) for value in fixture_handles]
        del fixture_handles
        if len(handle_values) != 4 or min(handle_values) < 1:
            raise RuntimeError("程序生成的蒙皮节点句柄不完整。")
        # Return to the host between creation and Skin edits so local data is
        # evaluated before writes, as in the existing runtime Skin regression.
        generated = rt.execute(
            r'''
            (
                local generatedMesh = getAnimByHandle ''' + str(handle_values[0]) + r'''
                local generatedSkin = getAnimByHandle ''' + str(handle_values[1]) + r'''
                local boneA = getAnimByHandle ''' + str(handle_values[2]) + r'''
                local boneB = getAnimByHandle ''' + str(handle_values[3]) + r'''
                local exportOk = false
                try
                (
                    select generatedMesh
                    max modify mode
                    subObjectLevel = 0
                    modPanel.setCurrentObject generatedSkin
                    local materializedVertexCount = getNumVerts generatedMesh
                    if (skinOps.GetNumberVertices generatedSkin) != materializedVertexCount do
                        throw "程序生成的 Skin 顶点数据没有完成初始化。"
                    local boneIdA = skinOps.GetBoneIDByListID generatedSkin 1
                    local boneIdB = skinOps.GetBoneIDByListID generatedSkin 2
                    for vertexIndex = 1 to (getNumVerts generatedMesh) do
                    (
                        local firstWeight = if (mod vertexIndex 2) == 0 then 0.25 else 0.75
                        skinOps.ReplaceVertexWeights generatedSkin vertexIndex \
                            #(boneIdA, boneIdB) #(firstWeight, 1.0 - firstWeight)
                    )
                    local firstCount = skinOps.GetVertexWeightCount generatedSkin 1
                    for vertexIndex = 1 to (getNumVerts generatedMesh) do
                        skinOps.setVertexDQWeight generatedSkin vertexIndex 0.25
                    if generatedMesh.modifiers.count != 1 or (classof generatedMesh.modifiers[1]) != Skin do
                        throw "程序生成的网格没有唯一 Skin。"
                    if (skinOps.GetNumberBones generatedSkin) != 2 do
                        throw "程序生成的 Skin 骨骼数不是 2。"
                    for vertexIndex = 1 to (getNumVerts generatedMesh) do
                    (
                        if (skinOps.GetVertexWeightCount generatedSkin vertexIndex) != 2 do
                            throw ("程序生成的 Skin 顶点 " + (vertexIndex as string) + \
                                " 权重数不是 2，实际 " + \
                                ((skinOps.GetVertexWeightCount generatedSkin vertexIndex) as string) + \
                                "；写入时点 1 数量 " + (firstCount as string) + \
                                "；BoneID " + (boneIdA as string) + "," + (boneIdB as string))
                        local firstWeight = if (mod vertexIndex 2) == 0 then 0.25 else 0.75
                        for influenceIndex = 1 to 2 do
                        (
                            local actualBone = skinOps.GetVertexWeightBoneID generatedSkin vertexIndex influenceIndex
                            local expectedWeight = if actualBone == boneIdA then firstWeight \
                                else if actualBone == boneIdB then (1.0 - firstWeight) else -1.0
                            if expectedWeight < 0.0 or \
                                (abs ((skinOps.GetVertexWeight generatedSkin vertexIndex influenceIndex) - expectedWeight)) > 0.000001 do
                                throw "程序生成的 Skin 权重读回不一致。"
                        )
                        if (abs ((skinOps.getVertexDQWeight generatedSkin vertexIndex) - 0.25)) > 0.000001 do
                            throw "程序生成的 Skin DQ 权重读回不一致。"
                    )
                    max create mode
                    subObjectLevel = 0
                    select #(generatedMesh, boneA, boneB)
                    exportOk = exportFile "'''
            + escaped_path
            + r'''" #noPrompt selectedOnly:true using:FBXEXP
                    clearSelection()
                )
                catch
                (
                    generatedSkin = undefined
                    generatedMesh = undefined
                    boneA = undefined
                    boneB = undefined
                    throw()
                )
                generatedSkin = undefined
                generatedMesh = undefined
                boneA = undefined
                boneB = undefined
                exportOk
            )
            '''
        )
        if not bool(generated) or not os.path.isfile(fixture_path):
            raise RuntimeError("程序生成的两骨骼蒙皮 FBX 没有成功导出。")
    except BaseException as exc:
        generation_error = str(exc)
    finally:
        if exporter_settings_pushed:
            try:
                exporter_state_command("PopSettings")
            except BaseException as exc:
                restoration_errors.append("完整导出设置恢复（" + str(exc) + "）")
        for name, value in snapshot.items():
            try:
                rt.FBXExporterSetParam(name, value)
                if exporter_boolean(name, rt.FBXExporterGetParam(name)) != value:
                    restoration_errors.append(name + "（读回不一致）")
            except BaseException as exc:
                restoration_errors.append(name + "（" + str(exc) + "）")
        try:
            _reset_max_file_safely()
        except BaseException as exc:
            restoration_errors.append("程序生成场景清理（" + str(exc) + "）")
    if generation_error or restoration_errors:
        raise RuntimeError(
            "；".join(
                [generation_error] if generation_error else []
            ) + ("；FBX 导出/场景恢复失败：" + "，".join(restoration_errors)
                 if restoration_errors else "")
        )
    return fixture_path


def _skin_fbx_check() -> str:
    _require_runtime()
    skin = _load_local("f2m_skin_replace.py", "_f2m_sc_skin_fbx")
    if not hasattr(skin, "run_selfcheck_fixture"):
        raise RuntimeError("蒙皮引擎缺少 run_selfcheck_fixture() 集成自检入口。")
    fixture = _synthetic_skin_fixture()
    result = skin.run_selfcheck_fixture(fixture)
    if isinstance(result, dict):
        if not bool(result.get("ok", False)):
            raise SelfCheckCaseFailure(
                str(result.get("summary", "蒙皮替换集成自检失败。")),
                str(result.get("diagnostic", "")),
            )
        return str(result.get("summary", "蒙皮替换集成自检通过。")) + "；夹具完全由本次自检程序生成。"
    if result is not True:
        raise AssertionError(f"蒙皮替换集成自检返回异常：{result!r}")
    return "蒙皮替换集成自检通过。"


def _write_report(checks: Iterable[Check], run_id: str) -> Dict[str, Any]:
    check_list = list(checks)
    ok_count = sum(1 for item in check_list if item.ok)
    all_ok = ok_count == len(check_list) and bool(check_list)
    summary = (
        f"FBXTo3dsMax v{TOOL_VERSION} 自检"
        f"{'通过' if all_ok else '失败'}：{ok_count}/{len(check_list)} 项通过。"
    )
    lines = [
        _display_text(summary),
        _display_text("说明：自检覆盖已知关键不变量和内置样本，不能证明不存在所有未知缺陷。"),
        "=" * 72,
    ]
    for item in check_list:
        lines.append(_display_text(f"[{'通过' if item.ok else '失败'}] {item.name}（{item.elapsed_ms} 毫秒）"))
        lines.append(_localize_visible_text(item.detail))
        lines.append("")
    path = os.path.join(_report_folder(), f"FBXTo3dsMax_自检_{run_id}.txt")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines).rstrip() + "\n")
    diagnostic_path = ""
    diagnostic_sections = [
        f"[{item.name}]\n{item.diagnostic}"
        for item in check_list
        if item.diagnostic.strip()
    ]
    if diagnostic_sections:
        diagnostic_path = os.path.join(
            os.path.dirname(path),
            f"FBXTo3dsMax_自检_{run_id}_内部诊断.txt",
        )
        with open(diagnostic_path, "w", encoding="utf-8") as handle:
            handle.write(
                "FBXTo3dsMax 自检内部诊断\n"
                "说明：此文件供定位程序错误使用，可能包含 Python 或 3ds Max "
                "原始异常名称。\n"
                + "=" * 72
                + "\n"
                + "\n\n".join(diagnostic_sections)
                + "\n"
            )
    return {
        "ok": all_ok,
        "summary": summary,
        "report_path": path,
        "diagnostic_report_path": diagnostic_path,
        "passed": ok_count,
        "total": len(check_list),
        "checks": [item.__dict__ for item in check_list],
    }


def _run_isolated(progress_path: str = "", cancel_path: str = "") -> Dict[str, Any]:
    _require_runtime()
    run_id = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    checks: List[Check] = []
    started_at = time.time()
    cases = (
        ("运行文件、绝对路径与版本", _module_check),
        ("光滑组纯算法与32位限制", _algorithm_check),
        ("3ds Max 过程网格与修改器栈", _procedural_max_check),
        ("显式法线空间、共存与失败回滚", _normal_safety_check),
        ("内置 FBX 同拓扑完整链路", _topology_fbx_check),
        ("内置 FBX 蒙皮替换完整链路", _skin_fbx_check),
    )

    def cancelled() -> bool:
        return bool(cancel_path and os.path.exists(cancel_path))

    def max_log_marker(phase: str, case_index: int) -> None:
        clean_phase = re.sub(r"[^A-Z_]", "", str(phase).upper())
        try:
            rt.execute(
                'format "F2M_SELFCHECK_'
                + clean_phase
                + " INDEX="
                + str(int(case_index))
                + " PID="
                + str(int(os.getpid()))
                + '\\n"'
            )
        except Exception:
            pass

    reset_error = ""
    try:
        if progress_path:
            _publish_progress(
                progress_path,
                state="正在启动",
                completed=0,
                total=len(cases),
                current_name="正在准备独立测试场景",
                started_at=started_at,
            )
        for index, (name, callback) in enumerate(cases, start=1):
            if cancelled():
                raise SelfCheckCancelled("用户已取消插件自检。")
            max_log_marker("CASE_BEGIN", index)
            if progress_path:
                _publish_progress(
                    progress_path,
                    state="正在运行",
                    completed=index - 1,
                    total=len(cases),
                    current_name=name,
                    started_at=started_at,
                )
            check = _run_case(name, callback)
            checks.append(check)
            max_log_marker("CASE_END", index)
            if progress_path:
                _publish_progress(
                    progress_path,
                    state="正在运行",
                    completed=index,
                    total=len(cases),
                    current_name=name,
                    started_at=started_at,
                    last_detail=check.detail,
                )
            if not check.ok:
                # Continue through all independent cases so one run reports every
                # known regression instead of forcing the user to restart it.
                continue
        if cancelled():
            raise SelfCheckCancelled("用户已取消插件自检。")
    finally:
        max_log_marker("FINAL_RESET_BEGIN", len(cases) + 1)
        try:
            _reset_max_file_safely()
        except BaseException:
            reset_error = traceback.format_exc().strip()
        max_log_marker("FINAL_RESET_END", len(cases) + 1)
    if reset_error:
        raise RuntimeError(
            "自检业务项完成后无法安全清空隔离场景；本次结果不能作为通过证据。\n"
            + reset_error
        )
    return _write_report(checks, run_id)


def _find_batch_executable() -> str:
    candidates: List[str] = []
    if rt is not None:
        try:
            candidates.append(os.path.join(str(rt.getDir(rt.Name("maxroot"))), "3dsmaxbatch.exe"))
        except Exception:
            pass
    candidates.append(os.path.join(os.path.dirname(sys.executable), "3dsmaxbatch.exe"))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)
    raise FileNotFoundError("找不到当前 3ds Max 对应的 3dsmaxbatch.exe。")


def _qt_modules() -> Any:
    try:
        from PySide6 import QtCore, QtWidgets  # type: ignore
    except ImportError:
        from PySide2 import QtCore, QtWidgets  # type: ignore
    import qtmax  # type: ignore

    return QtCore, QtWidgets, qtmax


def _new_process_paths() -> Dict[str, str]:
    token = f"{os.getpid()}_{uuid.uuid4().hex}"
    root = tempfile.gettempdir()
    prefix = os.path.join(root, f"FBXTo3dsMax_selfcheck_{token}")
    return {
        "result": prefix + "_result.json",
        "progress": prefix + "_progress.json",
        "cancel": prefix + "_cancel.json",
        "output": prefix + "_batch.log",
    }


def _display_selfcheck_summary(result: Dict[str, Any]) -> str:
    """Render exact typed gate prefixes; keep protocol and unknown tails opaque."""

    summary = str(result.get("summary", "自检结束。") or "").strip()
    reasons: List[Tuple[str, str]] = []
    observed = result.get("child_process_exit_observed")
    code = result.get("child_process_exit_code")
    forced = result.get("child_process_completion_stop_requested")
    natural = result.get("child_process_natural_exit")
    if (
        result.get("child_process_exit_failure") is True
        and result.get("child_process_exit_gate_passed") is False
        and type(observed) is bool
        and type(forced) is bool
        and type(natural) is bool
        and ((observed and type(code) is int) or (not observed and code is None))
        and natural == (observed and not forced)
        and not (natural and code == 0)
    ):
        if forced:
            reason = (
                "独立 3ds Max Batch 在业务结果生成后触发了强制结束，"
                "不能把该业务结果视为真实完成。"
            )
        elif not observed:
            reason = "没有观察到独立 3ds Max Batch 完全退出。"
        else:
            reason = (
                "独立 3ds Max Batch 未以退出代码 0 完成"
                f"（实际退出代码 {code}）。"
            )
        reasons.append(("process", reason))

    checked = result.get("native_max_log_checked")
    gc_count = result.get("native_max_log_gc_error_count")
    if (
        result.get("native_max_log_failure") is True
        and type(checked) is bool
        and type(gc_count) is int
        and gc_count >= 0
        and type(result.get("business_result_ok")) is bool
    ):
        if checked and gc_count > 0:
            reason = (
                "独立 3ds Max 子进程完全退出后，在本次新增的原生日志中发现 "
                f"{gc_count} 条 MAXScript 内存收集错误。"
            )
            reasons.append(("native", reason))
        elif not checked and result.get("business_result_ok") is True:
            reason = (
                "无法核验本次独立 3ds Max 子进程的原生日志，"
                "不能确认没有 MAXScript 内存收集错误。"
            )
            reasons.append(("native", reason))

    def render(value: str, remaining: set) -> str:
        for kind, reason in reasons:
            if kind not in remaining:
                continue
            verdict = "自检失败：" + reason
            prefix = verdict + "\n原业务检查摘要："
            if value.startswith(prefix):
                return (
                    _display_text("自检失败：")
                    + _display_text(reason)
                    + "\n"
                    + _display_text("原业务检查摘要：")
                    + render(value[len(prefix):], remaining - {kind})
                )
            if value == verdict:
                return _display_text("自检失败：") + _display_text(reason)
        return _localize_visible_text(value)

    return render(summary, {kind for kind, _reason in reasons})


class _AsyncSelfCheckController:
    """Own one isolated Batch process while the interactive Max UI stays live."""

    def __init__(self, batch: str) -> None:
        self.batch = os.path.abspath(batch)
        self.paths = _new_process_paths()
        self.process: Optional[subprocess.Popen[Any]] = None
        self.output_handle: Any = None
        self.terminator: Optional[subprocess.Popen[Any]] = None
        self.started_at = time.monotonic()
        self.cancel_started_at = 0.0
        self.cancel_requested = False
        self.timed_out = False
        self.finished = False
        self.result: Dict[str, Any] = {}
        self.completed_result: Optional[Dict[str, Any]] = None
        self.result_seen_at = 0.0
        self.completion_stop_requested = False
        self.max_log_checkpoint: Dict[str, Any] = {}
        self.process_started_wall_time = 0.0
        self.max_log_child_pid = 0
        self.QtCore, self.QtWidgets, self.qtmax = _qt_modules()
        self.application = self.QtWidgets.QApplication.instance()
        if self.application is None:
            raise RuntimeError("无法取得 3ds Max 的 Qt 应用程序。")
        self.dialog = self._create_dialog()
        self.timer = self.QtCore.QTimer(self.application)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self._poll)
        self.application.aboutToQuit.connect(self.shutdown)

    def _create_dialog(self) -> Any:
        parent = self.qtmax.GetQMaxMainWindow()
        dialog = self.QtWidgets.QDialog(parent)
        dialog.setWindowTitle(_display_text("FBXTo3dsMax 插件自检"))
        dialog.setModal(False)
        dialog.setMinimumWidth(520)

        layout = self.QtWidgets.QVBoxLayout(dialog)
        self.state_label = self.QtWidgets.QLabel(_display_text("正在准备独立的 3ds Max 自检进程……"), dialog)
        self.state_label.setWordWrap(True)
        layout.addWidget(self.state_label)

        self.progress_bar = self.QtWidgets.QProgressBar(dialog)
        self.progress_bar.setRange(0, 6)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(_display_text("已完成 %v / %m 项"))
        layout.addWidget(self.progress_bar)

        self.detail_label = self.QtWidgets.QLabel(
            _display_text("自检在独立进程中运行，不会重置或修改当前打开的场景。"),
            dialog,
        )
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)

        self.action_button = self.QtWidgets.QPushButton(_display_text("取消自检"), dialog)
        self.action_button.clicked.connect(self._on_action)
        layout.addWidget(self.action_button)
        dialog.rejected.connect(self._on_dialog_rejected)
        return dialog

    def start(self) -> Dict[str, Any]:
        env = os.environ.copy()
        env[CHILD_ENV] = "1"
        env["F2M_LANGUAGE"] = _language_runtime().get_language()
        env[RESULT_ENV] = self.paths["result"]
        env[PROGRESS_ENV] = self.paths["progress"]
        env[CANCEL_ENV] = self.paths["cancel"]
        command = [self.batch, os.path.abspath(__file__), "-v", "0"]
        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
        _publish_progress(
            self.paths["progress"],
            state="正在启动",
            completed=0,
            total=6,
            current_name="正在启动独立的 3ds Max Batch",
            started_at=time.time(),
        )
        try:
            # 必须先记录共享 Max.log 的字节边界，再启动尚未知 PID 的 Batch。
            # 子进程完全退出后还会同时用实际 PID 与本地时间窗过滤该增量。
            self.max_log_checkpoint = _capture_max_log_checkpoint()
            self.process_started_wall_time = time.time()
            self.output_handle = open(self.paths["output"], "wb")
            self.process = subprocess.Popen(
                command,
                env=env,
                stdout=self.output_handle,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
        except BaseException as exc:
            self._close_output()
            self._remove_transient_files(keep_output=False)
            raise RuntimeError(f"无法启动独立的 3ds Max 自检进程：{exc}") from exc

        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
        self.timer.start()
        return {
            "started": True,
            "summary": "插件自检已在独立进程中启动。",
            "child_pid": int(self.process.pid),
        }

    def is_running(self) -> bool:
        return bool(
            not self.finished
            and self.process is not None
            and self.process.poll() is None
        )

    def show(self) -> None:
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def _on_action(self) -> None:
        if self.is_running():
            self.cancel("用户已取消插件自检。")
        else:
            self.dialog.close()

    def _on_dialog_rejected(self) -> None:
        if self.is_running():
            self.cancel("用户关闭了自检进度窗口，任务已取消。")

    def _taskkill_command(self) -> List[str]:
        if self.process is None:
            return []
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        executable = os.path.join(system_root, "System32", "taskkill.exe")
        if not os.path.isfile(executable):
            executable = "taskkill.exe"
        return [executable, "/PID", str(int(self.process.pid)), "/T", "/F"]

    def cancel(self, reason: str, *, timeout: bool = False) -> None:
        if not self.is_running() or self.cancel_requested:
            return
        self.cancel_requested = True
        self.timed_out = bool(timeout)
        self.cancel_started_at = time.monotonic()
        try:
            _atomic_write_json(
                self.paths["cancel"],
                {"cancelled": True, "reason": str(reason), "requested_at": time.time()},
            )
        except Exception:
            pass
        self.state_label.setText(
            _display_text("自检超时，正在终止独立进程……"
            if self.timed_out
            else "正在取消自检并清理独立进程……")
        )
        self.action_button.setEnabled(False)
        try:
            self.terminator = subprocess.Popen(
                self._taskkill_command(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            try:
                if self.process is not None:
                    self.process.kill()
            except Exception:
                pass

    def _update_progress(self, progress: Dict[str, Any]) -> None:
        completed = max(0, min(6, int(progress.get("completed", 0))))
        total = max(1, int(progress.get("total", 6)))
        current_name = str(progress.get("current_name", "正在运行"))
        elapsed = max(0, int(time.monotonic() - self.started_at))
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(min(completed, total))
        self.state_label.setText(
            _display_text(f"正在自检 {min(completed + 1, total)} / {total}：{current_name}")
        )
        detail = _localize_visible_text(progress.get("last_detail", ""))
        self.detail_label.setText(
            _display_text(f"已用时：{elapsed} 秒。"
            + (f"\n上一项结果：{detail}" if detail else ""))
        )

    def _poll(self) -> None:
        if self.finished or self.process is None:
            return

        progress = _read_json_if_ready(self.paths["progress"])
        if progress and not self.cancel_requested:
            try:
                reported_pid = int(progress.get("child_pid", 0) or 0)
                if reported_pid > 0:
                    # 若 3dsmaxbatch 启动器与嵌入 Python 的宿主 PID 不同，
                    # 以子进程自己写入的 PID 匹配 Max.log。
                    self.max_log_child_pid = reported_pid
            except (TypeError, ValueError):
                pass
            self._update_progress(progress)

        now = time.monotonic()
        result = (
            _read_json_if_ready(self.paths.get("result", ""))
            if not self.cancel_requested
            else None
        )
        return_code = self.process.poll()
        if result is not None and not self.cancel_requested:
            if getattr(self, "completed_result", None) is None:
                self.completed_result = dict(result)
                self.result_seen_at = now
                if return_code is None:
                    try:
                        self.state_label.setText(
                            _display_text("自检结果已生成，正在等待独立进程自然退出……")
                        )
                    except Exception:
                        pass
            if return_code is None:
                grace_elapsed = now - float(self.result_seen_at)
                if (
                    grace_elapsed >= SELF_CHECK_EXIT_GRACE_SECONDS
                    and not getattr(self, "completion_stop_requested", False)
                ):
                    self.completion_stop_requested = True
                    try:
                        self.terminator = subprocess.Popen(
                            self._taskkill_command(),
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=getattr(
                                subprocess,
                                "CREATE_NO_WINDOW",
                                0,
                            ),
                        )
                    except Exception:
                        try:
                            self.process.kill()
                        except Exception:
                            pass
                elif (
                    getattr(self, "completion_stop_requested", False)
                    and grace_elapsed >= SELF_CHECK_EXIT_GRACE_SECONDS + 5
                ):
                    try:
                        self.process.kill()
                    except Exception:
                        pass
                return

        elapsed = now - self.started_at
        if (
            result is None
            and not self.cancel_requested
            and elapsed >= SELF_CHECK_TIMEOUT_SECONDS
            and return_code is None
        ):
            self.cancel(
                f"独立 3ds Max 自检超过 {SELF_CHECK_TIMEOUT_SECONDS} 秒。",
                timeout=True,
            )

        if return_code is None:
            if self.cancel_requested and time.monotonic() - self.cancel_started_at > 5.0:
                try:
                    self.process.kill()
                except Exception:
                    pass
            return

        self._close_output()
        if self.cancel_requested:
            summary = (
                f"独立 3ds Max 自检超过 {SELF_CHECK_TIMEOUT_SECONDS} 秒，已终止。"
                if self.timed_out
                else "插件自检已取消，独立进程已清理。"
            )
            self._finish(
                {
                    "ok": False,
                    "cancelled": not self.timed_out,
                    "timed_out": self.timed_out,
                    "summary": summary,
                    "report_path": "",
                },
                keep_output=False,
            )
            return

        native_log_audit = _inspect_max_log_since(
            getattr(self, "max_log_checkpoint", {}),
            child_pid=int(
                getattr(self, "max_log_child_pid", 0)
                or self.process.pid
            ),
            process_started_at=float(
                getattr(self, "process_started_wall_time", 0.0)
                or time.time()
            ),
            process_finished_at=time.time(),
        )
        result = getattr(self, "completed_result", None) or _read_json_if_ready(
            self.paths.get("result", "")
        )
        if result is None:
            missing_result = _apply_native_max_log_gate(
                {
                    "ok": False,
                    "summary": (
                        "独立 3ds Max 自检进程没有返回有效结果"
                        f"（退出代码 {return_code}）。"
                    ),
                    "report_path": "",
                    "diagnostic_output": self.paths["output"],
                },
                native_log_audit,
            )
            missing_result = _apply_process_exit_gate(
                missing_result,
                return_code=return_code,
                completion_stop_requested=bool(
                    getattr(self, "completion_stop_requested", False)
                ),
            )
            self._finish(missing_result, keep_output=True)
            return
        result = _apply_native_max_log_gate(result, native_log_audit)
        result = _apply_process_exit_gate(
            result,
            return_code=return_code,
            completion_stop_requested=bool(
                getattr(self, "completion_stop_requested", False)
            ),
        )
        if not bool(result.get("ok", False)):
            # 失败时保留并明确展示 Batch 原始输出位置；正式中文报告只放
            # 本地化摘要，完整 traceback 留在诊断文件中供开发排查。
            result.setdefault("diagnostic_output", self.paths["output"])
        self._finish(result, keep_output=not bool(result.get("ok", False)))

    def _finish(self, result: Dict[str, Any], *, keep_output: bool) -> None:
        if self.finished:
            return
        self.finished = True
        self.result = dict(result)
        self.timer.stop()
        ok = bool(result.get("ok", False))
        summary = _display_selfcheck_summary(result)
        report_path = str(result.get("report_path", ""))
        diagnostic_report_path = str(result.get("diagnostic_report_path", ""))
        diagnostic_path = str(result.get("diagnostic_output", ""))
        native_log_path = str(result.get("native_max_log_path", ""))
        native_log_checked = result.get("native_max_log_checked")
        native_gc_count = int(result.get("native_max_log_gc_error_count", 0) or 0)

        self.progress_bar.setValue(
            self.progress_bar.maximum() if ok else self.progress_bar.value()
        )
        self.state_label.setText(summary)
        details: List[str] = []
        if report_path:
            details.append("详细报告：\n" + report_path)
        if diagnostic_report_path:
            details.append("内部诊断报告：\n" + diagnostic_report_path)
        if diagnostic_path:
            details.append("进程诊断输出：\n" + diagnostic_path)
        if native_log_path:
            if native_log_checked:
                details.append(
                    "3ds Max 原生日志核验："
                    + (
                        f"发现 {native_gc_count} 条 MAXScript 内存收集错误。"
                        if native_gc_count
                        else "本次子进程增量未发现 MAXScript 内存收集错误。"
                    )
                    + "\n"
                    + native_log_path
                )
            else:
                details.append(
                    "3ds Max 原生日志核验：未能确认本次子进程日志。\n"
                    + native_log_path
                )
        if not details:
            details.append("本次自检没有生成正式报告。")
        self.detail_label.setText(_display_text("\n\n".join(details)))
        self.action_button.setText(_display_text("关闭"))
        self.action_button.setEnabled(True)
        self.dialog.show()
        self.dialog.raise_()
        self._remove_transient_files(keep_output=keep_output)

    def _close_output(self) -> None:
        try:
            if self.output_handle is not None:
                self.output_handle.close()
        except Exception:
            pass
        self.output_handle = None

    def _remove_transient_files(self, *, keep_output: bool) -> None:
        for key in ("result", "progress", "cancel"):
            try:
                if os.path.exists(self.paths[key]):
                    os.remove(self.paths[key])
            except OSError:
                pass
        if not keep_output:
            try:
                if os.path.exists(self.paths["output"]):
                    os.remove(self.paths["output"])
            except OSError:
                pass

    def shutdown(self) -> None:
        """Synchronously stop every owned Qt callback and Batch process."""

        process_was_running = bool(
            self.process is not None and self.process.poll() is None
        )
        self.cancel_requested = process_was_running
        try:
            self.timer.stop()
        except Exception:
            pass
        try:
            self.dialog.hide()
        except Exception:
            pass

        if process_was_running:
            try:
                _atomic_write_json(
                    self.paths["cancel"],
                    {
                        "cancelled": True,
                        "reason": "3ds Max 正在退出。",
                        "requested_at": time.time(),
                    },
                )
            except Exception:
                pass
            command = self._taskkill_command()
            if command:
                try:
                    subprocess.run(
                        command,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=5,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        check=False,
                    )
                except Exception:
                    pass
            if self.process is not None and self.process.poll() is None:
                try:
                    self.process.wait(timeout=2)
                except Exception:
                    try:
                        self.process.kill()
                        self.process.wait(timeout=2)
                    except Exception:
                        pass
            if self.process is not None and self.process.poll() is None:
                # 保留控制文件与输出句柄，并恢复监控界面；安装器随后会阻止
                # 覆盖，不能把仍在运行的子进程伪装成“已停止”。
                try:
                    self.timer.start()
                except Exception:
                    pass
                try:
                    self.dialog.show()
                    self.dialog.raise_()
                except Exception:
                    pass
                raise RuntimeError("自检子进程在停止后仍然运行。")

        self.finished = True
        try:
            self.timer.timeout.disconnect(self._poll)
        except Exception:
            pass
        try:
            self.application.aboutToQuit.disconnect(self.shutdown)
        except Exception:
            pass
        try:
            self.dialog.close()
        except Exception:
            pass
        self._close_output()
        self._remove_transient_files(keep_output=False)


def _shutdown_controller_at_exit() -> None:
    controller = getattr(builtins, CONTROLLER_SLOT, None)
    try:
        if controller is not None:
            controller.shutdown()
    except Exception:
        pass


atexit.register(_shutdown_controller_at_exit)


def start_from_max() -> Dict[str, Any]:
    """Start one modeless, monitored self-check and return immediately."""

    _require_runtime()
    existing = getattr(builtins, CONTROLLER_SLOT, None)
    if existing is not None:
        try:
            if existing.is_running():
                existing.show()
                return {
                    "started": False,
                    "already_running": True,
                    "summary": "插件自检已经在运行，不能重复启动。",
                    "child_pid": int(existing.process.pid),
                }
            existing.dialog.close()
        except Exception:
            pass

    controller = _AsyncSelfCheckController(_find_batch_executable())
    result = controller.start()
    setattr(builtins, CONTROLLER_SLOT, controller)
    return result


def run_from_max(show_dialog: bool = True) -> Dict[str, Any]:
    """Compatibility entry: self-checks are now always modeless and asynchronous."""

    del show_dialog
    return start_from_max()


def _child_entry() -> None:
    # Validation happens before _run_isolated().  An accidental execution in the
    # user's interactive context must never reach its resetMaxFile() cleanup.
    paths = _validate_child_environment()
    started_at = time.time()
    try:
        result = _run_isolated(paths["progress"], paths["cancel"])
        state = "已完成" if result.get("ok", False) else "检查失败"
    except SelfCheckCancelled as exc:
        result = {
            "ok": False,
            "cancelled": True,
            "summary": _localize_visible_text(str(exc)),
            "report_path": "",
        }
        state = "已取消"
    except BaseException as exc:
        diagnostic = traceback.format_exc()
        try:
            diagnostic_report_path = _write_framework_diagnostic(
                paths["result"],
                diagnostic,
            )
        except Exception:
            diagnostic_report_path = ""
        # 独立 Batch 的标准错误同时写入父控制器保留的进程诊断输出。
        print(diagnostic, file=sys.stderr, flush=True)
        result = {
            "ok": False,
            "summary": "自检框架发生未捕获错误：" + _localize_visible_text(str(exc)),
            "report_path": "",
            "diagnostic_report_path": diagnostic_report_path,
            "diagnostic": diagnostic,
        }
        state = "检查失败"

    _atomic_write_json(paths["result"], result)
    _publish_progress(
        paths["progress"],
        state=state,
        completed=int(result.get("passed", 0)),
        total=int(result.get("total", 6)),
        current_name=_localize_visible_text(result.get("summary", state)),
        started_at=started_at,
    )


if __name__ == "__main__":
    _child_entry()
