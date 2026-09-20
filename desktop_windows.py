"""Native Windows keyboard and focus operations."""
import ctypes
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.GetForegroundWindow.argtypes = ()
user32.GetForegroundWindow.restype = wintypes.HWND
user32.IsWindow.argtypes = (wintypes.HWND,)
user32.IsWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.SetForegroundWindow.restype = wintypes.BOOL


def key_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)

def foreground_target():
    return int(user32.GetForegroundWindow() or 0)

def activate_target(hwnd: int) -> bool:
    """Restore the window focused when recording began before injecting final text."""
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    if user32.GetForegroundWindow() == hwnd:
        return True
    if not user32.SetForegroundWindow(hwnd):
        return False
    for _ in range(10):
        if user32.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.01)
    return False

