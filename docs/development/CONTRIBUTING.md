# 参与贡献 / Contributing

欢迎提交 BUG、教程修正和有具体用途的改进。项目由 Dimmens 开发，采用 [MIT](../../LICENSE)。

Welcome bug reports, documentation fixes and focused improvements. Start from the [English guide](../en/USER_GUIDE.md) or [中文教程](../zh/FBXTo3dsMax_详细说明书.md).

## 报告问题 / Report a problem

提供插件版本、Max 完整版本、Windows 版本、界面语言、操作步骤、期望/实际结果及脱敏报告。优先用原创程序生成的最小场景；不要公开正式模型、个人路径、账号、令牌或原始本机日志。报告位于 `%LOCALAPPDATA%\FBXTo3dsMax`。

Include plug-in/Max/Windows versions, UI language, steps, expected/actual behavior and a sanitized report. Use an original procedural minimal scene rather than production assets. For installation failures retain the transaction log; for self-check failures include natural-exit status. Preserve the original scene and reproduce on a copy.

## 修改代码 / Change code

1. Read root [AGENTS](../../AGENTS.md), [project memory](PROJECT_MEMORY.md), the Chinese [overview](../zh/README_中文.md), [installation](../zh/INSTALL_中文.md), and [changelog](CHANGELOG_中文.md).
2. Use a focused branch and explain the concrete trigger, resulting behavior and limits.
3. Preserve the two modes, strict validation, scene state/importer restoration and rollback boundaries.
4. Run relevant pure tests. Core/host changes require real Max Batch; layout/installer changes require isolated fresh/repeat install, source-origin SHA readback, cold start, installed self-check, injected rollback and recoverable uninstall. Language changes also verify both languages, persistence and retained UI state. See [TESTING](../TESTING.md).
5. Bug fixes add `0.0.1`; features add `0.1.0`. Synchronize every product marker. Documentation-only changes may retain the product version.

分别写清已经执行与尚未验证的范围。编译、静态 PASS 或旧版结果不能代替当前真机验收。Do not present compilation, static checks or historical results as current runtime qualification.

## 数据与输出 / Data and output

测试使用原创程序生成场景，不提交 FBX/MAX/BLEND 模型。输出写入用户本地数据目录；不提交日志、结果、缓存、安装副本、解释器、工具链或编译产物。经作者明确授权的教程媒体须另查隐私和公开资格，媒体授权不等于模型分发授权。

Keep test inputs read-only and outputs outside source/installed code. Review the changed-file list and run `tools/check_repository.py`. Retain MIT and attribution; document provenance and licenses for any added third-party resource.
