# 回归测试与验证边界

**1.4.24 本轮本地验证（2026-10-09）**：298 项纯回归、32 项静态安装资源检查，以及下表所列真实宿主流程通过。实测环境为 **Windows 11 x64、3ds Max 2023.3.10、内置 Python 3.9.7**。历史 1.3.24 结果在末节单独保留。

**1.4.24 local validation, 2026-10-09:** 298 pure regressions, the 32-target static check and the real-host workflows below passed on **Windows 11 x64 / 3ds Max 2023.3.10 / bundled Python 3.9.7**. The 1.3.24 results remain separate.

[中文使用教程](zh/FBXTo3dsMax_详细说明书.md) · [English user guide](en/USER_GUIDE.md)

## 本轮结果 / Current results

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
python -B -m unittest discover -s tests -v
```

静态工具只读文件并输出到 stdout，支持 `--json` 与 `--root`。纯测试使用临时/原创数据，不依赖私有模型。仓库不含 FBX、MAX 或 BLEND；拓扑由 `f2m_test_fixtures.py` 生成，Skin 在自检中程序生成并导出。纯回归或 Python 编译不能替代 Max 运行。

Run these commands at the repository root with a deliberately selected Python 3.9+ interpreter or Max's bundled Python. Static checks are read-only; pure tests use temporary/original data. Neither compilation nor pure tests establish real Max correctness.

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

下表仅针对源码版本 **1.3.24**，不是当前 1.4.24 的验收结果。实际宿主为 **Windows 11 x64、3ds Max 2023.3.10 / 内置 Python 3.9.7**。安装生命周期使用隔离配置与独立进程；业务数据为运行时原创生成的小型拓扑和两骨骼 Skin 场景，未使用私有或前雇主模型。

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
