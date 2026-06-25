#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

APP_NAME="Phil"
DMG_NAME="Phil-macOS.dmg"
STAGING_DIR="dist/dmg"

rm -rf build "dist/${APP_NAME}" "dist/${APP_NAME}.app" "$STAGING_DIR" "dist/${DMG_NAME}"

venv/bin/python -m pip install -r setup/requirements.txt
venv/bin/python -m PyInstaller --clean --noconfirm Phil.spec

xattr -cr "dist/${APP_NAME}.app" || true
xattr -dr com.apple.provenance "dist/${APP_NAME}.app" 2>/dev/null || true
if ! codesign --force --deep -s - "dist/${APP_NAME}.app"; then
  echo "Warning: ad-hoc codesign failed. The DMG will still be created, but notarization will require a clean signed app."
fi

mkdir -p "$STAGING_DIR"
cp -R "dist/${APP_NAME}.app" "$STAGING_DIR/"
ln -s /Applications "$STAGING_DIR/Applications"

hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$STAGING_DIR" \
  -ov \
  -format UDZO \
  "dist/${DMG_NAME}"

echo "Created dist/${DMG_NAME}"
