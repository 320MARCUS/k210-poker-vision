[CmdletBinding()]
param(
    [ValidateSet("menu", "status", "resolve", "bootstrap", "test", "ports", "capture", "run", "ide", "sd-pack", "release", "leak")]
    [string]$Action = "menu",
    [string]$ComPort,
    [ValidateSet("SMOKE", "BENCHMARK", "STABILITY", "HOLDOUT", "DEMO")]
    [string]$Mode = "SMOKE",
    [switch]$ForceBootstrap,
    [switch]$AssumeNoUv
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$centralEnvironmentRoot = $null
foreach ($anchor in @(
    $env:UV_PYTHON_INSTALL_DIR,
    $env:PNPM_HOME,
    $env:GRADLE_USER_HOME,
    $env:JAVA_HOME
)) {
    if ($anchor -match "^(.+?)[\\/](runtimes|tools|cache|envs)[\\/]") {
        $centralEnvironmentRoot = $Matches[1]
        break
    }
}
$centralPython = if ($env:POKER_VISION_CENTRAL_PYTHON) {
    $env:POKER_VISION_CENTRAL_PYTHON
}
elseif ($centralEnvironmentRoot) {
    Join-Path $centralEnvironmentRoot "envs\yolo\Scripts\python.exe"
}
else {
    $null
}
$centralToolsRoot = if ($env:POKER_VISION_TOOLS_ROOT) {
    $env:POKER_VISION_TOOLS_ROOT
}
elseif ($centralEnvironmentRoot) {
    Join-Path $centralEnvironmentRoot "tools"
}
else {
    $null
}
$uvVersion = "0.12.24"
$uvExeSha256 = "1e9d1e0a766024a212d165dc67db2d7f71831a5ff4bb60ab7e6863391871c1d5"
$script:ProjectPython = $null

function Write-Section {
    param([string]$Text)
    Write-Host ""
    Write-Host "== $Text =="
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

function Get-UvExecutable {
    $localUv = Join-Path $projectRoot ".tools\uv-$uvVersion\uv.exe"
    if (Test-Path -LiteralPath $localUv -PathType Leaf) {
        return $localUv
    }
    $command = Get-Command uv.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    Write-Host "uv not found; downloading the pinned Windows build into .tools."
    $downloadDir = Join-Path $projectRoot ".tools\downloads"
    $installDir = Join-Path $projectRoot ".tools\uv-$uvVersion"
    New-Item -ItemType Directory -Force -Path $downloadDir | Out-Null
    New-Item -ItemType Directory -Force -Path $installDir | Out-Null
    $archive = Join-Path $downloadDir "uv-x86_64-pc-windows-msvc-$uvVersion.zip"
    $url = "https://github.com/astral-sh/uv/releases/download/$uvVersion/uv-x86_64-pc-windows-msvc.zip"
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $archive
    Expand-Archive -LiteralPath $archive -DestinationPath $installDir -Force
    if (-not (Test-Path -LiteralPath $localUv -PathType Leaf)) {
        throw "The uv archive did not contain uv.exe."
    }
    $actualHash = (Get-FileHash -LiteralPath $localUv -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $uvExeSha256) {
        throw "uv.exe SHA-256 mismatch. Expected $uvExeSha256, got $actualHash"
    }
    return $localUv
}

function Get-UvCandidate {
    if ($AssumeNoUv) {
        return $null
    }
    $localUv = Join-Path $projectRoot ".tools\uv-$uvVersion\uv.exe"
    if (Test-Path -LiteralPath $localUv -PathType Leaf) {
        return $localUv
    }
    $command = Get-Command uv.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    return $null
}

function Show-ResolutionPlan {
    if ($centralPython -and (Test-Path -LiteralPath $centralPython -PathType Leaf)) {
        Write-Host "Selected: central environment"
        Write-Host "Python: $centralPython"
        return
    }
    $localPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $localPython -PathType Leaf) {
        Write-Host "Selected: existing project environment"
        Write-Host "Python: $localPython"
        return
    }
    $uv = Get-UvCandidate
    if ($uv) {
        Write-Host "Selected: uv bootstrap"
        Write-Host "uv: $uv"
    }
    else {
        Write-Host "Selected: pinned uv download, then uv bootstrap"
        Write-Host "uv download: 0.12.24"
    }
}

function Resolve-ProjectEnvironment {
    if ($script:ProjectPython -and -not $ForceBootstrap) {
        return $script:ProjectPython
    }
    if (-not $ForceBootstrap -and $centralPython -and (Test-Path -LiteralPath $centralPython -PathType Leaf)) {
        $script:ProjectPython = $centralPython
        $env:PYTHONPATH = Join-Path $projectRoot "src"
        Write-Host "Python: shared environment ($centralPython)"
        return $script:ProjectPython
    }

    $localPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if (-not $ForceBootstrap -and (Test-Path -LiteralPath $localPython -PathType Leaf)) {
        $script:ProjectPython = $localPython
        $env:PYTHONPATH = Join-Path $projectRoot "src"
        Write-Host "Python: project environment ($localPython)"
        return $script:ProjectPython
    }

    Write-Host "No usable project Python found; bootstrapping with uv."
    $uv = Get-UvExecutable
    Push-Location $projectRoot
    try {
        Invoke-Checked -Label "uv sync" -Command { & $uv sync --frozen --extra dev }
    }
    finally {
        Pop-Location
    }
    if (-not (Test-Path -LiteralPath $localPython -PathType Leaf)) {
        throw "uv sync completed but .venv\Scripts\python.exe is missing."
    }
    $script:ProjectPython = $localPython
    $env:PYTHONPATH = Join-Path $projectRoot "src"
    Write-Host "Python: project environment ($localPython)"
    return $script:ProjectPython
}

function Show-Status {
    $python = Resolve-ProjectEnvironment
    $uv = Get-Command uv.exe -ErrorAction SilentlyContinue
    Write-Section "Environment"
    Write-Host "Project: $projectRoot"
    Write-Host "Python:  $python"
    & $python -c "import sys, torch; print('Python runtime:', sys.version.split()[0]); print('PyTorch:', torch.__version__); print('CUDA available:', torch.cuda.is_available())"
    if ($uv) {
        Write-Host "uv:      $($uv.Source)"
    }
    else {
        Write-Host "uv:      not on PATH; fallback copy will be downloaded only when needed"
    }
    Write-Host "MaixPy IDE candidates:"
    Get-MaixPyIdeCandidates | ForEach-Object { Write-Host "  $_" }
}

function Invoke-Tests {
    $python = Resolve-ProjectEnvironment
    $stamp = [DateTimeOffset]::UtcNow.ToString("yyyyMMdd-HHmmss")
    $tempRoot = Join-Path $projectRoot ".tmp\temp"
    $baseTemp = Join-Path $projectRoot ".tmp\pytest-$stamp"
    New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $baseTemp | Out-Null
    $oldTemp = $env:TEMP
    $oldTmp = $env:TMP
    $env:TEMP = $tempRoot
    $env:TMP = $tempRoot
    try {
        Write-Section "Pytest"
        Invoke-Checked -Label "pytest" -Command {
            & $python -m pytest -q -p no:cacheprovider --basetemp $baseTemp
        }
        Write-Section "Ruff"
        $ruff = Get-Command ruff.exe -ErrorAction SilentlyContinue
        $ruffPath = if ($ruff) { $ruff.Source } else { $null }
        if (-not $ruff -and $centralToolsRoot) {
            $centralExtensions = Join-Path $centralToolsRoot "vscode-extensions"
            $centralRuff = Get-ChildItem -Path (
                Join-Path $centralExtensions "charliermarsh.ruff-*"
            ) -Directory -ErrorAction SilentlyContinue |
                Sort-Object Name -Descending |
                ForEach-Object {
                    Join-Path $_.FullName "bundled\libs\bin\ruff.exe"
                } |
                Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
                Select-Object -First 1
            if ($centralRuff) {
                $ruffPath = $centralRuff
            }
        }
        if ($ruffPath) {
            Invoke-Checked -Label "ruff" -Command { & $ruffPath check . }
        }
        else {
            $uv = Get-UvExecutable
            Invoke-Checked -Label "ruff via uv" -Command {
                & $uv tool run --from "ruff==0.17.1" ruff check .
            }
        }
    }
    finally {
        $env:TEMP = $oldTemp
        $env:TMP = $oldTmp
    }
}

function Get-MaixPyIdeCandidates {
    $candidates = @()
    if ($env:MAIXPY_IDE) {
        $candidates += $env:MAIXPY_IDE
    }
    $command = Get-Command maixpyide.exe -ErrorAction SilentlyContinue
    if ($command) {
        $candidates += $command.Source
    }
    return $candidates |
        Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
        Select-Object -Unique
}

function Show-Ports {
    & (Join-Path $PSScriptRoot "k210_serial_capture.ps1") -ListPorts
}

function Get-RequestedPort {
    param([string]$Requested)
    if ($Requested) {
        return $Requested
    }
    $ports = @([IO.Ports.SerialPort]::GetPortNames() | Sort-Object -Unique)
    if ($ports.Count -eq 0) {
        throw "No COM ports are visible. Reconnect the board with a known-good USB data cable."
    }
    Write-Host "Visible ports: $($ports -join ', ')"
    return (Read-Host "Enter the MaixPy REPL port")
}

function Invoke-Capture {
    $port = Get-RequestedPort $ComPort
    $log = Join-Path $projectRoot ".tmp\serial\capture-$([DateTimeOffset]::UtcNow.ToString('yyyyMMdd-HHmmss')).log"
    & (Join-Path $PSScriptRoot "k210_serial_capture.ps1") -ComPort $port -OutputPath $log
}

function Invoke-RunMode {
    $port = Get-RequestedPort $ComPort
    & (Join-Path $PSScriptRoot "k210_run_mode.ps1") -ComPort $port -Mode $Mode
}

function Open-MaixPyIde {
    $candidates = @(Get-MaixPyIdeCandidates)
    if ($candidates.Count -eq 0) {
        Write-Host "MaixPy IDE was not found."
        Write-Host "Install MaixPy IDE 0.2.5 or set MAIXPY_IDE to its executable."
        return
    }
    Start-Process -FilePath $candidates[0]
}

function Invoke-SdPack {
    & (Join-Path $PSScriptRoot "build_k210_sd.ps1")
}

function Invoke-Release {
    & (Join-Path $PSScriptRoot "build_release.ps1")
}

function Invoke-LeakScan {
    & (Join-Path $PSScriptRoot "leak_scan.ps1") -Path $projectRoot
}

switch ($Action) {
    "status" { Show-Status; exit 0 }
    "resolve" { Show-ResolutionPlan; exit 0 }
    "bootstrap" { [void](Resolve-ProjectEnvironment); Write-Host "Environment ready."; exit 0 }
    "test" { Invoke-Tests; exit 0 }
    "ports" { Show-Ports; exit 0 }
    "capture" { Invoke-Capture; exit $LASTEXITCODE }
    "run" { Invoke-RunMode; exit $LASTEXITCODE }
    "ide" { Open-MaixPyIde; exit 0 }
    "sd-pack" { Invoke-SdPack; exit $LASTEXITCODE }
    "release" { Invoke-Release; exit $LASTEXITCODE }
    "leak" { Invoke-LeakScan; exit $LASTEXITCODE }
}

while ($true) {
    Write-Host ""
    Write-Host "K210 Poker Vision - Windows development terminal"
    Write-Host "1. Environment status"
    Write-Host "2. Bootstrap or repair environment"
    Write-Host "3. Run tests and Ruff"
    Write-Host "4. List serial ports"
    Write-Host "5. Capture PVJSON logs"
    Write-Host "6. Run device mode"
    Write-Host "7. Open MaixPy IDE"
    Write-Host "8. Build the SD package"
    Write-Host "9. Build the complete release bundle"
    Write-Host "10. Run leak scan"
    Write-Host "0. Exit"
    $choice = Read-Host "Select"
    try {
        switch ($choice) {
            "1" { Show-Status }
            "2" { $ForceBootstrap = $true; [void](Resolve-ProjectEnvironment) }
            "3" { Invoke-Tests }
            "4" { Show-Ports }
            "5" { Invoke-Capture }
            "6" {
                $selected = Read-Host "Mode: SMOKE/BENCHMARK/STABILITY/HOLDOUT/DEMO"
                $Mode = $selected.ToUpperInvariant()
                Invoke-RunMode
            }
            "7" { Open-MaixPyIde }
            "8" { Invoke-SdPack }
            "9" { Invoke-Release }
            "10" { Invoke-LeakScan }
            "0" { break }
            default { Write-Host "Unknown selection." }
        }
    }
    catch {
        Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    }
    if ($choice -eq "0") {
        break
    }
}
