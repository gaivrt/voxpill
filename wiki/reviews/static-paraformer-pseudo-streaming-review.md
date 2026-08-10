---
title: Static Paraformer pseudo-streaming review
type: review
updated: 2026-08-10 21:31
---

# Static Paraformer pseudo-streaming review

- Contract: [Static Paraformer pseudo-streaming](../contracts/static-paraformer-pseudo-streaming-contract.md)
- Verdict: PASS

## Evidence

- Windows suite 37/37 PASS; focused suite 14/14 PASS; `py_compile` and `uv lock --check` PASS.
- Fixed 12-utterance result remains CER 10.60%, WER 20.83%, MER 28.79%, CPU RTF 0.0353 and 363.46 MiB benchmark peak working set.
- One eager `OfflineAsr` pipeline and one priority gate serialize accumulated preview and full bounded final. Release and publication share the same lock; final has one injection site and no retry/fallback path.
- Preview uses 1–2 second adaptive monotonic deadlines and skips missed ticks. Overlay preserves the common prefix, reveals one code point at a time, and applies final text immediately.
- Fourteen live microphone sessions produced preview and final results. The App then held steady at 500.3 MiB working set across eight samples, below the 512 MiB limit; no forced trim, Torch runtime, Qwen child, or VoxPill GPU compute process was present.
- Cleanup is idempotent and stops publication, capture, workers, and overlay. Current Wiki pages, index, and links are consistent.

## Residual risk

Working set was not sampled after every live session, so the exact growth curve is unknown. Full-final and cleanup behavior use source audit plus live session/restart evidence rather than additional dedicated tests, matching the revised contract and the user's decision to stop further testing.
