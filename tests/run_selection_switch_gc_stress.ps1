#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$MaxBatchExecutable = 'D:\Autodesk\3dsmax2023\3ds Max 2023\3dsmaxbatch.exe',
    [ValidateRange(8, 512)]
    [int]$Iterations = 16,
    [ValidateRange(60, 7200)]
    [int]$TimeoutSeconds = 1800,
    [ValidateRange(0, 4096)]
    [int]$MaxPrivateExcessGrowthMiB = 256,
    [string]$MaxLogPath = (
        Join-Path $env:LOCALAPPDATA `
            'Autodesk\3dsMax\2023 - 64bit\CHS\Network\Max.log'
    )
)

$ErrorActionPreference = 'Stop'
# Historical gate: supply caller-owned fixtures outside this source tree via
# F2M_PRIVATE_MAX_FIXTURE, F2M_PRIVATE_FBX_VARIANT1/2 and matching *_SHA256.
# Optional F2M_PRIVATE_NODE_A/B select scene nodes (ExampleMeshA/B by default).
$reportBase = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { [IO.Path]::GetTempPath() }
$reportRoot = Join-Path $reportBase (
    'FBXTo3dsMax\Validation\selection-gc-' + [Guid]::NewGuid().ToString('N')
)
New-Item -ItemType Directory -Path $reportRoot -Force | Out-Null
$scriptPath = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot 'max_selection_switch_gc_stress.py')
)
$resultPath = [IO.Path]::GetFullPath(
    (Join-Path $reportRoot '_max_selection_switch_gc_stress_result.json')
)
$rawScriptPath = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot 'max_fbx_import_gc_baseline.py')
)
$rawResultPath = [IO.Path]::GetFullPath(
    (Join-Path $reportRoot '_max_fbx_import_gc_baseline.json')
)
$rawBeforeLogPath = [IO.Path]::GetFullPath(
    (Join-Path $reportRoot '_max_fbx_import_gc_baseline_Max_before.log')
)
$rawAfterLogPath = [IO.Path]::GetFullPath(
    (Join-Path $reportRoot '_max_fbx_import_gc_baseline_Max_after.log')
)
$rawSliceLogPath = [IO.Path]::GetFullPath(
    (Join-Path $reportRoot '_max_fbx_import_gc_baseline_Max_current.log')
)
$rawListenerLogPath = [IO.Path]::GetFullPath(
    (Join-Path $reportRoot '_max_fbx_import_gc_baseline_listener.log')
)
$rawListenerSliceLogPath = [IO.Path]::GetFullPath(
    (Join-Path $reportRoot '_max_fbx_import_gc_baseline_listener_current.log')
)
$beforeLogPath = [IO.Path]::GetFullPath(
    (Join-Path $reportRoot '_max_selection_switch_gc_stress_Max_before.log')
)
$afterLogPath = [IO.Path]::GetFullPath(
    (Join-Path $reportRoot '_max_selection_switch_gc_stress_Max_after.log')
)
$sliceLogPath = [IO.Path]::GetFullPath(
    (Join-Path $reportRoot '_max_selection_switch_gc_stress_Max_current.log')
)
$listenerLogPath = [IO.Path]::GetFullPath(
    (Join-Path $reportRoot '_max_selection_switch_gc_stress_listener.log')
)
$listenerSliceLogPath = [IO.Path]::GetFullPath(
    (Join-Path $reportRoot '_max_selection_switch_gc_stress_listener_current.log')
)
$logGatePath = [IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot 'selection_gc_log_gate.ps1')
)
$workspaceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
function Get-RequiredPrivateFixture {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value) -or
        $value -notmatch '^(?:[A-Za-z]:\\|\\\\[^\\]+\\[^\\]+\\)') {
        throw "Provide an absolute caller-owned private fixture path: $Name"
    }
    $path = [IO.Path]::GetFullPath($value)
    $sourcePrefix = $workspaceRoot.TrimEnd('\') + '\'
    if ($path.StartsWith($sourcePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Private fixtures must be outside the source tree: $Name"
    }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Private fixture does not exist: $Name"
    }
    return $path
}
function Get-RequiredPrivateHash {
    param([string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value) -or
        $value -notmatch '\A[0-9a-fA-F]{64}\z') {
        throw "Provide the expected caller-owned fixture SHA-256: $Name"
    }
    return $value.ToUpperInvariant()
}
$maxPath = Get-RequiredPrivateFixture 'F2M_PRIVATE_MAX_FIXTURE'
$fbx001Path = Get-RequiredPrivateFixture 'F2M_PRIVATE_FBX_VARIANT1'
$fbx002Path = Get-RequiredPrivateFixture 'F2M_PRIVATE_FBX_VARIANT2'
$privateEnvironmentValues = @{
    F2M_PRIVATE_MAX_FIXTURE = $maxPath
    F2M_PRIVATE_FBX_VARIANT1 = $fbx001Path
    F2M_PRIVATE_FBX_VARIANT2 = $fbx002Path
    F2M_PRIVATE_MAX_SHA256 = (Get-RequiredPrivateHash 'F2M_PRIVATE_MAX_SHA256')
    F2M_PRIVATE_FBX_VARIANT1_SHA256 = (Get-RequiredPrivateHash 'F2M_PRIVATE_FBX_VARIANT1_SHA256')
    F2M_PRIVATE_FBX_VARIANT2_SHA256 = (Get-RequiredPrivateHash 'F2M_PRIVATE_FBX_VARIANT2_SHA256')
    F2M_PRIVATE_NODE_A = $(if ($env:F2M_PRIVATE_NODE_A) { $env:F2M_PRIVATE_NODE_A } else { 'ExampleMeshA' })
    F2M_PRIVATE_NODE_B = $(if ($env:F2M_PRIVATE_NODE_B) { $env:F2M_PRIVATE_NODE_B } else { 'ExampleMeshB' })
}
$MaxBatchExecutable = [IO.Path]::GetFullPath($MaxBatchExecutable)
$MaxLogPath = [IO.Path]::GetFullPath($MaxLogPath)
$maxRoot = [IO.Path]::GetFullPath(
    (Split-Path -Parent $MaxBatchExecutable)
)
$runToken = [Guid]::NewGuid().ToString('N').ToLowerInvariant()
$environmentValues = @{
    F2M_SELECTION_STRESS_TOKEN = $runToken
    F2M_SELECTION_STRESS_EXPECTED_SCRIPT = $scriptPath
    F2M_SELECTION_STRESS_RESULT = $resultPath
    F2M_SELECTION_STRESS_ITERATIONS = $Iterations.ToString(
        [Globalization.CultureInfo]::InvariantCulture
    )
    F2M_SELECTION_STRESS_MAX_PRIVATE_EXCESS_GROWTH_MB = (
        $MaxPrivateExcessGrowthMiB.ToString(
            [Globalization.CultureInfo]::InvariantCulture
        )
    )
}
foreach ($name in $privateEnvironmentValues.Keys) {
    $environmentValues[$name] = $privateEnvironmentValues[$name]
}
$expectedHashes = @{
    $maxPath = $privateEnvironmentValues.F2M_PRIVATE_MAX_SHA256
    $fbx001Path = $privateEnvironmentValues.F2M_PRIVATE_FBX_VARIANT1_SHA256
    $fbx002Path = $privateEnvironmentValues.F2M_PRIVATE_FBX_VARIANT2_SHA256
}

if (-not (Test-Path -LiteralPath $logGatePath -PathType Leaf)) {
    throw "找不到日志归属门：$logGatePath"
}
. $logGatePath

function Get-AssetHashes {
    param([hashtable]$Expected)
    $actual = @{}
    foreach ($path in $Expected.Keys) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "缺少压力验收资产：$path"
        }
        $actual[$path] = (
            Get-FileHash -LiteralPath $path -Algorithm SHA256
        ).Hash.ToUpperInvariant()
    }
    return $actual
}

function Assert-ExpectedHashes {
    param(
        [hashtable]$Expected,
        [hashtable]$Actual,
        [string]$Phase
    )
    foreach ($path in $Expected.Keys) {
        if ($Actual[$path] -ne $Expected[$path]) {
            throw (
                "$Phase 资产 SHA-256 不匹配：$path；" +
                "期望 $($Expected[$path])，实际 $($Actual[$path])。"
            )
        }
    }
}

function Copy-MaxLogSnapshot {
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
        $deltaLength = $afterBytes.Length - $beforeBytes.Length
        if ($deltaLength -gt 0) {
            $deltaBytes = New-Object byte[] $deltaLength
            [Array]::Copy(
                $afterBytes,
                $beforeBytes.Length,
                $deltaBytes,
                0,
                $deltaLength
            )
        }
    }
    else {
        # 仅记录 Max 的截断/重建事实；异常扫描另由 JSON PID 标记时间窗完成。
        $mode = 'replaced_or_rewritten'
        $deltaBytes = $afterBytes
    }

    return [pscustomobject]@{
        bytes = $deltaBytes
        mode = $mode
        before_length = $beforeBytes.Length
        after_length = $afterBytes.Length
        delta_length = $deltaBytes.Length
    }
}

function Get-CompactErrorText {
    param(
        [AllowNull()]
        [object]$Value,
        [int]$MaximumLength = 2048
    )
    $text = ([string]$Value).Trim()
    if ([string]::IsNullOrWhiteSpace($text)) {
        return '<未提供 error>'
    }
    $text = $text -replace '\s+', ' '
    if ($text.Length -gt $MaximumLength) {
        return $text.Substring(0, $MaximumLength) + '…'
    }
    return $text
}

function Get-OwnedMaxProcesses {
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
    return @(
        $all |
            Where-Object { $wanted.Contains([int]$_.ProcessId) }
    )
}

function Stop-OwnedMaxProcessTree {
    param(
        [int]$RootPid,
        [string]$ExpectedMaxRoot
    )
    $owned = @(Get-OwnedMaxProcesses -RootPid $RootPid)
    foreach ($item in ($owned | Sort-Object ProcessId -Descending)) {
        $name = [IO.Path]::GetFileName([string]$item.ExecutablePath)
        $path = [string]$item.ExecutablePath
        $isMaxProcess = $name -in @('3dsmax.exe', '3dsmaxbatch.exe')
        $isExpectedPath = (
            $path -and
            [IO.Path]::GetFullPath($path).StartsWith(
                $ExpectedMaxRoot,
                [StringComparison]::OrdinalIgnoreCase
            )
        )
        if ($isMaxProcess -and $isExpectedPath) {
            Stop-Process `
                -Id ([int]$item.ProcessId) `
                -Force `
                -ErrorAction SilentlyContinue
        }
    }
}

