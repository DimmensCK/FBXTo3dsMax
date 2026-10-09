# -*- coding: utf-8 -*-
"""English presentation of backend reports; never classify business results.

Only fixed product wording is translated. Unknown technical text, paths, and
identifiers remain available verbatim, including failures from Autodesk/Python.
This module has no Max imports, filesystem writes, or language preference state.
"""
from __future__ import annotations

import re
import string
from typing import Any

TOOL_VERSION = "1.4.25"

# Complete fixed messages precede fragments. Internal Chinese status values
# belong to the engines and must never be replaced with these display values.
CATALOG = {
    "处理中": "Processing",
    "已检查：可安全执行": "Checked: safe to execute",
    "失败：属性预检未通过": "Failed: attribute preflight did not pass",
    "失败：模型不一致": "Failed: models do not match",
    "失败：已回滚": "Failed: rolled back",
    "失败：未匹配": "Failed: no match",
    "失败：替换未完成": "Failed: replacement incomplete",
    "完成：同拓扑传递": "Completed: matching-topology transfer",
    "完成：整模替换": "Completed: mesh replacement",
    "已检查：可替换": "Checked: replacement is possible",
    "已检查：整模替换": "Checked: mesh replacement",
    "部分完成/跳过": "Partially completed / skipped",
    "跳过：需解除对象状态": "Skipped: object state must be cleared",
    "底层操作失败，未返回可读原因。": "The underlying operation failed without a readable reason.",
    "底层操作失败，具体技术信息已写入内部诊断文件。": "The underlying operation failed. Full technical details are in the diagnostic report.",
    "检查完成，未发现错误或警告。": "Check complete. No errors or warnings were found.",
    "检查完成。": "Check complete.",
    "报告文件写入失败，请查看 MaxScript Listener。": "The report could not be written. See the MAXScript Listener.",
    "写入失败，请查看 MaxScript 侦听器。": "Writing failed. See the MAXScript Listener.",
    "传递未完成，失败结果没有提交。": "Transfer incomplete. Failed results were not committed.",
    "正式传递没有成功完成。": "The transfer did not complete successfully.",
    "其它可用属性已继续执行。": "Other available attributes were processed.",
    "以下已勾选的属性在 FBX 目标模型中不存在，已自动跳过对应传递：": "These selected attributes are absent from the FBX target and were skipped:",
    "以下 Max 源模型使用了“光滑组基线 + 自定义法线差异”策略：": "These Max source models used the smoothing-group baseline with custom-normal differences:",
    "插件已先确认最终光滑组：只勾选“顶点法线”时保留模型原有光滑组；同时勾选“光滑组”和“顶点法线”时先写入并读回目标光滑组。随后以实际接收模型最终点位产生的蓝色光滑组法线为基线，与 FBX 目标自定义法线逐面角比较：角差不超过 0.1° 的方向继续保留为蓝色 SG 法线；只有超过 0.1° 的差异才写成绿色/黄色 Explicit 自定义法线。": "The final smoothing groups were verified first. Normals-only keeps the existing groups; combined transfer writes and reads back the target groups first. Each FBX corner normal is compared with the blue SG normal computed from the receiver's final geometry. Differences up to 0.1 degrees remain blue SG normals; larger differences become green/yellow explicit custom normals.",
    "最终每个面角方向仍必须与 FBX 目标一致，否则本次对象会回滚。": "Every final corner direction must still match the FBX target; otherwise this object is rolled back.",
    "3ds Max 导入命令明确返回失败状态。": "The 3ds Max import command explicitly returned failure.",
    "FBX 导入没有创建任何节点。": "FBX import did not create any nodes.",
    "FBX 中没有可处理的几何体。": "The FBX contains no usable geometry.",
    "FBX 中没有与当前选中 Max 源模型同名的目标网格。": "The FBX has no target mesh matching the selected Max source name.",
    "FBX 目标模型与 Max 源模型的基础网格顶点数不同。": "The FBX target and Max source have different base-mesh vertex counts.",
    "FBX 目标模型与 Max 源模型的基础网格面数不同。": "The FBX target and Max source have different base-mesh face counts.",
    "FBX 目标模型与 Max 源模型的基础网格边数不同。": "The FBX target and Max source have different base-mesh edge counts.",
    "变形：完成，已按同序顶点 ID 写入 Max 源模型基础网格；Skin 修改器未删除。": "Shape: completed. Base-mesh vertices were written by matching vertex ID; the Skin modifier was retained.",
    "变形：失败。": "Shape: failed.",
    "光滑组：完成，已按面写入并回读验证。": "Smoothing groups: completed, written per face and verified by readback.",
    "光滑组：失败。": "Smoothing groups: failed.",
    "光滑组：写入后回读验证失败。": "Smoothing groups: readback verification failed after writing.",
    "光滑组：失败，FBX 目标光滑组数量与 Max 源模型面数不一致。": "Smoothing groups: failed. The FBX mask count does not match the Max source face count.",
    "光滑组：失败，旧版残留的顶点法线修改器未能完整清理；为防止旧显式法线继续覆盖新光滑组，本次在写入前停止。": "Smoothing groups: failed before writing because stale plug-in normal modifiers could not be fully removed. They could override the new smoothing groups.",
    "材质：完成，已将 FBX 目标模型材质赋予 Max 源模型。": "Material: completed. The FBX target material was assigned to the Max source.",
    "材质：失败，无法把 FBX 目标模型材质赋予 Max 源模型。": "Material: failed. The FBX target material could not be assigned to the Max source.",
    "材质 ID：完成，已通过 ChannelInfo 多边形通道复制。": "Material IDs: completed using the ChannelInfo polygon channel.",
    "材质 ID：失败，ChannelInfo 多边形通道复制没有成功。": "Material IDs: ChannelInfo polygon-channel copying failed.",
    "材质：因材质/ID 传递未完整成功，已恢复 Max 源模型原材质。": "Material: the original Max source material was restored because material/ID transfer was incomplete.",
    "材质：传递失败后无法恢复 Max 源模型原材质。": "Material: the original Max source material could not be restored after transfer failure.",
    "检查警告：已勾选顶点色 RGB，但 FBX 目标模型没有通道 0；正式执行会跳过。": "Check warning: RGB was selected, but the FBX target has no channel 0. Transfer will skip it.",
    "检查警告：已勾选顶点 Alpha，但 FBX 目标模型没有通道 -2；正式执行会跳过。": "Check warning: Alpha was selected, but the FBX target has no channel -2. Transfer will skip it.",
    "检查结果：已勾选材质与 ID，但 FBX 目标模型没有可赋予的材质。": "Check result: material and IDs were selected, but the FBX target has no assignable material.",
    "检查结果：FBX 目标模型有材质；正式执行会赋予 Max 源模型，并按面映射复制材质 ID。": "Check result: the FBX target has a material. Transfer will assign it to the Max source and copy material IDs through the face mapping.",
    "检查结果：读取 FBX 目标模型材质失败。": "Check result: reading the FBX target material failed.",
    "建议：如果这是改过拓扑的新模型，请改用模式二“替换网格并保留蒙皮”。": "Suggestion: for changed topology, use Mode 2, Replace mesh and retain Skin.",
    "顶点法线：跳过。组合策略要求先成功写入并逐面读回光滑组；本对象的光滑组阶段失败，已禁止在错误基线上继续写法线。": "Normals: skipped. Combined transfer requires smoothing groups to be written and verified per face first. That stage failed, so normals were not written on an invalid baseline.",
    "本对象在失败前产生的可撤销更改，已由 3ds Max 对象级 Undo 块自动回滚。": "This object's undoable changes before failure were rolled back by its 3ds Max Undo block.",
    "整模替换：跳过，FBX 目标模型没有 Skin 修改器。": "Mesh replacement: skipped. The FBX target has no Skin modifier.",
    "整模替换：跳过，FBX 目标模型的 Skin 没有骨骼。": "Mesh replacement: skipped. The FBX target Skin has no bones.",
    "整模替换：提交失败，未报告完成。": "Mesh replacement: commit failed; completion was not reported.",
    "对象没有完整完成，触发对象级回滚。": "The object did not complete; object-level rollback was requested.",
    "场景节点名称没有完整恢复，详见报告。": "Scene node names were not fully restored. See the report.",
    "数据传递报告": "Data transfer report",
    "FBX 到 3ds Max 数据传递报告": "FBX to 3ds Max data transfer report",
    "FBX 到 3ds Max 检查结果": "FBX to 3ds Max check results",
    "FBX 到 3ds Max 属性缺失提醒": "FBX to 3ds Max missing attributes",
    "FBX 到 3ds Max 传递未完成": "FBX to 3ds Max transfer incomplete",
    "顶点法线差异传递说明": "Normal-difference transfer details",
    "FBXTo3dsMax 插件自检": "FBXTo3dsMax self-check",
    "正在准备独立的 3ds Max 自检进程……": "Preparing a dedicated 3ds Max self-check process...",
    "自检在独立进程中运行，不会重置或修改当前打开的场景。": "Self-check runs in a dedicated process and does not reset or modify the current scene.",
    "取消自检": "Cancel self-check",
    "关闭": "Close",
    "已完成 %v / %m 项": "Completed %v / %m checks",
    "自检超时，正在终止独立进程……": "Self-check timed out. Stopping its dedicated process...",
    "正在取消自检并清理独立进程……": "Cancelling self-check and cleaning up its dedicated process...",
    "自检结果已生成，正在等待独立进程自然退出……": "Results are ready. Waiting for the dedicated process to exit naturally...",
    "本次自检没有生成正式报告。": "This self-check did not produce a formal report.",
    "自检结束。": "Self-check finished.",
    "模块、版本、界面与安装完整性": "Modules, version, UI and installation integrity",
    "纯 Python 光滑组与 FBX 元数据": "Pure Python smoothing groups and FBX metadata",
    "过程模型、光滑组与通道写回": "Procedural meshes, smoothing groups and channel readback",
    "内置 FBX 同拓扑与原生平滑层": "Generated matching-topology FBX and native smoothing layers",
    "显式法线空间、共存与失败回滚": "Explicit-normal space, coexistence and failure rollback",
    "内置 FBX 替换与完整蒙皮状态": "Generated FBX replacement and complete Skin state",
    "源代码运行：未发现安装包 SHA-256 清单，跳过本项。": "Source execution: no installed SHA-256 manifest was found; this installed-package check was skipped.",
    "说明：自检覆盖已知关键不变量和内置样本，不能证明不存在所有未知缺陷。": "Self-check covers known key invariants and generated fixtures; it cannot establish the absence of every unknown defect.",
    "普通自动法线已正确拒绝；选择与临时修改器栈均已恢复": "Automatic normals were correctly rejected; selection and the temporary modifier stack were restored",
    "已检测用户的“编辑法线”修改器干扰；F2M 状态已回滚": "User Edit Normals interference was detected; F2M state was rolled back",
    "光滑组 1 与局部显式法线可共存，并在保存/重新载入后保持": "SG 1 and local explicit normals coexist and survive save/reload",
    "光滑组 DSATUR、32 位与间接泄漏测试通过。": "Smoothing-group DSATUR, 32-bit and indirect-leak tests passed.",
    "光滑组算法测试通过。": "Smoothing algorithm tests passed.",
    "蒙皮替换集成自检通过。": "Skin replacement integration checks passed.",
    "蒙皮替换集成自检失败。": "Skin replacement integration checks failed.",
    "夹具完全由本次自检程序生成。": "The fixture was generated entirely by this self-check.",
    "通过": "Passed",
    "失败": "Failed",
    "已完成": "Completed",
    "正在运行": "Running",
    "正在启动": "Starting",
    "检查失败": "Check failed",
    "【父控制器最终判定】": "[Parent controller final verdict]",
    "【父控制器进程退出门禁】": "[Parent controller process-exit gate]",
    "原生日志：": "Native log: ",
    "原业务检查摘要：": "Original business-check summary: ",
    "未找到": "Not found",
    "无法核验本次独立 3ds Max 子进程的原生日志，不能确认没有 MAXScript 内存收集错误。": "The dedicated 3ds Max child's native log could not be verified; the absence of MAXScript garbage-collection errors cannot be confirmed.",
    "说明：下方六项业务检查结果不能覆盖上述原生进程错误。": "The six business checks below do not override the native-process error above.",
    "说明：下方保留子进程原始业务报告及其它父控制器门禁信息。": "The original child business report and other parent-controller verdicts are retained below.",
    "独立 3ds Max Batch 在业务结果生成后触发了强制结束，不能把该业务结果视为真实完成。": "The dedicated 3ds Max Batch was forcibly stopped after its business result; that result cannot establish genuine completion.",
    "没有观察到独立 3ds Max Batch 完全退出。": "The dedicated 3ds Max Batch was not observed to exit completely.",
}

