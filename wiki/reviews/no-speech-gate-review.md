---
title: No-speech hallucination gate review
type: workflow
updated: 2026-08-23
---

# No-Speech Hallucination Gate Review

Contract: [No-speech hallucination gate](../contracts/no-speech-gate-contract.md)

Verdict: PASS

## Evidence

- The Windows suite passed 60 tests, including silence, impulse, white/colored noise, 60 Hz hum, steady 220 Hz tone, quiet multi-harmonic voice, and leading-silence regressions.
- All 12 recorded corpus utterances remain eligible at full and 25% amplitude; sustained multi-harmonic voice remains eligible at amplitudes 100, 260, 1000, and 5000.
- The 120-second noise gate remains bounded and measured about 24 ms.
- The final clean PyInstaller analysis and bundle include `webrtcvad.py`, `_webrtcvad.cp313-win_amd64.pyd`, and `webrtcvad-wheels` metadata.
- Reviewer independently ran both staging and installed `--smoke-acoustic-gate`; each exited 0 after evaluating silence and synthesized voice.
- Staging and installed EXE SHA-256 both equal `d5f719b8e2765d671fe9a7f1c6541600678a84a671e5e0b633ca07399c665f2f`.

## Blocking Issues

None. The initial continuous-voice, steady-noise, leading-silence, and packaging blockers were corrected and independently re-checked.

## Residual Risk

Heuristic VAD can still encounter unusual real microphone noise not represented by the synthetic matrix. A real silent-hold user check remains useful but is not a release blocker.

## Wiki Check

The runtime pipeline, index, and log describe the shared preview/final gate and its bounded fallback.