function Invoke-IsolatedMaxBatch {
    param(
        [string]$Script,
        [hashtable]$Environment,
        [string]$BeforeLog,
        [string]$AfterLog,
        [string]$ListenerLog
    )

    $existing = @(
        Get-Process -Name @('3dsmax', '3dsmaxbatch') `
            -ErrorAction SilentlyContinue
    )
    if ($existing.Count -ne 0) {
        throw (
            '检测到已打开的 3ds Max/Batch，拒绝启动串行发布门阶段：' +
            (($existing | ForEach-Object {
                "$($_.ProcessName):$($_.Id)"
            }) -join ', ')
        )
    }

    Copy-MaxLogSnapshot -Source $MaxLogPath -Destination $BeforeLog
    $previous = @{}
    foreach ($name in $Environment.Keys) {
        $previous[$name] = [Environment]::GetEnvironmentVariable(
            $name,
            [EnvironmentVariableTarget]::Process
        )
    }
    $process = $null
    $owned = New-Object 'System.Collections.Generic.HashSet[int]'
    $exitCode = $null
    $timedOut = $false
    $startedUtc = [DateTime]::UtcNow
    try {
        foreach ($name in $Environment.Keys) {
            [Environment]::SetEnvironmentVariable(
                $name,
                $Environment[$name],
                [EnvironmentVariableTarget]::Process
            )
        }
        $process = Start-Process `
            -FilePath $MaxBatchExecutable `
            -ArgumentList @(
                ('"' + $Script + '"'),
                '-v',
                '5',
                '-listenerlog',
                ('"' + $ListenerLog + '"')
            ) `
            -WindowStyle Hidden `
            -PassThru
        [void]$owned.Add($process.Id)
        $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
        while (
            -not $process.HasExited -and
            [DateTime]::UtcNow -lt $deadline
        ) {
            foreach (
                $item in @(Get-OwnedMaxProcesses -RootPid $process.Id)
            ) {
                [void]$owned.Add([int]$item.ProcessId)
            }
            Start-Sleep -Milliseconds 500
            $process.Refresh()
        }
        if (-not $process.HasExited) {
            $timedOut = $true
            Stop-OwnedMaxProcessTree `
                -RootPid $process.Id `
                -ExpectedMaxRoot $maxRoot
        }
        else {
            $process.WaitForExit()
            $exitCode = $process.ExitCode
        }
    }
    finally {
        foreach ($name in $previous.Keys) {
            [Environment]::SetEnvironmentVariable(
                $name,
                $previous[$name],
                [EnvironmentVariableTarget]::Process
            )
        }
        if ($null -ne $process) {
            try {
                if (-not $process.HasExited) {
                    Stop-OwnedMaxProcessTree `
                        -RootPid $process.Id `
                        -ExpectedMaxRoot $maxRoot
                }
            }
            catch {
                # 专用进程可能在检查与清理之间自行退出。
            }
        }
        Copy-MaxLogSnapshot -Source $MaxLogPath -Destination $AfterLog
    }
    return [pscustomobject]@{
        root_pid = if ($null -eq $process) { 0 } else { $process.Id }
        owned_pids = $owned
        exit_code = $exitCode
        timed_out = $timedOut
        started_utc = $startedUtc
        finished_utc = [DateTime]::UtcNow
    }
}

if (-not (Test-Path -LiteralPath $MaxBatchExecutable -PathType Leaf)) {
    throw "找不到 3ds Max Batch：$MaxBatchExecutable"
}
if (
    [IO.Path]::GetFileName($MaxBatchExecutable) -ine '3dsmaxbatch.exe'
) {
    throw "发布门必须使用 3dsmaxbatch.exe：$MaxBatchExecutable"
}
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    throw "找不到选择切换压力脚本：$scriptPath"
}
if (-not (Test-Path -LiteralPath $rawScriptPath -PathType Leaf)) {
    throw "找不到原生 FBX 对照脚本：$rawScriptPath"
}
$existingMax = @(
    Get-Process -Name @('3dsmax', '3dsmaxbatch') -ErrorAction SilentlyContinue
)
if ($existingMax.Count -ne 0) {
    throw '检测到已打开的 3ds Max/Batch。为避免污染交互会话和 Max.log，压力发布门已拒绝启动。'
}

$assetHashesBefore = Get-AssetHashes -Expected $expectedHashes
Assert-ExpectedHashes `
    -Expected $expectedHashes `
    -Actual $assetHashesBefore `
    -Phase '运行前'

$criticalLogPatterns = @(
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

$rawEnvironment = @{
    F2M_FBX_GC_BASELINE_RESULT = $rawResultPath
    F2M_FBX_GC_BASELINE_ITERATIONS = $Iterations.ToString(
        [Globalization.CultureInfo]::InvariantCulture
    )
}
foreach ($name in $privateEnvironmentValues.Keys) {
    $rawEnvironment[$name] = $privateEnvironmentValues[$name]
}
$rawRun = Invoke-IsolatedMaxBatch `
    -Script $rawScriptPath `
    -Environment $rawEnvironment `
    -BeforeLog $rawBeforeLogPath `
    -AfterLog $rawAfterLogPath `
    -ListenerLog $rawListenerLogPath
$rawErrors = New-Object 'System.Collections.Generic.List[string]'
if ($rawRun.timed_out) {
    $rawErrors.Add("原生对照超过 $TimeoutSeconds 秒，没有自然退出。")
}
if ($null -eq $rawRun.exit_code -or [int]$rawRun.exit_code -ne 0) {
    $rawErrors.Add("原生对照退出码异常：$($rawRun.exit_code)")
}
$rawResult = $null
if (-not (Test-Path -LiteralPath $rawResultPath -PathType Leaf)) {
    $rawErrors.Add("原生对照没有生成 JSON：$rawResultPath")
}
else {
    try {
        $rawResultItem = Get-Item -LiteralPath $rawResultPath
        $rawResult = Get-Content `
            -LiteralPath $rawResultPath `
            -Raw `
            -Encoding UTF8 |
            ConvertFrom-Json
        if (
            $rawResultItem.LastWriteTimeUtc -lt
            $rawRun.started_utc.AddSeconds(-2)
        ) {
            $rawErrors.Add('原生对照 JSON 不是本次运行的新鲜结果。')
        }
    }
    catch {
        $rawErrors.Add("读取原生对照 JSON 失败：$($_.Exception.Message)")
    }
}
$expectedHeavy = 0
for ($index = 0; $index -lt $Iterations; $index++) {
    if (($index % 8) -ge 4) {
        $expectedHeavy += 1
    }
}
$expectedImports = $Iterations + $expectedHeavy
if ($null -ne $rawResult) {
    if (-not $rawRun.owned_pids.Contains([int]$rawResult.pid)) {
        $rawErrors.Add(
            "原生对照 JSON PID $($rawResult.pid) 不属于本次启动树。"
        )
    }
    if (
        $rawResult.ok -ne $true -or
        [int]$rawResult.iterations -ne $Iterations -or
        [int]$rawResult.imported_total -ne $expectedImports -or
        [int]$rawResult.heavy_mixed_iterations -ne $expectedHeavy
    ) {
        $rawErrors.Add(
            "原生对照规模/状态异常：ok=$($rawResult.ok)，" +
            "iterations=$($rawResult.iterations)，" +
            "imports=$($rawResult.imported_total)，" +
            "heavy=$($rawResult.heavy_mixed_iterations)。"
        )
    }
    if (
        $rawResult.delete_strategy -ne
        'single_node_by_handle_immediate_release'
    ) {
        $rawErrors.Add('原生对照未使用逐句柄即时删除策略。')
    }
    if (
        $rawResult.assets.unchanged -ne $true -or
        @($rawResult.production_modules_loaded).Count -ne 0
    ) {
        $rawErrors.Add('原生对照未证明资产不变或生产模块零加载。')
    }
    if (@($rawResult.samples).Count -ne ($Iterations + 1)) {
        $rawErrors.Add('原生对照采样数量不完整。')
    }
    foreach ($sample in @($rawResult.samples)) {
        if (
            ([string]$sample.heap_check).Trim().ToLowerInvariant() -notin
            @('ok', 'true')
        ) {
            $rawErrors.Add(
                "原生对照 heapCheck 异常：$($sample.heap_check)"
            )
        }
        if (
            $sample.phase -eq 'iteration' -and
            $sample.scene.node_identity_sha256 -ne
            $rawResult.baseline_scene.node_identity_sha256
        ) {
            $rawErrors.Add(
                "原生对照第 $($sample.index) 轮场景身份未恢复。"
            )
        }
    }
    if ([int64]$rawResult.private_usage_growth -lt 0) {
        $rawErrors.Add('原生对照私有内存增长为负，数据不可接受。')
    }
}
$rawLogDelta = $null
try {
    $rawLogDelta = Get-FileByteDelta `
        -BeforePath $rawBeforeLogPath `
        -AfterPath $rawAfterLogPath
}
catch {
    $rawErrors.Add("无法读取原生对照 Max.log 快照：$($_.Exception.Message)")
}
$rawMaxWindow = $null
$rawListenerWindow = $null
if ($null -ne $rawResult) {
    $rawPid = [int]$rawResult.pid
    $rawPidPattern = [regex]::Escape(([string]$rawPid))
    $rawBeginPattern = (
        '^F2M_RAW_FBX_GC_BASELINE_BEGIN\s+PID=' + $rawPidPattern +
        '\s+UTC=\S+\s*$'
    )
    $rawEndPattern = (
        '^F2M_RAW_FBX_GC_BASELINE_END\s+PID=' + $rawPidPattern +
        '\s+UTC=\S+\s+OK=true\s*$'
    )
    try {
        $rawMaxLogText = Read-F2MLogTextStrict -Path $rawAfterLogPath
        $rawMaxWindow = Get-F2MMarkerWindow `
            -Text $rawMaxLogText `
            -TargetPid $rawPid `
            -BeginMessagePattern $rawBeginPattern `
            -EndMessagePattern $rawEndPattern `
            -StructuredMaxLog
        if (
            $rawMaxWindow.begin_utc -lt
            $rawRun.started_utc.AddSeconds(-2) -or
            $rawMaxWindow.end_utc -gt
            $rawRun.finished_utc.AddSeconds(2)
        ) {
            $rawErrors.Add(
                '原生对照 Max.log 的 PID 标记不在本次启动器 UTC 时间窗内。'
            )
        }
    }
    catch {
        $rawErrors.Add(
            "原生对照 Max.log PID 时间片不可接受：$($_.Exception.Message)"
        )
    }
    try {
        $rawListenerText = Read-F2MLogTextStrict -Path $rawListenerLogPath
        $rawListenerWindow = Get-F2MMarkerWindow `
            -Text $rawListenerText `
            -TargetPid $rawPid `
            -BeginMessagePattern $rawBeginPattern `
            -EndMessagePattern $rawEndPattern
        if (
            $rawListenerWindow.begin_utc -lt
            $rawRun.started_utc.AddSeconds(-2) -or
            $rawListenerWindow.end_utc -gt
            $rawRun.finished_utc.AddSeconds(2)
        ) {
            $rawErrors.Add(
                '原生对照 listener 的 PID 标记不在本次启动器 UTC 时间窗内。'
            )
        }
    }
    catch {
        $rawErrors.Add(
            "原生对照 listener PID 时间片不可接受：$($_.Exception.Message)"
        )
    }
}
$utf8NoBom = New-Object Text.UTF8Encoding($false)
$rawMaxWindowText = if ($null -eq $rawMaxWindow) {
    ''
}
else {
    [string]$rawMaxWindow.text
}
$rawListenerWindowText = if ($null -eq $rawListenerWindow) {
    ''
}
else {
    [string]$rawListenerWindow.text
}
[IO.File]::WriteAllText(
    $rawSliceLogPath,
    $rawMaxWindowText,
    $utf8NoBom
)
[IO.File]::WriteAllText(
    $rawListenerSliceLogPath,
    $rawListenerWindowText,
    $utf8NoBom
)
foreach (
    $pattern in @(
        Get-F2MCriticalLogHits `
            -Text $rawMaxWindowText `
            -Patterns $criticalLogPatterns
    )
) {
    $rawErrors.Add(
        "原生对照 Max.log 当前 PID 从 BEGIN 到退出尾部命中异常：$pattern"
    )
}
foreach (
    $pattern in @(
        Get-F2MCriticalLogHits `
            -Text $rawListenerWindowText `
            -Patterns $criticalLogPatterns
    )
) {
    $rawErrors.Add("原生对照 listener 当前 PID 时间片命中异常：$pattern")
}
$betweenRuns = @(
    Get-Process -Name @('3dsmax', '3dsmaxbatch') `
        -ErrorAction SilentlyContinue
)
if ($betweenRuns.Count -ne 0) {
    $rawErrors.Add('原生对照后仍有 Max 进程，插件阶段已拒绝启动。')
}
$assetHashesAfterRaw = Get-AssetHashes -Expected $expectedHashes
try {
    Assert-ExpectedHashes `
        -Expected $expectedHashes `
        -Actual $assetHashesAfterRaw `
        -Phase '原生对照后'
}
catch {
    $rawErrors.Add($_.Exception.Message)
}
foreach ($path in $expectedHashes.Keys) {
    if ($assetHashesBefore[$path] -ne $assetHashesAfterRaw[$path]) {
        $rawErrors.Add("原生对照修改了冻结资产：$path")
    }
}
if ($rawErrors.Count -ne 0) {
    throw (
        "原生 FBX 对照前置失败：`n- " +
        ($rawErrors -join "`n- ")
    )
}

$environmentValues[
    'F2M_SELECTION_STRESS_RAW_PRIVATE_GROWTH_BYTES'
] = ([int64]$rawResult.private_usage_growth).ToString(
    [Globalization.CultureInfo]::InvariantCulture
)
$pluginRun = Invoke-IsolatedMaxBatch `
    -Script $scriptPath `
    -Environment $environmentValues `
    -BeforeLog $beforeLogPath `
    -AfterLog $afterLogPath `
    -ListenerLog $listenerLogPath
$ownedPids = $pluginRun.owned_pids
$exitCode = $pluginRun.exit_code
$timedOut = $pluginRun.timed_out
$runStartedUtc = $pluginRun.started_utc
$runFinishedUtc = $pluginRun.finished_utc
$assetHashesAfter = Get-AssetHashes -Expected $expectedHashes

$gateErrors = New-Object 'System.Collections.Generic.List[string]'
if ($timedOut) {
    $gateErrors.Add(
        "专用 MaxBatch 进程超过 $TimeoutSeconds 秒；只清理了该启动树。"
    )
}
if ($null -eq $exitCode) {
    $gateErrors.Add('专用 MaxBatch 没有可接受的退出码。')
}
elseif ($exitCode -ne 0) {
    $gateErrors.Add("专用 MaxBatch 退出码不是 0：$exitCode")
}
try {
    Assert-ExpectedHashes `
        -Expected $expectedHashes `
        -Actual $assetHashesAfter `
        -Phase '运行后'
}
catch {
    $gateErrors.Add($_.Exception.Message)
}
foreach ($path in $expectedHashes.Keys) {
    if ($assetHashesAfter[$path] -ne $assetHashesBefore[$path]) {
        $gateErrors.Add("压力验收改写了用户资产：$path")
    }
}

