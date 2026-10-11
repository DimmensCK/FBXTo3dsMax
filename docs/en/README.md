![FBXTo3dsMax — bring edits back to your Max scene](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/brand/fbx-to-max.svg)

# FBXTo3dsMax 1.4.26 · English overview

**Edit elsewhere. Continue in your Max scene.** Bring FBX shape, UVs, materials, vertex colors and normals into an existing 3ds Max scene. Update selected channels on matching topology, or replace a changed mesh after Skin, bone and binding checks pass.

Dimmens · Free readable Python / MAXScript · MIT · 中文 / English

**[Download complete v1.4.26 source](https://github.com/DimmensCK/FBXTo3dsMax/archive/refs/tags/v1.4.26.zip)** · [Release notes](https://github.com/DimmensCK/FBXTo3dsMax/releases/tag/v1.4.26) · [Install](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/INSTALL.md) · [中文概览](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/README_中文.md) · [Illustrated homepage](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/README.md)

[Start](#quick-start) · [UI](#language-ui) · [Workflows](#workflows) · [See each feature](#examples) · [Task guides](#guides) · [Scope](#scope)

<a id="quick-start"></a>

## Start in three steps

1. **Download and extract everything.** Keep the installer, `contents/` and the other folders together. Do not run inside the ZIP or download one script alone.
2. **Drag in the installer and confirm success.** Save your scene, then drag root **`Install_FBXTo3dsMax.ms`** into the Max viewport. Resolve any installation failure before use.
3. **Open, self-check and try a copy.** Click **FBX 转 MAX / FBX to MAX** on the top toolbar, choose **EN**, and run **Run Self-check**. Start on a scene copy with one receiving mesh and the default **Shape** option.

The plug-in uses Max's bundled Python; normal installation needs no separate interpreter, compiler or administrator access. Root `Uninstall_FBXTo3dsMax.ms` is the removal entry. [Detailed installation, reinstall and removal →](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/INSTALL.md)

<a id="language-ui"></a>

## English or Chinese, in the same window

![Actual English UI reference from earlier 1.4.26 source](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/ui/rollout-1.4.26-en.png)

[Full-size English UI](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/ui/rollout-1.4.26-en.png) · [Chinese UI](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/ui/rollout-1.4.26-cn.png)

This is a real **earlier 1.4.26 UI reference in Max 2023.3.10**, not qualification of the later revised core. **Language · 中文 / EN** switches in place, retaining the mode, FBX, options and check state; clicking the active language still leaves one selected. Known UI/report labels follow the language; technical diagnostics retain their original text when needed.

Select the **receiving Max mesh**, then the FBX: **FBX supplies data → Max receives it**. One mesh on each side can pair directly; other combinations require unique full mesh-name matches.

<a id="workflows"></a>

## Choose the workflow for your edit

| Your task | Choose | What must hold |
|---|---|---|
| Update shape, UVs, materials/face IDs, RGB/Alpha, SG or normals | **Mode 1 · Matching Models / Transfer Data** | Retain the Max node and update selected channels. Vertex identity, connectivity, winding and face mapping must correspond uniquely; matching counts alone are insufficient |
| Use a changed FBX mesh and its weights with Max scene bones | **Mode 2 · Different Models / Replace / Keep Skin** | Each side needs one qualifying Skin. Bone, weight and binding checks must pass; the old mesh is hidden as a backup by default |

![Original concept diagram: the two workflows](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/diagrams/two-modes.svg)

<a id="examples"></a>

## See what each feature does

Historical screenshots below are authorized inspection examples. They do not qualify the current source, and their left/right positions do not define data authority. No underlying model files accompany them. [Media provenance and scope](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/assets/MEDIA.md)

### Shape: retain the receiving Max node

| Authorized historical example: before | After |
|---|---|
| ![Historical shape before](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/deformation-before.webp) | ![Historical shape after](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/deformation-after.webp) |

Use Mode 1 with **Shape** only to change proportions or silhouette while retaining topology identity. Leave other channels unchecked. [Shape steps](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-1--update-shape-only) · [Historical v1.3.23 result-inspection clip, about 10 seconds](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/assets/demos/mode1-deformation-v1.3.23.mp4)

### An original exercise you can generate locally

| Original canopy before | After actual Shape + UV1 transfer |
|---|---|
| ![Original canopy before transfer](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/demos/canopy-before-1.4.26.png) | ![Original canopy after transfer](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/demos/canopy-after-1.4.26.png) |

This actual installed-copy 1.4.26 demonstration ran in **Max 2023.3.10**, using an original **91-vertex, 144-triangle** mesh. Both **960×640** renders share the camera, checker material and lighting; real Shape + UV1 transfer retained the receiver, material and selection. [Generate and try the canopy exercise](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/examples/README.md). The generator prepares data; you perform the check and transfer. No model download is needed. See TESTING for the executed scope.

### UV 1 / 2 / 3: inspect the actual map channel

![Historical UV editor inspecting map channel 2](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/uv-channel-2.webp)

Select only the UV channels present in the FBX. The historical image shows **map channel 2** and its UV islands; inspect channels 1 and 3 separately when transferring them. UVs are mapped by face corner, preserving seams. A missing selected channel is reported and skipped. [UV steps](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-2--update-uvs-materials-and-face-ids)

### Materials and face IDs: update assignment together

![Historical material and face-ID inspection](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/materials-and-face-ids.webp)

Select **Material / ID** to bring back the material object and per-face IDs. Check actual material slots and affected faces, rather than viewport color alone. Leave this option off for a UV-only edit. [Material and ID steps](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-2--update-uvs-materials-and-face-ids)

### RGB and Alpha: two independent channels

| Historical RGB inspection | Historical independent Alpha inspection |
|---|---|
| ![Historical Vertex RGB](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/vertex-color-rgb.webp) | ![Historical Vertex Alpha](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/vertex-alpha.webp) |

Select **Vertex RGB** and **Alpha** independently. RGB is **map channel 0**; Alpha is **map channel -2**, never inferred from RGB brightness. Inspect each selected channel with the appropriate viewport display or material. [Vertex-data steps](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-3--transfer-rgb-and-alpha-separately)

### Smoothing Groups: inspect the sharing between faces

![Historical Select by Smoothing Groups inspection](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/smoothing-groups.webp)

Select **Smoothing Groups** to update per-face masks and soft/hard relationships. Prefer a valid native FBX smoothing layer; strict inference stops when constraints cannot be represented exactly. The historical image shows face selection by SG, not every solver input passing. [SG choices and inspection](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-4--choose-smoothing-groups-or-custom-normals)

### Custom normals: preserve the intended corner directions

![Historical F2M normal modifier and direction display](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/custom-normals.webp)

Select **Vertex Normals** for custom directions; select SG too when both must come from FBX. Keep the resulting **`F2M_顶点法线`** modifier enabled and do not delete or collapse it. Line colors show editing/selection state, not which source supplied a normal. [Normals steps and transfer paths](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-4--choose-smoothing-groups-or-custom-normals)

### Changed topology: use FBX weights with Max scene bones

![Original concept diagram, not an execution capture: Mode 2 Skin data sources](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/diagrams/skin-data-authority.svg)

Mode 2 adopts the **FBX mesh, channels, default material and per-vertex weights**, and uses **Max scene-bone identity, binding local data and envelopes**. Candidate Mesh Bind is adapted. Both meshes need one qualifying Skin; matching, weights and binding are checked before submission. Keep the hidden old backup and inspect animation plus save/reload on a copy.

This is an **original concept diagram**, not a recording of a replacement. Old parenting, transform/animation controllers, constraints and arbitrary modifiers do not migrate automatically. [Complete Skin workflow](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-5--replace-a-skinned-mesh-after-topology-changes)

<a id="guides"></a>

## Continue with a task

| Task | English | 中文 |
|---|---|---|
| Install, reinstall and remove | [Install](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/INSTALL.md) | [安装指南](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/INSTALL_中文.md) |
| Shape only | [Task 1](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-1--update-shape-only) | [任务一](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务一只修改形状) |
| UVs, materials and face IDs | [Task 2](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-2--update-uvs-materials-and-face-ids) | [任务二](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务二更新-uv材质与面-id) |
| RGB and Alpha | [Task 3](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-3--transfer-rgb-and-alpha-separately) | [任务三](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务三分别传递-rgb-与-alpha) |
| SG and custom normals | [Task 4](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-4--choose-smoothing-groups-or-custom-normals) | [任务四](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务四选择光滑组或自定义法线) |
| Changed topology and Skin | [Task 5](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-5--replace-a-skinned-mesh-after-topology-changes) | [任务五](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务五拓扑改变后替换带-skin-的网格) |
| Data contracts and transactions | [Reference](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#technical-reference) | [技术参考](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#技术参考) |

The UI initially selects **Shape only**. The Python API separately defaults to `transfer_uv=True` and `uv_channels=[1]`; set intended channels explicitly in scripts.

<a id="scope"></a>

## Check, transfer, then inspect

A passed precheck means ready to attempt transfer, not completed transfer. Read skipped channels and per-object failures, then inspect the result and save/reload a copy. Mode 1 uses per-object transactions; a later failure does not undo earlier successful objects. Mode 2 supports batch rollback while backups are retained; single-object replacement without backup has an irreversible deletion boundary. Transfer is synchronous, without safe mid-transfer cancellation.

[TESTING](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md) records version-specific execution and limits. **Max 2023.3.10** is the tested host; package metadata routes 2023–2026, but **2024–2026 remain unverified**. Small original regressions do not guarantee every complex asset or zero unknown defects. Archive-byte verification does not mean restoration was exercised.

Reports are under `%LOCALAPPDATA%\FBXTo3dsMax`; installer logs/archives are under `%APPDATA%\Autodesk\FBXTo3dsMaxInstaller`. Remove paths, model names and project details before [Issues](https://github.com/DimmensCK/FBXTo3dsMax/issues). [Contributing](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/development/CONTRIBUTING.md) · [Changelog](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/development/CHANGELOG_中文.md)

## Source and offline guides

Installed text is flat beside the runtime as `README_EN.md`, `INSTALL_EN.md`, `USER_GUIDE_EN.md` and the three Chinese guides. Images/videos use online repository links and need internet access. The [main ZIP](https://github.com/DimmensCK/FBXTo3dsMax/archive/refs/heads/main.zip) is a development snapshot; choose the fixed release for a first installation. [GitHub download and maintenance guide](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/GITHUB_发布指南.md)

Copyright © 2026 **Dimmens** · [MIT](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/LICENSE). Free use, modification, redistribution and commercial use require retaining copyright and license. The repository distributes no private FBX/MAX/BLEND, original internal PDF or internal links. Tutorial-media permission does not grant rights to underlying private models. Autodesk 3ds Max is licensed separately.
