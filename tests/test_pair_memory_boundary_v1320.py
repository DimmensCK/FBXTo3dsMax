# -*- coding: utf-8 -*-
"""Multi-object normals memory-boundary source contracts."""

from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
TOPOLOGY_PATH = ROOT / "contents" / "f2m_topology_transfer.py"


def _python_function_source(source: str, name: str) -> str:
    marker = f"def {name}("
    start = source.find(marker)
    if start < 0:
        raise AssertionError(f"缺少 Python 函数：{name}")
    end = source.find("\ndef ", start + len(marker))
    return source[start:] if end < 0 else source[start:end]


def _assert_order(
    case: unittest.TestCase,
    source: str,
    *needles: str,
) -> None:
    cursor = -1
    for needle in needles:
        cursor = source.find(needle, cursor + 1)
        case.assertGreaterEqual(cursor, 0, f"缺少或顺序错误：{needle}")


class PairMemoryBoundaryV1320Tests(unittest.TestCase):
    def test_normals_smoothing_preparation_is_pair_local(self) -> None:
        source = TOPOLOGY_PATH.read_text(encoding="utf-8-sig")
        prepare_all = _python_function_source(
            source,
            "_prepare_normals_only_smoothing_targets",
        )
        self.assertNotIn("for record in target_records", prepare_all)
        self.assertNotIn("getFaceSmoothingGroups", prepare_all)

        prepare_one = _python_function_source(
            source,
            "_prepare_current_normals_only_smoothing_target",
        )
        self.assertIn("getFaceSmoothingGroups(record.node)", prepare_one)
        self.assertIn("values = None", prepare_one)
        self.assertIn(
            "ctx.existing_smoothing_masks_by_handle[record.handle]",
            prepare_one,
        )

        smoothing = _python_function_source(source, "copy_smoothing_groups")
        self.assertNotIn("already_equal", smoothing)
        self.assertNotIn("current_masks == masks", smoothing)
        _assert_order(
            self,
            smoothing,
            "canSetFaceSmoothingGroups",
            "setFaceSmoothingGroups",
        )

    def test_pair_queue_releases_all_node_proxies_before_next_pair(self) -> None:
        source = TOPOLOGY_PATH.read_text(encoding="utf-8-sig")
        process = _python_function_source(source, "_process_imported_pairs")
        self.assertIn("node_handle(source)", process)
        self.assertIn("int(record.handle)", process)
        self.assertIn("ctx.imported_nodes.clear()", process)
        self.assertIn("rt.select(target)", process)
        _assert_order(
            self,
            process,
            "process_pair_transactional(",
            "record.node = None",
            "source = None",
            "target = None",
            "pair_report = None",
            "pair_completed",
            "not ctx.options.dry_run",
            "ctx.options.transfer_normals",
            "_release_completed_pair_boundary(ctx, object_name)",
        )
        self.assertNotIn("pair_index + 1 < len(handle_queue)", process)

    def test_pair_boundary_parks_panel_without_forced_collection(self) -> None:
        source = TOPOLOGY_PATH.read_text(encoding="utf-8-sig")
        pair_boundary = _python_function_source(
            source,
            "_release_completed_pair_boundary",
        )
        _assert_order(
            self,
            pair_boundary,
            "release_modifier_panel_reference()",
            "raise RuntimeError(",
            "未主动触发垃圾回收",
        )
        self.assertNotIn("gc.collect()", pair_boundary)
        self.assertNotIn("gc light:true", pair_boundary)
        self.assertNotIn("heapCheck", pair_boundary)

        reserve = _python_function_source(
            source,
            "ensure_maxscript_heap_reserve",
        )
        self.assertIn("MAXSCRIPT_MIN_HEAP_BYTES", reserve)
        self.assertIn("heapSize", reserve)
        self.assertIn("after_value < minimum", reserve)
        self.assertNotIn("gc.collect()", reserve)
        self.assertNotIn("gc light:true", reserve)

        run_transfer = _python_function_source(
            source,
            "run_transfer",
        )
        _assert_order(
            self,
            run_transfer,
            "ensure_maxscript_heap_reserve()",
            "prepare_scene_names(ctx)",
            "_process_imported_pairs(ctx, target_records)",
        )

        cleanup = _python_function_source(source, "cleanup_imported_nodes")
        self.assertNotIn("gc.collect()", cleanup)
        self.assertNotIn("gc light:true", cleanup)


if __name__ == "__main__":
    unittest.main()
