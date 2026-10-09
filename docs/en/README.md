![FBXTo3dsMax](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/brand/fbx-to-max.svg)

# FBXTo3dsMax

**Bring FBX changes back into an existing 3ds Max scene.** A free, readable Python / MAXScript plug-in by **Dimmens**, under the MIT License.

[中文](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/README_中文.md) · [Installation](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/INSTALL.md) · [User guide](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md) · [Repository](https://github.com/DimmensCK/FBXTo3dsMax)

**Version: 1.4.24** · **UI: 中文 / English**. This version adds language switching and a cleaner layout. This page defines operation and proof requirements; consult [testing](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md) for current results. Historical 1.3.24 results do not automatically qualify later versions.

## Choose a workflow

| Situation | Mode | Result |
|---|---|---|
| Verified matching topology; shape or channels changed | **Matching Models / Transfer Data** | Retains the selected Max node and writes the selected channels |
| Changed FBX topology; both meshes have Skin | **Different Models / Replace / Keep Skin** | Uses the FBX mesh with existing Max scene bones and binding data, then writes FBX weights |

![Two transfer workflows](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/diagrams/two-modes.svg)

Mode 1 supports positions, UV channels 1–3, smoothing groups, custom normals, RGB vertex colors, alpha, materials and face material IDs. Equal vertex/face counts alone do not prove matching topology: vertex identity, edges, winding and face-corner correspondence must also match.

Mode 2 retains FBX geometry, channels, custom normals and materials by default. Max source Skin supplies the scene bones and coherent binding system; FBX supplies per-vertex weights and DQ state. The old mesh is hidden as a backup by default. It does not copy the old node's parenting, transform/animation controllers or arbitrary modifier stack.

## Start in five steps

1. Open the [repository](https://github.com/DimmensCK/FBXTo3dsMax), choose **Code → Download ZIP**, and extract the complete project.
2. Open Max and drag root **`Install_FBXTo3dsMax.ms`** into the viewport. Confirm installation succeeded.
3. Click **FBX 转 MAX / FBX to MAX**. Choose **English** in **语言 / Language**.
4. Run **Run Self-check**, read its report, and use a **scene copy** for the first transfer.
5. Select the Max receiving mesh, choose the FBX, mode and channels, use **Check FBX / Match**, read the report, then **Run Transfer**.

The plug-in uses Max's bundled Python. Normal installation needs no separate Python, compiler or administrator access. Keep the complete folder structure; downloading just the installer is insufficient.

The language selector updates the open UI in place and retains the mode, file, options and check state. Your selection is saved locally for later sessions. Technical diagnostics may retain their original wording.

## Shape transfer example

| Before | After |
|---|---|
| ![Before shape transfer](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/deformation-before.webp) | ![After shape transfer](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/deformation-after.webp) |

Author-authorized historical illustrations, not a 1.4.24 acceptance recording. No scene or model files are distributed. See [media notes](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/assets/MEDIA.md).

[Watch the historical deformation/binding inspection clip](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/assets/demos/mode1-deformation-v1.3.23.mp4) — v1.3.23, about 10 seconds. It shows result inspection, not the full operation or current-version qualification.

## Compatibility and limits

Historical real-host acceptance used **Windows 11 x64, Max 2023.3.10 and bundled Python 3.9.7**. The XML declares Max 2023–2026; **2024–2026 remain unverified**. Use the testing document to distinguish current results from historical coverage.

Mode 1 commits per object; later failures do not undo earlier successful objects. Mode 2 supports batch rollback when retaining the old meshes. Single-object deletion has an irreversible boundary. Small procedural self-check fixtures cannot establish complex-asset, performance or unknown-defect coverage.

Reports live under `%LOCALAPPDATA%\FBXTo3dsMax`. Installer archives live under `%APPDATA%\Autodesk\FBXTo3dsMaxInstaller`. The repository contains no FBX, MAX or BLEND model files.

## Reference and contribution

- [Full user guide](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md), including smoothing, custom normals and Skin authority.
- [Installation / uninstall](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/INSTALL.md), [testing](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md), [changelog](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/development/CHANGELOG_中文.md), and [contribution guide](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/development/CONTRIBUTING.md).

Installed copies contain the readable guides as `README_EN.md`, `INSTALL_EN.md` and `USER_GUIDE_EN.md` in the same `contents` directory. Website navigation above opens the maintained repository documentation.

Copyright © 2026 Dimmens. [MIT License](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/LICENSE): use, modification, redistribution and commercial use are permitted with the copyright and license notices retained. Private models are excluded; Autodesk 3ds Max is a separate product.
