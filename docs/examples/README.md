# 原创雨棚练习 / Original canopy exercise

无需下载模型。这里的脚本用公开的数学公式创建一个雨棚网格，并将编辑后的形状与 UV1 写入本地 FBX。全部几何均为本项目原创；仓库只分发生成代码。

No model download is needed. The script creates a canopy from published numerical formulas and writes its edited shape and UV1 into a local FBX. All geometry is original to this project; the repository distributes generation code only.

## 中文

1. 安装插件后，在 3ds Max 中打开一个**新的空场景**。脚本发现已有物体会停止，不会重置或清空场景。
2. 将本目录的 `Create_Demo.ms` 拖入 Max 视口，或通过 **Scripting → Run Script** 运行它。保持它与 `create_demo_scene.py` 在同一目录。
3. 脚本生成并选中 `F2M_Demo_Canopy`。按 **F11** 查看 Listener，复制打印的 `FBX:` 路径；输出位于本机用户数据的 `FBXTo3dsMax/Demos` 下。
4. 打开插件，选择**模式一**，选择该 FBX，只勾选**变形**与 **UV 1**，其余通道不勾选。先检查，再执行传递。
5. 查看雨棚起伏和 UV 的变化。接收物体应仍为同一个节点、同一个名称与材质，保持 **91个顶点、144个三角形**。可打开 UV 编辑器观察 UV 从原来0–0.6范围展开到0–1范围。

脚本仅准备练习，不代替插件执行。原始与编辑后的数值、FBX哈希及准备状态写在输出目录的 `recipe.json` 和 `prepared.json`；`SCENE_PREPARED_NOT_TRANSFERRED` 只表示准备完成。具体版本与实机验证范围见 [测试记录](../TESTING.md)。每次运行使用新目录，不覆盖旧练习。不需要改变系统单位、FBX导入偏好或保存任何生产模型。

## English

1. After installing the plug-in, open a **new empty scene** in 3ds Max. The script stops if objects already exist; it never resets or clears a scene.
2. Drag `Create_Demo.ms` into a Max viewport, or run it through **Scripting → Run Script**. Keep `create_demo_scene.py` beside it.
3. The script creates and selects `F2M_Demo_Canopy`. Press **F11** for the Listener and copy the printed `FBX:` path. Outputs stay under `FBXTo3dsMax/Demos` in local user data.
4. Open the plug-in, choose **Mode 1**, select that FBX and check only **Shape** and **UV 1**. Leave the other channels unchecked. Check first, then run the transfer.
5. Inspect the changed canopy and UVs. The receiving mesh should retain its node identity, name and material, with **91 vertices and 144 triangles**. In the UV editor, its original 0–0.6 UV range expands to 0–1.

The script prepares the exercise; the plug-in performs the transfer. `recipe.json` records the original/edited data and FBX hash. `prepared.json` uses `SCENE_PREPARED_NOT_TRANSFERRED` to distinguish preparation from a completed transfer. See [test evidence](../TESTING.md) for the exact tested version and host scope. Every run gets a fresh directory, preserving earlier exercises. No system-unit, FBX-preference or production-model changes are needed.
