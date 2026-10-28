param(
    [Parameter(Mandatory = $true)]
    [string]$LocalPath,
    [Parameter(Mandatory = $true)]
    [string]$RemotePath,
    [string]$ComPort = "COM3",
    [int]$BaudRate = 115200,
    [int]$ChunkBytes = 384,
    [int]$AckBatch = 16,
    [int]$TimeoutSeconds = 900,
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$LocalPath = [IO.Path]::GetFullPath($LocalPath)
if (-not (Test-Path -LiteralPath $LocalPath -PathType Leaf)) {
    throw "Local file not found: $LocalPath"
}
if ($ChunkBytes -lt 48 -or $ChunkBytes -gt 1536 -or ($ChunkBytes % 3) -ne 0) {
    throw "ChunkBytes must be a multiple of 3 between 48 and 1536."
}
if ($AckBatch -lt 1 -or $AckBatch -gt 64) {
    throw "AckBatch must be between 1 and 64."
}
$available = @([IO.Ports.SerialPort]::GetPortNames())
if ($available -notcontains $ComPort) {
    throw "Serial port $ComPort is unavailable. Enumerated ports: $($available -join ', ')"
}

$stamp = [DateTimeOffset]::UtcNow.ToString("yyyyMMdd-HHmmss")
if (-not $OutputPath) {
    $safeName = [IO.Path]::GetFileName($LocalPath)
    $OutputPath = Join-Path $projectRoot "artifacts\k210-serial\xfer-$safeName-$stamp.log"
}
$OutputPath = [IO.Path]::GetFullPath($OutputPath)
$outputDirectory = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $outputDirectory)) {
    New-Item -ItemType Directory -Path $outputDirectory | Out-Null
}

$serial = [IO.Ports.SerialPort]::new(
    $ComPort,
    $BaudRate,
    [IO.Ports.Parity]::None,
    8,
    [IO.Ports.StopBits]::One
)
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.ReadTimeout = 250
$serial.WriteTimeout = 5000
$serial.NewLine = "`r`n"
$transcript = [Text.StringBuilder]::new()

function Pump-Serial {
    param([double]$Seconds)
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($Seconds)
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        if ($serial.BytesToRead -gt 0) {
            $chunk = $serial.ReadExisting()
            [void]$transcript.Append($chunk)
        }
        else {
            Start-Sleep -Milliseconds 25
        }
    }
}

function Wait-SerialMarker {
    param(
        [string]$Marker,
        [int]$Seconds = 30
    )
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($Seconds)
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        Pump-Serial -Seconds 0.1
        if ($transcript.ToString().Contains($Marker)) {
            return
        }
    }
    throw "Timed out waiting for serial marker: $Marker"
}

function Wait-AckCount {
    param(
        [int]$ExpectedCount,
        [int]$Seconds = 60
    )
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($Seconds)
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        Pump-Serial -Seconds 0.1
        $count = [regex]::Matches($transcript.ToString(), "PVXFER_ACK").Count
        if ($count -ge $ExpectedCount) {
            return
        }
    }
    throw "Timed out waiting for ACK count $ExpectedCount."
}

$receiver = @"
import sys
import ubinascii
path = $(ConvertTo-Json -InputObject $RemotePath -Compress)
stream = open(path, "wb")
print("PVXFER_READY")
while True:
    line = sys.stdin.readline()
    if not line:
        continue
    if isinstance(line, bytes):
        line = line.strip()
        end_marker = b"END"
    else:
        line = line.strip()
        end_marker = "END"
    if line == end_marker:
        break
    stream.write(ubinascii.a2b_base64(line))
    print("PVXFER_ACK")
stream.close()
print("PVXFER_DONE")
"@

$bytes = [IO.File]::ReadAllBytes($LocalPath)
$offset = 0
$chunkIndex = 0
$started = [DateTimeOffset]::UtcNow
try {
    $serial.Open()
    [void]$transcript.AppendLine("# K210 serial file upload")
    [void]$transcript.AppendLine("# LocalPath=$LocalPath")
    [void]$transcript.AppendLine("# RemotePath=$RemotePath")
    [void]$transcript.AppendLine("# Bytes=$($bytes.Length) Port=$ComPort Baud=$BaudRate")
    [void]$transcript.AppendLine("# StartedUTC=$($started.ToString('o'))")

    $serial.Write(([string][char]3) * 2)
    Pump-Serial -Seconds 1
    $serial.DiscardInBuffer()
    [void]$transcript.Clear()
    $serial.Write([string][char]1)
    Wait-SerialMarker -Marker "raw REPL; CTRL-B to exit" -Seconds 10
    $serial.Write($receiver)
    $serial.Write([string][char]4)
    Wait-SerialMarker -Marker "PVXFER_READY" -Seconds 30
    $ackCount = 0
    $batchSent = 0

    while ($offset -lt $bytes.Length) {
        $count = [Math]::Min($ChunkBytes, $bytes.Length - $offset)
        $chunk = New-Object byte[] $count
        [Array]::Copy($bytes, $offset, $chunk, 0, $count)
        $payload = [Convert]::ToBase64String($chunk)
        $serial.WriteLine($payload)
        $offset += $count
        $chunkIndex += 1
        $batchSent += 1
        if ($batchSent -ge $AckBatch) {
            $ackCount += $batchSent
            Wait-AckCount -ExpectedCount $ackCount -Seconds 60
            $batchSent = 0
        }
        if (($chunkIndex % 128) -eq 0) {
            $elapsed = ([DateTimeOffset]::UtcNow - $started).TotalSeconds
            Write-Output ("uploaded={0}/{1} chunks={2} elapsed_s={3:N1}" -f $offset, $bytes.Length, $chunkIndex, $elapsed)
        }
    }
    if ($batchSent -gt 0) {
        $ackCount += $batchSent
        Wait-AckCount -ExpectedCount $ackCount -Seconds 60
    }

    $serial.WriteLine("END")
    Wait-SerialMarker -Marker "PVXFER_DONE" -Seconds 30
    $serial.Write([string][char]2)
    Pump-Serial -Seconds 0.5
}
finally {
    if ($serial.IsOpen) {
        $serial.Close()
    }
    $serial.Dispose()
    [void]$transcript.AppendLine()
    [void]$transcript.AppendLine("# FinishedUTC=$([DateTimeOffset]::UtcNow.ToString('o'))")
    $utf8NoBom = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($OutputPath, $transcript.ToString(), $utf8NoBom)
}

Write-Output "raw_log=$OutputPath"
Write-Output "bytes=$($bytes.Length)"
Write-Output "chunks=$chunkIndex"
Write-Output "elapsed_seconds=$([Math]::Round(([DateTimeOffset]::UtcNow - $started).TotalSeconds, 3))"
