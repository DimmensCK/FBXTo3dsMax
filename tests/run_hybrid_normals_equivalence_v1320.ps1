#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$MaxBatchExecutable = 'D:\Autodesk\3dsmax2023\3ds Max 2023\3dsmaxbatch.exe',
    [ValidateRange(60, 3600)]
    [int]$TimeoutSeconds = 900,
    [string]$MaxLogPath = (
        Join-Path $env:LOCALAPPDATA `
            'Autodesk\3dsMax\2023 - 64bit\CHS\Network\Max.log'
    )
)

$ErrorActionPreference = 'Stop'
$scriptPath = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot 'max_hybrid_normals_equivalence_v1320.py')
)
$resultPath = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot '_max_hybrid_normals_equivalence_v1320_result.json')
)
$gateResultPath = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot '_max_hybrid_normals_equivalence_v1320_gate.json')
)
$beforeLogPath = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot '_max_hybrid_normals_Max_before.log')
)
$afterLogPath = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot '_max_hybrid_normals_Max_after.log')
)
$maxSlicePath = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot '_max_hybrid_normals_Max_current.log')
)
$listenerLogPath = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot '_max_hybrid_normals_listener.log')
)
$listenerSlicePath = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot '_max_hybrid_normals_listener_current.log')
)
$MaxBatchExecutable = [IO.Path]::GetFullPath($MaxBatchExecutable)
$MaxLogPath = [IO.Path]::GetFullPath($MaxLogPath)
$maxRoot = [IO.Path]::GetFullPath((Split-Path -Parent $MaxBatchExecutable))
$runToken = [Guid]::NewGuid().ToString('N').ToLowerInvariant()
$runStartedUtc = [DateTime]::UtcNow
$environmentValues = @{
    F2M_HYBRID_NORMALS_TOKEN = $runToken
    F2M_HYBRID_NORMALS_EXPECTED_SCRIPT = $scriptPath
    F2M_HYBRID_NORMALS_RESULT = $resultPath
}

function Write-Utf8NoBom {
    param(
        [string]$Path,
        [string]$Text
    )
    [IO.File]::WriteAllText(
        $Path,
        $Text,
        (New-Object Text.UTF8Encoding($false))
    )
}

function Copy-LogSnapshot {
    param(
        [string]$Source,
        [string]$Destination
    )
    if (Test-Path -LiteralPath $Source -PathType Leaf) {
        [IO.File]::Copy($Source, $Destination, $true)
    }
    else {
        [IO.File]::WriteAllBytes($Destination, [byte[]]@())
    }
}

function Get-FileByteDelta {
    param(
        [string]$BeforePath,
        [string]$AfterPath
    )
    [byte[]]$beforeBytes = [IO.File]::ReadAllBytes($BeforePath)
    [byte[]]$afterBytes = [IO.File]::ReadAllBytes($AfterPath)
    $hasExactPrefix = $afterBytes.Length -ge $beforeBytes.Length
    if ($hasExactPrefix) {
        for ($index = 0; $index -lt $beforeBytes.Length; $index++) {
            if ($beforeBytes[$index] -ne $afterBytes[$index]) {
                $hasExactPrefix = $false
                break
            }
        }
    }

    [byte[]]$deltaBytes = [byte[]]@()
    $mode = 'append'
    if ($hasExactPrefix) {
        $length = $afterBytes.Length - $beforeBytes.Length
        if ($length -gt 0) {
            $deltaBytes = New-Object byte[] $length
            [Array]::Copy(
                $afterBytes,
                $beforeBytes.Length,
                $deltaBytes,
                0,
                $length
            )
        }
    }
    else {
        $mode = 'replaced_or_rewritten'
        $deltaBytes = $afterBytes
    }
    [pscustomobject]@{
        bytes = $deltaBytes
        mode = $mode
        before_length = $beforeBytes.Length
        after_length = $afterBytes.Length
        delta_length = $deltaBytes.Length
    }
}

function Get-OwnedProcesses {
    param([int]$RootPid)
    $all = @(
        Get-CimInstance -ClassName Win32_Process -ErrorAction SilentlyContinue
    )
    $wanted = New-Object 'System.Collections.Generic.HashSet[int]'
    [void]$wanted.Add($RootPid)
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($item in $all) {
            $pidValue = [int]$item.ProcessId
            $parentValue = [int]$item.ParentProcessId
            if (
                $wanted.Contains($parentValue) -and
                -not $wanted.Contains($pidValue)
            ) {
                [void]$wanted.Add($pidValue)
                $changed = $true
            }
        }
    }
    @($all | Where-Object { $wanted.Contains([int]$_.ProcessId) })
}

function Stop-OwnedMaxTree {
    param(
        [int]$RootPid,
        [string]$ExpectedRoot
    )
    $owned = @(Get-OwnedProcesses -RootPid $RootPid)
    foreach ($item in ($owned | Sort-Object ProcessId -Descending)) {
        $name = [IO.Path]::GetFileName([string]$item.ExecutablePath)
        $path = [string]$item.ExecutablePath
        $isMax = $name -in @('3dsmax.exe', '3dsmaxbatch.exe')
        $isExpected = (
            $path -and
            [IO.Path]::GetFullPath($path).StartsWith(
                $ExpectedRoot,
                [StringComparison]::OrdinalIgnoreCase
            )
        )
        if ($isMax -and $isExpected) {
            Stop-Process `
                -Id ([int]$item.ProcessId) `
                -Force `
                -ErrorAction SilentlyContinue
        }
    }
}

