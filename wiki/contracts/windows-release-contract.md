---
title: Windows Release Packaging
type: workflow
updated: 2026-08-11 01:34
---

# Windows Release Packaging Contract

## Target

Ship VoxPill 1.0.0 as a self-contained Windows x64 application that is discoverable from Windows Search and does not require Python or `uv` on the target machine.

## Scope

- Build the existing PyInstaller `onedir` application with VoxPill icon and Windows version metadata.
- Produce a versioned portable ZIP and SHA-256 checksums.
- Produce a per-user installer with Start Menu, uninstall, and optional login-start shortcuts.
- Document local build, install, portable use, and release publishing prerequisites.

## Non-goals

- Code signing or SmartScreen reputation.
- Automatic updates, Microsoft Store/MSIX distribution, or machine-wide installation.
- Publishing to a remote GitHub Release without separate user authorization.

## Acceptance Criteria

- `VoxPill.exe` launches without a console and loads bundled ASR and punctuation models.
- Installed VoxPill appears in Windows Search through a Start Menu shortcut.
- Installer defaults to per-user installation and offers login startup without requiring elevation.
- Uninstall removes installer-owned shortcuts and application files.
- Release output includes `VoxPill-1.0.0-portable.zip`, installer when Inno Setup is available, and `SHA256SUMS.txt`.
- Existing source-based startup remains usable for development.

## Required Validation

- Run the focused Python test suite.
- Build the Windows `onedir` bundle from a clean PyInstaller work directory.
- Launch the built executable and observe the ASR-ready log entry.
- Inspect the ZIP contents, installer metadata, shortcuts/tasks, and recorded hashes.

## Risk Class

Governed: release/install configuration writes Windows application, Start Menu, startup, and uninstall state.

## Reviewer Checklist

- Correct paths for frozen runtime data and models.
- Per-user install requires no administrator rights.
- Startup and Start Menu shortcuts target the packaged executable.
- Version/icon metadata and artifact names agree with project version.
- No credentials, runtime logs, caches, or development environments enter release artifacts.
