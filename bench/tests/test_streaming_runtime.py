from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

from hotkey import HotkeyGate
from overlay import (
    adaptive_layout,
    adaptive_width,
    display_text,
    ease_in_out_cubic,
    ease_out_quint,
    expanded_layout,
    OverlayLayout,
    overlay_palette,
    visual_units,
)


ROOT = Path(__file__).resolve().parents[2]


class StreamingRuntimeTest(unittest.TestCase):
    def test_mouse_click_pulses_do_not_start_hotkey(self):
        gate = HotkeyGate(stable_seconds=0.06, mouse_guard_seconds=0.12)
        events = [
            (0.00, False, True),
            (0.02, True, False),
            (0.04, False, True),
            (0.06, True, False),
            (0.08, False, False),
            (0.20, False, False),
        ]
        self.assertEqual(
            [gate.update(at, key, left) for at, key, left in events],
            [None] * len(events),
        )

    def test_stable_hotkey_starts_and_release_stops(self):
        gate = HotkeyGate(stable_seconds=0.06, mouse_guard_seconds=0.12)
        self.assertIsNone(gate.update(1.00, True, False))
        self.assertIsNone(gate.update(1.04, True, False))
        self.assertEqual(gate.update(1.06, True, False), "start")
        self.assertIsNone(gate.update(1.08, True, False))
        self.assertEqual(gate.update(1.10, False, False), "stop")

    def test_overlay_animation_curves_and_text_tail(self):
        self.assertEqual(ease_out_quint(0), 0)
        self.assertEqual(ease_out_quint(1), 1)
        self.assertEqual(ease_in_out_cubic(0), 0)
        self.assertEqual(ease_in_out_cubic(1), 1)
        self.assertEqual(display_text("a\n  b"), "a b")
        self.assertEqual(adaptive_width(""), 36)
        self.assertLess(adaptive_width("short"), adaptive_width("这是一段逐渐变长的中文 partial"))
        self.assertLessEqual(adaptive_width("x" * 500), 440)
        self.assertEqual(adaptive_layout("short").lines, 1)
        self.assertEqual(adaptive_layout("中" * 100), OverlayLayout(440, 40, 1))
        grown = expanded_layout(OverlayLayout(440, 40, 1), "short")
        self.assertEqual(grown, OverlayLayout(440, 40, 1))
        self.assertEqual(overlay_palette(True)[0], (0, 0, 0))
        self.assertEqual(overlay_palette(False)[0], (250, 249, 245))
        self.assertEqual(overlay_palette(False)[2], (80, 75, 65, 32))

    def test_default_hotkey_and_pseudo_streaming_config(self):
        config = tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual(config["hotkey"]["key"], "ctrl_r")
        self.assertEqual(config["overlay"]["theme"], "auto")
        self.assertTrue(config["final_pass"]["enabled"])
        self.assertEqual(config["final_pass"]["timeout_seconds"], 30.0)
        self.assertEqual(config["final_pass"]["max_audio_seconds"], 120.0)
        self.assertEqual(config["final_pass"]["preview_interval_seconds"], 1.0)
        self.assertEqual(config["final_pass"]["preview_min_seconds"], 0.8)
        self.assertEqual(config["final_pass"]["preview_timeout_seconds"], 8.0)
        self.assertIn("voicekey-qwen-win", config["final_pass"]["python"])
        for name in ("model.int8.onnx", "tokens.txt"):
            self.assertTrue((ROOT / "models" / "asr" / name).is_file())

    def test_production_runtime_and_portable_exclude_streaming_paraformer(self):
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        spec = (ROOT / "voicekey.spec").read_text(encoding="utf-8")
        build = (ROOT / "build-portable.bat").read_text(encoding="utf-8")

        self.assertNotIn("load_streaming_asr", main_source)
        self.assertNotIn("create_streaming_session", main_source)
        cleanup = main_source[main_source.index("    def cleanup():") :]
        self.assertLess(
            cleanup.index("job.recording_done.set()"),
            cleanup.index("qwen_client.close()"),
        )
        self.assertIn("cancel_event=stop_flag", main_source)
        self.assertIn("qwen_client.cancel_preview()", main_source)
        self.assertNotIn("asr-streaming", spec)
        self.assertNotIn("asr-streaming", build)
        self.assertIn("models/asr", spec)
        self.assertIn("models\\asr", build)


if __name__ == "__main__":
    unittest.main()