function Get-CompactText {
    param(
        [AllowNull()]
        [object]$Value,
        [int]$MaximumLength = 2048
    )
    $text = ([string]$Value).Trim() -replace '\s+', ' '
    if ([string]::IsNullOrWhiteSpace($text)) {
        return '<未提供 error>'
    }
    if ($text.Length -gt $MaximumLength) {
        return $text.Substring(0, $MaximumLength) + '…'
    }
    return $text
}

if (-not (Test-Path -LiteralPath $MaxBatchExecutable -PathType Leaf)) {
    throw "找不到 3ds Max Batch：$MaxBatchExecutable"
}
if ([IO.Path]::GetFileName($MaxBatchExecutable) -ine '3dsmaxbatch.exe') {
    throw "混合法线发布门必须使用 3dsmaxbatch.exe：$MaxBatchExecutable"
}
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    throw "找不到混合法线验收脚本：$scriptPath"
}
$existingMax = @(
    Get-Process -Name @('3dsmax', '3dsmaxbatch') -ErrorAction SilentlyContinue
)
if ($existingMax.Count -ne 0) {
    throw '检测到已打开的 3ds Max/Batch。为保护交互场景并隔离 Max.log，发布门已拒绝启动。'
}

foreach ($stalePath in @(
    $resultPath,
    $gateResultPath,
    $listenerLogPath,
    $listenerSlicePath,
    $maxSlicePath
)) {
    if (Test-Path -LiteralPath $stalePath -PathType Leaf) {
        Remove-Item -LiteralPath $stalePath -Force
    }
}
Copy-LogSnapshot -Source $MaxLogPath -Destination $beforeLogPath

$previousEnvironment = @{}
foreach ($name in $environmentValues.Keys) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable(
        $name,
        [EnvironmentVariableTarget]::Process
    )
}

$process = $null
$exitCode = $null
$timedOut = $false
$ownedPids = New-Object 'System.Collections.Generic.HashSet[int]'
try {
    foreach ($name in $environmentValues.Keys) {
        [Environment]::SetEnvironmentVariable(
            $name,
            $environmentValues[$name],
            [EnvironmentVariableTarget]::Process
        )
    }
    $quotedScript = '"' + $scriptPath + '"'
    $quotedListener = '"' + $listenerLogPath + '"'
    $process = Start-Process `
        -FilePath $MaxBatchExecutable `
        -ArgumentList @(
            $quotedScript,
            '-listenerlog',
            $quotedListener
        ) `
        -WindowStyle Hidden `
        -PassThru
    [void]$ownedPids.Add($process.Id)

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while (-not $process.HasExited -and [DateTime]::UtcNow -lt $deadline) {
        foreach ($item in @(Get-OwnedProcesses -RootPid $process.Id)) {
            [void]$ownedPids.Add([int]$item.ProcessId)
        }
        Start-Sleep -Milliseconds 500
        $process.Refresh()
    }
    if (-not $process.HasExited) {
        $timedOut = $true
        Stop-OwnedMaxTree -RootPid $process.Id -ExpectedRoot $maxRoot
    }
    else {
        $process.WaitForExit()
        $exitCode = $process.ExitCode
    }
}
finally {
    foreach ($name in $previousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable(
            $name,
            $previousEnvironment[$name],
            [EnvironmentVariableTarget]::Process
        )
    }
    if ($null -ne $process) {
        try {
            if (-not $process.HasExited) {
                Stop-OwnedMaxTree -RootPid $process.Id -ExpectedRoot $maxRoot
            }
        }
        catch {
            # 专用进程可能在检查和清理之间自行退出。
        }
    }
    Copy-LogSnapshot -Source $MaxLogPath -Destination $afterLogPath
}
$runFinishedUtc = [DateTime]::UtcNow

