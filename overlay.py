"""Native, no-focus, per-pixel transcript overlay for Windows."""

from __future__ import annotations

import ctypes
import math
import os
import queue
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass


MAX_WIDTH = 440
CHAR_REVEAL_SECONDS = 0.045


def enable_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SetProcessDpiAwarenessContext.argtypes = (ctypes.c_void_p,)
        user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass


enable_dpi_awareness()


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def ease_out_quint(value: float) -> float:
    value = clamp01(value)
    return 1.0 - (1.0 - value) ** 5


def ease_in_out_cubic(value: float) -> float:
    value = clamp01(value)
    return 4 * value**3 if value < 0.5 else 1 - (-2 * value + 2) ** 3 / 2


def lerp(start: float, end: float, amount: float) -> float:
    return start + (end - start) * amount


def visual_units(text: str) -> float:
    """Approximate text width while treating CJK as full-width glyphs."""
    return sum(2.0 if ord(ch) > 0xFF else 1.0 for ch in text)


def display_text(text: str) -> str:
    """Normalize transcript whitespace; pixel fitting happens in the renderer."""
    return " ".join(text.split())


def common_prefix(left: str, right: str) -> str:
    """Return the stable prefix shared by two successive ASR hypotheses."""
    end = min(len(left), len(right))
    index = 0
    while index < end and left[index] == right[index]:
        index += 1
    return left[:index]


def reconcile_partial_text(current: str, target: str) -> str:
    """Keep stable visible text and roll back only the revised suffix."""
    return current if target.startswith(current) else common_prefix(current, target)


def reveal_next_character(current: str, target: str) -> str:
    """Advance a reconciled partial by one Unicode code point."""
    if current == target:
        return current
    if not target.startswith(current):
        current = common_prefix(current, target)
    return target[: len(current) + 1]


def adaptive_width(text: str) -> int:
    if not text:
        return 36
    return int(max(118, min(MAX_WIDTH, 46 + visual_units(text) * 7.1)))


@dataclass(frozen=True)
class OverlayLayout:
    width: int
    height: int
    lines: int


def adaptive_layout(text: str) -> OverlayLayout:
    if not text:
        return OverlayLayout(36, 36, 0)
    return OverlayLayout(adaptive_width(text), 40, 1)


def expanded_layout(previous: OverlayLayout, text: str) -> OverlayLayout:
    """Grow an active overlay monotonically even when ASR revises a partial."""
    current = adaptive_layout(text)
    return OverlayLayout(
        max(previous.width, current.width),
        max(previous.height, current.height),
        max(previous.lines, current.lines),
    )


def system_prefers_dark() -> bool:
    """Read the Windows app theme; preserve dark mode if it is unavailable."""
    if os.name != "nt":
        return True
    try:
        import winreg

        path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            light, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return not bool(light)
    except (OSError, ImportError):
        return True


def overlay_palette(
    dark: bool,
) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int, int]]:
    """Return surface and foreground colors for the restrained two-theme UI."""
    if dark:
        return (0, 0, 0), (245, 245, 245), (200, 190, 175, 38)
    return (250, 249, 245), (58, 55, 51), (80, 75, 65, 32)


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _VARIANT_VALUE(ctypes.Union):
    _fields_ = [
        ("lVal", wintypes.LONG),
        ("llVal", ctypes.c_longlong),
        ("ptr", ctypes.c_void_p),
        ("record", ctypes.c_void_p * 2),
    ]


