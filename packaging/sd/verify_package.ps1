[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$packageRoot = $PSScriptRoot
$manifestPath = Join-Path $packageRoot "MANIFEST.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "MANIFEST.json is missing."
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$checked = 0
foreach ($entry in $manifest.files.PSObject.Properties) {
    $relative = $entry.Name.Replace("/", "\")
    $path = Join-Path $packageRoot $relative
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Package file is missing: $($entry.Name)"
    }
    $item = Get-Item -LiteralPath $path
    if ($item.Length -ne [long]$entry.Value.bytes) {
        throw "Size mismatch for $($entry.Name): expected $($entry.Value.bytes), got $($item.Length)"
    }
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne [string]$entry.Value.sha256) {
        throw "SHA-256 mismatch for $($entry.Name): $hash"
    }
    $checked++
}

[pscustomobject]@{
    status = "ok"
    files_checked = $checked
    package_version = $manifest.package.version
    model_sha256 = $manifest.model.sha256
    model_status = $manifest.model.status
} | ConvertTo-Json -Depth 4
