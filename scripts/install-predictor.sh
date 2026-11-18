#!/usr/bin/env bash
# Installs "Google's prediction" (TimesFM 2.5, 200M, Apache-2.0) into its own folder, separate from the app's Python:
#   ~/Library/Application Support/MarketSkew/predictor/{env,weights/timesfm}
# About 1.4 GB in total (PyTorch + the model weights). Free; runs on your Mac. Safe to run again: it skips what is there.
set -euo pipefail

HOME_DIR="${MARKET_SKEW_PREDICTOR_HOME:-$HOME/Library/Application Support/MarketSkew/predictor}"
ENV_DIR="$HOME_DIR/env"
WEIGHTS="$HOME_DIR/weights/timesfm"
REPO="google/timesfm-2.5-200m-pytorch"

command -v uv >/dev/null 2>&1 || { echo "uv is not installed. Install it from https://docs.astral.sh/uv/ and run this again."; exit 1; }

echo "Installing into: $HOME_DIR"
mkdir -p "$HOME_DIR"

if [[ ! -x "$ENV_DIR/bin/python" ]]; then
  echo "1/3 Creating the predictor's Python environment..."
  uv venv --python 3.12 "$ENV_DIR"
else
  echo "1/3 Python environment already there."
fi

echo "2/3 Installing the model libraries (PyTorch is large, this takes a few minutes)..."
uv pip install --python "$ENV_DIR/bin/python" \
  "timesfm[torch]==3.0.2" "torch==2.11.0" "numpy==2.5.4" "einops==0.8.2" "safetensors==0.8.0" "huggingface_hub==2.4.0"

if [[ -f "$WEIGHTS/model.safetensors" && -f "$WEIGHTS/config.json" ]]; then
  echo "3/3 Model weights already there."
else
  echo "3/3 Downloading the model weights from Hugging Face ($REPO, about 0.9 GB)..."
  mkdir -p "$WEIGHTS"
  "$ENV_DIR/bin/python" -I - "$REPO" "$WEIGHTS" <<'PY'
import sys
from huggingface_hub import snapshot_download
snapshot_download(repo_id=sys.argv[1], local_dir=sys.argv[2], allow_patterns=["config.json", "model.safetensors"])
PY
fi

[[ -f "$WEIGHTS/model.safetensors" ]] || { echo "The weights did not download. Run this script again."; exit 1; }
echo "Done. Google's prediction will show up on the Picks page after the next scan."
echo "To remove it later, delete: $HOME_DIR"
