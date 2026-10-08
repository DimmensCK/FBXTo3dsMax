param(
    [string]$MaxBatchExecutable =
        'D:\Autodesk\3dsmax2023\3ds Max 2023\3dsmaxbatch.exe',
    [int]$TimeoutSeconds = 300
)

$ErrorActionPreference = 'Stop'
$testsRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$scriptPath = Join-Path $testsRoot 'max_procedural_selfcheck.py'
$resultPath = Join-Path $testsRoot '_max_procedural_selfcheck_result.txt'
$listenerPath = Join-Path $testsRoot '_max_procedural_gcfix_v1320.listener.log'
$pidLogPath = Join-Path $testsRoot '_max_procedural_gcfix_v1320.Max.log'
$metaPath = Join-Path $testsRoot '_max_procedural_gcfix_v1320.meta.json'
$maxLogPath = Join-Path $env:LOCALAPPDATA (
    'Autodesk\3dsMax\2023 - 64bit\CHS\Network\Max.log'
)

if (-not (Test-Path -LiteralPath $MaxBatchExecutable -PathType Leaf)) {
    throw "3ds Max Batch not found: $MaxBatchExecutable"
}
if ([IO.Path]::GetFileName($MaxBatchExecutable) -ine '3dsmaxbatch.exe') {
    throw "The procedural gate requires 3dsmaxbatch.exe: $MaxBatchExecutable"
}
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    throw "Procedural test script not found: $scriptPath"
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

$quotedScript = '"' + $scriptPath + '"'
$quotedListener = '"' + $listenerPath + '"'
$startedAtUtc = [DateTime]::UtcNow
$process = Start-Process `
    -FilePath $MaxBatchExecutable `
    -ArgumentList @(
        $quotedScript,
        '-v',
        '5',
        '-listenerlog',
        $quotedListener
    ) `
    -WindowStyle Hidden `
    -PassThru

if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
    throw "The procedural gate did not exit within $TimeoutSeconds seconds."
}
$process.WaitForExit()
$finishedAtUtc = [DateTime]::UtcNow
$exitCode = $process.ExitCode

if (-not (Test-Path -LiteralPath $resultPath -PathType Leaf)) {
    throw 'The procedural gate did not create its business result.'
}
$businessText = Get-Content -LiteralPath $resultPath -Raw -Encoding UTF8
$pidMatch = [regex]::Match(
    $businessText,
    '(?m)^ENGINE_PID=(?<pid>\d+)\s*$'
)
if (-not $pidMatch.Success) {
    throw 'The procedural gate result is missing the engine PID.'
}
$enginePid = [int]$pidMatch.Groups['pid'].Value

$allLines = @()
if (Test-Path -LiteralPath $maxLogPath -PathType Leaf) {
    $allLines = @(
        Get-Content -LiteralPath $maxLogPath -Encoding Default
    )
}
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
$pidLines = @(
    $deltaLines | Where-Object { [string]$_ -match $pidPattern }
)
$pidLines | Set-Content -LiteralPath $pidLogPath -Encoding UTF8

$localizedGcPattern = (
    'MAXScript ' +
    [char]0x5185 + [char]0x5B58 + [char]0x6536 + [char]0x96C6 +
    [char]0x9519 + [char]0x8BEF
)
$nativeGcErrors = @(
    $pidLines | Where-Object {
        [string]$_ -match (
            [regex]::Escape($localizedGcPattern) + '|' +
            'MAXScript Garbage Collection Error|' +
            'Unknown system exception|' +
            'Exception in MAXScript Garbage Collector'
        )
    }
)
$businessPassed = $businessText.StartsWith(
    'PASS',
    [StringComparison]::Ordinal
)
$meta = [ordered]@{
    schema_version = 1
    test = 'procedural mapped-channel and temporary-node GC gate'
    started_at_utc = $startedAtUtc.ToString('o')
    finished_at_utc = $finishedAtUtc.ToString('o')
    exit_code = $exitCode
    engine_pid = $enginePid
    business_pass = $businessPassed
    pid_log_line_count = $pidLines.Count
    native_gc_error_count = $nativeGcErrors.Count
    native_gc_error_lines = @($nativeGcErrors)
    result_path = $resultPath
    pid_log_path = $pidLogPath
}
$meta | ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath $metaPath -Encoding UTF8

if ($exitCode -ne 0) {
    throw "The procedural gate returned exit code $exitCode."
}
if (-not $businessPassed) {
    throw "The procedural business check failed: $businessText"
}
if ($pidLines.Count -eq 0) {
    throw "No structured Max.log lines were found for engine PID $enginePid."
}
if ($nativeGcErrors.Count -ne 0) {
    throw (
        "Engine PID $enginePid emitted $($nativeGcErrors.Count) " +
        "native GC errors before shutdown completed."
    )
}

$meta | ConvertTo-Json -Depth 6
