"""Resolve game library artwork from validated sources."""

from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path

from emulator.mame import get_game_info

LIBRETRO_MAME_BASE = "https://thumbnails.libretro.com/MAME"
ARTWORK_VERSION = 2
ICON_SIZE = 512
USER_AGENT = "CoinVault/1.0"
LOCAL_ARTWORK_NAMES = (
    "boxart.png",
    "boxart.jpg",
    "boxart.jpeg",
    "cover.png",
    "cover.jpg",
    "cover.jpeg",
    "flyer.png",
    "flyer.jpg",
    "flyer.jpeg",
    "marquee.png",
    "marquee.jpg",
    "marquee.jpeg",
    "artwork.png",
    "artwork.jpg",
    "artwork.jpeg",
    "title.png",
    "title.jpg",
    "title.jpeg",
)
LOCAL_ARTWORK_PATTERNS = (
    re.compile(r"(?:box[\s_-]?art|cover|flyer|marquee|cabinet|poster)", re.IGNORECASE),
)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def capture_icon(
    game_id: str,
    rompath: Path,
    icon_path: Path,
    *,
    title: str = "",
    source_dirs: list[Path] | None = None,
    cloneof: str = "",
) -> bool:
    """Backwards-compatible entry point used by the game library."""
    return resolve_game_icon(
        game_id=game_id,
        title=title,
        icon_path=icon_path,
        source_dirs=source_dirs,
        cloneof=cloneof,
    )


def resolve_game_icon(
    game_id: str,
    title: str,
    icon_path: Path,
    *,
    source_dirs: list[Path] | None = None,
    cloneof: str = "",
) -> bool:
    icon_path.parent.mkdir(parents=True, exist_ok=True)

    for directory in source_dirs or []:
        local = find_local_artwork(directory, game_id)
        if local is not None and _save_normalized_icon(local, icon_path):
            return True

    titles = _candidate_titles(title, game_id, cloneof)
    for candidate in titles:
        if _fetch_libretro_art("Named_Boxarts", candidate, icon_path):
            return True

    for candidate in titles:
        if _fetch_libretro_art("Named_Titles", candidate, icon_path):
            return True

    return False


def find_local_artwork(folder: Path, game_id: str) -> Path | None:
    if not folder.is_dir():
        return None

    exact_names = {name.lower() for name in LOCAL_ARTWORK_NAMES}
    exact_names.add(f"{game_id}.png")
    exact_names.add(f"{game_id}.jpg")
    exact_names.add(f"{game_id}.jpeg")

    matches: list[Path] = []
    for path in folder.iterdir():
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        lowered = path.name.lower()
        if lowered in exact_names or any(pattern.search(path.stem) for pattern in LOCAL_ARTWORK_PATTERNS):
            matches.append(path)

    if not matches:
        return None

    matches.sort(key=_local_artwork_rank)
    return matches[0]


def _local_artwork_rank(path: Path) -> tuple[int, str]:
    name = path.name.lower()
    if "boxart" in name or name.startswith("cover"):
        return (0, name)
    if "flyer" in name or "marquee" in name or "poster" in name:
        return (1, name)
    if "cabinet" in name or "artwork" in name:
        return (2, name)
    return (3, name)


def _candidate_titles(title: str, game_id: str, cloneof: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            candidates.append(cleaned)

    add(title)
    if cloneof:
        try:
            parent_info = get_game_info(cloneof)
        except RuntimeError:
            parent_info = None
        if parent_info:
            add(parent_info["title"])

    if not title:
        add(game_id.replace("_", " ").title())

    return candidates


def _fetch_libretro_art(category: str, title: str, icon_path: Path) -> bool:
    encoded_title = urllib.parse.quote(title, safe="")
    url = f"{LIBRETRO_MAME_BASE}/{category}/{encoded_title}.png"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status != 200:
                return False
            content_type = response.headers.get("Content-Type", "")
            if content_type and "image" not in content_type.lower():
                return False
            data = response.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return False

    if not data:
        return False

    return _save_normalized_icon(BytesIO(data), icon_path)


def _save_normalized_icon(source: Path | BytesIO, icon_path: Path) -> bool:
    try:
        from PIL import Image, ImageOps
    except ImportError:
        if isinstance(source, Path):
            icon_path.write_bytes(source.read_bytes())
            return icon_path.exists()
        return False

    try:
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA")

            width, height = image.size
            if width <= 0 or height <= 0:
                return False

            scale = max(ICON_SIZE / width, ICON_SIZE / height)
            resized = image.resize(
                (max(1, int(width * scale)), max(1, int(height * scale))),
                Image.Resampling.LANCZOS,
            )
            left = (resized.width - ICON_SIZE) // 2
            top = (resized.height - ICON_SIZE) // 2
            cropped = resized.crop(
                (left, top, left + ICON_SIZE, top + ICON_SIZE)
            )

            if cropped.mode == "RGBA":
                background = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (18, 20, 26, 255))
                background.alpha_composite(cropped)
                cropped = background.convert("RGB")
            else:
                cropped = cropped.convert("RGB")

            cropped.save(icon_path, format="PNG", optimize=True)
            return True
    except OSError:
        return False
