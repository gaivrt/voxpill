"""Native panel implementations; imported only inside the subtitle helper."""
import math
import subprocess
import time


def caption(state):
    if state.text:
        return state.text
    return "正在识别…" if state.status == "finalizing" else "正在聆听…"


def tail(text, measure, width):
    if measure(text) <= width:
        return text
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if measure("…" + text[-mid:]) <= width:
            low = mid
        else:
            high = mid - 1
    return "…" + text[-low:] if low else "…"


class X11Panel:
    def __init__(self, theme):
        import tkinter as tk
        from tkinter import font
        from Xlib.display import Display
        from Xlib import X, Xutil
        from Xlib.ext import shape
        self.tk, self.X, self.shape = tk, X, shape
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(takefocus=False)
        self.display = Display()
        self.dark = theme != "light"
        if theme == "auto":
            try:
                result = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                                        capture_output=True, text=True, timeout=1)
                self.dark = "prefer-light" not in result.stdout
            except (OSError, subprocess.TimeoutExpired):
                pass
        self.bg, self.fg = ("#101112", "#f5f3ed") if self.dark else ("#faf9f5", "#252525")
        self.canvas = tk.Canvas(self.root, bg=self.bg, highlightthickness=0, takefocus=False)
        self.canvas.pack(fill="both", expand=True)
        self.font = font.Font(family="Noto Sans CJK SC", size=12)
        self.root.update_idletasks()
        self.window = self.display.create_resource_object("window", self.root.winfo_id()).query_tree().parent
        self.window.set_wm_hints(flags=Xutil.InputHint, input=0)
        if not self.display.has_extension("SHAPE"):
            raise RuntimeError("X11 SHAPE extension is required for click-through subtitles")
        self.window.shape_rectangles(shape.SO.Set, shape.SK.Input, X.Unsorted, 0, 0, [])
        self.display.sync()
        self.visible = False
        self.session = None
        self.width = 180
        self.bounds = (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())

    def _monitor(self):
        # Xinerama includes negative origins and different-sized monitors.
        pointer = self.display.screen().root.query_pointer()
        try:
            from Xlib.ext import xinerama
            screens = self.display.xinerama_query_screens().screens
            for screen in screens:
                if screen.x <= pointer.root_x < screen.x + screen.width and screen.y <= pointer.root_y < screen.y + screen.height:
                    return screen.x, screen.y, screen.width, screen.height
        except Exception:
            pass
        return (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())

    def render(self, state):
        if state.status == "hidden":
            if self.visible:
                self.root.withdraw()
            self.visible = False
            return
        if state.session != self.session:
            self.session, self.bounds, self.width = state.session, self._monitor(), 180
        bx, by, bw, bh = self.bounds
        text = caption(state)
        height = max(48, self.font.metrics("linespace") + 24)
        self.width = min(max(self.width, self.font.measure(text) + 64), min(600, bw - 32))
        width = self.width
        x, y = bx + (bw - width) // 2, by + bh - height - 64
        # Tk negative geometry offsets are relative to the far edge; move via X.
        self.root.geometry(f"{width}x{height}")
        self.root.update_idletasks()
        self.window.configure(x=x, y=y, width=width, height=height, stack_mode=self.X.Above)
        radius = height // 2
        rectangles = []
        for row in range(height):
            dy = abs(row + 0.5 - radius)
            inset = int(radius - math.sqrt(max(0, radius * radius - dy * dy)))
            rectangles.append((inset, row, width - 2 * inset, 1))
        self.window.shape_rectangles(self.shape.SO.Set, self.shape.SK.Bounding, self.X.Unsorted, 0, 0, rectangles)
        self.canvas.delete("all")
        pulse = 3 + (1 + math.sin(time.monotonic() * 7)) * 1.5 if state.status == "listening" else 4
        self.canvas.create_oval(22-pulse, height/2-pulse, 22+pulse, height/2+pulse, fill=self.fg, outline="")
        self.canvas.create_text(40, height/2, text=tail(text, self.font.measure, width-56),
                                anchor="w", fill=self.fg, font=self.font)
        if not self.visible:
            self.root.deiconify()
            self.visible = True
        self.display.flush()

    def after(self, ms, callback):
        self.root.after(ms, callback)

    def run(self):
        self.root.mainloop()

    def close(self):
        self.root.destroy()
        self.display.close()

    def prepare_focus_test(self):
        self.sentinel = self.tk.Toplevel(self.root)
        self.sentinel.title("VoxPill focus test")
        self.sentinel.geometry("240x80+30+30")
        entry = self.tk.Entry(self.sentinel)
        entry.pack()
        self.sentinel.update()
        entry.focus_force()
        self.sentinel.update()
        self.focus_before = self.display.get_input_focus().focus.id

    def assert_focus_unchanged(self):
        self.display.sync()
        assert self.display.get_input_focus().focus.id == self.focus_before, "Subtitle stole keyboard focus"
        assert not self.window.shape_get_rectangles(self.shape.SK.Input).rectangles, "Subtitle intercepts mouse clicks"

    def snapshot(self, path):
        from PIL import ImageGrab
        self.root.update_idletasks()
        self.display.sync()
        geometry = self.window.get_geometry()
        ImageGrab.grab(bbox=(geometry.x, geometry.y, geometry.x+geometry.width, geometry.y+geometry.height),
                       xdisplay=self.display.get_display_name()).save(path)


