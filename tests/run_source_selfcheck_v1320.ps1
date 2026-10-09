param(
    [string]$MaxBatchExecutable =
        'D:\Autodesk\3dsmax2023\3ds Max 2023\3dsmaxbatch.exe',
    [int]$TimeoutSeconds = 900,
    [string]$ArtifactStem = '_max_source_selfcheck_v1320_current',
    [string]$SelfCheckScript = ''
)

$ErrorActionPreference = 'Stop'
$testsRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$projectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $testsRoot))
$scriptPath = if ([string]::IsNullOrWhiteSpace($SelfCheckScript)) {
    Join-Path $projectRoot 'contents\f2m_selfcheck.py'
}
else {
    [IO.Path]::GetFullPath($SelfCheckScript)
}
$resultPath = Join-Path $testsRoot ($ArtifactStem + '.json')
$progressPath = Join-Path $testsRoot ($ArtifactStem + '.progress.json')
$cancelPath = Join-Path $testsRoot ($ArtifactStem + '.cancel.json')
$listenerPath = Join-Path $testsRoot ($ArtifactStem + '.listener.log')
$pidLogPath = Join-Path $testsRoot ($ArtifactStem + '.Max.log')
$metaPath = Join-Path $testsRoot ($ArtifactStem + '.meta.json')
$maxLogPath = Join-Path $env:LOCALAPPDATA (
    'Autodesk\3dsMax\2023 - 64bit\CHS\Network\Max.log'
)

if (-not (Test-Path -LiteralPath $MaxBatchExecutable -PathType Leaf)) {
    throw "3ds Max Batch not found: $MaxBatchExecutable"
}
if ([IO.Path]::GetFileName($MaxBatchExecutable) -ine '3dsmaxbatch.exe') {
    throw "The full self-check requires 3dsmaxbatch.exe: $MaxBatchExecutable"
}
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    throw "Full self-check script not found: $scriptPath"
}
$scriptSha256 = (
    Get-FileHash -Algorithm SHA256 -LiteralPath $scriptPath
).Hash
if ($ArtifactStem -notmatch '^_[A-Za-z0-9_.-]+$') {
    throw "Unsafe artifact stem: $ArtifactStem"
}

$beforeLineCount = 0
if (Test-Path -LiteralPath $maxLogPath -PathType Leaf) {
    $beforeLineCount = @(
        Get-Content -LiteralPath $maxLogPath -Encoding Default
    ).Count
}
$artifactPaths = @(
    $resultPath,
    $progressPath,
    $cancelPath,
    $listenerPath,
    $pidLogPath,
    $metaPath
)
foreach ($path in $artifactPaths) {
    $resolvedParent = [IO.Path]::GetFullPath((Split-Path -Parent $path))
    if ($resolvedParent -ne $testsRoot) {
        throw "Artifact escaped tests directory: $path"
    }
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force
    }
}

$environmentNames = @(
    'F2M_SELFCHECK_CHILD',
    'F2M_SELFCHECK_RESULT',
    'F2M_SELFCHECK_PROGRESS',
    'F2M_SELFCHECK_CANCEL'
)
$previousEnvironment = @{}
foreach ($name in $environmentNames) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable(
        $name,
        [EnvironmentVariableTarget]::Process
    )
}

$process = $null
$startedAtUtc = [DateTime]::UtcNow
try {
    [Environment]::SetEnvironmentVariable(
        'F2M_SELFCHECK_CHILD',
        '1',
        [EnvironmentVariableTarget]::Process
    )
    [Environment]::SetEnvironmentVariable(
        'F2M_SELFCHECK_RESULT',
        $resultPath,
        [EnvironmentVariableTarget]::Process
    )
    [Environment]::SetEnvironmentVariable(
        'F2M_SELFCHECK_PROGRESS',
        $progressPath,
        [EnvironmentVariableTarget]::Process
    )
    [Environment]::SetEnvironmentVariable(
        'F2M_SELFCHECK_CANCEL',
        $cancelPath,
        [EnvironmentVariableTarget]::Process
    )
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
        throw "The full self-check exceeded $TimeoutSeconds seconds."
    }
    # The timed wait already establishes process exit.  Refresh once before
    # reading ExitCode; do not add a second unbounded wait.
    $process.Refresh()
}
finally {
    foreach ($name in $environmentNames) {
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
    throw 'The full self-check did not create its business result.'
}
if (-not (Test-Path -LiteralPath $progressPath -PathType Leaf)) {
    throw 'The full self-check did not create its progress result.'
}
$business = Get-Content -LiteralPath $resultPath -Raw -Encoding UTF8 |
    ConvertFrom-Json
$progress = Get-Content -LiteralPath $progressPath -Raw -Encoding UTF8 |
    ConvertFrom-Json
$enginePid = [int]$progress.child_pid
if ($enginePid -le 0) {
    throw 'The full self-check progress is missing the engine PID.'
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
$nativePatterns = (
    [regex]::Escape($localizedGcPattern) + '|' +
    'MAXScript Garbage Collection Error|' +
    'Unknown system exception|' +
    'Exception in MAXScript Garbage Collector'
)
$nativeErrors = @(
    $pidLines | Where-Object { [string]$_ -match $nativePatterns }
)
$businessPassed = (
    $business.ok -eq $true -and
    [int]$business.passed -eq 6 -and
    [int]$business.total -eq 6 -and
    @($business.checks | Where-Object { $_.ok -ne $true }).Count -eq 0 -and
    [int]$progress.completed -eq 6 -and
    [int]$progress.total -eq 6
)
$meta = [ordered]@{
    schema_version = 1
    test = 'full self-check with engine PID shutdown audit'
    selfcheck_script_path = $scriptPath
    selfcheck_script_sha256 = $scriptSha256
    started_at_utc = $startedAtUtc.ToString('o')
    finished_at_utc = $finishedAtUtc.ToString('o')
    exit_code = $exitCode
    engine_pid = $enginePid
    business_pass = $businessPassed
    passed = [int]$business.passed
    total = [int]$business.total
    progress_state = [string]$progress.state
    pid_log_line_count = $pidLines.Count
    native_error_count = $nativeErrors.Count
    native_error_lines = @($nativeErrors)
    result_path = $resultPath
    progress_path = $progressPath
    pid_log_path = $pidLogPath
}
$meta | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $metaPath -Encoding UTF8

if ($exitCode -ne 0) {
    throw "The full self-check returned exit code $exitCode."
}
if (-not $businessPassed) {
    throw 'The full self-check business assertions failed.'
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
