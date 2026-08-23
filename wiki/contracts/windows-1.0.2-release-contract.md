---
title: Windows 1.0.2 release
type: workflow
updated: 2026-08-23
---

# Windows 1.0.2 Release Contract

## Target

Publish the reviewed HighQoS long-utterance latency and no-speech hallucination fixes as GitHub release `v1.0.2`.

## Scope

- Commit only the HighQoS, timing, overlay fitting, no-speech gate, version, tests, dependency lock, and directly related documentation.
- Push the reviewed commit and annotated `v1.0.2` tag to `origin/main`.
- Publish the existing portable ZIP, installer, and SHA-256 manifest.
- Download or query the published assets and verify names, sizes, and hashes.

## Non-goals

- Include the local rolling-final or stable-prefix experiment work.
- Change ASR models, recognition text for eligible audio, hotkey, injection behavior, or preview cadence.
- Sign the Windows binaries.

## Acceptance Criteria

- `origin/main`, tag `v1.0.2`, and the GitHub Release target the same reviewed commit.
- Release title and version metadata agree on 1.0.2.
- Assets are public, downloadable, and match local SHA-256 values.
- The working tree retains all unrelated experiment changes without committing them.

## Required Validation

- Re-run the Windows test suite and `git diff --check` before commit.
- Inspect the exact staged diff and commit contents.
- Verify remote refs, release metadata, asset names/sizes, and downloaded hashes.

## Risk Class

Governed: remote Git push, tag, and public GitHub release.

## Reviewer Checklist

- No experiment files or unrelated user changes are committed.
- Version and release assets match the reviewed local 1.0.2 build.
- Remote commit, tag, release, and hashes are internally consistent.
