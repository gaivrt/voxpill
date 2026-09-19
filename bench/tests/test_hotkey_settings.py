import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from hotkey import HotkeyCapture, HotkeySelection, VK, parse_hotkey, save_hotkey


class HotkeySettingsTest(unittest.TestCase):
    def test_capture_chord_and_repeat_then_reload(self):
        capture = HotkeyCapture()
        for code in (0xA3, 0xA0, 0x20, 0x20):
            self.assertIsNone(capture.feed(code, True))
        self.assertIsNone(capture.feed(0x20, False))
        self.assertIsNone(capture.feed(0xA3, False))
        key = capture.feed(0xA0, False)
        self.assertEqual(set(parse_hotkey(key)), {0xA3, 0xA0, 0x20})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.toml"
            save_hotkey(path, key)
            saved = tomllib.loads(path.read_text())["hotkey"]["key"]
            self.assertEqual(parse_hotkey(saved), parse_hotkey(key))

    def test_single_key_oem_and_copilot_chord(self):
        for codes in ({0xA3}, {0xBA}, {0x5B, 0xA0, 0x86}):
            capture = HotkeyCapture()
            for code in codes:
                capture.feed(code, True)
            result = None
            for code in codes:
                result = capture.feed(code, False)
            self.assertEqual(set(parse_hotkey(result)), codes)

    def test_combination_switch_waits_for_every_member_release(self):
        selection = HotkeySelection("ctrl_r", "ctrl_l+shift_l+space")
        for held in (0xA3, 0xA2, 0xA0, 0x20):
            self.assertFalse(selection.apply_pending(False, lambda vk: vk == held))
        self.assertTrue(selection.apply_pending(False, lambda vk: False))

    def test_invalid_binding_does_not_overwrite_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.toml"
            path.write_text('[hotkey]\nkey = "ctrl_r"\n')
            original = path.read_bytes()
            for key in ("", "ctrl_l+", "vk_00", "unknown"):
                with self.assertRaises(ValueError):
                    save_hotkey(path, key)
                self.assertEqual(path.read_bytes(), original)

    def test_save_preserves_settings_and_comments(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.toml"
            source = '# 用户设置\n[hotkey]\nkey = "ctrl_r" # 默认键\n\n[audio]\ndevice = "麦克风"\n'
            path.write_text(source, encoding="utf-8")
            save_hotkey(path, "shift_r")
            updated = path.read_text(encoding="utf-8")
            self.assertIn('# 默认键', updated)
            self.assertEqual(tomllib.loads(updated), {
                "hotkey": {"key": "shift_r"}, "audio": {"device": "麦克风"},
            })

    def test_missing_file_section_and_key(self):
        for source in (None, '[audio]\ndevice = ""\n', '[hotkey]\n# choose\n[audio]\ndevice = ""\n'):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "config.toml"
                if source is not None:
                    path.write_text(source, encoding="utf-8")
                save_hotkey(path, "f8")
                self.assertEqual(tomllib.loads(path.read_text())["hotkey"]["key"], "f8")

    def test_failed_write_keeps_original_and_removes_temp(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.toml"
            source = '[hotkey]\nkey = "ctrl_r"\n'
            path.write_text(source)
            with patch("hotkey.os.replace", side_effect=PermissionError("read only")):
                with self.assertRaises(PermissionError):
                    save_hotkey(path, "f8")
            self.assertEqual(path.read_text(), source)
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_switch_waits_for_recording_and_release_of_both_keys(self):
        selection = HotkeySelection(pending="shift_r")
        self.assertFalse(selection.apply_pending(True, lambda vk: False))
        for held in (VK["ctrl_r"], VK["shift_r"]):
            self.assertFalse(selection.apply_pending(False, lambda vk: vk == held))
            self.assertEqual(selection.key, "ctrl_r")
        self.assertTrue(selection.apply_pending(False, lambda vk: False))
        self.assertEqual(selection.key, "shift_r")
        self.assertIsNone(selection.pending)
        self.assertFalse(selection.apply_pending(False, lambda vk: False))


if __name__ == "__main__":
    unittest.main()
