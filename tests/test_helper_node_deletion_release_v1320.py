# -*- coding: utf-8 -*-
"""临时节点删除的失效 MAXWrapper 生命周期回归。"""

from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
TOPOLOGY_PATH = ROOT / "contents" / "f2m_topology_transfer.py"
SKIN_PATH = ROOT / "contents" / "f2m_skin_replace.py"
SELFCHECK_PATH = ROOT / "contents" / "f2m_selfcheck.py"


def _maxscript_function_source(source: str, name: str) -> str:
    marker = f"    fn {name} "
    start = source.find(marker)
    if start < 0:
        raise AssertionError(f"缺少 MAXScript Helper 函数：{name}")
    end = source.find("\n    fn ", start + len(marker))
    return source[start:] if end < 0 else source[start:end]


class HelperNodeDeletionReleaseV1320Tests(unittest.TestCase):
    def test_selfcheck_scene_reset_does_not_dismantle_live_normal_stacks(
        self,
    ) -> None:
        source = SELFCHECK_PATH.read_text(encoding="utf-8-sig")
        marker = "def _reset_max_file_safely()"
        start = source.index(marker)
        end = source.index("\ndef ", start + len(marker))
        reset = source[start:end]

        self.assertIn("rt.clearSelection()", reset)
        self.assertIn(
            'rt.resetMaxFile(rt.Name("noPrompt"))',
            reset,
        )
        self.assertIn("if len(rt.objects) != 0:", reset)
        self.assertNotIn("deleteNodesByHandles", reset)
        self.assertNotIn("deleteModifier", reset)

    def test_topology_node_delete_crosses_native_delete_by_handle_only(
        self,
    ) -> None:
        source = TOPOLOGY_PATH.read_text(encoding="utf-8-sig")
        helper = _maxscript_function_source(
            source,
            "deleteNodesByHandles",
        )

        self.assertNotIn("local nodes = #()", helper)
        self.assertNotIn("append nodes nodeValue", helper)
        self.assertNotIn("delete nodes", helper)
        self.assertNotIn("delete nodeValue", helper)
        self.assertIn("for handleValue in handles do", helper)

        delete_at = helper.index("delete (getAnimByHandle handleValue)")
        self.assertGreaterEqual(
            helper.rfind("nodeValue = undefined", 0, delete_at),
            0,
            "节点 wrapper 必须在原生删除前释放",
        )
        self.assertIn(
            "try(nodeValue = getAnimByHandle handleValue)catch()",
            helper[:delete_at],
        )

        self.assertIn("try(subObjectLevel = 0)catch()", helper)
        self.assertIn("modPanel.getCurrentObject()", helper)
        self.assertIn("classof panelObject == Edit_Normals", helper)
        self.assertIn("getHandleByAnim panelObject", helper)
        self.assertIn("panelObject = undefined", helper)
        self.assertIn("setCommandPanelTaskMode #create", helper)
        self.assertIn(
            "removeModifierByAnimHandle nodeValue normalHandle",
            helper,
        )
        self.assertIn(
            "detachModifierPanelFromNodeIfNeeded nodeValue",
            helper,
        )

        after_delete = helper[delete_at:]
        self.assertIn("getAnimByHandle parkedPanelHandle", after_delete)
        self.assertIn("local leftovers = #()", after_delete)
        self.assertIn(
            "try(nodeValue = getAnimByHandle handleValue)catch()",
            after_delete,
        )
        self.assertIn("append leftovers handleValue", after_delete)
        self.assertIn("nodeValue = undefined", after_delete)

        code_without_comments = "\n".join(
            line.split("--", 1)[0] for line in helper.splitlines()
        ).lower()
        self.assertNotIn("gc(", code_without_comments)
        self.assertNotIn("gc ", code_without_comments)

    def test_skin_node_delete_crosses_native_delete_by_handle_only(
        self,
    ) -> None:
        source = SKIN_PATH.read_text(encoding="utf-8-sig")
        helper = _maxscript_function_source(
            source,
            "deleteNodesByHandles",
        )

        self.assertNotIn("local nodes = #()", helper)
        self.assertNotIn("append nodes nodeValue", helper)
        self.assertNotIn("delete nodes", helper)
        self.assertNotIn("delete nodeValue", helper)
        self.assertIn("for handleValue in handles do", helper)

        delete_at = helper.index("delete (getAnimByHandle handleValue)")
        self.assertGreaterEqual(
            helper.rfind("nodeValue = undefined", 0, delete_at),
            0,
            "模式二节点 wrapper 必须在原生删除前释放",
        )
        self.assertIn(
            "try(nodeValue = getAnimByHandle handleValue)catch()",
            helper[:delete_at],
        )
        self.assertIn(
            "detachModifierPanelFromNodeIfNeeded nodeValue",
            helper[:delete_at],
        )

        after_delete = helper[delete_at:]
        self.assertIn("local leftovers = #()", helper)
        self.assertIn(
            "try(nodeValue = getAnimByHandle handleValue)catch()",
            after_delete,
        )
        self.assertIn("append leftovers handleValue", after_delete)
        self.assertIn("nodeValue = undefined", after_delete)

        code_without_comments = "\n".join(
            line.split("--", 1)[0] for line in helper.splitlines()
        ).lower()
        self.assertNotIn("gc(", code_without_comments)
        self.assertNotIn("gc ", code_without_comments)


if __name__ == "__main__":
    unittest.main()
