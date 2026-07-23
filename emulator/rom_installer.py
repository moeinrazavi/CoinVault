"""Install dropped ROM folders into a MAME-compatible layout."""

from __future__ import annotations

import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from emulator.mame import run_mame, verify_game


@dataclass(frozen=True)
class RomEntry:
    name: str
    merged: bool
    merge_name: str


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
    seen: set[str] = set()

    for rom in machine.findall("rom"):
        name = rom.get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        merge_name = rom.get("merge") or name
        entries.append(
            RomEntry(
                name=name,
                merged=rom.get("merge") is not None,
                merge_name=merge_name,
            )
        )

    return parent, entries


def _index_source_files(source_dir: Path) -> dict[str, Path]:
    indexed: dict[str, Path] = {}
    for path in source_dir.rglob("*"):
        if not path.is_file() or path.name.startswith("."):
            continue
        indexed[path.name.lower()] = path
    return indexed


def _resolve_source(entry: RomEntry, indexed: dict[str, Path]) -> Path | None:
    for candidate in (entry.name, entry.merge_name):
        source = indexed.get(candidate.lower())
        if source is not None:
            return source
    return None


def _target_dir(rompath_root: Path, game_id: str, parent: str, entry: RomEntry) -> Path:
    if entry.merged:
        return rompath_root / parent
    return rompath_root / game_id


def _borrow_missing_roms(
    missing: list[RomEntry],
    rompath_root: Path,
    game_id: str,
    parent: str,
    library_root: Path | None,
) -> list[RomEntry]:
    if not missing or library_root is None or not library_root.exists():
        return missing

    search_roots = [
        library_root / parent / "roms" / parent,
        library_root / parent / "roms" / game_id,
        library_root / parent / "roms",
        library_root / game_id / "roms" / parent,
        library_root / game_id / "roms" / game_id,
        library_root / game_id / "roms",
    ]
    for game_dir in library_root.iterdir():
        if not game_dir.is_dir():
            continue
        search_roots.extend(
            [
                game_dir / "roms" / parent,
                game_dir / "roms" / game_dir.name,
                game_dir / "roms",
                game_dir / "source",
            ]
        )

    still_missing: list[RomEntry] = []
    for entry in missing:
        target_dir = _target_dir(rompath_root, game_id, parent, entry)
        target_path = target_dir / entry.name
        if target_path.exists():
            continue

        borrowed = False
        for search_root in search_roots:
            if not search_root.exists():
                continue
            for candidate in (entry.name, entry.merge_name):
                source = search_root / candidate
                if source.is_file():
                    target_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target_path)
                    borrowed = True
                    break
                match = next(search_root.rglob(candidate), None)
                if match is not None and match.is_file():
                    target_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(match, target_path)
                    borrowed = True
                    break
            if borrowed:
                break

        if not borrowed:
            still_missing.append(entry)

    return still_missing


def _format_verify_failure(
    game_id: str,
    parent: str,
    missing: list[RomEntry],
    verify_message: str,
    verify_output: str,
) -> str:
    issues: list[str] = []
    issue_pattern = re.compile(
        r"^\S+\s+:\s+(.+?)\s+-\s+(NOT FOUND|INCORRECT LENGTH|BAD CRC|WRONG LENGTH)",
        re.IGNORECASE,
    )
    for line in verify_output.splitlines():
        match = issue_pattern.match(line.strip())
        if match:
            issues.append(f"{match.group(1)} ({match.group(2).lower()})")

    if missing:
        names = ", ".join(entry.name for entry in missing[:8])
        if parent != game_id:
            issues.insert(
                0,
                f"Missing ROM files for {game_id} (parent set: {parent}): {names}",
            )
        else:
            issues.insert(0, f"Missing ROM files: {names}")

    if not issues:
        return verify_message

    if parent != game_id and any("NOT FOUND" in line for line in verify_output.splitlines()):
        issues.append(
            "Clone sets often need the parent ROM files as well. "
            f"Try importing the parent set ({parent}) or add the missing files to the folder."
        )

    return "\n".join(issues[:10])


def install_rom_folder(
    source_dir: Path,
    game_id: str,
    rompath_root: Path,
    *,
    library_root: Path | None = None,
) -> str | None:
    parent, entries = _parse_rom_entries(game_id)
    indexed = _index_source_files(source_dir)

    if rompath_root.exists():
        shutil.rmtree(rompath_root)
    rompath_root.mkdir(parents=True, exist_ok=True)

    missing: list[RomEntry] = []
    for entry in entries:
        source = _resolve_source(entry, indexed)
        if source is None:
            missing.append(entry)
            continue

        target_dir = _target_dir(rompath_root, game_id, parent, entry)
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target_dir / entry.name)

    missing = _borrow_missing_roms(missing, rompath_root, game_id, parent, library_root)

    ok, message, output = verify_game(game_id, rompath_root)
    if ok:
        return None

    clone_missing = [entry for entry in missing if not entry.merged]
    if parent != game_id and not clone_missing:
        return (
            "Imported clone ROM set without every parent file. "
            "The game may not launch until missing parent ROMs are added."
        )

    raise RuntimeError(
        _format_verify_failure(game_id, parent, missing, message, output)
    )
