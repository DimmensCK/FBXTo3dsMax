# -*- coding: utf-8 -*-
"""MAXScript 修改器删除/塌陷后的包装器生命周期回归。"""

from __future__ import annotations

import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
TOPOLOGY_PATH = ROOT / "contents" / "f2m_topology_transfer.py"
SKIN_PATH = ROOT / "contents" / "f2m_skin_replace.py"


def _maxscript_function_source(source: str, name: str) -> str:
    marker = f"    fn {name} "
    start = source.find(marker)
    if start < 0:
        raise AssertionError(f"缺少 MAXScript Helper 函数：{name}")
    end = source.find("\n    fn ", start + len(marker))
    return source[start:] if end < 0 else source[start:end]


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


class HelperModifierReleaseV1320Tests(unittest.TestCase):
    def test_topology_remove_modifier_obeys_handle_only_release_contract(
        self,
    ) -> None:
        source = TOPOLOGY_PATH.read_text(encoding="utf-8-sig")
        helper = _maxscript_function_source(
            source,
            "removeModifierByAnimHandle",
        )
        self.assertIn("local ok = false", helper)
        _assert_order(
            self,
            helper,
            "try(subObjectLevel = 0)catch()",
            "getAnimByHandle modifierHandle",
            "modifierIndex n modInst",
            "modPanel.getCurrentObject()",
            "getHandleByAnim currentObject",
            "if currentHandle == modifierHandle do",
            "n.baseObject",
            "modPanel.setCurrentObject survivor",
            "setCommandPanelTaskMode #create",
        )

        delete_at = helper.index("deleteModifier n stackIndex")
        self.assertGreaterEqual(
            helper.rfind("modInst = undefined", 0, delete_at),
            0,
            "待删修改器 wrapper 必须在原生删除前释放",
        )
        self.assertGreaterEqual(
            helper.rfind("verifiedMod = undefined", 0, delete_at),
            0,
            "删除前按句柄重解析的验证 wrapper 必须释放",
        )
        _assert_order(
            self,
            helper[delete_at:],
            "deleteModifier n stackIndex",
            "getAnimByHandle modifierHandle",
            "modifierIndex n leftoverMod",
            "leftoverMod = undefined",
            "\n        ok",
        )
        self.assertNotIn("deleteModifier n modInst", helper)

        code_without_comments = "\n".join(
            line.split("--", 1)[0] for line in helper.splitlines()
        ).lower()
        self.assertNotIn("gc(", code_without_comments)
        self.assertNotIn("gc ", code_without_comments)

    def test_modifier_instance_wrappers_release_alias_before_handle_delete(
        self,
    ) -> None:
        # Mode 2 is frozen for this incremental fix.  Keep checking only its
        # established wrapper-to-handle hand-off, without imposing topology's
        # new command-panel implementation details on f2m_skin_replace.py.
        for path in (TOPOLOGY_PATH, SKIN_PATH):
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8-sig")
                wrapper = _maxscript_function_source(
                    source,
                    "removeModifierInstance",
                )
                _assert_order(
                    self,
                    wrapper,
                    "getHandleByAnim modInst",
                    "modInst = undefined",
                    "removeModifierByAnimHandle n modifierHandle",
                )

    def test_collapse_drops_destroyed_modifier_aliases_before_more_max_calls(
        self,
    ) -> None:
        source = TOPOLOGY_PATH.read_text(encoding="utf-8-sig")
        helper = _maxscript_function_source(
            source,
            "collapseModifierSafely",
        )
        collapse_at = helper.index("maxOps.CollapseNodeTo n idx true")
        if_ok_at = helper.index("if ok then", collapse_at)
        self.assertLess(
            helper.index("modInst = undefined", collapse_at),
            if_ok_at,
        )
        self.assertLess(
            helper.index("newModNoSkin = undefined", collapse_at),
            if_ok_at,
        )

    def test_channel_copy_releases_modifier_arrays_and_pasted_alias(self) -> None:
        source = TOPOLOGY_PATH.read_text(encoding="utf-8-sig")
        helper = _maxscript_function_source(source, "copyMapChannel")
        collapse_at = helper.index(
            "collapseModifierSafely dst pastedMod"
        )
        self.assertLess(helper.index("beforeMods = #()"), collapse_at)
        self.assertLess(helper.index("afterMods = #()"), collapse_at)
        self.assertLess(
            helper.index("pastedMod = undefined", collapse_at),
            helper.index("collapseMessage = lastMessage", collapse_at),
        )

    def test_temporary_normal_helpers_release_before_selection_restore(
        self,
    ) -> None:
        source = TOPOLOGY_PATH.read_text(encoding="utf-8-sig")
        cases = (
            (
                "canReadExplicitNormals",
                "getHandleByAnim reader",
                "reader = undefined",
                "F2M_Helper.removeModifierByAnimHandle n readerHandle",
            ),
            (
                "snapshotSmoothingInputFlat",
                "getHandleByAnim reader",
                "reader = undefined",
                "F2M_Helper.removeModifierByAnimHandle n readerHandle",
            ),
            (
                "evaluatedEditNormalsMatch",
                "getHandleByAnim verifier",
                "verifier = undefined",
                "F2M_Helper.removeModifierByAnimHandle dstNode verifierHandle",
            ),
        )
        for name, handle_text, release_text, safe_delete_text in cases:
            with self.subTest(name=name):
                helper = _maxscript_function_source(source, name)
                _assert_order(
                    self,
                    helper,
                    handle_text,
                    release_text,
                    safe_delete_text,
                    "select oldSelection",
                )
                self.assertNotIn("deleteModifier n reader", helper)
                self.assertNotIn("deleteModifier dstNode verifier", helper)

    def test_normal_modifier_loop_collects_handles_before_any_delete(self) -> None:
        source = TOPOLOGY_PATH.read_text(encoding="utf-8-sig")
        helper = _maxscript_function_source(
            source,
            "removeF2MNormalModifiers",
        )
        _assert_order(
            self,
            helper,
            "getHandleByAnim m",
            "append modifierHandles modifierHandle",
            "m = undefined",
            "for modifierHandle in modifierHandles do",
            "F2M_Helper.removeModifierByAnimHandle n modifierHandle",
        )
        self.assertIn("local m = undefined", helper)
        self.assertNotIn("deleteModifier n i", helper)
        self.assertNotIn("deleteModifier n m", helper)

    def test_explicit_normal_cleanup_releases_before_native_restore(self) -> None:
        source = TOPOLOGY_PATH.read_text(encoding="utf-8-sig")
        residual = _maxscript_function_source(
            source,
            "copyExplicitNormalResiduals",
        )
        self.assertNotIn("snapshotSmoothingBaselineFlatTransient", source)
        self.assertNotIn("F2M_光滑组法线基线_临时", residual)
        self.assertIn("dstMod = Edit_Normals()", residual)
        self.assertNotIn("dstMod = copy srcMod", residual)
        self.assertNotIn("addModifierWithLocalData dst dstMod", residual)
        self.assertNotIn("deleteModifier src srcMod", residual)
        _assert_order(
            self,
            residual,
            "removeF2MNormalModifiers dst",
            "dstMod = Edit_Normals()",
            "addModifier dst dstMod",
            "resetEditNormalsToSmoothingBaselineStrict dst dstMod",
            "snapshotEditNormalsDataFlat dst dstMod",
            "buildEditNormalResidualSnapshotFlat",
        )
        zero_start = residual.index("if retainedNormalCount == 0 then")
        zero_end = residual.index("else", zero_start)
        zero_branch = residual[zero_start:zero_end]
        self.assertNotIn("getHandleByAnim dstMod", zero_branch)
        self.assertNotIn(
            "F2M_Helper.removeModifierByAnimHandle dst",
            zero_branch,
        )
        self.assertIn("保留一个全蓝色 ", zero_branch)
        self.assertNotIn(
            "\n                   not (removeModifierByAnimHandle dst "
            "emptyModifierHandle)",
            residual,
            "零残差分支不能依赖 struct 内晚声明函数的未限定前向引用",
        )
        self.assertNotIn("useDenseExactFallback", residual)
        _assert_order(
            self,
            residual,
            "getHandleByAnim srcMod",
            "srcMod = undefined",
            "F2M_Helper.removeModifierByAnimHandle src srcReaderHandle",
            "dstMod = undefined",
            "removeF2MNormalModifiers dst",
            "select oldSelection",
        )

        exact = _maxscript_function_source(source, "copyExplicitNormals")
        self.assertNotIn("deleteModifier src srcMod", exact)
        _assert_order(
            self,
            exact,
            "getHandleByAnim srcMod",
            "srcMod = undefined",
            "F2M_Helper.removeModifierByAnimHandle src srcReaderHandle",
            "dstMod = undefined",
            "removeF2MNormalModifiers dst",
            "select oldSelection",
        )

    def test_mode2_releases_deleted_skin_before_find_skin(self) -> None:
        source = SKIN_PATH.read_text(encoding="utf-8-sig")
        function = _python_function_source(
            source,
            "replace_with_source_skin",
        )
        call_at = function.index("removeModifierByAnimHandle(")
        find_at = function.index("if find_skin(src) is not None:", call_at)
        release_at = function.rindex("source_skin = None", 0, call_at)
        safe_current_at = function.rindex(
            "activate_modifier(old_target, target_skin)",
            0,
            call_at,
        )
        self.assertLess(
            release_at,
            call_at,
        )
        self.assertLess(safe_current_at, release_at)
        self.assertLess(safe_current_at, call_at)
        self.assertNotIn("source_skin,", function[call_at:find_at])
        self.assertNotIn(
            "collect_wrappers_before_native_destruction",
            function,
        )
        self.assertNotIn("gc.collect()", function)
        self.assertNotIn("gc light:true", function)

    def test_mode2_fresh_skin_failure_cleanup_is_handle_only_and_fail_closed(
        self,
    ) -> None:
        source = SKIN_PATH.read_text(encoding="utf-8-sig")
        helper = _maxscript_function_source(
            source,
            "createFreshSkinAtIndex",
        )

        self.assertNotIn("deleteModifier targetNode freshSkin", helper)
        safe_delete = (
            "F2M_Helper.removeModifierByAnimHandle targetNode freshHandle"
        )
        call_positions = [
            match.start()
            for match in re.finditer(re.escape(safe_delete), helper)
        ]
        self.assertEqual(
            len(call_positions),
            2,
            "堆栈读回失败和异常失败都必须接入 handle-only 清理",
        )
        for call_at in call_positions:
            handle_at = helper.rfind(
                "getHandleByAnim freshSkin",
                0,
                call_at,
            )
            release_at = helper.rfind(
                "freshSkin = undefined",
                0,
                call_at,
            )
            self.assertGreaterEqual(handle_at, 0)
            self.assertGreater(release_at, handle_at)
            self.assertLess(release_at, call_at)

        self.assertGreaterEqual(helper.count("freshHandle == undefined"), 2)
        self.assertGreaterEqual(helper.count("已停止提交"), 4)

    def test_mapped_channel_fixture_uses_existing_strict_delete_api(self) -> None:
        source = TOPOLOGY_PATH.read_text(encoding="utf-8-sig")
        function = _python_function_source(
            source,
            "run_mapped_channel_selfcheck",
        )
        self.assertIn("_delete_handles_strict(", function)
        self.assertNotIn("_delete_node_handles_strict(", function)
        self.assertIn("if cleanup_error:", function)


if __name__ == "__main__":
    unittest.main()
