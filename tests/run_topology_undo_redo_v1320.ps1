param(
    [string]$MaxBatchExecutable =
        'D:\Autodesk\3dsmax2023\3ds Max 2023\3dsmaxbatch.exe',
    [int]$TimeoutSeconds = 600,
    [switch]$SaveReload
)

$ErrorActionPreference = 'Stop'
$testsRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$workspaceRoot = [IO.Path]::GetFullPath(
    (Join-Path $testsRoot '..')
)
$scriptPath = Join-Path $testsRoot 'max_topology_undo_redo_v1320.py'
$artifactStem = if ($SaveReload) {
    '_max_topology_save_reload_v1320'
}
else {
    '_max_topology_undo_redo_v1320'
}
$resultPath = Join-Path $testsRoot ($artifactStem + '_result.json')
$listenerPath = Join-Path $testsRoot ($artifactStem + '.listener.log')
$pidLogPath = Join-Path $testsRoot ($artifactStem + '.Max.log')
$metaPath = Join-Path $testsRoot ($artifactStem + '.meta.json')
$modulePath = Join-Path $workspaceRoot 'f2m_topology_transfer.py'
$fixturePath = Join-Path $testsRoot 'fixtures\topology_source.fbx'
$maxLogPath = Join-Path $env:LOCALAPPDATA (
    'Autodesk\3dsMax\2023 - 64bit\CHS\Network\Max.log'
)
$tokenEnvironmentName = 'F2M_TOPOLOGY_UNDO_REDO_RUN_TOKEN'
$resultEnvironmentName = 'F2M_TOPOLOGY_GATE_RESULT'
$saveReloadEnvironmentName = 'F2M_TOPOLOGY_SAVE_RELOAD_PATH'

function Test-HeapCheckValue {
    param([object]$Value)
    $normalized = ([string]$Value).Trim().ToLowerInvariant()
    return $normalized -eq 'true' -or $normalized -eq 'ok'
}

function Update-OwnedProcessSet {
    param(
        [System.Collections.Generic.HashSet[int]]$OwnedPids,
        [hashtable]$ExecutablePaths
    )
    $rows = @(
        Get-CimInstance `
            -ClassName Win32_Process `
            -ErrorAction SilentlyContinue
    )
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($row in $rows) {
            $processId = [int]$row.ProcessId
            $parentId = [int]$row.ParentProcessId
            if (
                $processId -gt 0 -and
                $OwnedPids.Contains($parentId) -and
                $OwnedPids.Add($processId)
            ) {
                $changed = $true
            }
            if (
                $OwnedPids.Contains($processId) -and
                [string]$row.ExecutablePath
            ) {
                $ExecutablePaths[$processId] = [string]$row.ExecutablePath
            }
        }
    }
}

