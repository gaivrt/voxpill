"""Keyboard capture dialog. Its temporary hook prevents captured app shortcuts."""

import ctypes
from ctypes import wintypes
import queue
import tkinter as tk
from tkinter import ttk, messagebox

from hotkey import HotkeyCapture, hotkey_label


def show_hotkey_dialog(current, save, stop_flag, *, smoke=False):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

    class KeyboardEvent(ctypes.Structure):
        _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                    ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("extra", ctypes.c_size_t)]

    user32.SetWindowsHookExW.argtypes = (ctypes.c_int, callback_type, wintypes.HINSTANCE, wintypes.DWORD)
    user32.SetWindowsHookExW.restype = wintypes.HANDLE
    user32.CallNextHookEx.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    user32.CallNextHookEx.restype = ctypes.c_ssize_t
    user32.UnhookWindowsHookEx.argtypes = (wintypes.HANDLE,)
    kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    root = tk.Tk()
    if smoke:
        root.withdraw()
    root.title("VoxPill · 设置快捷键")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    frame = ttk.Frame(root, padding=24)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="按下想使用的键或组合键，然后全部松开", font=("Microsoft YaHei UI", 11)).pack(anchor="w")
    ttk.Label(frame, text="例如：右 Ctrl、F8、Ctrl + Shift + 空格").pack(anchor="w", pady=(8, 12))
    display = tk.StringVar(value="正在等待按键…")
    ttk.Label(frame, textvariable=display, font=("Microsoft YaHei UI", 14)).pack(pady=12)
    ttk.Label(frame, text=f"当前：{hotkey_label(current)}").pack(anchor="w")
    ttk.Label(frame, text="录入时拦截按键；日常使用仍可能触发其他软件快捷键。\nWindows 保留的安全快捷键无法录入。").pack(anchor="w", pady=12)
    buttons = ttk.Frame(frame)
    buttons.pack(fill="x")
    events = queue.SimpleQueue()
    capture = HotkeyCapture()
    candidate = None
    armed = not smoke
    hook = None

    @callback_type
    def on_key(code, message, data):
        if code >= 0 and armed:
            event = ctypes.cast(data, ctypes.POINTER(KeyboardEvent)).contents
            if not event.flags & 0x10 and message in (0x100, 0x104, 0x101, 0x105):
                vk = event.vkCode
                if vk == 0x10:
                    vk = 0xA1 if event.scanCode == 0x36 else 0xA0
                elif vk in (0x11, 0x12):
                    vk = (0xA2 if vk == 0x11 else 0xA4) + bool(event.flags & 1)
                events.put((vk, message in (0x100, 0x104)))
                return 1
        return user32.CallNextHookEx(None, code, message, data)

    def record_again():
        nonlocal armed, capture, candidate
        capture = HotkeyCapture()
        candidate = None
        armed = True
        save_button.configure(state="disabled")
        display.set("正在等待按键…")

    def default():
        nonlocal candidate, armed
        if capture.held:
            return
        armed = False
        candidate = "ctrl_r"
        display.set(hotkey_label(candidate))
        save_button.configure(state="normal")

    def commit():
        if candidate:
            try:
                save(candidate)
            except Exception as exc:
                messagebox.showerror("无法保存快捷键", str(exc), parent=root)
                return
            root.destroy()

    def tick():
        nonlocal candidate, armed
        if stop_flag.is_set():
            root.destroy()
            return
        while not events.empty():
            vk, down = events.get()
            result = capture.feed(vk, down)
            if result:
                candidate = result
                armed = False
                display.set(hotkey_label(result))
                save_button.configure(state="normal")
        root.after(20, tick)

    ttk.Button(buttons, text="重新录入", command=record_again).pack(side="left")
    ttk.Button(buttons, text="恢复右 Ctrl", command=default).pack(side="left", padx=8)
    ttk.Button(buttons, text="取消", command=root.destroy).pack(side="right")
    save_button = ttk.Button(buttons, text="保存", command=commit, state="disabled")
    save_button.pack(side="right", padx=8)
    try:
        hook = user32.SetWindowsHookExW(13, on_key, kernel32.GetModuleHandleW(None), 0)
        if not hook:
            raise ctypes.WinError(ctypes.get_last_error())
        if smoke:
            # Exercise Tcl/Tk, native hook installation, controls and save path
            # in frozen builds without intercepting the user's keyboard.
            root.after(50, default)
            root.after(100, commit)
        root.after(20, tick)
        root.mainloop()
    finally:
        if hook:
            user32.UnhookWindowsHookEx(hook)
        try:
            root.destroy()
        except tk.TclError:
            pass
