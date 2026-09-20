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

VoxPill is a lightweight, fully offline push-to-talk typing tool for Windows, with macOS and Linux X11 preview support.
Hold **Right Ctrl**, speak, then release the key to insert the final text into
the window you started from. On Windows, a compact native pill displays a pseudo-streaming
preview without stealing focus.

## Highlights

- **CPU-only recognition** — one static INT8 Paraformer pipeline; no discrete GPU, CUDA, or Torch.
- **Offline by design** — audio never leaves your computer.
- **Pseudo-streaming preview** — accumulated audio is adaptively re-decoded while you speak, then each new hypothesis is revealed character by character.
- **One-model consistency** — preview and final use the same recognizer and punctuation model.
- **Type anywhere** — chat boxes, documents, browsers, editors, and other Windows apps.
- **Focus-safe commit** — the final text returns to the window active when recording began.
- **Native 60 Hz overlay** — per-pixel alpha, no focus stealing, light/dark auto theme.

## Demo

<p align="center">
  <img src="docs/assets/voxpill-demo.gif" alt="VoxPill streaming voice typing demo" width="100%">
</p>

## Quick start

### macOS / Linux preview (1.1.1)

Download the matching archive from [GitHub Releases](https://github.com/gaivrt/voxpill/releases).
macOS builds target Apple Silicon (macOS 14+) and Intel (macOS 15+); Linux builds target x86_64, glibc 2.35+ and X11.
Move `VoxPill.app` to Applications on macOS, or extract the Linux archive and run
`./VoxPill/VoxPill` in a terminal. Linux needs `libportaudio2`, `python3-tk` and
`xclip` (`sudo apt install libportaudio2 python3-tk xclip` on Ubuntu).

macOS requires Microphone and Accessibility permission for VoxPill (or the
terminal when running from source); grant Input Monitoring if requested, then
restart. The preview is unsigned/not notarized; approve first launch through
Finder / Privacy & Security. Linux Wayland is currently unsupported.

These platforms support recording, live floating subtitles and final insertion,
with tray/menu-bar controls where available. Subtitles show recording/recognition
status, reveal previews character by character, display the final text and then
retire automatically. They do not take keyboard focus or intercept mouse clicks.
Install a CJK font on Linux if needed (`sudo apt install fonts-noto-cjk` on Ubuntu).
Keep the original window focused until insertion finishes: on macOS/Linux a
focus change cancels insertion. If the desktop has no supported tray menu,
use terminal mode and Ctrl+C to quit. Edit the hotkey by name in settings
(e.g. `ctrl_r`, `f8`, `ctrl_l+shift_l+space`); `win_l`/`win_r` mean Command on Mac.

User config and `voxpill.log` live in `~/Library/Application Support/VoxPill`
on macOS and `${XDG_CONFIG_HOME:-~/.config}/voxpill` on Linux.
From source (Python 3.11+ with Tk installed):

```sh
uv sync
uv run python bench/download_models.py --origin current_paraformer punctuation
uv run python main.py
# Build a native package on the target OS:
uv run python scripts/build_release.py
```

### Windows

Requirements: Windows 10/11 x64, Python 3.11+, a microphone, and
[uv](https://docs.astral.sh/uv/getting-started/installation/).

```powershell
git clone https://github.com/gaivrt/voxpill.git
cd voxpill

$env:UV_PROJECT_ENVIRONMENT = ".venv-win"
uv sync
uv run python bench\download_models.py current_paraformer punctuation
uv run python -u main.py
```

After setup, `start-voicekey.bat` provides a convenient launcher. The model
download is roughly 320 MiB; weights are intentionally not stored in Git.

## Start with Windows

First confirm that `start-voicekey-hidden.vbs` launches VoxPill correctly. Then
press **Win+R**, enter `shell:startup`, and create a shortcut to that VBS file
inside the Startup folder. Create a shortcut to the original file rather than
copying it, because the script locates `start-voicekey.bat` relative to itself.

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

To disable startup, delete only `VoxPill.lnk` from `shell:startup`.

## Use

```text
Hold Right Ctrl  → recording starts and the live transcript appears
Release          → the full recording is recognized and inserted once
```

VoxPill types text by default; it does not press Enter or send the message.
Recordings shorter than 0.3 seconds are ignored. A mouse guard filters brief
modifier pulses emitted by some mouse drivers.

中文：按住右 Ctrl 说话，松开后文字会自动写入开始录音时的窗口。默认不会自动回车发送。

## Configuration

Right-click the VoxPill tray icon → **设置快捷键…**, press a key or combination,
release all keys, then click **保存**. Use **重新录入** to try again or **恢复右 Ctrl**
to restore the default. The selection is saved and takes effect without restarting,
after any current recording ends and the keys are released. Recording is paused
while settings are open. Windows-reserved security shortcuts cannot be captured;
bindings may still trigger shortcuts in other apps during normal use.

中文：右键托盘图标 → **设置快捷键…**，直接按下想绑定的键或组合键，全部松开后点击 **保存**。
默认仍为右 Ctrl；支持重新录入、恢复默认和取消，设置会自动记住。

For other settings, edit `config.toml`, then restart VoxPill:

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

[recognition]
preview_interval_seconds = 1.0
preview_max_interval_seconds = 2.0
preview_min_seconds = 0.8
preview_max_audio_seconds = 30.0
max_audio_seconds = 120.0
activity_rms_floor = 50.0
activity_min_seconds = 0.12
activity_vad_mode = 2

[audio]
device = ""                  # empty = Windows default input device
```

Supported single-key hotkeys include left/right Ctrl, Alt, Shift, the grave key,
and F1–F12.

## Models

| Component | Purpose | Approx. size |
|---|---|---:|
| Static INT8 Paraformer | Chinese/English preview and final | 232 MiB |
| INT8 CT-Transformer | Chinese/English punctuation | 72 MiB |

Sources, exact sizes, and SHA-256 values are documented in
[`models/README.md`](models/README.md). The downloader prefers the configured
Hugging Face mirror; pass `--origin` for the canonical source.

## Windows app release

Download the models, then run:

```powershell
.\build-release.bat
```

The release build creates:

- `dist\release\VoxPill-1.1.1-portable.zip` — unzip and launch
  `VoxPill.exe`; no Python or `uv` is required.
- `dist\release\VoxPill-1.1.1-setup.exe` — per-user installer with a Start
  Menu entry, Windows Search discovery, uninstall support, and an optional
  login-start shortcut (enabled by default).
- `dist\release\SHA256SUMS.txt` — hashes for release verification.

The full release build requires Inno Setup 6 or 7. Run `build-portable.bat` to
build only the portable application and ZIP. The application stays as a
PyInstaller `onedir` bundle because its 300+ MiB offline models would otherwise
be unpacked again on every launch.

## Architecture

```text
Right Ctrl gate
  → PortAudio callback queues 16 kHz mono PCM
  → capture worker appends to a bounded buffer
  → one static Paraformer adaptively re-decodes accumulated audio
  → native no-activate overlay renders previews
  → key release stops preview scheduling and publication
  → the same Paraformer recognizes the full recording with final priority
  → original target window is restored
  → text is inserted once
```

Audio callbacks only copy PCM. One priority gate serializes recognition; a
waiting final passes any waiting preview, while a release/session lock prevents
late preview text from appearing. The overlay owns a separate Win32 UI thread
and 60 Hz ticker.

## Development

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-win"
uv run python -m unittest discover -s bench\tests -v
```

The personal-corpus benchmark records CER, WER, MER, RTF, load time, and peak
working set. Recordings, weights, results, environments, logs, and builds are
excluded from Git.

On the development Windows machine, the fixed static baseline measured CER
10.60%, WER 20.83%, MER 28.79%, corpus RTF 0.035, about 1.16 seconds load time,
and about 363 MiB peak model-process working set. These are reference values,
not hardware-independent guarantees.

After 14 successful microphone sessions, the full Windows App stabilized at
about 500.3 MiB working set, within its 512 MiB steady-state budget. VoxPill
does not force-trim memory at the cost of the next utterance's latency.

## Acknowledgements

VoxPill is built on [`sherpa-onnx`](https://github.com/k2-fsa/sherpa-onnx) and
the quantized Paraformer and CT-Transformer models listed in
[`models/README.md`](models/README.md).

## Friends

- [LINUX DO](https://linux.do/) — Where possible begins.