class VARIANT(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = [
        ("vt", wintypes.WORD),
        ("reserved1", wintypes.WORD),
        ("reserved2", wintypes.WORD),
        ("reserved3", wintypes.WORD),
        ("value", _VARIANT_VALUE),
    ]


IID_IACCESSIBLE = GUID(
    0x618736E0,
    0x3C3D,
    0x11CF,
    (ctypes.c_ubyte * 8)(0x81, 0x0C, 0x00, 0xAA, 0x00, 0x38, 0x9B, 0x71),
)
OBJID_CARET = 0xFFFFFFF8
CLSID_CUIAUTOMATION = GUID(
    0xFF48DBA4,
    0x60EF,
    0x4201,
    (ctypes.c_ubyte * 8)(0xAA, 0x87, 0x54, 0x10, 0x3E, 0xEF, 0x59, 0x4E),
)
IID_IUIAUTOMATION = GUID(
    0x30CBE57D,
    0xD9D0,
    0x452A,
    (ctypes.c_ubyte * 8)(0xAB, 0x13, 0x7A, 0xC5, 0xAC, 0x48, 0x25, 0xEE),
)
IID_IUIAUTOMATIONTEXTPATTERN2 = GUID(
    0x506A921A,
    0xFCC9,
    0x409F,
    (ctypes.c_ubyte * 8)(0xB2, 0x3B, 0x37, 0xEB, 0x74, 0x10, 0x68, 0x72),
)
UIA_TEXTPATTERN2_ID = 10024


def _vtable(pointer: ctypes.c_void_p):
    return ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents


def _release(pointer: ctypes.c_void_p) -> None:
    if pointer and pointer.value:
        ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(_vtable(pointer)[2])(pointer)


def _safe_array_values(array: ctypes.c_void_p) -> list[float]:
    if not array.value:
        return []
    oleaut32 = ctypes.OleDLL("oleaut32", use_last_error=True)
    oleaut32.SafeArrayGetLBound.argtypes = (
        ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(wintypes.LONG)
    )
    oleaut32.SafeArrayGetUBound.argtypes = (
        ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(wintypes.LONG)
    )
    oleaut32.SafeArrayAccessData.argtypes = (
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
    )
    lower, upper = wintypes.LONG(), wintypes.LONG()
    data = ctypes.c_void_p()
    values: list[float] = []
    accessed = False
    try:
        if (
            oleaut32.SafeArrayGetLBound(array, 1, ctypes.byref(lower)) >= 0
            and oleaut32.SafeArrayGetUBound(array, 1, ctypes.byref(upper)) >= 0
            and upper.value >= lower.value
            and oleaut32.SafeArrayAccessData(array, ctypes.byref(data)) >= 0
        ):
            accessed = True
            doubles = ctypes.cast(data, ctypes.POINTER(ctypes.c_double))
            values = [doubles[index] for index in range(upper.value - lower.value + 1)]
    finally:
        if accessed:
            oleaut32.SafeArrayUnaccessData(array)
        oleaut32.SafeArrayDestroy(array)
    return values


def _uia_caret() -> tuple[int, int] | None:
    """Get the focused TextPattern2 caret used by Chromium/Electron editors."""
    ole32 = ctypes.OleDLL("ole32", use_last_error=True)
    ole32.CoInitializeEx.argtypes = (ctypes.c_void_p, wintypes.DWORD)
    ole32.CoInitializeEx.restype = ctypes.c_long
    initialized = ole32.CoInitializeEx(None, 2) in (0, 1)
    automation = ctypes.c_void_p()
    element = ctypes.c_void_p()
    unknown_pattern = ctypes.c_void_p()
    pattern = ctypes.c_void_p()
    text_range = ctypes.c_void_p()
    try:
        ole32.CoCreateInstance.argtypes = (
            ctypes.POINTER(GUID),
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(GUID),
            ctypes.POINTER(ctypes.c_void_p),
        )
        ole32.CoCreateInstance.restype = ctypes.c_long
        if ole32.CoCreateInstance(
            ctypes.byref(CLSID_CUIAUTOMATION),
            None,
            1,
            ctypes.byref(IID_IUIAUTOMATION),
            ctypes.byref(automation),
        ) < 0:
            return None
        get_focused = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
        )(_vtable(automation)[8])
        if get_focused(automation, ctypes.byref(element)) < 0 or not element.value:
            return None
        get_pattern = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)
        )(_vtable(element)[16])
        if get_pattern(element, UIA_TEXTPATTERN2_ID, ctypes.byref(unknown_pattern)) < 0:
            return None
        query_interface = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,
            ctypes.POINTER(GUID),
            ctypes.POINTER(ctypes.c_void_p),
        )(_vtable(unknown_pattern)[0])
        if query_interface(
            unknown_pattern,
            ctypes.byref(IID_IUIAUTOMATIONTEXTPATTERN2),
            ctypes.byref(pattern),
        ) < 0:
            return None
        active = wintypes.BOOL()
        get_caret_range = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.BOOL),
            ctypes.POINTER(ctypes.c_void_p),
        )(_vtable(pattern)[10])
        if get_caret_range(pattern, ctypes.byref(active), ctypes.byref(text_range)) < 0:
            return None
        rectangles = ctypes.c_void_p()
        get_rectangles = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
        )(_vtable(text_range)[10])
        if get_rectangles(text_range, ctypes.byref(rectangles)) < 0:
            return None
        values = _safe_array_values(rectangles)
        if len(values) >= 4:
            left, top, _, height = values[-4:]
            return round(left), round(top + max(1.0, height))
    except Exception:
        return None
    finally:
        _release(text_range)
        _release(pattern)
        _release(unknown_pattern)
        _release(element)
        _release(automation)
        if initialized:
            ole32.CoUninitialize()
    return None


