# FBXTo3dsMax project memory

## Current source distribution

- Author: Dimmens. License: MIT. Current target version: 1.4.25; version-specific results are recorded in docs/TESTING.md. Historical 1.3.24 and 1.4.24 acceptance remains separate and does not qualify later source.
- Historical version baseline: 1.2.16; bug fixes add 0.0.1, features add 0.1.0.
- Version 1.4.25 repairs the existing language selector's layout: compact Language / 中文 / EN buttons occupy the mode heading's unused corner and remove the extra top row. Language preview, catalog/toolbar refresh and native locale readback now precede the atomic preference commit; recovery failures retain their diagnostic instead of claiming a consistent rollback. No filesystem cleanup follows a successful preference replace. The two-mode business workflow is preserved. Expanded bilingual task tutorials and authorized historical media explain the existing capabilities; marketing does not establish new compatibility or performance qualification.
- The 2026-10-08 source release increments 1.3.23 to 1.3.24 for the self-check dependency fix: private/employer-owned fixture files are replaced by original procedural generation. The mature two-mode business workflow remains unchanged.
- Runtime source/resources are under lowercase `contents/`; user guides are under `docs/zh/` and `docs/en/`, maintenance records under `docs/development/`. Root retains README, LICENSE, package metadata and install/uninstall entries. The optional PowerShell installer is `tools/Install_FBXTo3dsMax.ps1`. It ships no FBX, MAX, or BLEND assets.
- Version 1.4.24 adds Chinese/English UI and user-report switching, language persistence, the directory cleanup and complete English guides. The two-mode data authority and transaction contracts remain the maintenance baseline; current acceptance and its limits are recorded in docs/TESTING.md.
- Historical encrypted releases, native build toolchains, private user models, retired experiments, logs, and original long-form evidence are held in the owner's separate recoverable backup. They are not current build inputs or public deliverables.
- GitHub repository: https://github.com/DimmensCK/FBXTo3dsMax; primary branch: main. Acceptance and limits are in [TESTING](../TESTING.md); download and maintenance instructions are in the [GitHub guide](../GITHUB_发布指南.md). Public documents describe product scope; local publication receipts remain outside Git.
- Tutorial screenshots authorized by the owner may be distributed after privacy review. This does not authorize distributing underlying private/employer model files. Original corporate PDF exports, internal links and personal/path information are excluded.

## Compatibility and proof boundary

- Current 1.4.25 executions used Windows 11 x64, 3ds Max 2023.3.10 and bundled Python 3.9.7. See the current acceptance section and docs/TESTING.md for completed runs, scoped exceptions and limits. Historical versions remain separate.
- Source PackageContents.xml declares SeriesMin=2023 / SeriesMax=2026. Max 2024–2026 are unverified; declared routing is not compatibility proof.
- 2026-10-09, version 1.3.24 only: 231/231 pure tests; source and installed-copy Max Batch self-checks both 6/6. Standard source fresh/repeat installation passed independent source-origin SHA readback for all historical 27 targets; ordinary AutoLoader cold start and programmatic toolbar/UI click passed.
- The isolated source installation lifecycle passed one post-activation failure injection: complete byte/existence restoration of the old package, managed files and legacy startup scripts, failed new-package preservation, lock reopen and normal-source reinstall. This is one fault point, not all installer failures.
- Standard recoverable uninstall archived every package/managed file with matching SHA and cleaned owned runtime state. Archive restoration was not exercised; retaining and hashing an archive does not prove its future restoration.
- These host checks require natural process exit 0, zero selected native severe errors and unchanged production source hashes. UI evidence is programmatic QToolButton.click, not physical mouse input. Original local evidence and private tools remain outside Git.
- Fixtures are small original procedural topology/two-bone Skin data. They do not establish complex-asset or large-model performance coverage or absence of unknown defects.
- Python compilation and static contracts do not prove live Max correctness. Run pure algorithm tests and real Max regressions; installation changes require isolated install/reinstall/rollback/cold-start qualification. First formal user execution is on an isolated scene or a copy.

