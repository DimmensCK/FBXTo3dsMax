# FBXTo3dsMax 1.4.24 — user guide

[中文教程](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md) · [Installation](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/INSTALL.md) · [Overview](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/README.md)

By Dimmens. This guide defines operation and proof requirements for the readable source edition. Current results and the separate historical 1.3.24 scope are in [testing](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md).

## Data direction and matching

**FBX data → selected Max receiving mesh.** The Chinese UI calls these “Max 源模型” and “FBX 目标模型”; these names do not reverse the data flow. Mode 1 retains the Max node. Mode 2 replaces it with the imported FBX candidate, giving the candidate the old name.

A geometric vertex may belong to several **face corners**. UV and normal data is corner-based; smoothing masks and material IDs are face-based.

One selected Max mesh and one FBX mesh may pair directly. Other combinations match by full mesh name. Duplicate names, missing matches or multiple receivers using the same FBX mesh fail. Bone matching prefers full names and permits only a unique normalized-name fallback.

Group heads/members, frozen nodes, LOD visibility controllers, instances and XRefs are blocked when their state is unsafe. Make an independent scene copy or resolve the unsupported state before checking again.

## First transfer and language

1. Save a scene copy and select the Max receiving mesh.
2. Choose **中文 / English** in **语言 / Language**. Switching updates the open window without losing the selected mode, FBX, options or check state; the choice is saved for future sessions.
3. Select the FBX, choose a mode and the channels you need.
4. Run **Check FBX / Match**. It performs isolated imports and checks, restores names, selection and importer settings, and produces a report.
5. Read the report, then use **Run Transfer**. Check appearance, channels/Skin, animation and save/reload before processing more objects.

Changing the FBX, mode, selection or hidden-object scope requires a new check. Changing only transfer channels does not require another expensive precheck. Every actual transfer still imports and validates the current data again; cached checks do not replace write-time validation.

| Advanced option | Default | Effect |
|---|---|---|
| Hide old mesh as backup | On | Mode 2 retains old meshes for batch rollback |
| Use Max source material | Off | Explicitly replaces the default FBX material with the old Max material |
| Keep import for debug | Off | Retains isolated import nodes during transfer; may enlarge the scene |
| Include hidden objects | On | Includes eligible hidden meshes; changing this requires a new check |

Precheck never retains temporary import nodes. The self-check is asynchronous and cancellable; actual transfer is synchronous and has no safe mid-transfer cancellation.

## Mode 1 — matching topology

**Matching Models / Transfer Data** requires stable vertex identity, equal edge connections and face-corner counts, consistent winding, and a unique mapping for every face. Equal point/face counts alone are insufficient. Reordered faces and same-winding cyclic corner rotations are handled by explicit mappings. Reverse winding, ambiguous duplicate faces and changed connectivity stop the operation.

Hidden triangle-diagonal differences may produce a warning while preserving Max triangulation. If the workflow requires identical triangles, triangulate consistently in the DCC first.

| Channel | Authority and details |
|---|---|
| Shape / positions | FBX point positions, converted through object transforms and read back per point; retains the Max node and user stack |
| UV 1/2/3 | Map channels 1/2/3, with face/corner mappings |
| RGB vertex color | Map channel 0 |
| Vertex alpha | Independent map channel -2; never inferred from RGB |
| Material and IDs | Material object plus each face's material ID |
| Smoothing groups | FBX/strictly solved 32-bit per-face masks |
| Custom normals | FBX Specified/Explicit corner directions |

Positions are the only selected channel by default. Missing selected UV/RGB/alpha channels are warned about and skipped: read the object report to see what actually transferred. Ordinary computed normals are not presented as custom normals.

Write order is positions, material/IDs, UV, SG, RGB, alpha, then normals. Basic channels use snapshots and readback. Necessary temporary ChannelInfo modifiers may only be collapsed safely at the bottom of the stack; persistent normal modifiers are retained.

Mode 1 is transactional **per object**. Failure attempts to restore that object; earlier successful objects are not automatically undone.

### Shape illustration

| Before | After |
|---|---|
| ![Before shape transfer](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/deformation-before.webp) | ![After shape transfer](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/deformation-after.webp) |

