# FBXTo3dsMax 1.4.26 · 中文快速概览

**把修改后的 FBX 数据带回已有 Max 场景：同拓扑按通道更新，异拓扑经过 Skin 检查后替换网格。**

Dimmens · 可读 Python / MAXScript · MIT · 中文 / English

[English overview](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/README.md) · [图文首页](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/README.md) · **[下载完整发行版](https://github.com/DimmensCK/FBXTo3dsMax/archive/refs/tags/v1.4.26.zip)** · [发行说明](https://github.com/DimmensCK/FBXTo3dsMax/releases/tag/v1.4.26)

## 第一次使用，从这里开始

1. **完整解压**，保留根目录安装器与 `contents/` 等目录。
2. 保存场景，将 **`Install_FBXTo3dsMax.ms`** 拖入 Max 视口，确认安装成功。
3. 点击顶部 **FBX 转 MAX / FBX to MAX**，在 **Language · 中文 / EN** 选语言并运行自检。首次用场景副本、单对象、默认“变形”。

[完整安装、重装与卸载步骤](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/INSTALL_中文.md)。通常无需额外 Python、编译器或管理员权限。安装失败先解决，不忽略错误继续使用。

<a id="language-ui"></a>

## 窗口与数据方向

![1.4.25中文真实界面参考](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/ui/rollout-1.4.25-cn.png)

[查看原图](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/assets/ui/rollout-1.4.25-cn.png) · [English UI](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/README.md#language-ui)

这是 **1.4.25实机界面参考**，不是1.4.26运行证明。语言按钮原位切换，保留模式、FBX、选项和检查状态；必要的技术诊断保留原文。

先选 **Max 接收网格**，再选 FBX。数据始终 **FBX → Max**；一个网格可直接配对，多对象按完整网格名称匹配。

## 用哪个模式

| | 模式一：模型完全一致 / 传递数据 | 模式二：模型不一致 / 替换并保留蒙皮 |
|---|---|---|
| 适合 | 形状、UV、材质/ID、RGB/Alpha、SG/法线更新 | 改拓扑后采用FBX网格与权重，沿用Max场景骨骼/绑定系统 |
| 保留/替换 | 保留Max接收节点，只写勾选数据 | 用通过验证的FBX候选替换旧网格，默认隐藏备份旧网格 |
| 前提 | 顶点身份、连接、绕序及面映射唯一；相同数量不够 | 双方各一个Skin，骨骼、权重与绑定读回通过 |
| 主要边界 | 逐对象事务；后续失败不自动撤销先前成功对象 | 不复制旧父子关系、动画控制器/约束或任意修改器；多对象须备份 |

![原创示意：两模式与数据来源](https://raw.githubusercontent.com/DimmensCK/FBXTo3dsMax/main/docs/assets/diagrams/two-modes.svg)

## 按你的任务继续

| 你要完成的事 | 设置与教程 |
|---|---|
| 只改轮廓/比例 | 默认只勾变形；[任务一](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务一只修改形状) |
| 更新UV，不动材质 | 取消变形，只选UV1/2/3；[任务二](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务二更新-uv材质与面-id) |
| 更新材质与逐面分配 | 勾材质与ID，检查实际面；[任务二](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务二更新-uv材质与面-id) |
| 传回顶点色/独立Alpha | RGB通道0、Alpha通道-2分别选择；[任务三](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务三分别传递-rgb-与-alpha) |
| 还原明暗关系 | 分清SG与自定义方向，保留F2M法线修改器；[任务四](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务四选择光滑组或自定义法线) |
| 替换带Skin的网格 | FBX提供权重，Max提供场景骨骼/绑定；[任务五](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#任务五拓扑改变后替换带-skin-的网格) |

这些通道按顶点、面角和面分别处理；每次实际执行仍重新验证，旧预检不会代替写入读回。[数据合同、法线三路与事务完整参考](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md#技术参考)

## 看示例、读报告

试做[原创雨棚练习](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/examples/README.md)：现场生成接收网格和编辑后的 FBX，先检查，再传递变形与 UV 1，并核对结果。无需下载模型。生成器只准备场景，不代替插件执行；实机覆盖以 TESTING 为准。

[授权历史画廊与版本说明](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/README.md#examples)展示形状、材质、RGB/Alpha；1.3.23历史视频仅检查结果。[媒体来源](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/assets/MEDIA.md)

**说明性判读示例，不是本版实测收据：** 检查通过表示可以执行；所选通道缺失并跳过表示没有复制；执行完成后仍核对外观、通道与保存重载；失败/回滚不完整时保留副本和报告，先解决再扩大操作。

## 测试范围与问题反馈

对应版本的宿主、自检和安装结果以[TESTING](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md)为准。包描述声明2023–2026，**Max2024–2026未实测**。小型程序自检不保证全部复杂资产或未知缺陷为零；卸载归档字节校验不等于演练复装。正式传递同步执行，没有中途安全取消。

报告：`%LOCALAPPDATA%\FBXTo3dsMax`；安装日志/归档：`%APPDATA%\Autodesk\FBXTo3dsMaxInstaller`。公开反馈先去掉路径、模型名与项目资料。[Issues](https://github.com/DimmensCK/FBXTo3dsMax/issues) · [更新日志](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/development/CHANGELOG_中文.md) · [贡献](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/development/CONTRIBUTING.md)

## 开源与本地指南

安装副本的本篇为`contents/README_中文.md`，旁边有`INSTALL_中文.md`、`FBXTo3dsMax_详细说明书.md`及`README_EN.md`、`INSTALL_EN.md`、`USER_GUIDE_EN.md`。文字本地可读，网页图片/视频需要网络。main ZIP是开发快照，首次安装推荐固定发行版；[GitHub下载与维护](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/GITHUB_发布指南.md)。

免费MIT源码，保留Dimmens署名与许可证。仓库不分发私有FBX/MAX/BLEND、原PDF或内部链接；教程媒体授权不包含底层私有模型权利。[MIT](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/LICENSE)。如果有帮助，欢迎Star以便下次找到。
