"""Persistent game library stored beside the installed app."""

from __future__ import annotations

import json
import shutil
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from emulator.game_id import choose_best_game, collect_rom_files
from emulator.icon_capture import capture_icon
from emulator.mame import get_game_info, verify_game
from emulator.paths import games_root, library_index_path, saves_root
from emulator.rom_installer import install_rom_folder


@dataclass
class GameEntry:
    id: str
    title: str
    year: str
    manufacturer: str
    added_at: str
    icon: str
    source_name: str

    @property
    def rompath(self) -> Path:
        return games_root() / self.id / "roms"

    @property
    def icon_path(self) -> Path:
        return games_root() / self.id / self.icon

    @property
    def source_path(self) -> Path:
        return games_root() / self.id / "source"


class GameLibrary:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def _load_index(self) -> dict[str, GameEntry]:
        index_path = library_index_path()
        if not index_path.exists():
            return {}

        with index_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)

        entries: dict[str, GameEntry] = {}
        for item in raw.get("games", []):
            entry = GameEntry(**item)
            entries[entry.id] = entry
        return entries

    def _save_index(self, entries: dict[str, GameEntry]) -> None:
        index_path = library_index_path()
        payload = {
            "games": [asdict(entry) for entry in sorted(
                entries.values(),
                key=lambda game: game.title.lower(),
            )]
        }
        with index_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")

    def list_games(self) -> list[GameEntry]:
        with self._lock:
            return list(self._load_index().values())

    def get_game(self, game_id: str) -> GameEntry | None:
        with self._lock:
            return self._load_index().get(game_id)

    def add_game_from_folder(
        self,
        folder: Path,
        progress: Callable[[str], None] | None = None,
    ) -> GameEntry:
        def update(message: str) -> None:
            if progress:
                progress(message)

        folder = folder.resolve()
        if not folder.is_dir():
            raise ValueError("Drop a folder containing ROM files")

        update("Identifying game...")
        identified = choose_best_game(folder)
        if identified is None:
            raise RuntimeError("Could not identify a supported MAME game")

        game_id = identified.game_id
        update(f"Detected {identified.title}")

        with self._lock:
            entries = self._load_index()
            if game_id in entries:
                raise RuntimeError(f"{entries[game_id].title} is already in your library")

            game_dir = games_root() / game_id
            source_dir = game_dir / "source"
            rompath = game_dir / "roms"
            icon_path = game_dir / "icon.png"

            if game_dir.exists():
                shutil.rmtree(game_dir)
            source_dir.mkdir(parents=True, exist_ok=True)

            update("Copying ROM files...")
            copied = 0
            for rom_file in collect_rom_files(folder):
                target = source_dir / rom_file.name
                shutil.copy2(rom_file, target)
                copied += 1

            if copied == 0:
                raise RuntimeError("No ROM files found in the dropped folder")

            update("Organizing ROM set...")
            install_rom_folder(source_dir, game_id, rompath)

            info = get_game_info(game_id)
            update("Capturing icon...")
            if not capture_icon(game_id, rompath, icon_path):
                icon_path = game_dir / "icon.png"
                _write_placeholder_icon(icon_path, info["title"])

            entry = GameEntry(
                id=game_id,
                title=info["title"],
                year=info.get("year", ""),
                manufacturer=info.get("manufacturer", ""),
                added_at=datetime.now(timezone.utc).isoformat(),
                icon="icon.png",
                source_name=folder.name,
            )
            entries[game_id] = entry
            self._save_index(entries)
            (saves_root() / game_id).mkdir(parents=True, exist_ok=True)
            return entry

    def remove_game(self, game_id: str) -> None:
        with self._lock:
            entries = self._load_index()
            if game_id not in entries:
                return

            game_dir = games_root() / game_id
            if game_dir.exists():
                shutil.rmtree(game_dir)

            save_dir = saves_root() / game_id
            if save_dir.exists():
                shutil.rmtree(save_dir)

            del entries[game_id]
            self._save_index(entries)

    def verify_installed(self, game_id: str) -> tuple[bool, str]:
        entry = self.get_game(game_id)
        if entry is None:
            return False, "Game not found"
        return verify_game(game_id, entry.rompath)


def _write_placeholder_icon(icon_path: Path, title: str) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        icon_path.write_bytes(b"")
        return

    size = 256
    image = Image.new("RGB", (size, size), color=(24, 28, 36))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((16, 16, 240, 240), radius=24, fill=(45, 95, 168))

    words = title.split()
    line = words[0] if words else "?"
    if len(words) > 1:
        line = f"{words[0]}\n{' '.join(words[1:3])}"

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 28)
    except OSError:
        font = ImageFont.load_default()

    draw.multiline_text(
        (128, 128),
        line,
        fill="white",
        font=font,
        anchor="mm",
        align="center",
    )
    image.save(icon_path, format="PNG")
