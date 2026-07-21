"""Lightweight offline ASR + punctuation using INT8 ONNX models."""

from dataclasses import dataclass, field
from pathlib import Path
import threading
import time

import numpy as np


SR = 16000
MIN_UTTER_BYTES = SR * 2 * 3 // 10


@dataclass(frozen=True)
class AsrPipeline:
    recognizer: object
    punctuation: object


@dataclass
class StreamingAsrPipeline:
    recognizer: object
    punctuation: object
    decode_lock: threading.Lock = field(default_factory=threading.Lock)


@dataclass
class StreamingSession:
    pipeline: StreamingAsrPipeline
    stream: object
    finished: bool = False


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


def load_streaming_asr(base_dir: Path | None = None, say=print) -> StreamingAsrPipeline:
    """Load bilingual streaming Paraformer plus the existing punctuation model."""
    root = (base_dir or Path(__file__).resolve().parent) / "models"
    streaming = root / "asr-streaming"
    encoder = streaming / "encoder.int8.onnx"
    decoder = streaming / "decoder.int8.onnx"
    tokens = streaming / "tokens.txt"
    punc_model = root / "punctuation" / "model.int8.onnx"
    missing = [p for p in (encoder, decoder, tokens, punc_model) if not p.is_file()]
    if missing:
        raise FileNotFoundError(
            "Missing VoxPill streaming model files: " + ", ".join(map(str, missing))
        )

    say("[asr] loading streaming INT8 Paraformer + punctuation ...")
    started = time.perf_counter()
    import sherpa_onnx

    recognizer = sherpa_onnx.OnlineRecognizer.from_paraformer(
        encoder=str(encoder),
        decoder=str(decoder),
        tokens=str(tokens),
        num_threads=2,
        provider="cpu",
        enable_endpoint_detection=False,
    )
    punctuation = sherpa_onnx.OfflinePunctuation(
        sherpa_onnx.OfflinePunctuationConfig(
            model=sherpa_onnx.OfflinePunctuationModelConfig(
                ct_transformer=str(punc_model), num_threads=1, provider="cpu"
            )
        )
    )
    say(f"[asr] streaming ready in {time.perf_counter() - started:.1f}s")
    return StreamingAsrPipeline(recognizer=recognizer, punctuation=punctuation)


def create_streaming_session(pipeline: StreamingAsrPipeline) -> StreamingSession:
    return StreamingSession(pipeline=pipeline, stream=pipeline.recognizer.create_stream())


def accept_streaming_pcm(session: StreamingSession, pcm: bytes) -> str:
    """Feed one PCM16 chunk and return the latest non-final transcript."""
    if session.finished:
        raise RuntimeError("streaming session already finished")
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    with session.pipeline.decode_lock:
        session.stream.accept_waveform(SR, samples)
        while session.pipeline.recognizer.is_ready(session.stream):
            session.pipeline.recognizer.decode_stream(session.stream)
        return session.pipeline.recognizer.get_result(session.stream).strip()


def punctuate_streaming_text(session: StreamingSession, text: str) -> str:
    """Add punctuation to a partial transcript without racing the decoder."""
    if not text:
        return ""
    with session.pipeline.decode_lock:
        return session.pipeline.punctuation.add_punctuation(text)


def finish_streaming_session(session: StreamingSession) -> str:
    """Flush a stream once and return a punctuated final transcript."""
    if session.finished:
        raise RuntimeError("streaming session already finished")
    session.finished = True
    with session.pipeline.decode_lock:
        session.stream.accept_waveform(SR, np.zeros(SR // 2, dtype=np.float32))
        session.stream.input_finished()
        while session.pipeline.recognizer.is_ready(session.stream):
            session.pipeline.recognizer.decode_stream(session.stream)
        text = session.pipeline.recognizer.get_result(session.stream).strip()
        return session.pipeline.punctuation.add_punctuation(text) if text else ""


def transcribe(pipeline: AsrPipeline, pcm: bytes) -> str:
    """Convert mono 16 kHz signed-16-bit PCM to punctuated text."""
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    stream = pipeline.recognizer.create_stream()
    stream.accept_waveform(SR, samples)
    pipeline.recognizer.decode_stream(stream)
    text = stream.result.text.strip()
    return pipeline.punctuation.add_punctuation(text) if text else ""
