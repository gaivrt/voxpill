# Qwen pseudo-streaming and lazy fallback contract

- Date: 2026-08-09
- Risk class: governed (production ASR pipeline and performance-sensitive runtime change)

## Target

Make the persistent Qwen3-ASR worker the only normally resident recognizer. While recording, periodically re-decode the accumulated PCM with Qwen and show that result as a pseudo-streaming preview. Load the offline Paraformer model only after Qwen is confirmed unavailable or a final Qwen request fails.

## Scope

- Remove streaming Paraformer from application startup and recording sessions.
- Capture each recording into a thread-safe bounded PCM buffer.
- Run one Qwen preview request at a time, using accumulated-audio snapshots at a configurable interval.
- Stop scheduling previews on key release; final Qwen requests take priority over waiting preview requests.
- Wait briefly for a Qwen worker that is still starting before declaring it unavailable.
- Lazily load static INT8 Paraformer plus punctuation on the first confirmed fallback and reuse it thereafter.
- Preserve single final injection, target-window restoration, hotkey behavior, cleanup, and the isolated Qwen Windows runtime.
- Update tests, configuration, packaging metadata, README, schema, and runtime wiki.

## Non-goals

- Native token/audio streaming support inside Qwen3-ASR.
- A second resident preview model, vLLM, WSL inference, or GPU model duplication.
- Unloading Paraformer again after a rare fallback has loaded it.
- Bundling the external Qwen Python runtime and checkpoint into the portable build.

## Acceptance criteria

- Normal startup loads no Paraformer and imports no `sherpa_onnx` through the application ASR module.
- After Qwen is ready, a recording longer than the preview threshold produces Qwen preview updates and exactly one Qwen final injection.
- A final request waits behind at most the active preview and is preferred over queued previews.
- Qwen loading is awaited for a bounded startup grace period; missing runtime/model, fatal preload, timeout, request error, or empty final triggers one static Paraformer transcription.
- Paraformer remains unloaded throughout healthy Qwen recordings.
- Audio memory and preview work are bounded; stale preview results never overwrite a stopped or newer session.
- Cleanup leaves no Qwen worker or application-owned recording/preview thread.
- Targeted and full Windows tests, compile, lock check, healthy-path smoke, and forced-fallback smoke pass.

## Required validation

- Unit tests for config bounds, thread-safe PCM snapshots, final-priority scheduling, Qwen preview lifecycle, and lazy Paraformer loading.
- Full Windows production-environment test suite and Python compile.
- `uv lock --check` and production dependency isolation check.
- Real Windows recording showing Qwen preview followed by Qwen final with Paraformer still unloaded.
- Forced Qwen failure showing one lazy static Paraformer load and successful fallback.
- One independent reviewer pass after implementation and validation.

## Reviewer checklist

- Correctness and exactly-once injection.
- Request ordering, races, stale preview suppression, and cleanup.
- Lazy-load guarantee and fallback boundaries.
- Bounded memory/GPU work and absence of duplicate resident models.
- Documentation and configuration consistency.