def _accessible_caret() -> tuple[int, int] | None:
    """Read the accessibility caret exposed by custom text controls."""
    try:
        oleacc = ctypes.OleDLL("oleacc", use_last_error=True)
        oleacc.AccessibleObjectFromWindow.argtypes = (
            wintypes.HWND,
            wintypes.DWORD,
            ctypes.POINTER(GUID),
            ctypes.POINTER(ctypes.c_void_p),
        )
        oleacc.AccessibleObjectFromWindow.restype = ctypes.c_long
        accessible = ctypes.c_void_p()
        result = oleacc.AccessibleObjectFromWindow(
            None, OBJID_CARET, ctypes.byref(IID_IACCESSIBLE), ctypes.byref(accessible)
        )
        if result < 0 or not accessible.value:
            return None
        vtable = ctypes.cast(
            accessible, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
        ).contents
        release = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)(vtable[2])
        acc_location = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.LONG),
            ctypes.POINTER(wintypes.LONG),
            ctypes.POINTER(wintypes.LONG),
            ctypes.POINTER(wintypes.LONG),
            VARIANT,
        )(vtable[22])
        left = wintypes.LONG()
        top = wintypes.LONG()
        width = wintypes.LONG()
        height = wintypes.LONG()
        child_self = VARIANT(vt=3, lVal=0)  # VT_I4 / CHILDID_SELF
        try:
            result = acc_location(
                accessible,
                ctypes.byref(left),
                ctypes.byref(top),
                ctypes.byref(width),
                ctypes.byref(height),
                child_self,
            )
        finally:
            release(accessible)
        if result >= 0 and width.value >= 0 and height.value >= 0:
            return left.value, top.value + max(1, height.value)
    except Exception:
        pass
    return None


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def input_anchor() -> tuple[int, int, str]:
    """Return the insertion caret; use the focused window before the mouse."""
    if os.name != "nt":
        return 0, 0, "cursor"
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.c_void_p)
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetGUIThreadInfo.argtypes = (wintypes.DWORD, ctypes.POINTER(GUITHREADINFO))
    user32.GetGUIThreadInfo.restype = wintypes.BOOL
    user32.ClientToScreen.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.POINT))
    user32.ClientToScreen.restype = wintypes.BOOL
    user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
    user32.GetCursorPos.restype = wintypes.BOOL
    foreground = user32.GetForegroundWindow()
    thread_id = user32.GetWindowThreadProcessId(foreground, None)
    info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
    if thread_id and user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)) and info.hwndCaret:
        point = wintypes.POINT(info.rcCaret.left, info.rcCaret.bottom)
        if user32.ClientToScreen(info.hwndCaret, ctypes.byref(point)):
            return point.x, point.y, "gui-caret"
    accessible = _accessible_caret()
    if accessible is not None:
        return accessible[0], accessible[1], "accessibility-caret"
    automation = _uia_caret()
    if automation is not None:
        return automation[0], automation[1], "uia-caret"
    user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    user32.GetWindowRect.restype = wintypes.BOOL
    focus = info.hwndFocus or foreground
    rect = wintypes.RECT()
    if focus and user32.GetWindowRect(focus, ctypes.byref(rect)):
        return (rect.left + rect.right) // 2, rect.bottom - 8, "focus-window"
    point = wintypes.POINT()
    if user32.GetCursorPos(ctypes.byref(point)):
        return point.x, point.y, "cursor"
    return 0, 0, "cursor"


