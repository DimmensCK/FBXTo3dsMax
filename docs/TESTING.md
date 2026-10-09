# 回归测试与验证边界

## 1.4.25 当前结果 / Current results

**实测环境：Windows 11 x64、3ds Max 2023.3.10、内置 Python 3.9.7。** 下表记录本版已完成的实跑结果及明确例外；独立复核与发布读回分开记录。历史1.4.24和1.3.24结果保持独立，不代替本版验收。

**Tested environment: Windows 11 x64, 3ds Max 2023.3.10 and bundled Python 3.9.7.** The table records completed executions and explicit exceptions; independent review and publication readback are separate. Historical results do not qualify this version.

| 检查 / Check | 当前结果 / Current result | 实际范围 / Scope |
|---|---|---|
| 纯 Python / Pure Python | **305/305** | 算法、解析、映射、语言事务与源码契约 / Algorithms, parsing, mapping, language transactions and source contracts |
| 静态检查 / Static check | **32项通过 / 32 targets passed** | 固定安装资源、必要目标、版本及公开内容检查 / Fixed installation resources, required targets, versions and public-content checks |
| 全新与重复安装 / Fresh and repeat install | **通过 / Passed** | 标准源码安装器与同版本重复安装、32项按来源读回 / Standard source installer, same-version repeat and 32-target origin readback |
| 隔离配置冷启动 / Isolated-profile cold start | **通过 / Passed** | 自动加载、正式工具栏及原公开UI验证器；新运行通过不解释旧失败 / Automatic loading, installed toolbar and the original public UI verifier; a later success does not explain an earlier failure |
| 中文源码自检 / Chinese source self-check | **6/6，自然退出0 / 6/6, natural exit 0** | 独立隔离配置下全新安装、冷启动后，从源码contents绝对入口执行原创小样本 / Original small fixtures through the absolute source contents entry after a separate isolated fresh install and cold start |
| 中文安装副本自检 / Chinese installed self-check | **6/6，自然退出0 / 6/6, natural exit 0** | 实际安装副本、32项清单与六类业务回归 / Actual installed copy,32-target manifest and six business regression categories |
| 双语界面 / Bilingual UI | **72图已双审 / 72 images reviewed twice** | 6次切换、模式一已有检查缓存/原生语言值变化、模式二正常空缓存、2次同进程重开；两个AI分别逐张查看72原图 / Six switches, a populated Mode 1 check cache and native locale changes, normally empty Mode 2 cache, two same-process reopens; each AI actor viewed all 72 originals |
| 英文安装副本自检 / English installed self-check | **6/6，自然退出0 / 6/6, natural exit 0** | 实际安装副本；英文已知标题与六类显示名称，原技术诊断及JSON协议保留 / Actual installed copy; English known headings and six display names, with original diagnostics and stable JSON retained |
| PowerShell安装入口 / PowerShell installer | **功能有限接受 / Functional scope accepted** | 原样公开入口；启动保护与非安装配置阶段自然退出0，实际静默安装及32项读回完成；最终INI变化另行有限复核，原失败收据保留 / Unmodified public entry; startup guard and non-installing profile phase exited naturally 0, actual silent installation and 32-target readback completed; final INI changes received a bounded separate review, with the original failed receipt retained |
| 激活后失败回滚 / Postactivation rollback | **通过 / Passed** | 单处真实激活后故障；旧包、受管及遗留状态完整恢复，失败新包32项资源保留，锁可重新独占并标准重装 / One actual postactivation fault; old package, managed and legacy state restored, all32 failed-package resources retained, exclusive lock reopened and normal retry completed |
| 可恢复卸载 / Recoverable uninstall | **通过 / Passed** | 33个包内文件与3个受管文件归档逐字节哈希完整，运行状态清理；未从归档复装 / Matching byte hashes for33 package and3 managed files, with runtime cleanup; archive restoration not exercised |

**PowerShell的限制：** 本次静默安装完成，原生静默消息、安装结果、32项来源与工具栏检查用于功能判断；没有看到或按过可见结果弹窗。安装退出后的INI与先前合格退出快照不完全相等：`Maximized`由1变0，并出现`Size=800 600`窗口布局变化。完整差异经本次有限复核接受；原最终收据仍为失败、要求独立INI复核，**不是三个原始收据全部通过，也不是配置全程字节不变**。这不允许忽略其他安装失败或任意配置变更。

