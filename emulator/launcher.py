#!/usr/bin/env python3
"""Launch a MAME game with rotating save slots."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from emulator.controller import controller_launch_args, ensure_controller_ready
from emulator.game_library import GameEntry, GameLibrary
from emulator.mame import find_mame_paths
from emulator.mame_config import mame_launch_args
from emulator.paths import APP_NAME, saves_root
from emulator.save_slots import SaveSlotManager


def notify(message: str) -> None:
    print(f"[{APP_NAME}] {message}", flush=True)
    subprocess.run(
        [
            "osascript",
            "-e",
            f'display notification "{message}" with title "{APP_NAME}"',
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def run_game_entry(entry: GameEntry) -> int:
    paths = find_mame_paths()
    slot_manager = SaveSlotManager(entry.id, saves_root())
    notify(slot_manager.status_summary())

    os.environ["MAME_SLOT_DIR"] = str(slot_manager.game_dir)
    os.environ["MAME_SLOT_CMD"] = str(slot_manager.command_path)
    os.environ["MAME_SLOT_ACK"] = str(slot_manager.ack_path)

    ensure_controller_ready()

    mame_cmd = [
        str(paths.binary),
        entry.id,
        "-rompath",
        str(entry.rompath),
        "-window",
        "-skip_gameinfo",
        "-homepath",
        str(paths.homepath),
        "-state_directory",
        str(slot_manager.states_dir),
        "-statename",
        ".",
        "-plugin",
        "slot_saves",
        "-pluginspath",
        paths.pluginspath,
        *mame_launch_args(),
        *controller_launch_args(),
    ]

    notify(f"Starting {entry.title}...")
    notify("Save/load hotkeys: Cmd+S save, Cmd+L load newest")
    process = subprocess.Popen(mame_cmd)
    return process.wait()


def run_game_by_id(game_id: str) -> int:
    library = GameLibrary()
    entry = library.get_game(game_id)
    if entry is None:
        notify(f"Game not found in library: {game_id}")
        return 1
    return run_game_entry(entry)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        notify("No game specified")
        return 1
    try:
        return run_game_by_id(argv[0])
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        notify(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
