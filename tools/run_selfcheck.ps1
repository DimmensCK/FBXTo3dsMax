#requires -Version 7.0
<#
Run the source regression suite in a dedicated 3ds Max Batch process.
The current interactive scene and installed package are never used as targets.
All artifacts are retained under LOCALAPPDATA, including failed runs.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$MaxBatchExecutable,

    [Parameter(Mandatory = $true)]
    [ValidateRange(30, 7200)]
    [int]$TimeoutSeconds
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-MaxProcesses {
    return @(Get-CimInstance -ClassName Win32_Process -Filter (
        "Name='3dsmax.exe' OR Name='3dsmaxbatch.exe'"
    ) | Select-Object ProcessId, ParentProcessId, CreationDate, ExecutablePath)
}

function Get-MaxLogPaths {
    $base = Join-Path $env:LOCALAPPDATA 'Autodesk\3dsMax'
    if (-not (Test-Path -LiteralPath $base -PathType Container)) { return @() }
    $paths = [Collections.Generic.List[string]]::new()
    # Only the product/version/locale levels; never follow directory links.
    foreach ($versionDir in @(Get-ChildItem -LiteralPath $base -Directory)) {
        if ($versionDir.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
        foreach ($localeDir in @(Get-ChildItem -LiteralPath $versionDir.FullName -Directory)) {
            if ($localeDir.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
            $networkDir = Join-Path $localeDir.FullName 'Network'
            if (-not (Test-Path -LiteralPath $networkDir -PathType Container)) { continue }
            if ((Get-Item -LiteralPath $networkDir).Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
            $path = Join-Path $networkDir 'Max.log'
            if (Test-Path -LiteralPath $path -PathType Leaf) { $paths.Add($path) }
        }
    }
    return $paths.ToArray()
}

function Read-LogBytes([string]$Path, [long]$Offset, [int]$Count) {
    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read,
        [IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete)
    try {
        [void]$stream.Seek($Offset, [IO.SeekOrigin]::Begin)
        $buffer = [byte[]]::new($Count)
        $read = 0
        while ($read -lt $Count) {
            $next = $stream.Read($buffer, $read, $Count - $read)
            if ($next -eq 0) { break }
            $read += $next
        }
        if ($read -ne $Count) { throw "Max.log changed during read: $Path" }
        return ,$buffer
    }
    finally { $stream.Dispose() }
}

function Get-ByteHash([byte[]]$Bytes) {
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Bytes))
}

function Get-SourceHashes {
    $hashes = [ordered]@{}
    foreach ($relative in @(
        'f2m_topology_transfer.py', 'f2m_skin_replace.py', 'f2m_smoothing.py',
        'f2m_fbx_metadata.py', 'f2m_selfcheck.py', 'f2m_test_fixtures.py', 'FBXTo3dsMax_UI.ms',
        'Contents\f2m_toolbar.py', 'Contents\FBXTo3dsMax_Bootstrap.ms',
        'Contents\FBXTo3dsMax.mcr', 'VERSION.txt'
    )) {
        $path = Join-Path $projectRoot $relative
        $hashes[$relative] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
    }
    return $hashes
}

function Update-OwnedProcesses {
    $snapshot = @(Get-MaxProcesses)
    # Creation time and executable identity prevent PID reuse from granting authority.
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($item in $snapshot) {
            $id = [int]$item.ProcessId
            $parentId = [int]$item.ParentProcessId
            if ($owned.ContainsKey($id)) { continue }
            if (-not $owned.ContainsKey($parentId)) { continue }
            $created = ([DateTime]$item.CreationDate).ToUniversalTime()
            if ($created -lt $startedAtUtc.AddSeconds(-1)) { continue }
            if ([string]::IsNullOrWhiteSpace([string]$item.ExecutablePath)) {
                # Win32_Process can report the new child before its executable
                # path is populated. Keep it outside the authorized cleanup set
                # while waiting for a complete identity; never treat null as a
                # path match. A persistently unreadable identity still fails.
                if (-not $pendingOwned.ContainsKey($id) -or
                    $pendingOwned[$id].created -ne $created) {
                    $pendingOwned[$id] = @{
                        created = $created
                        first_seen = [DateTime]::UtcNow
                    }
                }
                if ([DateTime]::UtcNow -lt $pendingOwned[$id].first_seen.AddSeconds(15)) {
                    continue
                }
                throw "Child executable identity remained unreadable for PID $id."
            }
            $path = [IO.Path]::GetFullPath([string]$item.ExecutablePath)
            if ([IO.Path]::GetDirectoryName($path) -ine $maxRoot) {
                throw "Unexpected Max child executable for PID ${id}: $path"
            }
            $owned[$id] = @{ created = $created; path = $path }
            [void]$pendingOwned.Remove($id)
            $changed = $true
        }
    }
}