**PowerShell limit:** The actual silent installation, native silent message,32-source readback and toolbar checks support the functional result; no visible result dialog was observed or clicked. The final INI differed from the previously qualified post-exit snapshot: `Maximized` changed from 1 to 0 and a `Size=800 600` window-layout entry appeared. The complete difference received a bounded review for this run. The original final receipt remains failed and requests independent INI review: **this is not three passing original receipts or byte-invariant configuration throughout**, and it does not authorize ignoring other failures or arbitrary changes.

**冷启动的限制：** 早先一次独立运行出现按钮命中遮挡断言失败，原因尚未确定。新诊断运行没有再出现该异常；后来通过不能倒推旧运行当时命中了什么，也不能宣称已定位或修复其原因。

**Cold-start limit:** An earlier isolated run failed the button-hit occlusion assertion; its cause remains unknown. The new diagnostic run did not reproduce it. A later pass neither reconstructs the original hit nor establishes a causal fix.

**源码与文档边界：** 本轮宿主流程绑定同一组32项安装资源。主页、两张真实UI图、本页和项目记忆属于清单之外的文档更新，不改变这些安装资源；更新后的整仓库快照没有被当作原宿主源码快照重新执行全部步骤。完整仓库、下载包及新clone的逐字节读回属于后续发布检查，未在此提前声明通过。

**Source/document boundary:** The host workflows bind the same 32 installation resources. The homepage, two actual UI images, this page and project memory are documentation updates outside that set. They do not change the installation resources, but the complete updated repository snapshot has not been rerun as the original host-tested source snapshot. Remote-tree, archive and fresh-clone byte checks are separate publication checks, not preclaimed results.

所有安装与宿主验收均使用隔离测试配置和自有进程，不能推断已给正常用户配置安装新版。完成项目应有自然退出0、选定原生日志严重错误0、原始日志及后续完整前缀/追加字节/进程身份时间窗、源码与安装来源不变等证据；仅JSON成功不够。

Installation/host acceptance uses isolated test profiles and owned processes; it does not mean the new version was installed into the user's normal profile. Completed checks require natural exit 0, zero selected native severe errors, raw-log evidence with full-prefix/delta/process-time validation where applicable, and unchanged verified source/installation origins. A successful JSON alone is insufficient.

界面检查只覆盖实际宿主字体/DPI和所审原图；属于程序操作与两个AI的逐张审阅，**不是物理鼠标、真人可用性或数学字体证明**。语言偏好验证包括文件保存、6次无环境语言覆盖的新模块读回及2次同一个Max进程重开，**没有验证另一个Max进程的语言偏好冷启动恢复**。已知英文标签与状态不表示原技术诊断全文英语。

UI checks cover the actual host font/DPI and reviewed images through programmatic interaction and two AI image reviews, **not physical-mouse, human-usability or mathematical-font proof**. Preference checks include file saving, six new-module reads without a language override and two reopens in the same Max process, **not preference restoration after starting another Max process**. English labels/states do not imply fully English technical diagnostics.

包描述声明Max 2023–2026，**2024–2026尚未实测**。小型原创拓扑与两骨骼Skin不覆盖复杂生产资产、大模型性能或所有未知故障。单一故障回滚不代表全部失败点；卸载归档逐字节可读不等于已从归档复装。历史27项到32项的跨版本升级未单独验证。

The package declares Max 2023–2026; **2024–2026 remain untested**. Small original topology/two-bone Skin fixtures do not establish complex-asset, large-model performance or unknown-defect coverage. One rollback fault is not every failure point, and byte-readable uninstall archives are not an exercised restoration. The historical 27-target to 32-target upgrade was not tested separately.

## 1.4.24 历史结果 / Historical results

**1.4.24 本轮本地验证（2026-10-09）**：298 项纯回归、32 项静态安装资源检查，以及下表所列真实宿主流程通过。实测环境为 **Windows 11 x64、3ds Max 2023.3.10、内置 Python 3.9.7**。历史 1.3.24 结果在末节单独保留。

