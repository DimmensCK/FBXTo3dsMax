# FBXTo3dsMax project memory

## Current source distribution

- Author: Dimmens. License: MIT. Current product version: 1.4.24; current results are recorded in docs/TESTING.md. Historical 1.3.24 acceptance remains separate.
- Historical version baseline: 1.2.16; bug fixes add 0.0.1, features add 0.1.0.
- The 2026-10-08 source release increments 1.3.23 to 1.3.24 for the self-check dependency fix: private/employer-owned fixture files are replaced by original procedural generation. The mature two-mode business workflow remains unchanged.
- Runtime source/resources are under lowercase `contents/`; user guides are under `docs/zh/` and `docs/en/`, maintenance records under `docs/development/`. Root retains README, LICENSE, package metadata and install/uninstall entries. The optional PowerShell installer is `tools/Install_FBXTo3dsMax.ps1`. It ships no FBX, MAX, or BLEND assets.
- Version 1.4.24 adds Chinese/English UI and user-report switching, language persistence, the directory cleanup and complete English guides. The two-mode data authority and transaction contracts remain the maintenance baseline; current acceptance and its limits are recorded in docs/TESTING.md.
- Historical encrypted releases, native build toolchains, private user models, retired experiments, logs, and original long-form evidence are held in the owner's separate recoverable backup. They are not current build inputs or public deliverables.
- GitHub repository: https://github.com/DimmensCK/FBXTo3dsMax; primary branch: main. Acceptance and limits are in [TESTING](../TESTING.md); download and maintenance instructions are in the [GitHub guide](../GITHUB_发布指南.md). Public documents describe product scope; local publication receipts remain outside Git.
- Tutorial screenshots authorized by the owner may be distributed after privacy review. This does not authorize distributing underlying private/employer model files. Original corporate PDF exports, internal links and personal/path information are excluded.

## Compatibility and proof boundary

- Current and historical tested environment: Windows 11 x64, 3ds Max 2023.3.10, bundled Python 3.9.7. Version-specific results are separate in docs/TESTING.md.
- Source PackageContents.xml declares SeriesMin=2023 / SeriesMax=2026. Max 2024–2026 are unverified; declared routing is not compatibility proof.
- 2026-10-09, version 1.3.24 only: 231/231 pure tests; source and installed-copy Max Batch self-checks both 6/6. Standard source fresh/repeat installation passed independent source-origin SHA readback for all historical 27 targets; ordinary AutoLoader cold start and programmatic toolbar/UI click passed.
- The isolated source installation lifecycle passed one post-activation failure injection: complete byte/existence restoration of the old package, managed files and legacy startup scripts, failed new-package preservation, lock reopen and normal-source reinstall. This is one fault point, not all installer failures.
- Standard recoverable uninstall archived every package/managed file with matching SHA and cleaned owned runtime state. Archive restoration was not exercised; retaining and hashing an archive does not prove its future restoration.
- These host checks require natural process exit 0, zero selected native severe errors and unchanged production source hashes. UI evidence is programmatic QToolButton.click, not physical mouse input. Original local evidence and private tools remain outside Git.
- Fixtures are small original procedural topology/two-bone Skin data. They do not establish complex-asset or large-model performance coverage or absence of unknown defects.
- Python compilation and static contracts do not prove live Max correctness. Run pure algorithm tests and real Max regressions; installation changes require isolated install/reinstall/rollback/cold-start qualification. First formal user execution is on an isolated scene or a copy.

- 2026-10-09, version 1.4.24: 298 pure regressions and the 32-target static check passed. Fresh/repeat standard installation, ordinary AutoLoader cold start and independent origin-hash readback passed. Source Chinese, installed Chinese and installed English self-checks each passed 6/6.
- Current UI evidence comprises six switches/new-module preference reads without F2M_LANGUAGE, two reopens in the same Max process and all 72 original images viewed separately by two AI actors on the actual host/font/DPI. It is not physical-mouse, human-usability, mathematical-font or new-Max-process preference cold-start proof.
- The unmodified public PowerShell installer passed startup guard, non-installing profile qualification and actual silent installation; qualified runtime/post-exit and final-installation INI bytes matched exactly. It proves the native silent message and result/readback, not an observed/clicked visible dialog. No whole normal-user preference before/after witness is implied.
- One postactivation failure restored the old package/managed/legacy state, preserved the failed package, released its lock and allowed normal retry. Uninstall archives matched the original bytes; restoration from those archives was not exercised. The historical 27-target to current 32-target upgrade was not tested.
- English known labels/catalog and final outward states are translated. Stable JSON check names/summary and prior mixed/unknown technical diagnostics retain their original text; do not describe reports as fully English.
- Text checkout uses LF with automatic binary detection. Publication must independently read back its remote tree, ZIP and a fresh clone; these future checks are not preclaimed acceptance results.

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
- The persistent `语言 / Language` selector accepts `zh-CN`/`en`, defaults to Chinese and updates the open UI in place without losing mode/file/options/check state. Store user selection atomically in LOCALAPPDATA/FBXTo3dsMax/language.txt. F2M_LANGUAGE is a test/child initial override; explicit user choice takes precedence in the process.
- Maintain one persistent localized toolbar button, a cancellable timer lifecycle, and shutdown guards. Keep Components Description exactly `post-start-up scripts parts`.
- Install/uninstall share an exclusive package lock. Keep staging, SHA-256 validation, ownership checks, backup, complete-package switch, readback, and rollback. Archive previous installation and legacy AutoLoader; never silently delete them.
- Clear and verify all three MAXScript helper globals during runtime cleanup. Uninstall rollback must archive regenerated templates before restoring exact pre-uninstall bytes and hashes.
- Current source installation uses exactly 32 safe unique targets (the historical 27 plus two language modules and three English guides); installed hash-manifest targets must equal the fixed manifest set. Current acceptance includes independent installed source-origin readback; count alone is not runtime proof.
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