# Bounded, product-owned prefixes/fragments. Names and paths embedded in the
# remaining text are left intact; do not translate arbitrary Chinese words.
FRAGMENTS = {
    "作者：": "Author: ",
    "报告文件：": "Report file: ",
    "数据方向：Max 源模型 ": "Data direction: Max source ",
    "Max 源模型 <- FBX 目标模型": "Max source <- FBX target",
    "<- FBX 目标模型": "<- FBX target",
    "FBX 目标模型统计：点 ": "FBX target counts: vertices ",
    "Max 源模型统计：点 ": "Max source counts: vertices ",
    "，边 ": ", edges ",
    "，基础多边面 ": ", base polygons ",
    "成对变换警告：": "Paired transform warning: ",
    "状态提醒：": "Object-state warning: ",
    "检查结果：": "Check result: ",
    "检查警告：": "Check warning: ",
    "执行警告：": "Execution warning: ",
    "模式一失败：": "Mode 1 failed: ",
    "传递失败：": "Transfer failed: ",
    "对象处理发生异常：": "Object processing raised an exception: ",
    "恢复阶段错误：": "Recovery errors: ",
    "清理失败：": "Cleanup failed: ",
    "名称恢复失败：": "Name restoration failed: ",
    "内部诊断文件：": "Diagnostic report: ",
    "内部诊断报告：": "Diagnostic report: ",
    "进程诊断输出：": "Process diagnostic output: ",
    "详细报告：": "Detailed report: ",
    "完整报告：": "Full report: ",
    "更多内容：": "More details: ",
    "报告：": "Report: ",
    "错误：": "Errors: ",
    "警告：": "Warnings: ",
    "提醒：": "Notice: ",
    "自检失败：": "Self-check failed: ",
    "自检通过：": "Self-check passed: ",
    " 自检": " self-check ",
    " 项通过。": " checks passed.",
    " 毫秒）": " ms)",
    "（": " (",
    "已用时：": "Elapsed: ",
    " 秒。": " seconds.",
    "上一项结果：": "Previous check: ",
    "正在自检 ": "Running self-check ",
    "正在启动独立的 3ds Max Batch": "Starting a dedicated 3ds Max Batch",
    "3ds Max 原生日志核验：": "3ds Max native-log verification: ",
    "本次子进程增量未发现 MAXScript 内存收集错误。": "No MAXScript garbage-collection errors were found in this child's log delta.",
    "未能确认本次子进程日志。": "This child's native log could not be verified.",
    "发现 ": "Found ",
    " 条 MAXScript 内存收集错误。": " MAXScript garbage-collection errors.",
    "普通自动法线：": "Automatic normals: ",
    "法线逆转置：": "Inverse-transpose normals: ",
    "上层法线覆盖：": "Upper normal override: ",
    "光滑组与显式法线共存：": "SG and explicit-normal coexistence: ",
    "逆转置旋转/非均匀缩放误差=": "Inverse-transpose rotation/nonuniform-scale error=",
    "软边": "soft edge",
    "硬边": "hard edge",
    "第 32 位": "bit 32",
    "确定性": "determinism",
    "组数溢出时安全停止": "fail closed on group overflow",
    "非流形时安全停止": "fail closed on non-manifold input",
    "二进制 FBX": "binary FBX",
    "：通过——": ": PASS - ",
    "：失败": ": FAIL",
    "：": ": ",
    "；": "; ",
    "。": ".",
    "——": " - ",
}

