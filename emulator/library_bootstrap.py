"""Copy bundled seed games into the user library on first launch."""

from __future__ import annotations

import json
import shutil

from emulator.paths import library_index_path, library_root, seed_library_root


def bootstrap_library() -> bool:
    """Install bundled seed content when the user library is empty."""
    if library_index_path().exists():
        try:
            with library_index_path().open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if payload.get("games"):
                return False
        except (json.JSONDecodeError, OSError):
            pass

    seed = seed_library_root()
    if seed is None:
        return False

    target = library_root()
    for folder_name in ("games", "saves"):
        source = seed / folder_name
        if not source.exists():
            continue
        destination = target / folder_name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)

    seed_index = seed / "library.json"
    if seed_index.exists():
        shutil.copy2(seed_index, library_index_path())

    return True
