![FBXTo3dsMax：把 FBX 修改带回已有 Max 场景](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/brand/fbx-to-max.svg)

# FBXTo3dsMax

### 在别处修改模型，回到 Max 继续工作。

**把 FBX 的形状、UV、材质、顶点色与法线带回已有的 3ds Max 场景；拓扑改变时，按严格条件替换网格并沿用场景骨骼与绑定系统。**

由 **Dimmens** 开发 · 免费可读 Python / MAXScript 源码 · **MIT** · **中文 / English**

[English](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/README.md) · [立即安装](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/INSTALL_中文.md) · [完整使用教程](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md) · [下载源码](https://github.com/DimmensCK/FBXTo3dsMax/archive/refs/heads/main.zip)

本页描述 **1.4.25** 的操作与设计。各版本实测结果见[测试说明](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md)；**1.4.24 的历史结果不替代 1.4.25 验收**。

## 1 · 它解决什么问题？

你已经在 Max 中完成了场景组织、材质或蒙皮，随后又在建模工具中调整了模型。每次重新导入，不想重新整理整个场景，也不想凭肉眼猜测哪些数据正确。

FBXTo3dsMax 把这件事拆成两条明确的工作流：**拓扑不变，选择性传回数据；拓扑改变，检查后替换带 Skin 的网格。** 数据始终是 **FBX → Max 接收模型**。

| 你的任务 | 可以尝试的工作流 |
|---|---|
| 调比例、修形状，继续使用原 Max 节点 | 模式一，只勾“变形” |
| 重做 UV、材质面分配、RGB 或 Alpha | 模式一，只勾需要的通道 |
| 带回光滑组和手工调整的法线 | 模式一，按需求选择 SG / 顶点法线 |
| 改变拓扑，仍需要 Max 场景中的骨骼系统 | 模式二；双方必须有合格 Skin 与可匹配骨骼 |

## 2 · 选对模式

![两种工作流与数据方向](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/diagrams/two-modes.svg)

| | 模式一：模型完全一致 / 传递数据 | 模式二：模型不一致 / 替换并保留蒙皮 |
|---|---|---|
| 基本条件 | 顶点身份、连接和绕序能唯一对应 | 双方网格各有一个 Skin，骨骼、权重和绑定检查通过 |
| 网格处理 | 保留 Max 接收节点，写入勾选数据 | 用 FBX 候选替换旧网格 |
| 蒙皮数据 | 不用新网格替代原节点 | Max 提供场景骨骼/绑定系统，FBX 提供权重 |
| 默认保护 | 每个对象写前快照、写后读回 | 隐藏备份旧网格；保留备份时支持批次回滚 |
| 必须知道 | 点数、面数相同并不够 | 不复制旧节点的父子层级、动画控制器或任意修改器栈 |

## 3 · 真正有用的地方

| 能力 | 对实际工作的意义 |
|---|---|
| **按通道选择** | 只更新这次确实修改的内容，例如保留材质，只传 UV；默认只传变形 |
| **面角级映射** | UV 与法线按面角处理，材质 ID 与光滑组按面处理，避免把不同层级的数据混为一谈 |
| **严格光滑与法线路径** | 优先有效原生 FBX 平滑层；需要推导时检查软硬边约束，不能严格表达就停止 |
| **蒙皮来源分清楚** | 不把另一套 FBX 绑定矩阵直接盖到场景骨架上；绑定、权重与骨骼身份逐项读回 |
| **检查、写入、恢复都有报告** | 预检不是最终成功；实际执行重新验证，恢复选择、名称和 FBX 导入器设置 |
| **源码直接可读** | 使用 Max 自带 Python，通常无需管理员权限、额外 Python 或编译器；可按 MIT 修改与再分发 |

这些是设计能力与检查机制，不是“任何模型无损”“零缺陷”或性能领先的承诺。

## 4 · 一个工具，处理这些数据

![原创示意：点、面角、面与独立数据通道](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/diagrams/channel-map.svg)

### 形状：让修改回到原场景

| 历史示意：传递前 | 历史示意：传递后 |
|---|---|
| ![历史形状传递前](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/deformation-before.webp) | ![历史形状传递后](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/deformation-after.webp) |

模式一传递点位置，保留 Max 接收节点与用户栈。图片只展示历史功能效果，不规定画面左右哪边固定是 FBX 或 Max。

[观看约 10 秒历史结果检查：变形与绑定（v1.3.23）](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/assets/demos/mode1-deformation-v1.3.23.mp4)。片段没有展示完整操作，不是新版验收录像。

### 材质与面 ID：一起传回分配关系

![授权历史截图：材质和逐面 ID 的查看](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/materials-and-face-ids.webp)

勾选“材质与 ID”，传递材质对象和每个面的材质 ID。单看物体颜色不能证明逐面 ID 一致，应在 Max 中检查相应面和材质槽。

### UV：按面角传递 1 / 2 / 3 通道

UV 的几何顶点共享关系与网格顶点并非一一对应。插件按面与角映射 **map channel 1、2、3**；只勾选这次修改的 UV。缺失的勾选通道会提示并跳过，不能把“跳过”当成已经复制。

### 顶点色：RGB 与 Alpha 分开控制

![授权历史截图：RGB 顶点色的显示检查](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/vertex-color-rgb.webp)

**RGB 对应 map channel 0。** 材质、照明和视口显示会影响看到的颜色；检查时也要查看实际通道。

![授权历史截图：独立顶点 Alpha 的查看](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/tutorial/vertex-alpha.webp)

**Alpha 对应独立 map channel -2。** 它不是由 RGB 亮度猜出的透明度。RGB 与 Alpha 可分别勾选、分别读回。

以上五张截图均为作者授权的**历史教程画面**，不是 1.4.25 操作截图；不随附模型文件。原创 SVG 仅解释概念，不冒充软件截图。[媒体来源与使用范围](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/assets/MEDIA.md)

## 5 · 第一次传递，照这五步做

1. **完整下载、解压。** 到[仓库](https://github.com/DimmensCK/FBXTo3dsMax)选择 **Code → Download ZIP**，保留完整目录；不要只下载安装脚本。
2. **安装并确认成功。** 将根目录 `Install_FBXTo3dsMax.ms` 拖入 Max 视口。失败就先看日志，不跳过错误。
3. **打开并选语言。** 点击顶部 **FBX 转 MAX / FBX to MAX**；点击 **Language** 旁的 **中文** 或 **EN（英文）**，运行自检。
4. **从副本和单对象开始。** 选择 Max 接收网格、FBX、模式与通道；默认仅“变形”。
5. **先检查，再执行，再核对。** 点击 **检查 FBX/匹配 / Check FBX / Match**，读报告后 **开始执行 / Run Transfer**；检查外观、通道、动画和保存重载。

[安装与卸载的完整步骤](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/INSTALL_中文.md) · [按任务操作的完整教程](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md)

## 6 · 光滑组与自定义法线，分工不同

![原创示意：光滑组关系与面角法线方向](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/diagrams/smoothing-and-normals.svg)

- **光滑组（SG）** 描述面之间如何共享计算法线。一个面可以同时属于多个组。
- **自定义法线** 给出面角的实际方向。仅传 SG 不一定能表达手工法线或 Weighted Normal 的效果。
- 有唯一有效的 FBX 原生平滑层时优先使用；没有时才按方向关系严格推导，非流形或矛盾约束等会停止。
- 同时选择 SG 和法线时，先写并读回 SG，再处理法线。不要删除或塌陷插件保留的 `F2M_顶点法线`。

颜色并不证明法线来自哪一方；以方向、状态和报告读回为准。[法线三路行为与限制](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md)

## 7 · 拓扑改变后，“保留蒙皮”到底保留什么？

![原创示意：模式二网格、权重与绑定的来源](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/diagrams/skin-data-authority.svg)

**FBX 提供新网格和逐顶点权重；Max 提供原场景骨骼身份、绑定 local data、包络等数据。** 新候选的 Mesh Bind 经过自适应建立，随后全量读回。

双方各有一个 Skin、实际权重影响能唯一映射到 Max 骨骼，才允许提交。默认隐藏旧网格备份；多个对象必须保留备份。关闭备份只允许单对象，删除旧网格后存在不可逆边界。

这不是任意改拓扑后完整复制旧动画系统的工具。旧父子层级、Transform/动画控制器、约束与任意修改器不会自动迁移。复杂绑定请在副本里播放动画并保存重载。[模式二完整合同](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md)

## 8 · 中文与 English，用同一套工作流

模式标题右侧提供紧凑的 **Language · 中文 / EN** 按钮，**EN** 即英文。两个按钮保持单选，点击已选语言不会取消选择。切换原位更新，不关闭重建窗口，也不清空模式、FBX、选项或检查状态；选择保存供后续使用。

[仓库中的语言界面说明](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/README.md#language-ui)。本地安装包含本页文字；图片、视频和网页导航指向在线仓库，需要网络。

| 中文按钮 | English |
|---|---|
| 模型完全一致 / 传递数据 | Matching Models / Transfer Data |
| 模型不一致 / 替换并保留蒙皮 | Different Models / Replace / Keep Skin |
| 检查 FBX/匹配 | Check FBX / Match |
| 开始执行 | Run Transfer |
| 运行插件自检 | Run Self-check |

已知界面标签与用户提示跟随语言。原始技术诊断可能保留原文，JSON 的检查名称和摘要协议不因显示语言而改变；不承诺所有诊断全文英文。

## 9 · 使用前知道这些边界

历史实测环境为 **Windows 11 x64、Max 2023.3.10、内置 Python 3.9.7**。包描述声明 Max 2023–2026，**2024–2026 尚未实测**。当前版以[测试说明](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md)为准；旧27项版本到32项版本的升级流程未单独验证。

模式一是**逐对象事务**，后续对象失败不会自动撤销先前成功的对象。模式二保留旧网格时支持批次回滚，单一故障回归不等于穷尽所有故障。卸载保留归档，归档字节校验不等于已实际从归档复装。

自检使用原创小型程序场景，不能替代复杂资产、性能测试或你自己的场景副本验收。正式传递同步执行，没有中途安全取消。

报告在 `%LOCALAPPDATA%\FBXTo3dsMax`；安装备份在 `%APPDATA%\Autodesk\FBXTo3dsMaxInstaller`。公开反馈前去掉本地路径、模型名称与项目资料。

## 10 · 文档、反馈与源码

| 想做什么 | 从这里开始 |
|---|---|
| 安装、重复安装、卸载 | [中文安装说明](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/INSTALL_中文.md) / [English installation](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/INSTALL.md) |
| 按任务使用、理解数据与失败处理 | [中文完整教程](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md) / [English user guide](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/USER_GUIDE.md) |
| 看版本实际测了什么 | [测试范围](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md) · [更新日志](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/development/CHANGELOG_中文.md) |
| 提问题、改源码 | [Issues](https://github.com/DimmensCK/FBXTo3dsMax/issues) · [贡献说明](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/development/CONTRIBUTING.md) |
| 初次使用 GitHub、后续维护 | [GitHub 下载与维护指南](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/GITHUB_发布指南.md) |

仓库提供源码、文档、授权教程画面与程序生成回归代码，**不分发 FBX / MAX / BLEND 模型文件、原始 PDF 或内部资料链接**。

Copyright © 2026 **Dimmens** · [MIT License](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/LICENSE)。免费使用、修改、再分发及商用，须保留版权和许可证。教程画面按作者授权用于文档；不授予底层私有模型的使用权。Autodesk 3ds Max 需另行取得。
