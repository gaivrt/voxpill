"""把文本注入当前焦点窗口。两条路径：

- type_unicode：逐字符 SendInput + KEYEVENTF_UNICODE。通用，但微信等用 IME/自绘
  输入框的应用会把合成的 keyup 也当一次输入 → 标点/字符重复。
- paste_text：写剪贴板 + Ctrl+V，完全绕过逐字符键盘事件，所有应用表现一致（推荐）。
  默认保留本次文本，避免繁忙应用延迟读取时粘到已经恢复的旧剪贴板。

复制自 Buddy companion 的 inject.py 并扩展，保持 VoxPill 自包含。
"""
import ctypes
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

INPUT_KEYBOARD    = 1
KEYEVENTF_KEYUP   = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_RETURN  = 0x0D
VK_CONTROL = 0x11
VK_V       = 0x56

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR))


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR))


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD))


class _INPUTUNION(ctypes.Union):
    _fields_ = (("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT))


class INPUT(ctypes.Structure):
    _fields_ = (("type", wintypes.DWORD), ("u", _INPUTUNION))


# Explicit signature so the array pointer isn't truncated on 64-bit Python, and
# so cbSize == sizeof(INPUT) (== 40 on x64) — both else cause WinError 87.
user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT


def _send(events):
    n = len(events)
    if not n:
        return 0
    arr = (INPUT * n)(*events)
    sent = user32.SendInput(n, arr, ctypes.sizeof(INPUT))
    if sent != n:
        raise ctypes.WinError(ctypes.get_last_error())
    return sent


def _unicode_event(code_unit, keyup):
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if keyup else 0)
    return INPUT(INPUT_KEYBOARD, _INPUTUNION(ki=KEYBDINPUT(0, code_unit, flags, 0, 0)))


def _vk_event(vk, keyup):
    flags = KEYEVENTF_KEYUP if keyup else 0
    return INPUT(INPUT_KEYBOARD, _INPUTUNION(ki=KEYBDINPUT(vk, 0, flags, 0, 0)))


def _utf16_units(ch):
    enc = ch.encode("utf-16-le")
    return [enc[i] | (enc[i + 1] << 8) for i in range(0, len(enc), 2)]


def type_unicode(text):
    """Type arbitrary Unicode text into the focused window, char by char."""
    events = []
    for ch in text:
        for unit in _utf16_units(ch):
            events.append(_unicode_event(unit, keyup=False))
            events.append(_unicode_event(unit, keyup=True))
    _send(events)


def press_enter():
    _send([_vk_event(VK_RETURN, keyup=False), _vk_event(VK_RETURN, keyup=True)])


# ── 剪贴板 paste 路径 ─────────────────────────────────────────────────────────
# 64 位下句柄必须声明为指针宽度，否则被截断 → 崩溃/拿到错误句柄。
CF_UNICODETEXT = 13
GMEM_MOVEABLE  = 0x0002

kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = (ctypes.c_void_p,)
kernel32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
kernel32.GlobalFree.argtypes = (ctypes.c_void_p,)
user32.OpenClipboard.argtypes = (wintypes.HWND,)
user32.GetClipboardData.restype = ctypes.c_void_p
user32.GetClipboardData.argtypes = (wintypes.UINT,)
user32.SetClipboardData.restype = ctypes.c_void_p
user32.SetClipboardData.argtypes = (wintypes.UINT, ctypes.c_void_p)


def _get_clipboard_text():
    """读剪贴板里的 unicode 文本；没有文本则返回 None。"""
    if not user32.OpenClipboard(None):
        return None
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        p = kernel32.GlobalLock(h)
        if not p:
            return None
        try:
            return ctypes.c_wchar_p(p).value
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def _set_clipboard_text(text):
    """把 text 放进剪贴板。成功返回 True。"""
    data = text.encode("utf-16-le") + b"\x00\x00"
    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h:
            return False
        p = kernel32.GlobalLock(h)
        if not p:                    # lock 失败：句柄还归我们，释放后回退
            kernel32.GlobalFree(h)
            return False
        ctypes.memmove(p, data, len(data))
        kernel32.GlobalUnlock(h)
        if not user32.SetClipboardData(CF_UNICODETEXT, h):
            kernel32.GlobalFree(h)   # 失败时句柄还归我们，要释放；成功后系统接管
            return False
        return True
    finally:
        user32.CloseClipboard()


def paste_text(text, *, restore_clipboard=False):
    """通过剪贴板 + Ctrl+V 注入，绕过逐字符键盘事件（对微信等 IME 应用更稳）。

    剪贴板失败时回退到逐字符注入。默认不恢复旧剪贴板：Ctrl+V 是异步
    键盘消息，目标应用繁忙时可能在函数返回很久以后才读取剪贴板；过早
    恢复会让它粘贴出旧内容。若显式要求恢复，则保守等待后再恢复文本。
    """
    old = _get_clipboard_text() if restore_clipboard else None
    if not _set_clipboard_text(text):
        type_unicode(text)           # 剪贴板拿不到 → 退回逐字符
        return
    _send([_vk_event(VK_CONTROL, False), _vk_event(VK_V, False),
           _vk_event(VK_V, True), _vk_event(VK_CONTROL, True)])
    if restore_clipboard and old is not None:
        time.sleep(0.75)
        _set_clipboard_text(old)
