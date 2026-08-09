# Qwen cancellable preview contract

- Date: 2026-08-09
- Risk class: governed (production inference scheduling and release latency)

## Target

Preserve full-recording Qwen final accuracy while reducing perceived latency. Preview begins earlier, and key release cancels any active preview generation so the final request does not wait for a redundant accumulated-audio decode to finish.

## Scope

- Add an out-of-band cancel message to the existing local request-ID protocol.
- Let the worker read cancel messages while model generation is active.
- Use a Transformers stopping criterion backed by a per-request cancellation event.
- Track only the active preview request in the parent; cancellation must never target a final request.
- Treat preview cancellation as an expected lifecycle result, not as Qwen failure and not as a Paraformer trigger.
- On key release, atomically stop preview publication, request cancellation, then enqueue the unchanged full-recording final.
- Reduce default preview interval/minimum audio to improve first-text latency without allowing concurrent inference.
- Preserve final priority, timeout/restart, request-ID isolation, bounded PCM, shutdown cancellation, lazy static fallback, target restoration, and exactly-once injection.

## Non-goals

- VAD/audio segmentation or concatenated phrase final text.
- Reusing an incomplete preview as the committed final.
- Concurrent model generations or duplicate Qwen workers.
- Native audio/token streaming from Qwen.

## Acceptance criteria

- A cancel message can be written while a preview `transcribe()` call holds the inference gate.
- Worker cancellation stops generation and returns `cancelled` for the matching request ID; wrong/late IDs have no effect.
- A cancelled preview publishes no new text, does not restart Qwen, and does not load Paraformer.
- Key release cancels only the active preview and the full-recording final still uses Qwen once.
- On a long corpus WAV, cancel-to-preview-return is below 1.5 seconds and the subsequent full final matches the fixed baseline hypothesis.
- Default first preview scheduling starts at 1.0 second with at least 0.8 seconds of audio.
- Full Windows tests, compile, lock check, real microphone preview/final, cleanup validation, and one independent reviewer PASS complete.

## Required validation

- Unit tests for active-preview tracking, concurrent cancel write, wrong-ID cancellation, cancelled-preview lifecycle, and no-fallback behavior.
- Windows worker smoke that cancels an in-flight long preview, measures cancellation latency, then gets the unchanged full final.
- Full Windows production test suite, `py_compile`, `uv lock --check`, dependency isolation, and real microphone validation.

## Reviewer checklist

- IPC thread safety and stdout/write ordering.
- Cancellation ID scope and final protection.
- Deadlock/race behavior across request gate, stop, timeout, restart, and cleanup.
- No accuracy-path change to full final.
- No accidental fallback or duplicate injection after cancellation.
