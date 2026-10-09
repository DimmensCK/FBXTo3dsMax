# Installing FBXTo3dsMax 1.4.25

[中文安装说明](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/INSTALL_中文.md) · [Overview](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/README.md) · [User guide](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md)

This is the installation and removal guide for the **1.4.25 readable source edition**. Consult [testing](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md) for version-specific acceptance. Historical 1.4.24 and 1.3.24 results do not qualify 1.4.25.

## Choose the right entry

| Goal | Entry |
|---|---|
| Install or reinstall the same version | Root `Install_FBXTo3dsMax.ms` |
| Remove the package while retaining recovery archives | Root `Uninstall_FBXTo3dsMax.ms` |
| Work after installation | Max top-toolbar **FBX 转 MAX / FBX to MAX** |

**Complete ZIP → extract → run installer → confirm success → self-check → first transfer on a scene copy.** The installer and `contents/` must come from the same complete version. Opening the UI script alone does not install the package.

## Download and environment

Download the complete [repository](https://github.com/DimmensCK/FBXTo3dsMax) using **Code → Download ZIP**, then extract it. Keep root `Install_FBXTo3dsMax.ms`, `PackageContents.xml`, `LICENSE`, and the lowercase `contents/`, `docs/`, `tests/`, `tools/` directories together. Do not execute inside the ZIP or download the installer alone.

Historical acceptance used Windows 11 x64, Max 2023.3.10 and Python 3.9.7. Package routing declares Max 2023–2026; 2024–2026 have not been validated. The plug-in uses the Python shipped with Max; normal installation needs no separate interpreter or compiler.

The source distribution contains no FBX/MAX/BLEND model files. Self-check data is generated procedurally in the local user-data directory.

## Recommended installation

1. Save your current Max scene.
2. Drag root **`Install_FBXTo3dsMax.ms`** into the Max viewport.
3. Wait for completion and confirm success. Interactive installation normally shows a result dialog; silent startup may record the result in the log instead. On failure, retain the log and resolve it before use.
4. After success, click **FBX 转 MAX / FBX to MAX** on the top toolbar. The main toolbar is preferred; a docked fallback toolbar is used when necessary.
5. Click **EN** beside **Language** for English (or **中文** for Chinese), then **Run Self-check** and read its report.
6. Close and reopen Max, confirm the button remains available, and try your first transfer on a scene copy.

Installation does not automatically open the plug-in window. It is per-user and normally needs no administrator access. The installed package is normally:

```text
%APPDATA%\Autodesk\ApplicationPlugins\FBXTo3dsMax
```

After installation, Max runs the complete installed copy. The UI language updates without reopening the window and is saved in `%LOCALAPPDATA%\FBXTo3dsMax\language.txt`. See the root [language UI reference](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/README.md#language-ui); installed text is local, while web images and videos require internet access.

## Reinstall, upgrade and archives

Drag the same installer again for a same-version reinstall. Downgrades are rejected by default. Install/uninstall share an exclusive package lock. The installer stages the fixed resources, verifies SHA-256, archives the previous package, switches the complete package, then reads back files, version and toolbar state. On failure it attempts to restore the previous package and managed files.

The current source manifest has **32 safe, unique targets**. Installed hashes are recorded in `FBXTo3dsMax.install-manifest.sha256`; its target set must equal the fixed source manifest. Do not use a historical encrypted-edition manifest or the former 27-target source manifest.

Logs, staging, archives and the lock live under:

```text
%APPDATA%\Autodesk\FBXTo3dsMaxInstaller
```

The result dialog gives the exact paths for that transaction. Unrecognized same-name package, Macro or icon files cause an ownership failure rather than an overwrite. Recognized legacy AutoLoader scripts are archived with their locations recorded. Historical source projects are outside the cleanup scope.

The historical 27-target to current 32-target upgrade has not been separately exercised; the new target count does not qualify that upgrade.

An archived installation is recoverable data, not an automatic restore button. Preserve its manifest and logs; inspect it before manual recovery. Historical uninstall acceptance verified archived bytes but did not exercise restoring from that archive. It does not establish installation, removal or recovery in your normal daily profile.

## Missing button or window

Check that the download was complete and extracted, read the actual installation result/log, then rerun the standard installer and restart Max. Do not manually delete same-name packages, Macros, icons or old AutoLoader scripts whose ownership is unknown just to remove a warning. If the problem remains, report the full Max version, plug-in version and reproduction steps with sanitized logs.

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

Task-based operation is covered in the [complete user guide](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md). Development checks are described in [TESTING](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md). The installed offline guide is named `INSTALL_EN.md`; `README_EN.md` and `USER_GUIDE_EN.md` are beside it.
