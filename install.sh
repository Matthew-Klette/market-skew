#!/usr/bin/env bash
# Market Skew installer for macOS. Safe to run again: it only does what is missing and re-builds the app.
#   ./install.sh                     full install, asks a couple of questions
#   --yes            answer the questions with their defaults (no email is asked for)
#   --skip-tests     skip the quick self-test
#   --app-dir DIR    put the app in DIR instead of ~/Applications
#   --no-dock        do not add the app to the Dock
#   --no-predictor   do not offer the Google predictor (about 1.4 GB)
set -euo pipefail

PROJECT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT"
APP_DIR="$HOME/Applications"; YES=0; SKIP_TESTS=0; DOCK=1; PREDICTOR=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes|-y) YES=1; shift ;;
    --skip-tests) SKIP_TESTS=1; shift ;;
    --no-dock) DOCK=0; shift ;;
    --no-predictor) PREDICTOR=0; shift ;;
    --app-dir) [[ $# -ge 2 ]] || { echo "--app-dir needs a folder"; exit 2; }; APP_DIR="$2"; shift 2 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1 (try --help)"; exit 2 ;;
  esac
done

say() { printf '\n==> %s\n' "$*"; }
stop() { printf '\nStopped: %s\n' "$*" >&2; exit 1; }

# ask "question" default(Y|N): returns 0 for yes. With --yes, or without a keyboard, the default is used.
ask() {
  local question="$1" default="$2" reply
  if [[ $YES -eq 1 ]]; then [[ "$default" == "Y" ]]; return; fi
  if [[ ! -t 0 ]]; then return 1; fi
  read -r -p "$question " reply || return 1
  reply="${reply:-$default}"
  [[ "$reply" =~ ^[Yy] ]]
}

say "Checking this Mac"
[[ "$(uname -s)" == "Darwin" ]] || stop "Market Skew only runs on macOS."
ARCH="$(uname -m)"
case "$ARCH" in
  arm64) echo "macOS on Apple Silicon: good." ;;
  x86_64) echo "macOS on an Intel Mac: fine for the app. (The Google predictor may not work on Intel.)" ;;
  *) stop "Unrecognised processor: $ARCH" ;;
esac
if ! command -v swiftc >/dev/null 2>&1 || ! xcode-select -p >/dev/null 2>&1; then
  stop "Apple's Command Line Tools are missing (needed to build the app window). Run:  xcode-select --install
Wait for it to finish, then run ./install.sh again."
fi
echo "Command Line Tools: found."
if ! command -v uv >/dev/null 2>&1; then
  stop "uv (the Python package manager) is not installed. Install it yourself with Homebrew:  brew install uv
or with the official one-liner from https://docs.astral.sh/uv/getting-started/installation/ , then run ./install.sh again.
(This script does not download and run installers for you.)"
fi
echo "uv: found."

say "Setting up Python packages"
if [[ ! -x .venv/bin/python ]]; then
  uv venv --python 3.12 .venv
else
  echo "Python environment already there."
fi
uv pip install --python .venv/bin/python -r requirements-dev.txt

say "Creating your config files (only the ones that are missing)"
.venv/bin/python -B -c "from market_skew import seed; made = seed.seed(); print('Created: ' + ', '.join(made) if made else 'Nothing to create; your files are untouched.')"

if [[ $SKIP_TESTS -eq 0 ]]; then
  say "Running the quick self-test"
  .venv/bin/python -B -m pytest -q tests || stop "The self-test failed. Re-run with --skip-tests to install anyway, and tell whoever sent you this."
fi

say "Building the app"
bash app/bundle.sh --app-dir "$APP_DIR"

APP="$APP_DIR/Market Skew.app"
if [[ $DOCK -eq 1 ]]; then
  say "Adding Market Skew to the Dock"
  if defaults read com.apple.dock persistent-apps 2>/dev/null | grep -q "Market Skew.app"; then
    echo "Already in the Dock."
  else
    URL="file://$(.venv/bin/python -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$APP")/"
    defaults write com.apple.dock persistent-apps -array-add \
      "<dict><key>tile-data</key><dict><key>file-data</key><dict><key>_CFURLString</key><string>$URL</string><key>_CFURLStringType</key><integer>15</integer></dict></dict></dict>"
    killall Dock || true
    echo "Added. (The Dock restarts for a second.)"
  fi
fi

if [[ $PREDICTOR -eq 1 ]]; then
  say "Google's price prediction (optional)"
  echo "It adds a one-month range, with a track record, to the stocks on the Picks page."
  if [[ "$ARCH" == "arm64" ]]; then DEFAULT="Y"; PROMPT="Matt recommends installing the Google predictor (about 1.4 GB, free, runs on your Mac). Install it now? [Y/n]"
  else DEFAULT="N"; PROMPT="Install the Google predictor (about 1.4 GB, free)? It may not run on an Intel Mac. [y/N]"; fi
  if ask "$PROMPT" "$DEFAULT"; then
    bash scripts/install-predictor.sh || echo "The predictor did not finish installing. Everything else works; run scripts/install-predictor.sh to try again."
  else
    echo "Skipped. Add it any time with: scripts/install-predictor.sh"
  fi
fi

if [[ $YES -eq 0 && -t 0 ]]; then
  say "Optional: an email address for SEC downloads"
  echo "The US SEC asks every program that downloads company filings to say who is asking. Your address is stored only in"
  echo "config/prefs.json on this Mac and sent only to sec.gov. Leave it blank to skip; you can add it later in the app (How it works tab)."
  read -r -p "Email (or press Enter to skip): " EMAIL || EMAIL=""
  if [[ -n "$EMAIL" ]]; then
    SKEW_EMAIL="$EMAIL" .venv/bin/python -B - <<'PY'
import json, os
from market_skew import settings
email = os.environ["SKEW_EMAIL"].strip()
if not settings.valid_email(email):
    print("That does not look like an email address, so nothing was saved. Add it later in the app.")
else:
    try:
        saved = json.loads(settings.PREFS.read_text())
    except (OSError, ValueError):
        saved = {}
    saved["sec_contact"] = email
    settings.PREFS.write_text(json.dumps(saved))
    print("Saved.")
PY
  fi
fi

say "Done"
echo "Open it from: $APP"
[[ $DOCK -eq 1 ]] && echo "(or from the Dock)"
echo "The first time, it asks how much you invest each month and scans the market when you open it after the US close."
echo "Not financial advice. See README.md."
