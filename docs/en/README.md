![FBXTo3dsMax — bring FBX edits back into your Max scene](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/brand/fbx-to-max.svg)

# FBXTo3dsMax

### Edit elsewhere. Continue in your Max scene.

**Bring FBX shape, UVs, materials, vertex colors and normals into an existing 3ds Max scene. When topology changes, replace the skinned mesh under strict validation while using the scene's skeleton and binding system.**

By **Dimmens** · Free, readable Python / MAXScript source · **MIT** · **中文 / English**

[中文](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/README_中文.md) · [Install](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/INSTALL.md) · [Complete user guide](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md) · [Download source](https://github.com/DimmensCK/FBXTo3dsMax/archive/refs/heads/main.zip)

This page describes **1.4.25** operations and design. See [testing](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md) for version-specific results. **Historical 1.4.24 results do not qualify 1.4.25.**

## 1 · What problem does it solve?

Your Max scene already contains organization, materials or skinning. You then revise the mesh in a modeling tool. A fresh import should not require rebuilding the scene or guessing which data came across correctly.

FBXTo3dsMax makes the choice explicit: **transfer selected data when topology matches; validate and replace a skinned mesh when topology changes.** Data always flows **FBX → receiving Max mesh**.

| Your task | Workflow to try |
|---|---|
| Adjust proportions or shape while keeping the Max node | Mode 1, positions only |
| Revise UVs, face material assignments, RGB or alpha | Mode 1, the required channels only |
| Bring back smoothing groups and edited normals | Mode 1, SG and/or custom normals as appropriate |
| Change topology while using the Max scene's bones | Mode 2, with valid Skin on both meshes and uniquely matched bones |

## 2 · Choose a workflow

![Two workflows and their data direction](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/diagrams/two-modes.svg)

| | Mode 1: Matching Models / Transfer Data | Mode 2: Different Models / Replace / Keep Skin |
|---|---|---|
| Requirement | Unique vertex, connectivity and winding correspondence | One Skin per mesh; valid bone, weight and binding checks |
| Mesh | Retains the receiving Max node; writes selected channels | Replaces the old mesh with the FBX candidate |
| Skin | Does not replace the original node with a new mesh | Max supplies scene bones/binding data; FBX supplies weights |
| Default protection | Snapshot and readback for each object | Hidden old-mesh backup; batch rollback while backups are retained |
| Important limit | Equal vertex/face counts are not enough | Does not clone old parenting, animation controllers or arbitrary modifiers |

## 3 · What makes it useful?

| Capability | Practical benefit |
|---|---|
| **Selective channels** | Update only the data you changed: UVs without replacing materials, for example. Only positions are selected by default |
| **Face-corner mapping** | UVs/normals are corner-based; material IDs/smoothing masks are face-based. The transfer respects that distinction |
| **Strict smoothing and normal paths** | A valid native FBX smoothing layer takes priority. Inferred constraints must validate; unrepresentable cases stop |
| **Explicit Skin authority** | Avoids writing another skeleton's FBX bind matrices onto scene bones; reads back bones, weights and bindings |
| **Inspect, write, restore, report** | Precheck is not final completion. Execution validates again and restores selection, names and importer settings |
| **Readable source** | Uses Max's bundled Python. Usually no administrator access, extra Python or compiler is needed; MIT permits modification and redistribution |

These are capabilities and checks, not promises of universal losslessness, zero defects or superior benchmark performance.

## 4 · The data you can bring back

![Original schematic: vertices, face corners, faces and independent data channels](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/diagrams/channel-map.svg)

### Shape — bring the edit back into the scene

| Historical illustration: before | Historical illustration: after |
|---|---|
| ![Before historical shape transfer](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/deformation-before.webp) | ![After historical shape transfer](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/deformation-after.webp) |

Mode 1 writes point positions while retaining the Max receiving node and user stack. The images illustrate a historical result; their left/right arrangement does not define a fixed FBX/Max source convention.

[Watch the historical deformation/binding inspection clip, about 10 seconds (v1.3.23)](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/assets/demos/mode1-deformation-v1.3.23.mp4). It does not show the complete operation or qualify the current version.

### Materials and face IDs — transfer the assignment too

![Authorized historical screenshot: material and per-face ID inspection](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/materials-and-face-ids.webp)

Select materials/IDs to transfer both the material object and each face's ID. Viewport color alone does not prove per-face assignment: inspect the affected faces and material slots.

### UVs — face-corner transfer for channels 1 / 2 / 3

UV sharing does not correspond one-to-one with geometric vertices. The plug-in maps faces and corners for **map channels 1, 2 and 3**. Select only the UV channels you changed. Missing selected channels are reported and skipped; skipped is not copied.

### Vertex color — separate RGB and alpha control

![Authorized historical screenshot: RGB vertex-color inspection](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/vertex-color-rgb.webp)

**RGB is map channel 0.** Materials, lighting and viewport settings affect its appearance; inspect the actual channel as well.

![Authorized historical screenshot: independent vertex-alpha inspection](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/vertex-alpha.webp)

**Alpha is independent map channel -2.** It is not guessed from RGB brightness. RGB and alpha can be selected and read back separately.

All five screenshots are **author-authorized historical tutorial images**, not 1.4.25 UI captures. No model files accompany them. Original SVGs explain concepts and are not software screenshots. [Media provenance and scope](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/assets/MEDIA.md)

## 5 · Your first transfer in five steps

1. **Download and extract everything.** Use **Code → Download ZIP** in the [repository](https://github.com/DimmensCK/FBXTo3dsMax). Keep the directory structure; do not download only the installer.
2. **Install and confirm success.** Drag root `Install_FBXTo3dsMax.ms` into the Max viewport. On failure, read the log before continuing.
3. **Open and choose a language.** Click **FBX 转 MAX / FBX to MAX**, then **EN** beside **Language** for English (or **中文** for Chinese), and run the self-check.
4. **Start with a copy and one mesh.** Select the receiving Max mesh, FBX, mode and channels. Positions are the default.
5. **Check, transfer, inspect.** Run **Check FBX / Match**, read the report, then **Run Transfer**. Inspect appearance, channels, animation and save/reload.

[Full installation and removal steps](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/INSTALL.md) · [Task-oriented user guide](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md)

## 6 · Smoothing groups and custom normals do different jobs

![Original schematic: smoothing relationships and corner-normal directions](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/diagrams/smoothing-and-normals.svg)

- **Smoothing groups (SG)** define which faces share computed normals. A face can belong to several groups.
- **Custom normals** specify actual corner directions. SG alone cannot express every hand-edited or Weighted Normal result.
- A unique, valid native FBX smoothing layer takes priority. Otherwise direction-based inference must satisfy strict constraints; non-manifold or contradictory cases stop.
- With both selected, SG is written and read back first. Do not delete or collapse the retained `F2M_顶点法线` modifier.

Display color does not prove source authority. Directions, flags and readback do. [Normal transfer paths and limits](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md)

## 7 · What does “keep Skin” mean after a topology change?

![Original schematic: Mode 2 geometry, weights and binding authority](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/diagrams/skin-data-authority.svg)

**FBX supplies the new mesh and per-vertex weights. Max supplies existing scene-bone identities, binding local data, envelopes and related parameters.** Mesh Bind is adapted for the candidate, then fully read back.

Commit requires one Skin on each mesh and unique mapping of every actual influence to Max bones. Hidden old-mesh backup is on by default and mandatory for multiple objects. Disabling it is single-object only and creates an irreversible boundary after deletion.

This does not copy the entire old animation system after arbitrary topology editing. Old parenting, transform/animation controllers, constraints and arbitrary modifiers do not migrate automatically. Test complex rigs on a copy, with playback and save/reload. [Complete Mode 2 contract](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md)

## 8 · 中文 and English, the same workflow

Compact **Language · 中文 / EN** buttons occupy the mode heading’s right corner. **EN** selects English. Exactly one stays selected, including when the active button is clicked. Switching updates the existing window in place without clearing the mode, FBX, options or check state. The chosen language is saved for later use.

[Language UI reference in the repository](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/README.md#language-ui). The installed copy includes this page’s text; images, videos and web navigation use the online repository and require internet access.

| 中文 | English |
|---|---|
| 模型完全一致 / 传递数据 | Matching Models / Transfer Data |
| 模型不一致 / 替换并保留蒙皮 | Different Models / Replace / Keep Skin |
| 检查 FBX/匹配 | Check FBX / Match |
| 开始执行 | Run Transfer |
| 运行插件自检 | Run Self-check |

Known UI labels and user messages follow the selected language. Original technical diagnostics may retain their original language, and stable JSON check names/summary protocols are unchanged. This is not a promise of all-English diagnostics.

## 9 · Scope to know before use

Historical validation used **Windows 11 x64, Max 2023.3.10 and bundled Python 3.9.7**. Package metadata declares Max 2023–2026; **2024–2026 remain untested**. Check [version-specific testing](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md). The former 27-target to 32-target upgrade was not separately exercised.

Mode 1 is transactional **per object**; a later failure does not automatically undo earlier successful objects. Mode 2 supports batch rollback while the old meshes remain. One injected-failure regression does not cover every failure. Uninstall retains recovery archives; archived-byte verification is not an exercised reinstall from those archives.

Self-check uses small original procedural scenes. It cannot replace complex-asset or performance tests, or your own scene-copy acceptance. Actual transfer is synchronous and has no safe mid-transfer cancellation.

Reports go to `%LOCALAPPDATA%\FBXTo3dsMax`; installation archives go to `%APPDATA%\Autodesk\FBXTo3dsMaxInstaller`. Sanitize local paths, model names and project information before public feedback.

## 10 · Documentation, feedback and source

| Goal | Start here |
|---|---|
| Install, reinstall or remove | [English installation](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/INSTALL.md) / [中文安装](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/INSTALL_中文.md) |
| Use the workflows and understand failures | [Complete English guide](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md) / [中文教程](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md) |
| See what a version actually passed | [Testing](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md) · [Changelog](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/development/CHANGELOG_中文.md) |
| Report a problem or contribute | [Issues](https://github.com/DimmensCK/FBXTo3dsMax/issues) · [Contributing](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/development/CONTRIBUTING.md) |
| Download or maintain with GitHub | [GitHub download and maintenance guide](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/GITHUB_发布指南.md) |

The repository includes source, documentation, authorized tutorial media and procedural regression code. It distributes **no FBX / MAX / BLEND model files, original PDF or internal resource links**.

Copyright © 2026 **Dimmens** · [MIT License](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/LICENSE). Free to use, modify, redistribute and use commercially while retaining the copyright and license. Tutorial media is authorized for documentation; no rights to the underlying private models are granted. Autodesk 3ds Max must be obtained separately.
