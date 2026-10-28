param(
    [Parameter(Mandatory = $true)]
    [string]$Tflite,

    [Parameter(Mandatory = $true)]
    [string]$CalibrationDir,

    [Parameter(Mandatory = $true)]
    [string]$Output,

    [string]$NccPath = "ncc",

    # NNCase RC5 deliberately rejects narrower weight widths.
    [ValidateSet("8", "16")]
    [string]$WeightsBits = "8"
)

$ErrorActionPreference = "Stop"
$ncc = Get-Command $NccPath -ErrorAction Stop
$outputPath = [IO.Path]::GetFullPath($Output)
$outputDir = Split-Path -Parent $outputPath
if (-not (Test-Path -LiteralPath $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir | Out-Null
}

& $ncc.Source `
    -i tflite `
    -o k210model `
    --dataset $CalibrationDir `
    --dataset-format image `
    --inference-type uint8 `
    --weights-bits $WeightsBits `
    $Tflite `
    $outputPath

if ($LASTEXITCODE -ne 0) {
    throw "ncc failed with exit code $LASTEXITCODE"
}

Get-Item -LiteralPath $outputPath |
    Select-Object FullName, Length, LastWriteTime
