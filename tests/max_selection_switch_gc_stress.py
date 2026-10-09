# -*- coding: utf-8 -*-
"""3ds Max 2023 release gate for repeated source-selection FBX checks.

The script is intentionally restricted to an isolated ``3dsmaxbatch.exe``
process started by ``run_selection_switch_gc_stress.ps1``.  It never saves the
loaded scene, never calls full MAXScript garbage collection, and never changes
the MAXScript heap size.  Every iteration runs the production dry-run engine,
then verifies that selection, scene nodes, source stacks, runtime modules and
the versioned MAXScript helper remain stable.

This historical gate requires caller-owned private fixtures supplied through
F2M_PRIVATE_MAX_FIXTURE, F2M_PRIVATE_FBX_VARIANT1/2, their SHA256 variables and
optional F2M_PRIVATE_NODE_A/B selectors. No original test assets are bundled.
"""

from __future__ import annotations

import ctypes
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

import pymxs


rt = pymxs.runtime
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
RUNTIME_ROOT = os.path.join(ROOT, "contents") if os.path.isdir(os.path.join(ROOT, "contents")) else ROOT
SCRIPT_PATH = os.path.abspath(__file__)
DEFAULT_RESULT = os.path.join(
    os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(),
    "FBXTo3dsMax", "Validation",
    "_max_selection_switch_gc_stress_result.json",
)
RESULT = os.path.abspath(
    os.environ.get("F2M_SELECTION_STRESS_RESULT", DEFAULT_RESULT)
)
TOKEN = os.environ.get("F2M_SELECTION_STRESS_TOKEN", "").strip().lower()
EXPECTED_SCRIPT = os.environ.get(
    "F2M_SELECTION_STRESS_EXPECTED_SCRIPT",
    "",
).strip()
ITERATIONS_TEXT = os.environ.get(
    "F2M_SELECTION_STRESS_ITERATIONS",
    "16",
).strip()

def _required_private_path(variable):
    path = os.environ.get(variable, "").strip()
    if not path or not os.path.isabs(path) or not os.path.isfile(path):
        raise RuntimeError(f"Provide an existing absolute private fixture: {variable}")
    path = os.path.abspath(path)
    try:
        inside_source = os.path.commonpath((ROOT, path)) == ROOT
    except ValueError:
        inside_source = False
    if inside_source:
        raise RuntimeError(f"Private fixtures must be outside the source tree: {variable}")
    return path


