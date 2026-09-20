"""macOS / X11 physical keys and conservative focus-safe text insertion.

Configuration retains the existing portable key names and internal VK numbers.
No global listener is used: polling physical state avoids missed key releases.
"""
import os
import subprocess
import sys
import threading
import time

from hotkey import parse_hotkey

# Apple hardware keycodes, independent of pynput's character event translation.
MAC_CODES = {
    0xA2: 59, 0xA3: 62, 0xA0: 56, 0xA1: 60, 0xA4: 58, 0xA5: 61,
    0x5B: 55, 0x5C: 54, 0x20: 49, 0x0D: 36, 0x09: 48, 0x1B: 53,
    0x08: 51, 0x2E: 117, 0x24: 115, 0x23: 119, 0x21: 116, 0x22: 121,
    0x25: 123, 0x26: 126, 0x27: 124, 0x28: 125, 0xC0: 50,
}
MAC_CODES.update(zip(map(ord, "ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    (0,11,8,2,14,3,5,4,34,38,40,37,46,45,31,35,12,15,1,17,32,9,13,7,16,6)))
MAC_CODES.update(zip(map(ord, "0123456789"), (29,18,19,20,21,23,22,26,28,25)))
MAC_CODES.update(zip(range(0x70, 0x84), (122,120,99,118,96,97,98,100,101,109,103,111,105,107,113,106,64,79,80,90)))
MAC_CODES.update({0xBA: 41, 0xBB: 24, 0xBC: 43, 0xBD: 27, 0xBE: 47,
                  0xBF: 44, 0xDB: 33, 0xDC: 42, 0xDD: 30, 0xDE: 39,
                  0x60: 82, 0x61: 83, 0x62: 84, 0x63: 85, 0x64: 86,
                  0x65: 87, 0x66: 88, 0x67: 89, 0x68: 91, 0x69: 92,
                  0x6A: 67, 0x6B: 69, 0x6D: 78, 0x6E: 65, 0x6F: 75})
X_NAMES = {
    0xA2: "Control_L", 0xA3: "Control_R", 0xA0: "Shift_L", 0xA1: "Shift_R",
    0xA4: "Alt_L", 0xA5: "Alt_R", 0x5B: "Super_L", 0x5C: "Super_R",
    0x20: "space", 0x0D: "Return", 0x09: "Tab", 0x1B: "Escape",
    0x08: "BackSpace", 0x2E: "Delete", 0x2D: "Insert", 0x24: "Home",
    0x23: "End", 0x21: "Prior", 0x22: "Next", 0x25: "Left",
    0x26: "Up", 0x27: "Right", 0x28: "Down", 0xC0: "grave",
}
X_NAMES.update({code: chr(code).lower() for code in range(65, 91)})
X_NAMES.update({code: chr(code) for code in range(48, 58)})
X_NAMES.update({0x6F + i: f"F{i}" for i in range(1, 25)})
MODIFIERS = {0x11: (0xA2, 0xA3), 0x10: (0xA0, 0xA1), 0x12: (0xA4, 0xA5)}
_local = threading.local()


def validate_hotkey(name):
    codes = parse_hotkey(name)
    supported = MAC_CODES if sys.platform == "darwin" else X_NAMES
    if any(code not in supported and code not in MODIFIERS for code in codes):
        raise ValueError(f"Unsupported hotkey on this platform: {name}")
    return codes


def _display():
    if os.environ.get("XDG_SESSION_TYPE") == "wayland" or os.environ.get("WAYLAND_DISPLAY"):
        raise RuntimeError("VoxPill requires an X11 desktop session; Wayland is not supported yet.")
    if not getattr(_local, "display", None):
        from Xlib.display import Display
        _local.display = Display()
    return _local.display


def check_desktop():
    if sys.platform == "darwin":
        import ApplicationServices
        if not ApplicationServices.AXIsProcessTrusted():
            raise RuntimeError("Enable VoxPill (or your terminal) in System Settings > Privacy & Security > Accessibility, then restart.")
    else:
        _display()


def key_down(code):
    if code in MODIFIERS:
        return any(key_down(item) for item in MODIFIERS[code])
    if sys.platform == "darwin":
        import Quartz
        if code == 1:
            return bool(Quartz.CGEventSourceButtonState(Quartz.kCGEventSourceStateCombinedSessionState, 0))
        native = MAC_CODES.get(code)
        return native is not None and bool(Quartz.CGEventSourceKeyState(Quartz.kCGEventSourceStateCombinedSessionState, native))
    display = _display()
    if code == 1:
        from Xlib import X
        return bool(display.screen().root.query_pointer().mask & X.Button1Mask)
    from Xlib import XK
    name = X_NAMES.get(code)
    native = display.keysym_to_keycode(XK.string_to_keysym(name)) if name else 0
    return bool(native and display.query_keymap()[native // 8] & (1 << (native % 8)))


def foreground_target():
    if sys.platform == "darwin":
        from mac_desktop import foreground_target as capture
        return capture()
    focus = _display().get_input_focus().focus
    return getattr(focus, "id", None)


def activate_target(target):
    if sys.platform == "darwin":
        from mac_desktop import activate_target as restore
        return restore(target)
    # Never insert into a different window while a slow decode was running.
    return bool(target and foreground_target() == target)


def _keyboard():
    from pynput.keyboard import Controller
    return Controller()


def type_unicode(text):
    _keyboard().type(text)


def press_enter():
    from pynput.keyboard import Key
    keyboard = _keyboard()
    keyboard.tap(Key.enter)


def _clipboard_read():
    if sys.platform == "darwin":
        return subprocess.run(["pbpaste"], check=True, capture_output=True).stdout.decode("utf-8")
    return subprocess.run(["xclip", "-selection", "clipboard", "-o"], check=True, capture_output=True).stdout.decode("utf-8")


def _clipboard_write(text):
    command = ["pbcopy"] if sys.platform == "darwin" else ["xclip", "-selection", "clipboard"]
    subprocess.run(command, input=text.encode("utf-8"), check=True, timeout=5)


def paste_text(text, *, restore_clipboard=False):
    from pynput.keyboard import Key
    try:
        old = _clipboard_read() if restore_clipboard else None
    except (OSError, subprocess.SubprocessError):
        old = None
    try:
        _clipboard_write(text)
    except (OSError, subprocess.SubprocessError):
        type_unicode(text)
        return
    keyboard = _keyboard()
    with keyboard.pressed(Key.cmd if sys.platform == "darwin" else Key.ctrl):
        keyboard.tap("v")
    if old is not None:
        time.sleep(0.75)
        _clipboard_write(old)
