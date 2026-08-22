---
title: Responsiveness deployment review
type: workflow
updated: 2026-08-22 23:24
---

# Responsiveness Deployment Review

Contracts: [Windows release](../contracts/windows-release-contract.md), [long-running responsiveness](../contracts/overlay-frame-scheduling-contract.md)

Verdict: PASS

## Evidence

- Windows Python 3.13 ran 49 tests successfully.
- The clean release build completed; portable and setup SHA-256 values match `SHA256SUMS.txt`.
- The staging executable reached ASR ready in 1.5 seconds.
- The installed executable is byte-identical to staging, and the installed instance reached ASR ready in 2.5 seconds.
- Start Menu and Startup shortcuts target the installed executable; the HKCU uninstall registration and uninstaller exist.
- Exactly one installed VoxPill process remained running after deployment.

## Blocking Issues

None.

## Residual Risk

Real speech end-to-end latency and a multi-hour Windows soak still require observation during normal use.

## Wiki Check

The release and responsiveness contracts remain accurate; no durable packaging behavior changed.
