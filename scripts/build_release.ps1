[CmdletBinding()]
param(
    [switch]$SkipMediaRefresh,
    [string]$MediaSourceDir
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$projectRoot = Split-Path -Parent $PSScriptRoot
$distRoot = Join-Path $projectRoot "dist"
$githubRoot = Join-Path $distRoot "github"
$publicCopy = Join-Path $githubRoot "k210-poker-vision"
$releaseRoot = Join-Path $distRoot "release"
$pcStage = Join-Path $distRoot "pc-staging"
$sdVerifyRoot = Join-Path $distRoot "sd-verify"

function Assert-UnderDist {
    param([string]$Target)
    $full = [IO.Path]::GetFullPath($Target)
    $prefix = [IO.Path]::GetFullPath($distRoot).TrimEnd("\") + "\"
    if (-not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify path outside dist: $full"
    }
    return $full
}

foreach ($path in @($releaseRoot, $pcStage, $sdVerifyRoot)) {
    $safe = Assert-UnderDist $path
    if (Test-Path -LiteralPath $safe) {
        Remove-Item -LiteralPath $safe -Recurse -Force
    }
}

$preparedMedia = Join-Path $projectRoot "media\k210-demo.mp4"
if ($MediaSourceDir) {
    if (-not (Test-Path -LiteralPath $MediaSourceDir -PathType Container)) {
        throw "Source media directory not found: $MediaSourceDir"
    }
    & (Join-Path $PSScriptRoot "prepare_media.ps1") -SourceDir $MediaSourceDir
}
elseif (-not $SkipMediaRefresh -and -not (Test-Path -LiteralPath $preparedMedia)) {
    throw "Prepared media is missing. Pass -MediaSourceDir or prepare media first."
}

& (Join-Path $PSScriptRoot "build_public_copy.ps1")
$sdResult = & (Join-Path $PSScriptRoot "build_k210_sd.ps1") | ConvertFrom-Json
New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null

$sdArchive = Join-Path $releaseRoot "k210-poker-vision-sd-v1.0.0.zip"
if ([IO.Path]::GetFullPath($sdResult.path) -ne [IO.Path]::GetFullPath($sdArchive)) {
    Copy-Item -LiteralPath $sdResult.path -Destination $sdArchive -Force
}

New-Item -ItemType Directory -Force -Path $sdVerifyRoot | Out-Null
[IO.Compression.ZipFile]::ExtractToDirectory($sdArchive, $sdVerifyRoot)
$sdVerification = & (Join-Path $sdVerifyRoot "verify_package.ps1") | ConvertFrom-Json
if ($sdVerification.status -ne "ok") {
    throw "SD package verification did not pass."
}

New-Item -ItemType Directory -Force -Path $pcStage | Out-Null
foreach ($item in Get-ChildItem -LiteralPath $publicCopy -Force) {
    Copy-Item -LiteralPath $item.FullName -Destination $pcStage -Recurse -Force
}
$pcArchive = Join-Path $releaseRoot "k210-poker-vision-pc-v1.0.0.zip"
Compress-Archive -Path (Join-Path $pcStage "*") -DestinationPath $pcArchive -CompressionLevel Optimal -Force

$verifiedModel = Join-Path $projectRoot "artifacts\run-k210-live-160x120-pool4\k210-poker-live-160x120.kmodel"
$candidateRoot = Join-Path $projectRoot "artifacts\run-160x120-finetune-e05"
$candidateModel = Join-Path $candidateRoot "k210-poker-160x120-e20.kmodel"
$candidateOnnx = Join-Path $candidateRoot "k210-poker-160x120-e20.onnx"
foreach ($path in @($verifiedModel, $candidateModel, $candidateOnnx)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Release input not found: $path"
    }
}

Copy-Item -LiteralPath $verifiedModel -Destination (Join-Path $releaseRoot "k210-poker-vision-default.kmodel") -Force
Copy-Item -LiteralPath $candidateModel -Destination (Join-Path $releaseRoot "candidate-e20-physical-verification-pending.kmodel") -Force
Copy-Item -LiteralPath $candidateOnnx -Destination (Join-Path $releaseRoot "candidate-e20-physical-verification-pending.onnx") -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "docs\model-card.md") -Destination (Join-Path $releaseRoot "MODEL_CARD.md") -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "media\k210-demo.mp4") -Destination $releaseRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "media\k210-demo-poster.jpg") -Destination $releaseRoot -Force

$candidateStatus = [ordered]@{
    model = "160x120 e20"
    sha256 = (Get-FileHash -LiteralPath $candidateModel -Algorithm SHA256).Hash.ToLowerInvariant()
    validation_map50 = 0.48057453572343073
    validation_identity_accuracy = 0.5878594249201278
    validation_identity_coverage = 0.747016706443914
    nine_of_clubs_ap50 = 0.5048777789866896
    physical_verification = "pending"
    intended_use = "reproducibility and optimization reference only"
}
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText(
    (Join-Path $releaseRoot "candidate-e20-physical-verification-pending.json"),
    ($candidateStatus | ConvertTo-Json -Depth 5),
    $utf8NoBom
)

$assets = @(Get-ChildItem -LiteralPath $releaseRoot -File | Sort-Object Name)
$lines = foreach ($asset in $assets) {
    $hash = (Get-FileHash -LiteralPath $asset.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $($asset.Name)"
}
$lines | Set-Content -LiteralPath (Join-Path $releaseRoot "SHA256SUMS.txt") -Encoding ASCII

$releaseManifest = [ordered]@{}
foreach ($asset in $assets) {
    $releaseManifest[$asset.Name] = [ordered]@{
        bytes = $asset.Length
        sha256 = (Get-FileHash -LiteralPath $asset.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$releaseManifest["SHA256SUMS.txt"] = [ordered]@{
    bytes = (Get-Item -LiteralPath (Join-Path $releaseRoot "SHA256SUMS.txt")).Length
    sha256 = (Get-FileHash -LiteralPath (Join-Path $releaseRoot "SHA256SUMS.txt") -Algorithm SHA256).Hash.ToLowerInvariant()
}
$manifestJson = $releaseManifest | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText(
    (Join-Path $releaseRoot "release_manifest.json"),
    $manifestJson,
    $utf8NoBom
)

[pscustomobject]@{
    status = "ok"
    public_copy = $publicCopy
    release_root = $releaseRoot
    sd_package = $sdArchive
    pc_package = $pcArchive
    assets = @(Get-ChildItem -LiteralPath $releaseRoot -File | Select-Object -ExpandProperty Name)
} | ConvertTo-Json -Depth 5
