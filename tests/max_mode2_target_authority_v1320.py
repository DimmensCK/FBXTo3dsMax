# -*- coding: utf-8 -*-
"""Real 3ds Max Batch gate for mode-2 FBX target authority."""

from __future__ import annotations

import importlib.util
import gc
import hashlib
import json
import os
import sys
import time
import traceback
import uuid
import re
from typing import Any

from pymxs import runtime as rt


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_ROOT = os.path.join(ROOT, "contents") if os.path.isdir(os.path.join(ROOT, "contents")) else ROOT
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "skin_source.fbx")
RESULT = os.path.join(
    ROOT,
    "tests",
    "_max_mode2_target_authority_v1320_result.json",
)


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def load_skin_module() -> Any:
    path = os.path.join(RUNTIME_ROOT, "f2m_skin_replace.py")
    name = "_f2m_mode2_target_authority_v1320"
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    setattr(module, "_F2M_IMPORT_COMPLETE", True)
    if os.path.normcase(os.path.abspath(module.__file__)) != os.path.normcase(
        os.path.abspath(path)
    ):
        raise RuntimeError("模式二验收加载到了错误的运行模块。")
    return module


payload = {
    "ok": False,
        "version": "1.4.26",
    "run_token": uuid.uuid4().hex,
    "engine_pid": os.getpid(),
    "started_at_utc_epoch": time.time(),
    "finished_at_utc_epoch": 0.0,
    "fixture": FIXTURE,
    "fixture_sha256": "",
    "module_path": "",
    "module_sha256": "",
    "heap_check_before": "",
    "heap_check_after": "",
    "result": {},
    "error": "",
    "cleanup_error": "",
}
skin = None
result = None
try:
    payload["heap_check_before"] = str(rt.execute("heapCheck() as string"))
    skin = load_skin_module()
    payload["module_path"] = os.path.abspath(skin.__file__)
    payload["module_sha256"] = sha256_file(payload["module_path"])
    payload["fixture_sha256"] = sha256_file(FIXTURE)
    if str(skin.TOOL_VERSION) != payload["version"]:
        raise AssertionError(
            f"版本不一致：{skin.TOOL_VERSION}/{payload['version']}"
        )
    result = skin.run_selfcheck_fixture(FIXTURE)
    payload["result"] = result
    if not bool(result.get("ok")):
        raise AssertionError(result)
    if result.get("weight_write_method") != "逐顶点权威写入":
        raise AssertionError(
            "模式二没有报告逐顶点权威写入："
            + str(result.get("weight_write_method", "未记录"))
        )
    if result.get("bulk_fallback_reason"):
        raise AssertionError(
            "模式二不应报告批量首写/回退："
            + str(result["bulk_fallback_reason"])
        )
    for required_flag in (
        "source_sentinel_verified",
        "authority_content_verified",
        "saved_and_reloaded",
        "scene_bone_handles_preserved",
    ):
        if not bool(result.get(required_flag)):
            raise AssertionError(f"模式二专项缺少通过标志：{required_flag}")
    coverage = result.get("authority_content_coverage")
    if not isinstance(coverage, dict) or len(coverage) != int(
        result.get("mesh_count", 0)
    ):
        raise AssertionError("模式二内容指纹覆盖集合不完整。")
    total_covered_vertices = 0
    required_components = {
        "object",
        "material",
        "modifiers",
        "geometry",
        "faces",
        "maps",
        "normals",
    }
    for mesh_name, mesh_coverage in coverage.items():
        channels = {int(value) for value in mesh_coverage["map_channels"]}
        if not {-2, 0, 1, 2}.issubset(channels):
            raise AssertionError(
                f"模式二夹具 {mesh_name} 缺少 Alpha/颜色/UV1/UV2："
                f"{sorted(channels)}"
            )
        vertex_count = int(mesh_coverage["vertex_count"])
        face_count = int(mesh_coverage["face_count"])
        if vertex_count < 1 or face_count < 1:
            raise AssertionError(f"模式二夹具 {mesh_name} 网格为空。")
        if int(mesh_coverage["map_vertex_count"]) < 1:
            raise AssertionError(f"模式二夹具 {mesh_name} 没有 Map 顶点。")
        if int(mesh_coverage["map_face_count"]) < face_count:
            raise AssertionError(f"模式二夹具 {mesh_name} Map 面覆盖不足。")
        if int(mesh_coverage["render_normal_corners"]) != face_count * 3:
            raise AssertionError(f"模式二夹具 {mesh_name} 面角法线覆盖不足。")
        component_hashes = mesh_coverage.get("component_sha256")
        if not isinstance(component_hashes, dict):
            raise AssertionError(f"模式二夹具 {mesh_name} 缺少分量指纹。")
        if set(component_hashes) != required_components:
            raise AssertionError(
                f"模式二夹具 {mesh_name} 分量指纹集合不完整。"
            )
        for component, value in component_hashes.items():
            if re.fullmatch(r"[0-9A-F]{64}", str(value)) is None:
                raise AssertionError(
                    f"模式二夹具 {mesh_name}/{component} 指纹无效。"
                )
        total_covered_vertices += vertex_count
    if total_covered_vertices != int(result["verified_vertices"]):
        raise AssertionError("模式二内容指纹顶点覆盖与 Skin 读回不一致。")
    payload["heap_check_after"] = str(rt.execute("heapCheck() as string"))
    if payload["heap_check_before"].strip().casefold() not in {"ok", "true"}:
        raise AssertionError(
            f"模式二验收前 heapCheck 失败：{payload['heap_check_before']}"
        )
    if payload["heap_check_after"].strip().casefold() not in {"ok", "true"}:
        raise AssertionError(
            f"模式二验收后 heapCheck 失败：{payload['heap_check_after']}"
        )
    payload["ok"] = True
except BaseException:
    payload["error"] = traceback.format_exc()
finally:
    result = None
    try:
        if skin is not None:
            skin._reset_max_file_safely()
        else:
            gc.collect()
            if not bool(rt.execute("(try(gc light:true; true)catch(false))")):
                raise RuntimeError("安全包装器回收失败。")
            rt.clearSelection()
            rt.resetMaxFile(rt.Name("noPrompt"))
    except BaseException:
        payload["cleanup_error"] = traceback.format_exc()
        payload["ok"] = False
    skin = None
    gc.collect()
    payload["finished_at_utc_epoch"] = time.time()
    with open(RESULT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

if not payload["ok"]:
    raise RuntimeError("模式二 FBX 目标权威验收失败，请查看结果 JSON。")
