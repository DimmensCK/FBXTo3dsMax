# FBXTo3dsMax 1.4.26 安装与卸载

[English installation](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/INSTALL.md) · [中文概览](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/README_中文.md) · [完整使用手册](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md)

## 三步开始

1. **下载完整发行版并解压。** 使用 [v1.4.26 源码 ZIP](https://github.com/DimmensCK/FBXTo3dsMax/archive/refs/tags/v1.4.26.zip)，或在 [Release 页面](https://github.com/DimmensCK/FBXTo3dsMax/releases/tag/v1.4.26) 的 Assets 中选择 **Source code (zip)**。不要只保存安装器，也不要在 ZIP 内运行。
2. **保存场景，拖入安装器。** 将根目录 **`Install_FBXTo3dsMax.ms`** 拖入 Max 视口，等待并确认成功。安装失败先保留日志、解决问题，不继续使用。
3. **打开、自检、试副本。** 点击顶部 **FBX 转 MAX / FBX to MAX**，使用 **Language · 中文 / EN** 切换语言，运行自检。首次传递从场景副本、单对象和默认“变形”开始。

安装不会自动打开插件窗口。交互安装通常显示结果对话框，静默启动可能将结果写入日志。成功后重启 Max，确认顶部入口仍存在；主工具栏优先，必要时使用停靠备用工具栏。[查看双语界面参考](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/README.md#language-ui)

## 安装前确认

安装器、`PackageContents.xml`、`LICENSE` 与小写 `contents/`、`docs/`、`tests/`、`tools/` 必须来自同一个完整版本。插件使用 Max 自带 Python，通常不需要额外解释器、编译器或管理员权限。

各版本实测结果与限制请读 [TESTING](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md)。包描述声明 Max 2023–2026，**2024–2026 尚未实测**。自检数据在本地用户目录程序生成，源码包不附带 FBX / MAX / BLEND 模型文件。

| 要做什么 | 使用入口 |
|---|---|
| 安装或重复安装同一版本 | 根目录 `Install_FBXTo3dsMax.ms` |
| 卸载并保留恢复归档 | 根目录 `Uninstall_FBXTo3dsMax.ms` |
| 安装后使用 | Max 顶部 **FBX 转 MAX / FBX to MAX** |

直接运行 `contents/FBXTo3dsMax_UI.ms` 只会临时打开界面，不代表安装完成。仓库的 [main ZIP](https://github.com/DimmensCK/FBXTo3dsMax/archive/refs/heads/main.zip) 是开发快照；首次安装优先选择上面的固定发行版。

## 安装位置与语言

正常按用户安装到：

```text
%APPDATA%\Autodesk\ApplicationPlugins\FBXTo3dsMax
```

安装成功后，Max 使用完整的安装副本。**中文 / EN** 两个按钮保持单选，原位切换不必重开窗口；偏好文件为 `%LOCALAPPDATA%\FBXTo3dsMax\language.txt`。本地指南文字可离线阅读，线上图片和视频需要网络。

安装日志、暂存、归档和互斥锁位于：

```text
%APPDATA%\Autodesk\FBXTo3dsMaxInstaller
```

结果对话框给出本次事务的具体路径，请保留失败日志与归档信息。

## 重装、升级与备份

再次拖入同一安装器可重复安装同版本；默认拒绝降级。安装/卸载共用独占锁。安装器先暂存固定资源并校验 SHA-256，归档旧包及受管文件，再切换完整包、读回文件/版本/工具栏状态；失败时尝试恢复。

当前固定源码清单为 **32 个安全、唯一目标**。安装后的 `FBXTo3dsMax.install-manifest.sha256` 记录哈希，其目标集合必须与固定源码清单一致。32 是安装资源数量，不是功能测试数量。不要混用历史加密版清单或旧 27 项源码清单。

无法确认所有权的同名包、Macro 或图标会阻止覆盖；已识别的旧 AutoLoader 脚本会归档并记录原位置，不会静默删除。历史源码工程不在清理范围内。

历史 27 项到当前 32 项的跨版本升级尚未单独实测。归档是可供恢复检查的数据，不是自动还原按钮；保留其清单与日志。归档字节完整不等于已经演练归档复装，也不等于你的日常配置已完成安装、卸载或恢复验收。

## 找不到按钮，或安装失败

先确认完整下载、已经解压，读实际安装结果与日志，再使用标准安装器重装并重启 Max。不要为消除提示而手工删除所有权未知的同名包、Macro、图标或旧 AutoLoader。

问题仍存在时，在 [Issues](https://github.com/DimmensCK/FBXTo3dsMax/issues) 提供 Max 完整版本、插件版本、复现步骤及去隐私日志；不要上传私有模型、本机完整路径或项目资料。开发者须保留 `PackageContents.xml` 中的 `post-start-up scripts parts`，它是 AutoLoader 路由标识。

## 自检与第一次正式传递

内置自检启动专用 `3dsmaxbatch.exe`，使用程序生成的原创场景，不重置当前交互场景。它异步执行并可取消；成功要求六类检查全部通过，且独立进程自然退出 **0**。超时、强制清理、取消或非零退出均失败，不能只看绿色 JSON。

报告位于 `%LOCALAPPDATA%\FBXTo3dsMax\SelfCheck`。先解决失败，再处理正式资产。通过后从副本单对象开始，核对所选通道、外观、动画与保存重载；模式一默认只更新点位置，其他通道按需勾选。

正式传递在 Max 主线程同步执行，目前没有中途安全取消。按任务操作见[完整使用手册](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md)。

## 卸载

将根目录 `Uninstall_FBXTo3dsMax.ms` 拖入 Max，或运行安装副本内的 `contents/Uninstall_FBXTo3dsMax.ms`。卸载器检查所有权，清理受管界面/工具栏/回调，将插件包与受管 Macro/图标归档并记录 SHA-256；失败时尝试恢复。

保留结果所示归档位置，卸载后重启 Max 清除缓存动作。用户场景和保留的恢复归档不会被永久删除。需要手工恢复时先检查完整清单、版本与日志，不能把“有归档”当作已经恢复成功。

## 可选 PowerShell 入口

Max 已打开时，优先用上面的拖入方式。若所有 Max / Batch 进程均已关闭，可在工程根目录用 PowerShell 7 运行：

```powershell
pwsh -NoLogo -NoProfile -File .\tools\Install_FBXTo3dsMax.ps1 -MaxRoot '<Max安装目录绝对路径>'
```

将占位文字换成实际安装目录或 `3dsmax.exe` 的绝对路径。此入口先核文件、版本和 Max 路径，再启动 Max 执行同一个标准 `.ms` 事务；发现已有 Max / Batch 会拒绝，不会结束它们。当前实测与验收工具的例外范围见 [TESTING](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md)，不应把某次有限接受当作所有安装失败的豁免。

## 离线指南

安装副本的 `contents/` 将指南平铺为 `README_中文.md`、`INSTALL_中文.md`、`FBXTo3dsMax_详细说明书.md`、`README_EN.md`、`INSTALL_EN.md`、`USER_GUIDE_EN.md`，并附更新日志。这里的网页链接指向完整教程与媒体；离线时直接打开同目录对应文本即可。
