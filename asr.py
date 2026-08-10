"""CPU-only static Paraformer ASR, punctuation, and pseudo-streaming helpers."""

from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
import threading
import time
from typing import Callable, Mapping

SR = 16000
MIN_UTTER_BYTES = SR * 2 * 3 // 10


@dataclass(frozen=True)
class AsrPipeline:
    recognizer: object
    punctuation: object


@dataclass(frozen=True)
class RecognitionConfig:
    preview_interval_seconds: float = 1.0
    preview_max_interval_seconds: float = 2.0
    preview_min_seconds: float = 0.8
    preview_max_audio_seconds: float = 30.0
    max_audio_seconds: float = 120.0

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "RecognitionConfig":
        preview_interval = max(
            0.5, float(values.get("preview_interval_seconds", 1.0))
        )
        preview_min = max(0.3, float(values.get("preview_min_seconds", 0.8)))
        return cls(
            preview_interval_seconds=preview_interval,
            preview_max_interval_seconds=max(
                preview_interval,
                float(values.get("preview_max_interval_seconds", 2.0)),
            ),
            preview_min_seconds=preview_min,
            preview_max_audio_seconds=max(
                preview_min,
                float(values.get("preview_max_audio_seconds", 30.0)),
            ),
            max_audio_seconds=max(1.0, float(values.get("max_audio_seconds", 120.0))),
        )


@dataclass
class BoundedPcmBuffer:
    max_bytes: int

    def __post_init__(self) -> None:
        self.data = bytearray()
        self.eligible = True
        self.total_bytes = 0
        self._lock = threading.Lock()

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


class RecognitionPriorityGate:
    """Serialize one recognizer while allowing waiting finals past previews."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._active = False
        self._final_waiters = 0

    @contextmanager
    def acquire(self, priority: str):
        if priority not in {"preview", "final"}:
            raise ValueError(f"unknown recognition priority: {priority}")
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


class OfflineAsr:
    """Eagerly load and serialize one static Paraformer pipeline."""

    def __init__(self, base_dir: Path | None = None, say=print, loader=None):
        self.base_dir = base_dir
        self.say = say
        self._gate = RecognitionPriorityGate()
        model_loader = loader or load_asr
        self._pipeline = model_loader(self.base_dir, self.say)

    @property
    def is_loaded(self) -> bool:
        return True

    def recognize(self, pcm: bytes, *, priority: str = "final") -> str:
        with self._gate.acquire(priority):
            return transcribe(self._pipeline, pcm)


def adaptive_preview_interval(
    decode_seconds: float,
    minimum_seconds: float,
    maximum_seconds: float,
) -> float:
    """Keep preview responsive without spending more than about half the time decoding."""
    return max(minimum_seconds, min(maximum_seconds, decode_seconds * 2.0))


def advance_preview_deadline(
    previous_deadline: float,
    finished_at: float,
    interval_seconds: float,
) -> float:
    """Return the next future cadence deadline, skipping rather than queueing missed ticks."""
    deadline = previous_deadline + interval_seconds
    if deadline <= finished_at:
        missed = int((finished_at - deadline) // interval_seconds) + 1
        deadline += missed * interval_seconds
    return deadline


def run_pseudo_streaming_preview(
    engine: OfflineAsr,
    pcm_buffer: BoundedPcmBuffer,
    recording_done: threading.Event,
    config: RecognitionConfig,
    on_partial: Callable[[str], None],
    say: Callable[..., None] = print,
    session_lock: threading.Lock | None = None,
) -> None:
    """Adaptively re-decode accumulated PCM without queuing stale previews."""
    last_text = ""
    interval = config.preview_interval_seconds
    deadline = time.monotonic() + interval
    while True:
        if recording_done.wait(max(0.0, deadline - time.monotonic())):
            return
        if not pcm_buffer.eligible:
            return
        pcm = pcm_buffer.to_bytes()
        duration = len(pcm) / (SR * 2)
        if duration < config.preview_min_seconds:
            deadline = advance_preview_deadline(
                deadline, time.monotonic(), config.preview_interval_seconds
            )
            continue
        if duration > config.preview_max_audio_seconds:
            say("[asr] preview limit reached; waiting for final")
            return
        started = time.perf_counter()
        try:
            text = engine.recognize(pcm, priority="preview").strip()
        except Exception as exc:
            say(f"[asr] preview failed: {type(exc).__name__}: {exc}")
            return
        interval = adaptive_preview_interval(
            time.perf_counter() - started,
            config.preview_interval_seconds,
            config.preview_max_interval_seconds,
        )
        if text and text != last_text:
            with session_lock if session_lock is not None else nullcontext():
                if recording_done.is_set():
                    return
                last_text = text
                on_partial(text)
        deadline = advance_preview_deadline(deadline, time.monotonic(), interval)


def load_asr(base_dir: Path | None = None, say=print) -> AsrPipeline:
    """Load quantized Paraformer ASR and CT-Transformer punctuation."""
    root = (base_dir or Path(__file__).resolve().parent) / "models"
    asr_model = root / "asr" / "model.int8.onnx"
    asr_tokens = root / "asr" / "tokens.txt"
    punc_model = root / "punctuation" / "model.int8.onnx"
    missing = [p for p in (asr_model, asr_tokens, punc_model) if not p.is_file()]
    if missing:
        raise FileNotFoundError("Missing VoxPill model files: " + ", ".join(map(str, missing)))

    say("[asr] loading INT8 ONNX Paraformer + punctuation ...")
    started = time.perf_counter()
    import sherpa_onnx

    recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
        paraformer=str(asr_model),
        tokens=str(asr_tokens),
        num_threads=2,
        provider="cpu",
    )
    punctuation = sherpa_onnx.OfflinePunctuation(
        sherpa_onnx.OfflinePunctuationConfig(
            model=sherpa_onnx.OfflinePunctuationModelConfig(
                ct_transformer=str(punc_model),
                num_threads=1,
                provider="cpu",
            )
        )
    )
    say(f"[asr] ready in {time.perf_counter() - started:.1f}s")
    return AsrPipeline(recognizer=recognizer, punctuation=punctuation)


def transcribe(pipeline: AsrPipeline, pcm: bytes) -> str:
    """Convert mono 16 kHz signed-16-bit PCM to punctuated text."""
    import numpy as np

    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    stream = pipeline.recognizer.create_stream()
    stream.accept_waveform(SR, samples)
    pipeline.recognizer.decode_stream(stream)
    text = stream.result.text.strip()
    return pipeline.punctuation.add_punctuation(text) if text else ""
