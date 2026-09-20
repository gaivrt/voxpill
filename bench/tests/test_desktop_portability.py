import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import app_paths
import desktop_unix as desktop


class DesktopPortabilityTest(unittest.TestCase):
    def test_mac_polls_right_control_and_generic_modifier(self):
        quartz = SimpleNamespace(kCGEventSourceStateCombinedSessionState=0,
                                 CGEventSourceKeyState=lambda source, key: key == 62)
        with patch.object(desktop.sys, "platform", "darwin"), patch.dict("sys.modules", Quartz=quartz):
            self.assertTrue(desktop.key_down(0xA3))
            self.assertFalse(desktop.key_down(0xA2))
            self.assertTrue(desktop.key_down(0x11))
            self.assertFalse(desktop.key_down(0xFE))

    def test_x11_polls_native_bitmap_and_observes_release(self):
        display = MagicMock()
        display.keysym_to_keycode.return_value = 105
        bitmap = [0] * 32
        bitmap[13] = 2
        display.query_keymap.return_value = bitmap
        xlib = SimpleNamespace(XK=SimpleNamespace(string_to_keysym=lambda name: name))
        with patch.object(desktop.sys, "platform", "linux"), patch.object(desktop, "_display", return_value=display), patch.dict("sys.modules", Xlib=xlib):
            self.assertTrue(desktop.key_down(0xA3))
            bitmap[13] = 0
            self.assertFalse(desktop.key_down(0xA3))

    def test_reject_wayland_even_when_xwayland_display_exists(self):
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}):
            with self.assertRaisesRegex(RuntimeError, "X11"):
                desktop._display()

    def test_focus_changes_fail_closed(self):
        with patch.object(desktop, "foreground_target", return_value=(123, 456)):
            self.assertTrue(desktop.activate_target((123, 456)))
            self.assertFalse(desktop.activate_target((123, 789)))
            self.assertFalse(desktop.activate_target(None))

    def test_clipboard_command_receives_unicode_as_data(self):
        with patch.object(desktop.sys, "platform", "linux"), patch.object(desktop.subprocess, "run") as run:
            desktop._clipboard_write("中文 $(do not execute)")
            self.assertEqual(run.call_args.args[0], ["xclip", "-selection", "clipboard"])
            self.assertEqual(run.call_args.kwargs["input"].decode(), "中文 $(do not execute)")

    def test_mac_paste_uses_command_and_retains_clipboard(self):
        keyboard = MagicMock()
        keys = SimpleNamespace(cmd="command", ctrl="control")
        with patch.object(desktop.sys, "platform", "darwin"), patch.dict("sys.modules", {"pynput.keyboard": SimpleNamespace(Key=keys)}), patch.object(desktop, "_keyboard", return_value=keyboard), patch.object(desktop, "_clipboard_write") as write:
            desktop.paste_text("你好")
            write.assert_called_once_with("你好")
            keyboard.pressed.assert_called_once_with("command")
            keyboard.tap.assert_called_once_with("v")

    def test_config_initialization_preserves_user_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            resources, data = root / "bundle", root / "user"
            resources.mkdir()
            (resources / "config.toml").write_text("original")
            with patch.multiple(app_paths, RESOURCE_DIR=resources, DATA_DIR=data, CONFIG_PATH=data / "config.toml"):
                app_paths.initialize_config()
                self.assertEqual(app_paths.CONFIG_PATH.read_text(), "original")
                app_paths.CONFIG_PATH.write_text("custom")
                app_paths.initialize_config()
                self.assertEqual(app_paths.CONFIG_PATH.read_text(), "custom")

    def test_unsupported_native_key_is_rejected(self):
        for platform in ("darwin", "linux"):
            with patch.object(desktop.sys, "platform", platform):
                self.assertEqual(desktop.validate_hotkey("ctrl_r+f8"), (0xA3, 0x77))
                with self.assertRaises(ValueError):
                    desktop.validate_hotkey("vk_ff")


if __name__ == "__main__":
    unittest.main()
