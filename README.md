# FBXTo3dsMax

A free, open source 3ds Max plug-in by **Dimmens**. It transfers FBX data exported from Blender, Maya, and other DCC tools to models in an existing Max scene.

**Version:** 1.3.24 · **License:** [MIT](LICENSE) · **Interface:** Chinese

**Validation (2026-10-09):** local source acceptance completed on Max 2023.3.10: 231/231 pure tests, 6/6 source and installed-copy self-checks, fresh/repeat installation, cold start, one post-activation rollback and recoverable uninstall. UI checks used programmatic button clicks. Source and updates: [GitHub](https://github.com/DimmensCK/FBXTo3dsMax). See [testing](docs/TESTING.md) for the evidence scope and remaining limits.

[中文说明](README_中文.md) · [Installation / 安装](INSTALL_中文.md) · [Usage reference / 使用参考](FBXTo3dsMax_详细说明书.md)

## Two workflows

| Mode | Use it when | Result |
|---|---|---|
| 1 — Transfer data | The meshes have verified matching topology | Keeps the selected Max node and transfers the chosen channels |
| 2 — Replace mesh and retain skinning | The FBX topology has changed and both meshes have Skin | Uses the FBX mesh with the existing Max scene bones and binding data |

Mode 1 supports vertex positions, UV channels 1–3, smoothing groups, custom normals, RGB vertex colors, vertex alpha, materials, and face material IDs. Matching vertex/face counts alone are insufficient; the plug-in validates vertex identity, edges, winding, and face-corner correspondence.

Mode 2 keeps FBX geometry, channels, custom normals, and materials by default. It copies the Max source Skin with local binding data, then writes and verifies the FBX vertex weights and DQ state. Keeping a hidden backup of the old mesh is enabled by default.

## Install and use

1. Download or clone the **complete repository**, then extract it if necessary. Keep the file structure intact.
2. Open 3ds Max and drag `Install_FBXTo3dsMax.ms` from the repository root into the viewport.
3. After installation succeeds, click **FBX 转 MAX** on the top toolbar.
4. Run the built-in self-check, then try the first transfer on a **copy of your scene**.
5. Select the Max receiving mesh, choose the FBX and mode, click **检查 FBX/匹配**, read the report, then click **开始执行**.

The plug-in uses Max's bundled Python. No separate Python installation, compiler, encrypted payload, or administrator access is required for normal installation.

The installer stages and verifies files with SHA-256, archives the previous installation, switches the complete package, reads it back, and rolls back on failure. `Uninstall_FBXTo3dsMax.ms` archives the installation rather than permanently deleting it. See the [installation guide](INSTALL_中文.md).

## Compatibility and limits

The recorded real-host validation environment is **Windows 11 x64, 3ds Max 2023.3.10, bundled Python 3.9.7**. The source package's XML declares Max 2023–2026; **Max 2024–2026 have not been validated**. A version declaration is not a compatibility guarantee.

Mode 1 uses per-object transactions; it does not roll back earlier successful objects if a later object fails. Mode 2 supports batch rollback when the old meshes are retained. Single-object deletion has an irreversible boundary. Mode 2 does not copy the old node's parenting, transform/animation controllers, or arbitrary modifier stack.

Self-checks cover known regressions and data generated procedurally at runtime. They cannot establish that every asset or unknown bug is covered. See [testing](docs/TESTING.md) and the [usage reference](FBXTo3dsMax_详细说明书.md).

## Reports and development

Runtime reports are saved under `%LOCALAPPDATA%\FBXTo3dsMax`, outside the source and installed-code directories. Installer archives and logs are under `%APPDATA%\Autodesk\FBXTo3dsMaxInstaller`.

The repository contains readable Python/MAXScript source, installer resources, maintained test source, and an original procedural test-data generator. During self-check, `f2m_test_fixtures.py` provides original topology/native-smoothing data, and `f2m_selfcheck.py` builds and exports a simple two-bone Skin scene. Generated files stay under the local user-data directory. The repository ships no FBX, MAX, or BLEND model files. Historical protected builds, toolchains, private/employer assets, and local verification output are excluded.

For tests and contributions, see [TESTING.md](docs/TESTING.md) and [CONTRIBUTING.md](CONTRIBUTING.md). For a first GitHub publication, see the [Chinese walkthrough](docs/GITHUB_发布指南.md).

## License

Copyright © 2026 Dimmens. Released under the [MIT License](LICENSE). You may use, modify, redistribute, and use it commercially while retaining the copyright and license notices. This source distribution includes only the project code and original procedurally generated test data; it grants no rights to private or employer-owned assets. Autodesk 3ds Max is a separate product and is not included.
