# 参与贡献 / Contributing

欢迎提交 BUG、教程修正和有具体用途的改进。项目由 Dimmens 开发，采用 [MIT](../../LICENSE)。

Welcome bug reports, documentation fixes and focused improvements. Start from the [English guide](../en/USER_GUIDE.md) or [中文教程](../zh/FBXTo3dsMax_详细说明书.md).

## 报告问题 / Report a problem

提供插件版本、Max 完整版本、Windows 版本、界面语言、操作步骤、期望/实际结果及脱敏报告。优先用原创程序生成的最小场景；不要公开正式模型、个人路径、账号、令牌或原始本机日志。报告位于 `%LOCALAPPDATA%\FBXTo3dsMax`。

Include plug-in/Max/Windows versions, UI language, steps, expected/actual behavior and a sanitized report. Use an original procedural minimal scene rather than production assets. For installation failures retain the transaction log; for self-check failures include natural-exit status. Preserve the original scene and reproduce on a copy.

在 [Issues](https://github.com/DimmensCK/FBXTo3dsMax/issues/new/choose) 中选择问题报告、使用问题或改进建议，也可创建空白 Issue。使用问题说明想完成的任务和已尝试的步骤；改进建议说明困难、收益与替代方案。不要求提供私人模型或完整原始日志。

Choose a bug report, usage question, improvement proposal or blank issue in the [issue chooser](https://github.com/DimmensCK/FBXTo3dsMax/issues/new/choose). Explain your task and attempts for usage questions, or the need, benefit and alternatives for proposals. Private models and full raw local logs are not required.

## 修改代码 / Change code

1. Read root [AGENTS](../../AGENTS.md), [project memory](PROJECT_MEMORY.md), the Chinese [overview](../zh/README_中文.md), [installation](../zh/INSTALL_中文.md), and [changelog](CHANGELOG_中文.md).
2. Use a focused branch and explain the concrete trigger, resulting behavior and limits.
3. Preserve the two modes, strict validation, scene state/importer restoration and rollback boundaries.
4. Run relevant pure tests. Core/host changes require real Max Batch; layout/installer changes require isolated fresh/repeat install, source-origin SHA readback, cold start, installed self-check, injected rollback and recoverable uninstall. Language changes also verify both languages, persistence and retained UI state. See [TESTING](../TESTING.md).
5. Bug fixes add `0.0.1`; features add `0.1.0`. Synchronize every product marker. Documentation-only changes may retain the product version.

分别写清已经执行与尚未验证的范围。编译、静态 PASS 或旧版结果不能代替当前真机验收。Do not present compilation, static checks or historical results as current runtime qualification.

## 自动检查与本地运行 / Automated checks and local runs

[Source checks](https://github.com/DimmensCK/FBXTo3dsMax/actions/workflows/source-checks.yml) 使用 Windows 2022 runner 与普通 CPython 3.9，运行标准库静态检查和纯 Python 回归。它由推送到 `main`、Pull Request 或手动触发；结果以对应提交的实际运行记录为准。工作流不启动 Max、不安装插件，也不上传本机报告或日志。

The [workflow source](../../.github/workflows/source-checks.yml) pins official actions to full commit SHAs, uses read-only repository permission and does not persist checkout credentials. It runs static checks and pure regressions on Windows 2022 with CPython 3.9; it does not start Max, install the plug-in or upload local reports/logs. Check the actual run for the relevant commit rather than treating the workflow file as a passing result.

在仓库根目录，用明确选定的 Python 3.9+ 和 PowerShell 7 执行：

```powershell
$ErrorActionPreference = 'Stop'
python -B .\tools\check_repository.py
if ($LASTEXITCODE -ne 0) { throw 'Repository static check failed.' }
$testLanguageBefore = $env:F2M_LANGUAGE
try {
    $env:F2M_LANGUAGE = 'zh-CN'
    python -B -m unittest discover -s tests -p 'test_*.py' -v
    if ($LASTEXITCODE -ne 0) { throw 'Pure regression tests failed.' }
} finally {
    $env:F2M_LANGUAGE = $testLanguageBefore
}
```

Run these commands at the repository root with a deliberately selected Python 3.9+ and PowerShell 7. The test locale is temporary; it does not change the user's saved language. Windows is required for the full suite, including Windows PowerShell and PowerShell 7 source/log-gate tests.

CI 通过只表示该提交的静态与纯回归通过，不能替代真实 Max 的功能、安装、回滚或界面资格。涉及这些行为的改动仍按上面的规则和 [TESTING](../TESTING.md) 完成相关隔离验收，并如实记录未测范围。

A passing CI run proves that commit's static and pure regressions only. Host behavior, installation, rollback and UI changes still need the relevant isolated real-Max checks described above and in [TESTING](../TESTING.md), with untested scope stated explicitly.

## 数据与输出 / Data and output

测试使用原创程序生成场景，不提交 FBX/MAX/BLEND 模型。输出写入用户本地数据目录；不提交日志、结果、缓存、安装副本、解释器、工具链或编译产物。经作者明确授权的教程媒体须另查隐私和公开资格，媒体授权不等于模型分发授权。

Keep test inputs read-only and outputs outside source/installed code. Review the changed-file list and run `tools/check_repository.py`. Retain MIT and attribution; document provenance and licenses for any added third-party resource.
