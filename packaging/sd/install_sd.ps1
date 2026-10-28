[CmdletBinding()]
param(
    [string]$Drive,
    [switch]$DryRun,
    [switch]$InstallFlashLauncher,
    [string]$ComPort
)

$ErrorActionPreference = "Stop"
$packageRoot = $PSScriptRoot
& (Join-Path $packageRoot "verify_package.ps1")

if (-not $Drive) {
    $Drive = Read-Host "Enter the FAT32 SD-card drive letter (for example F:)"
}
$Drive = $Drive.Trim().TrimEnd("\")
if ($Drive -notmatch "^[A-Za-z]:$") {
    throw "Drive must be a single Windows drive letter such as F:."
}
$letter = $Drive.Substring(0, 1).ToUpperInvariant()
if ($letter -eq $env:SystemDrive.Substring(0, 1).ToUpperInvariant()) {
    throw "Refusing to write to the Windows system drive."
}

$volume = Get-Volume -DriveLetter $letter -ErrorAction Stop
if (-not $volume.DriveLetter) {
    throw "Drive $Drive is not a mounted volume."
}
$allowedBusTypes = @("USB", "SD", "MMC")
$isRemovable = $volume.DriveType -eq "Removable"
$busType = $null
if (-not $isRemovable) {
    try {
        $disk = Get-Partition -DriveLetter $letter -ErrorAction Stop | Get-Disk -ErrorAction Stop
        $busType = [string]$disk.BusType
    }
    catch {
        $busType = $null
    }
}
if (-not $isRemovable -and $allowedBusTypes -notcontains $busType) {
    throw "Drive $Drive is neither removable nor confirmed as a USB/SD device. Refusing to continue."
}
if ($volume.FileSystem -ne "FAT32") {
    throw "Drive $Drive uses $($volume.FileSystem); this package requires FAT32."
}

$targetRoot = "${letter}:\"
$stamp = [DateTimeOffset]::LocalDateTime.ToString("yyyyMMdd-HHmmss")
$backupRoot = Join-Path $targetRoot ".poker-vision-backup-$stamp"
$plan = [ordered]@{
    drive = $Drive
    filesystem = $volume.FileSystem
    source = $packageRoot
    target = $targetRoot
    backup = $backupRoot
    dry_run = [bool]$DryRun
}

if ($DryRun) {
    $plan.status = "validated"
    $plan | ConvertTo-Json -Depth 5
    exit 0
}

New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
foreach ($name in @("k210", "models")) {
    $existing = Join-Path $targetRoot $name
    if (Test-Path -LiteralPath $existing) {
        Copy-Item -LiteralPath $existing -Destination (Join-Path $backupRoot $name) -Recurse -Force
    }
}
if (Test-Path -LiteralPath (Join-Path $targetRoot "main.py")) {
    Copy-Item -LiteralPath (Join-Path $targetRoot "main.py") -Destination (Join-Path $backupRoot "main.py") -Force
}

foreach ($name in @("k210", "models")) {
    $destination = Join-Path $targetRoot $name
    New-Item -ItemType Directory -Force -Path $destination | Out-Null
    Copy-Item -Path (Join-Path $packageRoot "sd\$name\*") -Destination $destination -Recurse -Force
}

$manifest = Get-Content -LiteralPath (Join-Path $packageRoot "MANIFEST.json") -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($entry in $manifest.files.PSObject.Properties) {
    if (-not $entry.Name.StartsWith("sd/")) {
        continue
    }
    $relative = $entry.Name.Substring(3).Replace("/", "\")
    $target = Join-Path $targetRoot $relative
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
        throw "Copied file is missing: $target"
    }
    $actual = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne [string]$entry.Value.sha256) {
        throw "Copied file hash mismatch: $target"
    }
}

$plan.status = "installed"
$plan | ConvertTo-Json -Depth 5
Write-Host ""
Write-Host "SD files are installed. The installer did not format the card or flash firmware."
Write-Host "Before enabling auto-start, run SMOKE from MaixPy IDE."

if ($InstallFlashLauncher) {
    if (-not $ComPort) {
        $ComPort = Read-Host "Enter the MaixPy REPL COM port for /flash/main.py upload (or leave blank to skip)"
    }
    if ($ComPort) {
        & (Join-Path $packageRoot "tools\k210_serial_write_file.ps1") `
            -LocalPath (Join-Path $packageRoot "flash\main.py") `
            -RemotePath "/flash/main.py" `
            -ComPort $ComPort
    }
    else {
        Write-Host "Flash launcher upload skipped."
    }
}
