"""Install dropped ROM folders into a MAME-compatible layout."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from emulator.mame import run_mame, verify_game


@dataclass(frozen=True)
class RomEntry:
    name: str
    merged: bool


def _parse_rom_entries(game_id: str) -> tuple[str, list[RomEntry]]:
    result = run_mame([game_id, "-listxml"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Failed to read ROM layout")

    root = ET.fromstring(result.stdout)
    machine = root.find("machine")
    if machine is None:
        raise RuntimeError(f"Unknown game: {game_id}")

    parent = machine.get("cloneof") or game_id
    entries: list[RomEntry] = []
    for rom in machine.findall("rom"):
        name = rom.get("name")
        if not name:
            continue
        entries.append(RomEntry(name=name, merged=rom.get("merge") is not None))

    return parent, entries


def _index_source_files(source_dir: Path) -> dict[str, Path]:
    indexed: dict[str, Path] = {}
    for path in source_dir.rglob("*"):
        if path.is_file():
            indexed[path.name.lower()] = path
    return indexed


def install_rom_folder(source_dir: Path, game_id: str, rompath_root: Path) -> None:
    parent, entries = _parse_rom_entries(game_id)
    indexed = _index_source_files(source_dir)

    if rompath_root.exists():
        shutil.rmtree(rompath_root)
    rompath_root.mkdir(parents=True, exist_ok=True)

    missing: list[str] = []
    for entry in entries:
        source = indexed.get(entry.name.lower())
        if source is None:
            missing.append(entry.name)
            continue

        if entry.merged:
            target_dir = rompath_root / parent
        else:
            target_dir = rompath_root / game_id

        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target_dir / entry.name)

    ok, message = verify_game(game_id, rompath_root)
    if not ok:
        detail = ", ".join(missing[:5])
        if detail:
            raise RuntimeError(f"{message}. Missing: {detail}")
        raise RuntimeError(message)
