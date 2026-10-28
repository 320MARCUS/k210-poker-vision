param(
    [string]$ComPort,
    [string]$OutputPath,
    [int]$TimeoutSeconds = 360,
    [switch]$StopAfterSummary,
    [switch]$ListPorts,
    [switch]$ProbeStability,
    [string[]]$ExpectedPorts = @("COM3", "COM4"),
    [int]$StableSeconds = 30
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$utcNow = [DateTimeOffset]::UtcNow
$stamp = $utcNow.ToString("yyyyMMdd-HHmmss")

function Get-PortSnapshot {
    $serialNames = @([System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object -Unique)
    $pnpError = $null
    $ftdiDevices = @()
    try {
        $ftdiDevices = @(
            Get-CimInstance Win32_PnPEntity -ErrorAction Stop |
                Where-Object {
                    $_.PNPDeviceID -match "VID_0403&PID_6010" -and
                    $_.Name -match "\(COM\d+\)"
                } |
                Select-Object Name, DeviceID, PNPDeviceID, Status
        )
    }
    catch {
        $pnpError = $_.Exception.Message
    }
    [pscustomobject]@{
        timestamp_utc = [DateTimeOffset]::UtcNow.ToString("o")
        serial_port_names = $serialNames
        ftdi_devices = $ftdiDevices
        pnp_query_error = $pnpError
    }
}

if ($ListPorts) {
    Get-PortSnapshot | ConvertTo-Json -Depth 8
    exit 0
}

if ($ProbeStability) {
    $started = [DateTimeOffset]::UtcNow
    $samples = [System.Collections.Generic.List[object]]::new()
    $stable = $true
    $missingObserved = [System.Collections.Generic.HashSet[string]]::new()
    while (([DateTimeOffset]::UtcNow - $started).TotalSeconds -lt $StableSeconds) {
        $snapshot = Get-PortSnapshot
        $present = @($snapshot.serial_port_names)
        $missing = @($ExpectedPorts | Where-Object { $present -notcontains $_ })
        foreach ($port in $missing) {
            [void]$missingObserved.Add($port)
            $stable = $false
        }
        $samples.Add(
            [pscustomobject]@{
                timestamp_utc = $snapshot.timestamp_utc
                present = $present
                missing = $missing
            }
        )
        Start-Sleep -Milliseconds 500
    }
    $result = [ordered]@{
        status = $(if ($stable) { "passed" } else { "intermittent" })
        observed_seconds = [math]::Round((([DateTimeOffset]::UtcNow - $started).TotalSeconds), 3)
        expected_ports = $ExpectedPorts
        missing_observed = @($missingObserved | Sort-Object)
        samples = $samples
    }
    $result | ConvertTo-Json -Depth 8
    if (-not $stable) {
        exit 2
    }
    exit 0
}

if (-not $ComPort) {
    throw "Specify -ComPort after identifying the MaixPy REPL UART. Use -ListPorts for a read-only inventory."
}
$available = @([System.IO.Ports.SerialPort]::GetPortNames())
if ($available -notcontains $ComPort) {
    throw "Serial port $ComPort is not currently enumerable. Stable ports: $($available -join ', ')"
}
if ($TimeoutSeconds -le 0) {
    throw "TimeoutSeconds must be positive."
}

if (-not $OutputPath) {
    $OutputPath = Join-Path $projectRoot "artifacts\k210-serial\k210-$stamp.log"
}
$OutputPath = [IO.Path]::GetFullPath($OutputPath)
$outputDirectory = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $outputDirectory)) {
    New-Item -ItemType Directory -Path $outputDirectory | Out-Null
}
$jsonlPath = [IO.Path]::ChangeExtension($OutputPath, ".jsonl")
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$rawWriter = New-Object System.IO.StreamWriter($OutputPath, $false, $utf8NoBom)
$jsonWriter = New-Object System.IO.StreamWriter($jsonlPath, $false, $utf8NoBom)
$rawWriter.AutoFlush = $true
$jsonWriter.AutoFlush = $true
$serial = [System.IO.Ports.SerialPort]::new(
    $ComPort,
    115200,
    [System.IO.Ports.Parity]::None,
    8,
    [System.IO.Ports.StopBits]::One
)
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$buffer = New-Object System.Text.StringBuilder
$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
$eventCount = 0
$summarySeen = $false
$partialLine = $null

function Write-RawLine {
    param([string]$Line)
    $rawWriter.WriteLine($Line)
    if (-not $Line.StartsWith("PVJSON ")) {
        return
    }
    $payloadText = $Line.Substring(7)
    try {
        $payload = $payloadText | ConvertFrom-Json
        $payload | Add-Member -NotePropertyName captured_at_utc -NotePropertyValue ([DateTimeOffset]::UtcNow.ToString("o"))
        $payload | Add-Member -NotePropertyName captured_port -NotePropertyValue $ComPort
        $jsonWriter.WriteLine(($payload | ConvertTo-Json -Compress -Depth 20))
        $script:eventCount += 1
        if ($payload.event -eq "summary") {
            $script:summarySeen = $true
        }
    }
    catch {
        $rawWriter.WriteLine("# PVJSON parse error: $($_.Exception.Message)")
    }
}

try {
    $rawWriter.WriteLine("# K210 read-only serial capture")
    $rawWriter.WriteLine("# Port=$ComPort baud=115200 data=8 parity=N stop=1 DTR=false RTS=false")
    $rawWriter.WriteLine("# StartedUTC=$($utcNow.ToString('o'))")
    $serial.Open()
    while ($stopwatch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        $chunk = $serial.ReadExisting()
        if ($chunk) {
            [void]$buffer.Append($chunk)
            $text = $buffer.ToString()
            $lines = $text -split "`r?`n"
            [void]$buffer.Clear()
            if (-not $text.EndsWith("`n") -and -not $text.EndsWith("`r")) {
                $partialLine = $lines[-1]
                $lines = if ($lines.Count -gt 1) { $lines[0..($lines.Count - 2)] } else { @() }
            }
            else {
                $partialLine = $null
            }
            foreach ($line in $lines) {
                Write-RawLine $line
            }
            if ($partialLine) {
                [void]$buffer.Append($partialLine)
                $partialLine = $null
            }
            if ($StopAfterSummary -and $summarySeen) {
                break
            }
        }
        else {
            Start-Sleep -Milliseconds 50
        }
    }
    if ($buffer.Length -gt 0) {
        Write-RawLine $buffer.ToString()
    }
    $rawWriter.WriteLine(
        "# FinishedUTC=$([DateTimeOffset]::UtcNow.ToString('o')) events=$eventCount summary=$summarySeen"
    )
}
catch {
    $rawWriter.WriteLine("# CAPTURE ERROR: $($_.Exception.Message)")
    Write-Error $_
    exit 3
}
finally {
    if ($serial.IsOpen) {
        $serial.Close()
    }
    $serial.Dispose()
    $rawWriter.Dispose()
    $jsonWriter.Dispose()
}

Write-Output "raw_log=$OutputPath"
Write-Output "jsonl_log=$jsonlPath"
Write-Output "pvjson_events=$eventCount"
Write-Output "summary_seen=$summarySeen"
if ($StopAfterSummary -and -not $summarySeen) {
    exit 4
}
exit 0