**1.4.24 local validation, 2026-10-09:** 298 pure regressions, the 32-target static check and the real-host workflows below passed on **Windows 11 x64 / 3ds Max 2023.3.10 / bundled Python 3.9.7**. The 1.3.24 results remain separate.

[中文使用教程](zh/FBXTo3dsMax_详细说明书.md) · [English user guide](en/USER_GUIDE.md)

## 1.4.24 结果 / 1.4.24 results

| 检查 / Check | 结果 / Result | 实际范围 / Scope |
|---|---|---|
| 纯 Python / Pure Python | **298/298** | 算法、解析、映射、无效输入、语言与源码契约 / Algorithms, parsing, mapping, invalid inputs, language and source contracts |
| 静态检查 / Static check | **32 项通过 / 32 targets passed** | 资源、必要目标、版本与公开内容线索 / Resources, required targets, versions and publication checks |
| 全新与重复安装 / Fresh and repeat install | **通过 / Passed** | 标准源码安装器、旧 Helper 清理、32 项按来源独立哈希读回 / Standard source installer, stale-helper cleanup and independent origin-hash readback |
| 普通冷启动 / Ordinary cold start | **通过 / Passed** | AutoLoader 自动加载、唯一工具栏按钮及正式窗口；程序调用真实点击路径 / Automatic loading, unique toolbar button and actual UI via programmatic click |
| 中文源码自检 / Chinese source self-check | **6/6** | 独立源码入口、原创生成样本 / Absolute source entry and original generated fixtures |
| 中文安装副本自检 / Chinese installed self-check | **6/6** | 实际安装来源、32 项清单及六类业务回归 / Actual installed source, manifest and six regression categories |
| 双语界面 / Bilingual UI | **通过 / Passed** | 6 次语言切换与无环境覆盖的新模块偏好读回、2 次同进程重开；9 个视图共72原图由两个 AI 审阅者分别查看 / Six switches and preference reads, two same-process reopens; both AI reviewers inspected all 72 images |
| 英文安装副本自检 / English installed self-check | **6/6** | 英文标题与六类显示名称；稳定 JSON 名称/摘要及原技术诊断保留 / English heading and six display labels; stable JSON names/summary and original diagnostics retained |
| PowerShell 安装入口 / PowerShell installer | **通过 / Passed** | 原样公开入口；启动保护→非安装配置资格→实际安装，均自然退出0；合格运行、退出与安装退出 INI 全字节一致 / Unmodified public entry, three qualified phases and exact INI bytes |
| 激活后失败回滚 / Postactivation rollback | **通过 / Passed** | 单处故障后旧包、受管文件、遗留启动状态恢复；新失败包保留，锁可重开并正常重装 / One injected fault, exact restoration, retained failed package, lock reopen and normal retry |
| 可恢复卸载 / Recoverable uninstall | **通过 / Passed** | 完整包与受管文件归档哈希相同、运行状态清理；未从归档重新安装 / Matching archive hashes and runtime cleanup; archive restoration not exercised |

以上流程使用独立配置与自有进程，要求自然退出 **0**、所查原生严重错误 **0**、源码不变、实际来源与前序证据相符。首次启动保存完整原始日志；后续同配置启动验证完整非空前缀、追加字节和进程身份/时间窗。绿色 JSON、强制结束或旧报告不替代这些门。

The isolated acceptance processes required natural exit **0**, zero selected native severe errors, unchanged source and verified origins. The first start preserved its complete raw log; later starts verified the nonempty full prefix, appended bytes and process identity/time window. A green JSON file alone is insufficient.

**证明上限：** XML 声明 Max 2023–2026，**2024–2026 未验证**；旧27项版本升级到32项的流程也未单独验证。小型原创拓扑和两骨骼 Skin 样本不覆盖复杂资产、大模型压力或全部未知故障。单处回滚不代表所有失败点，归档逐字节可读不等于完成恢复演练。

**Limits:** Max 2024–2026 and the historical 27-target to 32-target upgrade were not tested. Small original topology/two-bone Skin fixtures do not establish complex-asset, performance or unknown-defect coverage. One rollback fault is not every failure point; a verified archive is not an exercised restoration.

