"""Controller profile and MAME input mapping."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from emulator.paths import cfg_root, ctrlr_root, library_root

CONTROLLER_NAME = "coinvault"
CONTROLLER_PROFILE_FILE = "controller.json"
CONTROLLER_CFG_FILE = f"{CONTROLLER_NAME}.cfg"

MAC_KEYCODE_TO_MAME: dict[int, str] = {
    0: "KEYCODE_A",
    1: "KEYCODE_S",
    2: "KEYCODE_D",
    3: "KEYCODE_F",
    4: "KEYCODE_H",
    5: "KEYCODE_G",
    6: "KEYCODE_Z",
    7: "KEYCODE_X",
    8: "KEYCODE_C",
    9: "KEYCODE_V",
    11: "KEYCODE_B",
    12: "KEYCODE_Q",
    13: "KEYCODE_W",
    14: "KEYCODE_E",
    15: "KEYCODE_R",
    16: "KEYCODE_Y",
    17: "KEYCODE_T",
    18: "KEYCODE_1",
    19: "KEYCODE_2",
    20: "KEYCODE_3",
    21: "KEYCODE_4",
    22: "KEYCODE_6",
    23: "KEYCODE_5",
    24: "KEYCODE_EQUALS",
    25: "KEYCODE_9",
    26: "KEYCODE_7",
    27: "KEYCODE_MINUS",
    28: "KEYCODE_8",
    29: "KEYCODE_0",
    31: "KEYCODE_O",
    32: "KEYCODE_U",
    33: "KEYCODE_I",
    34: "KEYCODE_P",
    35: "KEYCODE_L",
    37: "KEYCODE_J",
    38: "KEYCODE_K",
    39: "KEYCODE_SEMICOLON",
    40: "KEYCODE_M",
    41: "KEYCODE_N",
    42: "KEYCODE_COMMA",
    43: "KEYCODE_SLASH",
    44: "KEYCODE_PERIOD",
    45: "KEYCODE_LSHIFT",
    46: "KEYCODE_BACKSLASH",
    47: "KEYCODE_RSHIFT",
    48: "KEYCODE_TAB",
    49: "KEYCODE_SPACE",
    50: "KEYCODE_BACKQUOTE",
    51: "KEYCODE_BACKSPACE",
    53: "KEYCODE_ESC",
    36: "KEYCODE_ENTER",
    30: "KEYCODE_CLOSEBRACE",
    33: "KEYCODE_OPENBRACE",
    96: "KEYCODE_F5",
    97: "KEYCODE_F6",
    98: "KEYCODE_F7",
    99: "KEYCODE_F3",
    100: "KEYCODE_F8",
    101: "KEYCODE_F9",
    103: "KEYCODE_F11",
    109: "KEYCODE_F10",
    111: "KEYCODE_F12",
    118: "KEYCODE_F4",
    120: "KEYCODE_F2",
    122: "KEYCODE_F1",
    123: "KEYCODE_LEFT",
    124: "KEYCODE_RIGHT",
    125: "KEYCODE_DOWN",
    126: "KEYCODE_UP",
}

MAME_TO_LABEL: dict[str, str] = {
    "KEYCODE_UP": "Up Arrow",
    "KEYCODE_DOWN": "Down Arrow",
    "KEYCODE_LEFT": "Left Arrow",
    "KEYCODE_RIGHT": "Right Arrow",
    "KEYCODE_SPACE": "Space",
    "KEYCODE_ENTER": "Return",
    "KEYCODE_ESC": "Escape",
    "KEYCODE_TAB": "Tab",
    "KEYCODE_LSHIFT": "Left Shift",
    "KEYCODE_RSHIFT": "Right Shift",
    "KEYCODE_BACKSPACE": "Backspace",
    "KEYCODE_F1": "F1",
    "KEYCODE_F2": "F2",
    "KEYCODE_F3": "F3",
    "KEYCODE_F4": "F4",
    "KEYCODE_F5": "F5",
    "KEYCODE_F6": "F6",
    "KEYCODE_F7": "F7",
    "KEYCODE_F8": "F8",
    "KEYCODE_F9": "F9",
    "KEYCODE_F10": "F10",
    "KEYCODE_F11": "F11",
    "KEYCODE_F12": "F12",
    "KEYCODE_OPENBRACE": "[",
    "KEYCODE_CLOSEBRACE": "]",
    "KEYCODE_BACKSLASH": "\\",
    "KEYCODE_SEMICOLON": ";",
    "KEYCODE_EQUALS": "=",
    "KEYCODE_MINUS": "-",
    "KEYCODE_COMMA": ",",
    "KEYCODE_PERIOD": ".",
    "KEYCODE_SLASH": "/",
    "KEYCODE_BACKQUOTE": "`",
}


@dataclass(frozen=True)
class ControllerAction:
    action_id: str
    label: str
    port_type: str
    default_key: str
    group: str


def _player_actions(prefix: str, group: str, move_keys: tuple[str, str, str, str],
                    buttons: tuple[str, ...], start_key: str) -> tuple[ControllerAction, ...]:
    pid = prefix.lower()
    up, down, left, right = move_keys
    actions = [
        ControllerAction(f"{pid}_up", "Move Up", f"{prefix}_JOYSTICK_UP", up, group),
        ControllerAction(f"{pid}_down", "Move Down", f"{prefix}_JOYSTICK_DOWN", down, group),
        ControllerAction(f"{pid}_left", "Move Left", f"{prefix}_JOYSTICK_LEFT", left, group),
        ControllerAction(f"{pid}_right", "Move Right", f"{prefix}_JOYSTICK_RIGHT", right, group),
    ]
    for index, key in enumerate(buttons, start=1):
        actions.append(
            ControllerAction(
                f"{pid}_btn{index}",
                f"Button {index}",
                f"{prefix}_BUTTON{index}",
                key,
                group,
            )
        )
    actions.append(
        ControllerAction(f"{pid}_start", "Start", f"{prefix}_START", start_key, group)
    )
    return tuple(actions)


CONTROLLER_ACTIONS: tuple[ControllerAction, ...] = (
    *_player_actions(
        "P1",
        "Player 1",
        ("KEYCODE_UP", "KEYCODE_DOWN", "KEYCODE_LEFT", "KEYCODE_RIGHT"),
        ("KEYCODE_Z", "KEYCODE_X", "KEYCODE_C", "KEYCODE_V", "KEYCODE_B", "KEYCODE_N"),
        "KEYCODE_1",
    ),
    *_player_actions(
        "P2",
        "Player 2",
        ("KEYCODE_W", "KEYCODE_S", "KEYCODE_A", "KEYCODE_D"),
        ("KEYCODE_F", "KEYCODE_G", "KEYCODE_H", "KEYCODE_J", "KEYCODE_K", "KEYCODE_L"),
        "KEYCODE_2",
    ),
    *_player_actions(
        "P3",
        "Player 3",
        ("KEYCODE_I", "KEYCODE_K", "KEYCODE_J", "KEYCODE_L"),
        ("KEYCODE_U", "KEYCODE_O", "KEYCODE_P", "KEYCODE_OPENBRACE", "KEYCODE_CLOSEBRACE", "KEYCODE_BACKSLASH"),
        "KEYCODE_3",
    ),
    *_player_actions(
        "P4",
        "Player 4",
        ("KEYCODE_T", "KEYCODE_G", "KEYCODE_F", "KEYCODE_H"),
        ("KEYCODE_Y", "KEYCODE_R", "KEYCODE_E", "KEYCODE_Q", "KEYCODE_W", "KEYCODE_TAB"),
        "KEYCODE_4",
    ),
    ControllerAction("coin1", "Insert Coin 1", "COIN1", "KEYCODE_5", "System"),
    ControllerAction("coin2", "Insert Coin 2", "COIN2", "KEYCODE_6", "System"),
    ControllerAction("coin3", "Insert Coin 3", "COIN3", "KEYCODE_7", "System"),
    ControllerAction("coin4", "Insert Coin 4", "COIN4", "KEYCODE_8", "System"),
    ControllerAction("service", "Service", "SERVICE", "KEYCODE_9", "System"),
    ControllerAction("test", "Test / Diagnostics", "TEST", "KEYCODE_F2", "System"),
    ControllerAction("tilt", "Tilt", "TILT", "KEYCODE_T", "System"),
    ControllerAction("pause", "Pause", "UI_PAUSE", "KEYCODE_P", "MAME UI"),
    ControllerAction("ui_menu", "MAME Menu", "UI_CONFIGURE", "KEYCODE_TAB", "MAME UI"),
    ControllerAction("ui_cancel", "UI Back / Cancel", "UI_BACK", "KEYCODE_ESC", "MAME UI"),
)

PORT_ALIASES: dict[str, list[str]] = {
    "P1_START": ["START1"],
    "P2_START": ["START2"],
    "P3_START": ["START3"],
    "P4_START": ["START4"],
}


def controller_profile_path() -> Path:
    return library_root() / CONTROLLER_PROFILE_FILE


def cfg_directory() -> Path:
    return cfg_root()


def default_bindings() -> dict[str, str]:
    return {action.action_id: action.default_key for action in CONTROLLER_ACTIONS}


def format_key_label(mame_key: str) -> str:
    if mame_key in MAME_TO_LABEL:
        return MAME_TO_LABEL[mame_key]
    if mame_key.startswith("KEYCODE_"):
        suffix = mame_key.removeprefix("KEYCODE_")
        if len(suffix) == 1:
            return suffix
        return suffix.replace("_", " ").title()
    return mame_key


def mame_key_from_event(key_code: int, characters: str | None) -> str | None:
    if key_code in MAC_KEYCODE_TO_MAME:
        return MAC_KEYCODE_TO_MAME[key_code]
    if characters:
        char = characters.upper()
        if len(char) == 1 and char.isalnum():
            return f"KEYCODE_{char}"
    return None


class ControllerProfile:
    def __init__(self, name: str, bindings: dict[str, str]) -> None:
        self.name = name
        self.bindings = bindings

    @classmethod
    def load(cls) -> ControllerProfile:
        path = controller_profile_path()
        if not path.exists():
            profile = cls("Laptop Arcade", default_bindings())
            profile.save()
            return profile

        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        bindings = default_bindings()
        bindings.update(payload.get("bindings", {}))
        return cls(payload.get("name", "Laptop Arcade"), bindings)

    def save(self) -> None:
        path = controller_profile_path()
        payload = {
            "name": self.name,
            "version": 2,
            "bindings": self.bindings,
        }
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        write_mame_controller_cfg(self)

    def reset_defaults(self) -> None:
        self.bindings = default_bindings()

    def get_binding(self, action_id: str) -> str:
        action = _action_by_id(action_id)
        return self.bindings.get(action_id, action.default_key)

    def set_binding(self, action_id: str, mame_key: str) -> None:
        if action_id not in default_bindings():
            raise KeyError(f"Unknown action: {action_id}")
        self.bindings[action_id] = mame_key


def _action_by_id(action_id: str) -> ControllerAction:
    for action in CONTROLLER_ACTIONS:
        if action.action_id == action_id:
            return action
    raise KeyError(action_id)


def write_mame_controller_cfg(profile: ControllerProfile) -> Path:
    ctrlr_root().mkdir(parents=True, exist_ok=True)
    cfg_path = ctrlr_root() / CONTROLLER_CFG_FILE

    root = ET.Element("mameconfig", version="10")
    system = ET.SubElement(root, "system", name="default")
    input_elem = ET.SubElement(system, "input")

    ET.SubElement(input_elem, "comment").text = (
        f"CoinVault controller profile: {profile.name}"
    )

    ui_ports = {
        "UI_UP": "KEYCODE_UP",
        "UI_DOWN": "KEYCODE_DOWN",
        "UI_LEFT": "KEYCODE_LEFT",
        "UI_RIGHT": "KEYCODE_RIGHT",
        "UI_SELECT": "KEYCODE_ENTER",
        "UI_BACK": "KEYCODE_ESC",
        "UI_CANCEL": "KEYCODE_ESC",
        "UI_CLEAR": "KEYCODE_DEL",
    }
    for port_type, key in ui_ports.items():
        _append_port(input_elem, port_type, key)

    for action in CONTROLLER_ACTIONS:
        key = profile.get_binding(action.action_id)
        _append_port(input_elem, action.port_type, key)
        for alias in PORT_ALIASES.get(action.port_type, []):
            _append_port(input_elem, alias, key)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ")
    tree.write(cfg_path, encoding="utf-8", xml_declaration=True)
    return cfg_path


def _append_port(input_elem: ET.Element, port_type: str, mame_key: str) -> None:
    port = ET.SubElement(input_elem, "port", type=port_type)
    seq = ET.SubElement(port, "newseq", type="standard")
    seq.text = mame_key


def ensure_controller_ready() -> ControllerProfile:
    profile = ControllerProfile.load()
    write_mame_controller_cfg(profile)
    cfg_directory()
    return profile


def controller_launch_args() -> list[str]:
    write_mame_controller_cfg(ControllerProfile.load())
    return [
        "-ctrlrpath",
        str(ctrlr_root()),
        "-ctrlr",
        CONTROLLER_NAME,
        "-cfg_directory",
        str(cfg_directory()),
    ]
