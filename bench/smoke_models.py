#!/usr/bin/env python3
"""Load configured ASR models and run a short silent decode in isolation."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

try:
    from .benchmark import (
        decode_offline,
        decode_online,
        decode_qwen3,
        load_models,
        load_recognizer,
        peak_gpu_reserved_mb,
        peak_working_set_mb,
        resolve_model_paths,
        synchronize_recognizer,
        validate_model_files,
    )
except ImportError:
    from benchmark import (
        decode_offline,
        decode_online,
        decode_qwen3,
        load_models,
        load_recognizer,
        peak_gpu_reserved_mb,
        peak_working_set_mb,
        resolve_model_paths,
        synchronize_recognizer,
        validate_model_files,
    )


def smoke(model_id: str) -> dict:
    spec = resolve_model_paths(load_models()[model_id])
    validate_model_files(model_id, spec)
    started = time.perf_counter()
    recognizer = load_recognizer(spec, None)
    synchronize_recognizer(recognizer)
    load_seconds = time.perf_counter() - started
    samples = np.zeros(16000, dtype=np.float32)
    if spec["kind"] == "offline_qwen3_asr":
        result = decode_qwen3(recognizer, samples, 16000)
    elif spec["kind"].startswith("online_"):
        result = decode_online(recognizer, samples, 16000)
    else:
        result = decode_offline(recognizer, samples, 16000)
    return {
        "model_id": model_id,
        "kind": spec["kind"],
        "device": getattr(recognizer, "device", "cpu"),
        "dtype": getattr(recognizer, "dtype", None),
        "load_seconds": load_seconds,
        "decode_seconds": result["inference_seconds"],
        "peak_working_set_mb": peak_working_set_mb(),
        "peak_gpu_reserved_mb": peak_gpu_reserved_mb(recognizer),
        "text": result["text"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("models", nargs="*")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    available = load_models()
    selected = list(available) if args.all else args.models
    if not selected:
        parser.error("pass model IDs or --all")
    unknown = sorted(set(selected) - set(available))
    if unknown:
        parser.error(f"unknown models: {', '.join(unknown)}")
    if args.worker:
        # ASCII JSON remains readable even when the Windows console code page is not UTF-8.
        print(json.dumps(smoke(selected[0]), ensure_ascii=True))
        return 0
    for model_id in selected:
        command = [sys.executable, str(Path(__file__).resolve()), model_id, "--worker"]
        completed = subprocess.run(command, check=False)
        if completed.returncode != 0:
            raise SystemExit(f"smoke test failed for {model_id}: exit {completed.returncode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
