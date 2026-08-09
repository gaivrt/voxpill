"""Isolated Qwen3-ASR final-pass worker and resilient local client."""

from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
import itertools
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
from typing import Callable, Mapping


DEFAULT_PYTHON = r"%LOCALAPPDATA%\voicekey-qwen-win\Scripts\python.exe"
DEFAULT_MODEL_DIR = "bench/model_cache/qwen3-asr-0.6b-hf"
_WINDOWS_ENV = re.compile(r"%([^%]+)%")


def _expand_path(value: str, app_dir: Path, environ: Mapping[str, str]) -> Path:
    expanded = _WINDOWS_ENV.sub(
        lambda match: environ.get(match.group(1), match.group(0)), value
    )
    if os.name != "nt":
        expanded = expanded.replace("\\", os.sep)
    path = Path(os.path.expandvars(os.path.expanduser(expanded)))
    return path if path.is_absolute() else app_dir / path


@dataclass(frozen=True)
class QwenFinalConfig:
    enabled: bool
    python: Path
    model_dir: Path
    worker_script: Path
    timeout_seconds: float
    max_audio_seconds: float
    context: str
    log_path: Path
    preview_interval_seconds: float = 1.0
    preview_min_seconds: float = 0.8
    preview_max_audio_seconds: float = 30.0
    preview_timeout_seconds: float = 8.0
    startup_wait_seconds: float = 15.0

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, object],
        app_dir: Path,
        environ: Mapping[str, str] | None = None,
    ) -> "QwenFinalConfig":
        env = os.environ if environ is None else environ
        timeout = max(0.5, float(values.get("timeout_seconds", 8.0)))
        max_audio = max(1.0, float(values.get("max_audio_seconds", 120.0)))
        preview_interval = max(
            0.5, float(values.get("preview_interval_seconds", 1.0))
        )
        preview_min = max(0.3, float(values.get("preview_min_seconds", 0.8)))
        preview_max = max(
            preview_min, float(values.get("preview_max_audio_seconds", 30.0))
        )
        preview_timeout = max(
            0.5, float(values.get("preview_timeout_seconds", 8.0))
        )
        startup_wait = max(0.5, float(values.get("startup_wait_seconds", 15.0)))
        return cls(
            enabled=bool(values.get("enabled", True)),
            python=_expand_path(str(values.get("python", DEFAULT_PYTHON)), app_dir, env),
            model_dir=_expand_path(
                str(values.get("model_dir", DEFAULT_MODEL_DIR)), app_dir, env
            ),
            worker_script=app_dir / "qwen_final.py",
            timeout_seconds=timeout,
            max_audio_seconds=max_audio,
            context=str(values.get("context", "")),
            log_path=app_dir / "voxpill-qwen.log",
            preview_interval_seconds=preview_interval,
            preview_min_seconds=preview_min,
            preview_max_audio_seconds=preview_max,
            preview_timeout_seconds=preview_timeout,
            startup_wait_seconds=startup_wait,
        )


@dataclass(frozen=True)
class FinalPassResult:
    text: str
    source: str
    reason: str = ""


@dataclass
class BoundedPcmBuffer:
    max_bytes: int
    data: bytearray = field(default_factory=bytearray)
    eligible: bool = True
    total_bytes: int = 0
    _lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )

    def append(self, chunk: bytes) -> bool:
        with self._lock:
            self.total_bytes += len(chunk)
            if not self.eligible:
                return False
            if len(self.data) + len(chunk) > self.max_bytes:
                self.data.clear()
                self.eligible = False
                return False
            self.data.extend(chunk)
            return True

    def to_bytes(self) -> bytes:
        with self._lock:
            return bytes(self.data) if self.eligible else b""


