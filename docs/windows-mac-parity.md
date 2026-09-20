# Windows experience → macOS acceptance checklist

Baseline: Windows implementation at `v1.1.1`, inspected in `overlay.py`,
`main.py`, `hotkey_dialog.py`, `inject_windows.py`, `tray.py` and
`installer/VoxPill.iss`. This checklist covers behavior, not just a successful build.

| Area | Windows behavior / acceptance target | Earlier Mac gap |
| --- | --- | --- |
| Recording | Physical Right Ctrl / chord, 60 ms stability gate, 120 ms mouse guard, release of any chord key stops | Already shared |
| Initial pill | 36×36 logical pixels; 260 ms ease-out entrance; four animated monochrome bars | Large static caption with one pulsing dot |
| Expansion | 118–440 px single-line pill, up to 40 px tall; spring coefficient .17, damping .70; width never shrinks within a recording | Immediate resize, different size limits |
| Transcript | Unicode characters every 45 ms; reconcile changed prefix; fit newest suffix, no wrapping | Present, but separate visual implementation |
| Recognition | Four bars speed up from 5.2 to 8.0; same preview/final model; stale sessions excluded | Dot without equivalent recognition animation |
| Exit | Shrink toward 14×14; text fades in 120 ms; full exit 340 ms | Abrupt disappearance after a delay |
| Placement | Bottom center of active input monitor, 22 px above usable edge; DPI-aware | Pointer monitor only |
| Window behavior | Never activate/focus; click-through; transparent corners; light/dark/auto | Basic panel present |
| Hotkey settings | Press/release to record single key or chord; re-record, default, cancel; suppress capture; defer live switch until keys released | Required typing key names |
| Input target | Restore original recording window before insertion; reject missing/invalid target | Cancelled whenever user changed focus |
| Injection | Clipboard paste by default; Unicode alternative; optional clipboard restoration / Enter; no duplicate punctuation | Clipboard failure had no Unicode fallback |
| Tray | Idle/recording artwork, live theme, current shortcut, settings, exit | Theme always dark; Windows key labels |
| Startup/install | GUI launch, user settings preserved, single instance, optional login startup, clean exit | App bundle present, no login control |
| Audio/errors | CPU/offline, silent/short/overlong handling, continued operation after per-recording error, bounded PCM, logs | Already shared |

Verification must include native macOS ARM64 and Intel builds, actual native
window frame recordings (both themes), timeline/geometry checks against the
Windows animation code, focus/click-through tests, hotkey capture tests, input
target restoration tests, and packaged ASR checks. Hosted runners cannot replace
hands-on microphone, third-party app, multi-monitor and macOS permission approval
checks; those must remain explicitly unverified when unavailable.

Platform differences: macOS uses Command+V, Control/Option/Command names,
Accessibility/Microphone permissions, an Applications bundle and per-user login
agent. Windows HighQoS is Windows-specific; macOS does not expose that API.
Developer ID signing/notarization requires an Apple identity and is not supplied
by a passing build. Linux is outside this parity update.

## Implemented and verification scope

- Animation: Mac presents the existing Windows raster frames through NSImageView.
  All 276 sampled frames match the published Windows motion reference for geometry,
  text, phase and opacity. The previous Mac label/dot renderer was removed.
- Native window checks: both themes, Unicode, long-text tail, stale sessions,
  non-key/non-main panel, unchanged focused test window, empty mouse interception,
  auto-exit and helper-process shutdown run on both native Mac architectures.
- Shortcut UI: press/release capture, retry/default/cancel, native Mac labels and
  saving are implemented; packaged UI smoke feeds a captured Right Control gesture.
  Global physical event interception requires permissions and remains a manual check.
- Original-target restoration: Accessibility window/control capture, raise,
  activation, focus verification and invalid-target rejection are implemented and
  exercised with API doubles. Third-party application behavior is not certified.
- Login startup: per-user LaunchAgent creation/removal is checked in a temporary
  directory; an actual logout/login cycle remains a manual check.
- Shared audio/ASR behavior and packaged model loading/inference are tested;
  an actual microphone session on a Mac remains a manual check.

Native-window GIFs are captured from the rendered AppKit view, positioned using
the real panel geometry and opacity, with recorded frame timing. They demonstrate
the UI event-loop output; they are not a recording of a real microphone session.
