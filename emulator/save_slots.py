"""Rotating save-slot manager for per-game MAME save states."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

NUM_SLOTS = 8
ACK_TIMEOUT_SECONDS = 5.0


class SaveSlotManager:
    def __init__(self, game_id: str, saves_root: Path) -> None:
        self.game_id = game_id
        self.game_dir = saves_root / game_id
        self.states_dir = self.game_dir / "states"
        self.manifest_path = self.game_dir / "manifest.json"
        self.command_path = self.game_dir / "command.json"
        self.ack_path = self.game_dir / "ack.json"
        self.game_dir.mkdir(parents=True, exist_ok=True)
        self.states_dir.mkdir(parents=True, exist_ok=True)

    def _default_manifest(self) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "slots": [
                {
                    "id": slot_id,
                    "file": f"slot_{slot_id}",
                    "timestamp": None,
                }
                for slot_id in range(NUM_SLOTS)
            ],
        }

    def _normalize_slot(self, slot: dict[str, Any] | None, slot_id: int) -> dict[str, Any]:
        defaults = {
            "id": slot_id,
            "file": f"slot_{slot_id}",
            "timestamp": None,
        }
        if not isinstance(slot, dict):
            return defaults

        file_name = slot.get("file", defaults["file"])
        if "/" in file_name:
            file_name = file_name.rsplit("/", 1)[-1]

        return {
            "id": slot.get("id", slot_id),
            "file": file_name,
            "timestamp": slot.get("timestamp"),
        }

    def _normalize_manifest(self, manifest: dict[str, Any]) -> dict[str, Any]:
        slots = manifest.get("slots", [])
        normalized = [
            self._normalize_slot(slots[slot_id] if slot_id < len(slots) else None, slot_id)
            for slot_id in range(NUM_SLOTS)
        ]
        return {
            "game_id": manifest.get("game_id", self.game_id),
            "slots": normalized,
        }

    def _load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            manifest = self._default_manifest()
            self._write_manifest(manifest)
            return manifest

        with self.manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)

        normalized = self._normalize_manifest(manifest)
        if normalized != manifest:
            self._write_manifest(normalized)
        return normalized

    def _write_manifest(self, manifest: dict[str, Any]) -> None:
        with self.manifest_path.open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
            handle.write("\n")

    def _state_file_path(self, slot: dict[str, Any]) -> Path:
        direct = self.states_dir / f"{slot['file']}.sta"
        legacy = self.states_dir / self.game_id / f"{slot['file']}.sta"
        if legacy.exists():
            return legacy
        return direct

    def _state_file_exists(self, slot: dict[str, Any]) -> bool:
        return self._state_file_path(slot).exists()

    def _pick_save_slot(self, manifest: dict[str, Any]) -> dict[str, Any]:
        slots: list[dict[str, Any]] = manifest["slots"]
        empty_slots = [slot for slot in slots if slot.get("timestamp") is None]
        if empty_slots:
            return empty_slots[0]

        return min(slots, key=lambda slot: slot.get("timestamp") or "")

    def _pick_load_slot(self, manifest: dict[str, Any]) -> dict[str, Any] | None:
        saved_slots = [
            slot
            for slot in manifest["slots"]
            if slot.get("timestamp") is not None and self._state_file_exists(slot)
        ]
        if not saved_slots:
            return None

        return max(saved_slots, key=lambda slot: slot.get("timestamp") or "")

    def _write_command(self, action: str, file_name: str) -> None:
        if self.ack_path.exists():
            self.ack_path.unlink()

        payload = {"action": action, "file": file_name}
        with self.command_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle)

    def _wait_for_ack(self, action: str, file_name: str) -> tuple[bool, str]:
        deadline = time.time() + ACK_TIMEOUT_SECONDS
        while time.time() < deadline:
            if not self.ack_path.exists():
                time.sleep(0.05)
                continue

            try:
                with self.ack_path.open("r", encoding="utf-8") as handle:
                    ack = json.load(handle)
            except json.JSONDecodeError:
                time.sleep(0.05)
                continue

            if ack.get("action") != action or ack.get("file") != file_name:
                time.sleep(0.05)
                continue

            status = ack.get("status", "error")
            message = ack.get("message", "")
            return status == "ok", message

        return False, "Timed out waiting for MAME"

    def save(self) -> tuple[bool, str]:
        manifest = self._load_manifest()
        slot = self._pick_save_slot(manifest)
        file_name = slot["file"]

        self._write_command("save", file_name)
        ok, message = self._wait_for_ack("save", file_name)
        if not ok:
            return False, message

        slot["timestamp"] = datetime.now(timezone.utc).isoformat()
        self._write_manifest(manifest)
        return True, f"Saved to slot {slot['id'] + 1}/{NUM_SLOTS}"

    def load(self) -> tuple[bool, str]:
        manifest = self._load_manifest()
        slot = self._pick_load_slot(manifest)
        if slot is None:
            return False, "No save states found"

        file_name = slot["file"]
        self._write_command("load", file_name)
        ok, message = self._wait_for_ack("load", file_name)
        if not ok:
            return False, message

        return True, f"Loaded slot {slot['id'] + 1}/{NUM_SLOTS} (newest save)"

    def status_summary(self) -> str:
        manifest = self._load_manifest()
        used = sum(
            1
            for slot in manifest["slots"]
            if slot.get("timestamp") is not None and self._state_file_exists(slot)
        )
        return f"{used}/{NUM_SLOTS} slots used for {self.game_id}"
