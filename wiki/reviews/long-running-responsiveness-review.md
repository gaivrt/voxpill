---
title: Long-running responsiveness review
type: workflow
updated: 2026-08-22 23:12
---

# Long-running Responsiveness Review

Contract: [Long-running responsiveness](../contracts/overlay-frame-scheduling-contract.md)

Verdict: PASS

## Evidence

- `SetTimer(hwnd, 1, 16, None)` drives coalescing `WM_TIMER` frames; the dedicated `PostMessageW` producer was removed and `KillTimer` runs on window destruction.
- Released previews cancel only while waiting for the recognition gate. Active native decode and all final recognition remain non-cancellable; final waiters retain priority.
- `uv run python -m unittest discover -s bench/tests -p 'test_*.py'`: 49 tests passed.
- `uv run python -m py_compile asr.py overlay.py main.py`: passed.
- `git diff --check`: passed.

## Blocking Issues

None.

## Residual Risk

The current environment cannot perform a real Win32 long-running soak; timer coalescing and destruction behavior are supported by Win32 semantics, regression checks, and source review.

## Wiki Check

The runtime pipeline, index, and log describe the current timer and preview-cancellation behavior.
