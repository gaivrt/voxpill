from __future__ import annotations

import queue
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from qwen_final import (
    BoundedPcmBuffer,
    QwenFinalClient,
    QwenFinalConfig,
    QwenRequestCancelled,
    RequestPriorityGate,
    WorkerCancellationRegistry,
    recognize_final_with_fallback,
    run_pseudo_streaming_preview,
    select_final_text,
)


class FakeClient:
    def __init__(self, result=None, error=None, ready=True):
        self.result = result
        self.error = error
        self.is_ready = ready
        self.status = "ready" if ready else "failed"
        self.calls = []

    def wait_until_ready(self, timeout_seconds):
        return self.is_ready

    def transcribe(self, pcm, timeout_seconds, *, priority="final"):
        self.calls.append((pcm, timeout_seconds, priority))
        if self.error is not None:
            raise self.error
        return self.result


class QwenFinalConfigTest(unittest.TestCase):
    def test_default_paths_expand_and_timeout_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "app"
            config = QwenFinalConfig.from_mapping(
                {"timeout_seconds": 0.1},
                app_dir,
                {"LOCALAPPDATA": str(Path(tmp) / "local")},
            )

            self.assertTrue(config.enabled)
            self.assertEqual(config.timeout_seconds, 0.5)
            self.assertEqual(config.max_audio_seconds, 120.0)
            self.assertEqual(config.preview_interval_seconds, 1.0)
            self.assertEqual(config.preview_min_seconds, 0.8)
            self.assertEqual(config.preview_timeout_seconds, 8.0)
            self.assertEqual(config.startup_wait_seconds, 15.0)
            self.assertIn("voicekey-qwen-win", str(config.python))
            self.assertEqual(
                config.model_dir, app_dir / "bench/model_cache/qwen3-asr-0.6b-hf"
            )

    def test_missing_runtime_does_not_start_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = QwenFinalConfig(
                enabled=True,
                python=root / "missing-python.exe",
                model_dir=root / "missing-model",
                worker_script=root / "missing-worker.py",
                timeout_seconds=8.0,
                max_audio_seconds=120.0,
                context="",
                log_path=root / "worker.log",
            )
            messages = []
            client = QwenFinalClient(config, lambda *items: messages.append(items))

            self.assertFalse(client.start())
            self.assertFalse(client.is_ready)
            self.assertTrue(messages)


class FinalSelectionTest(unittest.TestCase):
    def test_qwen_text_wins_when_ready(self):
        client = FakeClient(result=" Qwen final ")

        selected = select_final_text(client, b"pcm", "Para final", 3.0)

        self.assertEqual(selected.text, "Qwen final")
        self.assertEqual(selected.source, "qwen")
        self.assertEqual(client.calls, [(b"pcm", 3.0, "final")])

    def test_not_ready_uses_paraformer_without_request(self):
        client = FakeClient(result="Qwen", ready=False)

        selected = select_final_text(client, b"pcm", " Para final ", 3.0)

        self.assertEqual(selected.text, "Para final")
        self.assertEqual(selected.reason, "qwen_not_ready")
        self.assertFalse(client.calls)

    def test_empty_or_error_uses_paraformer(self):
        messages = []
        empty = select_final_text(
            FakeClient(result=""), b"pcm", "Para", 3.0, messages.append
        )
        failed = select_final_text(
            FakeClient(error=TimeoutError("slow")),
            b"pcm",
            "Para",
            3.0,
            messages.append,
        )

        self.assertEqual((empty.text, empty.reason), ("Para", "qwen_empty"))
        self.assertEqual((failed.text, failed.reason), ("Para", "qwen_error"))
        self.assertEqual(len(messages), 2)

    def test_healthy_qwen_final_never_calls_lazy_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient(result="Qwen only")
            fallback_calls = []
            config = QwenFinalConfig.from_mapping({}, Path(tmp))

            selected = recognize_final_with_fallback(
                client,
                b"pcm",
                config,
                lambda pcm: fallback_calls.append(pcm) or "Para",
            )

            self.assertEqual((selected.text, selected.source), ("Qwen only", "qwen"))
            self.assertEqual(fallback_calls, [])
            self.assertEqual(client.calls, [(b"pcm", 8.0, "final")])

    def test_confirmed_qwen_failure_calls_fallback_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient(result="Qwen", ready=True)
            fallback_calls = []
            config = QwenFinalConfig.from_mapping({}, Path(tmp))

            selected = recognize_final_with_fallback(
                client,
                b"pcm",
                config,
                lambda pcm: fallback_calls.append(pcm) or "Para",
                qwen_failed=True,
            )

            self.assertEqual((selected.text, selected.source), ("Para", "paraformer"))
            self.assertEqual(fallback_calls, [b"pcm"])
            self.assertEqual(client.calls, [])

    def test_shutdown_cancels_fallback_without_loading_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient(error=RuntimeError("worker stopped"))
            fallback_calls = []
            stopping = threading.Event()
            stopping.set()

            selected = recognize_final_with_fallback(
                client,
                b"pcm",
                QwenFinalConfig.from_mapping({}, Path(tmp)),
                lambda pcm: fallback_calls.append(pcm) or "Para",
                cancel_event=stopping,
            )

            self.assertEqual(selected.source, "cancelled")
            self.assertEqual(selected.text, "")
            self.assertEqual(fallback_calls, [])

    def test_response_ids_do_not_cross_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = QwenFinalConfig(
                enabled=True,
                python=root / "python.exe",
                model_dir=root,
                worker_script=root / "worker.py",
                timeout_seconds=8.0,
                max_audio_seconds=120.0,
                context="",
                log_path=root / "worker.log",
            )
            client = QwenFinalClient(config)
            process = object()
            response_queue = queue.Queue()
            client._process = process
            client._pending["current"] = response_queue

            client._handle_message(
                process, {"type": "result", "id": "late", "text": "old"}
            )
            self.assertTrue(response_queue.empty())
            client._handle_message(
                process, {"type": "result", "id": "current", "text": "new"}
            )
            self.assertEqual(response_queue.get_nowait()["text"], "new")


