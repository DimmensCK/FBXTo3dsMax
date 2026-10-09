# Installing FBXTo3dsMax 1.4.26

[中文安装说明](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/INSTALL_中文.md) · [English overview](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/README.md) · [Complete user guide](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md)

## Start in three steps

1. **Download a complete release and extract it.** Use the [v1.4.26 source ZIP](https://github.com/DimmensCK/FBXTo3dsMax/archive/refs/tags/v1.4.26.zip), or choose **Source code (zip)** under Assets on the [Release page](https://github.com/DimmensCK/FBXTo3dsMax/releases/tag/v1.4.26). Do not save the installer alone or run inside the ZIP.
2. **Save your scene and drag in the installer.** Drag root **`Install_FBXTo3dsMax.ms`** into the Max viewport. Wait and confirm success; retain the log and resolve a failure before use.
3. **Open, self-check and try a copy.** Click **FBX 转 MAX / FBX to MAX** on the top toolbar. Click **EN** beside **Language**, then **Run Self-check**. Start on a scene copy with one receiving mesh and the default **Shape** option.

Installation does not open the plug-in window automatically. Interactive installation normally shows a result dialog; silent startup may record it in the log. After success, restart Max and confirm the toolbar entry remains. The main toolbar is preferred, with a docked fallback when necessary. [See the English UI reference](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/README.md#language-ui)

## Before installing

The installer, `PackageContents.xml`, `LICENSE` and lowercase `contents/`, `docs/`, `tests/`, `tools/` must come from the same complete version. The plug-in uses Max's bundled Python; normal installation needs no separate interpreter, compiler or administrator access.

Consult [TESTING](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md) for version-specific results and limits. Package metadata declares Max 2023–2026; **2024–2026 remain untested**. Self-check data is generated in the local user-data directory. The source package contains no FBX/MAX/BLEND model files.

| Goal | Entry |
|---|---|
| Install or reinstall the same version | Root `Install_FBXTo3dsMax.ms` |
| Remove the package and retain recovery archives | Root `Uninstall_FBXTo3dsMax.ms` |
| Work after installation | Max top-toolbar **FBX 转 MAX / FBX to MAX** |

Opening `contents/FBXTo3dsMax_UI.ms` directly is a temporary UI entry, not proof of installation. The repository's [main ZIP](https://github.com/DimmensCK/FBXTo3dsMax/archive/refs/heads/main.zip) is a development snapshot; prefer the fixed release above for your first installation.

## Installation and language locations

The normal per-user package location is:

```text
%APPDATA%\Autodesk\ApplicationPlugins\FBXTo3dsMax
```

Max runs the complete installed copy after installation. The mutually exclusive **中文 / EN** buttons switch the UI in place without reopening it. The preference file is `%LOCALAPPDATA%\FBXTo3dsMax\language.txt`. Installed guide text works offline; web images and videos require internet access.

Installer logs, staging, archives and the lock live under:

```text
%APPDATA%\Autodesk\FBXTo3dsMaxInstaller
```

The result dialog gives the paths for that transaction. Keep failure logs and archive information.

## Reinstall, upgrade and archives

Drag the same installer again for a same-version reinstall. Downgrades are rejected by default. Install/uninstall share an exclusive lock. The installer stages the fixed resources, verifies SHA-256, archives the previous package and managed files, switches the complete package, then reads back files, version and toolbar state. On failure it attempts restoration.

The fixed source manifest has **32 safe, unique targets**. `FBXTo3dsMax.install-manifest.sha256` records installed hashes; its target set must equal the fixed source manifest. This is an installation-resource count, not a test count. Do not mix a historical encrypted-edition manifest or the former 27-target source manifest with this version.

Unrecognized same-name package, Macro or icon files cause an ownership failure rather than an overwrite. Recognized legacy AutoLoader scripts are archived with their original locations recorded. Historical source projects are outside the cleanup scope.

The historical 27-target to current 32-target upgrade has not been separately exercised. An archive is data for inspected recovery, not an automatic restore button; keep its manifest and logs. Complete archived bytes do not prove that reinstalling from the archive was exercised or that installation/removal/recovery was qualified in your daily profile.

## Missing button, or installation failed

Check that the download was complete and extracted, read the actual installation result/log, then rerun the standard installer and restart Max. Do not manually delete same-name packages, Macros, icons or old AutoLoader scripts of unknown ownership to remove a warning.

If the problem remains, report the full Max version, plug-in version, reproduction steps and sanitized logs in [Issues](https://github.com/DimmensCK/FBXTo3dsMax/issues). Do not attach private models, full local paths or project information. Developers must retain `post-start-up scripts parts` in `PackageContents.xml`: it is the AutoLoader routing identifier.

## Self-check and first transfer

The built-in self-check starts a dedicated `3dsmaxbatch.exe` with original generated scenes. It does not reset your current interactive scene. It runs asynchronously and may be cancelled. Success requires all six categories and natural process exit **0**. Timeout, forced cleanup, cancellation or a nonzero exit are failure even if a JSON result is green.

Reports are saved in `%LOCALAPPDATA%\FBXTo3dsMax\SelfCheck`. Resolve failures before processing formal assets. Then start with a scene copy and one receiving mesh. Inspect the selected channels, appearance, animation and save/reload; Mode 1 updates positions by default, with other channels selected as needed.

Actual transfer is synchronous on Max's main thread and currently has no safe mid-transfer cancellation. Follow the [complete task guide](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md) for operation.

## Uninstall

Drag root `Uninstall_FBXTo3dsMax.ms` into Max, or run the installed `contents/Uninstall_FBXTo3dsMax.ms`. The uninstaller checks ownership, cleans the owned UI/toolbars/callbacks, archives the package and managed Macro/icons, and records SHA-256. On failure it attempts restoration.

Keep the archive location shown by the result. Restart Max after uninstall to clear cached action items. User scenes and retained recovery archives are not permanently deleted. Inspect the complete manifest, version and logs before attempting manual recovery; having an archive is not evidence of a completed restore.

## Optional PowerShell entry

Prefer drag-and-drop when interactive Max is open. With all Max/Batch processes closed, run PowerShell 7 from the repository root:

```powershell
pwsh -NoLogo -NoProfile -File .\tools\Install_FBXTo3dsMax.ps1 -MaxRoot '<absolute Max installation directory>'
```

Replace the placeholder with your installation directory or absolute `3dsmax.exe` path. This launcher checks files, versions and the Max path, then starts Max with the same standard `.ms` transaction. It refuses existing Max/Batch processes and does not terminate them. Read [TESTING](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md) for actual coverage and acceptance-tool exceptions; a narrowly accepted observation is not a waiver for every installation failure.

## Offline guides

Installed `contents/` keeps guide text flat as `README_中文.md`, `INSTALL_中文.md`, `FBXTo3dsMax_详细说明书.md`, `README_EN.md`, `INSTALL_EN.md`, `USER_GUIDE_EN.md`, alongside the changelog. Web links lead to the complete tutorials and media; open the corresponding neighboring text files when offline.
