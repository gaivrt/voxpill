from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import patch

from asr import (
    adaptive_preview_interval,
    advance_preview_deadline,
    BoundedPcmBuffer,
    OfflineAsr,
    RecognitionConfig,
    RecognitionPriorityGate,
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

        def recognize(self, pcm, *, priority="final"):
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
        )

    def test_preview_uses_accumulated_pcm_and_stops_after_release(self):
        engine = self.FakeEngine()
        buffer = BoundedPcmBuffer(max_bytes=1000)
        buffer.append(b"x" * 64)
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
        self.assertEqual(engine.calls[0], (b"x" * 64, "preview"))
        call_count = len(engine.calls)
        time.sleep(0.03)
        self.assertEqual(len(engine.calls), call_count)

    def test_adaptive_interval_is_bounded_by_configured_range(self):
        self.assertEqual(adaptive_preview_interval(0.1, 1.0, 2.0), 1.0)
        self.assertEqual(adaptive_preview_interval(0.75, 1.0, 2.0), 1.5)
        self.assertEqual(adaptive_preview_interval(2.0, 1.0, 2.0), 2.0)

    def test_deadline_skips_missed_ticks_without_queuing_catchup(self):
        self.assertEqual(advance_preview_deadline(10.0, 10.2, 1.0), 11.0)
        self.assertEqual(advance_preview_deadline(10.0, 13.2, 1.0), 14.0)

    def test_release_and_publish_share_one_session_lock(self):
        buffer = BoundedPcmBuffer(max_bytes=1000)
        buffer.append(b"x" * 64)
        done = threading.Event()
        session_lock = threading.Lock()
        recognition_started = threading.Event()
        allow_result = threading.Event()
        partials = []

        class BlockingEngine:
            def recognize(self, pcm, *, priority="final"):
                del pcm, priority
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