class BoundedPcmBufferTest(unittest.TestCase):
    def test_overflow_discards_pcm_and_stays_ineligible(self):
        pcm = BoundedPcmBuffer(max_bytes=4)

        self.assertTrue(pcm.append(b"12"))
        self.assertTrue(pcm.append(b"34"))
        self.assertFalse(pcm.append(b"5"))
        self.assertFalse(pcm.append(b"6"))
        self.assertFalse(pcm.eligible)
        self.assertEqual(pcm.to_bytes(), b"")
        self.assertEqual(pcm.total_bytes, 6)

    def test_snapshot_is_safe_while_audio_is_appended(self):
        pcm = BoundedPcmBuffer(max_bytes=4000)
        threads = [
            threading.Thread(target=lambda: [pcm.append(b"12") for _ in range(500)])
            for _ in range(4)
        ]
        for thread in threads:
            thread.start()
        snapshots = []
        while any(thread.is_alive() for thread in threads):
            snapshots.append(len(pcm.to_bytes()))
        for thread in threads:
            thread.join()

        self.assertTrue(pcm.eligible)
        self.assertEqual(pcm.total_bytes, 4000)
        self.assertEqual(len(pcm.to_bytes()), 4000)
        self.assertTrue(all(length % 2 == 0 for length in snapshots))


class RequestPriorityGateTest(unittest.TestCase):
    def test_waiting_final_passes_a_waiting_preview(self):
        gate = RequestPriorityGate()
        active = threading.Event()
        release = threading.Event()
        order = []

        def first_preview():
            with gate.acquire("preview"):
                active.set()
                release.wait(1)

        def request(priority):
            with gate.acquire(priority):
                order.append(priority)

        first = threading.Thread(target=first_preview)
        final = threading.Thread(target=request, args=("final",))
        preview = threading.Thread(target=request, args=("preview",))
        first.start()
        self.assertTrue(active.wait(1))
        final.start()
        deadline = time.monotonic() + 1
        while gate._final_waiters != 1 and time.monotonic() < deadline:
            time.sleep(0.005)
        preview.start()
        release.set()
        for thread in (first, final, preview):
            thread.join(1)

        self.assertEqual(order, ["final", "preview"])


class WorkerCancellationRegistryTest(unittest.TestCase):
    def test_wrong_and_late_ids_have_no_effect(self):
        registry = WorkerCancellationRegistry()
        event = threading.Event()

        self.assertFalse(registry.cancel("unknown"))
        registry.register("current")
        registry.activate("current", event)
        self.assertFalse(registry.cancel("wrong"))
        self.assertFalse(event.is_set())
        self.assertTrue(registry.cancel("current"))
        self.assertTrue(event.is_set())
        registry.finish("current")
        self.assertFalse(registry.cancel("current"))


