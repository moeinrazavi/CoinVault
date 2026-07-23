"""Global macOS hotkey listener for save/load commands."""

from __future__ import annotations

import threading
from collections.abc import Callable

from pynput import keyboard


class HotkeyListener:
    def __init__(
        self,
        on_save: Callable[[], None],
        on_load: Callable[[], None],
    ) -> None:
        self._on_save = on_save
        self._on_load = on_load
        self._listener: keyboard.GlobalHotKeys | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        hotkeys = {
            "<cmd>+s": self._on_save,
            "<cmd>+l": self._on_load,
        }
        self._listener = keyboard.GlobalHotKeys(hotkeys)
        self._thread = threading.Thread(
            target=self._listener.start,
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
