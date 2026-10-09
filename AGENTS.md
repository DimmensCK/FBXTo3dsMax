# FBXTo3dsMax development rules

Before editing, read:

- `docs/development/PROJECT_MEMORY.md`
- `docs/development/CHANGELOG_中文.md`
- `docs/zh/README_中文.md`
- `docs/zh/INSTALL_中文.md`

## Product and host

- The sibling `Blender To 3dsMax` directory is read-only historical source. Never edit, install from, rename or clean it.
- Keep the mature two-mode workflow unless a verified defect requires change.
- Original version baseline is `1.2.16`: bug fixes add `0.0.1`, new features add `0.1.0`. Current target `1.4.26` requires fresh qualification; historical `1.3.24` or `1.4.24` results do not qualify it.
- Runtime source/resources live under lowercase `contents/`. Keep root user entry points concise; PowerShell installation is `tools/Install_FBXTo3dsMax.ps1`.
- Synchronize versions in both Python engines, UI, language modules, `contents/VERSION.txt`, `contents/FBXTo3dsMax.version`, package metadata, installer manifest and changelog.
- Load runtime modules by absolute path and verify `module.__file__`, version, completion state and entry point.
- Preserve selection, node names, FBX importer global settings, temporary cleanup and failure rollback.
- Use pure algorithm tests and real 3ds Max Batch for core changes. Compilation alone is not proof of a core fix. First formal execution uses an isolated scene or a copy.
- XML routing declares Max 2023–2026; only Max 2023.3.10 has historical real-host acceptance. Do not infer compatibility with other versions.

## Installation and language

- Keep install/uninstall idempotent and transactional: exclusive lock, staging, SHA-256, ownership, backup, complete-package switch, readback and rollback.
- Do not silently delete previous installations or legacy AutoLoader scripts; archive and record their locations.
- Current source manifest has 32 safe unique targets. Installed hash-manifest targets must equal that set. Historical 27-target results apply only to version 1.3.24.
- Installed guides are flat in `contents/`: Chinese names plus `README_EN.md`, `INSTALL_EN.md`, `USER_GUIDE_EN.md`. Resolve installed files by absolute package path.
- Compact `Language` buttons select 中文/EN in place, retaining mode, file, options and check state. Keep exactly one language selected, including after clicking the active language. Persist only `zh-CN`/`en` atomically under local user data. Keep original technical diagnostics when translation would lose information.
- Run isolated fresh/repeat install, cold start, installed self-check, relevant failure rollback and recoverable uninstall for layout/installer changes. Verify both languages and persistence for language changes. Distinguish archived-byte verification from an exercised archive restoration.

## Public repository

- Never distribute private/employer FBX/MAX/BLEND model files. Generate original self-check geometry/data at runtime under local user data or temporary storage.
- Authorized tutorial screenshots/videos may be included after privacy/provenance review; this does not authorize distributing their underlying models. Exclude original internal PDF exports, internal links, personal paths, employee/account details and secrets.
- Keep historical encrypted builds, toolchains, downloaded runtimes, installation copies, logs and evidence outside Git.
- Use `tools/check_repository.py` and `tools/run_selfcheck.ps1` as public validation entry points. Reports belong under `%LOCALAPPDATA%\FBXTo3dsMax`, not beside source or installed code.
- Keep MIT and Dimmens attribution. A self-check is a regression suite, not proof that unknown bugs do not exist. Report exactly tested versions, fixtures and limits.