Author-authorized historical illustrations. They are not current-version acceptance evidence, and no underlying model files are included. The figures show scene meshes; they do not define a left/right source convention.

[Historical result-inspection clip](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/assets/demos/mode1-deformation-v1.3.23.mp4) — v1.3.23, about 10 seconds. It shows deformation/binding inspection rather than the complete operation; it does not qualify this version.

## Smoothing groups — authority and limits

Each Max face has a 32-bit SG mask and may belong to multiple groups. Adjacent faces whose masks have a nonzero bitwise AND share computed normals. Bit 32 may appear negative in signed int32; this is valid.

A unique, valid native FBX `LayerElementSmoothing` takes priority. Without that layer, normalized corner directions and a **0.01°** equality tolerance establish soft/hard edges and normal fans. Importer-generated normal IDs are not evidence of edge intent.

- **SG only:** two isolated imports; use the Autodesk candidate only after strict validation, otherwise solve the constraints.
- **SG + normals:** a separate Max-bundled-Python worker strictly parses and solves; the main Max process imports once with `SmoothingGroups=false` and verifies the topology summary from the same read.
- The solver first assigns bits to connected soft regions, reuses bits only when constraints permit, and uses multi-bit DSATUR with bounded backtracking when necessary.

Every soft/hard edge and vertex fan is validated. Non-manifold input, one-endpoint soft edges, contradictory direction partitions, genuinely unrepresentable 32-bit conflicts or exhausted search budgets stop the operation. It does not produce an approximate smoothing result.

Without native SG, a hard edge whose two sides happen to have identical directions cannot be inferred from directions alone. Include a native smoothing layer to preserve that intent. SG also cannot express arbitrary weighted or manually locked normal directions; transfer custom normals when required.

## Custom normals — three transfer paths

| Selected channels | Receiver SG | Behavior |
|---|---|---|
| SG only | Any | Removes only stale plug-in-owned normals, writes SG and reads every mask back |
| Normals only | All zero | Fully transfers authoritative normal pool, IDs, Specified/Explicit flags and directions |
| Normals only | Any nonzero mask | Retains SG; compares against the actual receiver's final geometry/SG baseline |
| SG + normals | Any | Writes and reads FBX SG first, then uses that baseline for normal differences |

In the difference path, a corner more than **0.1°** from the actual SG baseline is a semantic residual. Max may require the minimal companion-corner closure sharing a baseline normal ID. Reports distinguish these structural guards from semantic residuals. Every written target is the complete FBX direction, not a direction delta.

This path retains one bottom `F2M_顶点法线` Edit Normals modifier. Even with no residuals, an all-blue Unspecified baseline stays in place so embedded old custom directions cannot reappear. **Do not delete or collapse this modifier.**

User Edit Normals/Weighted Normal modifiers are not silently deleted; detected overriding conflicts stop the operation. Normal-space conversion uses the inverse transpose. SG masks and all final corner directions are read immediately and after forced reevaluation; directions must agree with authoritative FBX within **0.1°**. Green/yellow display colors describe state and selection, not data provenance or correctness.

## Mode 2 — replace mesh and keep skinning

**Different Models / Replace / Keep Skin** requires exactly one Skin on each mesh. Every actual nonzero FBX influence must map uniquely to a Max source Skin bone. Empty weights, ambiguous bones, missing required APIs or inconsistent readback block commit.

| Final content | Source |
|---|---|
| Node, geometry, UV, RGB/alpha, normals, default material and non-Skin data | Imported FBX candidate |
| Scene-bone identities, semantic parameters, Bone Bind/Stretch TM, envelopes and local data | Max source Skin |
| Mesh Bind | Adapted binding created for the candidate by `addModifierWithLocalData` |
| Per-vertex weights, Unnormalized, DQ and global DQ | FBX |

Skin is copied with local data at the original FBX Skin stack position. There is no ordinary-modifier-copy fallback. Each FBX weight row is written once with `ReplaceVertexWeights`, followed by full readback of bindings, bones and vertex state. Writing FBX binding matrices onto a different Max scene skeleton is not supported.

The candidate retains its imported FBX world transform and inherits the old Max layer and node display state. Commit verifies identity, pivot, visibility, every world point and the bounding box. World-point tolerance is `max(0.001 cm, 0.000002 cm + coordinate_scale × 0.000002)`; non-finite input and significant differences fail.

