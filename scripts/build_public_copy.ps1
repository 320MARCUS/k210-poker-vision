[CmdletBinding()]
param(
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$githubRoot = Join-Path $projectRoot "dist\github"
if (-not $OutputPath) {
    $OutputPath = Join-Path $githubRoot "k210-poker-vision"
}
$OutputPath = [IO.Path]::GetFullPath($OutputPath)
$expectedPrefix = [IO.Path]::GetFullPath($githubRoot).TrimEnd("\") + "\"
if (-not $OutputPath.StartsWith($expectedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Public copy must stay under $githubRoot"
}

if (Test-Path -LiteralPath $OutputPath) {
    Remove-Item -LiteralPath $OutputPath -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null

$rootFiles = @(
    ".gitignore",
    "LICENSE",
    "NOTICE.md",
    "README.md",
    "UPLOAD.md",
    "pyproject.toml",
    "start-dev.bat",
    "uv.lock"
)
$directories = @(
    ".github",
    "configs",
    "docs",
    "k210",
    "media",
    "packaging",
    "results",
    "scripts",
    "src",
    "tests"
)

foreach ($name in $rootFiles) {
    $source = Join-Path $projectRoot $name
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required public file is missing: $name"
    }
    Copy-Item -LiteralPath $source -Destination (Join-Path $OutputPath $name) -Force
}
foreach ($name in $directories) {
    $source = Join-Path $projectRoot $name
    if (-not (Test-Path -LiteralPath $source -PathType Container)) {
        throw "Required public directory is missing: $name"
    }
    Copy-Item -LiteralPath $source -Destination (Join-Path $OutputPath $name) -Recurse -Force
}

$privateDiagnostics = @(
    "k210\model_probe.py",
    "scripts\k210_fix_sd_layout.ps1",
    "scripts\k210_model_probe_serial.ps1",
    "scripts\k210_raw_exec.ps1",
    "scripts\k210_repl_diag.ps1",
    "scripts\k210_slow_model_probe.ps1",
    "scripts\k210_slow_ping.ps1"
)
foreach ($relative in $privateDiagnostics) {
    $candidate = Join-Path $OutputPath $relative
    if (Test-Path -LiteralPath $candidate) {
        Remove-Item -LiteralPath $candidate -Force
    }
}

$cacheDirectories = @(Get-ChildItem -LiteralPath $OutputPath -Recurse -Directory -Force | Where-Object {
    $_.Name -in @("__pycache__", ".pytest_cache", ".ruff_cache", ".tmp", ".tools")
})
foreach ($directory in $cacheDirectories) {
    if (Test-Path -LiteralPath $directory.FullName) {
        Remove-Item -LiteralPath $directory.FullName -Recurse -Force
    }
}
Get-ChildItem -LiteralPath $OutputPath -Recurse -File -Force | Where-Object {
    $_.Extension -in @(".pyc", ".pyo")
} | ForEach-Object {
    Remove-Item -LiteralPath $_.FullName -Force
}

$forbidden = @(Get-ChildItem -LiteralPath $OutputPath -Recurse -File -Force | Where-Object {
    $_.Extension -in @(".pth", ".pt", ".weights", ".kmodel", ".onnx", ".tflite", ".bin")
})
if ($forbidden.Count -gt 0) {
    throw "Public copy contains forbidden model files: $($forbidden.FullName -join ', ')"
}

$files = @(Get-ChildItem -LiteralPath $OutputPath -Recurse -File -Force)
$bytes = ($files | Measure-Object Length -Sum).Sum
[pscustomobject]@{
    status = "ok"
    path = $OutputPath
    files = $files.Count
    bytes = $bytes
} | ConvertTo-Json -Depth 3
