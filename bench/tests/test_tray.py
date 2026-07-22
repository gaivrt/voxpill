from __future__ import annotations

import unittest

import tray


class TrayIconTest(unittest.TestCase):
    def test_tooltip_is_product_name_only(self):
        self.assertEqual(tray.TOOLTIP, "VoxPill")

    def test_icon_geometry_is_centered_and_transparent(self):
        image = tray.make_image(False, dark=True)
        self.assertEqual(image.mode, "RGBA")
        self.assertEqual(image.size, (64, 64))
        self.assertEqual(image.getpixel((0, 0))[3], 0)
        self.assertEqual(image.getpixel((63, 63))[3], 0)

        box = image.getchannel("A").getbbox()
        self.assertIsNotNone(box)
        left, top, right, bottom = box
        self.assertEqual(right - left, bottom - top)
        self.assertGreaterEqual(right - left, 62)
        self.assertLessEqual(abs((left + right - 1) / 2 - 31.5), 0.5)
        self.assertLessEqual(abs((top + bottom - 1) / 2 - 31.5), 0.5)

    def test_recording_state_changes_waveform_frame_not_orb_color(self):
        idle = tray.make_image(False, dark=True)
        active = tray.make_image(True, dark=True)
        self.assertEqual(idle.getchannel("A").tobytes(), active.getchannel("A").tobytes())
        self.assertNotEqual(idle.tobytes(), active.tobytes())
        self.assertEqual(idle.getpixel((14, 32)), active.getpixel((14, 32)))

    def test_light_and_dark_icons_share_the_same_circle(self):
        light = tray.make_image(False, dark=False)
        dark = tray.make_image(False, dark=True)
        self.assertEqual(light.getchannel("A").tobytes(), dark.getchannel("A").tobytes())
        self.assertNotEqual(light.getpixel((32, 32)), dark.getpixel((32, 32)))

    def test_windows_theme_value_is_mapped_to_dark_mode(self):
        self.assertFalse(tray.dark_from_apps_use_light_theme(1))
        self.assertTrue(tray.dark_from_apps_use_light_theme(0))


if __name__ == "__main__":
    unittest.main()
