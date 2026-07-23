"""Locate and invoke the MAME binary."""

from __future__ import annotations

import shutil
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from emulator.paths import mame_bundle_root, plugins_root


@dataclass(frozen=True)
class MamePaths:
    binary: Path
    homepath: Path
    pluginspath: str


def find_mame_paths() -> MamePaths:
    bundled_bin = mame_bundle_root() / "bin" / "mame"
    if bundled_bin.exists():
        homepath = mame_bundle_root()
        pluginspath = _plugin_search_path(homepath)
        return MamePaths(bundled_bin, homepath, pluginspath)

    system_bin = shutil.which("mame")
    if system_bin:
        homepath = Path("/opt/homebrew/opt/mame")
        if not homepath.exists():
            homepath = Path.home() / ".mame"
        pluginspath = _plugin_search_path(homepath)
        return MamePaths(Path(system_bin), homepath, pluginspath)

    brew_bin = Path("/opt/homebrew/bin/mame")
    if brew_bin.exists():
        homepath = Path("/opt/homebrew/opt/mame")
        pluginspath = _plugin_search_path(homepath)
        return MamePaths(brew_bin, homepath, pluginspath)

    raise RuntimeError(
        "MAME was not found. Install it with: brew install mame"
    )


def _plugin_search_path(homepath: Path) -> str:
    paths = [str(plugins_root())]
    default_plugins = homepath / "share" / "mame" / "plugins"
    if default_plugins.exists():
        paths.append(str(default_plugins))
    return ";".join(paths)


def run_mame(args: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    paths = find_mame_paths()
    command = [
        str(paths.binary),
        *args,
        "-homepath",
        str(paths.homepath),
        "-pluginspath",
        paths.pluginspath,
    ]
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        **kwargs,
    )


def get_game_info(game_id: str) -> dict[str, str]:
    result = run_mame([game_id, "-listxml"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Failed to read game info")

    root = ET.fromstring(result.stdout)
    machine = root.find("machine")
    if machine is None:
        raise RuntimeError(f"Game not found: {game_id}")

    description = machine.findtext("description", game_id)
    year = machine.findtext("year", "")
    manufacturer = machine.findtext("manufacturer", "")
    cloneof = machine.get("cloneof", "")

    return {
        "id": game_id,
        "title": description,
        "year": year,
        "manufacturer": manufacturer,
        "cloneof": cloneof,
    }


def verify_game(game_id: str, rompath: Path) -> tuple[bool, str, str]:
    rompath_arg = build_rompath(rompath)
    result = run_mame([game_id, "-rompath", rompath_arg, "-verifyroms"])
    output = f"{result.stdout}\n{result.stderr}".strip()
    if "is good" in output:
        return True, "ROM set verified", output
    if "is bad" in output or "NOT FOUND" in output or "INCORRECT" in output:
        return False, "ROM set verification failed", output
    return False, output or "Unable to verify ROM set", output


def build_rompath(*paths: Path) -> str:
    """Build a MAME rompath search list from library paths and bundled ROMs."""
    entries: list[str] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        resolved = str(path.resolve())
        if resolved not in seen and path.exists():
            seen.add(resolved)
            entries.append(resolved)

    for path in paths:
        add(path)

    paths_info = find_mame_paths()
    for candidate in (
        paths_info.homepath / "roms",
        paths_info.homepath / "share" / "mame" / "roms",
        Path.home() / ".mame" / "roms",
    ):
        add(candidate)

    if not entries:
        raise RuntimeError("No ROM path available for MAME")
    return ";".join(entries)
