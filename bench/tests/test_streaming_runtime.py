from __future__ import annotations

import tomllib
import unittest
import threading
import time
from pathlib import Path

import numpy as np

from hotkey import HotkeyGate

from asr import (
    StreamingAsrPipeline,
    accept_streaming_pcm,
    create_streaming_session,
    finish_streaming_session,
    punctuate_streaming_text,
)
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


class FakeStream:
    def __init__(self):
        self.ready = False
        self.finished = False

    def accept_waveform(self, sample_rate, samples):
        self.ready = True

    def input_finished(self):
        self.finished = True


class FakeRecognizer:
    def __init__(self):
        self.decodes = 0

    def create_stream(self):
        return FakeStream()

    def is_ready(self, stream):
        return stream.ready

    def decode_stream(self, stream):
        stream.ready = False
        self.decodes += 1

    def get_result(self, stream):
        return "final" if stream.finished else f"partial-{self.decodes}"


class FakePunctuation:
    def add_punctuation(self, text):
        return text + "."


class OverlapPunctuation:
    def __init__(self):
        self.active = 0
        self.overlap = False
        self.lock = threading.Lock()

    def add_punctuation(self, text):
        with self.lock:
            self.active += 1
            self.overlap |= self.active > 1
        time.sleep(0.03)
        with self.lock:
            self.active -= 1
        return text + "."


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

    def test_streaming_session_partial_and_single_finish(self):
        pipeline = StreamingAsrPipeline(FakeRecognizer(), FakePunctuation())
        session = create_streaming_session(pipeline)
        pcm = np.zeros(1600, dtype=np.int16).tobytes()
        self.assertEqual(accept_streaming_pcm(session, pcm), "partial-1")
        self.assertEqual(punctuate_streaming_text(session, "partial-1"), "partial-1.")
        self.assertEqual(finish_streaming_session(session), "final.")
        with self.assertRaises(RuntimeError):
            finish_streaming_session(session)

    def test_punctuation_shares_the_decode_lock(self):
        punctuation = OverlapPunctuation()
        pipeline = StreamingAsrPipeline(FakeRecognizer(), punctuation)
        sessions = [create_streaming_session(pipeline) for _ in range(2)]
        threads = [
            threading.Thread(target=finish_streaming_session, args=(session,))
            for session in sessions
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertFalse(punctuation.overlap)

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

    def test_default_hotkey_and_streaming_assets(self):
        config = tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual(config["hotkey"]["key"], "ctrl_r")
        self.assertEqual(config["overlay"]["theme"], "auto")
        for name in ("encoder.int8.onnx", "decoder.int8.onnx", "tokens.txt"):
            self.assertTrue((ROOT / "models" / "asr-streaming" / name).is_file())


if __name__ == "__main__":
    unittest.main()
