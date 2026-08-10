# Static Paraformer pseudo-streaming contract

- Date: 2026-08-10
- Risk class: governed (production inference scheduling, model retirement, and resource behavior)

## Target

Replace the Qwen/Torch/CUDA production path with one CPU-only static INT8 Paraformer plus CT-Transformer punctuation pipeline. While the hotkey is held, periodically re-decode accumulated audio for pseudo-streaming preview; after release, decode the unchanged full recording once and inject exactly one final result.

## Scope

- Eagerly load one static Paraformer/punctuation pipeline before the App becomes ready.
- Serialize preview and final recognition through one model lock; do not create duplicate recognizers.
- Start preview scheduling at 1.0 second with at least 0.8 seconds of audio. Adapt the next cadence to twice the last decode time within 1–2 seconds, use monotonic deadlines, and skip missed ticks rather than queueing catch-up work.
- Reveal each new partial hypothesis one character at a time in the overlay. On revision, preserve the common prefix and replace only the changed suffix; final text bypasses animation and remains authoritative.
- Preserve bounded PCM, short-recording rejection, target HWND restoration, overlay lifecycle, clipboard behavior, hotkey mouse guard, tray cleanup, and exactly-once injection.
- Remove Qwen production/benchmark adapters, config, optional dependencies, packaging entries, tests, contracts/reviews, local checkpoint, isolated Windows runtime, and Qwen-only result artifacts.
- Keep the append-only Wiki log as historical evidence, but mark Qwen retired and describe only static Paraformer as current behavior.

## Non-goals

- True model-native streaming.
- Concurrent preview/final decode or a second Paraformer instance.
- GPU or NPU acceleration; the selected sherpa-onnx provider is CPU.
- Preserving Qwen English/code-switch accuracy or any Qwen fallback path.

## Acceptance criteria

- Production source/config/package contains no Qwen, Torch, Transformers, Accelerate, CUDA, or external model-runtime dependency.
- Static Paraformer is the only ASR model loaded and works without the NVIDIA GPU enabled.
- Preview periodically re-decodes accumulated PCM, publishes only while its session is active, and cannot publish stale text after release.
- Preview cadence remains within 1–2 seconds without drift or queued catch-up; overlay character animation does not add model decodes or delay final injection.
- Final always uses the full bounded recording and is injected at most once into the captured target window.
- Same-corpus static final metrics remain CER 10.60%, WER 20.83%, and MER 28.79%.
- Windows App steady-state working set after recognition stays below 512 MiB and no Qwen/Torch child or dedicated model VRAM remains. Do not force-trim the working set to satisfy this bound.
- Qwen checkpoint and `%LOCALAPPDATA%\voicekey-qwen-win` are deleted after exact-target verification.
- Windows tests, `py_compile`, `uv lock --check`, static WAV smoke, real microphone preview/final, cleanup validation, and one independent reviewer PASS complete.

## Required validation

- Unit tests for bounded PCM, eager single-model loading, serialized and adaptive pseudo-streaming preview, missed-deadline skipping, hypothesis revision/character reveal, and release/publication synchronization.
- Source audit plus successful microphone sessions for unchanged full-PCM final decode, exactly-once injection, and idempotent cleanup behavior.
- Re-run the fixed 12-utterance `current_paraformer` benchmark or audit an exact same-model run without scoring-path changes.
- Inspect Windows process/RAM and GPU process state after real recognition.

## Reviewer checklist

- No stale Qwen imports, dependency groups, config, package data, or current-behavior documentation.
- One recognizer instance and one serialization boundary across preview/final.
- No stale preview publication or duplicate final injection across release/cleanup races.
- Character reveal preserves stable prefixes, converges to the latest hypothesis, and never animates or changes the injected final.
- Destructive targets are exact and exclude static models and the production virtual environment.
