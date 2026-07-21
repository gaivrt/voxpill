# VoxPill

<p align="center">
  <img src="docs/assets/voxpill-demo.gif" alt="VoxPill streaming voice typing demo" width="100%">
</p>

**Speak. Release. Typed.**

VoxPill is a lightweight, fully offline push-to-talk typing tool for Windows.
Hold **Right Ctrl**, speak naturally in Chinese, English, or both, then release
the key to insert the final text into the window you started from.

The live transcript appears in a compact native Windows pill. It stays centered
above the taskbar, grows smoothly without wrapping, follows the Windows light or
dark theme, and disappears after the text is committed.

## Highlights

- **Offline by design** — audio never leaves your computer.
- **Chinese + English** — one bilingual streaming model, no language switching.
- **True streaming preview** — partial results appear while you are speaking.
- **Punctuation included** — partial and final text use a bilingual punctuation model.
- **Type anywhere** — chat boxes, documents, browsers, editors, and other Windows apps.
- **Focus-safe commit** — the final text returns to the window active when recording began.
- **Native 60 Hz overlay** — per-pixel alpha, no focus stealing, light/dark auto theme.
- **Small runtime** — CPU-only `sherpa-onnx`; no PyTorch, CUDA, or cloud service.

## Quick start

Requirements: Windows 10/11 x64, Python 3.11+, a microphone, and
[uv](https://docs.astral.sh/uv/getting-started/installation/).

Open PowerShell:

```powershell
git clone https://github.com/gaivrt/voxpill.git
cd voxpill

$env:UV_PROJECT_ENVIRONMENT = ".venv-win"
uv sync
uv run python bench\download_models.py streaming_paraformer punctuation
uv run python -u main.py
```

After the first setup, `start-voicekey.bat` provides a convenient launcher.

> The model download is roughly 320 MiB. Model weights are intentionally not
> stored in this Git repository.

## Use

```text
Hold Right Ctrl  → recording starts and the live transcript appears
Release          → punctuation is finalized and the text is inserted once
```

VoxPill types text by default; it does not press Enter or send the message.
Very short recordings under 0.3 seconds are ignored. A mouse guard filters the
brief modifier pulses that some mouse drivers emit during clicking or drag selection.

中文：按住右 Ctrl 说话，松开后文字会自动写入开始录音时的窗口。默认不会自动回车发送。

## Configuration

Edit `config.toml`, then restart VoxPill:

```toml
[hotkey]
key = "ctrl_r"

[overlay]
theme = "auto"  # auto / light / dark

[behavior]
inject_method = "paste"      # paste / unicode
restore_clipboard = false
auto_enter = false
min_seconds = 0.3

[audio]
device = ""                  # empty = Windows default input device
```

Supported single-key hotkeys include left/right Ctrl, Alt, Shift, the grave key,
and F1–F12.

## Models

VoxPill uses quantized Apache-2.0 ONNX assets through `sherpa-onnx`:

| Component | Purpose | Approx. size |
|---|---|---:|
| Bilingual streaming Paraformer | Chinese/English online ASR | 237 MiB |
| CT-Transformer | Chinese/English punctuation | 80 MiB |

Sources, exact file sizes, and known SHA-256 values are documented in
[`models/README.md`](models/README.md). The downloader prefers the configured
Hugging Face mirror; pass `--origin` to download from the canonical source.

## Portable build

Download the models first, then run:

```powershell
.\build-portable.bat
```

The portable application is created at `dist\VoxPill\VoxPill.exe`. Copy the
entire `dist\VoxPill` directory to another Windows x64 computer; Python is not
required on the destination machine.

## Architecture

```text
Right Ctrl gate
  → PortAudio callback queues 16 kHz mono PCM
  → streaming Paraformer produces partial text
  → CT-Transformer adds preview punctuation
  → native no-activate overlay renders the preview
  → key release flushes one final result
  → original target window is restored
  → text is inserted once
```

Audio callbacks only copy PCM. Recognition runs in a worker, final insertion is
serialized, and the overlay owns a separate Win32 UI thread and 60 Hz ticker.

## Development

Run the source-level tests on Windows:

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-win"
uv run python -m unittest discover -s bench\tests -v
```

The `bench/` directory also contains a reproducible personal-corpus harness for
CER, WER, MER, real-time factor, first-partial position, and peak working set.
Personal recordings, model weights, generated results, virtual environments,
logs, and packaged builds are excluded from Git.

## Current development measurements

On the development Windows machine:

- first non-empty partial after roughly 1.3–1.9 seconds of speech audio;
- corpus real-time factor around 0.19;
- model load around 3.5 seconds;
- peak benchmark worker memory around 330 MiB.

These are reference measurements, not hardware-independent guarantees.

## Acknowledgements

VoxPill is built on [`sherpa-onnx`](https://github.com/k2-fsa/sherpa-onnx) and
the quantized Paraformer and CT-Transformer models listed in
[`models/README.md`](models/README.md).
