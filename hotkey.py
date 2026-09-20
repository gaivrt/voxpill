"""Small state machine for filtering synthetic push-to-talk key pulses."""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys
import tempfile
import tomllib


VK = {
    "ctrl_r": 0xA3, "ctrl_l": 0xA2, "ctrl": 0x11,
    "alt_r": 0xA5, "alt_l": 0xA4, "alt": 0x12,
    "shift_r": 0xA1, "shift_l": 0xA0, "shift": 0x10,
    "`": 0xC0, "grave": 0xC0,
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
}
VK.update({chr(i).lower(): i for i in range(0x41, 0x5B)})
VK.update({str(i): 0x30 + i for i in range(10)})
VK.update({f"f{i}": 0x6F + i for i in range(13, 25)})
VK.update({"win_l": 0x5B, "win_r": 0x5C, "space": 0x20,
           "enter": 0x0D, "tab": 0x09, "escape": 0x1B,
           "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
           "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
           "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28})
KEY_LABELS = {
    "ctrl_r": "右 Ctrl（默认）", "ctrl_l": "左 Ctrl", "ctrl": "任一 Ctrl",
    "alt_r": "右 Alt", "alt_l": "左 Alt", "alt": "任一 Alt",
    "shift_r": "右 Shift", "shift_l": "左 Shift", "shift": "任一 Shift",
    "`": "反引号（`）",
    **{f"f{i}": f"F{i}" for i in range(1, 13)},
}
KEY_LABELS.update({"ctrl_r": "右 Ctrl", "win_l": "左 Win", "win_r": "右 Win",
                   "space": "空格", "enter": "Enter", "escape": "Esc"})
KEY_LABELS.update({f"vk_{0x60 + i:02x}": f"小键盘 {i}" for i in range(10)})
KEY_LABELS.update({
    "vk_ba": ";", "vk_bb": "=", "vk_bc": ",", "vk_bd": "-",
    "vk_be": ".", "vk_bf": "/", "vk_db": "[", "vk_dc": "\\",
    "vk_dd": "]", "vk_de": "'", "vk_14": "Caps Lock",
    "vk_90": "Num Lock", "vk_91": "Scroll Lock", "vk_2c": "Print Screen",
    "vk_13": "Pause", "vk_5d": "菜单键", "vk_6a": "小键盘 *",
    "vk_6b": "小键盘 +", "vk_6d": "小键盘 -", "vk_6e": "小键盘 .",
    "vk_6f": "小键盘 /", "vk_ad": "静音", "vk_ae": "音量 -",
    "vk_af": "音量 +", "vk_b0": "下一曲", "vk_b1": "上一曲",
    "vk_b2": "停止播放", "vk_b3": "播放 / 暂停",
})


def parse_hotkey(key: str) -> tuple[int, ...]:
    codes = []
    for part in key.lower().split("+"):
        part = part.strip()
        code = VK.get(part)
        if code is None and re.fullmatch(r"vk_[0-9a-f]{2}", part):
            code = int(part[3:], 16)
        if code is None or not 8 <= code <= 254:
            raise ValueError(f"Unsupported hotkey: {key}")
        if code not in codes:
            codes.append(code)
    return tuple(codes)


def encode_hotkey(codes) -> str:
    names = {value: name for name, value in reversed(list(VK.items()))}
    modifiers = (0xA2, 0xA3, 0xA0, 0xA1, 0xA4, 0xA5, 0x5B, 0x5C)
    ordered = sorted(set(codes), key=lambda code: (code not in modifiers, code))
    return "+".join(names.get(code, f"vk_{code:02x}") for code in ordered)


def hotkey_label(key: str) -> str:
    labels = KEY_LABELS
    if sys.platform == "darwin":
        labels = {**labels, "win_l": "左 Command", "win_r": "右 Command",
                  "alt_l": "左 Option", "alt_r": "右 Option", "alt": "任一 Option",
                  "ctrl_l": "左 Control", "ctrl_r": "右 Control", "ctrl": "任一 Control"}
    return " + ".join(labels.get(part, part.upper()) for part in key.split("+"))


class HotkeyCapture:
    """One press/release gesture, including modifier-only chords and repeats."""
    def __init__(self):
        self.held = set()
        self.chord = set()

    def feed(self, code, down):
        if down:
            self.held.add(code)
            self.chord.add(code)
        else:
            self.held.discard(code)
            if self.chord and not self.held:
                result = encode_hotkey(self.chord)
                self.chord.clear()
                return result
        return None


def save_hotkey(path: Path, key: str) -> None:
    """Atomically update only the hotkey, preserving other settings/comments."""
    parse_hotkey(key)
    source = path.read_text(encoding="utf-8") if path.exists() else ""
    before = tomllib.loads(source)
    section = re.search(r"(?m)^\[hotkey\][ \t]*(?:#[^\n]*)?$", source)
    if section:
        end = re.search(r"(?m)^\[", source[section.end():])
        stop = section.end() + end.start() if end else len(source)
        body = source[section.end():stop]
        body, count = re.subn(
            r'''(?m)^([ \t]*key[ \t]*=[ \t]*)(?:"[^"\n]*"|'[^'\n]*')''',
            lambda match: match[1] + f'"{key}"', body, count=1,
        )
        if not count:
            body = f'\nkey = "{key}"\n' + body
        updated = source[:section.end()] + body + source[stop:]
    else:
        updated = source + f'\n[hotkey]\nkey = "{key}"\n'
    expected = dict(before)
    expected["hotkey"] = {**before.get("hotkey", {}), "key": key}
    if tomllib.loads(updated) != expected:
        raise ValueError("无法在保留其他设置的同时保存快捷键")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False,
            prefix=path.name + ".", suffix=".tmp",
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(updated)
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


@dataclass
class HotkeySelection:
    key: str = "ctrl_r"
    pending: str | None = None

    def apply_pending(self, recording, is_down) -> bool:
        """Keep the old binding until recording ends and both keys are released."""
        if self.pending is None or recording:
            return False
        if any(is_down(code) for code in (*parse_hotkey(self.key), *parse_hotkey(self.pending))):
            return False
        self.key, self.pending = self.pending, None
        return True


@dataclass
class HotkeyGate:
    stable_seconds: float
    mouse_guard_seconds: float
    recording: bool = False
    candidate_since: float | None = None
    mouse_guard_until: float = 0.0
    previous_left: bool = False

    def update(self, checked_at: float, key_down: bool, left_down: bool) -> str | None:
        if left_down or left_down != self.previous_left:
            self.mouse_guard_until = checked_at + self.mouse_guard_seconds
        self.previous_left = left_down

        if self.recording:
            if not key_down:
                self.recording = False
                return "stop"
            return None

        if not key_down:
            self.candidate_since = None
            return None
        if self.candidate_since is None:
            self.candidate_since = checked_at
            return None
        if (
            checked_at - self.candidate_since >= self.stable_seconds
            and checked_at >= self.mouse_guard_until
        ):
            self.candidate_since = None
            self.recording = True
            return "start"
        return None