class QwenClientCancellationTest(unittest.TestCase):
    class FakePipe:
        def __init__(self):
            self.messages = []

        def write(self, line):
            self.messages.append(json.loads(line))

        def flush(self):
            pass

    class FakeProcess:
        def __init__(self):
            self.stdin = QwenClientCancellationTest.FakePipe()

        def poll(self):
            return None

    def make_client(self, root: Path):
        config = QwenFinalConfig(
            enabled=True,
            python=root / "python.exe",
            model_dir=root,
            worker_script=root / "worker.py",
            timeout_seconds=3.0,
            max_audio_seconds=120.0,
            context="",
            log_path=root / "worker.log",
        )
        client = QwenFinalClient(config)
        process = self.FakeProcess()
        client._process = process
        client._ready = True
        client._status = "ready"
        return client, process

    def test_cancel_writes_while_preview_holds_inference_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, process = self.make_client(Path(tmp))
            outcome = []

            def preview():
                try:
                    client.transcribe(b"pcm", 1.0, priority="preview")
                except Exception as exc:
                    outcome.append(type(exc))

            thread = threading.Thread(target=preview)
            thread.start()
            deadline = time.monotonic() + 1
            while client._active_preview is None and time.monotonic() < deadline:
                time.sleep(0.005)
            self.assertTrue(client.cancel_preview())
            request_id = process.stdin.messages[0]["id"]
            self.assertEqual(
                process.stdin.messages[1], {"type": "cancel", "id": request_id}
            )
            client._handle_message(
                process, {"type": "cancelled", "id": request_id}
            )
            thread.join(1)

            self.assertEqual(outcome, [QwenRequestCancelled])
            self.assertIsNone(client._active_preview)

    def test_no_active_preview_means_no_cancel_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, process = self.make_client(Path(tmp))
            self.assertFalse(client.cancel_preview())
            self.assertEqual(process.stdin.messages, [])

    def test_final_request_is_never_exposed_to_preview_cancel(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, process = self.make_client(Path(tmp))
            outcome = []

            thread = threading.Thread(
                target=lambda: outcome.append(
                    client.transcribe(b"pcm", 1.0, priority="final")
                )
            )
            thread.start()
            deadline = time.monotonic() + 1
            while not process.stdin.messages and time.monotonic() < deadline:
                time.sleep(0.005)
            self.assertIsNone(client._active_preview)
            self.assertFalse(client.cancel_preview())
            request_id = process.stdin.messages[0]["id"]
            client._handle_message(
                process, {"type": "result", "id": request_id, "text": "final"}
            )
            thread.join(1)

            self.assertEqual(outcome, ["final"])
            self.assertEqual(len(process.stdin.messages), 1)


class PseudoStreamingPreviewTest(unittest.TestCase):
    def make_config(self, root: Path) -> QwenFinalConfig:
        return QwenFinalConfig(
            enabled=True,
            python=root / "python.exe",
            model_dir=root,
            worker_script=root / "worker.py",
            timeout_seconds=3.0,
            max_audio_seconds=120.0,
            context="",
            log_path=root / "worker.log",
            preview_interval_seconds=0.01,
            preview_min_seconds=0.001,
            preview_max_audio_seconds=30.0,
            preview_timeout_seconds=1.0,
        )

    def test_preview_uses_qwen_and_stops_after_recording(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = threading.Event()
            pcm = BoundedPcmBuffer(32000)
            pcm.append(b"\0\0" * 100)
            client = FakeClient(result="preview")
            updates = []

            run_pseudo_streaming_preview(
                client,
                pcm,
                done,
                self.make_config(Path(tmp)),
                lambda text: (updates.append(text), done.set()),
            )

            self.assertEqual(updates, ["preview"])
            self.assertEqual(client.calls[0][2], "preview")

    def test_stale_preview_is_not_published_after_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = threading.Event()
            pcm = BoundedPcmBuffer(32000)
            pcm.append(b"\0\0" * 100)

            class StopDuringDecode(FakeClient):
                def transcribe(self, pcm, timeout_seconds, *, priority="final"):
                    done.set()
                    return "stale"

            updates = []
            run_pseudo_streaming_preview(
                StopDuringDecode(),
                pcm,
                done,
                self.make_config(Path(tmp)),
                updates.append,
            )
            self.assertEqual(updates, [])

    def test_cancelled_preview_does_not_trigger_failure_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = threading.Event()
            pcm = BoundedPcmBuffer(32000)
            pcm.append(b"\0\0" * 100)
            failures = []

            run_pseudo_streaming_preview(
                FakeClient(error=QwenRequestCancelled("release")),
                pcm,
                done,
                self.make_config(Path(tmp)),
                lambda text: self.fail(f"unexpected partial: {text}"),
                on_failure=lambda exc, audio: failures.append((exc, audio)),
            )

            self.assertEqual(failures, [])

    def test_publish_and_release_can_share_one_session_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = threading.Event()
            pcm = BoundedPcmBuffer(32000)
            pcm.append(b"\0\0" * 100)
            lock = threading.Lock()
            callback_had_lock = []

            def publish(text):
                del text
                acquired = lock.acquire(blocking=False)
                callback_had_lock.append(not acquired)
                if acquired:
                    lock.release()
                done.set()

            run_pseudo_streaming_preview(
                FakeClient(result="preview"),
                pcm,
                done,
                self.make_config(Path(tmp)),
                publish,
                session_lock=lock,
            )

            self.assertEqual(callback_had_lock, [True])


if __name__ == "__main__":
    unittest.main()
