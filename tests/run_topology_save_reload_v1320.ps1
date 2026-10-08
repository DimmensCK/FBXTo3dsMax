param(
    [string]$MaxBatchExecutable =
        'D:\Autodesk\3dsmax2023\3ds Max 2023\3dsmaxbatch.exe',
    [int]$TimeoutSeconds = 600
)

$ErrorActionPreference = 'Stop'
$runnerPath = Join-Path $PSScriptRoot 'run_topology_undo_redo_v1320.ps1'
& $runnerPath `
    -MaxBatchExecutable $MaxBatchExecutable `
    -TimeoutSeconds $TimeoutSeconds `
    -SaveReload