class RequestPriorityGate:
    """Serialize inference while allowing waiting final requests to pass previews."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._active = False
        self._final_waiters = 0

    @contextmanager
    def acquire(self, priority: str):
        if priority not in {"preview", "final"}:
            raise ValueError(f"unknown Qwen request priority: {priority}")
        is_final = priority == "final"
        with self._condition:
            if is_final:
                self._final_waiters += 1
            try:
                while self._active or (not is_final and self._final_waiters):
                    self._condition.wait()
                self._active = True
            finally:
                if is_final:
                    self._final_waiters -= 1
        try:
            yield
        finally:
            with self._condition:
                self._active = False
                self._condition.notify_all()


class QwenRequestCancelled(RuntimeError):
    """An expected preview cancellation, not a model failure."""


class WorkerCancellationRegistry:
    """Match queued/active worker requests with bounded, request-ID cancellation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._known: set[str] = set()
        self._cancelled: set[str] = set()
        self._active: tuple[str, threading.Event] | None = None

    def register(self, request_id: str) -> None:
        with self._lock:
            self._known.add(request_id)

    def cancel(self, request_id: str) -> bool:
        with self._lock:
            if request_id not in self._known:
                return False
            self._cancelled.add(request_id)
            if self._active is not None and self._active[0] == request_id:
                self._active[1].set()
            return True

    def activate(self, request_id: str, event: threading.Event) -> None:
        with self._lock:
            self._active = (request_id, event)
            if request_id in self._cancelled:
                event.set()

    def cancel_active(self) -> None:
        with self._lock:
            if self._active is not None:
                self._active[1].set()

    def finish(self, request_id: str) -> None:
        with self._lock:
            self._known.discard(request_id)
            self._cancelled.discard(request_id)
            if self._active is not None and self._active[0] == request_id:
                self._active = None


