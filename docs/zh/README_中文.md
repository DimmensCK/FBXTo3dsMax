# FBXTo3dsMax 1.4.24

**把 FBX 的修改带回已有的 Max 场景。** 作者 **Dimmens** · 免费可读源码 · [MIT](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/LICENSE)

[English](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/README.md) · [安装](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/INSTALL_中文.md) · [使用教程](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md) · [仓库](https://github.com/DimmensCK/FBXTo3dsMax)

本版增加中文/English 切换并整理目录。本页定义操作和证明标准，当前测试状态见[测试说明](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md)；1.3.24 的历史通过结果不自动证明后续版本。

数据方向是 **Max 接收网格 ← FBX 提供的数据**。中文界面沿用“Max 源模型”“FBX 目标模型”：Max 源模型是你选中的接收对象，FBX 目标模型是数据提供方。

## 两种模式

| 模式 | 适用情况 | 结果 |
|---|---|---|
| 模型完全一致 / 传递数据 | 顶点身份、边、面及绕序可严格对应 | 保留原 Max 节点，写入勾选的通道 |
| 模型不一致 / 替换并保留蒙皮 | FBX 拓扑改变，双方都有 Skin | FBX 网格替换旧网格，使用 Max 场景骨骼与绑定，采用 FBX 权重 |

模式一支持变形/点位置、UV 1/2/3、光滑组、自定义法线、RGB、Alpha、材质及逐面 ID。默认只勾选“变形”。相同点数、面数不够；反向绕序、顶点身份变化或匹配歧义会停止。

模式二默认保留 FBX 的网格、通道、法线与材质。Max Skin 提供场景骨骼和完整 local data，FBX 提供逐顶点权重、Unnormalized、DQ 与全局 DQ。写入后全量读回。隐藏旧网格备份默认开启，旧材质兼容选项默认关闭。

模式二不复制旧节点父子层级、变换/动画控制器、约束或任意修改器栈。不要把“保留蒙皮”理解为复制整个旧角色场景。

[历史演示：变形结果与绑定检查](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/assets/demos/mode1-deformation-v1.3.23.mp4)（v1.3.23，约 10 秒）。仅是结果片段，不证明新版或完整操作流程，不附带模型。

## 安装与第一次使用

1. 下载完整仓库，解压并保持 `contents/`、`docs/`、`tests/`、`tools/` 的相对结构。
2. 打开 Max，将根目录 **`Install_FBXTo3dsMax.ms`** 拖入视口。
3. 确认成功后点击顶部 **FBX 转 MAX / FBX to MAX**。
4. 用 **语言 / Language** 选择 **中文 / English**，运行插件自检并阅读报告。
5. 在场景副本中先选一个 Max 接收网格，选择 FBX、模式与通道。
6. 点击 **检查 FBX/匹配 / Check FBX / Match**，读报告，再 **开始执行 / Run Transfer**。
7. 核对视觉、通道、Skin、动画及保存重载结果，再扩大处理范围。

插件使用 Max 自带 Python，日常安装不需要另装 Python、编译器或管理员权限。语言切换原位更新，不重建窗口，不丢失模式、FBX、选项和检查状态；选择会保存在本地。原始技术诊断可能保留原语种。

## 光滑组与法线

| 选择 | 行为 |
|---|---|
| 只传光滑组 | 保留/严格求解 FBX 软硬边界，清理插件自己的旧法线 |
| 只传法线，接收端 SG 全 0 | 完整精确传递 FBX 自定义法线 |
| 只传法线，接收端 SG 非零 | 保留现有 SG，写入相对实际 SG 基线超过 `0.1°` 的方向差异 |
| 同时传两者 | 先写/读 FBX SG，再传法线差异 |

用户自己的法线修改器不会被静默删除；覆盖冲突会停止。不要删除或塌陷 `F2M_顶点法线`。绿色/黄色显示不证明数据来源；正确性以方向和标志读回为准。完整解释见使用教程。

## 验证与限制

历史实测环境是 **Windows 11 x64、Max 2023.3.10、内置 Python 3.9.7**。XML 声明 Max 2023–2026，**2024–2026 尚未验证**；当前结果与历史范围在测试说明中分开记录。

模式一按对象事务处理，后续失败不会自动撤销之前成功的对象。模式二保留旧网格时支持批次回滚；关闭备份只允许单对象，删除后存在不可逆边界。正式传递同步运行，没有中途安全取消。

自检在独立 Max Batch 中使用原创小型生成数据，不重置当前场景。所有类别通过且自然退出 0 才能成功。自检不能证明复杂资产、性能或未知缺陷都已覆盖。

## 文件、报告与许可

根目录保留安装、卸载、README、许可证和包入口；`contents/` 放运行源码/资源，`docs/zh/` 与 `docs/en/` 放用户文档，`docs/development/` 放维护记录，`tests/` 与 `tools/` 放开发验证入口。

传递、自检与诊断写到 `%LOCALAPPDATA%\FBXTo3dsMax`。安装归档写到 `%APPDATA%\Autodesk\FBXTo3dsMaxInstaller`。仓库不携带 FBX、MAX 或 BLEND；程序在本地生成自检素材。历史授权截图仅作功能示意，不分发其模型文件。

[更新日志](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/development/CHANGELOG_中文.md) · [贡献](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/development/CONTRIBUTING.md) · [GitHub 下载与维护](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/GITHUB_发布指南.md)

安装副本同目录提供 `README_中文.md`、`INSTALL_中文.md`、`FBXTo3dsMax_详细说明书.md`，英文文件为 `README_EN.md`、`INSTALL_EN.md`、`USER_GUIDE_EN.md`。上方网页导航指向维护中的仓库教程。

MIT 允许使用、修改、分发和商用，须保留版权与许可文本；私有/前雇主模型不在许可或分发范围。Autodesk 3ds Max 由 Autodesk 单独提供。
