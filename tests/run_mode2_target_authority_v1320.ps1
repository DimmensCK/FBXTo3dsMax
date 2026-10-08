param(
    [string]$MaxBatchExecutable =
        'D:\Autodesk\3dsmax2023\3ds Max 2023\3dsmaxbatch.exe',
    [int]$TimeoutSeconds = 600
)

$ErrorActionPreference = 'Stop'
$testsRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$scriptPath = Join-Path $testsRoot 'max_mode2_target_authority_v1320.py'
$resultPath = Join-Path $testsRoot '_max_mode2_target_authority_v1320_result.json'
$listenerPath = Join-Path $testsRoot '_max_mode2_target_authority_v1320.listener.log'
$pidLogPath = Join-Path $testsRoot '_max_mode2_target_authority_v1320.Max.log'
$metaPath = Join-Path $testsRoot '_max_mode2_target_authority_v1320.meta.json'
$maxLogPath = Join-Path $env:LOCALAPPDATA (
    'Autodesk\3dsMax\2023 - 64bit\CHS\Network\Max.log'
)

if (-not (Test-Path -LiteralPath $MaxBatchExecutable -PathType Leaf)) {
    throw "3ds Max Batch not found: $MaxBatchExecutable"
}
if ([IO.Path]::GetFileName($MaxBatchExecutable) -ine '3dsmaxbatch.exe') {
    throw "The mode-2 gate requires 3dsmaxbatch.exe: $MaxBatchExecutable"
}
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    throw "Mode-2 gate script not found: $scriptPath"
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
    try {
        & taskkill.exe /PID $process.Id /T /F | Out-Null
    }
    catch {
        try {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
        catch {
        }
    }
    throw "The mode-2 gate did not exit within $TimeoutSeconds seconds."
}
$process.WaitForExit()
$finishedAtUtc = [DateTime]::UtcNow
$exitCode = $process.ExitCode

if (-not (Test-Path -LiteralPath $resultPath -PathType Leaf)) {
    throw 'The mode-2 gate did not create its business result.'
}
$business = Get-Content -LiteralPath $resultPath -Raw -Encoding UTF8 |
    ConvertFrom-Json
$enginePid = [int]$business.engine_pid
if ($enginePid -le 0) {
    throw 'The mode-2 gate result is missing the engine PID.'
}

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
$expectedWriteMethod = (
    [char]0x9010 + [char]0x9876 + [char]0x70B9 +
    [char]0x6743 + [char]0x5A01 + [char]0x5199 + [char]0x5165
)
$businessPassed = (
    $business.ok -eq $true -and
    [string]$business.result.weight_write_method -eq $expectedWriteMethod -and
    -not [string]$business.result.bulk_fallback_reason -and
    $business.result.source_sentinel_verified -eq $true -and
    $business.result.authority_content_verified -eq $true -and
    $business.result.saved_and_reloaded -eq $true -and
    $business.result.scene_bone_handles_preserved -eq $true -and
    -not [string]$business.cleanup_error
)
$meta = [ordered]@{
    schema_version = 1
    test = 'mode-2 target FBX authority and Skin remap gate'
    run_token = [string]$business.run_token
    started_at_utc = $startedAtUtc.ToString('o')
    finished_at_utc = $finishedAtUtc.ToString('o')
    exit_code = $exitCode
    engine_pid = $enginePid
    module_path = [string]$business.module_path
    module_sha256 = [string]$business.module_sha256
    fixture = [string]$business.fixture
    fixture_sha256 = [string]$business.fixture_sha256
    business_pass = $businessPassed
    mesh_count = [int]$business.result.mesh_count
    verified_vertices = [int]$business.result.verified_vertices
    verified_bone_slots = [int]$business.result.verified_bone_slots
    source_sentinel_verified = [bool]$business.result.source_sentinel_verified
    authority_content_verified = [bool]$business.result.authority_content_verified
    saved_and_reloaded = [bool]$business.result.saved_and_reloaded
    scene_bone_handles_preserved = [bool]$business.result.scene_bone_handles_preserved
    weight_write_method = [string]$business.result.weight_write_method
    bulk_fallback_reason = [string]$business.result.bulk_fallback_reason
    pid_log_line_count = $pidLines.Count
    native_gc_error_count = $nativeGcErrors.Count
    native_gc_error_lines = @($nativeGcErrors)
    result_path = $resultPath
    pid_log_path = $pidLogPath
}
$meta | ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath $metaPath -Encoding UTF8

if ($exitCode -ne 0) {
    throw "The mode-2 gate returned exit code $exitCode."
}
if (-not $businessPassed) {
    throw 'The mode-2 target-authority business assertions failed.'
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
