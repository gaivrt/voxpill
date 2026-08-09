<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/voxpill-icon-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/voxpill-icon-light.svg">
    <img src="docs/assets/voxpill-icon-light.svg" alt="VoxPill icon" width="88" height="88">
  </picture>
</p>

<h1 align="center">VoxPill</h1>

<p align="center">
  <img src="docs/assets/voxpill-hero.png" alt="VoxPill light and dark voice typing overlay" width="100%">
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
- **Multilingual Qwen recognition** — Chinese, English, and code-switching use one local GPU model.
- **Qwen pseudo-streaming preview** — accumulated audio is periodically re-decoded while you speak.
- **Consistent final text** — preview and committed text normally come from the same Qwen3-ASR worker.
- **Lazy CPU fallback** — static INT8 Paraformer loads only after Qwen is confirmed unavailable.
- **Type anywhere** — chat boxes, documents, browsers, editors, and other Windows apps.
- **Focus-safe commit** — the final text returns to the window active when recording began.
- **Native 60 Hz overlay** — per-pixel alpha, no focus stealing, light/dark auto theme.
- **Isolated runtimes** — Qwen and Torch live in a separate Windows environment; the app loads sherpa-onnx weights only on fallback.

## Demo

<p align="center">
  <img src="docs/assets/voxpill-demo.gif" alt="VoxPill streaming voice typing demo" width="100%">
</p>

## Quick start

Requirements: Windows 10/11 x64, Python 3.11+, a microphone, and
[uv](https://docs.astral.sh/uv/getting-started/installation/).

Open PowerShell:

```powershell
git clone https://github.com/gaivrt/voxpill.git
cd voxpill

$env:UV_PROJECT_ENVIRONMENT = ".venv-win"
uv sync
uv run python bench\download_models.py current_paraformer punctuation
uv run python -u main.py
```

After the first setup, `start-voicekey.bat` provides a convenient launcher.

> The model download is roughly 320 MiB. Model weights are intentionally not
> stored in this Git repository.

### Qwen runtime

Qwen is the normal recognition path. The app never imports Torch; it starts one
isolated worker in the background, uses the same worker for periodic previews
and the final transcript. Key release cancels an active preview before giving
the unchanged full-recording final request priority. If Qwen is still starting,
final recognition waits for a bounded grace
period. Only a confirmed unavailable, failed, timed-out, or empty Qwen final
causes the static Paraformer fallback to load into RAM.

The local development runtime is `%LOCALAPPDATA%\voicekey-qwen-win`. See
[`bench/README.md`](bench/README.md) for the pinned dependency and model setup.
After setup, normal startup remains:

```powershell
.\start-voicekey.bat
```

## Start with Windows

First confirm that `start-voicekey-hidden.vbs` launches VoxPill correctly. Then
press **Win+R**, enter `shell:startup`, and create a shortcut to that VBS file
inside the Startup folder.

> Create a **shortcut** to the original VBS file. Do not copy the VBS itself
> into the Startup folder, because it locates `start-voicekey.bat` relative to
> its own project directory.

You can also create the shortcut automatically. Open PowerShell in the VoxPill
project directory and run:

```powershell
$project = (Get-Location).Path
$startup = [Environment]::GetFolderPath("Startup")
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path $startup "VoxPill.lnk"))
$link.TargetPath = "$env:SystemRoot\System32\wscript.exe"
$link.Arguments = '"' + (Join-Path $project "start-voicekey-hidden.vbs") + '"'
$link.WorkingDirectory = $project
$link.Description = "VoxPill offline voice typing"
$link.Save()
```

Double-click `VoxPill.lnk` once to test it. VoxPill should appear in the system
tray without opening a console window. To disable startup, open `shell:startup`
and delete only `VoxPill.lnk`.

If Windows starts an older build, open the shortcut properties and check its
target. Remove shortcuts that point to an obsolete path such as
`dist\voicekey\voicekey.exe`; the current source launcher should reference
`start-voicekey-hidden.vbs` in this repository. Recreate the shortcut whenever
the project directory is moved.

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

[final_pass]
enabled = true
python = "%LOCALAPPDATA%\\voicekey-qwen-win\\Scripts\\python.exe"
model_dir = "bench/model_cache/qwen3-asr-0.6b-hf"
timeout_seconds = 30.0
startup_wait_seconds = 15.0
preview_interval_seconds = 1.0
preview_min_seconds = 0.8
preview_max_audio_seconds = 30.0
preview_timeout_seconds = 8.0
max_audio_seconds = 120.0
context = ""

[audio]
device = ""                  # empty = Windows default input device
```

Supported single-key hotkeys include left/right Ctrl, Alt, Shift, the grave key,
and F1–F12.

## Models

VoxPill normally uses the isolated Qwen checkpoint. Quantized ONNX assets are a lazy fallback:

| Component | Purpose | Approx. size |
|---|---|---:|
| Qwen3-ASR 0.6B HF | Multilingual pseudo-streaming preview and final | 1.46 GiB |
| Static INT8 Paraformer | Chinese/English failure fallback | 232 MiB |
| CT-Transformer | Fallback punctuation | 72 MiB |

Sources, exact file sizes, and known SHA-256 values are documented in
[`models/README.md`](models/README.md). The downloader prefers the configured
Hugging Face mirror; pass `--origin` to download from the canonical source.

## Portable build

Download the models first, then run:

```powershell
.\build-portable.bat
```

The portable application is created at `dist\VoxPill\VoxPill.exe`. Static
Paraformer and punctuation remain self-contained; the obsolete streaming model
is not packaged. Qwen still requires the configured external Windows runtime
and checkpoint. Without them the app lazily loads the bundled static fallback.

## Architecture

```text
Right Ctrl gate
  → PortAudio callback queues 16 kHz mono PCM
  → capture worker appends to a bounded buffer
  → isolated Qwen worker periodically re-decodes accumulated audio
  → native no-activate overlay renders Qwen previews
  → key release stops preview scheduling and cancels active generation
  → priority Qwen request returns the final
  → only confirmed Qwen failure lazy-loads static Paraformer
  → original target window is restored
  → text is inserted once
```

Audio callbacks only copy PCM. Preview work is serialized and never queues more
than one request per recording. Cancel travels through an out-of-band local IPC
message, so final no longer waits for redundant preview generation to finish.
Final insertion is serialized, and the overlay
owns a separate Win32 UI thread and 60 Hz ticker.

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

- Qwen preview scheduling starts at 1.0 second with at least 0.8 seconds of audio;
- two cancellation runs on a 16.6-second in-flight preview released the
  inference gate in 0.574–0.837 seconds on the development machine;
- Windows Qwen final-pass load around 8.9 seconds, corpus RTF around 0.16,
  peak process RAM around 2.31 GiB, and Torch-reserved VRAM around 1.98 GiB.

These are reference measurements, not hardware-independent guarantees.

## Acknowledgements

VoxPill is built on Qwen3-ASR, [`sherpa-onnx`](https://github.com/k2-fsa/sherpa-onnx),
and the quantized static Paraformer and CT-Transformer fallback models listed in
[`models/README.md`](models/README.md).

## Friends

- [LINUX DO](https://linux.do/) — Where possible begins.