def _required_private_sha256(variable):
    value = os.environ.get(variable, "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise RuntimeError(f"Provide the expected private fixture SHA-256: {variable}")
    return value


MAX_PATH = _required_private_path("F2M_PRIVATE_MAX_FIXTURE")
FBX_PATHS = (
    _required_private_path("F2M_PRIVATE_FBX_VARIANT1"),
    _required_private_path("F2M_PRIVATE_FBX_VARIANT2"),
)
SOURCE_NAMES = (
    os.environ.get("F2M_PRIVATE_NODE_A", "ExampleMeshA"),
    os.environ.get("F2M_PRIVATE_NODE_B", "ExampleMeshB"),
)
ASSET_PATHS = (MAX_PATH,) + FBX_PATHS
EXPECTED_ASSET_HASHES = {
    MAX_PATH: _required_private_sha256("F2M_PRIVATE_MAX_SHA256"),
    FBX_PATHS[0]: _required_private_sha256("F2M_PRIVATE_FBX_VARIANT1_SHA256"),
    FBX_PATHS[1]: _required_private_sha256("F2M_PRIVATE_FBX_VARIANT2_SHA256"),
}
MIN_ITERATIONS = 8
MAX_ITERATIONS = 512
MAX_HEAP_GROWTH_BYTES = int(
    float(os.environ.get("F2M_SELECTION_STRESS_MAX_HEAP_GROWTH_MB", "256"))
    * 1024
    * 1024
)
RAW_PRIVATE_GROWTH_TEXT = os.environ.get(
    "F2M_SELECTION_STRESS_RAW_PRIVATE_GROWTH_BYTES",
    "",
).strip()
MAX_PRIVATE_EXCESS_GROWTH_BYTES = int(
    float(
        os.environ.get(
            "F2M_SELECTION_STRESS_MAX_PRIVATE_EXCESS_GROWTH_MB",
            "256",
        )
    )
    * 1024
    * 1024
)
TEMP_NODE_PREFIXES = ("__F2M_SCENE_", "__F2M_SRC_", "__F2M_")
TEMP_MODIFIER_PREFIXES = (
    "F2M_检查",
    "F2M_读取",
    "F2M_光滑组法线基线_临时",
    "F2M_最终评估法线验证",
    "F2M_粘贴",
)
HELPER_SENTINEL_GLOBAL = "F2M_GCStress_HelperIdentity"
TRACKED_MODULE_NAMES = (
    "_f2m_selection_switch_gc_stress_runtime",
    "_f2m_smoothing_runtime",
    "_f2m_fbx_metadata_runtime",
)


class _ProcessMemoryCountersEx(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


_KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
_PSAPI = ctypes.WinDLL("psapi", use_last_error=True)
_KERNEL32.GetCurrentProcess.restype = ctypes.c_void_p
_KERNEL32.OpenProcess.argtypes = (
    ctypes.c_ulong,
    ctypes.c_int,
    ctypes.c_ulong,
)
_KERNEL32.OpenProcess.restype = ctypes.c_void_p
_KERNEL32.QueryFullProcessImageNameW.argtypes = (
    ctypes.c_void_p,
    ctypes.c_ulong,
    ctypes.c_wchar_p,
    ctypes.POINTER(ctypes.c_ulong),
)
_KERNEL32.QueryFullProcessImageNameW.restype = ctypes.c_int
_KERNEL32.CloseHandle.argtypes = (ctypes.c_void_p,)
_KERNEL32.CloseHandle.restype = ctypes.c_int
_KERNEL32.GetModuleFileNameW.argtypes = (
    ctypes.c_void_p,
    ctypes.c_wchar_p,
    ctypes.c_ulong,
)
_KERNEL32.GetModuleFileNameW.restype = ctypes.c_ulong
_KERNEL32.GetProcessHandleCount.argtypes = (
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_ulong),
)
_KERNEL32.GetProcessHandleCount.restype = ctypes.c_int
_PSAPI.GetProcessMemoryInfo.argtypes = (
    ctypes.c_void_p,
    ctypes.POINTER(_ProcessMemoryCountersEx),
    ctypes.c_ulong,
)
_PSAPI.GetProcessMemoryInfo.restype = ctypes.c_int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalized_path(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _asset_hashes() -> Dict[str, str]:
    return {path: _sha256(path) for path in ASSET_PATHS}


def _host_executable() -> str:
    buffer = ctypes.create_unicode_buffer(32768)
    length = _KERNEL32.GetModuleFileNameW(
        None,
        buffer,
        len(buffer),
    )
    if not length:
        raise ctypes.WinError(ctypes.get_last_error())
    return os.path.abspath(buffer.value)


def _process_executable(pid: int) -> str:
    # PROCESS_QUERY_LIMITED_INFORMATION is sufficient for querying the image
    # path and does not grant mutation rights to the parent process.
    process_handle = _KERNEL32.OpenProcess(0x1000, False, int(pid))
    if not process_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.c_ulong(len(buffer))
        if not _KERNEL32.QueryFullProcessImageNameW(
            process_handle,
            0,
            buffer,
            ctypes.byref(length),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return os.path.abspath(buffer.value[: int(length.value)])
    finally:
        _KERNEL32.CloseHandle(process_handle)


def _process_memory() -> Dict[str, int]:
    process_handle = _KERNEL32.GetCurrentProcess()
    counters = _ProcessMemoryCountersEx()
    counters.cb = ctypes.sizeof(counters)
    if not _PSAPI.GetProcessMemoryInfo(
        process_handle,
        ctypes.byref(counters),
        counters.cb,
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    handle_count = ctypes.c_ulong()
    if not _KERNEL32.GetProcessHandleCount(
        process_handle,
        ctypes.byref(handle_count),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return {
        "pid": os.getpid(),
        "working_set": int(counters.WorkingSetSize),
        "peak_working_set": int(counters.PeakWorkingSetSize),
        "private_usage": int(counters.PrivateUsage),
        "process_handle_count": int(handle_count.value),
    }


def _parse_iterations() -> int:
    try:
        value = int(ITERATIONS_TEXT)
    except ValueError as exc:
        raise RuntimeError(
            "F2M_SELECTION_STRESS_ITERATIONS 必须是整数。"
        ) from exc
    if value < MIN_ITERATIONS or value > MAX_ITERATIONS:
        raise RuntimeError(
            "F2M_SELECTION_STRESS_ITERATIONS 必须位于 "
            f"{MIN_ITERATIONS}–{MAX_ITERATIONS}。"
        )
    return value


def _parse_raw_private_growth() -> int:
    if not RAW_PRIVATE_GROWTH_TEXT:
        raise RuntimeError(
            "压力验收缺少同资产、同规模原生 FBX 基线增长。"
        )
    try:
        value = int(RAW_PRIVATE_GROWTH_TEXT)
    except ValueError as exc:
        raise RuntimeError(
            "原生 FBX 基线私有内存增长必须是整数字节数。"
        ) from exc
    if value < 0:
        raise RuntimeError("原生 FBX 基线私有内存增长不能为负数。")
    if MAX_PRIVATE_EXCESS_GROWTH_BYTES < 0:
        raise RuntimeError("插件额外私有内存预算不能为负数。")
    return value


def _validate_launch_identity() -> Dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{32}", TOKEN):
        raise RuntimeError("压力验收缺少有效的 32 位十六进制单次令牌。")
    if not EXPECTED_SCRIPT:
        raise RuntimeError("压力验收缺少启动方声明的脚本绝对路径。")
    if _normalized_path(EXPECTED_SCRIPT) != _normalized_path(SCRIPT_PATH):
        raise RuntimeError(
            "压力验收脚本路径与启动方声明不一致："
            f"{SCRIPT_PATH} != {EXPECTED_SCRIPT}"
        )
    host = _host_executable()
    host_name = os.path.basename(host).casefold()
    parent_pid = os.getppid()
    parent_executable = _process_executable(parent_pid)
    parent_name = os.path.basename(parent_executable).casefold()
    if host_name == "3dsmax.exe":
        if parent_name != "3dsmaxbatch.exe":
            raise RuntimeError(
                "非交互 3dsmax.exe 不是由 3dsmaxbatch.exe 启动："
                f"父进程 {parent_pid} / {parent_executable}"
            )
    elif host_name != "3dsmaxbatch.exe":
        raise RuntimeError(
            "压力验收只允许在独立 3dsmaxbatch 启动树中运行，"
            f"当前宿主为：{host}"
        )
    try:
        noninteractive = bool(rt.maxOps.isInNonInteractiveMode())
    except Exception as exc:
        raise RuntimeError("无法确认当前进程是否为 Max Batch。") from exc
    if not noninteractive:
        raise RuntimeError("当前 3ds Max 不是非交互 Batch，会话已拒绝。")
    return {
        "token": TOKEN,
        "pid": os.getpid(),
        "host_executable": host,
        "parent_pid": parent_pid,
        "parent_executable": parent_executable,
        "script_path": SCRIPT_PATH,
        "noninteractive_max_batch": True,
    }


def _atomic_write_payload(payload: Mapping[str, Any]) -> None:
    folder = os.path.dirname(RESULT)
    os.makedirs(folder, exist_ok=True)
    temporary = (
        RESULT
        + f".{TOKEN or 'invalid'}.{os.getpid()}.tmp"
    )
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
        os.replace(temporary, RESULT)
    finally:
        if os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _log_marker(kind: str, ok: Any = None) -> None:
    parts = [
        f"F2M_SELECTION_GC_STRESS_{kind}",
        f"TOKEN={TOKEN}",
        f"PID={os.getpid()}",
        f"UTC={_utc_now()}",
    ]
    if ok is not None:
        parts.append(f"OK={str(bool(ok)).lower()}")
    message = " ".join(parts)
    try:
        rt.logsystem.logEntry(message, broadcast=True)
    except Exception:
        escaped = message.replace("\\", "\\\\").replace('"', '\\"')
        rt.execute(
            f'logsystem.logEntry "{escaped}" broadcast:true'
        )
    print(message, flush=True)


def _load_topology() -> Any:
    path = os.path.abspath(os.path.join(RUNTIME_ROOT, "f2m_topology_transfer.py"))
    name = TRACKED_MODULE_NAMES[0]
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if sys.modules.get(name) is module:
            sys.modules.pop(name, None)
        raise
    setattr(module, "_F2M_IMPORT_COMPLETE", True)
    if _normalized_path(str(module.__file__)) != _normalized_path(path):
        raise RuntimeError("压力验收加载到了错误的拓扑运行模块。")
    return module


def _valid_nodes(nodes: Iterable[Any]) -> List[Any]:
    result: List[Any] = []
    for node in nodes:
        try:
            if bool(rt.isValidNode(node)):
                result.append(node)
        except Exception:
            continue
    return result


def _handles(nodes: Iterable[Any]) -> List[int]:
    return sorted(
        int(rt.getHandleByAnim(node))
        for node in _valid_nodes(nodes)
    )


def _modifier_signature(node: Any) -> List[Dict[str, str]]:
    signature: List[Dict[str, str]] = []
    for modifier in list(node.modifiers):
        signature.append(
            {
                "class": str(rt.classOf(modifier)),
                "name": str(modifier.name),
            }
        )
    return signature


def _scene_snapshot() -> Dict[str, Any]:
    nodes = _valid_nodes(list(rt.objects))
    identities = sorted(
        (
            int(rt.getHandleByAnim(node)),
            str(node.name),
            str(rt.classOf(node)),
        )
        for node in nodes
    )
    temporary_nodes = [
        {
            "handle": handle,
            "name": name,
            "class": class_name,
        }
        for handle, name, class_name in identities
        if name.startswith(TEMP_NODE_PREFIXES)
    ]
    temporary_modifiers: List[Dict[str, Any]] = []
    for node in nodes:
        for modifier in list(node.modifiers):
            modifier_name = str(modifier.name)
            if modifier_name.startswith(TEMP_MODIFIER_PREFIXES):
                temporary_modifiers.append(
                    {
                        "node_handle": int(rt.getHandleByAnim(node)),
                        "node_name": str(node.name),
                        "modifier_name": modifier_name,
                        "modifier_class": str(rt.classOf(modifier)),
                    }
                )
    source_stacks: Dict[str, List[Dict[str, str]]] = {}
    for name in SOURCE_NAMES:
        node = rt.getNodeByName(name)
        if node is None or not bool(rt.isValidNode(node)):
            source_stacks[name] = [{"class": "<missing>", "name": "<missing>"}]
        else:
            source_stacks[name] = _modifier_signature(node)
    identity_text = json.dumps(
        identities,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "node_count": len(identities),
        "nodes": [
            {"handle": handle, "name": name, "class": class_name}
            for handle, name, class_name in identities
        ],
        "node_identity_sha256": hashlib.sha256(identity_text).hexdigest(),
        "selection_handles": _handles(list(rt.selection)),
        "temporary_nodes": temporary_nodes,
        "temporary_modifiers": temporary_modifiers,
        "source_modifier_stacks": source_stacks,
    }


def _heap_sample() -> Dict[str, Any]:
    status = str(rt.execute("heapCheck() as string")).strip()
    normalized_status = status.casefold()
    heap_size = int(rt.execute("heapSize"))
    heap_free = int(rt.execute("heapFree"))
    sample: Dict[str, Any] = {
        "heap_check": status,
        "heap_size": heap_size,
        "heap_free": heap_free,
        "heap_used": heap_size - heap_free,
    }
    sample.update(_process_memory())
    if normalized_status not in {"ok", "true"}:
        raise RuntimeError(f"MAXScript heapCheck 未通过：{status}")
    if heap_size <= 0 or heap_free < 0 or heap_free > heap_size:
        raise RuntimeError(
            "MAXScript heapSize/heapFree 读回不合理："
            f"{heap_size}/{heap_free}"
        )
    return sample


def _module_identity(module: Any) -> Dict[str, Any]:
    return {
        "name": str(getattr(module, "__name__", "")),
        "python_object_id": int(id(module)),
        "file": os.path.abspath(str(getattr(module, "__file__", ""))),
        "tool_version": str(getattr(module, "TOOL_VERSION", "")),
        "import_complete": (
            getattr(module, "_F2M_IMPORT_COMPLETE", False) is True
        ),
    }


def _module_identities() -> Dict[str, Dict[str, Any]]:
    return {
        name: _module_identity(sys.modules[name])
        for name in TRACKED_MODULE_NAMES
        if name in sys.modules
    }


def _helper_identity() -> Dict[str, Any]:
    helper = rt.F2M_TopologyHelper
    sentinel_same = bool(
        rt.execute(
            f"{HELPER_SENTINEL_GLOBAL} == F2M_TopologyHelper"
        )
    )
    alias_same = bool(
        rt.execute("F2M_Helper == F2M_TopologyHelper")
    )
    identity = {
        "api_kind": str(helper.apiKind),
        "api_version": str(helper.apiVersion),
        "sentinel_same_instance": sentinel_same,
        "shared_alias_same_instance": alias_same,
    }
    if identity["api_kind"] != "topology":
        raise RuntimeError(f"拓扑 Helper 类型漂移：{identity}")
    if not sentinel_same or not alias_same:
        raise RuntimeError(f"拓扑 Helper 实例在压力测试中被替换：{identity}")
    return identity


def _install_helper_sentinel(topology: Any) -> Dict[str, Any]:
    topology.ensure_runtime()
    rt.execute(
        "global F2M_GCStress_HelperIdentity; "
        "F2M_GCStress_HelperIdentity = F2M_TopologyHelper"
    )
    identity = _helper_identity()
    if identity["api_version"] != str(topology.TOOL_VERSION):
        raise RuntimeError(
            "拓扑 Helper 与 Python 引擎版本不一致："
            f"{identity['api_version']} != {topology.TOOL_VERSION}"
        )
    return identity


def _scenario(index: int) -> Dict[str, Any]:
    # Eight entries cover both FBX files, both source selections, and both the
    # default shape check and the expensive normals+smoothing double import.
    matrix: Sequence[Tuple[int, int, bool]] = (
        (0, 0, False),
        (0, 1, False),
        (1, 0, False),
        (1, 1, False),
        (0, 0, True),
        (0, 1, True),
        (1, 0, True),
        (1, 1, True),
    )
    fbx_index, source_index, mixed = matrix[index % len(matrix)]
    return {
        "fbx_path": FBX_PATHS[fbx_index],
        "source_name": SOURCE_NAMES[source_index],
        "mixed_normals_smoothing": mixed,
        "transfer_shape": not mixed,
        "transfer_normals": mixed,
        "transfer_smoothing_groups": mixed,
    }


def _assert_scene_restored(
    baseline: Mapping[str, Any],
    current: Mapping[str, Any],
    selected_handle: int,
    iteration: int,
) -> None:
    if current["node_identity_sha256"] != baseline["node_identity_sha256"]:
        raise AssertionError(
            f"第 {iteration} 轮改变了场景节点身份集合。"
        )
    if current["nodes"] != baseline["nodes"]:
        raise AssertionError(
            f"第 {iteration} 轮场景节点 handle/name/class 没有完整恢复。"
        )
    if current["selection_handles"] != [selected_handle]:
        raise AssertionError(
            f"第 {iteration} 轮没有恢复当前 Max 源模型选择。"
        )
    if current["temporary_nodes"]:
        raise AssertionError(
            f"第 {iteration} 轮残留临时节点："
            f"{current['temporary_nodes'][:8]}"
        )
    if current["temporary_modifiers"]:
        raise AssertionError(
            f"第 {iteration} 轮残留临时修改器："
            f"{current['temporary_modifiers'][:8]}"
        )
    if current["source_modifier_stacks"] != baseline["source_modifier_stacks"]:
        raise AssertionError(
            f"第 {iteration} 轮改变了 Max 源模型修改器栈。"
        )


def _assert_module_stability(
    expected_ids: Dict[str, int],
    identities: Mapping[str, Mapping[str, Any]],
    iteration: int,
) -> None:
    for name, identity in identities.items():
        object_id = int(identity["python_object_id"])
        if name not in expected_ids:
            expected_ids[name] = object_id
        elif expected_ids[name] != object_id:
            raise AssertionError(
                f"第 {iteration} 轮运行模块被重复加载：{name}，"
                f"{expected_ids[name]} -> {object_id}"
            )
        if not identity["import_complete"]:
            raise AssertionError(
                f"第 {iteration} 轮运行模块缺少完整导入标记：{name}"
            )
        module_file = str(identity["file"])
        if not os.path.isabs(module_file) or not os.path.isfile(module_file):
            raise AssertionError(
                f"第 {iteration} 轮运行模块缺少绝对来源：{name}"
            )


def main() -> None:
    iterations: Any = ITERATIONS_TEXT
    payload: Dict[str, Any] = {
        "schema_version": 2,
        "test": "FBXTo3dsMax selection-switch native-GC release gate",
        "state": "starting",
        "ok": False,
        "token": TOKEN,
        "pid": os.getpid(),
        "started_at_utc": _utc_now(),
        "finished_at_utc": None,
        "iterations": iterations,
        "completed_iterations": 0,
        "heavy_mixed_iterations": 0,
        "samples": [],
        "assets": {
            "max_path": MAX_PATH,
            "fbx_paths": list(FBX_PATHS),
            "expected_sha256": EXPECTED_ASSET_HASHES,
        },
        "safety": {
            "isolated_max_batch": False,
            "scene_saved": False,
            "full_maxscript_gc_called": False,
            "maxscript_heap_resized": False,
        },
    }
    begin_logged = False
    run_error = ""
    cleanup_errors: List[str] = []
    asset_hashes_before: Dict[str, str] = {}
    try:
        identity = _validate_launch_identity()
        payload["launch_identity"] = identity
        payload["safety"]["isolated_max_batch"] = True
        iterations = _parse_iterations()
        payload["iterations"] = iterations
        raw_private_growth = _parse_raw_private_growth()
        payload["paired_raw_baseline"] = {
            "private_usage_growth": raw_private_growth,
            "max_plugin_excess_growth_allowed": (
                MAX_PRIVATE_EXCESS_GROWTH_BYTES
            ),
        }
        _log_marker("BEGIN")
        begin_logged = True

        asset_hashes_before = _asset_hashes()
        payload["assets"]["sha256_before"] = asset_hashes_before
        if asset_hashes_before != EXPECTED_ASSET_HASHES:
            raise AssertionError(
                "发布门输入资产不是冻结基线："
                f"{asset_hashes_before}"
            )
        payload["state"] = "running"
        _atomic_write_payload(payload)

        if not bool(rt.loadMaxFile(MAX_PATH, useFileUnits=True, quiet=True)):
            raise RuntimeError("无法加载 PrivateFixture 场景。")
        topology = _load_topology()
        payload["tool_version"] = str(topology.TOOL_VERSION)
        sources = {
            name: rt.getNodeByName(name)
            for name in SOURCE_NAMES
        }
        if len(_valid_nodes(sources.values())) != len(SOURCE_NAMES):
            raise RuntimeError("测试场景缺少预期 Max 源模型。")

        initial_helper = _install_helper_sentinel(topology)
        payload["initial_helper_identity"] = initial_helper
        baseline_scene = _scene_snapshot()
        if baseline_scene["temporary_nodes"] or baseline_scene["temporary_modifiers"]:
            raise AssertionError("PrivateFixture 基线本身含 F2M 临时对象。")
        payload["baseline_scene"] = baseline_scene
        baseline_heap = _heap_sample()
        baseline_modules = _module_identities()
        expected_module_ids = {
            name: int(identity["python_object_id"])
            for name, identity in baseline_modules.items()
        }
        payload["baseline_module_identities"] = baseline_modules
        payload["samples"].append(
            {
                "phase": "baseline",
                "heap": baseline_heap,
                "scene": baseline_scene,
                "modules": baseline_modules,
                "helper": initial_helper,
            }
        )
        _atomic_write_payload(payload)

        for index in range(iterations):
            iteration_number = index + 1
            scenario = _scenario(index)
            selected = sources[scenario["source_name"]]
            rt.select(selected)
            selected_handle = int(rt.getHandleByAnim(selected))
            started = time.perf_counter()
            summary = topology.run_from_max(
                scenario["fbx_path"],
                mode="topology_only",
                dry_run=True,
                transfer_shape=bool(scenario["transfer_shape"]),
                transfer_uv=False,
                transfer_normals=bool(scenario["transfer_normals"]),
                transfer_smoothing_groups=bool(
                    scenario["transfer_smoothing_groups"]
                ),
                transfer_vertex_color=False,
                transfer_alpha=False,
                transfer_material_ids=False,
                keep_imported=False,
                include_hidden=True,
                show_ui=False,
            )
            elapsed = time.perf_counter() - started
            if not bool(topology.LAST_RUN_OK):
                raise AssertionError(summary)
            if summary.count("[已检查：可安全执行]") != 1:
                raise AssertionError(
                    f"第 {iteration_number} 轮没有且只有一个源模型通过：\n"
                    f"{summary}"
                )
            rt.execute("windows.processPostedMessages()")

            scene = _scene_snapshot()
            _assert_scene_restored(
                baseline_scene,
                scene,
                selected_handle,
                iteration_number,
            )
            module_identities = _module_identities()
            _assert_module_stability(
                expected_module_ids,
                module_identities,
                iteration_number,
            )
            helper_identity = _helper_identity()
            if helper_identity["api_version"] != str(topology.TOOL_VERSION):
                raise AssertionError(
                    f"第 {iteration_number} 轮 Helper 版本漂移："
                    f"{helper_identity}"
                )
            heap = _heap_sample()
            payload["samples"].append(
                {
                    "phase": "iteration",
                    "index": iteration_number,
                    "scenario": scenario,
                    "selected_handle": selected_handle,
                    "elapsed_seconds": round(elapsed, 6),
                    "report_path": str(topology.LAST_RUN_REPORT_PATH),
                    "heap": heap,
                    "scene": scene,
                    "modules": module_identities,
                    "helper": helper_identity,
                }
            )
            payload["completed_iterations"] = iteration_number
            if scenario["mixed_normals_smoothing"]:
                payload["heavy_mixed_iterations"] += 1
            _atomic_write_payload(payload)

        if payload["heavy_mixed_iterations"] < 4:
            raise AssertionError(
                "混合法线+光滑组重路径覆盖不足："
                f"{payload['heavy_mixed_iterations']}/4"
            )
        iteration_heaps = [
            sample["heap"]
            for sample in payload["samples"]
            if sample["phase"] == "iteration"
        ]
        max_heap_size = max(
            int(sample["heap_size"])
            for sample in iteration_heaps
        )
        max_private_usage = max(
            int(sample["private_usage"])
            for sample in iteration_heaps
        )
        heap_growth = max_heap_size - int(baseline_heap["heap_size"])
        private_growth = (
            max_private_usage - int(baseline_heap["private_usage"])
        )
        private_excess_growth = private_growth - raw_private_growth
        max_private_growth_allowed = (
            raw_private_growth + MAX_PRIVATE_EXCESS_GROWTH_BYTES
        )
        payload["memory_gate"] = {
            "baseline_heap_size": int(baseline_heap["heap_size"]),
            "max_heap_size": max_heap_size,
            "heap_size_growth": heap_growth,
            "max_heap_growth_allowed": MAX_HEAP_GROWTH_BYTES,
            "baseline_private_usage": int(baseline_heap["private_usage"]),
            "max_private_usage": max_private_usage,
            "private_usage_growth": private_growth,
            "raw_private_usage_growth": raw_private_growth,
            "private_usage_excess_over_raw": private_excess_growth,
            "max_private_excess_growth_allowed": (
                MAX_PRIVATE_EXCESS_GROWTH_BYTES
            ),
            "max_private_growth_allowed": max_private_growth_allowed,
        }
        if heap_growth > MAX_HEAP_GROWTH_BYTES:
            raise AssertionError(
                "MAXScript heap 在重复检查中增长过大："
                f"{heap_growth}/{MAX_HEAP_GROWTH_BYTES} 字节。"
            )
        if private_excess_growth > MAX_PRIVATE_EXCESS_GROWTH_BYTES:
            raise AssertionError(
                "插件相对同资产原生 FBX 基线的额外私有内存增长过大："
                f"{private_excess_growth}/"
                f"{MAX_PRIVATE_EXCESS_GROWTH_BYTES} 字节；"
                f"插件总增长={private_growth}，"
                f"原生基线增长={raw_private_growth}。"
            )
    except BaseException:
        run_error = traceback.format_exc()
        payload["error"] = run_error
    finally:
        try:
            rt.execute(
                "global F2M_GCStress_HelperIdentity; "
                "F2M_GCStress_HelperIdentity = undefined"
            )
        except Exception:
            cleanup_errors.append(
                "测试 Helper 身份哨兵清理失败：\n"
                + traceback.format_exc()
            )
        try:
            rt.resetMaxFile(rt.Name("noPrompt"))
        except Exception:
            cleanup_errors.append(
                "Max Batch 内存场景丢弃失败：\n"
                + traceback.format_exc()
            )
        asset_hashes_after: Dict[str, str] = {}
        try:
            asset_hashes_after = _asset_hashes()
            payload["assets"]["sha256_after"] = asset_hashes_after
            payload["assets"]["unchanged"] = (
                bool(asset_hashes_before)
                and asset_hashes_after == asset_hashes_before
                and asset_hashes_after == EXPECTED_ASSET_HASHES
            )
            if not payload["assets"]["unchanged"]:
                cleanup_errors.append(
                    "压力测试前后用户资产 SHA-256 不一致。"
                )
        except Exception:
            payload["assets"]["unchanged"] = False
            cleanup_errors.append(
                "压力测试结束时无法复核用户资产 SHA-256：\n"
                + traceback.format_exc()
            )

        if cleanup_errors:
            payload["cleanup_errors"] = cleanup_errors
        payload["finished_at_utc"] = _utc_now()
        payload["state"] = "finished"
        payload["ok"] = bool(
            not run_error
            and not cleanup_errors
            and payload.get("completed_iterations") == payload.get("iterations")
            and payload.get("heavy_mixed_iterations", 0) >= 4
            and payload["assets"].get("unchanged") is True
        )
        try:
            if begin_logged:
                _log_marker("END", ok=payload["ok"])
        except Exception:
            payload["ok"] = False
            payload.setdefault("cleanup_errors", []).append(
                "无法向 listener log 写入本次压力验收结束标记：\n"
                + traceback.format_exc()
            )
        _atomic_write_payload(payload)
        print(
            json.dumps(
                {
                    "ok": payload["ok"],
                    "error": payload.get("error", ""),
                    "completed_iterations": payload.get(
                        "completed_iterations", 0
                    ),
                    "iterations": payload.get("iterations", 0),
                    "heavy_mixed_iterations": payload.get(
                        "heavy_mixed_iterations", 0
                    ),
                    "result_path": RESULT,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