$result = $null
if (-not (Test-Path -LiteralPath $resultPath -PathType Leaf)) {
    $gateErrors.Add("专用进程没有生成业务 JSON：$resultPath")
}
else {
    try {
        $result = Get-Content -LiteralPath $resultPath -Raw -Encoding UTF8 |
            ConvertFrom-Json
    }
    catch {
        $gateErrors.Add("无法读取业务 JSON：$($_.Exception.Message)")
    }
}
if ($null -ne $result) {
    if ($result.token -ne $runToken) {
        $gateErrors.Add('业务 JSON 单次令牌不匹配，拒绝接受旧结果。')
    }
    $resultPid = [int]$result.pid
    if (-not $ownedPids.Contains($resultPid)) {
        $gateErrors.Add(
            "业务 JSON PID $resultPid 不属于本次 MaxBatch 启动树。"
        )
    }
    if (
        $result.state -ne 'finished' -or
        $result.ok -ne $true
    ) {
        $compactError = Get-CompactErrorText -Value $result.error
        $gateErrors.Add(
            "选择切换压力业务未通过：error=$compactError；" +
            "轮次=$($result.completed_iterations)/$($result.iterations)"
        )
    }
    if (
        [int]$result.iterations -ne $Iterations -or
        [int]$result.completed_iterations -ne $Iterations
    ) {
        $gateErrors.Add(
            "业务 JSON 轮次不完整：$($result.completed_iterations)/$Iterations"
        )
    }
    if ([int]$result.heavy_mixed_iterations -lt 4) {
        $gateErrors.Add(
            "混合法线+光滑组重路径不足：$($result.heavy_mixed_iterations)/4"
        )
    }
    if ($result.assets.unchanged -ne $true) {
        $gateErrors.Add('业务 JSON 未证明三份用户资产保持不变。')
    }
    $expectedRawGrowth = [int64]$rawResult.private_usage_growth
    $expectedExcessBudget = [int64]$MaxPrivateExcessGrowthMiB * 1MB
    if (
        [int64]$result.paired_raw_baseline.private_usage_growth -ne
        $expectedRawGrowth -or
        [int64]$result.memory_gate.raw_private_usage_growth -ne
        $expectedRawGrowth
    ) {
        $gateErrors.Add('插件业务 JSON 没有绑定本次原生对照增长。')
    }
    if (
        [int64]$result.memory_gate.max_private_excess_growth_allowed -ne
        $expectedExcessBudget
    ) {
        $gateErrors.Add('插件业务 JSON 的额外私有内存预算不一致。')
    }
    if (
        [int64]$result.memory_gate.private_usage_excess_over_raw -gt
        $expectedExcessBudget
    ) {
        $gateErrors.Add(
            "插件相对原生对照的额外增长超限：" +
            "$($result.memory_gate.private_usage_excess_over_raw)/" +
            "$expectedExcessBudget 字节。"
        )
    }
    foreach ($sample in @($result.samples)) {
        if ($null -ne $sample.heap) {
            $heapCheckStatus = (
                ([string]$sample.heap.heap_check).Trim().ToLowerInvariant()
            )
            if ($heapCheckStatus -notin @('ok', 'true')) {
                $gateErrors.Add(
                    "业务 JSON 发现 heapCheck 异常：$($sample.heap.heap_check)"
                )
            }
        }
        if ($null -ne $sample.scene) {
            if (@($sample.scene.temporary_nodes).Count -ne 0) {
                $gateErrors.Add('业务 JSON 发现残留 F2M 临时节点。')
            }
            if (@($sample.scene.temporary_modifiers).Count -ne 0) {
                $gateErrors.Add('业务 JSON 发现残留 F2M 临时修改器。')
            }
        }
    }
}