$errors = New-Object 'System.Collections.Generic.List[string]'
if ($timedOut) {
    $errors.Add("专用 MaxBatch 超过 $TimeoutSeconds 秒，已只清理本次启动树。")
}
if ($null -eq $exitCode) {
    $errors.Add('专用 MaxBatch 没有可接受的退出码。')
}
elseif ($exitCode -ne 0) {
    $errors.Add("专用 MaxBatch 退出码不是 0：$exitCode")
}

$result = $null
if (-not (Test-Path -LiteralPath $resultPath -PathType Leaf)) {
    $errors.Add("专用进程没有生成业务 JSON：$resultPath")
}
else {
    try {
        $result = Get-Content -LiteralPath $resultPath -Raw -Encoding UTF8 |
            ConvertFrom-Json
    }
    catch {
        $errors.Add("业务 JSON 无法解析：$($_.Exception.Message)")
    }
}

if ($null -ne $result) {
    if ($result.token -ne $runToken) {
        $errors.Add('业务 JSON 单次令牌不匹配，拒绝接受旧结果。')
    }
    $resultScript = ''
    try {
        $resultScript = [IO.Path]::GetFullPath([string]$result.script_path)
    }
    catch {
        $errors.Add('业务 JSON 脚本路径不是有效绝对路径。')
    }
    if (
        $resultScript -and
        -not $resultScript.Equals(
            $scriptPath,
            [StringComparison]::OrdinalIgnoreCase
        )
    ) {
        $errors.Add(
            "业务 JSON 脚本身份不匹配：$resultScript / $scriptPath"
        )
    }
    $resultPid = [int]$result.pid
    if (-not $ownedPids.Contains($resultPid)) {
        $errors.Add("业务 JSON PID $resultPid 不属于本次 MaxBatch 启动树。")
    }
    if ($result.version -ne '1.3.20') {
        $errors.Add("业务 JSON 版本错误：$($result.version)/1.3.20")
    }
    if ($result.state -ne 'finished' -or $result.ok -ne $true) {
        $errors.Add(
            '混合法线业务验收未通过：' +
            (Get-CompactText -Value $result.error)
        )
    }
    if (
        [int]$result.case_count -ne 3 -or
        [int]$result.persistence_case_count -ne 3 -or
        $result.saved_and_reloaded -ne $true
    ) {
        $errors.Add(
            "三案例/保存重载不完整：$($result.case_count)/" +
            "$($result.persistence_case_count)/$($result.saved_and_reloaded)"
        )
    }
    $expectedCornerSets = @{
        AllSGExpressible = @{
            semantic = ''
            retained = ''
        }
        SharedIdPartialResidual = @{
            semantic = '7'
            retained = '7'
        }
        HardSoftLocalCustom = @{
            semantic = '8'
            retained = '8,10'
        }
    }
    foreach ($case in @($result.cases)) {
        if ($case.status -ne 'PASS') {
            $errors.Add("组合案例未通过：$($case.name)")
        }
        $before = $case.before_reload
        $semanticText = @($before.semantic_residual_corners) -join ','
        $retainedText = @($before.retained_corners) -join ','
        $specifiedText = @($before.specified_corners) -join ','
        $explicitText = @($before.explicit_corners) -join ','
        if (
            $retainedText -ne $specifiedText -or
            $retainedText -ne $explicitText
        ) {
            $errors.Add("最小稳定锁定角集合不精确：$($case.name)")
        }
        if (-not $expectedCornerSets.ContainsKey([string]$case.name)) {
            $errors.Add("未知的混合法线案例：$($case.name)")
        }
        else {
            $expected = $expectedCornerSets[[string]$case.name]
            if ($semanticText -ne $expected.semantic) {
                $errors.Add(
                    "语义残差角集合错误：$($case.name) " +
                    "$semanticText/$($expected.semantic)"
                )
            }
            if ($retainedText -ne $expected.retained) {
                $errors.Add(
                    "Max 稳定保护闭包错误：$($case.name) " +
                    "$retainedText/$($expected.retained)"
                )
            }
        }
        if (
            [double]$before.max_final_angle_degrees -gt
            [double]$result.final_tolerance_degrees
        ) {
            $errors.Add("逐面角权威方向超差：$($case.name)")
        }
        if (
            (@($case.smoothing_masks_before_normals) -join ',') -ne
            (@($case.smoothing_masks_after_normals) -join ',')
        ) {
            $errors.Add("法线写入改变 SG 掩码：$($case.name)")
        }
    }
    foreach ($case in @($result.persistence_cases)) {
        if ($case.status -ne 'PASS') {
            $errors.Add("保存重载案例未通过：$($case.name)")
        }
    }
    foreach ($heapValue in @(
        [string]$result.heap_check_before,
        [string]$result.heap_check_after
    )) {
        if ($heapValue.Trim().ToLowerInvariant() -notin @('true', 'ok')) {
            $errors.Add("业务 JSON heapCheck 异常：$heapValue")
        }
    }
    if ($result.temporary_scene_removed -ne $true) {
        $errors.Add('业务 JSON 未确认临时 .max 场景已删除。')
    }
    $resultWriteUtc = (Get-Item -LiteralPath $resultPath).LastWriteTimeUtc
    if (
        $resultWriteUtc -lt $runStartedUtc.AddSeconds(-2) -or
        $resultWriteUtc -gt $runFinishedUtc.AddSeconds(2)
    ) {
        $errors.Add('业务 JSON 修改时间不在本次启动窗口内。')
    }
}