CATALOG.update({
    "未匹配": "Unmatched",
    "已检查": "Checked",
    "自检": "Self-check",
    "显式法线": "Specified normals",
    "光滑组": "Smoothing groups",
    "失败：批次回滚不完整": "Failed: batch rollback incomplete",
    "失败：批次已回滚": "Failed: batch rolled back",
    "失败：整模替换": "Failed: mesh replacement",
    "失败：FBX 目标模型无材质": "Failed: FBX target has no material",
    "失败：读取材质": "Failed: material read",
    "失败：需解除对象状态": "Failed: object state must be cleared",
    "完成：替换网格并保留蒙皮": "Completed: mesh replacement retaining Skin",
    "失败：替换网格并保留蒙皮": "Failed: mesh replacement retaining Skin",
    "拓扑映射自检通过：同向循环换起点、唯一面序重排、贴图面面角映射、逐面值映射及反向绕序阻断均正常。": "Topology mapping passed: same-winding cyclic rotations, unique face reorder, map-face corner mapping, per-face values and reverse-winding rejection.",
    "真实 Max 非恒等映射通道自检通过：变形、UV、顶点色 RGB、顶点 Alpha、光滑组、材质 ID、显式法线均按面/角映射读回；光滑组与局部显式法线共存；混合的可编辑网格/可编辑多边形写入预检已安全阻断。": "Real Max non-identity mapping passed: shape, UV, RGB, Alpha, SG, material IDs and specified normals were read back through face/corner mapping. SG and local normals coexist; mixed Editable Mesh/Poly writing was safely blocked in preflight.",
    "运行文件、绝对路径与版本": "Runtime files, absolute paths and versions",
    "光滑组纯算法与32位限制": "Pure smoothing algorithm and 32-bit limits",
    "3ds Max 过程网格与修改器栈": "3ds Max procedural meshes and modifier stacks",
    "内置 FBX 同拓扑完整链路": "Generated FBX matching-topology workflow",
    "内置 FBX 蒙皮替换完整链路": "Generated FBX Skin replacement workflow",
    "FBX 原生平滑层 / Autodesk 精确导入": "Native FBX smoothing layer / exact Autodesk import",
    "FBX 导入设置：导入模式=创建，动画=关闭，蒙皮=开启（读取求值网格/法线）。": "FBX import: Create mode; animation off; Skin on to read evaluated geometry and normals.",
    "FBX 导入设置：导入光滑组=开启，由 Autodesk FBX 导入器从 FBX 目标的平滑信息/法线生成 Max 光滑组。": "FBX import: smoothing groups on. The Autodesk importer derives Max groups from the FBX target's smoothing data and normals.",
    "FBX 导入设置：导入光滑组=关闭，保留 FBX 显式/自定义法线。": "FBX import: smoothing groups off; FBX specified/custom normals retained.",
    "FBX 导入设置：导入模式=创建，动画=关闭，蒙皮=开启，光滑组导入=关闭（优先保留 FBX 显式/自定义法线）。": "FBX import: Create mode; animation off; Skin on; smoothing groups off to retain FBX specified/custom normals.",
    "组合路径不再批量预读接收端光滑组；将逐对象明确写入并读回 FBX 光滑组，再处理自定义法线。": "Combined transfer writes and verifies FBX smoothing groups per object before processing custom normals; it does not pre-read all receivers' groups.",
    "仅法线路径不再批量预读接收端光滑组；将在处理每个对象前 即时读取当前对象，避免跨对象保留 MAXWrapper。": "Normals-only reads the receiver's groups immediately before each object, avoiding MAXWrapper references across object boundaries.",
    "光滑组与显式法线同时启用：严格 FBX 解析/求解已在独立 Python 子进程完成；Max 主进程只执行一次 SmoothingGroups=false 精确导入。该路径不回退到主进程解析，不在密集 Edit Normals 残差前执行第二次导入或额外源法线读取器生命周期。": "Combined SG and normals: strict FBX parsing/solving ran in a separate Python process. Max performs one exact import with SmoothingGroups=false. There is no in-process parser fallback, second import or extra source-normal reader before residual processing.",
    "光滑组启用：执行双重隔离导入；第一次取得 Autodesk 原生层结果，第二次保留面角法线供无原生层时的 DSATUR 求解。": "SG-only uses two isolated imports: the first obtains Autodesk's native-layer result; the second retains corner normals for DSATUR when no native layer exists.",
    "仅传递顶点法线且 Max 源模型已有光滑组：只导入一次 FBX 完整自定义法线；蓝色 SG 基线直接由实际接收模型的现有光滑组和点位生成。": "Normals-only with existing Max SG: one FBX import reads all custom normals. The blue SG baseline comes from the actual receiver's groups and vertex positions.",
    "已有同名 Max 源模型使用了这个 FBX 目标网格，跳过重复匹配。": "Another same-name Max source already uses this FBX target; the duplicate match was skipped.",
    "模式一失败：FBX 目标模型与 Max 源模型无法建立安全拓扑映射，已停止传递。": "Mode 1 failed: a safe topology mapping could not be built between the FBX target and Max source. Transfer stopped.",
    "检查结果：模式一不能安全传递。": "Check result: Mode 1 cannot transfer safely.",
    "检查结果：Max 源模型基础网格不支持逐面写入光滑组。": "Check result: the Max source base mesh cannot write smoothing groups per face.",
    "检查结果：读取/验证光滑组失败。": "Check result: smoothing-group reading/validation failed.",
    "检查结果：FBX 目标模型的面角显式法线可读取。": "Check result: the FBX target's specified corner normals can be read.",
    "检查结果：无法读取 FBX 目标模型的显式法线，正式执行已被阻断。": "Check result: the FBX target's specified normals could not be read. Transfer is blocked.",
    "组合法线策略：光滑组数据已先行写入并读回；随后只保留光滑组不能等价表达的自定义法线残差；全部面角最终方向必须与 FBX 目标一致。": "Combined normal strategy: SG was written and verified first. Only custom-normal residuals that SG cannot represent are retained; every final corner direction must match the FBX target.",
    "仅法线差异策略：Max 源模型已有非零光滑组，本次不改写这些光滑组；以现有蓝色 SG 法线为基线，只保留与 FBX 目标方向角差超过 0.1° 的自定义法线。": "Normals-only difference strategy: existing nonzero Max SG is retained. Only custom-normal differences above 0.1 degrees from the existing blue SG baseline are kept.",
    "残差验收：顶点法线写入后已再次逐面读取光滑组，掩码保持不变。": "Residual verification: SG was read again per face after writing normals; masks are unchanged.",
    "仅法线完整复制策略：Max 源模型逐面光滑组全部为 0，已完整覆写 FBX 自定义法线。": "Normals-only full-copy strategy: all Max face SG masks are zero; all FBX custom normals were copied.",
    "残差验收：顶点法线写入后的光滑组回读失败。": "Residual verification: SG readback failed after writing normals.",
    "整模替换：自动模式不调用 Skin Load Envelope 弹窗，改用逐顶点权重写入，避免 Max 卡在匹配窗口。": "Mesh replacement writes weights per vertex without the Skin Load Envelope matching dialog.",
    "整模替换：不调用 Skin Load Envelope 弹窗；保留 FBX 网格/材质/通道/法线，复制 Max 源 Skin 的场景骨骼与 local data；候选 Mesh Bind TM 采用 addModifierWithLocalData 为新 FBX 节点建立的实际值，仅按名称写入 FBX 顶点权重状态。": "Mesh replacement keeps the FBX mesh, material, channels and normals. It copies Max source Skin scene bones and local data without a Load Envelope dialog, retains the candidate Mesh Bind established by addModifierWithLocalData, and writes FBX vertex weight state by bone name.",
    "整模替换：新候选已继承 Max 源模型图层/显示状态；临时 FBX 导入层的隐藏状态不会进入最终节点。": "Mesh replacement: the candidate inherited Max source layer/display state. Temporary FBX import-layer visibility does not control the final node.",
    "整模替换：正式提交时会继承 Max 源模型的图层、隐藏/冻结、Box Mode、Renderable 与当前 Visibility，避免临时 FBX 导入层决定最终可见性。": "Mesh replacement: commit inherits the Max source layer, hidden/frozen state, Box Mode, Renderable and current Visibility.",
    "整模替换：可执行。已读取 FBX 全部逐顶点权重/归一化/DQ，且每条实际权重影响都能唯一映射到 Max 源 Skin；正式执行时会把 Max Skin 及本地绑定数据复制到 FBX 网格原 Skin 栈位，再写入 FBX 权重。": "Mesh replacement: ready. All FBX weights, normalization and DQ state were read, and each used influence uniquely maps to Max source Skin. Transfer copies Max Skin/local binding data at the original FBX Skin stack position, then writes FBX weights.",
    "整模替换：FBX 目标候选的节点、基础对象、材质对象、网格统计、对象变换、Pivot、目标图层/显示状态、非 Skin 修改器身份以及评估后全部世界顶点/包围盒已在 Skin 重建后读回不变；材质 ID、UV、顶点色、Alpha 与锁定法线没有进入复制路径，继续保留在同一个 FBX 候选基础对象中。": "Mesh replacement: node/base-object/material identity, mesh counts, transform, pivot, layer/display state, non-Skin modifiers and all evaluated world vertices/bounds were verified unchanged after rebuilding Skin. Material IDs, UV, RGB, Alpha and locked normals remain on the same FBX base object.",
    "整模替换：已按显式兼容选项改用 Max 源模型材质。": "Mesh replacement: the explicit compatibility option selected the Max source material.",
    "整模替换：复制 Max 源模型 Skin 到新网格失败，未得到有效 Skin 修改器。": "Mesh replacement: copying Max source Skin did not produce a valid Skin modifier.",
    "整模替换：复制后在新网格上没有找到 Skin 修改器。": "Mesh replacement: no Skin modifier was found on the new mesh after copying.",
    "整模替换：复制后的 Max Skin 没有位于原 FBX Skin 栈位，已停止提交。": "Mesh replacement: copied Max Skin is not at the original FBX Skin stack position. Commit stopped.",
    "替换失败：FBX 目标模型没有 Skin 修改器；模式二要求 FBX 目标模型必须带骨骼蒙皮。": "Replacement failed: the FBX target has no Skin modifier; Mode 2 requires a skinned FBX target.",
    "替换失败：Max 源模型没有 Skin 修改器；模式二需要从它确认场景骨架。": "Replacement failed: the Max source has no Skin modifier from which to identify the scene skeleton.",
    "整模替换：删除 FBX 目标模型自带 Skin 失败，已停止，避免新网格堆栈里残留多个 Skin。": "Mesh replacement: deleting the original FBX Skin failed. Transfer stopped to avoid multiple Skin modifiers on the candidate.",
    "整模替换：Skin 权重没有使用唯一允许的逐顶点权威写入路径，候选不会提交。": "Mesh replacement: Skin weights did not use the required per-vertex authority path. The candidate will not be committed.",
    "整模替换：检测到已废止的批量首写/回退状态，候选不会提交。": "Mesh replacement: retired bulk-write/fallback state was detected. The candidate will not be committed.",
    "整模替换：复制 Max 源模型蒙皮到新网格失败。": "Mesh replacement: copying Max source Skin to the new mesh failed.",
    "替换失败：无法读取 FBX 目标模型蒙皮数量。": "Replacement failed: the FBX target Skin count could not be read.",
    "替换失败：无法读取 Max 源模型蒙皮数量。": "Replacement failed: the Max source Skin count could not be read.",
    "整模替换：失败，FBX 权重或 Max 源 Skin 的场景骨架/本地绑定没有通过只读检查。": "Mesh replacement: the read-only checks of FBX weights or Max source Skin scene bones/local binding did not pass.",
    "整模替换：无法把新候选从 FBX 临时层级安全分离，或无法继承 Max 源模型图层/显示状态。": "Mesh replacement: the candidate could not be safely detached from temporary FBX hierarchy or could not inherit Max source layer/display state.",
    "整模替换：无法建立 FBX 目标网格权威快照，已停止。": "Mesh replacement: the FBX target authority snapshot could not be created. Transfer stopped.",
    "整模替换：删除 FBX 目标模型自带蒙皮失败。": "Mesh replacement: deleting the original FBX target Skin failed.",
    "整模替换：复制 Max Skin 本地绑定数据、映射/写入 FBX 权重或目标网格身份读回失败，Max 源模型尚未提交变更。": "Mesh replacement: copying Max Skin local binding, mapping/writing FBX weights or target identity readback failed. No change to the Max source was committed.",
    "整模替换：提交前无法建立最终候选权威快照，Max 源模型尚未变更。": "Mesh replacement: the final candidate authority snapshot could not be created before commit. The Max source is unchanged.",
    "整模替换：读取 Max 源模型材质失败，已在修改候选前停止。": "Mesh replacement: reading the Max source material failed. Transfer stopped before changing the candidate.",
    "整模替换：复制 Max 源模型材质到候选失败，Max 源模型尚未提交变更。": "Mesh replacement: copying the Max source material to the candidate failed. The Max source is unchanged.",
    "检查结果：当前是替换网格并保留蒙皮模式，通道勾选不会参与判断。正式执行会以 FBX 目标网格数据为准，复制 Max 源模型 Skin，并按骨骼名称写入 FBX Skin 权重。": "Check result: mesh replacement retains Skin; channel checkboxes do not determine this mode. The FBX target owns mesh data, Max source Skin is copied, and FBX weights are written by bone name.",
    "检查结果：FBX 目标模型带 Skin，可尝试整模替换并按骨骼名称重建 Max 源模型的 Skin。": "Check result: the FBX target has Skin; mesh replacement can rebuild the Max source Skin by bone name.",
    "检查结果：FBX 目标模型没有 Skin，不能走整模替换保留蒙皮。": "Check result: the FBX target has no Skin; replacement retaining Skin is unavailable.",
    "变形：跳过，点数不一致。": "Shape: skipped because vertex counts differ.",
    "变形：完成，直接写入 Max 源模型基础网格，Skin 修改器未删除。": "Shape: completed by writing the Max source base mesh; Skin was retained.",
    "材质：失败，FBX 目标模型没有可赋予的材质。": "Material: failed because the FBX target has no assignable material.",
    "检查结果：FBX 目标模型有材质；正式执行会赋予 Max 源模型，并通过 ChannelInfo 多边形通道复制材质 ID。": "Check result: the FBX target material will be assigned to the Max source; IDs will be copied through the ChannelInfo polygon channel.",
})

