---
title: Windows 1.0.1 release
type: workflow
updated: 2026-08-22 23:35
---

# Windows 1.0.1 Release Contract

## Target

Publish the long-running responsiveness fixes as GitHub release `v1.0.1`.

## Scope

- Version the current overlay frame-coalescing and stale-preview cancellation fixes as 1.0.1.
- Commit only the responsiveness implementation, tests, release metadata, and related Wiki pages.
- Build and validate the Windows portable ZIP and per-user installer.
- Push the reviewed commit and tag, then publish both artifacts and checksums to GitHub.

## Non-goals

- Publish the local rolling-final or stable-prefix experiment work.
- Change recognition accuracy, models, or configuration defaults.
- Sign the Windows binaries.

## Acceptance Criteria

- Version metadata agrees on 1.0.1.
- Windows tests and clean release build pass.
- Staging executable reaches ASR ready.
- ZIP/setup hashes agree with `SHA256SUMS.txt`.
- GitHub `main`, tag `v1.0.1`, and release target the reviewed commit.
- Release assets are downloadable and match local hashes.

## Required Validation

- Run all Windows tests.
- Build with `build-release.bat`.
- Smoke-test the staging executable.
- Verify artifact contents, hashes, commit scope, remote refs, and published assets.

## Risk Class

Governed: public release and remote repository mutation.

## Reviewer Checklist

- No unrelated experiment files enter the commit or artifacts.
- Timer coalescing and waiting-preview cancellation remain covered by tests.
- Version, tag, release name, filenames, and executable metadata agree.
- Remote release assets match local SHA-256 values.
