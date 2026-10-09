# -*- coding: utf-8 -*-
"""UI selection-lifetime regression checks for the v1.4.25 repair."""

from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
UI_PATH = ROOT / "contents" / "FBXTo3dsMax_UI.ms"


def read_ui() -> str:
    return UI_PATH.read_text(encoding="utf-8-sig")


def source_between(source: str, start_marker: str, end_marker: str) -> str:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


class UiSelectionLifetimeTests(unittest.TestCase):
    def test_selection_snapshot_contains_only_handles_and_names(self) -> None:
        ui = read_ui()
        capture = source_between(
            ui,
            "fn captureSelectionHandlesAndNames",
            "fn restoreSelectionByHandlesOrNames",
        )

        self.assertNotIn("selection as array", ui)
        self.assertIn("getHandleByAnim n", capture)
        self.assertIn("n.name as string", capture)
        self.assertIn("#(handles, names)", capture)
        self.assertNotRegex(
            capture,
            r"(?m)^\s*append\s+(?:handles|names)\s+n\s*$",
        )

    def test_restore_resolves_live_handle_then_unique_exact_name(self) -> None:
        ui = read_ui()
        restore = source_between(
            ui,
            "fn restoreSelectionByHandlesOrNames",
            "fn confirmRunForSelection",
        )

        handle_lookup = restore.index("getAnimByHandle handles[i]")
        same_name_guard = restore.index("nodeByHandle.name as string")
        name_fallback = restore.index("for candidate in objects")
        unique_guard = restore.index("if exactMatches.count == 1")
        self.assertLess(handle_lookup, same_name_guard)
        self.assertLess(same_name_guard, name_fallback)
        self.assertLess(name_fallback, unique_guard)
        self.assertIn("validNodeSafe nodeByHandle", restore)
        self.assertIn("validNodeSafe targetNode", restore)
        self.assertNotIn("getNodeByName originalName", restore)

    def test_check_does_not_retain_node_wrappers_across_python(self) -> None:
        ui = read_ui()
        handler = source_between(
            ui,
            "on btn_check pressed do",
            "on btn_run pressed do",
        )

        capture = handler.index(
            "local selectionIdentityBeforeCheck = "
            "captureSelectionHandlesAndNames()"
        )
        execute = handler.index("local checkSucceeded = runPython true")
        restore = handler.index(
            "restoreSelectionByHandlesOrNames "
            "selectionIdentityBeforeCheck[1] "
            "selectionIdentityBeforeCheck[2]"
        )
        mark = handler.index("if checkSucceeded do")
        self.assertLess(capture, execute)
        self.assertLess(execute, restore)
        self.assertLess(restore, mark)
        self.assertNotIn("selectionBeforeCheck", handler)

    def test_formal_run_restores_by_identity_after_python_returns(self) -> None:
        ui = read_ui()
        handler = ui[ui.index("on btn_run pressed do") :]

        capture = handler.index(
            "local selectionIdentityBeforeRun = "
            "captureSelectionHandlesAndNames()"
        )
        execute = handler.index("local transferSucceeded = runPython false")
        restore = handler.index(
            "restoreSelectionByHandlesOrNames "
            "selectionIdentityBeforeRun[1] "
            "selectionIdentityBeforeRun[2]"
        )
        self.assertLess(capture, execute)
        self.assertLess(execute, restore)
        self.assertNotIn("selectionBeforeRun", handler)
        self.assertNotIn("selectionNamesBeforeRun", handler)
        self.assertNotIn("restoreSelectionByNodesOrNames", ui)


if __name__ == "__main__":
    unittest.main()
