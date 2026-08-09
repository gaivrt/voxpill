#!/usr/bin/env python3
"""Cancel an active Qwen preview, then verify the unchanged full final."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import threading
import time
import tomllib
import wave


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qwen_final import QwenFinalClient, QwenFinalConfig, QwenRequestCancelled


WAV = ROOT / "bench" / "corpus" / "audio" / "en-long.wav"
BASELINE = (
    ROOT / "bench" / "results" / "20260808-234215" / "qwen3_asr_0_6b.json"
)


def main() -> int:
    values = tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))
    config = QwenFinalConfig.from_mapping(values["final_pass"], ROOT)
    with wave.open(str(WAV), "rb") as wav:
        pcm = wav.readframes(wav.getnframes())
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    expected = next(
        item["hypothesis"] for item in baseline["utterances"] if item["id"] == "en-long"
    )
    client = QwenFinalClient(config)
    if not client.start() or not client.wait_until_ready(30):
        status = client.status
        client.close()
        raise RuntimeError(f"Qwen worker did not become ready: {status}")

    preview_outcome = []

    def preview() -> None:
        try:
            client.transcribe(pcm, config.preview_timeout_seconds, priority="preview")
            preview_outcome.append("completed")
        except QwenRequestCancelled:
            preview_outcome.append("cancelled")
        except Exception as exc:
            preview_outcome.append(f"error:{type(exc).__name__}:{exc}")

    thread = threading.Thread(target=preview, name="cancel-smoke-preview")
    thread.start()
    deadline = time.monotonic() + 2
    while client._active_preview is None and time.monotonic() < deadline:
        time.sleep(0.005)
    time.sleep(0.25)
    cancel_started = time.perf_counter()
    cancel_sent = client.cancel_preview()
    thread.join(3)
    cancel_seconds = time.perf_counter() - cancel_started
    final_started = time.perf_counter()
    final = client.transcribe(pcm, config.timeout_seconds, priority="final")
    final_seconds = time.perf_counter() - final_started
    client.close()

    result = {
        "audio_seconds": len(pcm) / 32000,
        "cancel_sent": cancel_sent,
        "preview_outcome": preview_outcome,
        "cancel_seconds": cancel_seconds,
        "final_seconds": final_seconds,
        "final": final,
        "baseline": expected,
        "final_matches_baseline": final == expected,
    }
    print(json.dumps(result, ensure_ascii=False))
    if not cancel_sent or preview_outcome != ["cancelled"]:
        return 2
    if cancel_seconds >= 1.5 or final != expected:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
