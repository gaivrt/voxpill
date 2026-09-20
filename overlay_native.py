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
                if result.returncode == 0:
                    self.dark = "dark" in result.stdout
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
        self.panel.setHasShadow_(False)
        self.panel.setIgnoresMouseEvents_(True)
        self.panel.setHidesOnDeactivate_(False)
        self.panel.setCollectionBehavior_(A.NSWindowCollectionBehaviorCanJoinAllSpaces | A.NSWindowCollectionBehaviorFullScreenAuxiliary)
        self.view = A.NSImageView.alloc().initWithFrame_(A.NSMakeRect(0, 0, 36, 36))
        self.view.setImageScaling_(A.NSImageScaleAxesIndependently)
        self.panel.setContentView_(self.view)
        self.theme, self.session = theme, None
        self.visible = False
        self.screen = A.NSScreen.mainScreen()
        self.recorded_frames = []
        self.recorded_geometry = []
        self.next_capture = 0

    def _target_geometry(self, layout):
        work = self.screen.visibleFrame()
        scale = self.scale
        width, height = layout.width * scale, layout.height * scale
        top = self.screen.frame().origin.y + self.screen.frame().size.height
        return ((work.origin.x + work.size.width / 2) * scale - width / 2,
                (top - work.origin.y - 22) * scale - height, width, height)

    def render(self, state):
        import io
        from Foundation import NSData
        A = self.A
        if state.status == "hidden":
            if self.visible:
                self.panel.orderOut_(None)
            self.visible = False
            return
        if state.session != self.session:
            self.session = state.session
            # Prefer the active input window's monitor; fall back to pointer.
            from mac_desktop import input_point
            point = input_point() or A.NSEvent.mouseLocation()
            self.screen = next((s for s in A.NSScreen.screens() if A.NSPointInRect(point, s.frame())), A.NSScreen.mainScreen())
            self.scale = float(self.screen.backingScaleFactor())
            state._scale = self.scale
            state._font = None
            appearance = self.app.effectiveAppearance().bestMatchFromAppearancesWithNames_([A.NSAppearanceNameAqua, A.NSAppearanceNameDarkAqua])
            state._dark_surface = self.theme == "dark" or (self.theme == "auto" and appearance == A.NSAppearanceNameDarkAqua)
            from overlay import OverlayLayout
            x, y, w, h = self._target_geometry(OverlayLayout(36, 36, 0))
            state._state["geometry"] = [x, y - 6 * self.scale, w, h]
            state._state["velocity"] = [0.0] * 4
        result = state._advance_frame(time.monotonic(), self._target_geometry)
        if result is None:
            self.panel.orderOut_(None)
            self.visible = False
            return
        frame, x, y, alpha = result
        stream = io.BytesIO()
        frame.save(stream, format="PNG", compress_level=1)
        raw = stream.getvalue()
        image = A.NSImage.alloc().initWithData_(NSData.dataWithBytes_length_(raw, len(raw)))
        self.view.setImage_(image)
        top = self.screen.frame().origin.y + self.screen.frame().size.height
        self.panel.setFrame_display_(A.NSMakeRect(x/self.scale, top-(y+frame.height)/self.scale,
                                                frame.width/self.scale, frame.height/self.scale), True)
        self.panel.setAlphaValue_(alpha / 255)
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

    def record_frame(self, elapsed, state):
        if elapsed < self.next_capture:
            return
        self.next_capture = elapsed + 1 / 30
        import io
        from PIL import Image
        background = (35, 37, 40, 255) if self.theme == "dark" else (226, 228, 230, 255)
        canvas = Image.new("RGBA", (960, 160), background)
        if self.visible:
            rep = self.view.bitmapImageRepForCachingDisplayInRect_(self.view.bounds())
            self.view.cacheDisplayInRect_toBitmapImageRep_(self.view.bounds(), rep)
            data = rep.representationUsingType_properties_(self.A.NSBitmapImageFileTypePNG, {})
            image = Image.open(io.BytesIO(bytes(data))).convert("RGBA")
            frame = self.panel.frame()
            width, height = round(frame.size.width * 2), round(frame.size.height * 2)
            image = image.resize((max(1, width), max(1, height)), Image.Resampling.LANCZOS)
            image.putalpha(image.getchannel("A").point(lambda a: round(a*self.panel.alphaValue())))
            work = self.screen.visibleFrame()
            left = work.origin.x + work.size.width / 2 - 240
            bottom = work.origin.y + 6
            canvas.alpha_composite(image, (round((frame.origin.x-left)*2), round((bottom+80-frame.origin.y-frame.size.height)*2)))
            self.recorded_geometry.append({"time": elapsed, "width": frame.size.width,
                                           "height": frame.size.height, "alpha": self.panel.alphaValue(), "status": state.status})
        self.recorded_frames.append(canvas.convert("RGB"))

    def save_recording(self, directory):
        import json
        if self.recorded_frames:
            self.recorded_frames[0].save(directory / "animation.gif", save_all=True,
                append_images=self.recorded_frames[1:], duration=40, loop=0, disposal=2)
            (directory / "animation-timeline.json").write_text(json.dumps(self.recorded_geometry, indent=2))
