[CmdletBinding()]
param(
    [string]$ModelPath,
    [string]$OutputPath,
    [int]$ExpectedModelBytes = 2089896,
    [string]$ExpectedModelSha256 = "060163f63db6b4bb818a3c8483ca2f686f3e7e1331bef09b7567b79422fc3b6a"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $ModelPath) {
    $ModelPath = Join-Path $projectRoot "artifacts\run-k210-live-160x120-pool4\k210-poker-live-160x120.kmodel"
}
if (-not $OutputPath) {
    $OutputPath = Join-Path $projectRoot "dist\release\k210-poker-vision-sd-v1.0.0.zip"
}
$ModelPath = [IO.Path]::GetFullPath($ModelPath)
$OutputPath = [IO.Path]::GetFullPath($OutputPath)
if (-not (Test-Path -LiteralPath $ModelPath -PathType Leaf)) {
    throw "KModel not found: $ModelPath"
}
$model = Get-Item -LiteralPath $ModelPath
if ($model.Length -ne $ExpectedModelBytes) {
    throw "KModel size mismatch: expected $ExpectedModelBytes, got $($model.Length)"
}
$modelHash = (Get-FileHash -LiteralPath $ModelPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($modelHash -ne $ExpectedModelSha256.ToLowerInvariant()) {
    throw "KModel SHA-256 mismatch: $modelHash"
}

$entries = [ordered]@{
    "flash/main.py" = Join-Path $projectRoot "k210\main.py"
    "sd/k210/poker_app.py" = Join-Path $projectRoot "k210\poker_app.py"
    "sd/k210/config.py" = Join-Path $projectRoot "k210\config.py"
    "sd/models/yolov2_k210.kmodel" = $ModelPath
    "README.md" = Join-Path $projectRoot "packaging\sd\README.md"
    "install-sd.bat" = Join-Path $projectRoot "packaging\sd\install-sd.bat"
    "install_sd.ps1" = Join-Path $projectRoot "packaging\sd\install_sd.ps1"
    "verify-package.bat" = Join-Path $projectRoot "packaging\sd\verify-package.bat"
    "verify_package.ps1" = Join-Path $projectRoot "packaging\sd\verify_package.ps1"
    "tools/k210_serial_write_file.ps1" = Join-Path $projectRoot "scripts\k210_serial_write_file.ps1"
}
foreach ($pair in $entries.GetEnumerator()) {
    if (-not (Test-Path -LiteralPath $pair.Value -PathType Leaf)) {
        throw "Package input not found: $($pair.Value)"
    }
}

$manifestFiles = [ordered]@{}
foreach ($pair in $entries.GetEnumerator()) {
    $item = Get-Item -LiteralPath $pair.Value
    $manifestFiles[$pair.Key] = [ordered]@{
        bytes = $item.Length
        sha256 = (Get-FileHash -LiteralPath $pair.Value -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$manifest = [ordered]@{
    format = "k210-poker-vision-sd"
    package = [ordered]@{
        version = "1.0.0"
        status = "public-candidate"
    }
    layout = "Copy the sd tree to the FAT32 card root; optionally install flash/main.py through the MaixPy REPL."
    model = [ordered]@{
        path = "/sd/models/yolov2_k210.kmodel"
        bytes = $model.Length
        sha256 = $modelHash
        input_width = 160
        input_height = 120
        weights_bits = 8
        status = "physically-demonstrated"
        evidence = "camera, KPU, YOLO2 post-processing and LCD display ran on Maix-Bit V2.0"
        unverified = @("three-round full-pipeline FPS", "300-second stability", "104-instance holdout")
    }
    thresholds = [ordered]@{
        box = 0.25
        identity = 0.20
        nms_iou = 0.45
    }
    firmware_observed = "MaixPy 0.6.2"
    files = $manifestFiles
}
$manifestText = $manifest | ConvertTo-Json -Depth 10

$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
$fixedTimestamp = [DateTimeOffset]::new(2026, 10, 28, 0, 0, 0, [TimeSpan]::Zero)
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Add-ZipText {
    param(
        [System.IO.Compression.ZipArchive]$Archive,
        [string]$Name,
        [string]$Text
    )
    $entry = $Archive.CreateEntry($Name, [IO.Compression.CompressionLevel]::Optimal)
    $entry.LastWriteTime = $fixedTimestamp
    $stream = $entry.Open()
    $writer = New-Object System.IO.StreamWriter($stream, $utf8NoBom)
    try {
        $writer.Write($Text)
    }
    finally {
        $writer.Dispose()
    }
}

function Add-ZipFile {
    param(
        [System.IO.Compression.ZipArchive]$Archive,
        [string]$Name,
        [string]$Path
    )
    $entry = $Archive.CreateEntry($Name, [IO.Compression.CompressionLevel]::Optimal)
    $entry.LastWriteTime = $fixedTimestamp
    $target = $entry.Open()
    $source = [IO.File]::OpenRead($Path)
    try {
        $source.CopyTo($target)
    }
    finally {
        $source.Dispose()
        $target.Dispose()
    }
}

$temporaryZip = Join-Path $outputDirectory ("k210-sd-" + [Guid]::NewGuid().ToString("N") + ".tmp")
$archive = [IO.Compression.ZipFile]::Open(
    $temporaryZip,
    [IO.Compression.ZipArchiveMode]::Create
)
try {
    Add-ZipText -Archive $archive -Name "MANIFEST.json" -Text $manifestText
    foreach ($pair in $entries.GetEnumerator()) {
        Add-ZipFile -Archive $archive -Name $pair.Key -Path $pair.Value
    }
}
catch {
    $archive.Dispose()
    if (Test-Path -LiteralPath $temporaryZip) {
        [IO.File]::Delete($temporaryZip)
    }
    throw
}
finally {
    if ($null -ne $archive) {
        $archive.Dispose()
    }
}
Move-Item -LiteralPath $temporaryZip -Destination $OutputPath -Force

$zip = Get-Item -LiteralPath $OutputPath
[pscustomobject]@{
    path = $OutputPath
    bytes = $zip.Length
    sha256 = (Get-FileHash -LiteralPath $OutputPath -Algorithm SHA256).Hash.ToLowerInvariant()
    model_sha256 = $modelHash
    entries = @("MANIFEST.json") + @($entries.Keys)
} | ConvertTo-Json -Depth 5
