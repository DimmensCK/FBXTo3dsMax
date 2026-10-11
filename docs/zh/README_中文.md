![FBXTo3dsMax — 把修改带回已有 Max 场景](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/brand/fbx-to-max.svg)

# FBXTo3dsMax 1.4.26 · 中文概览

**在别处修改模型，回到 Max 继续工作。** 将 FBX 的形状、UV、材质、顶点色与法线带回已有 3ds Max 场景。同拓扑按通道更新；拓扑改变时，经过 Skin、骨骼与绑定检查后替换网格。

Dimmens · 免费可读 Python / MAXScript · MIT · 中文 / English

**[下载 v1.4.26 完整源码](https://github.com/DimmensCK/FBXTo3dsMax/archive/refs/tags/v1.4.26.zip)** · [发行说明](https://github.com/DimmensCK/FBXTo3dsMax/releases/tag/v1.4.26) · [安装指南](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/INSTALL_中文.md) · [English overview](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/README.md) · [图文首页](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/README.md)

[三步开始](#quick-start) · [真实界面](#language-ui) · [选择模式](#workflows) · [逐项看功能](#examples) · [任务教程](#guides) · [测试与边界](#scope)

<a id="quick-start"></a>

## 三步开始

1. **完整下载并解压。** 保留安装器、`contents/` 和其余目录，不只保存单个脚本，不在 ZIP 内运行。
2. **拖入安装器，确认成功。** 保存场景，将根目录 **`Install_FBXTo3dsMax.ms`** 拖入 Max 视口。安装失败先解决，不继续使用。
3. **打开、自检、试副本。** 点击顶部 **FBX 转 MAX / FBX to MAX**，选择 **中文 / EN** 并运行自检。首次从场景副本、单对象和默认“变形”开始。

插件使用 Max 自带 Python，通常无需额外解释器、编译器或管理员权限。卸载入口为根目录 `Uninstall_FBXTo3dsMax.ms`。[安装、重复安装与卸载的详细步骤 →](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/INSTALL_中文.md)

<a id="language-ui"></a>

## 中文与 English，在同一窗口切换

![较早1.4.26源码的真实中文界面参考](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/ui/rollout-1.4.26-cn.png)

[查看中文原图](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/ui/rollout-1.4.26-cn.png) · [English UI](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/ui/rollout-1.4.26-en.png)

这是 **较早1.4.26源码在 Max 2023.3.10 中的真实界面参考**，不代替之后新核心修订的验收。**Language · 中文 / EN** 原位切换，保留模式、FBX、选项与检查状态；再次点击当前语言仍保持唯一选中。已知界面/报告标签跟随语言，必要的技术诊断保留原文。

先选 **Max 接收网格**，再选 FBX：方向始终是 **FBX 提供数据 → Max 接收数据**。双方各一个网格可直接配对，其余数量组合要求完整网格名唯一匹配。

<a id="workflows"></a>

## 为这次修改选择模式

| 你要完成的事 | 选择 | 保留与前提 |
|---|---|---|
| 更新形状、UV、材质/逐面ID、RGB/Alpha、SG或法线 | **模式一 · 模型完全一致 / 传递数据** | 保留Max接收节点，只写勾选通道。顶点身份、连接、绕序及面映射须唯一对应；相同数量不够 |
| 采用拓扑改变后的FBX网格/权重，沿用Max场景骨骼 | **模式二 · 模型不一致 / 替换并保留蒙皮** | 双方各有一个合格Skin，骨骼、权重及绑定检查通过；默认隐藏备份旧网格 |

![原创概念图：两模式的数据方向与对象保留](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/diagrams/two-modes.svg)

<a id="examples"></a>

## 逐项看清可以带回什么

下列历史截图均经作者授权，用于展示检查方法；不是当前源码的验收收据，画面左右也不定义谁提供数据。不附带任何底层模型。[媒体来源与范围](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/assets/MEDIA.md)

### 形状：继续使用原 Max 接收节点

| 授权历史示意：传递前 | 传递后 |
|---|---|
| ![历史形状传递前](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/deformation-before.webp) | ![历史形状传递后](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/deformation-after.webp) |

模式一只勾 **变形**，用于保持拓扑身份的比例、轮廓或点位修改。不需要更新的通道保持未勾选。[形状操作步骤](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务一只修改形状) · [约10秒 v1.3.23 历史结果检查视频](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/assets/demos/mode1-deformation-v1.3.23.mp4)

### 在本机生成一个原创练习

| 原创雨棚：传递前 | 真实变形 + UV1 传递后 |
|---|---|
| ![原创雨棚传递前](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/demos/canopy-before-1.4.26.png) | ![原创雨棚传递后](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/demos/canopy-after-1.4.26.png) |

这组1.4.26安装副本的真实演示在 **Max 2023.3.10** 完成，原创网格为 **91顶点、144三角形**。两幅 **960×640** 渲染采用同一相机、棋盘材质与灯光，实际传递变形和UV1并保留接收节点、材质与选择。按[雨棚练习](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/examples/README.md)现场生成数据，再亲自检查、传递；无需下载模型。生成器只准备数据，实机覆盖见TESTING。

### UV 1 / 2 / 3：查看实际贴图通道

![历史UV编辑器检查map channel 2](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/uv-channel-2.webp)

只勾FBX实际存在的UV通道。历史图右下角是 **map channel 2**，可检查UV岛与接缝；传UV1/3时分别切到通道1/3查看。UV按面角映射，支持接缝；勾选通道缺失会报告并跳过。[UV操作步骤](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务二更新-uv材质与面-id)

### 材质与逐面 ID：一起核对分配

![历史材质与逐面ID查看](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/materials-and-face-ids.webp)

勾 **材质与 ID** 可带回材质对象和逐面ID。核对实际材质槽与受影响的面，不能只凭视口颜色判断；仅修UV时不勾此项。[材质与ID步骤](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务二更新-uv材质与面-id)

### RGB 与 Alpha：两个独立通道

| 历史RGB查看 | 历史独立Alpha查看 |
|---|---|
| ![历史顶点RGB](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/vertex-color-rgb.webp) | ![历史顶点Alpha](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/vertex-alpha.webp) |

**顶点色 RGB** 与 **顶点 Alpha** 分别勾选。RGB为 **map channel 0**，Alpha为 **map channel -2**，不由RGB亮度推测。执行后使用对应的视口显示或材质分别核对。[顶点数据步骤](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务三分别传递-rgb-与-alpha)

### 光滑组：查看面之间的共享关系

![历史按平滑组选择查看](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/smoothing-groups.webp)

勾 **光滑组** 更新逐面掩码与软硬关系。优先采用有效FBX原生平滑层；严格推导无法表达的约束会停止。历史图展示按SG选择对应面，不证明任何输入都能求解。[SG选择与检查](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务四选择光滑组或自定义法线)

### 自定义法线：保留想要的面角方向

![历史F2M法线修改器和方向显示](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/custom-normals.webp)

勾 **顶点法线** 传自定义方向；SG也需要来自FBX时两项同时勾选。保留并启用结果中的 **`F2M_顶点法线`**，不要删除或塌陷。方向线颜色表示编辑/选择状态，不表示数据来自谁。[法线步骤与三路行为](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务四选择光滑组或自定义法线)

### 改变拓扑：结合 FBX 权重与 Max 场景骨骼

![原创概念图，不是执行截图：模式二Skin数据来源](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/diagrams/skin-data-authority.svg)

模式二采用 **FBX网格、通道、默认材质与逐顶点权重**，沿用 **Max场景骨骼身份、绑定local data和包络**，候选Mesh Bind自适应建立。双方各需一个合格Skin，提交前核对匹配、权重与绑定。保留隐藏旧备份，并在副本中检查动画与保存重载。

上图是 **原创概念示意**，不是替换操作录像。旧父子层级、Transform/动画控制器、约束与任意修改器不会自动复制。[完整Skin替换步骤](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务五拓扑改变后替换带-skin-的网格)

<a id="guides"></a>

## 按任务继续阅读

| 任务 | 中文 | English |
|---|---|---|
| 安装、重复安装与卸载 | [安装指南](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/INSTALL_中文.md) | [Install](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/INSTALL.md) |
| 只改形状 | [任务一](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务一只修改形状) | [Task 1](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-1--update-shape-only) |
| UV、材质与面ID | [任务二](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务二更新-uv材质与面-id) | [Task 2](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-2--update-uvs-materials-and-face-ids) |
| RGB与Alpha | [任务三](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务三分别传递-rgb-与-alpha) | [Task 3](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-3--transfer-rgb-and-alpha-separately) |
| SG与自定义法线 | [任务四](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务四选择光滑组或自定义法线) | [Task 4](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-4--choose-smoothing-groups-or-custom-normals) |
| 改拓扑后的Skin替换 | [任务五](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务五拓扑改变后替换带-skin-的网格) | [Task 5](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#task-5--replace-a-skinned-mesh-after-topology-changes) |
| 数据合同与事务 | [技术参考](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#技术参考) | [Reference](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md#technical-reference) |

界面默认只勾 **变形**。Python API单独默认 `transfer_uv=True`、`uv_channels=[1]`，脚本调用应显式设置要传的通道。

<a id="scope"></a>

## 先检查，再传递，最后核对结果

“检查通过”表示可以尝试执行，不是传递完成。阅读通道跳过和逐对象失败，再核对结果及副本保存重载。模式一按对象建立事务，后续失败不会自动撤销先前成功对象；模式二保留备份时支持批次回滚，单对象关闭备份存在不可逆删除边界。正式传递同步执行，没有中途安全取消。

[TESTING](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md)记录版本对应的实际执行与限制。已实测宿主为 **Max 2023.3.10**；包描述路由2023–2026，但 **2024–2026未验证**。小型原创回归不能保证全部复杂资产或未知缺陷为零。归档字节完整不等于已经演练复装。

报告位于 `%LOCALAPPDATA%\FBXTo3dsMax`；安装日志/归档位于 `%APPDATA%\Autodesk\FBXTo3dsMaxInstaller`。公开[Issues](https://github.com/DimmensCK/FBXTo3dsMax/issues)前去掉路径、模型名与项目资料。[贡献](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/development/CONTRIBUTING.md) · [更新日志](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/development/CHANGELOG_中文.md)

## 开源与离线指南

安装指南平铺在运行目录，包含`README_中文.md`、`INSTALL_中文.md`、`FBXTo3dsMax_详细说明书.md`和`README_EN.md`、`INSTALL_EN.md`、`USER_GUIDE_EN.md`。文字可本地阅读，图片/视频使用线上仓库链接，需要网络。[main ZIP](https://github.com/DimmensCK/FBXTo3dsMax/archive/refs/heads/main.zip)是开发快照，首次安装选固定发行版。[GitHub下载与维护指南](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/GITHUB_发布指南.md)

Copyright © 2026 **Dimmens** · [MIT](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/LICENSE)。免费使用、修改、再分发及商用须保留版权与许可证。仓库不分发私有FBX/MAX/BLEND、原内部PDF或内部链接；教程媒体授权不授予底层私有模型的使用权。Autodesk 3ds Max需另行取得许可。
