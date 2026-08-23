---
title: Windows HighQoS long-utterance latency
type: workflow
updated: 2026-08-23
---

# Windows HighQoS Long-Utterance Latency Contract

## Target

Keep startup-launched VoxPill recognition on performance cores and prevent long overlay text from consuming excessive UI-thread work.

## Scope

- Opt the Windows process out of execution-speed power throttling before model load.
- Fail open with a diagnostic log when the Win32 QoS call is unavailable.
- Record recognition gate-wait, ASR decode, punctuation, and total final latency.
- Replace per-frame linear suffix trimming with a bounded lookup for long overlay text.
- Version, build, install, restart, and validate the local Windows application as 1.0.2.

## Non-goals

- Change models, recognition text, injection behavior, or preview cadence.
- Interrupt a native preview decode already in progress.
- Publish or push a remote GitHub release without separate confirmation.

## Acceptance Criteria

- Windows HighQoS configuration uses `ProcessPowerThrottling`, current structure version, execution-speed control, and a cleared state mask.
- A failed QoS call never prevents VoxPill from starting.
- Timing logs distinguish gate wait, decode, punctuation, and total recognition time.
- Long-text fitting returns the same visible suffix without scanning every suffix sequentially.
- Focused tests, related Windows suite, packaged smoke test, local install, single-instance check, and startup shortcut check pass.

## Risk Class

Governed: performance-sensitive Win32 scheduling and local deployment.

## Reviewer Checklist

- Correct Win32 structure, constants, and fail-open behavior.
- No recognition-result or gate-priority regression.
- Long-text fitting preserves ellipsis and width bounds.
- Validation evidence covers HighQoS timing and installed artifact identity.
