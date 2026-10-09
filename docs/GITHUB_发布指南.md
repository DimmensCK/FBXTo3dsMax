# 下载源码与维护 GitHub 仓库

项目使用现有仓库 [DimmensCK/FBXTo3dsMax](https://github.com/DimmensCK/FBXTo3dsMax)，主分支 `main`。

[中文安装](zh/INSTALL_中文.md) · [English installation](en/INSTALL.md) · [测试范围](TESTING.md)

## 下载给自己用

在仓库页面选择 **Code → Download ZIP**，解压后找到同时包含 `Install_FBXTo3dsMax.ms` 和小写 `contents/` 的工程根目录。按安装说明拖入标准 `.ms` 入口，保持相对结构，不在 ZIP 中运行。[GitHub 官方下载说明](https://docs.github.com/en/repositories/working-with-files/using-files/downloading-source-code-archives)

如果需要固定版本，在 **Releases** 选择对应版本的完整源代码包；分支 `main` 可能继续变化。记录插件版本，不要将历史验证误当作新版本验证。

Root `LICENSE` 是 MIT，作者 Dimmens。公开内容是可读源码、资源、测试代码、双语文档及经授权审查的教程媒体，不携带 FBX/MAX/BLEND 模型、私有备份、本机日志或构建工具链。

## 用 GitHub Desktop 管理更新

安装 [GitHub Desktop](https://desktop.github.com/)，用自己的账号登录。作者沿用现有仓库，无需重复创建同名仓库；贡献者先 Fork，再克隆自己的副本。

1. 选择 **File → Clone repository**，选择 `DimmensCK/FBXTo3dsMax`；也可在 **URL** 页填该仓库链接。
2. 用 **Choose** 选择一个新的空开发目录，再点击 **Clone**。以线上公开历史为基线，不直接推送本机验收工程的候选历史。[官方克隆说明](https://docs.github.com/en/desktop/adding-and-cloning-repositories/cloning-and-forking-repositories-from-github-desktop)
3. 检查远端是目标仓库、当前分支与 **History** 正确。将审核后的源码文件改动复制进这个克隆目录，保持安装入口与 `contents/`、`docs/`、`tests/`、`tools/` 的相对结构；不复制 `.git/`、私有资产、备份或日志。
4. 在 **Changes** 逐项阅读变更，完成相关验证、更新版本和验证范围。使用开发分支保存修改，填写具体 **Summary** 并提交；需要合并时通过 Pull Request 审查。
5. 只对当前审核过的开发分支使用 **Push origin**。远端有新修改时先查看并合并；出现冲突先核对双方内容，不强制覆盖。[官方提交与推送说明](https://docs.github.com/en/desktop/making-changes-in-a-branch/committing-and-reviewing-changes-to-your-project-in-github-desktop)

已有目录仅在核对其远端、当前分支及提交历史与公开仓库一致后，才用 **File → Add local repository**。[官方添加本地仓库说明](https://docs.github.com/en/desktop/adding-and-cloning-repositories/adding-a-repository-from-your-local-computer-to-github-desktop) 本机验证分支和备份引用不属于发布内容；不要使用 `push --all`，不要用强制推送解决历史不一致。

`.gitignore` 用于忽略后续未跟踪文件，不会清除已经提交的文件或历史。发现不该公开的内容时先停止推送、查清范围，再单独处理；不能靠新增忽略规则证明历史已清理。[GitHub 官方忽略文件说明](https://docs.github.com/en/get-started/git-basics/ignoring-files)

**Commit** 保存本机历史；**Push** 才把提交发给远端。GitHub 登录使用正常 Desktop 流程，不把密码或令牌写入工程。

## 核对远端与发布版本

打开仓库确认 README、MIT、源码、双语教程和 **32 项**安装资源完整。重新下载或克隆到新目录，运行仓库检查和纯测试；相关源码/安装改动还需从远端副本做真实 Max 和隔离安装验收。单凭网页可见或 Push 成功不证明插件功能正常。

需要版本入口时，用 **Releases → Draft a new release**，目标选择已验收的提交；标签对应源码版本，例如 `v1.4.24`。写清安装方法、实测 Max 版本、变化与剩余限制，确认后发布。[官方 Release 指南](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)

后续沿用：从公开历史克隆 → 复制审核后的源码改动 → 验证 → 查看 Changes → Commit → Push 当前分支 → 审查合并。不要把尚未验收的改动写成全平台稳定版本。

## English quick reference

Download the complete repository via **Code → Download ZIP** and extract it before installation. For maintenance, use **GitHub Desktop → File → Clone repository**, choose `DimmensCK/FBXTo3dsMax` and a new empty development directory. Contributors fork and clone their own copy. Start from the published history, copy only reviewed source changes, verify them, then commit and push the reviewed branch. Before adding an existing local repository, check its remote, branch and history. Do not publish local validation branches or backup refs, use `push --all`, or force-push to resolve a history mismatch. `.gitignore` does not remove committed content or history. Commit is local; push updates the remote. Release only the exact qualified commit, state tested Max versions and limits, and verify a fresh remote download.