$listenerLogSlice = ''
if ($null -ne $result) {
    $resultPid = [int]$result.pid
    $escapedToken = [regex]::Escape($runToken)
    $escapedResultPid = [regex]::Escape(([string]$resultPid))
    $expectedMarkerOk = if ([bool]$result.ok) { 'true' } else { 'false' }
    $pluginBeginPattern = (
        '^F2M_SELECTION_GC_STRESS_BEGIN\s+TOKEN=' + $escapedToken +
        '\s+PID=' + $escapedResultPid + '\s+UTC=\S+\s*$'
    )
    $pluginEndPattern = (
        '^F2M_SELECTION_GC_STRESS_END\s+TOKEN=' + $escapedToken +
        '\s+PID=' + $escapedResultPid + '\s+UTC=\S+\s+OK=' +
        $expectedMarkerOk + '\s*$'
    )
    try {
        $listenerLogText = Read-F2MLogTextStrict -Path $listenerLogPath
        $listenerWindow = Get-F2MMarkerWindow `
            -Text $listenerLogText `
            -TargetPid $resultPid `
            -BeginMessagePattern $pluginBeginPattern `
            -EndMessagePattern $pluginEndPattern
        $listenerLogSlice = [string]$listenerWindow.text
        if (
            $listenerWindow.begin_utc -lt
            $pluginRun.started_utc.AddSeconds(-2) -or
            $listenerWindow.end_utc -gt
            $pluginRun.finished_utc.AddSeconds(2)
        ) {
            $gateErrors.Add(
                'listener 的令牌/PID 标记不在本次启动器 UTC 时间窗内。'
            )
        }
    }
    catch {
        $gateErrors.Add(
            "listener 令牌/PID 时间片不可接受：$($_.Exception.Message)"
        )
    }
}
[IO.File]::WriteAllText(
    $listenerSliceLogPath,
    $listenerLogSlice,
    $utf8NoBom
)

