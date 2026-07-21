#!/usr/bin/env python3
"""Interactively record the benchmark prompts with the selected microphone."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import sounddevice as sd

try:
    from .audio_io import SAMPLE_RATE, write_wav
except ImportError:  # direct script execution: python bench/record_corpus.py
    from audio_io import SAMPLE_RATE, write_wav


BENCH_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompts", type=Path, default=BENCH_DIR / "prompts.json")
    parser.add_argument("--output", type=Path, default=BENCH_DIR / "corpus" / "audio")
    parser.add_argument("--device", help="sounddevice input device name or index")
    parser.add_argument("--redo", action="store_true", help="overwrite existing recordings")
    parser.add_argument("--list-devices", action="store_true")
    return parser.parse_args()


def parse_device(value: str | None) -> str | int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def main() -> int:
    args = parse_args()
    if args.list_devices:
        print(sd.query_devices())
        return 0
    prompts = json.loads(args.prompts.read_text(encoding="utf-8"))
    device = parse_device(args.device)
    args.output.mkdir(parents=True, exist_ok=True)
    print("每条语料：Enter 开始，正常朗读，再按 Enter 停止。Ctrl+C 可随时退出。")
    for index, prompt in enumerate(prompts, start=1):
        output = args.output / f"{prompt['id']}.wav"
        if output.exists() and not args.redo:
            print(f"[{index}/{len(prompts)}] skip existing: {output.name}")
            continue
        print(f"\n[{index}/{len(prompts)}] {prompt['category']}\n{prompt['text']}")
        input("Enter 开始录音...")
        frames: list[np.ndarray] = []

        def callback(indata, frame_count, time_info, status):
            del frame_count, time_info
            if status:
                print(f"[audio] {status}", file=sys.stderr)
            frames.append(indata.copy())

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            device=device,
            callback=callback,
        ):
            input("● REC — Enter 停止...")
        if not frames:
            print("没有收到音频，跳过。", file=sys.stderr)
            continue
        samples = np.concatenate(frames, axis=0).reshape(-1)
        write_wav(output, samples)
        print(f"saved {output.name}: {len(samples) / SAMPLE_RATE:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
