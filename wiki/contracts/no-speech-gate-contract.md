---
title: No-speech hallucination gate
type: workflow
updated: 2026-08-23
---

# No-Speech Hallucination Gate Contract

## Target

Prevent static Paraformer hallucinations from appearing in the overlay or being injected when the hotkey is held over silence or steady background noise.

## Scope

- Classify accumulated PCM with WebRTC VAD, short-frame energy dynamics, and a conservative harmonic fallback for quiet sustained voice.
- Skip preview decode/publication until sufficient acoustic activity exists.
- Dismiss a no-speech final without recognition or text injection.
- Log the no-speech decision and keep thresholds configurable under `[recognition]`.
- Rebuild, reinstall, and include the fix in the pending 1.0.2 release.

## Non-goals

- Add a neural VAD model or any runtime network dependency.
- Segment speech, remove pauses, or change recognized speech content.
- Treat a single click or brief impulse as speech.

## Acceptance Criteria

- Zero PCM, broadband/colored steady noise, 50/60 Hz hum, and a steady single-frequency tone do not invoke preview/final recognition.
- Speech-like multi-frame energy and every existing recorded benchmark utterance remain eligible.
- Short or quiet but sustained speech is not rejected by the absolute floor alone.
- Existing priority, cancellation, timing, and injection semantics remain unchanged for eligible audio.
- Focused tests, full Windows suite, release build, staging smoke, install, startup, and reviewer pass succeed.

## Risk Class

Governed: performance-sensitive audio gating in the production recognition path.

## Reviewer Checklist

- Numerically safe PCM/frame handling and bounded work.
- Conservative thresholds and coverage for silence, steady noise, impulses, quiet speech, and corpus audio.
- Preview and final both enforce the same predicate.
- No unrelated experimental work enters the release commit.
