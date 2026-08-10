#!/usr/bin/env python3
"""Run reproducible ASR accuracy/performance benchmarks in isolated processes."""

from __future__ import annotations

import argparse
import csv
import ctypes
import json
import os
import subprocess
import sys
import time
import tomllib
from datetime import datetime
from pathlib import Path

import numpy as np

try:
    from .audio_io import read_wav
    from .metrics import ErrorScore, score
except ImportError:  # direct script execution: python bench/benchmark.py
    from audio_io import read_wav
    from metrics import ErrorScore, score


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BENCH_DIR = Path(__file__).resolve().parent
MODEL_CONFIG = BENCH_DIR / "models.toml"
PROMPTS = BENCH_DIR / "prompts.json"
DEFAULT_CORPUS = BENCH_DIR / "corpus" / "audio"
DEFAULT_RESULTS = BENCH_DIR / "results"


def load_models() -> dict[str, dict]:
    return tomllib.loads(MODEL_CONFIG.read_text(encoding="utf-8"))["models"]


def resolve_model_paths(spec: dict) -> dict:
    resolved = dict(spec)
    path_keys = {
        "model",
        "tokens",
        *spec.get("required", []),
    }
    for key in path_keys:
        if key in resolved:
            resolved[key] = str((PROJECT_ROOT / resolved[key]).resolve())
    return resolved


def validate_model_files(model_id: str, spec: dict) -> None:
    keys = {
        "offline_paraformer": ("model", "tokens"),
    }.get(spec["kind"])
    if keys is None:
        raise ValueError(f"{model_id}: unsupported kind {spec['kind']}")
    missing = [spec[key] for key in keys if not Path(spec[key]).is_file()]
    if missing:
        raise FileNotFoundError(f"{model_id}: missing model files: {missing}")