def dpi_scale_at(x: int, y: int) -> float:
    """Return effective DPI scale for the monitor containing a screen point."""
    if os.name != "nt":
        return 1.0
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        user32.MonitorFromPoint.argtypes = (wintypes.POINT, wintypes.DWORD)
        user32.MonitorFromPoint.restype = wintypes.HANDLE
        shcore.GetDpiForMonitor.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.POINTER(wintypes.UINT),
            ctypes.POINTER(wintypes.UINT),
        )
        shcore.GetDpiForMonitor.restype = ctypes.c_long
        monitor = user32.MonitorFromPoint(wintypes.POINT(x, y), 2)
        dpi_x, dpi_y = wintypes.UINT(), wintypes.UINT()
        if monitor and shcore.GetDpiForMonitor(
            monitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)
        ) == 0:
            return max(1.0, dpi_x.value / 96.0)
    except Exception:
        pass
    try:
        user32.GetDpiForSystem.restype = wintypes.UINT
        return max(1.0, user32.GetDpiForSystem() / 96.0)
    except Exception:
        return 1.0


class LiquidGlassOverlay:
    """Native Win32 overlay whose public API never blocks ASR threads."""

    def __init__(self, say=print, theme: str = "auto"):
        self._say = say
        self._theme = theme if theme in {"auto", "light", "dark"} else "auto"
        self._dark_surface = True
        self._commands: queue.SimpleQueue[tuple[str, int, str]] = queue.SimpleQueue()
        self._state = {
            "active_id": None,
            "phase": "hidden",
            "phase_started": time.perf_counter(),
            "text": "",
            "target_text": "",
            "next_character_at": 0.0,
            "status": "listening",
            "anchor": (0, 0, "cursor"),
            "max_layout": OverlayLayout(36, 36, 0),
            "geometry": [0.0, 0.0, 36.0, 36.0],
            "velocity": [0.0, 0.0, 0.0, 0.0],
        }
        self._scale = 1.0
        self._font = None
        self._base_cache_key = None
        self._base_cache_image = None
        self._surface = None
        self._hwnd: int | None = None
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="voxpill-overlay", daemon=True
        )
        self._thread.start()
        self._ready.wait(timeout=2.0)

    def show(self, session_id: int) -> None:
        self._commands.put(("show", session_id, ""))

    def partial(self, session_id: int, text: str) -> None:
        self._commands.put(("partial", session_id, text))

    def finalizing(self, session_id: int, text: str = "") -> None:
        self._commands.put(("finalizing", session_id, text))

    def committed(self, session_id: int, text: str) -> None:
        self._commands.put(("committed", session_id, text))

    def dismiss(self, session_id: int) -> None:
        self._commands.put(("dismiss", session_id, ""))

    def close(self) -> None:
        self._commands.put(("close", -1, ""))
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=2.0)

    def _drain(self, hwnd: int, user32) -> bool:
        close = False
        while True:
            try:
                command, session_id, text = self._commands.get_nowait()
            except queue.Empty:
                break
            now = time.perf_counter()
            if command == "close":
                close = True
            elif command == "show":
                anchor = input_anchor()
                self._dark_surface = (
                    self._theme == "dark"
                    or (self._theme == "auto" and system_prefers_dark())
                )
                new_scale = dpi_scale_at(anchor[0], anchor[1])
                if abs(new_scale - self._scale) > 0.01:
                    self._scale = new_scale
                    self._font = None
                    self._base_cache_key = None
                self._base_cache_key = None
                self._state.update(
                    active_id=session_id,
                    phase="showing",
                    phase_started=now,
                    text="",
                    target_text="",
                    next_character_at=now,
                    status="listening",
                    anchor=anchor,
                    max_layout=OverlayLayout(36, 36, 0),
                )
                scale = self._scale
                target_x, target_y, _, _ = self._target_geometry(
                    user32, OverlayLayout(36, 36, 0)
                )
                self._state["geometry"] = [
                    target_x,
                    target_y - 6 * scale,
                    36 * scale,
                    36 * scale,
                ]
                self._state["velocity"] = [0.0, 0.0, 0.0, 0.0]
                user32.ShowWindow(hwnd, 4)
            elif session_id != self._state["active_id"]:
                continue
            elif command == "partial":
                target = display_text(text)
                self._state["text"] = reconcile_partial_text(
                    self._state["text"], target
                )
                self._state["target_text"] = target
                self._state["next_character_at"] = now
                self._state["status"] = "listening"
                self._state["max_layout"] = expanded_layout(
                    self._state["max_layout"], target
                )
            elif command == "finalizing":
                if text:
                    self._state["text"] = display_text(text)
                    self._state["target_text"] = self._state["text"]
                    self._state["max_layout"] = expanded_layout(
                        self._state["max_layout"], self._state["text"]
                    )
                self._state["status"] = "finalizing"
            elif command in {"committed", "dismiss"}:
                if command == "committed" and text:
                    self._state["text"] = display_text(text)
                    self._state["target_text"] = self._state["text"]
                self._state["phase"] = "exiting"
                self._state["phase_started"] = now
                self._state["status"] = command
        return close

    def _target_geometry(self, user32, layout: OverlayLayout) -> tuple[float, ...]:
        anchor_x, anchor_y, _ = self._state["anchor"]
        scale = self._scale
        width, height = layout.width * scale, layout.height * scale
        margin = 12 * scale
        work = wintypes.RECT(0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
        monitor = user32.MonitorFromPoint(wintypes.POINT(anchor_x, anchor_y), 2)
        info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            work = info.rcWork
        # Keep the entire pill centered just above the active monitor taskbar.
        x = (work.left + work.right - width) / 2
        x = max(work.left + margin, min(work.right - width - margin, x))
        y = work.bottom - height - 22 * scale
        return x, y, width, height

    def _tick(self, hwnd: int, user32, gdi32) -> None:
        if self._drain(hwnd, user32):
            user32.DestroyWindow(hwnd)
            return
        phase = self._state["phase"]
        if phase == "hidden":
            return
        now = time.perf_counter()
        if (
            self._state["status"] == "listening"
            and self._state["text"] != self._state["target_text"]
            and now >= self._state["next_character_at"]
        ):
            self._state["text"] = reveal_next_character(
                self._state["text"], self._state["target_text"]
            )
            self._state["next_character_at"] = now + CHAR_REVEAL_SECONDS
        elapsed = now - self._state["phase_started"]
        targets = self._target_geometry(user32, self._state["max_layout"])
        if phase == "showing":
            progress = ease_out_quint(elapsed / 0.26)
            alpha = int(lerp(0, 255, progress))
            if progress >= 1:
                self._state["phase"] = "visible"
        elif phase == "exiting":
            progress = ease_in_out_cubic(elapsed / 0.34)
            targets = self._target_geometry(user32, OverlayLayout(14, 14, 0))
            fade = ease_out_quint(clamp01((elapsed - 0.10) / 0.24))
            alpha = int(lerp(255, 0, fade))
            if progress >= 1:
                user32.ShowWindow(hwnd, 0)
                self._state.update(
                    active_id=None,
                    phase="hidden",
                    text="",
                    target_text="",
                    status="",
                )
                return
        else:
            alpha = 255

        geometry = self._state["geometry"]
        velocity = self._state["velocity"]
        for index, target in enumerate(targets):
            velocity[index] = (velocity[index] + (target - geometry[index]) * 0.17) * 0.70
            geometry[index] += velocity[index]
        x, y, width, height = map(round, geometry)
        minimum = max(8, round(8 * self._scale))
        width, height = max(minimum, width), max(minimum, height)
        # Show the first partial immediately instead of waiting for the width
        # spring animation to finish most of its expansion.
        reveal = 1.0 if self._state["text"] else 0.0
        if phase == "exiting":
            reveal *= 1.0 - ease_out_quint(elapsed / 0.12)
        frame = self._render_frame(width, height, x, y, now, reveal)
        self._present(hwnd, user32, gdi32, frame, x, y, alpha)

    def _load_font(self, pixels: int):
        from PIL import ImageFont

        if self._font is not None and self._font[0] == pixels:
            return self._font[1]
        for path in (
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ):
            try:
                font = ImageFont.truetype(path, pixels)
                self._font = (pixels, font)
                return font
            except Exception:
                continue
        font = ImageFont.load_default()
        self._font = (pixels, font)
        return font

    def _fit_single_line(self, text: str, draw, font, max_width: int) -> str:
        """Elide the changing prefix; never let a partial trigger line wrapping."""
        if draw.textlength(text, font=font) <= max_width:
            return text
        suffix = text
        while suffix and draw.textlength("…" + suffix, font=font) > max_width:
            suffix = suffix[1:]
        return "…" + suffix.lstrip()

    def _render_frame(
        self, width: int, height: int, x: int, y: int, now: float,
        content_alpha: float = 1.0,
    ):
        from PIL import Image, ImageDraw

        scale = self._scale
        radius = height // 2
        box = (0, 0, width - 1, height - 1)
        cache_key = (width, height, self._dark_surface)
        if cache_key != self._base_cache_key:
            base = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            mask = Image.new("L", (width, height), 0)
            ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=255)
            surface, foreground, border = overlay_palette(self._dark_surface)
            pill = Image.new("RGBA", (width, height), (*surface, 255))
            pill.putalpha(mask)
            border_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            ImageDraw.Draw(border_layer, "RGBA").rounded_rectangle(
                box,
                radius=radius,
                outline=border,
                width=max(1, round(scale)),
            )
            pill.alpha_composite(border_layer)
            base.alpha_composite(pill)
            self._base_cache_key = cache_key
            self._base_cache_image = base
        canvas = self._base_cache_image.copy()

        text = self._state["text"]
        draw = ImageDraw.Draw(canvas, "RGBA")
        # A neutral voice meter keeps the control monochrome and legible.
        bar_width = max(1, round(1.5 * scale))
        gap = max(1, round(1.15 * scale))
        _, foreground, _ = overlay_palette(self._dark_surface)
        colors = (foreground,) * 4
        total = len(colors) * bar_width + (len(colors) - 1) * gap
        cy = height // 2
        fitted = ""
        font = None
        text_left = 0
        if text:
            font = self._load_font(max(12, round(14 * scale)))
            outer_padding = round(14 * scale)
            content_gap = round(9 * scale)
            text_room = max(1, width - 2 * outer_padding - total - content_gap)
            fitted = self._fit_single_line(text, draw, font, text_room)
            text_width = draw.textlength(fitted, font=font)
            group_width = total + content_gap + text_width
            group_left = max(outer_padding, round((width - group_width) / 2))
            cx = round(group_left + total / 2)
            text_left = group_left + total + content_gap
        else:
            cx = width // 2
        start_x = round(cx - total / 2)
        speed = 8.0 if self._state["status"] == "finalizing" else 5.2
        for index, color in enumerate(colors):
            wave = math.sin(now * speed + index * 1.35)
            bar_height = round((3.0 + (wave + 1.0) * 2.1) * scale)
            left = start_x + index * (bar_width + gap)
            draw.rounded_rectangle(
                (left, cy - bar_height // 2, left + bar_width, cy + bar_height // 2),
                radius=bar_width,
                fill=(*color, 232),
            )

        if fitted and font is not None:
            text_alpha = round(238 * clamp01(content_alpha))
            color = (*foreground, text_alpha)
            draw.text(
                (text_left, height // 2),
                fitted,
                font=font,
                fill=color,
                anchor="lm",
            )
        return canvas

    def _present(self, hwnd: int, user32, gdi32, image, x: int, y: int, alpha: int) -> None:
        import numpy as np

        rgba = np.asarray(image, dtype=np.uint8)
        pixel_alpha = (
            rgba[:, :, 3:4].astype(np.uint16) * max(0, min(255, alpha)) // 255
        ).astype(np.uint8)
        rgb = ((rgba[:, :, :3].astype(np.uint16) * pixel_alpha + 127) // 255).astype(np.uint8)
        bgra = np.ascontiguousarray(np.concatenate((rgb[:, :, ::-1], pixel_alpha), axis=2))
        height, width = bgra.shape[:2]
        if self._surface is None or self._surface[0:2] != (width, height):
            self._release_surface(user32, gdi32)
            screen = user32.GetDC(None)
            memory = gdi32.CreateCompatibleDC(screen)
            header = BITMAPINFOHEADER(
                ctypes.sizeof(BITMAPINFOHEADER), width, -height, 1, 32, 0,
                width * height * 4, 0, 0, 0, 0,
            )
            info = BITMAPINFO(header, (wintypes.DWORD * 3)())
            bits = ctypes.c_void_p()
            bitmap = gdi32.CreateDIBSection(
                screen, ctypes.byref(info), 0, ctypes.byref(bits), None, 0
            )
            if not screen or not memory or not bitmap or not bits:
                if bitmap:
                    gdi32.DeleteObject(bitmap)
                if memory:
                    gdi32.DeleteDC(memory)
                if screen:
                    user32.ReleaseDC(None, screen)
                raise ctypes.WinError(ctypes.get_last_error())
            old = gdi32.SelectObject(memory, bitmap)
            self._surface = (width, height, screen, memory, bitmap, old, bits)
        _, _, screen, memory, _, _, bits = self._surface
        ctypes.memmove(bits, bgra.ctypes.data, bgra.nbytes)
        destination = wintypes.POINT(x, y)
        size = wintypes.SIZE(width, height)
        source = wintypes.POINT(0, 0)
        blend = BLENDFUNCTION(0, 0, 255, 1)
        user32.UpdateLayeredWindow(
            hwnd, screen, ctypes.byref(destination), ctypes.byref(size), memory,
            ctypes.byref(source), 0, ctypes.byref(blend), 2,
        )

    def _release_surface(self, user32, gdi32) -> None:
        if self._surface is None:
            return
        _, _, screen, memory, bitmap, old, _ = self._surface
        self._surface = None
        if memory and old:
            gdi32.SelectObject(memory, old)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memory:
            gdi32.DeleteDC(memory)
        if screen:
            user32.ReleaseDC(None, screen)

    def _run(self) -> None:
        if os.name != "nt":
            self._say("[overlay] disabled: Windows only")
            self._ready.set()
            return
        try:
            # Pay renderer import cost during application startup, never on the
            # first push-to-talk interaction.
            import numpy  # noqa: F401
            from PIL import Image, ImageDraw  # noqa: F401

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            wparam_type = ctypes.c_size_t
            lparam_type = ctypes.c_ssize_t
            wndproc_type = ctypes.WINFUNCTYPE(
                ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wparam_type, lparam_type
            )

            class WNDCLASSW(ctypes.Structure):
                _fields_ = [
                    ("style", wintypes.UINT), ("lpfnWndProc", wndproc_type),
                    ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
                ]

            kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
            kernel32.GetModuleHandleW.restype = wintypes.HMODULE
            user32.RegisterClassW.argtypes = (ctypes.POINTER(WNDCLASSW),)
            user32.RegisterClassW.restype = wintypes.ATOM
            user32.CreateWindowExW.argtypes = (
                wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p,
            )
            user32.CreateWindowExW.restype = wintypes.HWND
            user32.DefWindowProcW.argtypes = (
                wintypes.HWND, wintypes.UINT, wparam_type, lparam_type
            )
            user32.DefWindowProcW.restype = ctypes.c_ssize_t
            user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
            user32.ShowWindow.restype = wintypes.BOOL
            user32.SetWindowPos.argtypes = (
                wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, wintypes.UINT,
            )
            user32.UpdateLayeredWindow.argtypes = (
                wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                ctypes.POINTER(wintypes.SIZE), wintypes.HDC, ctypes.POINTER(wintypes.POINT),
                wintypes.COLORREF, ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD,
            )
            user32.UpdateLayeredWindow.restype = wintypes.BOOL
            user32.MonitorFromPoint.argtypes = (wintypes.POINT, wintypes.DWORD)
            user32.MonitorFromPoint.restype = wintypes.HANDLE
            user32.GetMonitorInfoW.argtypes = (
                wintypes.HANDLE, ctypes.POINTER(MONITORINFO)
            )
            user32.GetMonitorInfoW.restype = wintypes.BOOL
            user32.GetDC.argtypes = (wintypes.HWND,)
            user32.GetDC.restype = wintypes.HDC
            user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
            user32.ReleaseDC.restype = ctypes.c_int
            user32.SetTimer.argtypes = (
                wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p
            )
            user32.SetTimer.restype = ctypes.c_size_t
            user32.KillTimer.argtypes = (wintypes.HWND, ctypes.c_size_t)
            user32.KillTimer.restype = wintypes.BOOL
            user32.DestroyWindow.argtypes = (wintypes.HWND,)
            user32.DestroyWindow.restype = wintypes.BOOL
            user32.GetMessageW.argtypes = (
                ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT
            )
            user32.GetMessageW.restype = wintypes.BOOL
            user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
            user32.TranslateMessage.restype = wintypes.BOOL
            user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
            user32.DispatchMessageW.restype = ctypes.c_ssize_t
            user32.PostQuitMessage.argtypes = (ctypes.c_int,)
            user32.UnregisterClassW.argtypes = (wintypes.LPCWSTR, wintypes.HINSTANCE)
            user32.UnregisterClassW.restype = wintypes.BOOL
            try:
                user32.GetDpiForSystem.restype = wintypes.UINT
                self._scale = max(1.0, user32.GetDpiForSystem() / 96.0)
            except Exception:
                self._scale = 1.0

            gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
            gdi32.CreateCompatibleDC.restype = wintypes.HDC
            gdi32.CreateDIBSection.argtypes = (
                wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
                ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD,
            )
            gdi32.CreateDIBSection.restype = wintypes.HBITMAP
            gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
            gdi32.SelectObject.restype = wintypes.HGDIOBJ
            gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
            gdi32.DeleteObject.restype = wintypes.BOOL
            gdi32.DeleteDC.argtypes = (wintypes.HDC,)
            gdi32.DeleteDC.restype = wintypes.BOOL
            frame_timer_id = 1

            @wndproc_type
            def wndproc(hwnd, message, wparam, lparam):
                if message == 0x0113 and wparam == frame_timer_id:  # WM_TIMER
                    self._tick(hwnd, user32, gdi32)
                    return 0
                if message == 0x0010:
                    user32.DestroyWindow(hwnd)
                    return 0
                if message == 0x0002:
                    user32.KillTimer(hwnd, frame_timer_id)
                    user32.PostQuitMessage(0)
                    return 0
                return user32.DefWindowProcW(hwnd, message, wparam, lparam)

            instance = kernel32.GetModuleHandleW(None)
            class_name = f"VoxPillOverlay{os.getpid()}"
            window_class = WNDCLASSW(
                0, wndproc, 0, 0, instance, None, None, None, None, class_name
            )
            if not user32.RegisterClassW(ctypes.byref(window_class)):
                raise ctypes.WinError(ctypes.get_last_error())
            ex_style = 0x00000008 | 0x00080000 | 0x00000020 | 0x08000000 | 0x00000080
            hwnd = user32.CreateWindowExW(
                ex_style, class_name, "VoxPill", 0x80000000,
                0, 0, round(MAX_WIDTH * self._scale), round(68 * self._scale),
                None, None, instance, None,
            )
            if not hwnd:
                raise ctypes.WinError(ctypes.get_last_error())
            self._hwnd = hwnd
            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
            if not user32.SetTimer(hwnd, frame_timer_id, 16, None):
                raise ctypes.WinError(ctypes.get_last_error())
            self._ready.set()
            message = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
            self._release_surface(user32, gdi32)
            user32.UnregisterClassW(class_name, instance)
            self._hwnd = None
        except Exception as exc:
            self._ready.set()
            self._say(f"[overlay] disabled: {type(exc).__name__}: {exc}")


def _demo() -> None:
    overlay = LiquidGlassOverlay()
    overlay.show(1)
    samples = [
        "今天天气不错",
        "今天天气不错，我准备测试 streaming partial",
        "今天天气不错，我准备测试 streaming partial 的单行浮窗，超长文字会稳定地从左侧省略。",
    ]
    for sample in samples:
        time.sleep(0.9)
        overlay.partial(1, sample)
    time.sleep(1.0)
    overlay.finalizing(1, samples[-1])
    time.sleep(0.35)
    overlay.committed(1, samples[-1])
    time.sleep(0.8)
    overlay.close()


if __name__ == "__main__":
    _demo()
