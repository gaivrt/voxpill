"""macOS equivalents of Windows focus restoration and per-user login startup."""
from dataclasses import dataclass
from pathlib import Path
import os
import plistlib
import sys
import time


@dataclass
class FocusTarget:
    pid: int
    window: object
    element: object


def _attribute(element, name):
    import ApplicationServices as AX
    error, value = AX.AXUIElementCopyAttributeValue(element, name, None)
    return value if error == 0 else None


def foreground_target():
    import AppKit
    import ApplicationServices as AX
    app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return None
    pid = app.processIdentifier()
    application = AX.AXUIElementCreateApplication(pid)
    window = _attribute(application, AX.kAXFocusedWindowAttribute)
    if window is None:
        return None
    return FocusTarget(pid, window, _attribute(application, AX.kAXFocusedUIElementAttribute))


def activate_target(target):
    import AppKit as A
    import ApplicationServices as AX
    from CoreFoundation import CFEqual
    if not isinstance(target, FocusTarget):
        return False
    app = A.NSRunningApplication.runningApplicationWithProcessIdentifier_(target.pid)
    if app is None or app.isTerminated():
        return False
    if AX.AXUIElementPerformAction(target.window, AX.kAXRaiseAction) != 0:
        return False
    AX.AXUIElementSetAttributeValue(target.window, AX.kAXMainAttribute, True)
    if not app.activateWithOptions_(A.NSApplicationActivateIgnoringOtherApps):
        return False
    for _ in range(30):
        current = foreground_target()
        if current and current.pid == target.pid and CFEqual(current.window, target.window):
            if target.element is not None:
                AX.AXUIElementSetAttributeValue(target.element, AX.kAXFocusedAttribute, True)
            return True
        time.sleep(0.01)
    return False


def input_point():
    """Center of the frontmost application's window, converted to Cocoa coords."""
    import AppKit as A
    import Quartz as Q
    app = A.NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return None
    windows = Q.CGWindowListCopyWindowInfo(Q.kCGWindowListOptionOnScreenOnly, Q.kCGNullWindowID) or []
    for window in windows:
        if window.get(Q.kCGWindowOwnerPID) == app.processIdentifier() and window.get(Q.kCGWindowLayer) == 0:
            bounds = window.get(Q.kCGWindowBounds, {})
            if {"X", "Y", "Width", "Height"}.issubset(bounds):
                top = A.NSScreen.screens()[0].frame().size.height
                return (bounds["X"] + bounds["Width"] / 2, top - bounds["Y"] - bounds["Height"] / 2)
    return None


def login_path():
    return Path.home() / "Library/LaunchAgents/io.github.gaivrt.voxpill.plist"


def login_enabled():
    return login_path().exists()


def set_login_enabled(enabled):
    path = login_path()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    if not getattr(sys, "frozen", False):
        raise RuntimeError("请先将 VoxPill.app 放入 Applications，再启用登录启动。")
    executable = Path(sys.executable).resolve()
    if "AppTranslocation" in executable.parts:
        raise RuntimeError("请先将 VoxPill.app 移入 Applications，再启用登录启动。")
    path.parent.mkdir(parents=True, exist_ok=True)
    content = plistlib.dumps({"Label": "io.github.gaivrt.voxpill", "ProgramArguments": [str(executable)],
                             "RunAtLoad": True, "ProcessType": "Interactive"})
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)
