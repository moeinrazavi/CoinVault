"""Write MAME ini files for an OpenEmu-like launch experience."""

from __future__ import annotations

from pathlib import Path

from emulator.paths import APP_NAME, cfg_root, ini_root


def ensure_mame_ini() -> Path:
    ini_dir = ini_root()
    ui_ini = ini_dir / "ui.ini"
    mame_ini = ini_dir / "mame.ini"

    ui_ini.write_text(
        "\n".join(
            [
                f"# {APP_NAME} UI settings",
                "skip_warnings             1",
                "confirm_quit              0",
                "",
            ]
        ),
        encoding="utf-8",
    )

    mame_ini.write_text(
        "\n".join(
            [
                f"# {APP_NAME} core settings",
                "skip_gameinfo             1",
                "confirm_quit              0",
                "",
            ]
        ),
        encoding="utf-8",
    )

    cfg_root()
    return ini_dir


def mame_launch_args() -> list[str]:
    ini_dir = ensure_mame_ini()
    return [
        "-inipath",
        str(ini_dir),
        "-cfg_directory",
        str(cfg_root()),
    ]
