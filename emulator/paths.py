"""Resolve application, bundle, and library paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "CoinVault"
LIBRARY_DIR_NAME = "CoinVault Library"
APPLICATION_SUPPORT_DIR = "CoinVault"
BUNDLE_ID = "com.coinvault.app"
ENV_VAR = "COINVAULT_LIBRARY"

LEGACY_APP_NAME = "ArcadeSave"
LEGACY_LIBRARY_DIR_NAME = "ArcadeSave Library"
LEGACY_APPLICATION_SUPPORT_DIR = "ArcadeSave"
LEGACY_ENV_VAR = "ARCADESAVE_LIBRARY"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def project_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent.parent
    return Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return project_root() / "Resources"
    return Path(__file__).resolve().parent.parent


def _resolve_library_root() -> Path:
    env_override = os.environ.get(ENV_VAR) or os.environ.get(LEGACY_ENV_VAR)
    if env_override:
        return Path(env_override)

    if is_frozen():
        support = Path.home() / "Library" / "Application Support"
        new_root = support / APPLICATION_SUPPORT_DIR
        legacy_root = support / LEGACY_APPLICATION_SUPPORT_DIR
        if new_root.exists():
            return new_root
        if legacy_root.exists():
            return legacy_root
        return new_root

    project = Path(__file__).resolve().parent.parent
    new_dev = project / LIBRARY_DIR_NAME
    legacy_dev = project / LEGACY_LIBRARY_DIR_NAME
    if new_dev.exists():
        return new_dev
    if legacy_dev.exists():
        return legacy_dev
    return new_dev


def library_root() -> Path:
    root = _resolve_library_root()
    root.mkdir(parents=True, exist_ok=True)
    (root / "games").mkdir(parents=True, exist_ok=True)
    (root / "saves").mkdir(parents=True, exist_ok=True)
    return root


def seed_library_root() -> Path | None:
    seed = resource_root() / "seed" / "library"
    if (seed / "library.json").exists() or (seed / "games").exists():
        return seed
    bundled_seed = project_root() / "Resources" / "seed" / "library"
    if (bundled_seed / "library.json").exists() or (bundled_seed / "games").exists():
        return bundled_seed
    return None


def games_root() -> Path:
    return library_root() / "games"


def saves_root() -> Path:
    return library_root() / "saves"


def ctrlr_root() -> Path:
    path = library_root() / "ctrlr"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cfg_root() -> Path:
    path = library_root() / "cfg"
    path.mkdir(parents=True, exist_ok=True)
    return path


def ini_root() -> Path:
    path = library_root() / "ini"
    path.mkdir(parents=True, exist_ok=True)
    return path


def library_index_path() -> Path:
    return library_root() / "library.json"


def plugins_root() -> Path:
    bundled = resource_root() / "plugins"
    if bundled.exists():
        return bundled
    return Path(__file__).resolve().parent.parent / "plugins"


def bundled_mame_root() -> Path | None:
    candidates = [
        resource_root() / "mame",
        project_root() / "Resources" / "mame",
    ]
    for candidate in candidates:
        if (candidate / "bin" / "mame").exists():
            return candidate
    return None


def mame_bundle_root() -> Path:
    bundled = bundled_mame_root()
    if bundled is not None:
        return bundled
    brew_path = Path("/opt/homebrew/opt/mame")
    if brew_path.exists():
        return brew_path
    return Path("/opt/homebrew/opt/mame")