Hidden backup is on by default. Later batch failure deletes committed candidates in reverse order and restores old names/display state. Multiple objects require backup. Disabling backup is allowed only for one object; the old mesh is deleted after candidate validation. A failure after deletion cannot promise lossless recovery.

The mode does **not** clone old parenting, transform/animation controllers, constraints or arbitrary user modifiers. Verify complex rigs on a copy, including world appearance, animation playback and save/reload.

## State restoration and reports

Before native FBX import, the plug-in detaches Modify's current object and switches to Create, verifies it, then changes importer settings. Settings use snapshot, set/get verification, `finally` restoration and readback. Names/selection use node handles; a name fallback must be unique. Temporary nodes are deleted and verified by handle.

| Report | Location |
|---|---|
| Transfers | `%LOCALAPPDATA%\FBXTo3dsMax\Reports` |
| Self-check | `%LOCALAPPDATA%\FBXTo3dsMax\SelfCheck` |
| UI bridge diagnostics | `%LOCALAPPDATA%\FBXTo3dsMax\Diagnostics` |
| Development validation | `%LOCALAPPDATA%\FBXTo3dsMax\Validation` |
| Install/uninstall logs and archives | `%APPDATA%\Autodesk\FBXTo3dsMaxInstaller` |

Precheck success means only that precheck passed. Completion requires writes, readback and temporary-state restoration. Skipped channels, object failures, rolled-back batches or incomplete rollback are not full success. Preserve a scene copy and report when cleanup/rollback is incomplete. Sanitize local paths and model names before a public Issue. User-facing summaries follow the chosen language; raw technical diagnostics may retain their original language.

## Self-check and troubleshooting

Self-check launches a dedicated Max Batch and covers six categories: files/version/loading source, pure algorithms, procedural Max mesh/stack, normal space/protection/rollback, synthetic matching-topology FBX, and synthetic Skin replacement. `f2m_test_fixtures.py` generates original small topology/UV/normal/native-SG data; `f2m_selfcheck.py` builds and exports a simple two-bone Skin scene in Max. Exporter settings are restored, and generated data stays in local user storage.

It does not reset the interactive scene. All six categories plus natural exit **0** are required. Timeout, cancel, nonzero exit and forced cleanup fail. These small regressions do not inherit historical private-model scale or performance coverage and do not replace installation, cold-start or your own scene-copy acceptance.

Historical real-host validation used Max 2023.3.10 / Python 3.9.7 on Windows 11 x64. XML declares 2023–2026; 2024–2026 are unverified. Consult the testing document for current-version evidence.

| Symptom | First checks |
|---|---|
| No toolbar button | Complete extraction, installation result/log and restart |
| Check must be repeated | Changed FBX, mode, selection or hidden scope |
| Equal counts but topology fails | Vertex identity, winding, connectivity and duplicate faces |
| SG cannot be solved | Native layer, directions, non-manifold input and 32-bit constraints |
| Unexpected shading | Need for custom normals and overriding modifiers |
| Skin replacement stops | Exactly one Skin per mesh, unique bones and complete weight/binding readback |
| Self-check fails | Report, internal diagnostics and natural exit; a green JSON alone is insufficient |

Use an original generated minimal scene when reporting a problem; no formal project assets are needed. The installed offline guide is `USER_GUIDE_EN.md`, beside `README_EN.md` and `INSTALL_EN.md`.

## Common misconceptions

- An installation transaction failure is not safe to ignore. Keep the log and resolve it before use.
- Equal mesh counts do not prove matching topology; identity, connectivity, winding and unique mapping matter.
- Non-manifold meshes are not a smoothing-stability recommendation; unsupported constraints fail closed.
- Keeping Skin does not promise arbitrary editing is lossless or copy the whole old rig. The Skin/bone/weight/binding requirements still apply.
- Normal display colors do not prove data authority. Verify directions and flags; only temporarily toggle F2M for comparison on a test copy, without deleting/collapsing it.
- No specific companion exporter plug-in is mandatory. Exported FBX must satisfy the mesh/channel/Skin contracts in this guide.