- 2026-10-09, version 1.4.24: 298 pure regressions and the 32-target static check passed. Fresh/repeat standard installation, ordinary AutoLoader cold start and independent origin-hash readback passed. Source Chinese, installed Chinese and installed English self-checks each passed 6/6.
- Historical 1.4.24 UI evidence comprises six switches/new-module preference reads without F2M_LANGUAGE, two reopens in the same Max process and all 72 original images viewed separately by two AI actors on the actual host/font/DPI. It is not physical-mouse, human-usability, mathematical-font or new-Max-process preference cold-start proof, and does not qualify the 1.4.25 buttons.
- The unmodified public PowerShell installer passed startup guard, non-installing profile qualification and actual silent installation; qualified runtime/post-exit and final-installation INI bytes matched exactly. It proves the native silent message and result/readback, not an observed/clicked visible dialog. No whole normal-user preference before/after witness is implied.
- One postactivation failure restored the old package/managed/legacy state, preserved the failed package, released its lock and allowed normal retry. Uninstall archives matched the original bytes; restoration from those archives was not exercised. The historical 27-target to current 32-target upgrade was not tested.
- English known labels/catalog and final outward states are translated. Stable JSON check names/summary and prior mixed/unknown technical diagnostics retain their original text; do not describe reports as fully English.
- Text checkout uses LF with automatic binary detection. Publication must independently read back its remote tree, ZIP and a fresh clone; these future checks are not preclaimed acceptance results.

## 1.4.25 current acceptance / 当前验收记录

2026-10-09: actual pure regressions 305/305 and the 32-target static check passed on the current source. Real-host work uses Windows 11 x64,3ds Max 2023.3.10 and bundled Python 3.9.7 in isolated profiles; it is not a normal-user installation. Earlier1.4.24/1.3.24 results remain historical.

2026-10-09：当前源码实际完成305/305纯回归及32项静态检查。真实宿主为隔离配置下的Windows 11 x64、Max 2023.3.10、内置Python 3.9.7，不等于在正常用户配置安装新版。旧版结果保持独立。

| Check / 检查 | Current record / 当前记录 |
|---|---|
| Fresh/repeat and isolated cold start / 全新、重复安装及隔离冷启动 | Passed with current32-resource origin checks / 当前32资源来源检查通过 |
| Chinese source and installed checks / 中文源码与安装自检 | Source and installed copies each 6/6, natural exit 0; separate source-profile fresh/cold and absolute source entry verified / 源码及安装副本各6/6自然退出0，源码另有独立全新安装/冷启动与绝对入口检查 |
| Bilingual UI / 双语界面 | Six switches with populated Mode 1 check state/native locale changes, normally empty Mode 2 cache, two same-process reopens; two AI actors each reviewed72 original images / 6次切换、模式一非空检查状态及原生语言值变化、模式二正常空缓存、2次同进程重开，两AI各审72原图 |
| English installed self-check / 英文安装自检 | 6/6, natural exit 0; known labels translated, stable JSON/original technical details retained / 6/6自然退出0，已知标签英文，协议与原诊断保留 |
| Public PowerShell installer / 公开PS安装入口 | Actual silent install and 32 readback functionally accepted with separately reviewed final window-layout INI difference; original final failure receipt unchanged / 实际静默安装及32读回有限接受，退出INI布局差异单独审阅，原失败收据未改 |
| Postactivation rollback and uninstall / 激活后回滚与卸载 | One actual postactivation fault restored old package/managed/legacy bytes, retained all 32 failed resources, reopened lock and completed normal retry; uninstall archived 33 package plus 3 managed files exactly, without restoration / 单处真实故障完整恢复旧状态并保留32项失败资源、重开锁及标准重试；卸载归档33包内文件+3受管文件字节完整，未复装 |

PowerShell startup/profile phases exited naturally 0. The final INI comparison did not pass unchanged: Maximized1→0 and Size800600 window-layout changes received a bounded independent review. Never summarize this as three passing canonical receipts or invariant configuration. The earlier cold-start widgetAt failure remains unexplained; non-reproduction in a new diagnostic run is not a causal repair.