def peak_working_set_mb() -> float:
    if os.name == "nt":
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.argtypes = []
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(Counters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        process = kernel32.GetCurrentProcess()
        ok = psapi.GetProcessMemoryInfo(
            process, ctypes.byref(counters), counters.cb
        )
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
        return counters.PeakWorkingSetSize / (1024 * 1024)
    import resource

    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return usage / 1024 if sys.platform.startswith("linux") else usage / (1024 * 1024)


def load_recognizer(spec: dict, threads_override: int | None):
    kind = spec["kind"]
    import sherpa_onnx

    threads = threads_override or int(spec.get("threads", 2))
    if kind == "offline_paraformer":
        return sherpa_onnx.OfflineRecognizer.from_paraformer(
            paraformer=spec["model"], tokens=spec["tokens"], num_threads=threads
        )
    raise ValueError(f"Unsupported model kind: {kind}")


def decode_offline(recognizer, samples: np.ndarray, sample_rate: int) -> dict:
    started = time.perf_counter()
    stream = recognizer.create_stream()
    stream.accept_waveform(sample_rate, samples)
    recognizer.decode_stream(stream)
    elapsed = time.perf_counter() - started
    return {"text": stream.result.text.strip(), "inference_seconds": elapsed}


def aggregate_scores(rows: list[dict]) -> dict:
    names = {"zh": "cer", "en": "wer", "mixed": "mer"}
    output: dict[str, dict] = {}
    for category, metric_name in names.items():
        selected = [row for row in rows if row["category"] == category]
        edits = sum(row["score_edits"] for row in selected)
        units = sum(row["score_reference_units"] for row in selected)
        output[metric_name] = {
            "edits": edits,
            "reference_units": units,
            "rate": edits / units if units else None,
        }
    return output


def run_worker(
    model_id: str, corpus: Path, output: Path, threads_override: int | None
) -> dict:
    models = load_models()
    if model_id not in models:
        raise KeyError(f"Unknown model: {model_id}")
    spec = resolve_model_paths(models[model_id])
    validate_model_files(model_id, spec)
    prompts = json.loads(PROMPTS.read_text(encoding="utf-8"))
    missing_audio = [str(corpus / f"{item['id']}.wav") for item in prompts if not (corpus / f"{item['id']}.wav").is_file()]
    if missing_audio:
        raise FileNotFoundError("Missing corpus recordings: " + ", ".join(missing_audio))

    load_started = time.perf_counter()
    recognizer = load_recognizer(spec, threads_override)
    load_seconds = time.perf_counter() - load_started
    rows = []
    for item in prompts:
        wav_path = corpus / f"{item['id']}.wav"
        samples, sample_rate = read_wav(wav_path)
        duration = len(samples) / sample_rate
        decoded = decode_offline(recognizer, samples, sample_rate)
        error: ErrorScore = score(item["text"], decoded["text"], item["category"])
        row = {
            "id": item["id"],
            "category": item["category"],
            "reference": item["text"],
            "hypothesis": decoded["text"],
            "audio_seconds": duration,
            "inference_seconds": decoded["inference_seconds"],
            "rtf": decoded["inference_seconds"] / duration if duration else None,
            "first_partial_audio_ms": decoded.get("first_partial_audio_ms"),
            "score_edits": error.edits,
            "score_reference_units": error.reference_units,
            "error_rate": error.rate,
        }
        rows.append(row)
        print(f"{model_id} {item['id']}: RTF={row['rtf']:.3f} error={row['error_rate']:.3f}")

    result = {
        "model_id": model_id,
        "label": spec["label"],
        "kind": spec["kind"],
        "true_streaming": bool(spec["true_streaming"]),
        "threads": threads_override or int(spec.get("threads", 2)),
        "device": "cpu",
        "dtype": None,
        "load_seconds": load_seconds,
        "peak_working_set_mb": peak_working_set_mb(),
        "peak_gpu_reserved_mb": None,
        "mean_rtf": sum(row["rtf"] for row in rows) / len(rows),
        "corpus_rtf": sum(row["inference_seconds"] for row in rows)
        / sum(row["audio_seconds"] for row in rows),
        "metrics": aggregate_scores(rows),
        "utterances": rows,
        "created_at": datetime.now().astimezone().isoformat(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def write_summary(results: list[dict], destination: Path) -> None:
    with destination.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "model_id",
                "true_streaming",
                "threads",
                "load_seconds",
                "peak_working_set_mb",
                "peak_gpu_reserved_mb",
                "mean_rtf",
                "corpus_rtf",
                "cer",
                "wer",
                "mer",
            ],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "model_id": result["model_id"],
                    "true_streaming": result["true_streaming"],
                    "threads": result["threads"],
                    "load_seconds": result["load_seconds"],
                    "peak_working_set_mb": result["peak_working_set_mb"],
                    "peak_gpu_reserved_mb": result.get("peak_gpu_reserved_mb"),
                    "mean_rtf": result["mean_rtf"],
                    "corpus_rtf": result["corpus_rtf"],
                    "cer": result["metrics"]["cer"]["rate"],
                    "wer": result["metrics"]["wer"]["rate"],
                    "mer": result["metrics"]["mer"]["rate"],
                }
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--model")
    selection.add_argument("--all", action="store_true")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--threads", type=int)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path, help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    corpus = args.corpus.resolve()
    if args.worker:
        if not args.model or args.output is None:
            raise ValueError("worker requires --model and --output")
        run_worker(args.model, corpus, args.output.resolve(), args.threads)
        return 0

    model_ids = list(load_models()) if args.all else [args.model]
    run_dir = args.results / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=False)
    results = []
    for model_id in model_ids:
        output = run_dir / f"{model_id}.json"
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--model",
            model_id,
            "--worker",
            "--corpus",
            str(corpus),
            "--output",
            str(output),
        ]
        if args.threads:
            command.extend(["--threads", str(args.threads)])
        completed = subprocess.run(command, check=False)
        if completed.returncode != 0:
            raise SystemExit(f"benchmark failed for {model_id}: exit {completed.returncode}")
        results.append(json.loads(output.read_text(encoding="utf-8")))
    write_summary(results, run_dir / "summary.csv")
    print(f"results: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
