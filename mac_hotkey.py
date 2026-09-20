"""Press/release hotkey capture with temporary macOS event suppression."""
import queue
import tkinter as tk
from tkinter import ttk, messagebox

from desktop_unix import MAC_CODES
from hotkey import HotkeyCapture, hotkey_label


class Capture:
    def __init__(self):
        self.gesture = HotkeyCapture()
        self.codes = {native: code for code, native in MAC_CODES.items()}

    def feed(self, native, down):
        code = self.codes.get(native)
        return self.gesture.feed(code, down) if code is not None else None


def show_dialog(current, save, stop_flag, *, smoke=False):
    root = tk.Tk()
    root.title("VoxPill · 设置快捷键")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    frame = ttk.Frame(root, padding=24)
    frame.pack()
    ttk.Label(frame, text="按下想使用的键或组合键，然后全部松开").pack(anchor="w")
    ttk.Label(frame, text="例如：右 Control、F8、Control + Shift + 空格").pack(anchor="w", pady=8)
    display = tk.StringVar(value="正在等待按键…")
    ttk.Label(frame, textvariable=display, font=("TkDefaultFont", 16)).pack(pady=12)
    ttk.Label(frame, text=f"当前：{hotkey_label(current)}").pack(anchor="w")
    ttk.Label(frame, text="录入时拦截按键；日常使用仍可能触发其他软件快捷键。\nmacOS 保留快捷键、Fn 和部分媒体键可能无法录入。").pack(anchor="w", pady=10)
    buttons = ttk.Frame(frame)
    buttons.pack(fill="x")
    events = queue.SimpleQueue()
    capture = Capture()
    candidate = None
    armed = True
    listener = None

    def again():
        nonlocal capture, candidate, armed
        capture, candidate, armed = Capture(), None, True
        display.set("正在等待按键…")
        button.configure(state="disabled")

    def default():
        nonlocal candidate, armed
        if capture.gesture.held:
            return
        candidate, armed = "ctrl_r", False
        display.set(hotkey_label(candidate))
        button.configure(state="normal")

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
        if listener is not None and not listener.is_alive():
            messagebox.showerror("无法监听按键", "请检查辅助功能与输入监控权限，然后重新打开设置。", parent=root)
            root.destroy()
            return
        while not events.empty():
            native, down = events.get()
            result = capture.feed(native, down)
            if result:
                candidate, armed = result, False
                display.set(hotkey_label(result))
                button.configure(state="normal")
        root.after(20, tick)

    ttk.Button(buttons, text="重新录入", command=again).pack(side="left")
    ttk.Button(buttons, text="恢复右 Control", command=default).pack(side="left", padx=8)
    ttk.Button(buttons, text="取消", command=root.destroy).pack(side="right")
    button = ttk.Button(buttons, text="保存", command=commit, state="disabled")
    button.pack(side="right", padx=8)
    try:
        if smoke:
            root.withdraw()
            root.after(50, lambda: (events.put((62, True)), events.put((62, False))))
            root.after(150, commit)
        else:
            from desktop_unix import check_desktop
            check_desktop()
            import Quartz as Q
            from pynput.keyboard import Listener

            def intercept(event_type, event):
                if not armed:
                    return event
                native = Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventKeycode)
                if event_type in (Q.kCGEventKeyDown, Q.kCGEventKeyUp):
                    events.put((native, event_type == Q.kCGEventKeyDown))
                elif event_type == Q.kCGEventFlagsChanged:
                    down = Q.CGEventSourceKeyState(Q.kCGEventSourceStateHIDSystemState, native)
                    events.put((native, bool(down)))
                return None

            listener = Listener(darwin_intercept=intercept)
            listener.start()
            listener.wait()
            if not listener.is_alive():
                raise RuntimeError("无法监听按键，请检查辅助功能与输入监控权限。")
        root.after(20, tick)
        root.mainloop()
    finally:
        if listener:
            listener.stop()
            listener.join(timeout=2)
        try:
            root.destroy()
        except tk.TclError:
            pass
