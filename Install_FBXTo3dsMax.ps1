#requires -Version 5.1

<#
.SYNOPSIS
启动 FBXTo3dsMax 的标准事务式 MAXScript 安装器。

.DESCRIPTION
此启动器本身不会复制插件文件。它会先验证源安装包，再用以下命令启动明确
指定的 3ds Max 版本：

    3dsmax.exe -U MAXScript Install_FBXTo3dsMax.ms

如果已有任何 3ds Max 进程在运行，此启动器会在进行任何更改前停止。此时请把
Install_FBXTo3dsMax.ms 拖入现有 Max 窗口，使安装器能够安全卸载内存中的旧版
插件状态。

.PARAMETER MaxRoot
受支持的 3ds Max 安装目录或其 3dsmax.exe 的绝对路径。

.EXAMPLE
.\Install_FBXTo3dsMax.ps1 -MaxRoot 'D:\Autodesk\3dsmax2023\3ds Max 2023'

.EXAMPLE
.\Install_FBXTo3dsMax.ps1 -MaxRoot 'C:\Program Files\Autodesk\3ds Max 2026\3dsmax.exe'
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, HelpMessage = "请输入 3ds Max 2023-2026 安装目录或 3dsmax.exe 的绝对路径。")]
    [ValidateNotNullOrEmpty()]
    [string]$MaxRoot
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$launcherRoot = $PSScriptRoot
$installerPath = Join-Path $launcherRoot "Install_FBXTo3dsMax.ms"
$manifestPath = Join-Path $launcherRoot "Contents\FBXTo3dsMax.files"
$packageXmlPath = Join-Path $launcherRoot "PackageContents.xml"
$versionPath = Join-Path $launcherRoot "Contents\FBXTo3dsMax.version"
$expectedPackageName = "FBXTo3dsMax"
$expectedUpgradeCode = "{B7AD0BB7-C64E-4F41-9767-CA72294639AE}"
$strictUtf8 = [System.Text.UTF8Encoding]::new($false, $true)

function Resolve-FBXTo3dsMaxMaxExecutable {
    param(
        [Parameter(Mandatory = $true)]
        [string]$InputPath
    )

    $candidate = [Environment]::ExpandEnvironmentVariables($InputPath.Trim())
    if (-not [System.IO.Path]::IsPathRooted($candidate)) {
        throw "MaxRoot 必须是绝对路径：$candidate"
    }
    if (-not (Test-Path -LiteralPath $candidate)) {
        throw "所选 3ds Max 路径不存在：$candidate"
    }

    $item = Get-Item -LiteralPath $candidate
    if ($item.PSIsContainer) {
        $candidate = Join-Path $item.FullName "3dsmax.exe"
    }
    elseif ($item.Name -ine "3dsmax.exe") {
        throw "MaxRoot 指向的文件不是 3dsmax.exe：$($item.FullName)"
    }
    else {
        $candidate = $item.FullName
    }

    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "所选目录中找不到 3dsmax.exe：$candidate"
    }

    return Get-Item -LiteralPath $candidate
}

function Assert-FBXTo3dsMaxSafeRelativePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    if ([string]::IsNullOrWhiteSpace($RelativePath)) {
        throw "$Label 不能为空。"
    }
    if ([System.IO.Path]::IsPathRooted($RelativePath) -or $RelativePath.Contains(":")) {
        throw "$Label 必须是相对路径：$RelativePath"
    }

    $segments = $RelativePath -split "[\\/]"
    foreach ($segment in $segments) {
        if ([string]::IsNullOrWhiteSpace($segment) -or $segment -eq "." -or $segment -eq "..") {
            throw "$Label 包含不安全的路径段：$RelativePath"
        }
    }
}

