# 下载源码与维护 GitHub 仓库

源码与后续更新使用同一仓库：[DimmensCK/FBXTo3dsMax](https://github.com/DimmensCK/FBXTo3dsMax)。主分支为 `main`。安装前先阅读[安装说明](../INSTALL_中文.md)与[测试范围](TESTING.md)。

在仓库页面选择 **Code → Download ZIP**，解压后找到包含 `Install_FBXTo3dsMax.ms` 和 `Contents/` 的工程根目录，保持相对结构，再按安装说明拖入标准 `.ms` 入口。[GitHub 官方源码下载说明](https://docs.github.com/en/repositories/working-with-files/using-files/downloading-source-code-archives)。

根目录 `LICENSE` 为 MIT，作者 Dimmens。上传内容是可读源码、资源、测试代码和文档，不包含 FBX/MAX/BLEND 模型、旧发行、工具链、私有备份、本机日志或验证工具。

下面是作者或贡献者维护本地 Git 仓库的方法。沿用现有仓库，无需重复创建同名仓库或选择 Publish repository。本地 Commit 只保存本机历史；Push origin 才把提交推送到远端。

## 1. 把本地工程加入 GitHub Desktop

安装 [GitHub Desktop](https://desktop.github.com/)，登录现有的 `DimmensCK` 账号。

1. 选择 **File → Add local repository**。
2. 点击 **Choose**，选择整理后的工程目录本身。
3. 点击 **Add repository**。
4. 确认当前仓库为 `FBXTo3dsMax`、分支为 `main`，远端为上面的现有 GitHub 仓库。

本地已是 Git 仓库；选择工程目录即可，不要另建嵌套目录。[GitHub 官方本地仓库说明](https://docs.github.com/en/desktop/adding-and-cloning-repositories/adding-a-repository-from-your-local-computer-to-github-desktop)。

## 2. 查看并提交本地修改

在 **Changes** 中逐项阅读本次文件列表，保持 `Contents/`、`tests/`、`tools/`、`docs/` 及根目录源码的相对结构。

有未提交修改时，在 **Summary** 填写简明说明，例如 `Prepare source v1.3.24`，再点击 **Commit to main**。如果修改已经由本轮本地提交保存，直接在 **History** 核对提交即可，无需重复提交。

**Commit** 把当前改动保存到本机 Git 历史；它还没有把源码上传给别人。

## 3. 推送本次更新

先按 [测试说明](TESTING.md) 完成与本次改动相关的验证，更新版本和证明范围，再提交修改。

确认即将上传的内容后，点击 **Push origin**，把本地提交推送到已有仓库。遇到登录提示，使用 Desktop 的正常登录流程；如果提示远端有新修改，先查看并合并，不使用强制推送覆盖远端。[GitHub 官方提交与推送说明](https://docs.github.com/en/desktop/making-changes-in-a-branch/committing-and-reviewing-changes-to-your-project-in-github-desktop)。

在浏览器打开 [现有仓库](https://github.com/DimmensCK/FBXTo3dsMax)，核对：README 已更新、LICENSE 显示 MIT、源码可浏览、27 项安装资源与生成器完整。这一步完成后才能称完整源码已上传。

## 4. 从远端新副本再验证

上传完成后，重新下载或克隆到新目录，对这份副本运行仓库检查和纯测试。在测试配置/场景副本中从该副本安装，核对冷启动按钮与安装副本自检，发现漏传文件或目录嵌套时先修正。

如需单独的版本入口，可以在 **Releases → Draft a new release** 准备 `v1.3.24`，目标选择已完成验收的提交，写明源码安装方法、实测 Max 版本和剩余限制。只有准备完成后再发布 Release。[GitHub 官方 Release 指南](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)。

后续更新沿用同一流程：修改 → 查看 Changes → Commit → Push origin。版本和验证结果随改动同步，不上传用户场景或本机验证日志。