FRAGMENTS.update({
    "FBX 到 3ds Max 同拓扑数据传递开始 v": "FBX to 3ds Max matching-topology transfer started, v",
    "FBX 到 3ds Max 替换网格并保留蒙皮开始 v": "FBX to 3ds Max mesh replacement retaining Skin started, v",
    " / 作者：": " / Author: ",
    "FBX 原生导入安全边界：已解除 Modify 面板当前对象并切换到 Create；此前面板模式=": "Native FBX import guard: current Modify object detached and panel switched to Create; previous panel mode=",
    "已导入 FBX：": "Imported FBX: ",
    "本次导入节点数量：": "Imported node count: ",
    "导入节点数量：": "Imported node count: ",
    "FBX 目标网格数量：": "FBX target mesh count: ",
    "选中 Max 源网格数量：": "Selected Max source mesh count: ",
    "传递方向：Max 源模型 ": "Transfer direction: Max source ",
    "匹配：Max 源模型 ": "Match: Max source ",
    "，面 ": ", faces ",
    "执行提醒：已勾选 ": "Execution notice: selected ",
    "，但 FBX 目标模型没有该属性；已跳过对应传递。": " is absent from the FBX target; this attribute was skipped.",
    "：跳过，严格拓扑不一致。": ": skipped because strict topology differs. ",
    "：跳过，点/边/面数量不完全一致。": ": skipped because vertex/edge/face counts differ. ",
    "：跳过，FBX 目标模型没有通道 ": ": skipped; the FBX target has no channel ",
    "：跳过，FBX 目标模型没有这个通道。": ": skipped; the FBX target has no such channel. ",
    "：直接写入不可用，准备使用 ChannelInfo。": ": direct writing is unavailable; trying ChannelInfo. ",
    "：失败。直接映射写入不可用，当前面/角顺序存在映射，不能退回到不支持映射的 ChannelInfo。": ": failed. Direct mapped writing is unavailable, and the changed face/corner mapping forbids fallback to unmapped ChannelInfo. ",
    "：完成。": ": completed. ",
    "：失败。": ": failed. ",
    "UV 通道 ": "UV channel ",
    "顶点法线：": "Vertex normals: ",
    "光滑组：": "Smoothing groups: ",
    "材质与 ID：": "Material / IDs: ",
    "变形：": "Shape: ",
    "顶点色 RGB": "Vertex RGB",
    "顶点 Alpha": "Vertex Alpha",
    "完成，按相同顶点 ID 写入 Max 源模型基础网格，Skin 修改器未删除。": "Completed by writing the Max source base mesh by identical vertex ID; Skin was retained. ",
    "MaxScript 内存堆安全下限已确认：": "MAXScript heap safety floor verified: ",
    " 字节；仅扩充不足的会话，不主动垃圾回收。": " bytes; only undersized sessions were expanded; no explicit garbage collection.",
    " 对象完成：已释放当前对象代理并停靠 Modify 面板；未主动触发垃圾回收。": " completed: current node wrapper released and Modify panel parked; no explicit garbage collection.",
    "运行文件齐全，绝对路径加载、v": "All runtime files are present. Absolute-path loading, v",
    " 版本、界面结果回传、模式一布局和仅默认勾选“变形”均通过；": " version, UI result bridge, Mode 1 layout and Shape-only defaults passed; ",
    "安装包清单 SHA-256：": "Installed package SHA-256 manifest: ",
    "安装后哈希清单 ": "Installed SHA-256 manifest: ",
    " 项全部匹配，目标集合与安装源清单完全一致。": " targets matched; the target set exactly equals the installation source manifest.",
    "；程序生成的 FBX 平滑元数据、独立子进程拓扑摘要与光滑组求解通过。": "; generated FBX smoothing metadata, isolated topology digests and smoothing solutions passed.",
    "严格拓扑、变形、顶点色/Alpha、材质ID、普通/第32位光滑组读回、Editable Mesh+Skin 基础 TriMesh 事务写回、同一光滑组+局部显式法线共存及保存重载、同数量异拓扑阻断、修改器栈保护均通过；": "Strict topology, shape, RGB/Alpha, material IDs, normal/bit-32 SG readback, Editable Mesh+Skin base TriMesh transactions, SG/local-normal coexistence across save/reload, equal-count topology mismatch rejection and modifier-stack protection passed; ",
    "程序生成的 FBX 的无原生层 DSATUR、预检、UV": "Generated FBX non-native-layer DSATUR, preflight and UV",
    "/光滑组": "/smoothing groups",
    "/显式法线": "/specified normals",
    "（诊断关闭光滑组）": " (SG disabled for diagnostics)",
    "（诊断关闭显式法线）": " (specified normals disabled for diagnostics)",
    "实际写入，以及程序生成的 FBX 的原生 LayerElementSmoothing 精确保留、清理与恢复均通过。": " actual writing, exact preservation of the generated FBX native LayerElementSmoothing, cleanup and restoration passed.",
    "内置蒙皮 FBX 的差异源哨兵、预检、备份式与删除式实际替换、保存重载、FBX 内容指纹、完整骨骼名称/场景句柄映射、": "Generated Skin FBX differential source sentinel, preflight, backed-up/deletion replacement, save/reload, FBX content fingerprint and complete bone-name/scene-handle mapping passed; ",
    " 个网格/": " meshes / ",
    " 个顶点权重、": " vertex weights; ",
    " 个骨骼槽的 Bind TM/Stretch TM/包络、": " bone slots' Bind TM/Stretch TM/envelopes; ",
    "全局 Skin 参数、归一化与 DQ 状态全量读回通过。": "global Skin parameters, normalization and DQ state passed full readback.",
    "普通自动法线": "Automatic normals",
    "显式法线": "Specified normals",
    "光滑组": "Smoothing groups",
})

