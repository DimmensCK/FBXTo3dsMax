# 回归测试与验证边界

## 1.4.26 当前修订 / Current revision

本次目标宿主为 **Windows 11 x64、3ds Max 2023.3.10、内置 Python 3.9.7**。最终验收日期：2026-10-10。新核心修订来源：`a9071872a1cfe3034af3c6b20c4e13ca7283fee3`；32 项安装资源指纹：`F2D7A897A4B9CC835BE14044810C6CCDCCA7400479654C52E2B20F5BEB6FD1D0`。

The target host is **Windows 11 x64, 3ds Max 2023.3.10 and bundled Python 3.9.7**. Qualification dates: 2026-10-10. The final source and 32-resource fingerprint are recorded above. This local qualification revision is not a public download commit; publication identities belong in the [Release](https://github.com/DimmensCK/FBXTo3dsMax/releases/tag/v1.4.26).

本表按当前源码的同一条新隔离链记录：全新/重复安装 → 冷启动 → 安装副本自检与扩展回归 → 真实安装失败回滚及正常重试 → 可恢复卸载。五步均已完成实际验收与独立复核；每一步只消费前一步的新成功收据，并核对自然退出、源码/安装来源、隔离、进程身份与完整原生日志。仅成功 JSON 不足以作为验收。

The five stages used one new isolated chain: fresh/repeat installation, cold start, installed checks and regressions, real installer-failure rollback with normal retry, and recoverable uninstall. All completed actual acceptance and independent review. Each stage consumed the preceding fresh success receipt and checked natural exit, verified origins, isolation, process identity and complete native logs. A successful JSON alone is insufficient.

| 检查 / Check | 当前修订结果 / Current result | 范围 / Scope |
|---|---|---|
| 纯 Python / Pure Python | **337/337，通过 / Passed**（9.190 s；源码回归 / source regressions） | 最终源码的算法、事务与契约回归；测试语言显式为 zh-CN / Final-source algorithm, transaction and contract regressions with explicit zh-CN locale |
| 静态清单 / Static manifest | **32/32，通过 / Passed**（1,315,661 B） | 最终源码的固定 32 个安装目标、版本和公开内容检查 / The fixed 32 installation targets, versions and public-content checks |
| 全新与重复安装 / Fresh and repeat install | **实际通过，自然退出 0 / Actual pass, natural exit 0** | 标准安装器、同版本重复安装及全部 32 项来源读回 / Standard installer, same-version repeat and all 32 origin checks |
| 隔离冷启动 / Isolated cold start | **实际通过，自然退出 0 / Actual pass, natural exit 0** | 自动加载、工具栏与界面 / Autoload, toolbar and UI |
| 中文安装副本六类自检 / Six Chinese installed checks | **6/6，通过，自然退出 0 / Passed, natural exit 0** | 实际新安装副本的原创小样本 / Original small fixtures through the actual new installed copy |
| 九个原生故障场景 / Nine native fault cases | **9/9，通过 / Passed** | 生产调用、场景读回、真实恢复与提交边界 / Production calls, scene readback, real recovery and commit boundaries |
| 独立世界坐标回归 / Independent world-coordinate cases | **16/16，通过 / Passed** | 16 例：Mesh/Poly × World/Local × 四组源/目标矩阵 / Sixteen cases across both base types, reference systems and four matrix pairs |
| 旧核心预期负例 / Expected old-core negative | **按预期拒绝 / Rejected as expected**（原生旧 MXS 点位 helper；世界点误差 2.554746 > 0.001） | 实际旧 MXS 生产点位 helper 被独立世界点读回拒绝；不是旧完整 Python/FBX 路径 / Actual legacy MXS point helper rejected by independent node-world reads; not the old complete Python/FBX path |
| 生成器故障清理 / Generator fault cleanup | **通过 / Passed** | 准备提交处故障、原异常保留、自有节点删除及无成功收据 / Prepared-commit failure, original error, owned-node cleanup and no success receipt |
| 原创雨棚 / Original canopy | **通过 / Passed**（91 顶点、144 三角形 / vertices and triangles） | 实际预检、形状/UV1 传递、节点/材质保留、原生前后渲染 / Actual preflight, shape/UV1 transfer, retained node/material and native before/after renders |
| 新来源双语范围 / Bilingual checks on the changed source | **本轮未重跑完整双语链 / Full bilingual chain not rerun** | 本轮仅 Fresh/Cold 程序界面检查；较早72图单独记录 / Fresh/Cold programmatic UI here; earlier 72 images separate |
| 新来源英文安装自检 / English installed checks on the changed source | **本轮未重跑附加英文自检 / Additional English suite not rerun** | 本轮六类安装自检为中文；较早英文6/6不迁移 / Current installed suite is Chinese; earlier English 6/6 not transferred |
| 新来源 PowerShell 入口 / PowerShell entry on the changed source | **本轮未重跑 PS 三阶段 / Three PowerShell phases not rerun** | 较早静默入口与 INI 结果仍为历史来源 / Earlier silent-entry and INI results retain historical scope |
| 安装失败回滚 / Installer rollback | **通过，自然退出 0 / Passed, natural exit 0** | 一个实际激活后故障点及完整旧状态读回 / One actual postactivation fault and previous-state readback |
| 可恢复卸载 / Recoverable uninstall | **通过，自然退出 0 / Passed, natural exit 0** | 归档数量与原始字节核对；33 个包文件及 3 个受管文件归档完整，未演练复装 / Archive count and original bytes; 33 package and 3 managed files archived exactly; restoration not exercised |
| 最终文档/图片覆盖检查 / Final documentation/media overlay | 与发行运输检查单独记录 / Recorded separately from host acceptance | 四文档、四 PNG 的内容与最终源码检查 / Content and source checks for four documents and four PNGs |
| GitHub 发布读回 / GitHub readback | 发布后单独记录 / Recorded after publication | 公开 commit/tree/tag、ZIP、全新 clone 与具体 CI 运行；不预写通过 / Public commit/tree/tag, ZIP, fresh clone and specific CI run, without preclaimed success |

### 当前来源记录 / Current source provenance

本地源码树为 `7e22a69821a1dbd0cf4ccee1f9dfd82ed5cbe3f8`，共 127 文件、3,609,063 B；宿主流程使用其中 121 文件的隔离副本，安装资源为 32 项、1,315,661 B。原始源码冻结 SHA-256 为 `2B85BCBA28665BBDF6CFAB48F98CF0D2710BB32FEC1CF9EF1F506ABD314AC719`。这些是本地来源记录，不是可访问的 GitHub 下载提交。

The local source tree contains 127 files (3,609,063 B); the isolated host copy contains 121 files and installs 32 resources (1,315,661 B). The source-freeze hash above binds these local records. It is separate from the future clean public commit and publication readback.

本页的当前 32 项指纹引用冻结的 `runtime32.canonical.json` 原始字节：UTF-8 无 BOM/末尾换行、紧凑 JSON 数组、冻结行序与 `source,target,sha256,length` 字段序，原始 Unicode、大写 SHA-256、整数长度。旧指纹仅作历史引用，不承诺采用同一序列化。该指纹与静态/纯回归都不代替原生功能验收。

The current fingerprint refers to the exact frozen canonical bytes with the declared field and row order; older fingerprints are historical references with no implied matching serialization. A fingerprint, static checks and pure regressions do not qualify native behavior.

### 本次修复与回归 / Repair and regression scope

当前源码去除模式一对求值快照点的重复变换，直接交给明确的世界坐标节点写入；目标逆矩阵仅用于基础对象局部读回，原点位预算和回滚保留。16 例保留原来的 8 例匹配矩阵检查，并增加单位缩放源/恒等目标与不同正负 TRS。预期点来自独立的节点世界坐标读取，不复用生产快照变换公式；保存源/目标局部点、矩阵、世界点和既定预算，便于独立重算。新安装副本已实际完成 16 例独立世界点回归，并由真实旧 MXS 点位 helper 负例检出已知重复变换错误。原生用例与整个安装副本运行的自然退出、日志和来源门已完成，并经独立复核采纳。

The source revision sends evaluated snapshot points directly to the explicit world-space node writer and keeps the receiver inverse only for base-local verification. Precision budgets and rollback stay intact. Sixteen cases retain the original eight matching-transform checks and add unit-scale/identity and distinct positive/negative TRS pairs. Expected points come from independent direct node-world reads. Raw base-local points, matrices, world points and budgets permit separate recomputation. The new installed copy completed all 16 independent world-coordinate cases and rejected the actual legacy MXS point helper for the known repeated-transform error. The parent installed run completed its natural-exit, log and origin checks and was independently reviewed and accepted.

这些坐标样本不带 Skin，不覆盖全部 FBX 通道；完整六类自检、九个故障场景和雨棚传递另行验收。旧核心负例验证预期能发现已知错误，不意味着修复后没有未知缺陷。生成器故障检查仅在自有空场景执行，真实触发准备收据提交失败并检查清理，不模拟核心、单位或原生 getter。

These coordinate fixtures are unskinned and do not cover every FBX channel. The six-category suite, nine fault cases and canopy transfer remain separate. Detecting the known old-core error does not establish absence of unknown bugs. The generator fault uses an owned empty scene and a real prepared-receipt collision without replacing the runtime, core, units or native getters.

原创练习修正逐行 FBX ASCII 区块、节点上的 UV 构建与最终面角读回，以及按 AnimHandle 查找自有节点的失败清理。独立 SDK 曾读回规范化 FBX 的完整数据；SDK 或纯测试均不代替 Max 导入、传递、渲染与生命周期验收。

The original exercise repairs multiline FBX ASCII blocks, node-level UV construction/final corner readback and AnimHandle-based owned cleanup. Standalone SDK readback of the normalized FBX is preparation evidence, not Max import, transfer, rendering or lifecycle qualification.

九个故障场景覆盖不同恢复与提交边界，不能统称“九次完整回滚”。T3 在点位/通道已提交后触发选择读回不一致，保留已提交数据并报告失败；S2 关闭备份后旧节点已删除，保留已验证的新节点并明确报告不可逆边界。它们验证正确的失败状态与保护行为，不要求伪造未发生的回滚。

The nine faults exercise different recovery and commit boundaries, not nine complete rollbacks. T3 fails selection readback after data commit and retains the committed data. In S2, deleting the old node with backup disabled is irreversible; the validated replacement remains protected and failure is reported explicitly.

安装生命周期另有一个实际激活后故障：Bootstrap 返回失败，旧包、受管与遗留状态按原始哈希恢复，32 项失败新资源保留，独占锁可重开并完成标准源码重试。随后卸载将 33 个包内文件和 3 个受管文件完整归档，活动安装已移除；本次没有执行归档复装。

A separate installer postactivation failure returned Bootstrap false, restored the previous package/managed/legacy state by exact hashes, preserved the 32 failed new resources, reopened the exclusive lock and completed normal source retry. Uninstall then archived 33 package and 3 managed files exactly and removed the live installation. Archive restoration was not exercised.

### 本轮语言与入口范围 / Language and entry-point scope

本次源码未改界面、语言模块或 PowerShell 安装入口，相关文件与较早来源已逐字节核对。本轮没有扩大重跑完整双语链、附加英文六类或 PS 三阶段。当前实证为新 Main 的 Fresh/Cold 程序界面检查，以及中文安装副本的六类、九故障和16组坐标回归；较早 f94 的72图、英文6/6和PS结果仍仅对应其历史来源。文件不变不等于整个旧32项资格迁移，也不证明物理鼠标、真人可用性或另一个 Max 进程的语言偏好冷恢复。

This source revision leaves the UI, language modules and PowerShell installer unchanged; the relevant files were compared byte for byte with the earlier source. The full bilingual chain, additional English six-category suite and three PowerShell phases were not rerun. Current evidence is the new Main Fresh/Cold programmatic UI checks and Chinese installed six-category, nine-fault and sixteen-coordinate runs. Earlier f94 images/English/PowerShell results retain their historical source scope. Unchanged files do not transfer qualification of the old complete 32-resource package or prove physical mouse use, human usability or preference cold restoration in another Max process.

### 较早 1.4.26 来源 / Earlier 1.4.26 source

下列结果使用本地较早来源 `f94fdb51a3f570bcba7dcf930a6b833c2958e84a`，绑定其当时的 32 项安装字节，**不作为修改后的核心/整个包验收**。它们不是新 Main 中回滚或卸载的前序。新核心改变了安装资源；不得再写新旧 32 项整体逐字节相同。

The following results belong to the earlier local source and its then-current 32 installation resources. **They do not qualify the changed core or complete new package** and are not predecessors for its Main rollback/uninstall chain.

| 历史检查 / Earlier check | 已完成结果 / Completed result | 证明范围 / Limit |
|---|---|---|
| 纯回归 / Pure regressions | 329/329 | 较早源码 / Earlier source |
| 中文源码自检 / Chinese source self-check | 6/6，自然退出 0 / Natural exit 0 | 较早源码的绝对入口与独立安装/冷启动 / Earlier absolute source entry and separate install/cold start |
| 双语界面 / Bilingual UI | 两个 AI 各逐张查看 72 原图 / Each AI viewed all 72 originals | 6 次切换、2 次同进程重开与当时字体/DPI；非物理鼠标或真人可用性 / Six switches, two same-process reopens and observed font/DPI, not physical mouse or human usability |
| 附加英文安装自检 / Additional English installed check | 6/6，自然退出 0 / Natural exit 0 | 独立附加链；已知英文标签，原 JSON/诊断保留 / Separate chain, known English labels with original JSON/diagnostics |
| 公开 PowerShell 入口 / Public PowerShell entry | 三阶段自然退出 0 / Three phases, natural exit 0 | 静默结果、32 项来源和最终 INI 逐字节一致；未看可见弹窗 / Silent result, 32 origins and exact final INI; no visible-dialog observation |

语言重开在同一 Max 进程中，不证明另一个进程的偏好冷启动。较早原图可作界面布局参考；新核心的业务、英文自检或安装范围必须据本表当前修订栏另记。原始失败记录保留，后续通过不改写它们，也不自动解释旧失败原因。

Same-process reopens do not prove preference restoration in another Max process. Earlier originals remain layout references; current-core business, English and installer scope must be stated separately. A later success neither rewrites earlier failures nor establishes their causes.

### 来源、覆盖与限制 / Origins, overlay and limits

本地验收修订号不随公开版本上传其本地历史，也不是可下载的 GitHub commit 链接。公开源码提交、标签、ZIP、全新克隆和 CI 的具体结果写入可编辑的 [Release](https://github.com/DimmensCK/FBXTo3dsMax/releases/tag/v1.4.26)，避免让 Git 文档引用尚不存在的自身提交。静态/纯 CI 不替代 Max 主机验证。

Local qualification history is not published as the public Git history. Public revision/tag/archive/clone and exact CI results belong in the editable [Release](https://github.com/DimmensCK/FBXTo3dsMax/releases/tag/v1.4.26). Static/pure CI does not qualify the Max host.

最终公开覆盖仅包含 `README.md`、`docs/TESTING.md`、`docs/assets/MEDIA.md`、`docs/development/PROJECT_MEMORY.md` 与四张原始 PNG，均在 32 项安装资源之外。更新日志已作为新源码中的安装资源单独验收，不能借最终覆盖更改。覆盖后重做源码/内容检查，不声称对文档覆盖后的整个仓库又执行了全部主机步骤。

The final overlay contains only four documents and four original PNGs outside the installation resources. The changelog is qualified separately with the changed source, not edited through this overlay. Repeat source/content checks without implying every host step was repeated on the final documentation overlay.

验收使用自有进程和隔离配置，继承许可环境；未对正常用户配置做全树字节比对。首次用户传递使用副本。包描述声明 Max 2023–2026，**2024–2026 尚未实测**；复杂资产、大模型性能、全部故障点与历史 27→32 项升级不在此覆盖中。归档哈希完整不等于实际复装。

Checks use owned processes and isolated profiles with inherited licensing, without a whole normal-user-profile byte comparison. Use a copy first. **Max 2024–2026 remain untested**. Complex assets, performance, every fault point and the historical 27→32 upgrade are outside coverage. Archive integrity is not exercised restoration.

## 1.4.25 历史结果 / Historical results

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
| 激活后失败回滚 / Postactivation rollback | **通过 / Passed** | 单处真实激活后故障；旧包、受管及遗留状态完整恢复，失败新包32项资源保留，锁可重新独占并标准重装 / One actual postactivation fault; old package, managed and legacy state restored, all 32 failed-package resources retained, exclusive lock reopened and normal retry completed |
| 可恢复卸载 / Recoverable uninstall | **通过 / Passed** | 33个包内文件与3个受管文件归档逐字节哈希完整，运行状态清理；未从归档复装 / Matching byte hashes for 33 package and 3 managed files, with runtime cleanup; archive restoration not exercised |

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

文本采用 LF，`.gitattributes` 保留自动二进制检测。发布读回以明确绑定原始 SHA-256 的最终文件清单为准，逐项比较安全相对路径、长度、SHA-256 与 Git blob 身份；32 项安装来源另外按 source/target/length/SHA-256 核对。历史指纹不能假定采用同一序列化。远端树、ZIP 和全新 clone 分别检查，**不把将来的结果预写为通过**。

Text uses LF with automatic binary detection. Bind the final file manifest by its raw SHA-256, then compare safe relative paths, lengths, SHA-256 and Git blob identities exactly. Check all 32 source/target/length/hash rows separately; do not assume historical fingerprints share a serialization. Remote tree, ZIP and fresh-clone checks remain separate and are not preclaimed success.

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
