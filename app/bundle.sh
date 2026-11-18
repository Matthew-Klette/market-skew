#!/usr/bin/env bash
# Builds "Market Skew.app" with Command Line Tools only, ad-hoc signs it and installs it.
#   app/bundle.sh                    installs to ~/Applications
#   app/bundle.sh --app-dir DIR      installs to DIR instead (created if missing)
set -euo pipefail
APP_DIR="$HOME/Applications"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-dir) [[ $# -ge 2 ]] || { echo "--app-dir needs a folder"; exit 2; }; APP_DIR="$2"; shift 2 ;;
    -h|--help) sed -n '2,5p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1"; exit 2 ;;
  esac
done

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="Market Skew"; EXEC="MarketSkew"; BUNDLE_ID="io.github.matthew-klette.marketskew"
BUILD="$PROJECT/app/build"
APP="$BUILD/$NAME.app"
PYTHON="$PROJECT/.venv/bin/python"
ICON="$PROJECT/app/AppIcon.icns"
RENDER="$HOME/.claude/skills/image-studio/scripts/render.sh"
[[ -x "$PYTHON" ]] || { echo "No Python environment yet. Run ./install.sh from the project folder first."; exit 1; }
command -v swiftc >/dev/null 2>&1 || { echo "swiftc not found. Run: xcode-select --install"; exit 1; }

# The icon is committed. It is only re-rendered when the svg is newer AND the renderer exists (the author's Mac).
if [[ -f "$PROJECT/app/icon.svg" && "$PROJECT/app/icon.svg" -nt "$ICON" && -f "$RENDER" ]]; then
  mkdir -p "$BUILD"
  ICONSET="$BUILD/AppIcon.iconset"
  rm -rf "$ICONSET" && mkdir -p "$ICONSET"
  bash "$RENDER" "$PROJECT/app/icon.svg" "$BUILD/icon-1024.png" 1024x1024 1 >/dev/null
  for px in 16 32 128 256 512; do
    sips -z $px $px "$BUILD/icon-1024.png" --out "$ICONSET/icon_${px}x${px}.png" >/dev/null
    sips -z $((px * 2)) $((px * 2)) "$BUILD/icon-1024.png" --out "$ICONSET/icon_${px}x${px}@2x.png" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o "$ICON"
fi
[[ -f "$ICON" ]] || { echo "Missing app/AppIcon.icns"; exit 1; }

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
/usr/bin/swiftc -O -framework AppKit -framework WebKit "$PROJECT/app/main.swift" -o "$APP/Contents/MacOS/$EXEC"
cp "$ICON" "$APP/Contents/Resources/AppIcon.icns"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>$NAME</string>
  <key>CFBundleDisplayName</key><string>$NAME</string>
  <key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
  <key>CFBundleExecutable</key><string>$EXEC</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1.0</string>
  <key>CFBundleVersion</key><string>0.1.0</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.finance</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
  <key>SkewPython</key><string>$PYTHON</string>
  <key>SkewProject</key><string>$PROJECT</string>
  <key>SkewLauncher</key><string>skew</string>
</dict>
</plist>
PLIST
codesign --force --sign - "$APP" >/dev/null 2>&1
mkdir -p "$APP_DIR"
rm -rf "$APP_DIR/$NAME.app"
cp -R "$APP" "$APP_DIR/$NAME.app"
echo "Installed $APP_DIR/$NAME.app"