# Template fields are copied exactly, so numbers, user node names, identifiers
# and exception details do not accidentally become translation keys.
TEMPLATES = (
    ("独立 3ds Max 子进程完全退出后，在本次新增的原生日志中发现 {0} 条 MAXScript 内存收集错误。", "After the dedicated 3ds Max child exited completely, {0} MAXScript garbage-collection errors were found in its new native-log entries."),
    ("独立 3ds Max Batch 未以退出代码 0 完成（实际退出代码 {0}）。", "The dedicated 3ds Max Batch did not complete with exit code 0 (actual exit code: {0})."),
    ("FBXTo3dsMax v{0} 自检通过：{1}/{2} 项通过。", "FBXTo3dsMax v{0} self-check Passed: {1}/{2} checks passed."),
    ("FBXTo3dsMax v{0} 自检失败：{1}/{2} 项通过。", "FBXTo3dsMax v{0} self-check Failed: {1}/{2} checks passed."),
    ("FBX 到 3ds Max 数据传递报告 v{0}", "FBX to 3ds Max transfer report v{0}"),
    ("运行文件齐全，绝对路径加载、v{0} 版本、界面结果回传、模式一布局和仅默认勾选“变形”均通过；源码运行：未发现安装后 SHA-256 清单，跳过该项。", "All runtime files are present. Absolute-path loading, v{0}, UI result bridge, Mode 1 layout and Shape-only defaults passed. Source execution: no installed SHA-256 manifest; that check was skipped."),
    ("运行文件齐全，绝对路径加载、v{0} 版本、界面结果回传、模式一布局和仅默认勾选“变形”均通过；安装后哈希清单 {1} 项全部匹配，目标集合与安装源清单完全一致。", "All runtime files are present. Absolute-path loading, v{0}, UI result bridge, Mode 1 layout and Shape-only defaults passed. All {1} installed SHA-256 targets matched the installation source manifest."),
    ("FBX 目标模型统计：点 {0}，边 {1}，基础多边面 {2}", "FBX target counts: vertices {0}, edges {1}, base polygons {2}"),
    ("Max 源模型统计：点 {0}，边 {1}，基础多边面 {2}", "Max source counts: vertices {0}, edges {1}, base polygons {2}"),
    ("FBX 目标模型统计：点 {0}，边 {1}，面 {2}", "FBX target counts: vertices {0}, edges {1}, faces {2}"),
    ("Max 源模型统计：点 {0}，边 {1}，面 {2}", "Max source counts: vertices {0}, edges {1}, faces {2}"),
    ("传递方向：Max 源模型 {0} <- FBX 目标模型 {1}", "Transfer direction: Max source {0} <- FBX target {1}"),
    ("匹配：Max 源模型 {0} <- FBX 目标模型 {1}", "Match: Max source {0} <- FBX target {1}"),
    ("FBX 平滑元数据：Mesh {0} 个，其中 {1} 个含原生 LayerElementSmoothing。", "FBX smoothing metadata: {0} meshes, {1} with native LayerElementSmoothing."),
    ("FBX 严格解析已在 Max 自带独立 Python 子进程完成：Mesh {0} 个，其中 {1} 个含 ByPolygon/Direct 原生平滑层；Max 主进程只接收已验证的拓扑摘要、逐面 signed int32 掩码和求解统计。", "Strict FBX parsing completed in a separate Max Python process: {0} meshes, {1} with ByPolygon/Direct native smoothing. Max receives verified topology digests, signed-int32 face masks and solver statistics."),
    ("{0}：检测到原生 LayerElementSmoothing；保留 Autodesk 导入的 32 位逐面掩码，自定义法线独立处理。", "{0}: native LayerElementSmoothing detected; Autodesk's 32-bit face masks retained; custom normals handled independently."),
    ("{0}：原生 LayerElementSmoothing 已从 FBX 文件直接解析；其 {1} 面拓扑摘要将在正式拓扑映射已有的唯一读取中同步验证；未执行第二次 FBX 导入。", "{0}: native LayerElementSmoothing parsed directly from FBX; the {1}-face topology digest is verified during the existing topology read; no second FBX import."),
    ("{0}：仅传递顶点法线，即时检测到现有非零光滑组；将保留该光滑组，并只写入超过 0.1° 的法线差异。", "{0}: normals-only detected nonzero receiver SG; groups are retained and only normal differences above 0.1 degrees are written."),
    ("{0}：仅传递顶点法线，即时检测完成；现有光滑组全部为 0；将完整复制 FBX 自定义法线。", "{0}: normals-only detected all-zero receiver SG; all FBX custom normals will be copied."),
    ("UV 通道 {0}：完成。{1}", "UV channel {0}: completed. {1}"),
    ("UV 通道 {0}：失败。{1}", "UV channel {0}: failed. {1}"),
    ("UV 通道 {0}：跳过，FBX 目标模型没有这个通道。", "UV channel {0}: skipped; the FBX target has no such channel."),
    ("检查警告：已勾选传递 UV {0}，但 FBX 目标模型没有这个 UV 集；正式执行会跳过该通道。", "Check warning: UV {0} is selected but absent from the FBX target; transfer will skip this channel."),
    ("执行提醒：已勾选 {0}，但 FBX 目标模型没有该属性；已跳过对应传递。", "Execution notice: selected attribute {0} is absent from the FBX target and was skipped."),
    ("整模替换：FBX Skin 完整骨骼 {0} 个，本网格权重实际使用 {1} 个，Max 源模型 Skin 骨骼 {2} 个，最终保留 Max Skin 的 {3} 个场景骨骼槽和绑定坐标系；顶点 {4} 个。", "Mesh replacement: FBX Skin has {0} bones, {1} used by this mesh; Max source Skin has {2}. The final Skin retains {3} Max scene bone slots and binding coordinates; {4} vertices."),
    ("整模替换：顶点附加状态已完整读取；未归一化顶点 {0} 个，非零 DQ 权重顶点 {1} 个，全局 DQ 开关为 {2}；Max Skin 语义参数 {3} 项、Max 逐骨绑定状态 {4} 项。", "Mesh replacement: vertex state read completely; {0} unnormalized vertices, {1} with nonzero DQ, global DQ={2}; {3} Max Skin semantic properties and {4} per-bone binding states."),
    ("整模替换：已保留 Max Skin 场景骨骼表和本地绑定状态 {0} 个，并读回验证骨骼节点身份、绑定矩阵、逐骨包络、全局参数及 {1}/{2} 个顶点权重；写入路径：{3}。", "Mesh replacement: retained {0} Max Skin scene bones/local binding states; bone identities, bind matrices, envelopes, global parameters and {1}/{2} vertex weights verified; write method: {3}."),
    ("整模替换：完成。最终节点就是 FBX 目标网格；材质/通道/锁定法线与 FBX 一致，全部 {0}/{1} 个顶点权重/归一化/DQ 来自 FBX；Skin 场景骨骼、Bone Bind/Stretch/包络来自 Max 源模型，Mesh Bind 使用候选自适应 local data；评估后世界顶点、包围盒与可见性均已在提交前后完整读回。", "Mesh replacement: completed. The final node is the FBX target, retaining its material/channels/locked normals. All {0}/{1} weights, normalization and DQ come from FBX; scene bones and Bone Bind/Stretch/envelopes come from Max source Skin. Mesh Bind uses the candidate's adapted local data. Evaluated world vertices, bounds and visibility were fully verified before and after commit."),
    ("替换失败：FBX 目标模型必须恰好有 1 个 Skin，实际为 {0} 个。", "Replacement failed: the FBX target needs exactly one Skin; actual count: {0}."),
    ("替换失败：Max 源模型必须恰好有 1 个 Skin，实际为 {0} 个。", "Replacement failed: the Max source needs exactly one Skin; actual count: {0}."),
    ("FBX 中存在多个同名目标网格 `{0}`，无法安全匹配。", "The FBX contains multiple target meshes named `{0}`; safe matching is impossible."),
    ("批次事务已回滚 {0} 个已提交对象：{1}", "The batch transaction rolled back {0} committed objects: {1}"),
    ("...还有 {0} 条，详见报告文件。", "...{0} more items. See the report file."),
)


