# FBXTo3dsMax 1.4.25 安装说明

[English installation](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/en/INSTALL.md) · [概览](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/README_中文.md) · [使用教程](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md)

这是 **1.4.25 可读源码版**的安装与卸载说明，标准入口是根目录 `Install_FBXTo3dsMax.ms`。各版本实际验收见[测试说明](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md)；1.4.24 与 1.3.24 的历史结果不自动证明 1.4.25。

## 先分清三个入口

| 你要做什么 | 使用入口 |
|---|---|
| 正常安装或同版本重新安装 | 根目录 `Install_FBXTo3dsMax.ms` |
| 正常卸载并保留恢复归档 | 根目录 `Uninstall_FBXTo3dsMax.ms` |
| 已安装后开始工作 | Max 顶部 **FBX 转 MAX / FBX to MAX** |

**下载完整 ZIP → 解压 → 拖入安装器 → 确认成功 → 自检 → 场景副本首次传递。** 安装脚本与 `contents/` 必须来自同一份完整版本。单独打开 UI 脚本不等于安装。

## 环境与下载

从[仓库](https://github.com/DimmensCK/FBXTo3dsMax)选择 **Code → Download ZIP** 并解压。保持根目录安装器、`PackageContents.xml`、`LICENSE` 与小写 `contents/`、`docs/`、`tests/`、`tools/` 的相对结构；不要只下载单个安装脚本，也不要在 ZIP 内执行。

历史真机环境为 Windows 11 x64、Max 2023.3.10 / Python 3.9.7。XML 声明 Max 2023–2026，2024–2026 未验证。插件用 Max 自带 Python，正常安装无需额外解释器或编译器。

仓库不携带 FBX/MAX/BLEND；自检素材由源码在用户本地数据目录程序生成。

## 推荐安装

1. 保存当前场景。
2. 把根目录 **`Install_FBXTo3dsMax.ms`** 拖入 Max 视口。
3. 等待安装结束并确认成功。交互安装通常显示结果对话框；静默启动可能只把结果记入日志。失败时保存日志，先解决问题再使用插件。
4. 成功后点击顶部 **FBX 转 MAX / FBX to MAX**。优先使用主工具栏，必要时使用顶部停靠备用栏。
5. 点击 **Language** 旁的 **中文** 或 **EN（英文）**，运行插件自检并阅读报告。
6. 重启 Max，确认按钮仍存在；首次传递使用场景副本。

安装不会自动打开插件主窗口。通常用户级安装位置为：

```text
%APPDATA%\Autodesk\ApplicationPlugins\FBXTo3dsMax
```

通常无需管理员权限。安装后运行完整安装副本。语言选择原位更新并保存到 `%LOCALAPPDATA%\FBXTo3dsMax\language.txt`。[语言界面说明](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/README.md#language-ui)在仓库根主页；安装文本可本地阅读，网页图片和视频需要网络。

## 重复安装、升级和归档

再次拖入同一安装器即可做同版本覆盖；较低版本默认拒绝。安装/卸载共用独占锁，安装器按固定清单暂存、逐项验证 SHA-256、归档旧包、整体切换，再读回文件、版本与工具栏。失败时尝试恢复旧包及受管文件。

当前固定清单为 **32 个安全且唯一的目标**。安装后的 `FBXTo3dsMax.install-manifest.sha256` 目标集合须等于固定源码清单，不能混用旧加密版或历史 27 项源码清单。

日志、暂存、恢复归档及锁位于：

```text
%APPDATA%\Autodesk\FBXTo3dsMaxInstaller
```

结果对话框提供本次准确路径。已有包、同名 Macro/图标无法确认所有权时，会停止而不覆盖。识别到属于插件的旧 AutoLoader 后先归档并记录；历史源工程不属于安装清理范围。

历史 27 项源码版到当前 32 项版的升级未单独验证；不要从新清单数量推断该升级已通过。

归档是可恢复数据，不是自动恢复按钮。保留清单与日志，手动恢复前先核对内容。历史卸载验收验证了归档逐字节一致，未执行从该归档恢复安装。它不等于已给当前日常用户环境完成安装、卸载或恢复。

## 没有按钮或打不开

确认完整下载/解压，阅读实际安装结果与日志，再运行标准安装器并重启 Max。不要为了消除提示而手动删除未确认所有权的同名包、Macro、图标或旧 AutoLoader。仍失败时提供 Max 完整版本、插件版本、重现步骤和脱敏日志。

直接运行 `contents/FBXTo3dsMax_UI.ms` 只临时打开窗口，不等于完整安装成功。开发者须保留包内 `post-start-up scripts parts`：它是 AutoLoader 路由标识。

## 自检与首次传递

自检启动专用 `3dsmaxbatch.exe`，在原创生成场景中运行，不重置当前交互场景；异步运行，可取消。六类全部通过且进程自然退出 **0** 才成功。超时、取消、强制清理或非零退出，即使 JSON 显示绿色也算失败。

报告位于 `%LOCALAPPDATA%\FBXTo3dsMax\SelfCheck`。失败先定位原因，通过后也从场景副本、单对象、默认“变形”开始，核对视觉、动画与保存重载。

正式传递在 Max 主线程同步执行，没有中途安全取消。

## 卸载

将根目录 `Uninstall_FBXTo3dsMax.ms` 拖入 Max，或运行安装副本的 `contents/Uninstall_FBXTo3dsMax.ms`。卸载器检查所有权、清理自有窗口/工具栏/回调，将包和受管 Macro/图标移入归档并生成 SHA-256 清单；失败时尝试恢复。

保留结果对话框显示的归档。卸载后重启 Max 清除缓存动作项；用户场景与恢复归档不会被永久删除。

## PowerShell 备用入口

交互 Max 已打开时优先拖入 `.ms`。所有 Max/Batch 已关闭时，在工程根目录使用 PowerShell 7：

```powershell
pwsh -NoLogo -NoProfile -File .\tools\Install_FBXTo3dsMax.ps1 -MaxRoot '<实际 Max 安装目录>'
```

将占位内容替换为安装目录或 `3dsmax.exe` 的绝对路径。启动器先只读检查文件、版本及选定 Max，再执行同一个 `.ms` 事务；检测到已有 Max/Batch 会拒绝，不会结束用户进程。

按任务操作见[完整教程](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/zh/FBXTo3dsMax_详细说明书.md)。开发验证见[测试说明](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md)。安装副本的本篇为 `INSTALL_中文.md`，英文为同目录 `INSTALL_EN.md`。
