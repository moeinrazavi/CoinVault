"""Identify MAME games from dropped ROM folders."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from emulator.mame import run_mame

PRIMARY_LINE = re.compile(
    r"^(?P<file>\S+)\s+=\s+(?P<alias>\S+)\s+"
    r"(?P<game_id>[a-z0-9_]+)\s+(?P<title>.+?)\s*$"
)
CONT_LINE = re.compile(
    r"^\s+=\s+(?P<alias>\S+)\s+(?P<game_id>[a-z0-9_]+)\s+(?P<title>.+?)\s*$"
)
SUMMARY_LINE = re.compile(
    r"Out of (?P<files>\d+) files, (?P<matched>\d+) matched"
)
ROM_EXTENSIONS = {
    ".bin", ".rom", ".f1", ".f3", ".h1", ".h3", ".j1", ".j3", ".k1", ".k3",
    ".v7", ".y1", ".z1", ".a1", ".y4", ".z4", ".y6", ".z6", ".y9", ".z9",
    ".a9", ".y12", ".z12", ".a12", ".f13", ".j13", ".k13", ".zip", ".7z",
    ".nv", ".key", ".dat", ".hex", ".s19", ".pal", ".pld", ".bprom",
}
MAME_LOCATION_SUFFIX = re.compile(r"^[a-z0-9]{1,8}$", re.IGNORECASE)
EXTENSIONLESS_ROM = re.compile(r"^[a-z0-9][a-z0-9_-]*$", re.IGNORECASE)
NON_ROM_EXTENSIONS = {
    "txt", "pdf", "png", "jpg", "jpeg", "gif", "bmp", "md", "nfo", "exe",
    "dll", "so", "dylib", "html", "htm", "url", "dmg", "doc", "rtf", "xml",
    "json", "lua", "py", "sh", "bat", "cmd", "log", "cue", "m3u", "wav",
    "mp3", "flac", "avi", "mkv", "mp4", "rar", "gz", "bz2", "xz", "tar",
}
SKIP_FILE_NAMES = {".ds_store", "thumbs.db", "desktop.ini", "readme.txt", "readme"}
SKIP_DIR_NAMES = {
    ".venv",
    ".git",
    "__pycache__",
    "CoinVault Library",
    "ArcadeSave Library",
    "build",
    "cfg",
    "dist",
    "dmg-staging",
    "emulator",
    "mame_home",
    "plugins",
    "roms",
    "saves",
}


@dataclass(frozen=True)
class IdentifiedGame:
    game_id: str
    title: str
    matched_files: int
    total_files: int
    confidence: float


def is_rom_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.name.startswith("."):
        return False
    if path.name.lower() in SKIP_FILE_NAMES:
        return False

    suffix = path.suffix.lower()
    if suffix in ROM_EXTENSIONS:
        return True

    stem_parts = path.name.lower().split(".")
    if len(stem_parts) >= 2 and stem_parts[-1] in {
        "f1", "h1", "j1", "k1", "f3", "h3", "j3", "k3", "v7", "y1", "z1",
        "a1", "y4", "z4", "y6", "z6", "y9", "z9", "a9", "y12", "z12", "a12",
        "f13", "j13", "k13",
    }:
        return True

    # MAME PCB location labels like 064e01.2f, epr-12010.43, epr-11264.95
    if len(stem_parts) >= 2:
        label = stem_parts[-1]
        if label not in NON_ROM_EXTENSIONS and MAME_LOCATION_SUFFIX.match(label):
            return True

    # Extensionless ROM names like buf1, ioa1, prg2, rom1
    if "." not in path.name and EXTENSIONLESS_ROM.match(path.name):
        return True

    return False


def collect_rom_files(folder: Path) -> list[Path]:
    roms: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        key = path.name.lower()
        if key not in seen and is_rom_file(path):
            seen.add(key)
            roms.append(path)

    for path in folder.iterdir():
        if path.is_file():
            add(path)
            continue
        if not path.is_dir():
            continue
        if path.name in SKIP_DIR_NAMES or path.name.startswith("."):
            continue
        for subpath in path.rglob("*"):
            if subpath.is_file():
                add(subpath)

    return roms


def _parse_romident_output(output: str) -> tuple[Counter[str], dict[str, str], int, int]:
    scores: Counter[str] = Counter()
    titles: dict[str, str] = {}
    file_games: dict[str, set[str]] = defaultdict(set)
    matched_files = 0
    total_files = 0
    current_file: str | None = None

    for line in output.splitlines():
        summary = SUMMARY_LINE.search(line)
        if summary:
            total_files = int(summary.group("files"))
            matched_files = int(summary.group("matched"))
            continue

        primary = PRIMARY_LINE.match(line)
        if primary:
            current_file = primary.group("file")
            game_id = primary.group("game_id")
            titles[game_id] = primary.group("title").strip()
            file_games[current_file].add(game_id)
            continue

        cont = CONT_LINE.match(line)
        if cont and current_file:
            game_id = cont.group("game_id")
            titles[game_id] = cont.group("title").strip()
            file_games[current_file].add(game_id)

    for game_ids in file_games.values():
        weight = 3 if len(game_ids) == 1 else 1
        for game_id in game_ids:
            scores[game_id] += weight

    return scores, titles, matched_files, total_files


def identify_game(folder: Path) -> IdentifiedGame | None:
    result = run_mame(["-romident", str(folder)])
    output = f"{result.stdout}\n{result.stderr}"
    scores, titles, matched_files, total_files = _parse_romident_output(output)
    if not scores:
        return None

    game_id, top_score = scores.most_common(1)[0]
    confidence = top_score / max(sum(scores.values()), 1)
    return IdentifiedGame(
        game_id=game_id,
        title=titles.get(game_id, game_id),
        matched_files=matched_files,
        total_files=total_files,
        confidence=confidence,
    )


def choose_best_game(folder: Path) -> IdentifiedGame | None:
    return identify_game(folder)
