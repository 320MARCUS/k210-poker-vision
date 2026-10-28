[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$rootPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)
$root = [IO.Path]::GetFullPath($rootPath)
if (-not (Test-Path -LiteralPath $root -PathType Container)) {
    throw "Scan path is not a directory: $root"
}

$skipSegments = @(
    "\.git\",
    "\.venv\",
    "\.tools\",
    "\.tmp\",
    "\__pycache__\",
    "\.pytest_cache\",
    "\.ruff_cache\",
    "\artifacts\",
    "\data\",
    "\dist\",
    "\vendor\"
)
$textExtensions = @(
    ".bat", ".cfg", ".csv", ".gitignore", ".json", ".jsonl", ".md",
    ".ps1", ".py", ".toml", ".txt", ".yaml", ".yml"
)
$forbiddenExtensions = @(".pth", ".pt", ".weights", ".zip", ".kmodel", ".onnx", ".tflite", ".bin")
$patterns = [ordered]@{
    local_user_path = "C:\\Users\\"
    local_project_path = "D:\\project\\"
    raw_download_path = "E:\\download"
    private_key = "BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY"
    github_token = "gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    bearer_token = "Bearer\s+[A-Za-z0-9._-]{20,}"
}

$findings = [System.Collections.Generic.List[object]]::new()
$files = @(Get-ChildItem -LiteralPath $root -Recurse -File -Force)
foreach ($file in $files) {
    $relative = $file.FullName.Substring($root.Length).TrimStart("\")
    $skipped = $false
    foreach ($segment in $skipSegments) {
        if ($file.FullName.Contains($segment)) {
            $skipped = $true
            break
        }
    }
    if ($skipped) {
        continue
    }
    if ($file.Extension.ToLowerInvariant() -in $forbiddenExtensions) {
        $findings.Add([ordered]@{
            severity = "error"
            rule = "forbidden-binary"
            file = $relative
            detail = $file.Extension
        })
        continue
    }
    if ($file.Extension.ToLowerInvariant() -notin $textExtensions -and $file.Name -ne ".gitignore") {
        continue
    }
    $lineNumber = 0
    foreach ($line in Get-Content -LiteralPath $file.FullName -Encoding UTF8) {
        $lineNumber++
        foreach ($rule in $patterns.GetEnumerator()) {
            if ($line -match $rule.Value) {
                $findings.Add([ordered]@{
                    severity = "error"
                    rule = $rule.Key
                    file = $relative
                    line = $lineNumber
                })
            }
        }
    }
}

$result = [ordered]@{
    status = $(if ($findings.Count -eq 0) { "passed" } else { "failed" })
    scanned_path = $root
    scanned_files = $files.Count
    findings = @($findings)
}
$json = $result | ConvertTo-Json -Depth 8
if ($OutputPath) {
    $parent = Split-Path -Parent $OutputPath
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($OutputPath, $json, $utf8NoBom)
}
Write-Output $json
if ($findings.Count -gt 0) {
    exit 1
}
