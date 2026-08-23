---
title: Windows HighQoS long-utterance latency review
type: workflow
updated: 2026-08-23
---

# Windows HighQoS Long-Utterance Latency Review

Contract: [Windows HighQoS long-utterance latency](../contracts/windows-high-qos-latency-contract.md)

Verdict: PASS

## Evidence

- Reviewer confirmed `ProcessPowerThrottling=4`, structure version 1, execution-speed control, cleared state mask, and fail-open startup behavior.
- `python -m unittest discover -s bench/tests -p "test_*.py"`: 60 tests passed in the final 1.0.2 tree.
- A 16.588-second corpus recording decoded in 0.717 seconds after `enable_high_qos`; process state queried as `control=1, state=0`.
- A 70-character overlay suffix fit measured 0.817 ms per frame after the bounded lookup change.
- Clean release build exited 0; rebuilt staging logged HighQoS enabled and ASR ready in 1.5 seconds.
- Staging and installed EXE SHA-256 both equal `d5f719b8e2765d671fe9a7f1c6541600678a84a671e5e0b633ca07399c665f2f`.
- Installed PE string versions are 1.0.2 and numeric file/product parts are 1.0.2.0; Startup and Start Menu shortcuts target the installed EXE; one installed process is running with `control=1, state=0`.
- Release hashes: portable `e826af00cea582dad28eb1df98826481da8d315154a0d4f261ff287ab9d311d2`; setup `3ac8faf242dcd94aa8fb74a446fc2b1ae83d7b51ed2cf2ebb523c8e98aebc7f2`.

## Blocking Issues

None. The initial fixed-version mismatch was corrected and independently re-checked.

## Residual Risk

Preview `audio=` timing labels use callback-time accumulated audio and can slightly exceed the exact decoded snapshot. Complex shaping and extremely narrow overlay widths have limited dedicated coverage. A real user long-utterance check remains the best final latency confirmation.

## Wiki Check

The runtime pipeline, index, and log describe the HighQoS, timing, and bounded overlay fitting behavior.