function Assert-FBXTo3dsMaxSourceManifest {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourceRoot,
        [Parameter(Mandatory = $true)]
        [string]$ManifestFile
    )

    $sourceRootFull = [System.IO.Path]::GetFullPath($SourceRoot)
    $sourceRootPrefix = $sourceRootFull.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
    $destinations = @{}
    $entryCount = 0

    foreach ($rawLine in [System.IO.File]::ReadAllLines($ManifestFile, $strictUtf8)) {
        $line = $rawLine.Trim()
        if ($line.Length -eq 0 -or $line.StartsWith("#")) {
            continue
        }

        $separatorIndex = $line.IndexOf("|", [System.StringComparison]::Ordinal)
        if ($separatorIndex -le 0 -or $separatorIndex -ne $line.LastIndexOf("|", [System.StringComparison]::Ordinal)) {
            throw "安装清单的每一项必须且只能包含一个竖线分隔符：$line"
        }

        $sourceRelative = $line.Substring(0, $separatorIndex).Trim()
        $destinationRelative = $line.Substring($separatorIndex + 1).Trim()
        Assert-FBXTo3dsMaxSafeRelativePath -RelativePath $sourceRelative -Label "安装清单源路径"
        Assert-FBXTo3dsMaxSafeRelativePath -RelativePath $destinationRelative -Label "安装清单目标路径"

        $sourceFull = [System.IO.Path]::GetFullPath((Join-Path $sourceRootFull $sourceRelative))
        if (-not $sourceFull.StartsWith($sourceRootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "安装清单源路径越出了源目录：$sourceRelative"
        }
        if (-not (Test-Path -LiteralPath $sourceFull -PathType Leaf)) {
            throw "安装清单引用的源文件不存在：$sourceFull"
        }

        $destinationKey = $destinationRelative.Replace("/", "\")
        if ($destinations.ContainsKey($destinationKey)) {
            throw "安装清单包含重复的目标路径：$destinationRelative"
        }
        $destinations[$destinationKey] = $true
        $entryCount += 1
    }

    if ($entryCount -eq 0) {
        throw "安装清单没有任何项目：$ManifestFile"
    }

    foreach ($requiredDestination in @(
        "PackageContents.xml",
        "Contents\FBXTo3dsMax_Bootstrap.ms",
        "Contents\FBXTo3dsMax.files",
        "Contents\FBXTo3dsMax.version",
        "Contents\FBXTo3dsMax_UI.ms",
        "Contents\FBXTo3dsMax.mcr",
        "Contents\f2m_toolbar.py",
        "Contents\f2m_topology_transfer.py",
        "Contents\f2m_skin_replace.py",
        "Contents\f2m_smoothing.py",
        "Contents\f2m_fbx_metadata.py",
        "Contents\f2m_selfcheck.py",
        "Contents\FBXTo3dsMax_详细说明书.md",
        "Contents\tests\max_normals_safety.py",
        "Contents\tests\fixtures\native_smoothing_source.fbx"
    )) {
        if (-not $destinations.ContainsKey($requiredDestination)) {
            throw "安装清单缺少必要的目标文件：$requiredDestination"
        }
    }

    return $entryCount
}

foreach ($requiredFile in @($installerPath, $manifestPath, $packageXmlPath, $versionPath)) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "缺少必要的安装源文件：$requiredFile"
    }
}

$manifestEntryCount = Assert-FBXTo3dsMaxSourceManifest -SourceRoot $launcherRoot -ManifestFile $manifestPath

$packageXml = New-Object System.Xml.XmlDocument
$packageXml.PreserveWhitespace = $true
$packageXml.Load($packageXmlPath)
$package = $packageXml.ApplicationPackage
if ($null -eq $package) {
    throw "PackageContents.xml 不包含 ApplicationPackage 根元素。"
}
if ([string]$package.Name -cne $expectedPackageName) {
    throw "PackageContents.xml 中的 Name 不正确：$($package.Name)"
}
if ([string]$package.UpgradeCode -ine $expectedUpgradeCode) {
    throw "PackageContents.xml 中的 UpgradeCode 不正确：$($package.UpgradeCode)"
}