界面证据针对实际宿主字体/DPI与所审原图，是程序点击和两个 AI 审阅者的结果，**不是物理鼠标、真人可用性或数学字体证明**。偏好验证是无 `F2M_LANGUAGE` 覆盖的6次新模块读回、文件保存及2次同一 Max 进程重开，**没有验证另一个 Max 进程的语言冷启动恢复**。英文仅已知显示标签/状态翻译，先前混合摘要及未知技术原文可保留，不能称诊断全文英语。静默 PS 安装验证真实原生英文消息、结果数据与安装读回，**没有看到或按过可见结果弹窗**。

UI evidence is bounded to the actual host font/DPI and images reviewed by two AI actors, not physical mouse input, human usability or mathematical font proof. Preference checks used six new-module reads without a language override and two reopens in the same Max process, not a new-process preference cold start. English labels do not imply fully translated technical diagnostics. The silent installer proof does not claim a visible dialog was observed or clicked.

## 1. 静态与纯回归 / Static and pure checks

在工程根目录，用明确选定的 Python 3.9+ 或目标 Max 内置 Python 执行：

```powershell
python -B .\tools\check_repository.py
$env:PYTHONDONTWRITEBYTECODE = '1'
$testLanguageBefore = $env:F2M_LANGUAGE
try {
    $env:F2M_LANGUAGE = 'zh-CN'
    python -B -m unittest discover -s tests -v
} finally {
    $env:F2M_LANGUAGE = $testLanguageBefore
}
```

静态工具只读文件并输出到 stdout，支持 `--json` 与 `--root`。纯测试使用临时/原创数据，不依赖私有模型。仓库不含 FBX、MAX 或 BLEND；拓扑由 `f2m_test_fixtures.py` 生成，Skin 在自检中程序生成并导出。纯回归或 Python 编译不能替代 Max 运行。

部分回归固定断言中文消息。上例只为测试临时指定 `zh-CN`，随后恢复环境变量；不修改用户语言偏好文件。未指定测试语言时，已有英文偏好可能导致这些中文消息断言失败。

Run these commands at the repository root with a deliberately selected Python 3.9+ interpreter or Max's bundled Python. The temporary `zh-CN` environment selects the locale expected by Chinese-message assertions and is restored afterward; it does not write the user's preference file. Static checks are read-only; pure tests use temporary/original data. Neither compilation nor pure tests establish real Max correctness.

## 2. 独立 Max Batch 自检 / Standalone Max Batch self-check

保存并关闭所有 Max/Batch，用 PowerShell 7 执行：

```powershell
pwsh -NoLogo -NoProfile -File .\tools\run_selfcheck.ps1 -MaxBatchExecutable '<实际 Max 安装目录>\3dsmaxbatch.exe' -TimeoutSeconds 900
```

替换为存在的绝对路径。入口拒绝已有 Max/Batch，不关闭用户进程，不安装或卸载插件，只运行当前源码自检。输出在 `%LOCALAPPDATA%\FBXTo3dsMax\Validation` 的唯一目录，包含结果、进度、监听器、stdout/stderr、日志和 `validation.json`。

**这个公开入口继承正常 Max 用户配置**；隔离的是进程与业务场景，Max 自身仍可能写用户配置或共享日志。它不提供本轮隔离安装验收的12项目录证明，也不证明正常用户配置完全不受影响。本轮隔离安装验收没有使用该正常配置入口。

Replace the placeholder with the existing absolute executable path. The launcher refuses existing Max/Batch processes and does not install/uninstall the plugin. **It inherits normal Max user configuration:** Max may write user settings or shared logs. Process/scene isolation is not full configuration isolation or the private acceptance's 12-directory proof. That normal-profile entry was not used for this isolated installation acceptance.

六类自检为加载来源/版本、光滑算法、过程网格与栈、法线空间/保护/回滚、合成 FBX 同拓扑、合成 FBX Skin 替换。成功要求全部6类、自然退出0、专用日志严重错误0和源码不变。安装副本自检另验证安装 manifest，报告在 `%LOCALAPPDATA%\FBXTo3dsMax\SelfCheck`。