def _template_pattern(source: str):
    parts = []
    for literal, field, _format, _conversion in string.Formatter().parse(source):
        parts.append(re.escape(literal))
        if field is not None:
            parts.append("(?P<f" + field + ">[^\\r\\n]*?)")
    return re.compile("^" + "".join(parts) + "$")


_TEMPLATES = tuple((_template_pattern(source), target) for source, target in TEMPLATES)

_BUSINESS_STATES = frozenset(
    key for key in CATALOG
    if key.startswith(("完成：", "失败：", "已检查：", "跳过："))
) | {"处理中", "未匹配", "已检查", "部分完成/跳过"}

_REPORT_PREFIXES = tuple(
    (source, FRAGMENTS[source]) for source in sorted(FRAGMENTS, key=len, reverse=True)
    if (source.endswith(("：", "=", "： "))
        or source.endswith("开始 v")
        or source in ("正在自检 ", "正在启动独立的 3ds Max Batch"))
)


def _retain_unknown(value: str, original: str) -> str:
    if re.search(r"[\u3400-\u9fff]", value):
        return value + "\nTechnical detail (original retained): " + original
    return value


def translate_english(text: Any) -> str:
    """Translate fixed report wording, retaining every unknown technical detail.

    English/native exception text is passed through unchanged. A remaining
    Chinese technical message is explicitly labelled as original detail rather
    than hidden, replaced with a success message, or guessed at.
    """
    original = str(text or "")
    if not original or not re.search(r"[\u3400-\u9fff]", original):
        return original
    if "Technical detail (original retained): " in original:
        return original
    if original in CATALOG:
        return CATALOG[original]
    bullet = re.match(r"^(\s*[-*]\s+)(.+)$", original)
    if bullet:
        return bullet.group(1) + translate_english(bullet.group(2))
    status = re.match(r"^(\s*)\[([^\]]+)\](.*)$", original)
    if status and status.group(2) in ("通过", "失败"):
        suffix = status.group(3)
        elapsed = re.match(r"^(\s*)(.*?)（(\d+) 毫秒）$", suffix)
        if elapsed and elapsed.group(2) in CATALOG:
            suffix = (elapsed.group(1) + CATALOG.get(elapsed.group(2), elapsed.group(2))
                      + " (" + elapsed.group(3) + " ms)")
            return status.group(1) + "[" + CATALOG[status.group(2)] + "]" + suffix
    # Summary rows are [fixed business status] opaque node name. Popup rows
    # reverse these fields. Recognize only business statuses, never every
    # catalog label (a node itself can be named '光滑组' or '通过').
    if status and status.group(2) in _BUSINESS_STATES and status.group(3).strip() in _BUSINESS_STATES:
        # Both fields look like states, so this untyped text is ambiguous.
        # Preserve it instead of guessing which one is a user's node name.
        return _retain_unknown(original, original)
    if status and status.group(2) in _BUSINESS_STATES:
        return status.group(1) + "[" + CATALOG[status.group(2)] + "]" + status.group(3)
    node_row = re.match(r"^(\s*\[.*\])(\s+)(.+)$", original, re.DOTALL)
    if node_row:
        return node_row.group(1) + node_row.group(2) + translate_english(node_row.group(3))
    for pattern, target in _TEMPLATES:
        matched = pattern.match(original)
        if matched:
            fields = matched.groupdict()
            values = [fields["f" + str(index)] for index in range(len(fields))]
            return target.format(*values)
    # Free paths are data, including Chinese directory/file components. Never
    # run prefix substitution over them. Full typed messages were handled above.
    if re.match(r"^\s*(?:[A-Za-z]:[\\/]|\\\\|/)", original):
        return original
    if "\n" in original:
        return "\n".join(translate_english(line) for line in original.split("\n"))
    # A known prefix can be localized; its untyped remainder stays verbatim.
    # Full-message templates above are the only place interpolated names,
    # paths, counts and error details are separated from fixed wording.
    for source, target in _REPORT_PREFIXES:
        if original.startswith(source):
            return _retain_unknown(target + original[len(source):], original)
    return _retain_unknown(original, original)


_F2M_IMPORT_COMPLETE = True
