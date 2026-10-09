![FBXTo3dsMax — bring edits back to your Max scene](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/brand/fbx-to-max.svg)

# FBXTo3dsMax

### Edit elsewhere. Continue in your Max scene.

Bring FBX shape, UVs, materials, vertex data and normals into an existing **3ds Max** scene. Update selected channels when topology matches; replace a changed mesh only after Skin, bone and binding checks pass.

**Dimmens · Free readable source · MIT · 中文 / English**

**[Download complete v1.4.26 source](https://github.com/DimmensCK/FBXTo3dsMax/archive/refs/tags/v1.4.26.zip)** · [Release notes](https://github.com/DimmensCK/FBXTo3dsMax/releases/tag/v1.4.26) · [Install](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/INSTALL.md) · [中文概览](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/README_中文.md)

[Start in three steps](#quick-start) · [English UI](#language-ui) · [Choose a workflow](#workflows) · [See the changes](#examples) · [Task guides](#guides) · [Scope](#scope)

<a id="quick-start"></a>

## Start in three steps

1. **Download and extract everything.** Keep the installer, `contents/` and the other folders together. Do not run inside the ZIP or download one script alone.
2. **Drag in the installer and confirm success.** Save your scene, then drag root **`Install_FBXTo3dsMax.ms`** into the Max viewport. Resolve any installation failure before use.
3. **Open, self-check and try a copy.** Click **FBX 转 MAX / FBX to MAX** on the top toolbar, choose **EN**, and run **Run Self-check**. Start on a scene copy with one receiving mesh and the default **Shape** option.

The plug-in uses Max's bundled Python; normal installation needs no separate interpreter, compiler or administrator access. Root `Uninstall_FBXTo3dsMax.ms` is the removal entry. [Detailed installation and removal →](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/INSTALL.md)

Read [TESTING](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md) for version-specific host results and limits. Package metadata declares Max 2023–2026; **2024–2026 remain untested**.

<a id="language-ui"></a>

## English or Chinese, in the same window

**Language · 中文 / EN** sits beside the mode heading. Switching in place preserves the selected mode, FBX, options and checked state. The two language buttons are mutually exclusive.

![English UI reference from 1.4.25](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/ui/rollout-1.4.25-en.png)

[Open the English image at full size](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/ui/rollout-1.4.25-en.png) · [中文界面原图](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/ui/rollout-1.4.25-cn.png) · [中文操作概览](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/README_中文.md#language-ui)

This is a **real 1.4.25 UI reference** with an empty FBX field, not execution evidence for 1.4.26. Known UI text and user-facing messages follow the selected language; original technical diagnostics are retained when needed.

<a id="workflows"></a>

## Choose the workflow for your edit

The direction is always **FBX supplies data → Max receives it**.

| Your task | Choose | What must hold |
|---|---|---|
| Adjust shape, unwrap UVs, update materials/face IDs, RGB/Alpha or normals | **Mode 1 · Matching Models / Transfer Data** | Keep the receiving Max node and write selected channels. Vertex identity, connectivity, winding and face mapping must correspond uniquely; matching counts alone are insufficient |
| Change topology and combine the FBX mesh/weights with Max scene bones | **Mode 2 · Different Models / Replace / Keep Skin** | Each side needs one qualifying Skin. Bone, weight and binding checks must pass. The old mesh is hidden as a backup by default |

![Original concept diagram: the two modes](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/diagrams/two-modes.svg)

Mode 2 does not copy the old node's hierarchy, transform/animation controllers, constraints or arbitrary modifiers. FBX supplies per-vertex weights; Max supplies scene bones and the binding system. Multi-object replacement requires backups. [Full Skin requirements and failure boundaries →](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-5--replace-a-skinned-mesh-after-topology-changes)

<a id="examples"></a>

## See what comes back to Max

Try the [original canopy exercise](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/examples/README.md): generate your own receiving mesh and edited FBX, then check, transfer Shape + UV 1 and inspect the result. No model download is needed. The generator prepares the scene; it does not run the plug-in. See TESTING for the exact real-host coverage.

### Update shape while keeping the Max node

| Authorized historical example: before | Authorized historical example: after |
|---|---|
| ![Historical shape transfer: before](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/deformation-before.webp) | ![Historical shape transfer: after](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/deformation-after.webp) |
| [Full-size image](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/deformation-before.webp) | [Full-size image](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/deformation-after.webp) |

In Mode 1, selecting only **Shape** updates vertex positions. Leave channels you do not intend to change unchecked. The images show a historical result; screen position does not define which object supplies data. [About 10 seconds of historical result inspection · v1.3.23](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/assets/demos/mode1-deformation-v1.3.23.mp4) · [Follow the shape task](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-1--update-shape-only)

### Select channels independently

| Data to update | Option | What to inspect |
|---|---|---|
| UVs | UV 1 / 2 / 3 | Map channels 1 / 2 / 3 and face-corner mapping; select channels actually present |
| Materials and assignment | Material / ID | Both material objects and each face's material ID |
| Color and masks | Vertex RGB and Alpha separately | RGB is map channel 0; independent Alpha is channel -2, not inferred from brightness |
| Surface continuity and direction | Smoothing Groups / Vertex Normals | SG controls sharing between faces; normals specify face-corner directions |

<details>
<summary>Authorized historical gallery: material IDs, RGB and Alpha</summary>

**Materials and per-face IDs:** inspect actual face assignments, not viewport color alone.

![Authorized historical screenshot: material IDs](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/materials-and-face-ids.webp)

[Open full size](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/materials-and-face-ids.webp)

**RGB and independent Alpha:** inspect both channels separately.

![Authorized historical screenshot: RGB](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/vertex-color-rgb.webp)

[RGB full size](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/vertex-color-rgb.webp)

![Authorized historical screenshot: Alpha](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/vertex-alpha.webp)

[Alpha full size](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/vertex-alpha.webp)

</details>

Historical images and video are authorized, without the underlying model files. Original SVGs explain concepts. UI references, historical results and diagrams have distinct labels. [Media provenance](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/assets/MEDIA.md)

## Built for deliberate model iteration

| Capability | Why it helps |
|---|---|
| **Selective updates** | Transfer UVs without replacing materials; shape is the default channel |
| **Face and corner mapping** | UVs/normals follow face corners; material IDs/SG follow faces |
| **Separate smoothing and normals** | Prefer a valid native FBX smoothing layer; stop when inference constraints cannot be met exactly |
| **Explicit Skin data sources** | Scene bones/binding and FBX weights have separate responsibilities, with readback before and after commit |
| **Inspectable execution** | Preflight, writing, readback and recovery produce reports; a passed check is not a completed transfer |
| **MIT source you can read** | Inspect, modify and redistribute Python/MAXScript while retaining copyright and license |

<details>
<summary>Understand smoothing, custom normals and Skin data sources</summary>

![Original concept diagram: smoothing and normals](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/diagrams/smoothing-and-normals.svg)

SG and custom directions solve different problems. The retained `F2M_顶点法线` modifier is part of the result; do not delete or collapse it. User Edit Normals / Weighted Normal modifiers are not silently cleared.

![Original concept diagram: Skin data sources](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/diagrams/skin-data-authority.svg)

FBX supplies the new mesh, channels and weights. Max supplies scene bone identity, binding local data and envelopes; candidate Mesh Bind is adapted. This is not a promise to copy an entire animation system after arbitrary topology edits.

</details>

<a id="guides"></a>

## Continue with a task

| Task | English | 中文 |
|---|---|---|
| Installation, reinstall and removal | [Install](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/INSTALL.md) | [安装指南](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/INSTALL_中文.md) |
| Shape only | [Task 1](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-1--update-shape-only) | [任务一](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务一只修改形状) |
| UVs, materials and face IDs | [Task 2](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-2--update-uvs-materials-and-face-ids) | [任务二](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务二更新-uv材质与面-id) |
| RGB and Alpha | [Task 3](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-3--transfer-rgb-and-alpha-separately) | [任务三](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务三分别传递-rgb-与-alpha) |
| Smoothing and custom normals | [Task 4](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-4--choose-smoothing-groups-or-custom-normals) | [任务四](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务四选择光滑组或自定义法线) |
| Skin replacement after topology changes | [Task 5](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-5--replace-a-skinned-mesh-after-topology-changes) | [任务五](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务五拓扑改变后替换带-skin-的网格) |
| Data contracts, algorithms and transactions | [Technical reference](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#technical-reference) | [技术参考](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#技术参考) |

<a id="scope"></a>

## Read the result, then verify the asset

**Illustrative interpretation examples, not execution receipts for this version:**

| Report state | What it means for your next step |
|---|---|
| Check passed | Ready to attempt the transfer; no data has been transferred yet |
| Selected UV channel missing and skipped | That channel was not copied; fix the FBX first if you need it |
| Transfer completed | Inspect selected channels, appearance, animation and save/reload |
| Failure / incomplete rollback | Keep your copy and report; resolve the problem before expanding the batch |

Mode 1 uses per-object transactions; a later failure does not undo earlier successful objects. Mode 2 supports batch rollback while backups are retained. Disabling backups for a single object introduces an irreversible deletion boundary. Transfer is synchronous and has no safe mid-transfer cancellation.

[TESTING](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md) records actual environments and coverage by version. Small generated regression scenes do not guarantee complex assets, every failure path or zero unknown bugs. Complete archive bytes are not proof that reinstallation from the archive was exercised.

Reports are under `%LOCALAPPDATA%\FBXTo3dsMax`; installer logs and archives are under `%APPDATA%\Autodesk\FBXTo3dsMaxInstaller`. Remove local paths, model names and project information before public feedback. [Issues](https://github.com/DimmensCK/FBXTo3dsMax/issues) · [Contributing](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/development/CONTRIBUTING.md) · [Changelog](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/development/CHANGELOG_中文.md)

## Open source and offline reading

Installed text is beside the runtime as `README_EN.md`, `INSTALL_EN.md`, `USER_GUIDE_EN.md` and the three Chinese guides. Web images and videos require internet access. The complete task manuals and technical contracts remain available; this page is a starting point.

The repository includes source, tutorials and authorized media. It does **not** distribute private FBX/MAX/BLEND models, the original PDF or internal links. The [main ZIP](https://github.com/DimmensCK/FBXTo3dsMax/archive/refs/heads/main.zip) is a development snapshot; use the fixed release above for your first installation. [GitHub download and maintenance guide](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/GITHUB_发布指南.md)

If it helps your work, a Star makes the project easier to find again.

Copyright © 2026 **Dimmens** · [MIT License](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/LICENSE). Free to use, modify, redistribute and use commercially, with copyright and license retained. Tutorial-media permission does not grant rights to underlying private model files. Autodesk 3ds Max is licensed separately.
