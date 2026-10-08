param(
    [string]$MaxBatchExecutable =
        'D:\Autodesk\3dsmax2023\3ds Max 2023\3dsmaxbatch.exe',
    [int]$TimeoutSeconds = 300,
    [switch]$DisableNormals,
    [switch]$DisableSmoothing
)

$ErrorActionPreference = 'Stop'
$testsRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$scriptPath = Join-Path $testsRoot 'max_topology_fbx_gc_gate_v1320.py'
$resultPath = Join-Path $testsRoot '_max_topology_fbx_gc_gate_v1320_result.json'
$listenerPath = Join-Path $testsRoot '_max_topology_fbx_gc_gate_v1320.listener.log'
$pidLogPath = Join-Path $testsRoot '_max_topology_fbx_gc_gate_v1320.Max.log'
$metaPath = Join-Path $testsRoot '_max_topology_fbx_gc_gate_v1320.meta.json'
$maxLogPath = Join-Path $env:LOCALAPPDATA (
    'Autodesk\3dsMax\2023 - 64bit\CHS\Network\Max.log'
)

if (-not (Test-Path -LiteralPath $MaxBatchExecutable -PathType Leaf)) {
    throw "3ds Max Batch not found: $MaxBatchExecutable"
}
if ([IO.Path]::GetFileName($MaxBatchExecutable) -ine '3dsmaxbatch.exe') {
    throw "The topology gate requires 3dsmaxbatch.exe: $MaxBatchExecutable"
}

$beforeLineCount = 0
if (Test-Path -LiteralPath $maxLogPath -PathType Leaf) {
    $beforeLineCount = @(
        Get-Content -LiteralPath $maxLogPath -Encoding Default
    ).Count
}
foreach ($path in @($resultPath, $listenerPath, $pidLogPath, $metaPath)) {
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force
    }
}

$startedAtUtc = [DateTime]::UtcNow
$environmentValues = [ordered]@{
    F2M_TOPOLOGY_GATE_DISABLE_NORMALS = $(
        if ($DisableNormals) { '1' } else { $null }
    )
    F2M_TOPOLOGY_GATE_DISABLE_SMOOTHING = $(
        if ($DisableSmoothing) { '1' } else { $null }
    )
}
$previousEnvironment = @{}
try {
    foreach ($name in $environmentValues.Keys) {
        $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable(
            $name,
            [EnvironmentVariableTarget]::Process
        )
        [Environment]::SetEnvironmentVariable(
            $name,
            $environmentValues[$name],
            [EnvironmentVariableTarget]::Process
        )
    }
    $process = Start-Process `
        -FilePath $MaxBatchExecutable `
        -ArgumentList @(
            '"' + $scriptPath + '"',
            '-v',
            '5',
            '-listenerlog',
            '"' + $listenerPath + '"'
        ) `
        -WindowStyle Hidden `
        -PassThru
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        throw "The topology gate exceeded $TimeoutSeconds seconds."
    }
    $process.Refresh()
}
finally {
    foreach ($name in $environmentValues.Keys) {
        [Environment]::SetEnvironmentVariable(
            $name,
            $previousEnvironment[$name],
            [EnvironmentVariableTarget]::Process
        )
    }
}
$finishedAtUtc = [DateTime]::UtcNow
$exitCode = $process.ExitCode

if (-not (Test-Path -LiteralPath $resultPath -PathType Leaf)) {
    throw 'The topology gate did not create its business result.'
}
$business = Get-Content -LiteralPath $resultPath -Raw -Encoding UTF8 |
    ConvertFrom-Json
$enginePid = [int]$business.engine_pid
if ($enginePid -le 0) {
    throw 'The topology gate result is missing the engine PID.'
}

$allLines = @(
    Get-Content -LiteralPath $maxLogPath -Encoding Default
)
$deltaLines = if ($allLines.Count -ge $beforeLineCount) {
    @($allLines | Select-Object -Skip $beforeLineCount)
}
else {
    @($allLines)
}
# Max.log zero-pads small process IDs; keep the square-bracket field boundary.
$pidPattern = '\[0*' +
    [regex]::Escape(([string]$enginePid)) +
    '\]'
$pidLines = [string[]]@(
    $deltaLines |
        ForEach-Object { [string]$_ } |
        Where-Object { $_ -match $pidPattern }
)
$pidLines | Set-Content -LiteralPath $pidLogPath -Encoding UTF8

$localizedGcPattern = (
    'MAXScript ' +
    [char]0x5185 + [char]0x5B58 + [char]0x6536 + [char]0x96C6 +
    [char]0x9519 + [char]0x8BEF
)
$nativeErrors = [string[]]@(
    $pidLines | Where-Object {
        $_ -match (
            [regex]::Escape($localizedGcPattern) + '|' +
            'MAXScript Garbage Collection Error|' +
            'Unknown system exception|' +
            'Exception in MAXScript Garbage Collector'
        )
    }
)
$businessPassed = (
    $business.ok -eq $true -and
    -not [string]$business.error -and
    -not [string]$business.cleanup_error
)
$meta = [ordered]@{
    schema_version = 1
    test = 'isolated real-FBX topology lifecycle gate'
    normals_enabled = -not [bool]$DisableNormals
    smoothing_enabled = -not [bool]$DisableSmoothing
    started_at_utc = $startedAtUtc.ToString('o')
    finished_at_utc = $finishedAtUtc.ToString('o')
    exit_code = $exitCode
    engine_pid = $enginePid
    business_pass = $businessPassed
    pid_log_line_count = $pidLines.Count
    native_error_count = $nativeErrors.Count
    native_error_lines = @($nativeErrors)
    result_path = $resultPath
    pid_log_path = $pidLogPath
}
$meta | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $metaPath -Encoding UTF8

if ($exitCode -ne 0 -or -not $businessPassed) {
    throw 'The topology business gate failed.'
}
if ($pidLines.Count -eq 0) {
    throw "No structured Max.log lines were found for engine PID $enginePid."
}
if ($nativeErrors.Count -ne 0) {
    throw (
        "Engine PID $enginePid emitted $($nativeErrors.Count) " +
        "native errors before shutdown completed."
    )
}

$meta | ConvertTo-Json -Depth 8
