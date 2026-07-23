#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

APP_NAME="CoinVault"
VERSION="1.0.0"
BUILD_DIR="$ROOT/build"
DIST_DIR="$ROOT/dist"
STAGE_DIR="$ROOT/dmg-staging"
DMG_PATH="$ROOT/${APP_NAME}-${VERSION}.dmg"

echo "==> Checking dependencies"
if ! command -v mame >/dev/null 2>&1; then
  echo "Installing MAME..."
  brew install mame
fi

VENV="$ROOT/.venv"
if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

python -m pip install -U pip wheel
python -m pip install -r requirements.txt

echo "==> Building app bundle"
rm -rf "$BUILD_DIR" "$DIST_DIR"
pyinstaller --noconfirm CoinVault.spec

APP_BUNDLE="$DIST_DIR/${APP_NAME}.app"
if [[ ! -d "$APP_BUNDLE" ]]; then
  echo "Build failed: ${APP_NAME}.app not found"
  exit 1
fi

echo "==> Bundling MAME runtime"
MAME_PREFIX="$(brew --prefix mame)"
MAME_RESOURCES="$APP_BUNDLE/Contents/Resources/mame"
mkdir -p "$MAME_RESOURCES/bin" "$MAME_RESOURCES/share/mame"
cp "$MAME_PREFIX/bin/mame" "$MAME_RESOURCES/bin/"
chmod +x "$MAME_RESOURCES/bin/mame"
for subdir in hash plugins ini; do
  if [[ -d "$MAME_PREFIX/share/mame/$subdir" ]]; then
    cp -R "$MAME_PREFIX/share/mame/$subdir" "$MAME_RESOURCES/share/mame/"
  fi
done

echo "==> Seeding bundled game library inside the app"
SEED_DIR="$APP_BUNDLE/Contents/Resources/seed/library"
mkdir -p "$SEED_DIR/games" "$SEED_DIR/saves"

if [[ -d "$ROOT/roms" ]] || ls "$ROOT"/*.f1 >/dev/null 2>&1; then
  COINVAULT_LIBRARY="$SEED_DIR" python - <<'PY'
import shutil
import tempfile
from pathlib import Path

from emulator.game_id import collect_rom_files
from emulator.game_library import GameLibrary

root = Path(".")
library = GameLibrary()
if library.list_games():
    print("Seed library already populated")
else:
    rom_files = collect_rom_files(root)
    if not rom_files:
        print("No ROM files found to seed")
    else:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            for rom in rom_files:
                shutil.copy2(rom, temp_path / rom.name)
            entry, _warning = library.add_game_from_folder(temp_path)
            print(f"Seeded {entry.title}")
PY
fi

echo "==> Preparing DMG layout"
rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR"
cp -R "$APP_BUNDLE" "$STAGE_DIR/"
ln -s /Applications "$STAGE_DIR/Applications"

echo "==> Creating DMG"
rm -f "$DMG_PATH"
hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$STAGE_DIR" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

echo "Built:"
echo "  App: $APP_BUNDLE"
echo "  DMG: $DMG_PATH"
