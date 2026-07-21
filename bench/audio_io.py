"""Minimal mono PCM16 WAV helpers shared by recorder and benchmark."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np


SAMPLE_RATE = 16_000


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    if channels != 1:
        raise ValueError(f"{path}: expected mono WAV, got {channels} channels")
    if sample_width != 2:
        raise ValueError(f"{path}: expected PCM16 WAV, got {sample_width * 8}-bit")
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    return samples, sample_rate


def write_wav(path: Path, samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.asarray(samples, dtype=np.int16)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
