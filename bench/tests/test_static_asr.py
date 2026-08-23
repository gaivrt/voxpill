from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import patch

import numpy as np

from asr import (
    adaptive_preview_interval,
    advance_preview_deadline,
    BoundedPcmBuffer,
    OfflineAsr,
    RecognitionConfig,
    RecognitionPriorityGate,
    has_acoustic_activity,
    run_pseudo_streaming_preview,
)


class OfflineAsrTest(unittest.TestCase):
    def test_model_loads_eagerly_once_and_reuses_one_pipeline(self):
        loads = []
        pipeline = object()

        def loader(base_dir, say):
            loads.append((base_dir, say))
            return pipeline

        engine = OfflineAsr(loader=loader)
        self.assertTrue(engine.is_loaded)
        self.assertEqual(len(loads), 1)

        with patch("asr.transcribe", side_effect=["first", "second"]) as recognize:
            self.assertEqual(engine.recognize(b"one"), "first")
            self.assertEqual(engine.recognize(b"two", priority="preview"), "second")

        self.assertEqual(len(loads), 1)
        self.assertEqual(recognize.call_count, 2)

    def test_timing_separates_gate_decode_punctuation_and_total(self):
        engine = OfflineAsr(loader=lambda *_: object())
        timings = []

        with (
            patch("asr.time.perf_counter", side_effect=[10.0, 10.2, 10.8]),
            patch("asr.transcribe_timed", return_value=("ok", 0.5, 0.01)),
        ):
            self.assertEqual(engine.recognize(b"pcm", on_timing=timings.append), "ok")

        self.assertEqual(len(timings), 1)
        self.assertAlmostEqual(timings[0].gate_seconds, 0.2)
        self.assertEqual(timings[0].decode_seconds, 0.5)
        self.assertEqual(timings[0].punctuation_seconds, 0.01)
        self.assertAlmostEqual(timings[0].total_seconds, 0.8)

    def test_one_pipeline_serializes_parallel_recognition(self):
        engine = OfflineAsr(loader=lambda *_: object())
        active = 0
        peak = 0
        lock = threading.Lock()

        def transcribe(*_):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            return "ok"

        with patch("asr.transcribe", side_effect=transcribe):
            threads = [
                threading.Thread(
                    target=engine.recognize,
                    args=(b"pcm",),
                    kwargs={"priority": "preview"},
                )
                for _ in range(3)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(peak, 1)

    def test_released_preview_cancels_while_waiting_for_pipeline(self):
        engine = OfflineAsr(loader=lambda *_: object())
        active_started = threading.Event()
        release_active = threading.Event()
        recording_done = threading.Event()
        preview_result = []

        def transcribe(*_):
            if not active_started.is_set():
                active_started.set()
                release_active.wait(1)
                return "final"
            return "stale preview"

        with patch("asr.transcribe", side_effect=transcribe) as recognize:
            active = threading.Thread(target=engine.recognize, args=(b"active",))
            preview = threading.Thread(
                target=lambda: preview_result.append(
                    engine.recognize(
                        b"preview",
                        priority="preview",
                        cancel_event=recording_done,
                    )
                )
            )
            active.start()
            self.assertTrue(active_started.wait(1))
            preview.start()
            time.sleep(0.02)
            recording_done.set()
            preview.join(0.5)
            release_active.set()
            active.join(1)

        self.assertFalse(preview.is_alive())
        self.assertEqual(preview_result, [""])
        self.assertEqual(recognize.call_count, 1)


class BoundedPcmBufferTest(unittest.TestCase):
    def test_snapshot_is_safe_while_audio_is_appended(self):
        buffer = BoundedPcmBuffer(max_bytes=8)
        self.assertTrue(buffer.append(b"ab"))
        self.assertEqual(buffer.to_bytes(), b"ab")
        self.assertTrue(buffer.append(b"cd"))
        self.assertEqual(buffer.to_bytes(), b"abcd")
        self.assertEqual(buffer.total_bytes, 4)

    def test_overflow_discards_pcm_and_stays_ineligible(self):
        buffer = BoundedPcmBuffer(max_bytes=3)
        self.assertTrue(buffer.append(b"ab"))
        self.assertFalse(buffer.append(b"cd"))
        self.assertFalse(buffer.eligible)
        self.assertEqual(buffer.to_bytes(), b"")
        self.assertFalse(buffer.append(b"e"))
        self.assertEqual(buffer.total_bytes, 5)


class AcousticActivityTest(unittest.TestCase):
    def setUp(self):
        self.config = RecognitionConfig(
            activity_rms_floor=50.0,
            activity_min_seconds=0.12,
            activity_vad_mode=2,
        )

    def test_zero_and_steady_noise_are_not_speech(self):
        zeros = np.zeros(16000 * 4, dtype=np.int16)
        noise = np.random.default_rng(7).normal(0, 300, 16000 * 4).astype(np.int16)

        self.assertFalse(has_acoustic_activity(zeros.tobytes(), self.config))
        self.assertFalse(has_acoustic_activity(noise.tobytes(), self.config))

    def test_brief_impulse_is_not_speech(self):
        samples = np.zeros(16000, dtype=np.int16)
        samples[320:960] = 5000

        self.assertFalse(has_acoustic_activity(samples.tobytes(), self.config))

    def test_quiet_speech_like_bursts_are_speech(self):
        samples = np.zeros(16000, dtype=np.int16)
        tone = (np.sin(np.arange(320) * 0.2) * 260).astype(np.int16)
        for start in range(1600, 1600 + 8 * 640, 640):
            samples[start : start + 320] = tone

        self.assertTrue(has_acoustic_activity(samples.tobytes(), self.config))

    def test_sustained_quiet_voiced_waveform_is_speech(self):
        phase = np.arange(16000, dtype=np.float32) * (2 * np.pi * 220 / 16000)
        voiced = np.sin(phase) + 0.45 * np.sin(phase * 2) + 0.2 * np.sin(phase * 3)
        voiced /= np.max(np.abs(voiced))
        for amplitude in (100, 260, 1000, 5000):
            samples = (voiced * amplitude).astype(np.int16)
            with self.subTest(amplitude=amplitude):
                self.assertTrue(
                    has_acoustic_activity(samples.tobytes(), self.config)
                )

    def test_leading_silence_does_not_hide_sustained_quiet_voice(self):
        phase = np.arange(16000, dtype=np.float32) * (2 * np.pi * 220 / 16000)
        voiced = np.sin(phase) + 0.45 * np.sin(phase * 2) + 0.2 * np.sin(phase * 3)
        voiced /= np.max(np.abs(voiced))
        silence = np.zeros(16000, dtype=np.int16)
        for amplitude in (100, 260):
            samples = np.concatenate((silence, (voiced * amplitude).astype(np.int16)))
            with self.subTest(amplitude=amplitude):
                self.assertTrue(
                    has_acoustic_activity(samples.tobytes(), self.config)
                )

    def test_electrical_hum_and_colored_noise_are_not_speech(self):
        phase = np.arange(16000, dtype=np.float32) * (2 * np.pi * 60 / 16000)
        hum = (np.sin(phase) * 1000).astype(np.int16)
        voice_band_tone = (
            np.sin(np.arange(16000) * (2 * np.pi * 220 / 16000)) * 1000
        ).astype(np.int16)
        rng = np.random.default_rng(11)
        source = rng.normal(0, 1, 16000)
        colored = np.empty(16000)
        colored[0] = source[0]
        for index in range(1, len(colored)):
            colored[index] = 0.98 * colored[index - 1] + source[index]
        colored = (colored / np.sqrt(np.mean(colored**2)) * 1000).astype(np.int16)

        self.assertFalse(has_acoustic_activity(hum.tobytes(), self.config))
        self.assertFalse(has_acoustic_activity(voice_band_tone.tobytes(), self.config))
        self.assertFalse(has_acoustic_activity(colored.tobytes(), self.config))


class RecognitionPriorityGateTest(unittest.TestCase):
    def test_waiting_final_passes_a_waiting_preview(self):
        gate = RecognitionPriorityGate()
        release_active = threading.Event()
        active_started = threading.Event()
        order = []

        def active_preview():
            with gate.acquire("preview"):
                active_started.set()
                release_active.wait(1)

        def waiter(priority):
            with gate.acquire(priority):
                order.append(priority)

        active = threading.Thread(target=active_preview)
        preview = threading.Thread(target=waiter, args=("preview",))
        final = threading.Thread(target=waiter, args=("final",))
        active.start()
        self.assertTrue(active_started.wait(1))
        preview.start()
        time.sleep(0.01)
        final.start()
        time.sleep(0.01)
        release_active.set()
        for thread in (active, preview, final):
            thread.join(1)

        self.assertEqual(order, ["final", "preview"])


class PseudoStreamingPreviewTest(unittest.TestCase):
    class FakeEngine:
        def __init__(self, result="partial"):
            self.result = result
            self.calls = []

        def recognize(self, pcm, *, priority="final", cancel_event=None):
            del cancel_event
            self.calls.append((pcm, priority))
            return self.result

    @staticmethod
    def config():
        return RecognitionConfig(
            preview_interval_seconds=0.01,
            preview_max_interval_seconds=0.02,
            preview_min_seconds=0.001,
            preview_max_audio_seconds=30.0,
            max_audio_seconds=120.0,
            activity_min_seconds=0.02,
        )

    @staticmethod
    def speech_pcm():
        samples = np.zeros(3200, dtype=np.int16)
        samples[320:960] = 1000
        return samples.tobytes()

    def test_preview_uses_accumulated_pcm_and_stops_after_release(self):
        engine = self.FakeEngine()
        pcm = self.speech_pcm()
        buffer = BoundedPcmBuffer(max_bytes=10000)
        buffer.append(pcm)
        done = threading.Event()
        partials = []

        thread = threading.Thread(
            target=run_pseudo_streaming_preview,
            args=(engine, buffer, done, self.config(), partials.append),
        )
        thread.start()
        deadline = time.monotonic() + 1
        while not partials and time.monotonic() < deadline:
            time.sleep(0.005)
        done.set()
        thread.join(1)

        self.assertEqual(partials, ["partial"])
        self.assertEqual(engine.calls[0], (pcm, "preview"))
        call_count = len(engine.calls)
        time.sleep(0.03)
        self.assertEqual(len(engine.calls), call_count)

    def test_preview_skips_no_speech_pcm(self):
        engine = self.FakeEngine()
        buffer = BoundedPcmBuffer(max_bytes=100000)
        buffer.append(bytes(16000 * 2))
        done = threading.Event()

        thread = threading.Thread(
            target=run_pseudo_streaming_preview,
            args=(engine, buffer, done, self.config(), lambda _: None),
        )
        thread.start()
        time.sleep(0.04)
        done.set()
        thread.join(1)

        self.assertEqual(engine.calls, [])

    def test_adaptive_interval_is_bounded_by_configured_range(self):
        self.assertEqual(adaptive_preview_interval(0.1, 1.0, 2.0), 1.0)
        self.assertEqual(adaptive_preview_interval(0.75, 1.0, 2.0), 1.5)
        self.assertEqual(adaptive_preview_interval(2.0, 1.0, 2.0), 2.0)

    def test_deadline_skips_missed_ticks_without_queuing_catchup(self):
        self.assertEqual(advance_preview_deadline(10.0, 10.2, 1.0), 11.0)
        self.assertEqual(advance_preview_deadline(10.0, 13.2, 1.0), 14.0)

    def test_release_and_publish_share_one_session_lock(self):
        buffer = BoundedPcmBuffer(max_bytes=10000)
        buffer.append(self.speech_pcm())
        done = threading.Event()
        session_lock = threading.Lock()
        recognition_started = threading.Event()
        allow_result = threading.Event()
        partials = []

        class BlockingEngine:
            def recognize(self, pcm, *, priority="final", cancel_event=None):
                del pcm, priority, cancel_event
                recognition_started.set()
                allow_result.wait(1)
                return "stale"

        thread = threading.Thread(
            target=run_pseudo_streaming_preview,
            args=(
                BlockingEngine(),
                buffer,
                done,
                self.config(),
                partials.append,
                print,
                session_lock,
            ),
        )
        thread.start()
        self.assertTrue(recognition_started.wait(1))
        with session_lock:
            done.set()
        allow_result.set()
        thread.join(1)

        self.assertEqual(partials, [])


if __name__ == "__main__":
    unittest.main()