$maxLogDelta = $null
try {
    $maxLogDelta = Get-FileByteDelta `
        -BeforePath $beforeLogPath `
        -AfterPath $afterLogPath
}
catch {
    $gateErrors.Add("无法读取插件阶段 Max.log 快照：$($_.Exception.Message)")
}
$maxLogWindowText = ''
if ($null -ne $result) {
    try {
        $maxLogText = Read-F2MLogTextStrict -Path $afterLogPath
        $maxLogWindow = Get-F2MMarkerWindow `
            -Text $maxLogText `
            -TargetPid ([int]$result.pid) `
            -BeginMessagePattern $pluginBeginPattern `
            -EndMessagePattern $pluginEndPattern `
            -StructuredMaxLog
        $maxLogWindowText = [string]$maxLogWindow.text
        if (
            $maxLogWindow.begin_utc -lt
            $pluginRun.started_utc.AddSeconds(-2) -or
            $maxLogWindow.end_utc -gt
            $pluginRun.finished_utc.AddSeconds(2)
        ) {
            $gateErrors.Add(
                'Max.log 的令牌/PID 标记不在本次启动器 UTC 时间窗内。'
            )
        }
    }
    catch {
        $gateErrors.Add(
            "Max.log 令牌/PID 时间片不可接受：$($_.Exception.Message)"
        )
    }
}
[IO.File]::WriteAllText(
    $sliceLogPath,
    $maxLogWindowText,
    $utf8NoBom
)
foreach (
    $pattern in @(
        Get-F2MCriticalLogHits `
            -Text $maxLogWindowText `
            -Patterns $criticalLogPatterns
    )
) {
    $gateErrors.Add(
        "Max.log 当前 JSON PID 从 BEGIN 到退出尾部命中异常：$pattern"
    )
}
foreach (
    $pattern in @(
        Get-F2MCriticalLogHits `
            -Text $listenerLogSlice `
            -Patterns $criticalLogPatterns
    )
) {
    $gateErrors.Add("listener 当前 JSON PID/令牌时间片命中异常：$pattern")
}
if ($runFinishedUtc -lt $runStartedUtc) {
    $gateErrors.Add('启动器 UTC 时间窗口无效。')
}

$remainingMax = @(
    Get-Process -Name @('3dsmax', '3dsmaxbatch') -ErrorAction SilentlyContinue
)
if ($remainingMax.Count -ne 0) {
    $gateErrors.Add(
        '压力验收结束后仍存在 3ds Max/Batch 进程：' +
        (($remainingMax | ForEach-Object { "$($_.ProcessName):$($_.Id)" }) -join ', ')
    )
}

if ($gateErrors.Count -ne 0) {
    throw (
        "选择切换 MAXScript GC 发布门失败：`n- " +
        ($gateErrors -join "`n- ")
    )
}

