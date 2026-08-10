---
title: Windows Build and Distribution
type: workflow
updated: 2026-08-10 23:46
---

# Windows Build and Distribution

VoxPill ships as a PyInstaller `onedir` Windows x64 application. The layout keeps the 300+ MiB offline models directly available instead of extracting them on every launch. Target machines do not need Python or `uv`.

## Release Build

`build-release.bat` invokes `scripts/build-release.ps1`, which:

1. Reads the version from `pyproject.toml` and verifies all production model files.
2. Regenerates the multi-resolution warm VoxPill icon.
3. Builds into `build/release-dist/VoxPill` so a running development or prior release instance under `dist/` cannot lock the staging output.
4. Creates `dist/release/VoxPill-<version>-portable.zip`.
5. Compiles `installer/VoxPill.iss` with Inno Setup 6 or 7.
6. Writes SHA-256 hashes for the ZIP and installer to `dist/release/SHA256SUMS.txt`.

`build-portable.bat` uses the same pipeline with `-PortableOnly`, so the two distribution paths cannot drift.

## Installer Behavior

The installer is per-user and does not request elevation. It installs to `%LOCALAPPDATA%\Programs\VoxPill`, creates a Start Menu shortcut used by Windows Search, registers an HKCU uninstall entry, and offers a login-start task that is enabled by default. During migration it removes only the two legacy VoxPill startup-link names before optionally creating the packaged startup shortcut.

The installer includes Simplified Chinese and English messages. The versioned Chinese language file is stored under `installer/languages/` so builds do not depend on optional compiler language packs.

## Release Boundary

Local builds are unsigned. Code signing and SmartScreen reputation remain release-owner responsibilities. Creating or uploading a remote GitHub Release is a separate authorized operation; local artifacts alone do not publish anything.

## See Also

- [Overview](../overview.md)
- [Windows release contract](../contracts/windows-release-contract.md)
