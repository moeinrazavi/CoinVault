"""Capture game icons using MAME snapshots."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from emulator.mame import find_mame_paths
from emulator.mame_config import mame_launch_args


def capture_icon(game_id: str, rompath: Path, icon_path: Path) -> bool:
    icon_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp_dir:
        snap_dir = Path(temp_dir)
        script_path = snap_dir / "capture.lua"
        script_path.write_text(
            "\n".join(
                [
                    "emu.wait(6)",
                    'manager.machine:popmessage("Capturing icon...")',
                    "emu.wait(1)",
                    'manager.machine.video:snapshot("icon")',
                    "emu.wait(0.5)",
                    "manager.machine:exit()",
                ]
            ),
            encoding="utf-8",
        )

        paths = find_mame_paths()
        command = [
            str(paths.binary),
            game_id,
            "-rompath",
            str(rompath),
            "-skip_gameinfo",
            "-homepath",
            str(paths.homepath),
            "-pluginspath",
            paths.pluginspath,
            "-snapshot_directory",
            str(snap_dir),
            "-snapname",
            "icon",
            *mame_launch_args(),
            "-autoboot_script",
            str(script_path),
            "-seconds_to_run",
            "20",
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        generated = snap_dir / "icon.png"
        if not generated.exists():
            return False

        icon_path.write_bytes(generated.read_bytes())
        return result.returncode in (0, 1, 2) or generated.exists()