[pscustomobject]@{
    ok = $true
    token = $runToken
    launcher_pid = $PID
    maxbatch_pid = [int]$pluginRun.root_pid
    engine_pid = [int]$result.pid
    iterations = $Iterations
    heavy_mixed_iterations = [int]$result.heavy_mixed_iterations
    exit_code = $exitCode
    started_at_utc = $runStartedUtc.ToString('o')
    finished_at_utc = $runFinishedUtc.ToString('o')
    business_result = $resultPath
    max_log_before = $beforeLogPath
    max_log_after = $afterLogPath
    max_log_current_slice = $sliceLogPath
    max_log_audit_boundary = 'target_pid_last_structured_line_after_process_exit'
    max_log_post_end_line_count = [int]$maxLogWindow.post_end_line_count
    max_log_delta_mode = $maxLogDelta.mode
    max_log_delta_bytes = [int64]$maxLogDelta.delta_length
    listener_log = $listenerLogPath
    listener_log_current_slice = $listenerSliceLogPath
    raw_baseline_result = $rawResultPath
    raw_maxbatch_pid = [int]$rawRun.root_pid
    raw_engine_pid = [int]$rawResult.pid
    raw_private_usage_growth = [int64]$rawResult.private_usage_growth
    plugin_private_usage_growth = (
        [int64]$result.memory_gate.private_usage_growth
    )
    plugin_private_usage_excess_over_raw = (
        [int64]$result.memory_gate.private_usage_excess_over_raw
    )
    max_private_excess_growth_allowed = (
        [int64]$result.memory_gate.max_private_excess_growth_allowed
    )
    raw_max_log_current_slice = $rawSliceLogPath
    raw_max_log_audit_boundary = 'target_pid_last_structured_line_after_process_exit'
    raw_max_log_post_end_line_count = [int]$rawMaxWindow.post_end_line_count
    raw_max_log_delta_mode = $rawLogDelta.mode
    raw_max_log_delta_bytes = [int64]$rawLogDelta.delta_length
    raw_listener_log = $rawListenerLogPath
    raw_listener_log_current_slice = $rawListenerSliceLogPath
    asset_hashes = $assetHashesAfter
}