class QwenFinalClient:
    """Own one persistent worker process without importing Torch in the app runtime."""

    def __init__(self, config: QwenFinalConfig, say: Callable[..., None] = print):
        self.config = config
        self.say = say
        self._state_lock = threading.RLock()
        self._state_changed = threading.Condition(self._state_lock)
        self._request_gate = RequestPriorityGate()
        self._write_lock = threading.Lock()
        self._pending: dict[str, queue.Queue] = {}
        self._ids = itertools.count(1)
        self._process: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._stderr_handle = None
        self._ready = False
        self._closed = False
        self._restarting = False
        self._restart_attempted = False
        self._status = "disabled" if not config.enabled else "idle"
        self._active_preview: tuple[object, str] | None = None

    @property
    def is_ready(self) -> bool:
        with self._state_lock:
            return bool(
                self._ready
                and self._process is not None
                and self._process.poll() is None
            )

    @property
    def status(self) -> str:
        with self._state_lock:
            return self._status

    def wait_until_ready(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        with self._state_changed:
            while True:
                if self.is_ready:
                    return True
                if self._status in {"disabled", "failed", "closed", "idle"}:
                    return False
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._state_changed.wait(remaining)

    def start(self) -> bool:
        with self._state_lock:
            if self._closed:
                return False
            if self._process is not None and self._process.poll() is None:
                return True
            if not self.config.enabled:
                self._status = "disabled"
                self._state_changed.notify_all()
                self.say("[qwen] final-pass disabled")
                return False
            missing = [
                path
                for path in (
                    self.config.python,
                    self.config.worker_script,
                    self.config.model_dir / "model.safetensors",
                )
                if not path.is_file()
            ]
            if missing:
                self._status = "failed"
                self._state_changed.notify_all()
                self.say("[qwen] unavailable; missing " + ", ".join(map(str, missing)))
                return False
            self._ready = False
            self._status = "loading"
            self.config.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._stderr_handle = self.config.log_path.open(
                "a", encoding="utf-8", errors="replace"
            )
            command = [
                str(self.config.python),
                str(self.config.worker_script),
                "--worker",
                "--model-dir",
                str(self.config.model_dir),
            ]
            if self.config.context:
                command.extend(["--context", self.config.context])
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                process = subprocess.Popen(
                    command,
                    cwd=str(self.config.worker_script.parent),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=self._stderr_handle,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=creationflags,
                )
            except Exception:
                self._stderr_handle.close()
                self._stderr_handle = None
                self._status = "failed"
                self._state_changed.notify_all()
                raise
            self._process = process
            reader = threading.Thread(
                target=self._reader_loop,
                args=(process,),
                name="voxpill-qwen-reader",
                daemon=True,
            )
            self._reader = reader
            reader.start()
        self.say("[qwen] background preload started")
        return True

    def _reader_loop(self, process: subprocess.Popen) -> None:
        try:
            assert process.stdout is not None
            for line in process.stdout:
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    self.say("[qwen] ignored malformed worker response")
                    continue
                self._handle_message(process, message)
        finally:
            self._handle_exit(process)

    def _handle_message(self, process: subprocess.Popen, message: dict) -> None:
        message_type = message.get("type")
        if message_type == "ready":
            with self._state_lock:
                if process is not self._process or self._closed:
                    return
                self._ready = True
                self._status = "ready"
                self._restart_attempted = False
                self._state_changed.notify_all()
            self.say(
                f"[qwen] ready in {float(message.get('load_seconds', 0)):.1f}s "
                f"on {message.get('device', 'unknown')}"
            )
            return
        if message_type == "fatal":
            with self._state_lock:
                if process is self._process:
                    self._ready = False
                    self._status = "failed"
                    self._state_changed.notify_all()
            self.say(f"[qwen] preload failed: {message.get('error', 'unknown error')}")
            return
        request_id = str(message.get("id", ""))
        with self._state_lock:
            response_queue = self._pending.pop(request_id, None)
        if response_queue is not None:
            response_queue.put(message)

    def _handle_exit(self, process: subprocess.Popen) -> None:
        should_restart = False
        with self._state_lock:
            if process is not self._process:
                return
            self._ready = False
            self._process = None
            self._active_preview = None
            pending = list(self._pending.values())
            self._pending.clear()
            if not self._closed and not self._restart_attempted:
                self._restart_attempted = True
                should_restart = True
                self._status = "restarting"
            elif not self._closed:
                self._status = "failed"
            self._state_changed.notify_all()
        for response_queue in pending:
            response_queue.put({"type": "error", "error": "worker exited"})
        self._close_stderr()
        if should_restart:
            self._schedule_restart("worker exited")

    def transcribe(
        self,
        pcm: bytes,
        timeout_seconds: float | None = None,
        *,
        priority: str = "final",
    ) -> str | None:
        if not self.is_ready:
            return None
        timeout = self.config.timeout_seconds if timeout_seconds is None else timeout_seconds
        with self._request_gate.acquire(priority):
            if not self.is_ready:
                return None
            request_id = str(next(self._ids))
            response_queue: queue.Queue = queue.Queue(maxsize=1)
            request = {
                "type": "transcribe",
                "id": request_id,
                "pcm16": base64.b64encode(pcm).decode("ascii"),
            }
            try:
                with self._write_lock:
                    with self._state_lock:
                        process = self._process
                        if process is None or process.stdin is None:
                            return None
                        self._pending[request_id] = response_queue
                        if priority == "preview":
                            self._active_preview = (process, request_id)
                    process.stdin.write(
                        json.dumps(request, separators=(",", ":")) + "\n"
                    )
                    process.stdin.flush()
            except Exception as exc:
                with self._state_lock:
                    self._pending.pop(request_id, None)
                    if self._active_preview == (process, request_id):
                        self._active_preview = None
                self._schedule_restart("request write failed")
                raise RuntimeError("Qwen worker request failed") from exc
            try:
                response = response_queue.get(timeout=max(0.1, timeout))
            except queue.Empty as exc:
                with self._state_lock:
                    self._pending.pop(request_id, None)
                self._schedule_restart("request timed out")
                raise TimeoutError(f"Qwen final-pass exceeded {timeout:.1f}s") from exc
            finally:
                if priority == "preview":
                    with self._state_lock:
                        if self._active_preview == (process, request_id):
                            self._active_preview = None
            if response.get("type") == "error":
                raise RuntimeError(str(response.get("error", "Qwen worker error")))
            if response.get("type") == "cancelled":
                raise QwenRequestCancelled("Qwen preview cancelled")
            return str(response.get("text", "")).strip()

    def cancel_preview(self) -> bool:
        """Cancel only the active preview without waiting for the inference gate."""
        with self._write_lock:
            with self._state_lock:
                active = self._active_preview
                if active is None:
                    return False
                process, request_id = active
                if process is not self._process or process.stdin is None:
                    return False
            try:
                process.stdin.write(
                    json.dumps(
                        {"type": "cancel", "id": request_id},
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                process.stdin.flush()
            except Exception as exc:
                self._schedule_restart("cancel write failed")
                raise RuntimeError("Qwen preview cancellation failed") from exc
        return True

    def _schedule_restart(self, reason: str) -> None:
        with self._state_lock:
            if self._closed or self._restarting:
                return
            self._restarting = True

        def restart() -> None:
            try:
                self.say(f"[qwen] restarting after {reason}")
                self._terminate_current()
                time.sleep(0.2)
                self.start()
            except Exception as exc:
                self.say(f"[qwen] restart failed: {type(exc).__name__}: {exc}")
                with self._state_changed:
                    self._status = "failed"
                    self._state_changed.notify_all()
            finally:
                with self._state_lock:
                    self._restarting = False

        threading.Thread(
            target=restart, name="voxpill-qwen-restart", daemon=True
        ).start()

    def _terminate_current(self) -> None:
        with self._state_lock:
            process = self._process
            self._ready = False
            self._process = None
            self._active_preview = None
            pending = list(self._pending.values())
            self._pending.clear()
        for response_queue in pending:
            response_queue.put({"type": "error", "error": "worker stopped"})
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)
            except Exception:
                pass
        self._close_stderr()

    def _close_stderr(self) -> None:
        with self._state_lock:
            handle = self._stderr_handle
            self._stderr_handle = None
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass

    def close(self) -> None:
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
            self._status = "closed"
            self._state_changed.notify_all()
        self._terminate_current()
        reader = self._reader
        if reader is not None and reader is not threading.current_thread():
            reader.join(timeout=2.0)


def run_pseudo_streaming_preview(
    client: QwenFinalClient | None,
    pcm_buffer: BoundedPcmBuffer,
    recording_done: threading.Event,
    config: QwenFinalConfig,
    on_partial: Callable[[str], None],
    say: Callable[..., None] = print,
    on_failure: Callable[[Exception, bytes], None] | None = None,
    session_lock: threading.Lock | None = None,
) -> None:
    """Periodically re-decode accumulated audio without queuing stale previews."""
    last_text = ""
    while not recording_done.wait(config.preview_interval_seconds):
        if client is None or not client.is_ready or not pcm_buffer.eligible:
            continue
        pcm = pcm_buffer.to_bytes()
        duration = len(pcm) / 32000
        if duration < config.preview_min_seconds:
            continue
        if duration > config.preview_max_audio_seconds:
            say("[qwen] preview limit reached; waiting for final")
            return
        try:
            text = client.transcribe(
                pcm, config.preview_timeout_seconds, priority="preview"
            )
        except QwenRequestCancelled:
            say("[qwen] preview cancelled for final")
            return
        except Exception as exc:
            say(f"[qwen] preview failed: {type(exc).__name__}: {exc}")
            if on_failure is not None:
                on_failure(exc, pcm)
            return
        text = text.strip() if text else ""
        if text and text != last_text:
            with session_lock if session_lock is not None else nullcontext():
                if recording_done.is_set():
                    return
                last_text = text
                on_partial(text)


def recognize_final_with_fallback(
    client: QwenFinalClient | None,
    pcm: bytes,
    config: QwenFinalConfig,
    fallback: Callable[[bytes], str],
    *,
    qwen_failed: bool = False,
    cancel_event: threading.Event | None = None,
    say: Callable[..., None] = print,
) -> FinalPassResult:
    """Prefer Qwen final and invoke the lazy fallback only after failure."""
    if not qwen_failed and client is not None:
        if not client.is_ready and client.status in {"loading", "restarting"}:
            say("[qwen] waiting for worker readiness before final")
            client.wait_until_ready(config.startup_wait_seconds)
        if client.is_ready:
            try:
                text = client.transcribe(
                    pcm, config.timeout_seconds, priority="final"
                )
            except Exception as exc:
                say(f"[qwen] final failed: {type(exc).__name__}: {exc}")
            else:
                text = text.strip() if text else ""
                if text:
                    return FinalPassResult(text, "qwen")
        say(f"[qwen] final unavailable ({client.status})")
    if cancel_event is not None and cancel_event.is_set():
        return FinalPassResult("", "cancelled", "shutdown")
    text = fallback(pcm).strip()
    reason = "qwen_preview_failed" if qwen_failed else "qwen_final_failed"
    return FinalPassResult(text, "paraformer", reason)


def select_final_text(
    client: QwenFinalClient | None,
    pcm: bytes,
    paraformer_text: str,
    timeout_seconds: float,
    say: Callable[..., None] = print,
) -> FinalPassResult:
    fallback = paraformer_text.strip()
    if client is None or not client.is_ready:
        return FinalPassResult(fallback, "paraformer", "qwen_not_ready")
    try:
        qwen_text = client.transcribe(pcm, timeout_seconds)
    except Exception as exc:
        say(f"[qwen] final-pass fallback: {type(exc).__name__}: {exc}")
        return FinalPassResult(fallback, "paraformer", "qwen_error")
    qwen_text = qwen_text.strip() if qwen_text else ""
    if not qwen_text:
        say("[qwen] final-pass returned empty text; using Paraformer")
        return FinalPassResult(fallback, "paraformer", "qwen_empty")
    return FinalPassResult(qwen_text, "qwen")


def _emit(message: dict) -> None:
    try:
        sys.stdout.write(
            json.dumps(message, ensure_ascii=True, separators=(",", ":")) + "\n"
        )
        sys.stdout.flush()
    except (BrokenPipeError, OSError) as exc:
        raise SystemExit(0) from exc


def run_worker(model_dir: Path, context: str) -> int:
    started = time.perf_counter()
    try:
        import numpy as np
        import torch
        from transformers import (
            AutoModelForMultimodalLM,
            AutoProcessor,
            StoppingCriteria,
            StoppingCriteriaList,
        )

        processor = AutoProcessor.from_pretrained(model_dir, local_files_only=True)
        model = AutoModelForMultimodalLM.from_pretrained(
            model_dir,
            dtype=torch.bfloat16,
            device_map="cuda:0",
            local_files_only=True,
            low_cpu_mem_usage=True,
        ).eval()
        torch.cuda.synchronize("cuda:0")
        _emit(
            {
                "type": "ready",
                "device": "cuda:0",
                "dtype": "bfloat16",
                "load_seconds": time.perf_counter() - started,
            }
        )
    except Exception as exc:
        _emit({"type": "fatal", "error": f"{type(exc).__name__}: {exc}"})
        return 1

    requests: queue.Queue = queue.Queue()
    cancellations = WorkerCancellationRegistry()

    def read_requests() -> None:
        try:
            for line in sys.stdin:
                try:
                    request = json.loads(line)
                except json.JSONDecodeError:
                    continue
                message_type = request.get("type")
                request_id = str(request.get("id", ""))
                if message_type == "transcribe":
                    cancellations.register(request_id)
                    requests.put(request)
                elif message_type == "cancel":
                    cancellations.cancel(request_id)
                elif message_type == "shutdown":
                    cancellations.cancel_active()
                    break
        finally:
            cancellations.cancel_active()
            requests.put(None)

    threading.Thread(
        target=read_requests, name="voxpill-qwen-stdin", daemon=True
    ).start()

    class CancelCriteria(StoppingCriteria):
        def __init__(self, event: threading.Event):
            self.event = event

        def __call__(self, input_ids, scores, **kwargs):
            del scores, kwargs
            return torch.full(
                (input_ids.shape[0],),
                self.event.is_set(),
                device=input_ids.device,
                dtype=torch.bool,
            )

    while True:
        request = requests.get()
        if request is None:
            return 0
        request_id = ""
        cancel_event = threading.Event()
        try:
            request_id = str(request.get("id", ""))
            cancellations.activate(request_id, cancel_event)
            if cancel_event.is_set():
                _emit({"type": "cancelled", "id": request_id})
                continue
            pcm = base64.b64decode(request["pcm16"], validate=True)
            samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
            kwargs: dict[str, object] = {"audio": samples}
            if context:
                kwargs["prompt"] = context
            inputs = processor.apply_transcription_request(**kwargs).to(
                model.device, model.dtype
            )
            torch.cuda.synchronize("cuda:0")
            with torch.inference_mode():
                output_ids = model.generate(
                    **inputs,
                    max_new_tokens=256,
                    do_sample=False,
                    stopping_criteria=StoppingCriteriaList(
                        [CancelCriteria(cancel_event)]
                    ),
                )
            torch.cuda.synchronize("cuda:0")
            if cancel_event.is_set():
                _emit({"type": "cancelled", "id": request_id})
                continue
            generated = output_ids[:, inputs["input_ids"].shape[1] :]
            text = processor.decode(
                generated, return_format="transcription_only"
            )[0].strip()
            _emit({"type": "result", "id": request_id, "text": text})
        except Exception as exc:
            _emit(
                {
                    "type": "error",
                    "id": request_id,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        finally:
            cancellations.finish(request_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--context", default="")
    args = parser.parse_args()
    if not args.worker or args.model_dir is None:
        parser.error("--worker and --model-dir are required")
    return run_worker(args.model_dir, args.context)


if __name__ == "__main__":
    raise SystemExit(main())
