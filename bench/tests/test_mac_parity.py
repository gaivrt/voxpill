import json
from pathlib import Path
import plistlib
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from overlay_unix import AnimatedSubtitleState
from mac_hotkey import Capture
import mac_desktop


class MacParityTest(unittest.TestCase):
    def test_every_frame_matches_published_windows_motion(self):
        rows = json.loads((Path(__file__).parents[1] / "fixtures/windows-overlay-motion.json").read_text(encoding="utf-8"))["frames"]
        state = AnimatedSubtitleState()
        state._render_frame = lambda w, h, *args: (w, h)
        def geometry(layout):
            return (1920-layout.width)/2, 1080-layout.height-22, layout.width, layout.height
        for row in rows:
            now = row["frame"] / 60
            if row["event"]:
                state.apply(*row["event"], now)
                if row["event"][0] == "show":
                    x, y, w, h = geometry(state._state["max_layout"])
                    state._state["geometry"] = [x, y-6, w, h]
                    state._state["velocity"] = [0.] * 4
            result = state._advance_frame(now, geometry)
            if result is None:
                self.assertIsNone(row["result"], row["frame"])
            else:
                frame, x, y, alpha = result
                actual = dict(width=frame[0], height=frame[1], x=x, y=y, alpha=alpha,
                              text=state.text, phase=state._state["phase"])
                self.assertEqual(actual, row["result"], row["frame"])

    def test_mac_capture_chord_repeats_and_side_specific_modifiers(self):
        capture = Capture()
        for key in (62, 56, 49, 49):
            self.assertIsNone(capture.feed(key, True))
        self.assertIsNone(capture.feed(49, False))
        self.assertIsNone(capture.feed(56, False))
        self.assertEqual(capture.feed(62, False), "shift_l+ctrl_r+space")
        self.assertIsNone(capture.feed(255, True))

    def test_login_file_is_per_user_atomic_and_reversible(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "LaunchAgents/io.github.gaivrt.voxpill.plist"
            with patch.object(mac_desktop, "login_path", return_value=path), patch.object(mac_desktop.sys, "frozen", True, create=True):
                mac_desktop.set_login_enabled(True)
                data = plistlib.loads(path.read_bytes())
                self.assertTrue(data["RunAtLoad"])
                self.assertEqual(data["ProgramArguments"], [str(Path(mac_desktop.sys.executable).resolve())])
                self.assertTrue(mac_desktop.login_enabled())
                mac_desktop.set_login_enabled(False)
                self.assertFalse(path.exists())

    def test_restore_original_window_and_reject_wrong_window(self):
        target = mac_desktop.FocusTarget(12, "window1", "field1")
        app = SimpleNamespace(isTerminated=lambda: False, activateWithOptions_=lambda options: True)
        cocoa = SimpleNamespace(NSApplicationActivateIgnoringOtherApps=2,
            NSRunningApplication=SimpleNamespace(runningApplicationWithProcessIdentifier_=lambda pid: app))
        calls = []
        ax = SimpleNamespace(kAXRaiseAction="raise", kAXMainAttribute="main", kAXFocusedAttribute="focus",
            AXUIElementPerformAction=lambda window, action: 0,
            AXUIElementSetAttributeValue=lambda *args: calls.append(args))
        with patch.dict("sys.modules", AppKit=cocoa, ApplicationServices=ax, CoreFoundation=SimpleNamespace(CFEqual=lambda a,b:a==b)), patch.object(mac_desktop.time, "sleep"), patch.object(mac_desktop, "foreground_target", return_value=target) as foreground:
            self.assertTrue(mac_desktop.activate_target(target))
            self.assertIn(("field1", "focus", True), calls)
            foreground.return_value = mac_desktop.FocusTarget(12, "window2", None)
            self.assertFalse(mac_desktop.activate_target(target))
            ax.AXUIElementPerformAction = lambda *args: -25202
            self.assertFalse(mac_desktop.activate_target(target))


if __name__ == "__main__":
    unittest.main()