PS启动/配置阶段自然退出0；最终INI并非全字节一致，本次窗口布局差异经有限独立复核，原失败保留。不可写成“三原始收据全通过”或“配置全程未变”。此前冷启动命中失败原因未定，新运行未复现不证明已修复旧原因。

The 32 installed resources stay byte-identical across the later homepage/UI-image/TESTING/project-memory documentation overlay; that complete repository overlay was not rerun as the original host source snapshot. Publication transport checks remain separate. UI evidence is host/font/DPI-specific programmatic interaction and AI image review, not physical mouse/human usability/math-font proof; two same-process reopens are not new-process preference cold starts. Max 2024–2026, complex assets, large-model performance, the27→32 upgrade and restoration from uninstall archives remain unverified. A single injected rollback fault does not cover all failures.

后续主页/实图/测试说明/项目记忆更新不改32安装资源，但整份文档覆盖后的仓库没有被当作原宿主源码快照重跑；发布传输检查另计。保留未测版本、复杂资产、性能、跨版本升级、归档复装及单故障覆盖限制。

## Product contract

- UI terminology/data direction: Max 源模型 <- FBX 目标模型.
- Keep the two-mode workflow. Mode 1 retains the selected node and transfers verified matching-topology channels. Same-winding cyclic corner rotations and face reorderings require explicit mappings; reverse winding, vertex-identity changes, edge-set changes, and ambiguous duplicate faces fail closed.
- Mode 1 uses per-object transactions, not whole-batch atomicity. Earlier successful objects are not automatically undone when a later object fails.
- Mode 2 keeps the imported FBX candidate as the final node, imports with smoothing groups off, and keeps FBX mesh/channels/material/custom normals/non-Skin data by default. The old Max material is an explicit, disabled-by-default compatibility option.
- Mode 2 copies Max source Skin with local data at the original FBX Skin stack index. Max supplies coherent scene-bone identities, Bone Bind/Stretch TM, envelopes, and semantic state; retain the candidate's adapted Mesh Bind established by addModifierWithLocalData. FBX supplies all per-vertex weights, Unnormalized/DQ, and global DQ.
- Mode 2 must validate every weight row and binding/presentation/world-appearance state. The world-point/bbox tolerance is max(0.001 cm, 0.000002 cm + coordinate_scale * 0.000002); non-finite inputs and material mismatches fail closed.
- Backup replacement supports reverse-order batch rollback. Multi-target deletion is blocked; single-target deletion has an irreversible boundary. Old node parenting, transform/animation controllers, constraints, and arbitrary modifiers are not cloned.
- Preserve names, selection, FBX importer settings, temporary cleanup, and failure rollback; any incomplete restoration is failure. Hold node handles across calls, release wrappers before deletion, and verify by handle after deletion. Name fallback must be unique.
- Park Modify current-object state in Create and verify detachment before changing importer settings or native import. Importer uses Set-then-Get plus nested finally restoration/readback; an explicit false import result is failure.

## Smoothing and normal authority

- Preserve unique valid native LayerElementSmoothing semantics. Without a native layer, direction/fan relationships are authoritative; raw normal IDs are diagnostic.
- SG-only keeps the double-import route and strictly validates Autodesk's candidate before using it. SG+normals uses a separate Max-bundled-Python strict resolver and one main-process import; validate module/input identities and bounded response data. No in-process fallback or extra imported-topology pre-read.
- The solver prioritizes connected soft regions, safely reuses bits only when required, and uses multi-bit DSATUR only when necessary. Validate every edge and vertex fan within 32 bits; reject invalid/unrepresentable input without approximation.
- Normals-only with receiver SG all zero performs full exact transfer. With any nonzero SG it preserves those masks and uses the actual receiver's final geometry/SG baseline. SG+normals always writes/reads FBX SG before using the same residual route.
- Semantic residuals are per-corner differences above 0.1 degrees. Write complete FBX target directions and only the necessary same-baseline-normal guard closure. Guards do not add custom-normal meaning.
- Retain one bottom F2M_顶点法线 Edit Normals even when residuals are empty, so old embedded normals cannot reappear. Do not collapse it. Re-read SG and every final face-corner direction immediately and after reevaluation.
- Never silently delete user Edit Normals/Weighted Normal. SG-only may remove only plug-in-owned stale normal modifiers and must verify their count is zero before writing.

