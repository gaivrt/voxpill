"""Lightweight offline ASR + punctuation using INT8 ONNX models."""

from dataclasses import dataclass
from pathlib import Path
import threading
import time

SR = 16000
MIN_UTTER_BYTES = SR * 2 * 3 // 10


@dataclass(frozen=True)
class AsrPipeline:
    recognizer: object
    punctuation: object


class LazyOfflineAsr:
    """Load static Paraformer only when a confirmed Qwen failure needs fallback."""

    def __init__(self, base_dir: Path | None = None, say=print, loader=None):
        self.base_dir = base_dir
        self.say = say
        self._loader = loader
        self._pipeline: AsrPipeline | None = None
        self._lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        with self._lock:
            return self._pipeline is not None

    def recognize(self, pcm: bytes) -> str:
        with self._lock:
            if self._pipeline is None:
                loader = self._loader or load_asr
                self.say("[asr] Qwen unavailable; loading static Paraformer fallback")
                self._pipeline = loader(self.base_dir, self.say)
            return transcribe(self._pipeline, pcm)


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
