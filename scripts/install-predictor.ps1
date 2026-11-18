# Installs "Google's prediction" (TimesFM 2.5, 200M, Apache-2.0) on Windows into its own folder, separate from the app's Python:
#   %LOCALAPPDATA%\MarketSkew\predictor\{env,weights\timesfm}
# About 1.4 GB in total (PyTorch + the model weights). Free; runs on your PC. Safe to run again: it skips what is there.
$ErrorActionPreference = "Stop"
$HomeDir = if ($env:MARKET_SKEW_PREDICTOR_HOME) { $env:MARKET_SKEW_PREDICTOR_HOME } else { Join-Path $env:LOCALAPPDATA "MarketSkew\predictor" }
$EnvDir = Join-Path $HomeDir "env"
$EnvPython = Join-Path $EnvDir "Scripts\python.exe"
$Weights = Join-Path $HomeDir "weights\timesfm"
$Repo = "google/timesfm-2.5-200m-pytorch"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Write-Host "uv is not installed. Install it with: winget install --id=astral-sh.uv -e  and run this again."; exit 1 }

Write-Host "Installing into: $HomeDir"
New-Item -ItemType Directory -Force -Path $HomeDir | Out-Null

if (-not (Test-Path $EnvPython)) {
    Write-Host "1/3 Creating the predictor's Python environment..."
    uv venv --python 3.12 $EnvDir
    if ($LASTEXITCODE -ne 0) { exit 1 }
} else {
    Write-Host "1/3 Python environment already there."
}

Write-Host "2/3 Installing the model libraries (PyTorch is large, this takes a few minutes)..."
uv pip install --python $EnvPython "timesfm[torch]==3.0.2" "torch==2.11.0" "numpy==2.5.4" "einops==0.8.2" "safetensors==0.8.0" "huggingface_hub==2.4.0"
if ($LASTEXITCODE -ne 0) { exit 1 }

if ((Test-Path (Join-Path $Weights "model.safetensors")) -and (Test-Path (Join-Path $Weights "config.json"))) {
    Write-Host "3/3 Model weights already there."
} else {
    Write-Host "3/3 Downloading the model weights from Hugging Face ($Repo, about 0.9 GB)..."
    New-Item -ItemType Directory -Force -Path $Weights | Out-Null
    $download = @'
import sys
from huggingface_hub import snapshot_download
snapshot_download(repo_id=sys.argv[1], local_dir=sys.argv[2], allow_patterns=["config.json", "model.safetensors"])
'@
    $download | & $EnvPython -I - $Repo $Weights
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

if (-not (Test-Path (Join-Path $Weights "model.safetensors"))) { Write-Host "The weights did not download. Run this script again."; exit 1 }
Write-Host "Done. Google's prediction will show up on the Picks page after the next scan."
Write-Host "To remove it later, delete: $HomeDir"
