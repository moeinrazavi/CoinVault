# CoinVault

A macOS MAME arcade launcher with drag-and-drop game import and 8 rotating save slots per game.

## Quick Start (development)

```bash
chmod +x play build_dmg.sh
./play
```

## Build the app + DMG

```bash
./build_dmg.sh
```

Outputs:

- `dist/CoinVault.app` — double-clickable macOS app
- `CoinVault-1.0.0.dmg` — standard macOS installer disk image

## Install from DMG

1. Open `CoinVault-1.0.0.dmg`
2. Drag **CoinVault.app** into **Applications**
3. Launch from Applications — RoboCop 2 is included and loads on first run

## Add games

Drag a ROM folder onto the app window. CoinVault will:

1. Identify the MAME game automatically
2. Copy ROMs into your library
3. Capture a screenshot icon
4. Create a dedicated save folder for that game

## In-game controls

Open **Controller Setup** in the app to view or change keyboard mappings. Defaults:

| Action | Player 1 | Player 2 |
|--------|----------|----------|
| Move | Arrow keys | W A S D |
| Buttons | Z X C | F G H |
| Start | 1 | 2 |
| Coin | 5 | 6 |

| Save / Load | Shortcut |
|-------------|----------|
| Save | **Cmd+S** |
| Load newest save | **Cmd+L** |

Mappings are saved to `controller.json` and exported as a MAME controller profile on launch.

## Save slots

- 8 slots per game
- **Cmd+S** fills empty slots first, then overwrites the oldest save
- **Cmd+L** loads the newest save

## Where data is stored

When installed from Applications, games and saves live at:

```
~/Library/Application Support/CoinVault/
  controller.json       # editable keyboard mappings
  ctrlr/coinvault.cfg   # MAME controller profile (auto-generated)
  cfg/                  # per-game MAME settings
  library.json
  games/
  saves/
```

Existing data from the previous **ArcadeSave** install is picked up automatically if present.

## Requirements

- macOS 12+
- MAME is bundled inside the built app
