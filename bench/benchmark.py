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
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Qwen3Recognizer:
    model: object
    processor: object
    torch: object
    device: str
    dtype: str
    max_new_tokens: int
    context: str


def load_models() -> dict[str, dict]:
    return tomllib.loads(MODEL_CONFIG.read_text(encoding="utf-8"))["models"]


def resolve_model_paths(spec: dict) -> dict:
    resolved = dict(spec)
    path_keys = {
        "model",
        "tokens",
        "encoder",
        "decoder",
        "joiner",
        "model_dir",
        *spec.get("required", []),
    }
    for key in path_keys:
        if key in resolved:
            resolved[key] = str((PROJECT_ROOT / resolved[key]).resolve())
    return resolved


def validate_model_files(model_id: str, spec: dict) -> None:
    keys = {
        "offline_paraformer": ("model", "tokens"),
        "online_paraformer": ("encoder", "decoder", "tokens"),
        "offline_wenet_ctc": ("model", "tokens"),
        "offline_fire_red_ctc": ("model", "tokens"),
        "offline_qwen3_asr": tuple(spec.get("required", ())),
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
    if kind == "offline_qwen3_asr":
        try:
            import torch
            from transformers import AutoModelForMultimodalLM, AutoProcessor
        except ImportError as exc:
            raise RuntimeError(
                "Qwen benchmark dependencies are missing; run "
                "`uv sync --group qwen-asr` first"
            ) from exc
        device = str(spec.get("device", "cuda:0"))
        dtype_name = str(spec.get("dtype", "bfloat16"))
        if device.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError("Qwen3-ASR benchmark requires an available CUDA device")
        if dtype_name == "bfloat16" and device.startswith("cuda"):
            if not torch.cuda.is_bf16_supported():
                raise RuntimeError("configured CUDA device does not support bfloat16")
        try:
            dtype = getattr(torch, dtype_name)
        except AttributeError as exc:
            raise ValueError(f"unsupported torch dtype: {dtype_name}") from exc
        if device.startswith("cuda"):
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats(device)
        processor = AutoProcessor.from_pretrained(
            spec["model_dir"], local_files_only=True
        )
        model = AutoModelForMultimodalLM.from_pretrained(
            spec["model_dir"],
            dtype=dtype,
            device_map=device,
            local_files_only=True,
            low_cpu_mem_usage=True,
        ).eval()
        return Qwen3Recognizer(
            model=model,
            processor=processor,
            torch=torch,
            device=device,
            dtype=dtype_name,
            max_new_tokens=int(spec.get("max_new_tokens", 256)),
            context=str(spec.get("context", "")),
        )

    import sherpa_onnx

    threads = threads_override or int(spec.get("threads", 2))
    if kind == "offline_paraformer":
        return sherpa_onnx.OfflineRecognizer.from_paraformer(
            paraformer=spec["model"], tokens=spec["tokens"], num_threads=threads
        )
    if kind == "online_paraformer":
        return sherpa_onnx.OnlineRecognizer.from_paraformer(
            encoder=spec["encoder"],
            decoder=spec["decoder"],
            tokens=spec["tokens"],
            num_threads=threads,
            enable_endpoint_detection=False,
        )
    if kind == "offline_wenet_ctc":
        return sherpa_onnx.OfflineRecognizer.from_wenet_ctc(
            model=spec["model"], tokens=spec["tokens"], num_threads=threads
        )
    if kind == "offline_fire_red_ctc":
        return sherpa_onnx.OfflineRecognizer.from_fire_red_asr_ctc(
            model=spec["model"], tokens=spec["tokens"], num_threads=threads
        )
    raise ValueError(f"Unsupported model kind: {kind}")


def synchronize_recognizer(recognizer) -> None:
    if isinstance(recognizer, Qwen3Recognizer) and recognizer.device.startswith("cuda"):
        recognizer.torch.cuda.synchronize(recognizer.device)


def decode_offline(recognizer, samples: np.ndarray, sample_rate: int) -> dict:
    started = time.perf_counter()
    stream = recognizer.create_stream()
    stream.accept_waveform(sample_rate, samples)
    recognizer.decode_stream(stream)
    elapsed = time.perf_counter() - started
    return {"text": stream.result.text.strip(), "inference_seconds": elapsed}


def decode_online(recognizer, samples: np.ndarray, sample_rate: int) -> dict:
    stream = recognizer.create_stream()
    chunk_samples = max(1, int(sample_rate * 0.1))
    first_partial_audio_ms: float | None = None
    started = time.perf_counter()
    fed = 0
    for offset in range(0, len(samples), chunk_samples):
        chunk = samples[offset : offset + chunk_samples]
        stream.accept_waveform(sample_rate, chunk)
        fed += len(chunk)
        while recognizer.is_ready(stream):
            recognizer.decode_stream(stream)
        if first_partial_audio_ms is None and recognizer.get_result(stream):
            first_partial_audio_ms = fed * 1000 / sample_rate
    stream.accept_waveform(sample_rate, np.zeros(int(sample_rate * 0.5), dtype=np.float32))
    stream.input_finished()
    while recognizer.is_ready(stream):
        recognizer.decode_stream(stream)
    elapsed = time.perf_counter() - started
    return {
        "text": recognizer.get_result(stream),
        "inference_seconds": elapsed,
        "first_partial_audio_ms": first_partial_audio_ms,
    }


def decode_qwen3(
    recognizer: Qwen3Recognizer, samples: np.ndarray, sample_rate: int
) -> dict:
    feature_rate = int(recognizer.processor.feature_extractor.sampling_rate)
    if sample_rate != feature_rate:
        raise ValueError(
            f"Qwen3-ASR expects {feature_rate} Hz audio, got {sample_rate} Hz"
        )
    request = {"audio": samples}
    if recognizer.context:
        request["prompt"] = recognizer.context
    inputs = recognizer.processor.apply_transcription_request(**request).to(
        recognizer.model.device, recognizer.model.dtype
    )
    if recognizer.device.startswith("cuda"):
        recognizer.torch.cuda.synchronize(recognizer.device)
    started = time.perf_counter()
    with recognizer.torch.inference_mode():
        output_ids = recognizer.model.generate(
            **inputs,
            max_new_tokens=recognizer.max_new_tokens,
            do_sample=False,
        )
    if recognizer.device.startswith("cuda"):
        recognizer.torch.cuda.synchronize(recognizer.device)
    elapsed = time.perf_counter() - started
    generated_ids = output_ids[:, inputs["input_ids"].shape[1] :]
    text = recognizer.processor.decode(
        generated_ids, return_format="transcription_only"
    )[0]
    return {"text": text.strip(), "inference_seconds": elapsed}


def peak_gpu_reserved_mb(recognizer) -> float | None:
    if not isinstance(recognizer, Qwen3Recognizer):
        return None
    if not recognizer.device.startswith("cuda"):
        return None
    return recognizer.torch.cuda.max_memory_reserved(recognizer.device) / (1024 * 1024)


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
    synchronize_recognizer(recognizer)
    load_seconds = time.perf_counter() - load_started
    rows = []
    for item in prompts:
        wav_path = corpus / f"{item['id']}.wav"
        samples, sample_rate = read_wav(wav_path)
        duration = len(samples) / sample_rate
        if spec["kind"] == "offline_qwen3_asr":
            decoded = decode_qwen3(recognizer, samples, sample_rate)
        elif spec["kind"].startswith("online_"):
            decoded = decode_online(recognizer, samples, sample_rate)
        else:
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
        "threads": (
            None
            if spec["kind"] == "offline_qwen3_asr"
            else threads_override or int(spec.get("threads", 2))
        ),
        "device": getattr(recognizer, "device", "cpu"),
        "dtype": getattr(recognizer, "dtype", None),
        "load_seconds": load_seconds,
        "peak_working_set_mb": peak_working_set_mb(),
        "peak_gpu_reserved_mb": peak_gpu_reserved_mb(recognizer),
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
