---
title: Windows Release Packaging Review
type: workflow
updated: 2026-08-11 01:40
---

# Windows Release Packaging Review

Contract: [Windows release packaging](../contracts/windows-release-contract.md)

Verdict: PASS

## Evidence

- Independent run: all 38 focused unittests passed, including release-version consistency.
- Full `build-release.bat` completed and produced the versioned portable ZIP, installer, and hashes.
- `pyproject.toml`, `uv.lock`, EXE metadata, Inno fallback, README, release notes, and artifact names agree on 1.0.0.
- `VoxPill.exe` is an x86-64 GUI PE with product/file version 1.0.0, bundled icon, models, and no console.
- Portable ZIP contains 160 files; runtime logs, caches, virtual environments, source tooling, build trees, credentials, and test corpus are absent.
- Both artifact hashes match `SHA256SUMS.txt`.
- Real per-user upgrade created the expected `%LOCALAPPDATA%` application, Start Menu and Startup shortcuts, and HKCU uninstall entry at version 1.0.0; the installed EXE reached ASR-ready in 3.2 seconds.
- Release staging is isolated from a running development or prior `dist` instance.

## Blocking Issues

None.

## Residual Risk

- Artifacts are unsigned and may trigger SmartScreen.
- The version consistency test uses substring checks and does not inspect `uv.lock`; current 1.0.0 metadata was also checked directly during review.
- `collect_all('sherpa_onnx')` includes a small amount of non-runtime package metadata and affects size only.

## Wiki Check

The release workflow and boundary are documented in `wiki/operations/build-and-distribution.md`; index coverage and Markdown links are current.