The six categories cover loading/version, smoothing algorithms, procedural meshes/stacks, normal-space safety/rollback, matching-topology FBX and Skin replacement. Installed self-checks additionally verify their manifest. Private asset experiments are not runnable public fixture coverage.

## 3. 使用与发布检查 / User and release checks

首次传递使用场景副本，核对视觉、动画和保存重载。模式一逐对象事务，后续失败不撤销先前成功对象；模式二保留旧网格时支持批次回滚，删除式提交不能承诺无损恢复。安装/layout/语言改动应重新验证安装、重复、来源、冷启动、报告、回滚和卸载，并说明是否实际恢复归档。

Use a scene copy first and inspect appearance, animation and save/reload. Mode 1 commits per object; Mode 2 batch rollback requires retaining the old meshes. Installation/layout/language changes require fresh acceptance, with archive restoration stated separately.

文本采用 LF，`.gitattributes` 保留自动二进制检测，便于 Windows clone 与已测源码保持相同字节。安装资源指纹按 target 排序，取 `bytes`、小写 `sha256`、`source`、`target`，序列化为键排序、紧凑 UTF-8 JSON（保留 Unicode，`ensure_ascii=False`；无 BOM/尾换行）再 SHA-256。发布时应独立读回远端树、ZIP 与新 clone；这里给出方法，**不把将来的发布检查预写为通过**。

Text uses LF with automatic binary detection. For the installation fingerprint, sort rows by target; use `bytes`, lowercase `sha256`, `source`, `target`; hash compact UTF-8 JSON with sorted keys, Unicode retained (`ensure_ascii=False`) and no BOM/trailing newline. Independently read back the remote tree, ZIP and a fresh clone during publication; these are release-check methods, not preclaimed results.

## 1.3.24 历史结果（2026-10-09）

下表仅针对源码版本 **1.3.24**，不替代后续版本的验收结果。实际宿主为 **Windows 11 x64、3ds Max 2023.3.10 / 内置 Python 3.9.7**。安装生命周期使用隔离配置与独立进程；业务数据为运行时原创生成的小型拓扑和两骨骼 Skin 场景，未使用私有或前雇主模型。

| 项目 | 本轮结果 | 证明范围 |
|---|---|---|
| 纯 Python 回归 | **231/231 通过** | 纯算法、解析、映射和源码契约 |
| 源码独立 Max Batch 自检 | **6/6 通过** | 当前源码与原创小样本的六类回归 |
| 全新安装与同版本重复安装 | **通过** | 标准源码安装器两轮事务、旧 Helper 清理、全部 27 个目标按源码来源 SHA-256 独立读回 |
| 新进程冷启动 | **通过** | 普通 AutoLoader 自动加载、唯一可见且可命中的中文按钮、程序点击后打开正式界面；没有手工加载 Bootstrap |
| 安装副本 Max Batch 自检 | **6/6 通过** | 执行实际安装副本，27 项清单与运行模块来源正确；使用相同原创生成回归 |
| 安装后激活失败回滚 | **通过** | 单处故障注入后旧包、受管文件与遗留启动脚本逐字节恢复；失败新包保留，锁可重开，正常源码重试安装成功 |
| 可恢复卸载 | **通过** | 标准卸载器归档完整包及受管文件，逐项 SHA-256 与卸载前一致；运行状态清理，恢复归档保留 |

这些宿主验收要求专用进程自然退出 **0**、所查原生严重错误 **0**、生产源码哈希不变；首次启动保留完整原始日志；后续同配置启动验证完整启动前前缀 SHA、追加字节与新进程身份/时间窗口，不能以旧报告、强制结束或仅 JSON 成功替代。

UI 验收调用真实 `QToolButton.click` 信号路径，并检查界面确实打开；它不是物理鼠标点击记录。回滚证明仅覆盖上述单处安装后激活失败，不能代表所有故障点。卸载证明完整可恢复归档的内容与哈希，**没有执行从该卸载归档重新恢复安装**。

XML 声明 Max 2023–2026，**Max 2024–2026 未验证**。小型生成样本不覆盖复杂生产资产、大模型压力或所有未知缺陷。首次使用仍应在场景副本上核对视觉、动画与保存重载。原始本机日志、运行身份、私有工具和资产不提交公开仓库。
