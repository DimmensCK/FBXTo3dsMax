# Installing FBXTo3dsMax 1.4.24

[中文安装说明](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/INSTALL_中文.md) · [Overview](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/README.md) · [User guide](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md)

This is the readable source edition. This page defines installation steps and proof requirements. Current results and the separate historical 1.3.24 installation scope are recorded in [testing](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md).

## Download and environment

Download the complete [repository](https://github.com/DimmensCK/FBXTo3dsMax) using **Code → Download ZIP**, then extract it. Keep root `Install_FBXTo3dsMax.ms`, `PackageContents.xml`, `LICENSE`, and the lowercase `contents/`, `docs/`, `tests/`, `tools/` directories together. Do not execute inside the ZIP or download the installer alone.

Historical acceptance used Windows 11 x64, Max 2023.3.10 and Python 3.9.7. Package routing declares Max 2023–2026; 2024–2026 have not been validated. The plug-in uses the Python shipped with Max; normal installation needs no separate interpreter or compiler.

The source distribution contains no FBX/MAX/BLEND model files. Self-check data is generated procedurally in the local user-data directory.

## Recommended installation

1. Save your current Max scene.
2. Drag root **`Install_FBXTo3dsMax.ms`** into the Max viewport.
3. Wait for the result dialog. On failure, retain the displayed log and stop before using the plug-in.
4. After success, click **FBX 转 MAX / FBX to MAX** on the top toolbar. The main toolbar is preferred; a docked fallback toolbar is used when necessary.
5. Select **English** in **语言 / Language**, then run **Run Self-check** and read its report.
6. Close and reopen Max, confirm the button remains available, and try your first transfer on a scene copy.

Installation does not automatically open the plug-in window. It is per-user and normally needs no administrator access. The installed package is normally:

```text
%APPDATA%\Autodesk\ApplicationPlugins\FBXTo3dsMax
```

After installation, Max runs the complete installed copy. The UI language updates without reopening the window and is saved in `%LOCALAPPDATA%\FBXTo3dsMax\language.txt`.

## Reinstall, upgrade and archives

Drag the same installer again for a same-version reinstall. Downgrades are rejected by default. Install/uninstall share an exclusive package lock. The installer stages the fixed resources, verifies SHA-256, archives the previous package, switches the complete package, then reads back files, version and toolbar state. On failure it attempts to restore the previous package and managed files.

The current source manifest has **32 safe, unique targets**. Installed hashes are recorded in `FBXTo3dsMax.install-manifest.sha256`; its target set must equal the fixed source manifest. Do not use a historical encrypted-edition manifest or the former 27-target source manifest.

Logs, staging, archives and the lock live under:

```text
%APPDATA%\Autodesk\FBXTo3dsMaxInstaller
```

The result dialog gives the exact paths for that transaction. Unrecognized same-name package, Macro or icon files cause an ownership failure rather than an overwrite. Recognized legacy AutoLoader scripts are archived with their locations recorded. Historical source projects are outside the cleanup scope.

An archived installation is recoverable data, not an automatic restore button. Preserve its manifest and logs; inspect it before manual recovery. Historical uninstall acceptance verified archived bytes but did not exercise restoring from that archive.

## Missing button or window

Check that the download was complete and extracted, read the actual installation result/log, then rerun the standard installer and restart Max. If the problem remains, report the full Max version, plug-in version and reproduction steps with sanitized logs.

Running `contents/FBXTo3dsMax_UI.ms` directly only opens a temporary UI; it does not establish that the package is installed correctly. Developers must retain `post-start-up scripts parts` in `PackageContents.xml`: it is the AutoLoader routing identifier.

## Self-check and first transfer

The built-in self-check starts a dedicated `3dsmaxbatch.exe` and uses original generated scenes. It does not reset the current interactive scene. It runs asynchronously and may be cancelled. Success requires all six categories and natural process exit **0**. Timeout, forced cleanup, cancellation or a nonzero exit are failure even if a JSON result looks successful.

Reports are saved in `%LOCALAPPDATA%\FBXTo3dsMax\SelfCheck`. Resolve self-check failures before processing formal assets. After success, use a scene copy and start with a single receiving mesh and the default position/shape channel. Check appearance, animation and save/reload.

The actual transfer is synchronous on Max's main thread; it currently has no safe mid-transfer cancellation.

## Uninstall

Drag root `Uninstall_FBXTo3dsMax.ms` into Max, or run the installed `contents/Uninstall_FBXTo3dsMax.ms`. The uninstaller checks ownership, cleans the owned UI/toolbars/callbacks, archives the package and managed Macro/icons, and records their SHA-256. On failure it attempts restoration.

Keep the archive path shown by the result dialog. Restart Max after uninstall to clear cached action items. User scenes and retained recovery archives are not permanently deleted.

## Optional PowerShell entry

Use drag-and-drop when interactive Max is already open. With all Max/Batch processes closed, run PowerShell 7 from the repository root:

```powershell
pwsh -NoLogo -NoProfile -File .\tools\Install_FBXTo3dsMax.ps1 -MaxRoot '<absolute Max installation directory>'
```

Replace the placeholder with your installation directory or absolute `3dsmax.exe` path. This launcher first checks files, versions and the chosen Max path, then starts Max with the same standard `.ms` transaction. It refuses existing Max/Batch processes and does not terminate them.

Development checks are described in [TESTING](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md). The installed offline guide is named `INSTALL_EN.md`; `README_EN.md` and `USER_GUIDE_EN.md` are beside it.