function Stop-OwnedProcesses {
    $cleanup = [Collections.Generic.List[string]]::new()
    # Never kill by process name; only identities observed in our own launch tree.
    foreach ($item in @(Get-MaxProcesses)) {
        $id = [int]$item.ProcessId
        if (-not $owned.ContainsKey($id)) { continue }
        $identity = $owned[$id]
        $created = ([DateTime]$item.CreationDate).ToUniversalTime()
        if ($created -ne $identity.created -or
            [string]$item.ExecutablePath -ine $identity.path) {
            $cleanup.Add("PID $id identity changed; refused cleanup.")
            continue
        }
        try {
            $targetProcess = [Diagnostics.Process]::GetProcessById($id)
            try {
                # Kill only this verified process and its current descendants,
                # including a resolver Python child if Max has not collected it.
                $targetProcess.Kill($true)
                if (-not $targetProcess.WaitForExit(5000)) {
                    throw "PID $id did not exit after cleanup."
                }
                $cleanup.Add("Stopped owned PID $id.")
            }
            finally { $targetProcess.Dispose() }
        }
        catch { $cleanup.Add("PID ${id} cleanup: $($_.Exception.Message)") }
    }
    return $cleanup.ToArray()
}

if (-not [IO.Path]::IsPathFullyQualified($MaxBatchExecutable)) {
    throw 'MaxBatchExecutable must be an absolute path.'
}
$MaxBatchExecutable = (Resolve-Path -LiteralPath $MaxBatchExecutable).ProviderPath
if ([IO.Path]::GetFileName($MaxBatchExecutable) -ine '3dsmaxbatch.exe') {
    throw 'MaxBatchExecutable must point to 3dsmaxbatch.exe.'
}
$maxRoot = [IO.Path]::GetDirectoryName($MaxBatchExecutable)
$projectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$scriptPath = Join-Path $projectRoot 'f2m_selfcheck.py'
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $projectRoot 'Contents\FBXTo3dsMax.files') -PathType Leaf)) {
    throw 'Cannot locate the source project from this launcher.'
}
if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    throw 'LOCALAPPDATA is required for validation artifacts.'
}
if (@(Get-MaxProcesses).Count -ne 0) {
    throw 'Close existing 3ds Max and 3ds Max Batch sessions before running this dedicated test.'
}

$runId = [Guid]::NewGuid().ToString('N')
$artifactRoot = Join-Path $env:LOCALAPPDATA 'FBXTo3dsMax\Validation'
$runDirectory = Join-Path $artifactRoot (
    'selfcheck_' + [DateTime]::UtcNow.ToString('yyyyMMdd_HHmmss') + '_' + $runId
)
[void][IO.Directory]::CreateDirectory($runDirectory)
$resultPath = Join-Path $runDirectory 'result.json'
$progressPath = Join-Path $runDirectory 'progress.json'
$cancelPath = Join-Path $runDirectory 'cancel.json'
$listenerPath = Join-Path $runDirectory 'listener.log'
$metaPath = Join-Path $runDirectory 'validation.json'
$beforeHashes = Get-SourceHashes
$logCheckpoints = @{}
foreach ($path in @(Get-MaxLogPaths)) {
    $length = (Get-Item -LiteralPath $path).Length
    $tailStart = [Math]::Max(0, $length - 256)
    $tail = Read-LogBytes $path $tailStart ([int]($length - $tailStart))
    $logCheckpoints[$path] = @{ length = $length; tail_start = $tailStart; tail_hash = Get-ByteHash $tail }
}

$owned = @{}
$pendingOwned = @{}
$process = $null
$stdoutTask = $null
$stderrTask = $null
$failure = ''
$cleanupActions = @()
$enginePid = 0
$exitCode = $null
$naturalExit = $false
$pidLines = [Collections.Generic.List[string]]::new()
$logSources = [Collections.Generic.List[string]]::new()
$nativeErrors = @()
$businessPassed = $false
$sourceUnchanged = $false
$startedAtUtc = [DateTime]::UtcNow