$listenerText = ''
if (Test-Path -LiteralPath $listenerLogPath -PathType Leaf) {
    $listenerText = Get-Content -LiteralPath $listenerLogPath -Raw -Encoding Default
}
$escapedToken = [regex]::Escape($runToken)
$beginPattern = (
    'F2M_HYBRID_NORMALS_BEGIN\s+TOKEN=' + $escapedToken +
    '\s+PID=(?<pid>\d+)\s+UTC=(?<utc>\S+)'
)
$endPattern = (
    'F2M_HYBRID_NORMALS_END\s+TOKEN=' + $escapedToken +
    '\s+PID=(?<pid>\d+)\s+UTC=(?<utc>\S+)\s+OK=(?<ok>true|false)'
)
$begin = [regex]::Match(
    $listenerText,
    $beginPattern,
    [Text.RegularExpressions.RegexOptions]::IgnoreCase
)
$listenerSlice = ''
if (-not $begin.Success) {
    $errors.Add('listener log 缺少本次令牌的 BEGIN 标记。')
}
else {
    $endStart = $begin.Index + $begin.Length
    $end = [regex]::Match(
        $listenerText.Substring($endStart),
        $endPattern,
        [Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
    if (-not $end.Success) {
        $listenerSlice = $listenerText.Substring($begin.Index)
        $errors.Add('listener log 缺少本次令牌的 END 标记。')
    }
    else {
        $absoluteEnd = $endStart + $end.Index + $end.Length
        $lineEnd = $listenerText.IndexOf("`n", $absoluteEnd)
        if ($lineEnd -lt 0) {
            $lineEnd = $listenerText.Length
        }
        else {
            $lineEnd += 1
        }
        $listenerSlice = $listenerText.Substring(
            $begin.Index,
            $lineEnd - $begin.Index
        )
        $beginPid = [int]$begin.Groups['pid'].Value
        $endPid = [int]$end.Groups['pid'].Value
        if ($beginPid -ne $endPid) {
            $errors.Add("listener BEGIN/END PID 不一致：$beginPid/$endPid")
        }
        if ($null -ne $result -and $beginPid -ne [int]$result.pid) {
            $errors.Add(
                "listener PID $beginPid 与业务 JSON PID $([int]$result.pid) 不一致。"
            )
        }
        if (
            $null -ne $result -and
            (($end.Groups['ok'].Value -ieq 'true') -ne [bool]$result.ok)
        ) {
            $errors.Add('listener END 状态与业务 JSON 不一致。')
        }
    }
}
Write-Utf8NoBom -Path $listenerSlicePath -Text $listenerSlice

$delta = Get-FileByteDelta `
    -BeforePath $beforeLogPath `
    -AfterPath $afterLogPath
[IO.File]::WriteAllBytes($maxSlicePath, [byte[]]$delta.bytes)
$deltaText = [Text.Encoding]::Default.GetString([byte[]]$delta.bytes)
$pidLogText = ''
if ($null -ne $result) {
    # Max.log pads small process IDs with leading zeroes (for example
    # os.getpid()==636 is logged as [00636]).
    $pidPattern = '\[0*' +
        [regex]::Escape(([int]$result.pid).ToString()) +
        '\]'
    $pidLines = @(
        $deltaText -split "`r?`n" |
            Where-Object { $_ -match $pidPattern }
    )
    $pidLogText = $pidLines -join "`n"
    if ($pidLines.Count -eq 0) {
        $errors.Add(
            "Max.log 本次字节增量中没有业务 PID $([int]$result.pid) 的行，原生发布门不可验证。"
        )
    }
    if (
        $pidLogText -notmatch
        [regex]::Escape([IO.Path]::GetFileName($scriptPath))
    ) {
        $errors.Add('Max.log 的业务 PID 时间片没有记录专用 Python 脚本身份。')
    }
}
else {
    $pidLogText = $deltaText
}

$criticalPatterns = @(
    'MAXScript\s*内存收集错误',
    '当\s*MAXScript\s*在执行内存收集时发生未知错误',
    'unknown\s+error.{0,120}MAXScript.{0,120}garbage\s+collect',
    'MAXScript.{0,120}garbage\s+collection.{0,120}(error|fail|unknown)',
    'EXCEPTION_ACCESS_VIOLATION',
    'unhandled\s+exception',
    'fatal\s+error',
    'out\s+of\s+memory',
    'heapCheck.{0,120}(-3|-4|-6|false|BAD|damaged|corrupt)'
)
foreach ($pattern in $criticalPatterns) {
    if ($pidLogText -match $pattern) {
        $errors.Add("Max.log 本次 PID 时间片命中原生异常：$pattern")
    }
    if ($listenerSlice -match $pattern) {
        $errors.Add("listener 本次令牌时间片命中异常：$pattern")
    }
}

$remaining = @(
    Get-Process -Name @('3dsmax', '3dsmaxbatch') -ErrorAction SilentlyContinue
)
if ($remaining.Count -ne 0) {
    $errors.Add(
        '发布门结束后仍存在 Max/Batch：' +
        (($remaining | ForEach-Object {
            "$($_.ProcessName):$($_.Id)"
        }) -join ', ')
    )
}

if ($errors.Count -ne 0) {
    throw (
        "光滑组 + Explicit 法线逐面角发布门失败：`n- " +
        ($errors -join "`n- ")
    )
}

$gatePayload = [ordered]@{
    ok = $true
    token = $runToken
    launcher_pid = $PID
    maxbatch_pid = $process.Id
    engine_pid = [int]$result.pid
    exit_code = $exitCode
    started_at_utc = $runStartedUtc.ToString('o')
    finished_at_utc = $runFinishedUtc.ToString('o')
    version = [string]$result.version
    case_count = [int]$result.case_count
    persistence_case_count = [int]$result.persistence_case_count
    saved_and_reloaded = [bool]$result.saved_and_reloaded
    max_log_delta_mode = $delta.mode
    max_log_delta_bytes = [int64]$delta.delta_length
    max_log_pid_line_count = @($pidLines).Count
    business_result = $resultPath
    max_log_before = $beforeLogPath
    max_log_after = $afterLogPath
    max_log_current_slice = $maxSlicePath
    listener_log = $listenerLogPath
    listener_log_current_slice = $listenerSlicePath
}
Write-Utf8NoBom `
    -Path $gateResultPath `
    -Text (($gatePayload | ConvertTo-Json -Depth 8) + "`n")

[pscustomobject]$gatePayload