$declaredVersion = [System.IO.File]::ReadAllText($versionPath, $strictUtf8).Trim()
if ([string]::IsNullOrWhiteSpace($declaredVersion) -or [string]$package.AppVersion -cne $declaredVersion) {
    throw "版本标记不一致：PackageContents.xml=$($package.AppVersion)，FBXTo3dsMax.version=$declaredVersion"
}

$maxExecutable = Resolve-FBXTo3dsMaxMaxExecutable -InputPath $MaxRoot
$maxMajorToYear = @{
    25 = 2023
    26 = 2024
    27 = 2025
    28 = 2026
}
$maxMajor = [int]$maxExecutable.VersionInfo.FileMajorPart
if (-not $maxMajorToYear.ContainsKey($maxMajor)) {
    throw "不支持 3ds Max $($maxExecutable.VersionInfo.FileVersion)。插件 v$declaredVersion 支持 3ds Max 2023-2026。"
}
$maxYear = [int]$maxMajorToYear[$maxMajor]

$runtimeRequirements = $package.Components.RuntimeRequirements
if ($null -eq $runtimeRequirements) {
    throw "PackageContents.xml 不包含 RuntimeRequirements。"
}
$seriesMin = [int]$runtimeRequirements.SeriesMin
$seriesMax = [int]$runtimeRequirements.SeriesMax
if ($maxYear -lt $seriesMin -or $maxYear -gt $seriesMax) {
    throw "所选 3ds Max $maxYear 超出声明的支持范围 $seriesMin-$seriesMax。"
}

$runningMax = @(
    Get-Process -Name "3dsmax", "3dsmaxbatch" -ErrorAction SilentlyContinue |
        ForEach-Object {
            $processPath = $null
            try {
                $processPath = $_.Path
            }
            catch {
                $processPath = "<路径不可用>"
            }
            [PSCustomObject]@{
                Id = $_.Id
                Name = $_.ProcessName
                Path = $processPath
            }
        }
)
if ($runningMax.Count -gt 0) {
    $runningDescription = ($runningMax | ForEach-Object {
        "PID $($_.Id) $($_.Name) [$($_.Path)]"
    }) -join "; "
    if ($runningMax.Count -eq 1 -and $runningMax[0].Name -ieq "3dsmax") {
        $recoveryInstruction = "请把这个安装脚本拖入该 Max 窗口：$installerPath 。也可以关闭 Max 后重新运行本启动器。"
    }
    else {
        $recoveryInstruction = "请关闭所有 Max/Max Batch 进程后重新运行本启动器；也可以只保留一个交互式 3ds Max 实例，再把这个安装脚本拖入该窗口：$installerPath 。"
    }
    throw "已有 3ds Max 进程正在运行：$runningDescription。未启动或复制任何内容。为避免并发写入插件，$recoveryInstruction"
}

if ($installerPath.Contains('"')) {
    throw "安装器路径包含不受支持的双引号：$installerPath"
}

$launcherArguments = '-q -silent -U MAXScript "' + $installerPath + '"'
$previousLauncherMarker = $env:F2M_POWERSHELL_LAUNCH
$env:F2M_POWERSHELL_LAUNCH = "1"
try {
    $maxProcess = Start-Process `
        -FilePath $maxExecutable.FullName `
        -ArgumentList $launcherArguments `
        -WorkingDirectory $maxExecutable.DirectoryName `
        -PassThru
}
finally {
    if ($null -eq $previousLauncherMarker) {
        Remove-Item Env:F2M_POWERSHELL_LAUNCH -ErrorAction SilentlyContinue
    }
    else {
        $env:F2M_POWERSHELL_LAUNCH = $previousLauncherMarker
    }
}

Write-Host ""
Write-Host "已启动 3ds Max $maxYear（进程号 $($maxProcess.Id)）。" -ForegroundColor Green
Write-Host "标准事务式安装器 Install_FBXTo3dsMax.ms 将执行安装。"
Write-Host "此 PowerShell 启动器没有复制任何插件文件。插件 v$declaredVersion 的预检已通过，安装清单共 $manifestEntryCount 项。"