class MacPanel:
    def __init__(self, theme):
        import AppKit as A
        from PyObjCTools import AppHelper
        self.A, self.helper = A, AppHelper
        self.app = A.NSApplication.sharedApplication()
        self.app.setActivationPolicy_(A.NSApplicationActivationPolicyAccessory)

        class SubtitlePanel(A.NSPanel):
            def canBecomeKeyWindow(self):
                return False

            def canBecomeMainWindow(self):
                return False

        self.panel = SubtitlePanel.alloc().initWithContentRect_styleMask_backing_defer_(
            A.NSMakeRect(0, 0, 180, 48), A.NSWindowStyleMaskBorderless | A.NSWindowStyleMaskNonactivatingPanel,
            A.NSBackingStoreBuffered, False)
        self.panel.setLevel_(A.NSFloatingWindowLevel)
        self.panel.setOpaque_(False)
        self.panel.setBackgroundColor_(A.NSColor.clearColor())
        self.panel.setHasShadow_(True)
        self.panel.setIgnoresMouseEvents_(True)
        self.panel.setHidesOnDeactivate_(False)
        self.panel.setCollectionBehavior_(A.NSWindowCollectionBehaviorCanJoinAllSpaces | A.NSWindowCollectionBehaviorFullScreenAuxiliary)
        self.view = A.NSView.alloc().initWithFrame_(A.NSMakeRect(0, 0, 180, 48))
        self.view.setWantsLayer_(True)
        self.view.layer().setCornerRadius_(24)
        self.panel.setContentView_(self.view)
        self.label = A.NSTextField.labelWithString_("")
        self.label.setFont_(A.NSFont.systemFontOfSize_(15))
        self.label.setLineBreakMode_(A.NSLineBreakByTruncatingHead)
        self.label.setMaximumNumberOfLines_(1)
        self.view.addSubview_(self.label)
        self.dot = A.NSView.alloc().initWithFrame_(A.NSMakeRect(18, 20, 8, 8))
        self.dot.setWantsLayer_(True)
        self.dot.layer().setCornerRadius_(4)
        self.view.addSubview_(self.dot)
        self.theme, self.session, self.width = theme, None, 180
        self.visible = False
        self.screen = A.NSScreen.mainScreen()

    def render(self, state):
        A = self.A
        if state.status == "hidden":
            if self.visible:
                self.panel.orderOut_(None)
            self.visible = False
            return
        if state.session != self.session:
            self.session, self.width = state.session, 180
            point = A.NSEvent.mouseLocation()
            self.screen = next((s for s in A.NSScreen.screens() if A.NSPointInRect(point, s.frame())), A.NSScreen.mainScreen())
            appearance = self.app.effectiveAppearance().bestMatchFromAppearancesWithNames_([A.NSAppearanceNameAqua, A.NSAppearanceNameDarkAqua])
            dark = self.theme == "dark" or (self.theme == "auto" and appearance == A.NSAppearanceNameDarkAqua)
            bg = A.NSColor.colorWithWhite_alpha_(0.055 if dark else 0.98, 0.97)
            fg = A.NSColor.colorWithWhite_alpha_(0.96 if dark else 0.12, 1)
            self.view.layer().setBackgroundColor_(bg.CGColor())
            self.label.setTextColor_(fg)
            self.dot.layer().setBackgroundColor_(fg.CGColor())
        text = caption(state)
        self.label.setStringValue_(text)
        work = self.screen.visibleFrame()
        measured = self.label.attributedStringValue().size().width
        self.width = min(max(self.width, measured + 64), min(600, work.size.width - 32))
        width = self.width
        self.panel.setFrame_display_(A.NSMakeRect(work.origin.x + (work.size.width-width)/2, work.origin.y+22, width, 48), True)
        self.label.setFrame_(A.NSMakeRect(40, 13, width-56, 23))
        self.dot.setAlphaValue_(0.65 + 0.35 * math.sin(time.monotonic()*7) if state.status == "listening" else 1)
        if not self.visible:
            self.panel.orderFrontRegardless()
            self.visible = True

    def after(self, ms, callback):
        self.helper.callLater(ms / 1000, callback)

    def run(self):
        self.app.run()

    def close(self):
        self.panel.orderOut_(None)
        # stopEventLoop terminates the process, hiding failed smoke assertions.
        # Return from run() so Python can propagate errors and clean up pipes.
        self.app.stop_(None)
        event = self.A.NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
            self.A.NSEventTypeApplicationDefined, (0, 0), 0, 0, 0, None, 0, 0, 0)
        self.app.postEvent_atStart_(event, True)

    def prepare_focus_test(self):
        A = self.A
        self.sentinel = A.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            A.NSMakeRect(40, 400, 240, 80), A.NSWindowStyleMaskTitled, A.NSBackingStoreBuffered, False)
        self.sentinel.setTitle_("VoxPill focus test")
        self.sentinel.makeKeyAndOrderFront_(None)
        self.app.activateIgnoringOtherApps_(True)

    def assert_focus_unchanged(self):
        assert self.app.keyWindow() == self.sentinel, "Subtitle stole keyboard focus"
        assert not self.panel.canBecomeKeyWindow() and not self.panel.canBecomeMainWindow()
        assert self.panel.ignoresMouseEvents(), "Subtitle intercepts mouse clicks"

    def snapshot(self, path):
        rep = self.view.bitmapImageRepForCachingDisplayInRect_(self.view.bounds())
        self.view.cacheDisplayInRect_toBitmapImageRep_(self.view.bounds(), rep)
        data = rep.representationUsingType_properties_(self.A.NSBitmapImageFileTypePNG, {})
        assert data.writeToFile_atomically_(str(path), True)
