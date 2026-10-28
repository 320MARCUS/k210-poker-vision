[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceDir,
    [string]$OutputManifest
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$imageDir = Join-Path $projectRoot "docs\images"
$mediaDir = Join-Path $projectRoot "media"
if (-not $OutputManifest) {
    $OutputManifest = Join-Path $projectRoot "results\media_manifest.json"
}

$ffmpegCandidates = @()
if ($env:FFMPEG_EXE) {
    $ffmpegCandidates += $env:FFMPEG_EXE
}
$ffmpegCandidates += "ffmpeg.exe"
$ffmpeg = $null
foreach ($candidate in $ffmpegCandidates) {
    if ($candidate -eq "ffmpeg.exe") {
        $command = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
        if ($command) {
            $ffmpeg = $command.Source
            break
        }
    }
    elseif (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $ffmpeg = $candidate
        break
    }
}
if (-not $ffmpeg) {
    throw "ffmpeg was not found. Set up FFmpeg or install MaixPy IDE with its bundled tools."
}

$hardwareSource = @(
    Get-ChildItem -LiteralPath $SourceDir -File -Filter "*196_25.jpg"
) | Select-Object -First 1
$detectionSource = @(
    Get-ChildItem -LiteralPath $SourceDir -File -Filter "*202_25.jpg"
) | Select-Object -First 1
$videoSource = Join-Path $SourceDir "3b4390c309b64c847a855c289309e483.mp4"
if (-not $hardwareSource) {
    throw "Hardware source image ending in 196_25.jpg was not found."
}
if (-not $detectionSource) {
    throw "Detection source image ending in 202_25.jpg was not found."
}
$hardwareSource = $hardwareSource.FullName
$detectionSource = $detectionSource.FullName
foreach ($path in @($hardwareSource, $detectionSource, $videoSource)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Media input not found: $path"
    }
}

New-Item -ItemType Directory -Force -Path $imageDir | Out-Null
New-Item -ItemType Directory -Force -Path $mediaDir | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputManifest) | Out-Null

$hardwareOutput = Join-Path $imageDir "k210-hardware.jpg"
$detectionOutput = Join-Path $imageDir "k210-lcd-detection.jpg"
$videoOutput = Join-Path $mediaDir "k210-demo.mp4"
$posterOutput = Join-Path $mediaDir "k210-demo-poster.jpg"

& $ffmpeg -hide_banner -loglevel error -y -i $hardwareSource -vf "scale=1200:1600" -q:v 3 -map_metadata -1 $hardwareOutput
if ($LASTEXITCODE -ne 0) { throw "Failed to prepare hardware image." }
& $ffmpeg -hide_banner -loglevel error -y -i $detectionSource -vf "scale=1200:1600" -q:v 3 -map_metadata -1 $detectionOutput
if ($LASTEXITCODE -ne 0) { throw "Failed to prepare detection image." }
& $ffmpeg -hide_banner -loglevel error -y -ss 1 -i $videoSource -t 55 -an -map_metadata -1 -c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p -movflags +faststart $videoOutput
if ($LASTEXITCODE -ne 0) { throw "Failed to prepare demo video." }
& $ffmpeg -hide_banner -loglevel error -y -ss 12 -i $videoSource -frames:v 1 -an -map_metadata -1 -vf "scale=720:-2" -q:v 3 $posterOutput
if ($LASTEXITCODE -ne 0) { throw "Failed to prepare video poster." }

function Get-FileRecord {
    param([string]$Path)
    $item = Get-Item -LiteralPath $Path
    return [ordered]@{
        bytes = $item.Length
        sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

$manifest = [ordered]@{
    status = "reviewed-public-derivatives"
    privacy_review = [ordered]@{
        faces = "none visible"
        identity_documents = "none visible"
        screens_messages_or_qr_codes = "none visible in selected frames"
        audio = "removed from public video"
        metadata = "stripped from public derivatives"
    }
    source_policy = "Originals remain private and are identified by basename and SHA-256 only."
    items = @(
        [ordered]@{
            source = [IO.Path]::GetFileName($hardwareSource)
            source_file = Get-FileRecord $hardwareSource
            output = "docs/images/k210-hardware.jpg"
            output_file = Get-FileRecord $hardwareOutput
            transform = "scale to 1200x1600, strip metadata"
        },
        [ordered]@{
            source = [IO.Path]::GetFileName($detectionSource)
            source_file = Get-FileRecord $detectionSource
            output = "docs/images/k210-lcd-detection.jpg"
            output_file = Get-FileRecord $detectionOutput
            transform = "scale to 1200x1600, strip metadata"
        },
        [ordered]@{
            source = [IO.Path]::GetFileName($videoSource)
            source_file = Get-FileRecord $videoSource
            output = "media/k210-demo.mp4"
            output_file = Get-FileRecord $videoOutput
            transform = "trim 1s to 56s, remove audio and metadata, H.264 yuv420p"
        },
        [ordered]@{
            source = [IO.Path]::GetFileName($videoSource)
            source_file = Get-FileRecord $videoSource
            output = "media/k210-demo-poster.jpg"
            output_file = Get-FileRecord $posterOutput
            transform = "frame at 12s, no synthetic boxes, strip metadata"
        }
    )
}
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText(
    $OutputManifest,
    ($manifest | ConvertTo-Json -Depth 8),
    $utf8NoBom
)
Write-Output $OutputManifest