try {
    # Child-local environment: the caller's environment needs no mutation or
    # restoration, even if process creation or validation throws.
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $MaxBatchExecutable
    $startInfo.WorkingDirectory = $runDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    foreach ($argument in @($scriptPath, '-v', '5', '-listenerlog', $listenerPath)) {
        $startInfo.ArgumentList.Add($argument)
    }
    $startInfo.Environment['F2M_SELFCHECK_CHILD'] = '1'
    $startInfo.Environment['F2M_SELFCHECK_RESULT'] = $resultPath
    $startInfo.Environment['F2M_SELFCHECK_PROGRESS'] = $progressPath
    $startInfo.Environment['F2M_SELFCHECK_CANCEL'] = $cancelPath
    $startInfo.Environment['PYTHONDONTWRITEBYTECODE'] = '1'
    [void]$startInfo.Environment.Remove('F2M_SELFCHECK_MAX_LOG')
    if (@(Get-MaxProcesses).Count -ne 0) {
        throw 'A Max session appeared during preflight; the dedicated test was not launched.'
    }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    if (-not $process.Start()) { throw 'Failed to start 3ds Max Batch.' }
    $launcher = @(Get-MaxProcesses | Where-Object { [int]$_.ProcessId -eq $process.Id })
    if ($launcher.Count -ne 1) { throw 'Cannot verify the launched Batch process identity.' }
    $owned[$process.Id] = @{
        created = ([DateTime]$launcher[0].CreationDate).ToUniversalTime()
        path = [IO.Path]::GetFullPath([string]$launcher[0].ExecutablePath)
    }
    if ($owned[$process.Id].path -ine $MaxBatchExecutable) {
        throw 'Launched Batch executable identity does not match the requested path.'
    }
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $deadline = $startedAtUtc.AddSeconds($TimeoutSeconds)
    while (-not $process.WaitForExit(500)) {
        Update-OwnedProcesses
        if ([DateTime]::UtcNow -ge $deadline) {
            throw "Self-check exceeded $TimeoutSeconds seconds."
        }
    }
    Update-OwnedProcesses
    $naturalExit = $true
    $exitCode = $process.ExitCode
    foreach ($path in @($resultPath, $progressPath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Self-check did not create $path"
        }
        if ((Get-Item -LiteralPath $path).Length -gt 16MB) {
            throw "Unexpectedly large self-check result: $path"
        }
    }
    $business = Get-Content -LiteralPath $resultPath -Raw -Encoding UTF8 | ConvertFrom-Json -AsHashtable
    $progress = Get-Content -LiteralPath $progressPath -Raw -Encoding UTF8 | ConvertFrom-Json -AsHashtable
    $enginePid = [int]$progress['child_pid']
    if ($enginePid -le 0 -or -not $owned.ContainsKey($enginePid)) {
        throw 'Result engine PID was not observed in this dedicated launch tree.'
    }
    $businessPassed = (
        $business['ok'] -eq $true -and [int]$business['passed'] -eq 6 -and
        [int]$business['total'] -eq 6 -and @($business['checks']).Count -eq 6 -and
        @($business['checks'] | Where-Object { $_['ok'] -ne $true }).Count -eq 0 -and
        [int]$progress['completed'] -eq 6 -and [int]$progress['total'] -eq 6
    )
    $finishedAtUtc = [DateTime]::UtcNow
    $structuredPattern = '^\s*(?<stamp>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})\s+\S+:\s+\[0*' +
        [regex]::Escape([string]$enginePid) + '\]\s+\[[^\]]+\]\s+'
    foreach ($path in @(Get-MaxLogPaths)) {
        $length = (Get-Item -LiteralPath $path).Length
        $offset = 0L
        if ($logCheckpoints.ContainsKey($path)) {
            $checkpoint = $logCheckpoints[$path]
            if ($length -ge $checkpoint.length) {
                $tail = Read-LogBytes $path $checkpoint.tail_start ([int]($checkpoint.length - $checkpoint.tail_start))
                if ((Get-ByteHash $tail) -eq $checkpoint.tail_hash) { $offset = $checkpoint.length }
            }
        }
        $count = $length - $offset
        if ($count -gt 32MB) { throw "Max.log delta exceeds the bounded reader: $path" }
        $bytes = Read-LogBytes $path $offset ([int]$count)
        $utf8 = [Text.UTF8Encoding]::new($false, $true)
        try { $logText = $utf8.GetString($bytes) }
        catch { $logText = [Text.Encoding]::GetEncoding('gb18030').GetString($bytes) }
        $matched = $false
        foreach ($line in [regex]::Split($logText, '\r?\n')) {
            $match = [regex]::Match($line, $structuredPattern)
            if (-not $match.Success) { continue }
            $stamp = [DateTime]::ParseExact($match.Groups['stamp'].Value,
                'yyyy/MM/dd HH:mm:ss', [Globalization.CultureInfo]::InvariantCulture).ToUniversalTime()
            if ($stamp -lt $startedAtUtc.AddSeconds(-3) -or $stamp -gt $finishedAtUtc.AddSeconds(3)) { continue }
            $pidLines.Add($line)
            $matched = $true
        }
        if ($matched) { $logSources.Add($path) }
    }
    $pidLines.ToArray() | Set-Content -LiteralPath (Join-Path $runDirectory 'engine.Max.log') -Encoding UTF8
    $severePattern = 'MAXScript 内存收集错误|MAXScript Garbage Collection Error|' +
        'Unknown system exception|Exception in MAXScript Garbage Collector|Access violation|' +
        'Unhandled exception|EXCEPTION_ACCESS_VIOLATION'
    $nativeErrors = @($pidLines | Where-Object { $_ -match $severePattern })
    $afterHashes = Get-SourceHashes
    $sourceUnchanged = @($beforeHashes.Keys | Where-Object {
        $beforeHashes[$_] -ne $afterHashes[$_]
    }).Count -eq 0
    if ($exitCode -ne 0) { throw "Batch exited with code $exitCode." }
    if (-not $businessPassed) { throw 'Self-check business assertions did not pass 6/6.' }
    if ($pidLines.Count -eq 0) { throw "No fresh structured Max.log evidence for engine PID $enginePid." }
    if ($nativeErrors.Count -ne 0) { throw "Engine PID $enginePid emitted $($nativeErrors.Count) native severe errors." }
    if (-not $sourceUnchanged) { throw 'Production source hashes changed during validation.' }
    $remaining = @(Get-MaxProcesses | Where-Object { $owned.ContainsKey([int]$_.ProcessId) })
    if ($remaining.Count -ne 0) { throw 'An owned Max process remains after the launcher exited.' }
}
catch {
    $failure = $_.Exception.Message
    if ($process -and $owned.Count -gt 0) {
        try { Update-OwnedProcesses } catch { $failure += " Process tracking: $($_.Exception.Message)" }
        $cleanupActions = @(Stop-OwnedProcesses)
    }
}
finally {
    foreach ($entry in @(
        @{ task = $stdoutTask; name = 'stdout.log' },
        @{ task = $stderrTask; name = 'stderr.log' }
    )) {
        if ($entry.task -and $entry.task.Wait(5000)) {
            [IO.File]::WriteAllText((Join-Path $runDirectory $entry.name), $entry.task.Result,
                [Text.UTF8Encoding]::new($false))
        }
    }
    $meta = [ordered]@{
        schema_version = 1
        run_id = $runId
        ok = [string]::IsNullOrEmpty($failure)
        source_script = $scriptPath
        max_batch_executable = $MaxBatchExecutable
        started_at_utc = $startedAtUtc.ToString('o')
        finished_at_utc = [DateTime]::UtcNow.ToString('o')
        launcher_pid = $(if ($process) { $process.Id } else { $null })
        engine_pid = $enginePid
        natural_exit = $naturalExit
        exit_code = $exitCode
        business_pass = $businessPassed
        source_hashes_unchanged = $sourceUnchanged
        source_sha256 = $beforeHashes
        max_log_sources = $logSources.ToArray()
        pid_log_line_count = $pidLines.Count
        native_severe_error_count = $nativeErrors.Count
        native_severe_error_lines = @($nativeErrors | Select-Object -First 20)
        cleanup_actions = $cleanupActions
        failure = $failure
        artifact_directory = $runDirectory
        result_path = $resultPath
        progress_path = $progressPath
        listener_path = $listenerPath
    }
    $meta | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $metaPath -Encoding UTF8
    if ($process) { $process.Dispose() }
}

if ($failure) { throw "$failure Validation record: $metaPath" }
$meta | ConvertTo-Json -Depth 5