function Stop-OwnedProcessTrees {
    param(
        [int]$RootProcessId,
        [System.Collections.Generic.HashSet[int]]$OwnedPids
    )
    $taskkillSucceeded = $false
    if ($RootProcessId -gt 0) {
        & taskkill.exe /PID $RootProcessId /T /F 2>$null | Out-Null
        $taskkillSucceeded = $LASTEXITCODE -eq 0
    }
    $liveOwned = @(
        $OwnedPids |
            Where-Object {
                Get-Process -Id $_ -ErrorAction SilentlyContinue
            }
    )
    if (-not $taskkillSucceeded -or $liveOwned.Count -gt 0) {
        foreach ($ownedProcessId in $liveOwned) {
            Stop-Process `
                -Id $ownedProcessId `
                -Force `
                -ErrorAction SilentlyContinue
        }
    }
    $stopDeadline = [DateTime]::UtcNow.AddSeconds(5)
    while (
        @(
            $OwnedPids |
                Where-Object {
                    Get-Process -Id $_ -ErrorAction SilentlyContinue
                }
        ).Count -gt 0 -and
        [DateTime]::UtcNow -lt $stopDeadline
    ) {
        Start-Sleep -Milliseconds 100
    }
}

foreach ($requiredPath in @(
    $MaxBatchExecutable,
    $scriptPath,
    $modulePath,
    $fixturePath
)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required Undo/Redo gate file not found: $requiredPath"
    }
}
if ([IO.Path]::GetFileName($MaxBatchExecutable) -ine '3dsmaxbatch.exe') {
    throw "The Undo/Redo gate requires 3dsmaxbatch.exe: $MaxBatchExecutable"
}
if ($TimeoutSeconds -lt 1) {
    throw 'TimeoutSeconds must be positive.'
}

$scriptPath = [IO.Path]::GetFullPath($scriptPath)
$modulePath = [IO.Path]::GetFullPath($modulePath)
$fixturePath = [IO.Path]::GetFullPath($fixturePath)
$scriptHash = (Get-FileHash -LiteralPath $scriptPath -Algorithm SHA256).Hash
$moduleHash = (Get-FileHash -LiteralPath $modulePath -Algorithm SHA256).Hash
$fixtureHash = (Get-FileHash -LiteralPath $fixturePath -Algorithm SHA256).Hash
$runToken = [Guid]::NewGuid().ToString('N')
if ($runToken -notmatch '^[0-9a-f]{32}$') {
    throw 'The launcher did not create a valid 32-hex run token.'
}
$saveReloadPath = if ($SaveReload) {
    Join-Path $testsRoot (
        '_max_topology_save_reload_v1320_' +
        $runToken +
        '.tmp.max'
    )
}
else {
    ''
}

$lockPath = Join-Path $testsRoot '.topology_undo_redo_v1320.lock'
try {
    $lockStream = [IO.File]::Open(
        $lockPath,
        [IO.FileMode]::OpenOrCreate,
        [IO.FileAccess]::ReadWrite,
        [IO.FileShare]::None
    )
}
catch {
    throw 'Another topology Undo/Redo gate is already running.'
}

try {
$beforeLineCount = 0
if (Test-Path -LiteralPath $maxLogPath -PathType Leaf) {
    $beforeLineCount = @(
        Get-Content -LiteralPath $maxLogPath -Encoding Default
    ).Count
}
$staleArtifacts = @($resultPath, $listenerPath, $pidLogPath, $metaPath)
if ($SaveReload) {
    $staleArtifacts += $saveReloadPath
}
foreach ($path in $staleArtifacts) {
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force
    }
}

$previousToken = [Environment]::GetEnvironmentVariable(
    $tokenEnvironmentName,
    [EnvironmentVariableTarget]::Process
)
$previousResultPath = [Environment]::GetEnvironmentVariable(
    $resultEnvironmentName,
    [EnvironmentVariableTarget]::Process
)
$previousSaveReloadPath = [Environment]::GetEnvironmentVariable(
    $saveReloadEnvironmentName,
    [EnvironmentVariableTarget]::Process
)
$startedAtUtc = [DateTime]::UtcNow
$process = $null
$timedOut = $false
$killIssued = $false
$launcherExitedNaturally = $false
$ownedPids = [System.Collections.Generic.HashSet[int]]::new()
$ownedProcessPaths = @{}
try {
    [Environment]::SetEnvironmentVariable(
        $tokenEnvironmentName,
        $runToken,
        [EnvironmentVariableTarget]::Process
    )
    [Environment]::SetEnvironmentVariable(
        $resultEnvironmentName,
        $resultPath,
        [EnvironmentVariableTarget]::Process
    )
    [Environment]::SetEnvironmentVariable(
        $saveReloadEnvironmentName,
        $(if ($SaveReload) { $saveReloadPath } else { $null }),
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
    $launcherPid = [int]$process.Id
    [void]$ownedPids.Add($launcherPid)
    $ownedProcessPaths[$launcherPid] = [IO.Path]::GetFullPath(
        $MaxBatchExecutable
    )
    $processDeadline = $startedAtUtc.AddSeconds($TimeoutSeconds)
    while (-not $process.HasExited -and [DateTime]::UtcNow -lt $processDeadline) {
        Update-OwnedProcessSet `
            -OwnedPids $ownedPids `
            -ExecutablePaths $ownedProcessPaths
        Start-Sleep -Milliseconds 250
        $process.Refresh()
    }
    Update-OwnedProcessSet `
        -OwnedPids $ownedPids `
        -ExecutablePaths $ownedProcessPaths
    if (-not $process.HasExited) {
        $timedOut = $true
        $killIssued = $true
        Stop-OwnedProcessTrees `
            -RootProcessId $launcherPid `
            -OwnedPids $ownedPids
        [void]$process.WaitForExit(5000)
    }
    else {
        $launcherExitedNaturally = $true
        [void]$process.WaitForExit(5000)
    }
}
finally {
    [Environment]::SetEnvironmentVariable(
        $tokenEnvironmentName,
        $previousToken,
        [EnvironmentVariableTarget]::Process
    )
    [Environment]::SetEnvironmentVariable(
        $resultEnvironmentName,
        $previousResultPath,
        [EnvironmentVariableTarget]::Process
    )
    [Environment]::SetEnvironmentVariable(
        $saveReloadEnvironmentName,
        $previousSaveReloadPath,
        [EnvironmentVariableTarget]::Process
    )
}
if ($timedOut) {
    throw (
        "The topology Undo/Redo gate exceeded $TimeoutSeconds seconds; " +
        "its exact launcher process tree was terminated."
    )
}
$process.Refresh()
$finishedAtUtc = [DateTime]::UtcNow
$exitCode = [int]$process.ExitCode

if (-not (Test-Path -LiteralPath $resultPath -PathType Leaf)) {
    throw 'The topology Undo/Redo gate did not create its business result.'
}
$resultInfo = Get-Item -LiteralPath $resultPath
if ($resultInfo.LastWriteTimeUtc -lt $startedAtUtc.AddSeconds(-2)) {
    throw 'The topology Undo/Redo result is stale.'
}
$business = Get-Content -LiteralPath $resultPath -Raw -Encoding UTF8 |
    ConvertFrom-Json

$enginePid = [int]$business.engine_pid
if ($enginePid -le 0) {
    throw 'The Undo/Redo result is missing a valid engine PID.'
}
$expectedScriptPath = [IO.Path]::GetFullPath($scriptPath)
$actualScriptPath = [IO.Path]::GetFullPath(
    [string]$business.gate_script_path
)
$expectedModulePath = [IO.Path]::GetFullPath($modulePath)
$actualModulePath = [IO.Path]::GetFullPath(
    [string]$business.module_path
)
$expectedFixturePath = [IO.Path]::GetFullPath($fixturePath)
$actualFixturePath = [IO.Path]::GetFullPath(
    [string]$business.fixture
)
$expectedResultPath = [IO.Path]::GetFullPath($resultPath)
$actualResultPath = [IO.Path]::GetFullPath(
    [string]$business.result_path
)
$expectedGateMode = if ($SaveReload) { 'save_reload' } else { 'undo_redo' }
$saveReloadIdentityPassed = if ($SaveReload) {
    [bool]$business.save_reload_requested -and
    [IO.Path]::GetFullPath(
        [string]$business.save_reload.temporary_max_path
    ) -ieq [IO.Path]::GetFullPath($saveReloadPath)
}
else {
    -not [bool]$business.save_reload_requested
}
$identityPassed = (
    [string]$business.version -eq '1.3.20' -and
    [string]$business.gate_mode -ceq $expectedGateMode -and
    [string]$business.run_token -ceq $runToken -and
    [string]$business.run_token -match '^[0-9a-fA-F]{32}$' -and
    $actualScriptPath -ieq $expectedScriptPath -and
    [string]$business.gate_script_sha256 -ieq $scriptHash -and
    $actualModulePath -ieq $expectedModulePath -and
    [string]$business.module_sha256 -ieq $moduleHash -and
    $actualFixturePath -ieq $expectedFixturePath -and
    [string]$business.fixture_sha256 -ieq $fixtureHash -and
    $actualResultPath -ieq $expectedResultPath -and
    $saveReloadIdentityPassed
)
if (-not $identityPassed) {
    throw (
        'The Undo/Redo result failed token/path/hash identity validation; ' +
        'no result-supplied PID was touched.'
    )
}
if (-not $ownedPids.Contains($enginePid)) {
    throw (
        "Engine PID $enginePid was not observed in launcher PID " +
        "$launcherPid's owned process tree; it will not be touched."
    )
}
$engineExecutablePath = [string]$ownedProcessPaths[$enginePid]
if (-not $engineExecutablePath -and $enginePid -eq $launcherPid) {
    $engineExecutablePath = [IO.Path]::GetFullPath($MaxBatchExecutable)
}
$expectedMaxRoot = [IO.Path]::GetDirectoryName(
    [IO.Path]::GetFullPath($MaxBatchExecutable)
)
if (-not $engineExecutablePath) {
    throw "Owned engine PID $enginePid has no captured executable path."
}
$engineExecutablePath = [IO.Path]::GetFullPath($engineExecutablePath)
$engineLeaf = [IO.Path]::GetFileName($engineExecutablePath)
$engineRoot = [IO.Path]::GetDirectoryName($engineExecutablePath)
if (
    $engineRoot -ine $expectedMaxRoot -or
    $engineLeaf -inotmatch '^3dsmax(batch)?\.exe$'
) {
    throw (
        "Owned engine executable identity is unexpected: " +
        $engineExecutablePath
    )
}

$engineExitedNaturally = $true
$engineDeadline = [DateTime]::UtcNow.AddSeconds(30)
while (
    (Get-Process -Id $enginePid -ErrorAction SilentlyContinue) -and
    [DateTime]::UtcNow -lt $engineDeadline
) {
    Update-OwnedProcessSet `
        -OwnedPids $ownedPids `
        -ExecutablePaths $ownedProcessPaths
    Start-Sleep -Milliseconds 100
}
if (Get-Process -Id $enginePid -ErrorAction SilentlyContinue) {
    $engineExitedNaturally = $false
    $killIssued = $true
    Stop-OwnedProcessTrees `
        -RootProcessId $launcherPid `
        -OwnedPids $ownedPids
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
# Max.log prints small PIDs with leading zeroes.  Preserve the bracket boundary.
$pidPattern = '\[0*' +
    [regex]::Escape(([string]$enginePid)) +
    '\]'
$pidLinesAll = [string[]]@(
    $deltaLines |
        ForEach-Object { [string]$_ } |
        Where-Object { $_ -match $pidPattern }
)
$beginMarker = (
    "F2M_TOPOLOGY_UNDO_REDO_BEGIN TOKEN=$runToken PID=$enginePid"
)
$endMarker = (
    "F2M_TOPOLOGY_UNDO_REDO_END TOKEN=$runToken PID=$enginePid OK=true"
)
$beginIndices = @()
$endIndices = @()
for ($lineIndex = 0; $lineIndex -lt $pidLinesAll.Count; $lineIndex++) {
    if ($pidLinesAll[$lineIndex].Contains($beginMarker)) {
        $beginIndices += $lineIndex
    }
    if ($pidLinesAll[$lineIndex].Contains($endMarker)) {
        $endIndices += $lineIndex
    }
}
$tokenLogBound = (
    $beginIndices.Count -eq 1 -and
    $endIndices.Count -eq 1 -and
    $beginIndices[0] -le $endIndices[0]
)
$pidLines = if ($tokenLogBound) {
    [string[]]@(
        # Keep every PID line through process shutdown.  The END marker binds
        # the business lifecycle but native exit-time GC errors occur after it.
        $pidLinesAll[$beginIndices[0]..($pidLinesAll.Count - 1)]
    )
}
else {
    [string[]]@($pidLinesAll)
}
$pidLines | Set-Content -LiteralPath $pidLogPath -Encoding UTF8

$listenerLines = @()
if (Test-Path -LiteralPath $listenerPath -PathType Leaf) {
    $listenerLines = [string[]]@(
        Get-Content -LiteralPath $listenerPath -Encoding Default
    )
}
$listenerBeginCount = @(
    $listenerLines | Where-Object { $_.Contains($beginMarker) }
).Count
$listenerEndCount = @(
    $listenerLines | Where-Object { $_.Contains($endMarker) }
).Count
$listenerTokenBound = (
    $listenerBeginCount -eq 1 -and
    $listenerEndCount -eq 1
)

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

$comparison = $business.comparison
$expectedFinalF2mCount = [int](
    $business.normal_contract.expected_final_f2m_count
)
$afterFinalF2mCount = if (
    $null -ne $business.snapshots.after.modifiers.final_f2m_count
) {
    [int]$business.snapshots.after.modifiers.final_f2m_count
}
else { -1 }
$redoFinalF2mCount = if (
    $null -ne $business.snapshots.after_redo.modifiers.final_f2m_count
) {
    [int]$business.snapshots.after_redo.modifiers.final_f2m_count
}
else { -1 }
$afterFinalStates = @(
    $business.snapshots.after.normals.final_f2m_states
)
$redoFinalStates = @(
    $business.snapshots.after_redo.normals.final_f2m_states
)
$zeroResidual = [bool]$business.normal_contract.zero_residual
$zeroResidualBlueF2mVerified = if ($zeroResidual) {
    $afterFinalStates.Count -eq 1 -and
    $redoFinalStates.Count -eq 1 -and
    [int]$afterFinalStates[0].explicit_count -eq 0 -and
    [int]$afterFinalStates[0].specified_count -eq 0 -and
    [int]$redoFinalStates[0].explicit_count -eq 0 -and
    [int]$redoFinalStates[0].specified_count -eq 0 -and
    $comparison.zero_residual_blue_f2m -eq $true
}
else {
    $true
}
$finalF2mContractVerified = if ($expectedFinalF2mCount -eq 0) {
    $afterFinalF2mCount -eq 0 -and
    $redoFinalF2mCount -eq 0
}
elseif ($expectedFinalF2mCount -eq 1) {
    $afterFinalF2mCount -eq 1 -and
    $redoFinalF2mCount -eq 1 -and
    $comparison.nonzero_residual_f2m_at_stack_bottom -eq $true -and
    $zeroResidualBlueF2mVerified
}
else {
    $false
}
$undoCallbackLabels = @($business.scene_undo_labels)
$redoCallbackLabels = @($business.scene_redo_labels)
$undoTransactionVerified = (
    [int]$business.undo_level_count_before_transfer -eq 0 -and
    [int]$business.undo_level_count_after_transfer -in @(0, 1) -and
    [int]$business.undo_level_count_after_undo -in @(0, 1) -and
    [int]$business.undo_level_count_after_redo -in @(0, 1) -and
    $undoCallbackLabels.Count -le 1 -and
    $redoCallbackLabels.Count -le 1 -and
    $comparison.pre_equals_after_undo -eq $true -and
    $comparison.post_equals_after_redo -eq $true -and
    $business.normal_semantics_preserved_through_redo -eq $true
)
$saveReloadF2mVerified = if ($SaveReload) {
    if ($expectedFinalF2mCount -eq 0) {
        [int]$business.save_reload.expected_final_f2m_count -eq 0 -and
        [int]$business.save_reload.post_final_f2m_count -eq 0 -and
        [int]$business.save_reload.reloaded_final_f2m_count -eq 0
    }
    elseif ($expectedFinalF2mCount -eq 1) {
        [int]$business.save_reload.expected_final_f2m_count -eq 1 -and
        [int]$business.save_reload.post_final_f2m_count -eq 1 -and
        [int]$business.save_reload.reloaded_final_f2m_count -eq 1 -and
        $business.save_reload.final_f2m_at_stack_bottom -eq $true -and
        $business.save_reload.zero_residual_blue_f2m_persisted -eq $true
    }
    else {
        $false
    }
}
else {
    $true
}
$saveReloadVerified = if ($SaveReload) {
    $business.save_reload.requested -eq $true -and
    $business.save_reload.verified -eq $true -and
    $business.save_reload.base_points_exact -eq $true -and
    $business.save_reload.evaluated_points_exact -eq $true -and
    $business.save_reload.topology_exact -eq $true -and
    $business.save_reload.uv1_exact -eq $true -and
    $business.save_reload.all_map_channels_exact -eq $true -and
    $business.save_reload.smoothing_groups_exact -eq $true -and
    $business.save_reload.edit_normals_semantic_state_exact -eq $true -and
    $business.save_reload.final_f2m_contract_verified -eq $true -and
    $saveReloadF2mVerified -and
    [int]$business.save_reload.undo_level_count_after_reload -eq 0 -and
    $business.temporary_max_removed -eq $true -and
    -not (Test-Path -LiteralPath $saveReloadPath)
}
else {
    $business.save_reload.requested -eq $false -and
    $business.save_reload.verified -eq $true -and
    $business.temporary_max_removed -eq $true
}
$businessPassed = (
    $business.ok -eq $true -and
    $identityPassed -and
    $ownedPids.Contains($enginePid) -and
    $tokenLogBound -and
    $listenerTokenBound -and
    $undoTransactionVerified -and
    (Test-HeapCheckValue $business.heap_check_before) -and
    (Test-HeapCheckValue $business.heap_check_after_undo) -and
    (Test-HeapCheckValue $business.heap_check_after_redo) -and
    $comparison.base_points_preserved_by_transfer -eq $true -and
    $comparison.points_preserved_by_transfer -eq $true -and
    $comparison.topology_preserved_by_transfer -eq $true -and
    $comparison.uv1_preserved_by_transfer -eq $true -and
    $comparison.all_map_channels_preserved_by_transfer -eq $true -and
    $comparison.smoothing_changed_by_transfer -eq $true -and
    $comparison.current_combo_contract_verified -eq $true -and
    $comparison.residual_not_full_override -eq $true -and
    $finalF2mContractVerified -and
    $comparison.post_f2m_at_stack_bottom -eq $true -and
    $comparison.zero_residual_blue_f2m -eq $true -and
    $comparison.nonzero_residual_f2m_at_stack_bottom -eq $true -and
    $business.normal_semantics_preserved_through_redo -eq $true -and
    $comparison.normal_semantics_preserved_through_redo -eq $true -and
    $comparison.pre_equals_after_undo -eq $true -and
    $comparison.post_equals_after_redo -eq $true -and
    $comparison.undo_has_no_f2m_baseline -eq $true -and
    $comparison.redo_has_only_final_f2m -eq $true -and
    $comparison.save_reload_verified -eq $true -and
    $saveReloadVerified -and
    $business.cleanup_reset -eq $true -and
    -not [string]$business.error -and
    -not [string]$business.cleanup_error
)

$meta = [ordered]@{
    schema_version = 1
    test = [string]$business.test
    gate_mode = [string]$business.gate_mode
    save_reload_requested = [bool]$business.save_reload_requested
    run_token = $runToken
    started_at_utc = $startedAtUtc.ToString('o')
    finished_at_utc = $finishedAtUtc.ToString('o')
    timeout_seconds = $TimeoutSeconds
    timed_out = $false
    launcher_pid = $launcherPid
    engine_pid = $enginePid
    exit_code = $exitCode
    launcher_exited_naturally = $launcherExitedNaturally
    engine_exited_naturally = $engineExitedNaturally
    kill_issued = $killIssued
    owned_process_ids = @($ownedPids | Sort-Object)
    engine_executable_path = $engineExecutablePath
    token_log_bound = $tokenLogBound
    listener_token_bound = $listenerTokenBound
    gate_script_path = $scriptPath
    gate_script_sha256 = $scriptHash
    module_path = $modulePath
    module_sha256 = $moduleHash
    fixture = $fixturePath
    fixture_sha256 = $fixtureHash
    target_handle = [int]$business.target_handle
    target_name = [string]$business.target_name
    expected_transaction_label = [string]$business.expected_transaction_label
    combo_report_target = [string](
        $business.normal_contract.report_target
    )
    combo_report_verified = [bool](
        $business.normal_contract.runtime_report_verified
    )
    strict_resolver_verified = [bool](
        $business.normal_contract.strict_resolver_verified
    )
    single_exact_import_verified = [bool](
        $business.normal_contract.single_exact_import_verified
    )
    normal_semantics_preserved_through_redo = [bool](
        $business.normal_semantics_preserved_through_redo
    )
    undo_names_after_transfer = @($business.undo_names_after_transfer)
    redo_names_after_undo = @($business.redo_names_after_undo)
    undo_names_after_redo = @($business.undo_names_after_redo)
    undo_level_count_before_transfer = [int](
        $business.undo_level_count_before_transfer
    )
    undo_level_count_after_transfer = [int](
        $business.undo_level_count_after_transfer
    )
    undo_level_count_after_undo = [int](
        $business.undo_level_count_after_undo
    )
    undo_level_count_after_redo = [int](
        $business.undo_level_count_after_redo
    )
    scene_undo_labels = @($undoCallbackLabels)
    scene_redo_labels = @($redoCallbackLabels)
    undo_transaction_verified = $undoTransactionVerified
    save_reload_verified = $saveReloadVerified
    expected_final_f2m_count = $expectedFinalF2mCount
    after_final_f2m_count = $afterFinalF2mCount
    redo_final_f2m_count = $redoFinalF2mCount
    final_f2m_contract_verified = $finalF2mContractVerified
    temporary_max_path = [string](
        $business.save_reload.temporary_max_path
    )
    temporary_max_removed = [bool]$business.temporary_max_removed
    before_fingerprint = [string](
        $business.snapshots.before.fingerprint_sha256
    )
    after_fingerprint = [string](
        $business.snapshots.after.fingerprint_sha256
    )
    business_pass = $businessPassed
    pid_log_line_count = $pidLines.Count
    native_error_count = $nativeErrors.Count
    native_error_lines = @($nativeErrors)
    result_path = $resultPath
    pid_log_path = $pidLogPath
}
$meta | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $metaPath -Encoding UTF8

if ($exitCode -ne 0) {
    throw "The topology Undo/Redo gate returned exit code $exitCode."
}
if (-not $launcherExitedNaturally -or $killIssued) {
    throw 'The launcher/process tree did not complete without a forced stop.'
}
if (-not $engineExitedNaturally) {
    throw (
        "Engine PID $enginePid did not exit naturally after the launcher; " +
        "the token-bound process tree was terminated."
    )
}
if (-not $businessPassed) {
    throw 'The topology Undo/Redo business assertions failed.'
}
if ($pidLines.Count -eq 0) {
    throw "No structured Max.log lines were found for engine PID $enginePid."
}
if (-not $tokenLogBound -or -not $listenerTokenBound) {
    throw 'The token/PID BEGIN-END log slice is incomplete or ambiguous.'
}
if ($nativeErrors.Count -ne 0) {
    throw (
        "Engine PID $enginePid emitted $($nativeErrors.Count) native " +
        "MAXScript/GC errors before shutdown completed."
    )
}

$meta | ConvertTo-Json -Depth 8
}
finally {
    if ($null -ne $lockStream) {
        $lockStream.Dispose()
    }
}
