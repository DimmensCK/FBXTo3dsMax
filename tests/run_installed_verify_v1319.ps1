#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$MaxExecutable = 'D:\Autodesk\3dsmax2023\3ds Max 2023\3dsmax.exe',
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = 'Stop'
$verifyPath = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot 'max_installed_interactive_verify_and_quit.py')
)
$resultRoot = if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    [IO.Path]::GetTempPath()
} else { $env:LOCALAPPDATA }
$resultPath = [IO.Path]::GetFullPath(
    (Join-Path $resultRoot 'FBXTo3dsMax\Validation\_max_installed_interactive_verify.json')
)
$tokenName = 'F2M_INSTALLED_VERIFY_TOKEN'
$runToken = 'v1.4.26-' + [Guid]::NewGuid().ToString('N')

if (-not (Test-Path -LiteralPath $MaxExecutable -PathType Leaf)) {
    throw "找不到 3ds Max：$MaxExecutable"
}
if (-not (Test-Path -LiteralPath $verifyPath -PathType Leaf)) {
    throw "找不到安装后验收脚本：$verifyPath"
}
$existingMax = @(
    Get-Process -Name @('3dsmax', '3dsmaxbatch') -ErrorAction SilentlyContinue
)
if ($existingMax.Count -ne 0) {
    throw '检测到已打开的 3ds Max/Batch。为避免碰到其它会话，安装后验收已拒绝启动。'
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
    $quotedVerify = '"' + $verifyPath + '"'
    $process = Start-Process `
        -FilePath $MaxExecutable `
        -WindowStyle Hidden `
        -ArgumentList @('-q', '-silent', '-U', 'PythonHost', $quotedVerify) `
        -PassThru
}
finally {
    [Environment]::SetEnvironmentVariable(
        $tokenName,
        $previousToken,
        [EnvironmentVariableTarget]::Process
    )
}

if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    throw "专用安装后验收进程 $($process.Id) 超过 $TimeoutSeconds 秒，已只终止该进程。"
}
$exitCode = $process.ExitCode
if (-not (Test-Path -LiteralPath $resultPath -PathType Leaf)) {
    throw "专用进程已退出，但没有生成验收结果：$resultPath"
}

$result = Get-Content -LiteralPath $resultPath -Raw -Encoding UTF8 |
    ConvertFrom-Json
if (
    $result.token -ne $runToken -or
    [int]$result.pid -ne $process.Id
) {
    throw '安装后验收结果的单次令牌或 PID 与启动方不一致，拒绝接受旧结果。'
}
if ($result.state -ne 'finished' -or $result.ok -ne $true) {
    throw ('安装后验收未通过：' + ($result | ConvertTo-Json -Depth 8))
}
if ($result.version -ne '1.4.26') {
    throw "安装后验收版本读回不一致：期望 1.4.26，实际 $($result.version)。"
}
if ($exitCode -ne 0) {
    throw "安装后验收内容通过，但专用 3ds Max 进程退出码为 $exitCode。"
}

[pscustomobject]@{
    ok = $true
    token = $runToken
    pid = $process.Id
    exit_code = $exitCode
    result = $resultPath
    button_text = $result.button_text
    button_rect = $result.button_rect
    rollout_open = $result.rollout_open
}
