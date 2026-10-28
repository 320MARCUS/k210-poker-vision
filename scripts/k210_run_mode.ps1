param(
    [string]$ComPort = "COM3",
    [ValidateSet("SMOKE", "BENCHMARK", "STABILITY", "HOLDOUT", "DEMO")]
    [string]$Mode = "SMOKE",
    [int]$TimeoutSeconds = 180,
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$stamp = [DateTimeOffset]::UtcNow.ToString("yyyyMMdd-HHmmss")
if (-not $OutputPath) {
    $OutputPath = Join-Path $projectRoot "artifacts\k210-serial\k210-$($Mode.ToLower())-$stamp.log"
}
$OutputPath = [IO.Path]::GetFullPath($OutputPath)
$outputDirectory = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $outputDirectory)) {
    New-Item -ItemType Directory -Path $outputDirectory | Out-Null
}
$jsonlPath = [IO.Path]::ChangeExtension($OutputPath, ".jsonl")

$serial = [System.IO.Ports.SerialPort]::new(
    $ComPort,
    115200,
    [System.IO.Ports.Parity]::None,
    8,
    [System.IO.Ports.StopBits]::One
)
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.ReadTimeout = 250
$serial.WriteTimeout = 1000
$serial.NewLine = "`r`n"
$transcript = [System.Text.StringBuilder]::new()

function Pump-Serial {
    param([double]$Seconds)
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($Seconds)
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        if ($serial.BytesToRead -gt 0) {
            $chunk = $serial.ReadExisting()
            [void]$transcript.Append($chunk)
            Write-Host -NoNewline $chunk
        }
        else {
            Start-Sleep -Milliseconds 50
        }
    }
}

function Send-ReplLine {
    param([string]$Command)
    [void]$transcript.AppendLine()
    [void]$transcript.AppendLine("# >>> $Command")
    $serial.WriteLine($Command)
}

$terminalPattern = '(?m)^PVJSON .*"event"\s*:\s*"(?:summary|error)"'

try {
    $serial.Open()
    [void]$transcript.AppendLine("# K210 $Mode run")
    [void]$transcript.AppendLine(
        "# Port=$ComPort baud=115200 data=8 parity=N stop=1 DTR=false RTS=false"
    )
    [void]$transcript.AppendLine("# StartedUTC=$([DateTimeOffset]::UtcNow.ToString('o'))")

    $serial.Write(([string][char]3) * 2)
    Pump-Serial -Seconds 1.2
    $serial.DiscardInBuffer()

    Send-ReplLine 'import sys'
    Pump-Serial -Seconds 0.4
    Send-ReplLine 'sys.path.insert(0, "/sd/k210")'
    Pump-Serial -Seconds 0.4
    Send-ReplLine 'import poker_app'
    Pump-Serial -Seconds 1.0

    if ($transcript.ToString() -match "(?m)^Traceback") {
        throw "poker_app import failed; inspect the raw log"
    }

    Send-ReplLine ('poker_app.main("%s")' -f $Mode)
    $started = [DateTimeOffset]::UtcNow
    while (([DateTimeOffset]::UtcNow - $started).TotalSeconds -lt $TimeoutSeconds) {
        Pump-Serial -Seconds 0.2
        if ($transcript.ToString() -match $terminalPattern) {
            break
        }
        if (-not $serial.IsOpen) {
            break
        }
    }
    Pump-Serial -Seconds 0.5
}
finally {
    if ($serial.IsOpen) {
        $serial.Close()
    }
    $serial.Dispose()
    [void]$transcript.AppendLine()
    [void]$transcript.AppendLine("# FinishedUTC=$([DateTimeOffset]::UtcNow.ToString('o'))")
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($OutputPath, $transcript.ToString(), $utf8NoBom)

    $events = [System.Collections.Generic.List[object]]::new()
    foreach ($line in ($transcript.ToString() -split "`r?`n")) {
        if (-not $line.StartsWith("PVJSON ")) {
            continue
        }
        try {
            $payload = $line.Substring(7) | ConvertFrom-Json
            $payload | Add-Member `
                -NotePropertyName captured_at_utc `
                -NotePropertyValue ([DateTimeOffset]::UtcNow.ToString("o"))
            $payload | Add-Member -NotePropertyName captured_port -NotePropertyValue $ComPort
            $events.Add($payload)
        }
        catch {
            [void]$transcript.AppendLine("# PVJSON parse error: $($_.Exception.Message)")
        }
    }
    $jsonLines = @($events | ForEach-Object { $_ | ConvertTo-Json -Compress -Depth 20 })
    [IO.File]::WriteAllLines($jsonlPath, $jsonLines, $utf8NoBom)
}

$rawText = $transcript.ToString()
$terminalSeen = $rawText -match $terminalPattern
Write-Output ""
Write-Output "raw_log=$OutputPath"
Write-Output "jsonl_log=$jsonlPath"
Write-Output "terminal_event_seen=$terminalSeen"
if (-not $terminalSeen) {
    exit 4
}
