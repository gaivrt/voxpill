---
title: Long-running responsiveness
type: workflow
updated: 2026-08-22 23:12
---

# Long-running Responsiveness Contract

## Target

Prevent stale UI frames and queued preview recognition from degrading responsiveness over time.

## Scope

- Replace the unbounded 60 Hz `PostMessageW` producer with coalescing UI-thread timer ticks.
- Cancel previews that are still waiting for the shared recognizer after recording stops.
- Preserve the existing animation cadence, rendering, no-focus window behavior, and cleanup.

## Non-goals

- Interrupt a native recognition call that has already started.
- Change recognition quality or final priority.
- Redesign the overlay visuals or interaction.

## Acceptance Criteria

- At most one timer message for the overlay is pending at a time under Win32 timer semantics.
- No dedicated ticker thread posts frame messages.
- Timer resources are stopped when the overlay window is destroyed.
- A released session's preview never starts native decoding if it was still waiting for the recognition gate.
- Existing streaming runtime tests pass, with a regression check for timer-based scheduling.

## Required Validation

- Run `uv run python -m unittest bench.tests.test_streaming_runtime`.
- Run the related test suite.

## Risk Class

Governed: performance-sensitive Win32 UI scheduling change.

## Reviewer Checklist

- Correct Win32 timer setup and teardown.
- No stale frame producer or message backlog remains.
- Waiting preview cancellation cannot cancel or starve final recognition.
- Overlay commands continue to drain while hidden and visible.
- Validation evidence is recorded.