## Runtime and installation

- Load runtime modules by absolute path and verify module.__file__, TOOL_VERSION, completion marker, and callable entry point before reuse. Evict exact half-imported objects after failure.
- Topology and Skin helpers have independent versioned globals; switch the compatibility alias instead of recompiling them on every mode change.
- The UI uses a -1/0/1 global bridge; python.Execute success is not business success. Use throwOnError:true clearUndoBuffer:false. Persist technical diagnostics under LOCALAPPDATA; display summaries follow the chosen UI language while original technical diagnostic text may remain unchanged.
- The compact `Language` buttons select `中文` / `EN` (`zh-CN` / `en`), default to Chinese and update the open UI in place without losing mode/file/options/check state. Clicking the active button must keep exactly one selection. Store user selection atomically in LOCALAPPDATA/FBXTo3dsMax/language.txt. F2M_LANGUAGE is a test/child initial override; explicit user choice takes precedence in the process.
- Maintain one persistent localized toolbar button, a cancellable timer lifecycle, and shutdown guards. Keep Components Description exactly `post-start-up scripts parts`.
- Install/uninstall share an exclusive package lock. Keep staging, SHA-256 validation, ownership checks, backup, complete-package switch, readback, and rollback. Archive previous installation and legacy AutoLoader; never silently delete them.
- Clear and verify all three MAXScript helper globals during runtime cleanup. Uninstall rollback must archive regenerated templates before restoring exact pre-uninstall bytes and hashes.
- Current source installation uses exactly 32 safe unique targets (the historical 27 plus two language modules and three English guides); installed hash-manifest targets must equal the fixed manifest set. The 1.4.25 executions completed readback of their own source bytes; see the current acceptance section and docs/TESTING.md. Historical 1.4.24 readback does not qualify later source. Count alone is not runtime proof.
- Installed guides are flat under contents: README_中文.md, INSTALL_中文.md, FBXTo3dsMax_详细说明书.md, CHANGELOG_中文.md, README_EN.md, INSTALL_EN.md and USER_GUIDE_EN.md. Load installed documents by their absolute package paths, not source-tree assumptions.
- Runtime reports belong under LOCALAPPDATA/FBXTo3dsMax. Installer logs/backups belong under APPDATA/Autodesk/FBXTo3dsMaxInstaller. Test output must not pollute source or installed code.
- f2m_test_fixtures.py generates original simple topology/UV/normal/native-SG data. f2m_selfcheck.py builds and exports the original two-bone Skin fixture in Max at runtime. Only these generated fixtures may be used by the public self-check; private/employer FBX/MAX/BLEND assets are excluded. Small generated regressions do not inherit historical large-asset or performance coverage.

## Maintenance checklist

1. Read root AGENTS.md, this file, docs/zh/README_中文.md, docs/zh/INSTALL_中文.md and docs/development/CHANGELOG_中文.md before edits.
2. Keep historical predecessor source read-only; do not install or clean it.
3. Synchronize release versions in both engines, UI, contents/VERSION.txt, contents/FBXTo3dsMax.version, package XML, installer metadata, language modules and changelog when product behavior changes.
4. Run `tools/check_repository.py`, pure tests, and real Max Batch self-check. See docs/TESTING.md for exact commands and limits.
5. For installation/layout/language changes, verify isolated fresh install, same-version repeat, stale-helper clearing, injected rollback, 32-target origin-hash readback, cold-start toolbar/UI, language persistence/reporting, uninstall/archive and natural process exits. State separately whether archive restoration was exercised.
6. Keep procedural test-data provenance and read-only inputs intact. Do not publish private asset names, personal machine paths, run tokens, PIDs, or raw local reports.
7. Record the exact tested scope and remaining limits. Do not convert author test results into universal compatibility claims.
