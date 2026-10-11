**English** | [简体中文](README.zh-CN.md)

> **中文用户：** 插件有完整中文界面与教程。[点击进入简体中文首页 →](README.zh-CN.md)

# FBXTo3dsMax

### Bring mesh revisions back to the Max scene you already built.

A free, open-source **FBX → Autodesk 3ds Max** plug-in for **selective mesh-data transfer**, **custom normals** and **Skin-aware mesh replacement**.

- **Update only what changed. Keep the Max receiver.** On matching topology, choose shape, UV 1/2/3, materials/IDs, RGB or alpha and write into the existing receiving node.
- **Bring smoothing groups and authored normals back together.** Transfer hard/soft relationships and custom corner directions, with strict checks and final-direction readback.
- **New FBX mesh and weights. Your Max scene bones.** Replace a skinned mesh after Skin, bone and binding checks, with a hidden old-mesh backup enabled by default.

**[Download v1.4.26 with refreshed tutorials](https://github.com/DimmensCK/FBXTo3dsMax/releases/tag/v1.4.26)** · **[Watch the walkthrough](#demos)** · [Quick start](#quick-start) · [Full tutorial](docs/en/USER_GUIDE.md)

Dimmens · MIT · Readable Python / MAXScript · Tested on **3ds Max 2023.3.10**

[![Source checks](https://github.com/DimmensCK/FBXTo3dsMax/actions/workflows/source-checks.yml/badge.svg?branch=main)](https://github.com/DimmensCK/FBXTo3dsMax/actions/workflows/source-checks.yml)

[Workflows](#workflows) · [Shape](#shape) · [UV](#uv) · [Materials](#materials) · [RGB & alpha](#colors) · [Smoothing](#smoothing) · [Normals](#normals) · [Skin](#skin) · [Install](#quick-start) · [中文 / English UI](#language-ui)

![Author's historical Mode 1 result preview](docs/assets/demos/mode1-historical-preview.gif)

*Historical v1.3.23 Mode 1 result inspection; full workflow below.*

<a id="demos"></a>

## See the author's workflow in action

The author's historical **v1.3.23 Mode 1 walkthrough** shows the complete flow: select an FBX, check the match, select multiple channels, transfer, read the normal/channel notices and inspect the result with the existing bones.

**Complete walkthrough · 60.43 seconds**

[![Open or download the author's full MP4 walkthrough](docs/assets/demos/mode1-author-poster.png)](https://github.com/DimmensCK/FBXTo3dsMax/raw/refs/heads/main/docs/assets/demos/mode1-author-full-v1.3.23.mp4)

**[Open / download the full MP4](https://github.com/DimmensCK/FBXTo3dsMax/raw/refs/heads/main/docs/assets/demos/mode1-author-full-v1.3.23.mp4)**

**Edited tour · 28.93 seconds · waiting sections shortened**

**[Open / download the edited-tour MP4](https://github.com/DimmensCK/FBXTo3dsMax/raw/refs/heads/main/docs/assets/demos/mode1-author-guide-v1.3.23.mp4)**

Click the frame or links to open / download the MP4; behavior depends on the browser. The [fixed tutorial snapshot ZIP](https://github.com/DimmensCK/FBXTo3dsMax/releases/tag/v1.4.26) also includes the [full recording](docs/assets/demos/mode1-author-full-v1.3.23.mp4) and [edited tour](docs/assets/demos/mode1-author-guide-v1.3.23.mp4).

| In the full recording | What to watch |
|---|---|
| Around 0:00 | Select the FBX and run the precheck |
| Around 0:17 | Select the data channels and start the transfer |
| Around 0:46 | Read the custom-normal explanation and missing-UV3 notice |
| Around 0:49 | Inspect the new shape and normal modifier, then rotate an existing bone |

Both cuts use the same author-provided historical recording and retain the important notices. The current UI may differ. [Media sources and versions](docs/assets/MEDIA.md).

<a id="workflows"></a>

## Two workflows for two kinds of revision

**Data flows from FBX into the receiving Max mesh.** Select the Max mesh first, then the FBX.

| What changed? | Choose | What the plug-in does |
|---|---|---|
| Shape, UVs, materials, vertex data or shading on matching topology | **Matching Models / Transfer Data** | Keeps the Max receiving node and writes the selected channels |
| Mesh topology and Skin weights | **Different Models / Replace / Keep Skin** | Uses the new FBX mesh/weights with the Max scene's Skin bones and binding data |

![Author's historical example: selecting Max receiving meshes](docs/assets/tutorial/select-receiving-meshes.webp)

One Max mesh and one FBX mesh can pair directly. Other object-count combinations match by full mesh names. The image above illustrates Max-side selection only. Mode 1 requires stable vertex identity, connectivity, winding and a unique face mapping; equal counts alone are insufficient.

![Author's historical FBX file-picker example, with private paths removed](docs/assets/tutorial/select-fbx-path-redacted.png)

After selecting the Max receiver, use the plug-in's file picker to choose the FBX that supplies the revised data.

![Author's historical precheck-button illustration, with private paths removed](docs/assets/tutorial/preflight-path-redacted.png)

**Check first, then run:** read matches and warnings in **Check FBX / Match**, then execute the transfer. A passed precheck has not written the selected data yet.

<a id="examples"></a>
<a id="shape"></a>

## Shape: change the silhouette, keep the Max node

Bring an edited shape back to the receiving mesh without replacing that node. Use this for proportion, silhouette and point-position revisions that preserve topology identity.

| Author's historical example: before | After |
|---|---|
| ![Shape before transfer](docs/assets/tutorial/deformation-before.webp) | ![Shape after transfer](docs/assets/tutorial/deformation-after.webp) |

**Try it:** choose Mode 1 → leave only **Shape** selected → **Check FBX / Match** → **Run Transfer**. Inspect the shape and original node; check Skin playback on a scene copy when applicable. Leave unrelated channels unselected.

[Shape tutorial](docs/en/USER_GUIDE.md#task-1--update-shape-only)

<a id="uv"></a>

## UV transfer: re-unwrap without moving the mesh

Transfer **UV 1 / 2 / 3** independently. Face-corner mapping preserves the distinction between a geometric vertex and its UV seam vertices.

![Author's historical UV inspection: map channel 2](docs/assets/tutorial/uv-channel-2.webp)

**Try it:** deselect **Shape** → select the UV channels actually present in the FBX → check and transfer. In a test copy, inspect the corresponding map channel in **Unwrap UVW**, including islands, seams and checker stretching. The author's image shows channel **2**; select channel 1 or 3 to inspect those transfers.

A missing channel is reported and skipped. The walkthrough deliberately retains its UV3-missing notice so you can see the difference between a completed operation and an uncopied channel.

[UV tutorial](docs/en/USER_GUIDE.md#task-2--update-uvs-materials-and-face-ids)

<a id="materials"></a>

## Materials: bring back assignments and face IDs

Update the material object and per-face material IDs together while choosing whether positions or other channels should change.

![Author's historical material and face-ID inspection](docs/assets/tutorial/materials-and-face-ids.webp)

**Try it:** select **Material / ID**, deselect unrelated channels → check and transfer → inspect material slots and the actual face IDs. A UV-only revision can leave materials untouched.

[Materials and face-ID tutorial](docs/en/USER_GUIDE.md#task-2--update-uvs-materials-and-face-ids)

<a id="vertex-data"></a>
<a id="colors"></a>

## Vertex colors and alpha: transfer them independently

Bring back RGB color and an independent alpha mask, selecting either or both.

| RGB vertex color | Independent vertex alpha |
|---|---|
| ![Author's historical RGB inspection](docs/assets/tutorial/vertex-color-rgb.webp) | ![Author's historical alpha inspection](docs/assets/tutorial/vertex-alpha.webp) |

**Try it:** select **Vertex RGB** and/or **Vertex Alpha** → check and transfer → inspect the relevant channel using an appropriate viewport display or material. RGB uses **map channel 0**; alpha uses **map channel -2** and is never inferred from RGB brightness.

[Vertex-data tutorial](docs/en/USER_GUIDE.md#task-3--transfer-rgb-and-alpha-separately)

<a id="smoothing"></a>

## Smoothing groups: preserve the soft and hard relationships

A valid native FBX smoothing layer takes priority. Where inference is needed, the strict solver validates soft/hard edges and vertex fans against Max's **32-bit smoothing masks**. Unsupported or unrepresentable relationships stop the operation.

![Author's historical selection by smoothing group](docs/assets/tutorial/smoothing-groups.webp)

**Try it:** select **Smoothing Groups** → check and transfer → inspect the per-face masks and **Select by Smoothing Groups** on a test copy. Choose custom normals as well when the authored directions carry information that SG cannot express.

[Smoothing-group tutorial and constraints](docs/en/USER_GUIDE.md#task-4--choose-smoothing-groups-or-custom-normals)

<a id="normals"></a>

## Custom-normal transfer: carry the directions you authored

Transfer FBX custom corner directions and keep them alongside smoothing groups. The SG-aware path retains custom differences greater than **0.1°** from the smoothing baseline; written directions are checked after writing and reevaluation.

![Author's historical F2M normal modifier and direction display](docs/assets/tutorial/custom-normals.webp)

| Your goal | Select |
|---|---|
| Update smoothing relationships only | **Smoothing Groups** |
| Keep the Max receiver's SG and bring back custom directions | **Vertex Normals** |
| Bring back both from FBX | **Smoothing Groups + Vertex Normals** |

**Try it:** choose the appropriate combination → check and transfer → inspect the result and retain **`F2M_顶点法线`**. This generated modifier is part of the final result: do not delete or collapse it. Detected overriding user **Edit Normals / Weighted Normal** modifiers stop the operation rather than being silently removed.

The full author video shows the normal-difference explanation and an inspection comparison. Display-line colors indicate editing or selection state; inspect the directions and report to assess the result.

[Normal-transfer paths and tutorial](docs/en/USER_GUIDE.md#task-4--choose-smoothing-groups-or-custom-normals)

<a id="skin"></a>

## Changed topology: new FBX weights, your Max scene bones

Mode 2 combines the revised FBX mesh and its per-vertex weights with the existing Max Skin's scene bones and binding data. It also handles the FBX vertex **Unnormalized** and **DQ** state and reads the completed candidate back before and after commit.

![Original schematic: FBX mesh and weights with Max Skin bones and binding](docs/assets/diagrams/skin-data-authority.svg)

*Original workflow schematic, not a software capture or replacement recording.*

| Final data | Comes from |
|---|---|
| New mesh, channels, default material and per-vertex weights | **FBX** |
| Scene-bone identities, Bone Bind/Stretch, envelopes and Skin local data | **Max Skin** |
| Candidate Mesh Bind | Adapted binding created for the new candidate |

**Try it:** save a scene copy → ensure each mesh has **one valid Skin** and the required bones match uniquely → choose Mode 2 → keep **Hide old mesh as backup** enabled → check and transfer. Inspect weight deformation, world placement and the hidden old backup, then play animation and save/reopen.

The candidate inherits the old Max layer and node display state. Backups enable batch rollback; multiple-object replacements require them. Old parenting, transform/animation controllers, constraints and arbitrary user modifiers do not migrate automatically. A single-object replacement with backup disabled crosses an irreversible old-node deletion boundary.

The recording above demonstrates **Mode 1**; no complete author Mode 2 recording is supplied. [Mode 2 tutorial and data contract](docs/en/USER_GUIDE.md#task-5--replace-a-skinned-mesh-after-topology-changes).

<a id="quick-start"></a>

## Start in three steps

1. **Open the [v1.4.26 release page](https://github.com/DimmensCK/FBXTo3dsMax/releases/tag/v1.4.26), download the complete-project ZIP featured at the top, and extract it.** Keep the installer, lowercase `contents/` and all other package folders together.
2. **Save your scene and drag `Install_FBXTo3dsMax.ms` into a Max viewport.** Confirm the installation result before proceeding.
3. **Open `FBX 转 MAX / FBX to MAX` from the toolbar.** Choose **EN** or **中文**, run **Self-check**, and start with one receiving object in a scene copy.

The plug-in uses Max's bundled Python; a separate interpreter, compiler or administrator access is normally unnecessary. Uninstall with `Uninstall_FBXTo3dsMax.ms`.

[Installation, repeat installation and uninstall](docs/en/INSTALL.md) · [Release notes](https://github.com/DimmensCK/FBXTo3dsMax/releases/tag/v1.4.26)

<a id="language-ui"></a>

### Choose the plug-in's language in place

| English UI | 中文界面 |
|---|---|
| [![English interface reference from an earlier 1.4.26 source](docs/assets/ui/rollout-1.4.26-en.png)](docs/assets/ui/rollout-1.4.26-en.png) | [![较早 1.4.26 来源的真实中文界面参考](docs/assets/ui/rollout-1.4.26-cn.png)](docs/assets/ui/rollout-1.4.26-cn.png) |

Use **Language · 中文 / EN** beside the mode heading. Switching retains the mode, FBX, options and check state, keeps exactly one language selected and saves the preference. Known UI/report labels are localized; raw technical diagnostics may retain their original language.

Both real Max 2023.3.10 captures show an earlier 1.4.26 layout. Click either image to open its original size. [Media details](docs/assets/MEDIA.md).

<a id="guides"></a>

## Keep learning

- [Full task-based user guide](docs/en/USER_GUIDE.md): operation steps, matching, channel contracts, Skin authority and troubleshooting.
- [Installation guide](docs/en/INSTALL.md): complete package, repeat install, ownership checks, logs and uninstall.
- [简体中文首页](README.zh-CN.md) and [Chinese full tutorial](docs/zh/FBXTo3dsMax_详细说明书.md).
- [Media notes](docs/assets/MEDIA.md): author screenshots/videos, historical versions and original illustrations.

<a id="exercise"></a>

### Try an original practice scene

The [canopy exercise](docs/examples/README.md) generates a receiving mesh and edited FBX locally. Try **Mode 1 + Shape + UV1**, then inspect the transfer yourself; no model download is required.

| Original canopy before | After actual Shape + UV1 transfer |
|---|---|
| ![Original canopy before transfer](docs/assets/demos/canopy-before-1.4.26.png) | ![Original canopy after transfer](docs/assets/demos/canopy-after-1.4.26.png) |

These native Max 2023.3.10 renders show one installed-copy 1.4.26 run on a **91-vertex, 144-triangle** original mesh, with the same camera, material and lighting. See the exercise and media notes for scope.

<a id="scope"></a>
<a id="testing"></a>

## Tested scope and scene protection

Real-host qualification used **Windows 11 x64, 3ds Max 2023.3.10 and bundled Python 3.9.7**. The documented source passed **337 pure regressions**, six installed business checks, nine native fault cases and sixteen independent world-point cases, plus the isolated installation/rollback/uninstall chain. [TESTING](docs/TESTING.md) records exact sources and limits; CI runs source checks without Max. This homepage revision changes presentation outside the installed runtime resources.

**Max 2024–2026 remain unverified.** Small original test scenes do not establish every complex rig, large-asset performance or absence of unknown bugs. Uninstall archives were hash-checked; archive restoration was not exercised.

Check before transfer, then read the execution result and inspect a scene copy. Mode 1 uses per-object transactions, so a later object's failure does not undo earlier successful objects. Mode 2 supports batch rollback with retained backups. Names, selection, importer settings and temporary nodes have restoration/readback safeguards. Actual transfer is synchronous and has no safe mid-operation cancellation.

## Feedback, source and license

The repository includes readable **Python / MAXScript**, installers, tests and tutorials. For a first installation, use the complete-project ZIP featured on the [v1.4.26 release page](https://github.com/DimmensCK/FBXTo3dsMax/releases/tag/v1.4.26). The automatic **Assets → Source code** ZIP is the original tag snapshot; [main ZIP](https://github.com/DimmensCK/FBXTo3dsMax/archive/refs/heads/main.zip) changes with the branch and is for development.

Have a reproducible issue? Include Max/plugin versions and sanitized steps in [Issues](https://github.com/DimmensCK/FBXTo3dsMax/issues). Remove local paths, model names and project information from logs; do not upload private assets.

[Contributing](docs/development/CONTRIBUTING.md) · [Changelog](docs/development/CHANGELOG_中文.md) · [GitHub download/update guide](docs/GITHUB_发布指南.md)

Copyright © 2026 **Dimmens** · [MIT License](LICENSE). Free use, modification, commercial use and redistribution require retaining the copyright/license. Authorized tutorial media does not grant rights to the underlying private models; no private FBX/MAX/BLEND model files are distributed. Autodesk 3ds Max is obtained separately.
