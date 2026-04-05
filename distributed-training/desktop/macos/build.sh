#!/usr/bin/env bash
# Build the macOS menu bar app and package it into a .dmg
# Run from the desktop/macos/ directory

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../" && pwd)"
DIST_DIR="$SCRIPT_DIR/dist"

echo "==> Installing build dependencies…"
pip install --quiet py2app dmgbuild rumps requests

echo "==> Building .app bundle…"
cd "$SCRIPT_DIR"
PYTHONPATH="$ROOT_DIR" python setup.py py2app 2>&1

echo "==> Signing .app (requires Apple Developer certificate)…"
APP_PATH="$DIST_DIR/Distributed Training.app"
if [ -n "${APPLE_SIGNING_IDENTITY:-}" ]; then
    codesign --deep --force --verify --verbose \
        --sign "$APPLE_SIGNING_IDENTITY" \
        --options runtime \
        --entitlements entitlements.plist \
        "$APP_PATH"
    echo "    Signed with: $APPLE_SIGNING_IDENTITY"
else
    echo "    APPLE_SIGNING_IDENTITY not set — skipping code signing"
    echo "    (app will show Gatekeeper warning on first launch)"
fi

echo "==> Building .dmg…"
DMG_PATH="$DIST_DIR/DTrain-$(python -c 'import src; print(src.__version__)').dmg"
dmgbuild \
    -s dmgbuild_settings.py \
    -D app="$APP_PATH" \
    "Distributed Training" \
    "$DMG_PATH"

echo ""
echo "✓ Done! Installer: $DMG_PATH"
echo ""
echo "To notarize for distribution outside the App Store:"
echo "  xcrun notarytool submit $DMG_PATH --apple-id <email> --team-id <team>"
