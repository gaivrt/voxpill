"""CPU-only static Paraformer ASR, punctuation, and pseudo-streaming helpers."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
import math
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
    activity_rms_floor: float = 50.0
    activity_min_seconds: float = 0.12
    activity_vad_mode: int = 2

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
            activity_rms_floor=max(
                1.0, float(values.get("activity_rms_floor", 50.0))
            ),
            activity_min_seconds=max(
                0.04, float(values.get("activity_min_seconds", 0.12))
            ),
            activity_vad_mode=max(
                0, min(3, int(values.get("activity_vad_mode", 2)))
            ),
        )


@dataclass(frozen=True)
class RecognitionTiming:
    gate_seconds: float
    decode_seconds: float
    punctuation_seconds: float
    total_seconds: float


def has_acoustic_activity(pcm: bytes, config: RecognitionConfig) -> bool:
    """Detect speech with WebRTC VAD plus conservative sustained-voice fallback."""
    import numpy as np
    import webrtcvad

    frame_samples = SR // 50  # 20 ms
    sample_count = len(pcm) // 2
    frame_count = sample_count // frame_samples
    if frame_count <= 0:
        return False
    samples = np.frombuffer(
        pcm, dtype=np.int16, count=frame_count * frame_samples
    ).astype(np.float32)
    frames = samples.reshape(frame_count, frame_samples)
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    required_frames = max(
        1, math.ceil(config.activity_min_seconds * SR / frame_samples)
    )
    if int(np.count_nonzero(rms > config.activity_rms_floor)) < required_frames:
        return False

    vad = webrtcvad.Vad(config.activity_vad_mode)
    voiced_frames = sum(
        vad.is_speech(
            pcm[index * frame_samples * 2 : (index + 1) * frame_samples * 2],
            SR,
        )
        for index in range(frame_count)
    )
    low, high = np.percentile(rms, (10, 90))
    if voiced_frames >= required_frames and high >= max(
        config.activity_rms_floor * 2.0, low * 2.5
    ):
        return True

    # A short sustained vowel has little energy variation and may be too quiet
    # for WebRTC VAD. Preserve only harmonic structure with a fundamental in
    # the human voice range; single-frequency hum and colored noise fail this.
    analysis_frame_count = min(frame_count, SR // frame_samples)
    frame_energy = rms * rms
    cumulative_energy = np.concatenate(
        (np.zeros(1, dtype=np.float32), np.cumsum(frame_energy, dtype=np.float32))
    )
    window_energy = (
        cumulative_energy[analysis_frame_count:]
        - cumulative_energy[:-analysis_frame_count]
    )
    analysis_start_frame = int(np.argmax(window_energy))
    analysis_samples = samples[
        analysis_start_frame * frame_samples
        : (analysis_start_frame + analysis_frame_count) * frame_samples
    ]
    if len(analysis_samples) < required_frames * frame_samples:
        return False
    centered = analysis_samples - float(np.mean(analysis_samples))
    windowed = centered * np.hanning(len(centered)).astype(np.float32)
    power = np.abs(np.fft.rfft(windowed)) ** 2
    frequencies = np.fft.rfftfreq(len(windowed), 1.0 / SR)
    audible = (frequencies >= 40.0) & (frequencies <= 4000.0)
    voice_fundamental = (frequencies >= 80.0) & (frequencies <= 300.0)
    total_power = float(np.sum(power[audible]))
    if total_power <= 1e-12:
        return False
    fundamental_bins = np.flatnonzero(voice_fundamental)
    fundamental_index = int(fundamental_bins[np.argmax(power[voice_fundamental])])
    fundamental_hz = float(frequencies[fundamental_index])
    harmonic = np.abs(frequencies - fundamental_hz * 2.0) <= 2.0
    fundamental_ratio = float(power[fundamental_index]) / total_power
    harmonic_ratio = float(np.sum(power[harmonic])) / total_power
    return fundamental_ratio >= 0.08 and harmonic_ratio >= 0.02


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
    def acquire(
        self,
        priority: str,
        cancel_event: threading.Event | None = None,
    ):
        if priority not in {"preview", "final"}:
            raise ValueError(f"unknown recognition priority: {priority}")
        is_final = priority == "final"
        cancelled = False
        with self._condition:
            if is_final:
                self._final_waiters += 1
            try:
                if not is_final and cancel_event is not None and cancel_event.is_set():
                    cancelled = True
                while self._active or (not is_final and self._final_waiters):
                    if (
                        not is_final
                        and cancel_event is not None
                        and cancel_event.is_set()
                    ):
                        cancelled = True
                        break
                    self._condition.wait(timeout=0.05 if cancel_event is not None else None)
                if not cancelled:
                    self._active = True
            finally:
                if is_final:
                    self._final_waiters -= 1
        if cancelled:
            yield False
            return
        try:
            yield True
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

    def recognize(
        self,
        pcm: bytes,
        *,
        priority: str = "final",
        cancel_event: threading.Event | None = None,
        on_timing: Callable[[RecognitionTiming], None] | None = None,
    ) -> str:
        started = time.perf_counter()
        with self._gate.acquire(priority, cancel_event) as acquired:
            if not acquired:
                return ""
            gate_seconds = time.perf_counter() - started
            if on_timing is None:
                return transcribe(self._pipeline, pcm)
            text, decode_seconds, punctuation_seconds = transcribe_timed(
                self._pipeline, pcm
            )
            on_timing(
                RecognitionTiming(
                    gate_seconds=gate_seconds,
                    decode_seconds=decode_seconds,
                    punctuation_seconds=punctuation_seconds,
                    total_seconds=time.perf_counter() - started,
                )
            )
            return text


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
    on_timing: Callable[[RecognitionTiming], None] | None = None,
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
        if not has_acoustic_activity(pcm, config):
            deadline = advance_preview_deadline(
                deadline, time.monotonic(), config.preview_interval_seconds
            )
            continue
        started = time.perf_counter()
        try:
            kwargs = {
                "priority": "preview",
                "cancel_event": recording_done,
            }
            if on_timing is not None:
                kwargs["on_timing"] = on_timing
            text = engine.recognize(pcm, **kwargs).strip()
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
    return transcribe_timed(pipeline, pcm)[0]


def transcribe_timed(pipeline: AsrPipeline, pcm: bytes) -> tuple[str, float, float]:
    """Transcribe PCM and expose native decode and punctuation durations."""
    import numpy as np

    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    stream = pipeline.recognizer.create_stream()
    stream.accept_waveform(SR, samples)
    decode_started = time.perf_counter()
    pipeline.recognizer.decode_stream(stream)
    decode_seconds = time.perf_counter() - decode_started
    text = stream.result.text.strip()
    punctuation_started = time.perf_counter()
    punctuated = pipeline.punctuation.add_punctuation(text) if text else ""
    punctuation_seconds = time.perf_counter() - punctuation_started
    return punctuated, decode_seconds, punctuation_seconds
