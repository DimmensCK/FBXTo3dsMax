#requires -Version 5.1

function Read-F2MLogTextStrict {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Log file does not exist: $Path"
    }
    try {
        [byte[]]$bytes = [IO.File]::ReadAllBytes($Path)
    }
    catch {
        throw "Log file is unreadable: $Path; $($_.Exception.Message)"
    }
    if ($bytes.Length -eq 0) {
        throw "Log file is empty: $Path"
    }
    $text = [Text.Encoding]::Default.GetString($bytes)
    if ([string]::IsNullOrWhiteSpace($text)) {
        throw "Log file has no readable text: $Path"
    }
    return $text
}

function Get-F2MMarkerWindow {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Text,

        [Parameter(Mandatory = $true)]
        [ValidateRange(1, 2147483647)]
        [int]$TargetPid,

        [Parameter(Mandatory = $true)]
        [string]$BeginMessagePattern,

        [Parameter(Mandatory = $true)]
        [string]$EndMessagePattern,

        [switch]$StructuredMaxLog
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        throw 'Log text is empty; cannot establish a BEGIN/END window.'
    }

    $regexOptions = (
        [Text.RegularExpressions.RegexOptions]::IgnoreCase -bor
        [Text.RegularExpressions.RegexOptions]::CultureInvariant
    )
    try {
        $beginRegex = New-Object Text.RegularExpressions.Regex(
            $BeginMessagePattern,
            $regexOptions
        )
        $endRegex = New-Object Text.RegularExpressions.Regex(
            $EndMessagePattern,
            $regexOptions
        )
    }
    catch {
        throw "Invalid BEGIN/END regex: $($_.Exception.Message)"
    }

    $records = New-Object 'System.Collections.Generic.List[object]'
    $lines = [regex]::Split($Text, "\r?\n")
    $maxLinePattern = (
        '^\s*\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\s+' +
        '\S+:\s+\[(?<pid>\d+)\]\s+\[[^\]]+\]\s+(?<message>.*)$'
    )
    for ($lineIndex = 0; $lineIndex -lt $lines.Count; $lineIndex++) {
        $line = [string]$lines[$lineIndex]
        if ($StructuredMaxLog) {
            $lineMatch = [regex]::Match(
                $line,
                $maxLinePattern,
                $regexOptions
            )
            if (-not $lineMatch.Success) {
                continue
            }
            if ([int]$lineMatch.Groups['pid'].Value -ne $TargetPid) {
                continue
            }
            $message = $lineMatch.Groups['message'].Value.Trim()
        }
        else {
            $message = $line.Trim()
        }
        $records.Add([pscustomobject]@{
            line_index = $lineIndex
            line = $line
            message = $message
        })
    }

    $expectedPidPattern = (
        '(?:^|\s)PID=' + [regex]::Escape(([string]$TargetPid)) + '(?:\s|$)'
    )
    $beginRecords = @(
        $records |
            Where-Object {
                $beginRegex.IsMatch($_.message) -and
                [regex]::IsMatch(
                    $_.message,
                    $expectedPidPattern,
                    $regexOptions
                )
            }
    )
    if ($beginRecords.Count -ne 1) {
        throw (
            "BEGIN marker count for PID=$TargetPid is not 1: " +
            "$($beginRecords.Count)"
        )
    }
    $beginRecord = $beginRecords[0]

    $endRecords = @(
        $records |
            Where-Object {
                $endRegex.IsMatch($_.message) -and
                [regex]::IsMatch(
                    $_.message,
                    $expectedPidPattern,
                    $regexOptions
                )
            }
    )
    if ($endRecords.Count -ne 1) {
        throw (
            "END marker count for PID=$TargetPid is not 1: " +
            "$($endRecords.Count)"
        )
    }
    $endRecord = $endRecords[0]
    if ($endRecord.line_index -le $beginRecord.line_index) {
        throw "END marker for PID=$TargetPid does not follow BEGIN."
    }

    $nestedBegin = @(
        $records |
            Where-Object {
                $_.line_index -gt $beginRecord.line_index -and
                $_.line_index -le $endRecord.line_index -and
                $beginRegex.IsMatch($_.message)
            }
    )
    if ($nestedBegin.Count -ne 0) {
        throw "Marker window for PID=$TargetPid contains a nested BEGIN."
    }

    $beginUtcMatch = [regex]::Match(
        $beginRecord.message,
        '(?:^|\s)UTC=(?<utc>\S+)(?:\s|$)',
        $regexOptions
    )
    $endUtcMatch = [regex]::Match(
        $endRecord.message,
        '(?:^|\s)UTC=(?<utc>\S+)(?:\s|$)',
        $regexOptions
    )
    if (-not $beginUtcMatch.Success -or -not $endUtcMatch.Success) {
        throw "BEGIN/END markers for PID=$TargetPid are missing UTC."
    }
    $beginUtc = [DateTimeOffset]::MinValue
    $endUtc = [DateTimeOffset]::MinValue
    $dateStyles = (
        [Globalization.DateTimeStyles]::AssumeUniversal -bor
        [Globalization.DateTimeStyles]::AdjustToUniversal
    )
    if (
        -not [DateTimeOffset]::TryParse(
            $beginUtcMatch.Groups['utc'].Value,
            [Globalization.CultureInfo]::InvariantCulture,
            $dateStyles,
            [ref]$beginUtc
        ) -or
        -not [DateTimeOffset]::TryParse(
            $endUtcMatch.Groups['utc'].Value,
            [Globalization.CultureInfo]::InvariantCulture,
            $dateStyles,
            [ref]$endUtc
        )
    ) {
        throw "BEGIN/END UTC for PID=$TargetPid cannot be parsed."
    }
    if ($endUtc -lt $beginUtc) {
        throw "END UTC for PID=$TargetPid precedes BEGIN UTC."
    }

    # END proves that the test body reached its own completion path.  It is not
    # the native-process audit boundary: 3ds Max can still emit GC/fatal records
    # while Python and MAXScript wrappers are being destroyed during shutdown.
    # A completed after-run snapshot therefore audits every structured record
    # owned by the target engine PID from BEGIN through that PID's final line.
    # Unstructured listener logs cannot safely attribute arbitrary tail lines,
    # so their evidence remains bounded by the unique token/PID markers.
    $scanEndRecord = $endRecord
    if ($StructuredMaxLog) {
        $targetTailRecords = @(
            $records |
                Where-Object {
                    $_.line_index -ge $endRecord.line_index
                }
        )
        if ($targetTailRecords.Count -eq 0) {
            throw "Structured PID tail for PID=$TargetPid is incomplete."
        }
        $scanEndRecord = $targetTailRecords[-1]
    }

    $windowRecords = @(
        $records |
            Where-Object {
                $_.line_index -ge $beginRecord.line_index -and
                $_.line_index -le $scanEndRecord.line_index
            }
    )
    if ($windowRecords.Count -lt 2) {
        throw "BEGIN/END window for PID=$TargetPid is incomplete."
    }

    return [pscustomobject]@{
        target_pid = $TargetPid
        structured_max_log = [bool]$StructuredMaxLog
        begin_utc = $beginUtc.UtcDateTime
        end_utc = $endUtc.UtcDateTime
        begin_line_index = [int]$beginRecord.line_index
        end_line_index = [int]$endRecord.line_index
        scan_end_line_index = [int]$scanEndRecord.line_index
        post_end_line_count = [int](
            @(
                $windowRecords |
                    Where-Object {
                        $_.line_index -gt $endRecord.line_index
                    }
            ).Count
        )
        line_count = [int]$windowRecords.Count
        text = (($windowRecords | ForEach-Object { $_.line }) -join "`r`n")
    }
}

function Get-F2MCriticalLogHits {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Text,

        [Parameter(Mandatory = $true)]
        [string[]]$Patterns
    )

    $hits = New-Object 'System.Collections.Generic.List[string]'
    foreach ($pattern in $Patterns) {
        if (
            [regex]::IsMatch(
                $Text,
                $pattern,
                (
                    [Text.RegularExpressions.RegexOptions]::IgnoreCase -bor
                    [Text.RegularExpressions.RegexOptions]::CultureInvariant
                )
            )
        ) {
            $hits.Add($pattern)
        }
    }
    return $hits.ToArray()
}
