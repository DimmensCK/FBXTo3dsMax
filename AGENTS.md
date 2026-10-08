# FBXTo3dsMax development rules

Read `PROJECT_MEMORY.md`, `CHANGELOG_中文.md`, `README_中文.md`, and
`INSTALL_中文.md` before changing this project.

- The sibling `Blender To 3dsMax` directory is the read-only historical source. Never
  edit, install from, rename, or clean that directory.
- Keep the mature two-mode workflow unless a verified defect requires change.
- Version baseline is the original plug-in's `1.2.16`. Bug-fix releases add
  `0.0.1`; releases with a new feature add `0.1.0`.
- Synchronize the version in both Python engines, UI, `VERSION.txt`, package
  metadata, installer manifest, and changelog.
- Load runtime Python modules by absolute path and verify `module.__file__`.
- Preserve scene selection, node names, FBX importer global settings, temporary
  node cleanup, and failure rollback.
- Never claim a core fix from ordinary Python compilation alone. Run pure
  algorithm tests and real 3ds Max Batch tests.
- Run the first formal execution on an isolated/test scene or a copy.
- Installer changes must remain idempotent and transactional: staging,
  SHA-256 validation, backup, atomic switch, readback, and rollback.
- Do not silently delete the previous installation or legacy AutoLoader;
  archive it and record the location.
- Reports belong under `%LOCALAPPDATA%\FBXTo3dsMax`, not beside installed code.
- A self-check is a regression suite, not proof that no unknown bug exists.

## Public source repository

- Keep this repository free of proprietary assets, historical binaries, logs,
  downloaded interpreters, and machine-specific paths.
- Generate test geometry and FBX data at runtime under the user's local
  application-data or temporary directory. Never copy private models here.
- Use `tools/check_repository.py` and `tools/run_selfcheck.ps1` as the public
  validation entry points; store detailed results outside the repository.
- Keep the MIT license and Dimmens attribution with redistributed source.
