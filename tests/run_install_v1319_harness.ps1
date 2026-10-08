#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$MaxExecutable = 'D:\Autodesk\3dsmax2023\3ds Max 2023\3dsmax.exe',
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = 'Stop'
$workspaceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$harnessPath = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot 'max_install_v1319_harness.ms')
)
$resultPath = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot '_max_install_v1319_harness.txt')
)
$tokenName = 'F2M_INSTALL_HARNESS_TOKEN'
$runToken = 'v1.3.24-' + [Guid]::NewGuid().ToString('N')

if (-not (Test-Path -LiteralPath $MaxExecutable -PathType Leaf)) {
    throw "找不到 3ds Max：$MaxExecutable"
}
if (-not (Test-Path -LiteralPath $harnessPath -PathType Leaf)) {
    throw "找不到安装验收脚本：$harnessPath"
}
$existingMax = @(
    Get-Process -Name @('3dsmax', '3dsmaxbatch') -ErrorAction SilentlyContinue
)
if ($existingMax.Count -ne 0) {
    throw '检测到已打开的 3ds Max/Batch。为避免碰到其它会话，安装验收已拒绝启动。'
}

$previousToken = [Environment]::GetEnvironmentVariable(
    $tokenName,
    [EnvironmentVariableTarget]::Process
)
$process = $null
try {
    [Environment]::SetEnvironmentVariable(
        $tokenName,
        $runToken,
        [EnvironmentVariableTarget]::Process
    )
    $quotedHarness = '"' + $harnessPath + '"'
    $process = Start-Process `
        -FilePath $MaxExecutable `
        -ArgumentList @('-q', '-silent', '-U', 'MAXScript', $quotedHarness) `
        -PassThru
}
finally {
    [Environment]::SetEnvironmentVariable(
        $tokenName,
        $previousToken,
        [EnvironmentVariableTarget]::Process
    )
}

try {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while (-not $process.HasExited -and [DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 500
        if (Test-Path -LiteralPath $resultPath -PathType Leaf) {
            $guardSnapshot = ''
            try {
                $guardSnapshot = Get-Content `
                    -LiteralPath $resultPath `
                    -Raw `
                    -Encoding UTF8
            }
            catch {
                # WriteAllText 可能短暂独占结果文件；下一轮再读取完整记录。
                $guardSnapshot = ''
            }
            if (
                $guardSnapshot.StartsWith("GUARD_FAIL`r`n") -and
                $guardSnapshot -match [Regex]::Escape("令牌=$runToken") -and
                $guardSnapshot -match [Regex]::Escape("进程=$($process.Id)")
            ) {
                Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                throw "专用安装验收身份守卫拒绝了本次进程：`n$guardSnapshot"
            }
        }
    }
    if (-not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        throw "专用安装验收进程 $($process.Id) 超过 $TimeoutSeconds 秒，已只终止该进程。"
    }
    $exitCode = $process.ExitCode
    if (-not (Test-Path -LiteralPath $resultPath -PathType Leaf)) {
        throw "专用进程已退出，但没有生成验收结果：$resultPath"
    }

    $resultText = Get-Content -LiteralPath $resultPath -Raw -Encoding UTF8
    $expectedTokenLine = "令牌=$runToken"
    $expectedPidLine = "进程=$($process.Id)"
    if (-not $resultText.StartsWith("PASS`r`n")) {
        throw "安装验收未通过：`n$resultText"
    }
    if (
        $resultText -notmatch [Regex]::Escape($expectedTokenLine) -or
        $resultText -notmatch [Regex]::Escape($expectedPidLine)
    ) {
        throw '验收结果的单次令牌或 PID 与启动方不一致，拒绝接受旧结果。'
    }
    if ($exitCode -ne 0) {
        throw "安装验收内容通过，但专用 3ds Max 进程退出码为 $exitCode。"
    }

    [pscustomobject]@{
        ok = $true
        token = $runToken
        pid = $process.Id
        exit_code = $exitCode
        result = $resultPath
        workspace = $workspaceRoot
    }
}
finally {
    if ($null -ne $process) {
        try {
            if (-not $process.HasExited) {
                Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            }
        }
        catch {
            # 专用进程可能恰好在状态检查与终止调用之间自行退出。
        }
    }
}
