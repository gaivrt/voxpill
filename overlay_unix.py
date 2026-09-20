"""Non-activating native subtitles, isolated from the tray's GUI main thread."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

from overlay import display_text, reconcile_partial_text, reveal_next_character
from overlay import LiquidGlassOverlay as WindowsOverlay, OverlayLayout, expanded_layout


class AnimatedSubtitleState(WindowsOverlay):
    """Mac uses the actual Windows animation/renderer, with a native presenter."""
    def __init__(self):
        self._init_visual_state()

    @property
    def session(self):
        return self._state["active_id"]

    @property
    def text(self):
        return self._state["text"]

    @property
    def status(self):
        return "hidden" if self._state["phase"] == "hidden" else self._state["status"]

    def apply(self, command, session, text, now):
        state = self._state
        if command == "show":
            state.update(active_id=session, phase="showing", phase_started=now,
                         text="", target_text="", next_character_at=now,
                         status="listening", max_layout=OverlayLayout(36, 36, 0))
        elif session == self.session:
            if command == "partial" and state["status"] == "listening":
                target = display_text(text)
                state["text"] = reconcile_partial_text(state["text"], target)
                state["target_text"] = target
                state["next_character_at"] = now
                state["max_layout"] = expanded_layout(state["max_layout"], target)
            elif command == "finalizing":
                if text:
                    state["text"] = state["target_text"] = display_text(text)
                    state["max_layout"] = expanded_layout(state["max_layout"], state["text"])
                state["status"] = command
            elif command in {"committed", "dismiss"}:
                if text and command == "committed":
                    state["text"] = state["target_text"] = display_text(text)
                state.update(phase="exiting", phase_started=now, status=command)

    def tick(self, now):
        # The native presenter advances shared motion and text together once/frame.
        pass


@dataclass
class SubtitleState:
    session: int | None = None
    text: str = ""
    target: str = ""
    status: str = "hidden"
    hide_at: float | None = None
    next_character: float = 0

    def apply(self, command, session, text, now):
        if command == "show":
            self.session, self.text, self.target = session, "", ""
            self.status, self.hide_at, self.next_character = "listening", None, now
        elif session == self.session:
            if command == "partial" and self.status == "listening":
                self.target = display_text(text)
                self.text = reconcile_partial_text(self.text, self.target)
            elif command == "finalizing":
                self.status = "finalizing"
                if text:
                    self.text = self.target = display_text(text)
            elif command == "committed":
                self.text = self.target = display_text(text)
                self.status, self.hide_at = "committed", now + 0.8
            elif command == "dismiss":
                self.status, self.hide_at = "dismiss", now + 0.15

    def tick(self, now):
        if self.hide_at is not None and now >= self.hide_at:
            self.session, self.text, self.target = None, "", ""
            self.status, self.hide_at = "hidden", None
        elif self.status == "listening" and now >= self.next_character:
            self.text = reveal_next_character(self.text, self.target)
            self.next_character = now + 0.045


class LiquidGlassOverlay:
    """Small JSON pipe keeps AppKit/Tk on a separate process's main thread."""
    def __init__(self, say=print, theme="auto"):
        command = [sys.executable]
        if not getattr(sys, "frozen", False):
            command.append(str(Path(__file__).with_name("main.py")))
        command += ["--overlay-worker", theme]
        self._say = say
        self._queue = queue.SimpleQueue()
        self._process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         text=True, encoding="utf-8", bufsize=1)
        ready = threading.Event()
        result = []

        def read_ready():
            result.append(self._process.stdout.readline().strip())
            ready.set()

        threading.Thread(target=read_ready, daemon=True).start()
        if not ready.wait(15) or result != ["READY"]:
            self._process.kill()
            self._process.wait()
            raise RuntimeError("Subtitle window failed to start; check the desktop session and log.")
        self._sender = threading.Thread(target=self._send, name="voxpill-subtitles", daemon=True)
        self._sender.start()

    def _send(self):
        try:
            while True:
                event = self._queue.get()
                self._process.stdin.write(json.dumps(event, ensure_ascii=False) + "\n")
                self._process.stdin.flush()
                if event[0] == "close":
                    break
        except (OSError, ValueError) as exc:
            self._say(f"[overlay] subtitle process stopped: {exc}")
        finally:
            self._process.stdin.close()

    def show(self, session):
        self._put(("show", session, ""))

    def partial(self, session, text):
        self._put(("partial", session, text))

    def finalizing(self, session, text=""):
        self._put(("finalizing", session, text))

    def committed(self, session, text):
        self._put(("committed", session, text))

    def dismiss(self, session):
        self._put(("dismiss", session, ""))

    def _put(self, event):
        # A dead GUI helper must not accumulate messages or stop transcription.
        if self._sender.is_alive():
            self._queue.put(event)

    def close(self):
        self._queue.put(("close", -1, ""))
        self._sender.join(timeout=2)
        try:
            self._process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()
        self._process.stdout.close()


def run_worker(theme="auto", smoke_dir=None):
    """Run a GUI event loop on this helper's main thread; EOF exits with parent."""
    from overlay_native import MacPanel, X11Panel
    if sys.stdout is None:
        sys.stdout = os.fdopen(1, "w", encoding="utf-8", closefd=False)
    if sys.stdin is None:
        sys.stdin = os.fdopen(0, "r", encoding="utf-8", closefd=False)
    panel = MacPanel(theme) if sys.platform == "darwin" else X11Panel(theme)
    state = AnimatedSubtitleState() if sys.platform == "darwin" else SubtitleState()
    events = queue.SimpleQueue()
    failure = []
    start = time.monotonic()
    next_frame = start
    smoke_step = 0
    if smoke_dir:
        Path(smoke_dir).mkdir(parents=True, exist_ok=True)
        panel.prepare_focus_test()
    else:
        def read_commands():
            try:
                for line in sys.stdin:
                    events.put(json.loads(line))
            finally:
                events.put(("close", -1, ""))
        threading.Thread(target=read_commands, daemon=True).start()
    print("READY", flush=True)

    def tick():
        nonlocal smoke_step, next_frame
        try:
            now = time.monotonic()
            if smoke_dir:
                elapsed = now - start
                if smoke_step == 0:
                    events.put(("show", 1, ""))
                    smoke_step = 10
                elif smoke_step == 10 and elapsed > 0.7:
                    events.put(("partial", 1, "你好，VoxPill 正在显示实时字幕。Speak, release, typed."))
                    smoke_step = 1
                elif smoke_step == 1 and elapsed > 2.8:
                    panel.assert_focus_unchanged()
                    assert state.text, "No partial subtitle rendered"
                    panel.snapshot(Path(smoke_dir) / "partial.png")
                    events.put(("finalizing", 1, "最终字幕：你好，世界。Hello, world!"))
                    smoke_step = 2
                elif smoke_step == 2 and elapsed > 3.2:
                    panel.assert_focus_unchanged()
                    panel.snapshot(Path(smoke_dir) / "final.png")
                    events.put(("finalizing", 1, "这是一段很长的字幕，需要保留最新内容。" * 30 + "末尾文字 END"))
                    smoke_step = 3
                elif smoke_step == 3 and elapsed > 3.6:
                    panel.assert_focus_unchanged()
                    panel.snapshot(Path(smoke_dir) / "long.png")
                    events.put(("committed", 1, "最终字幕：你好，世界。Hello, world!"))
                    smoke_step = 4
                elif smoke_step == 4 and elapsed > 4.8:
                    assert state.status == "hidden", "Subtitle did not retire"
                    panel.assert_focus_unchanged()
                    events.put(("show", 2, ""))
                    events.put(("partial", 1, "stale subtitle"))
                    events.put(("dismiss", 2, ""))
                    smoke_step = 5
                elif smoke_step == 5 and elapsed > 5.2:
                    assert state.status == "hidden"
                    if sys.platform == "darwin":
                        panel.save_recording(Path(smoke_dir))
                    panel.close()
                    return
            while not events.empty():
                command, session, text = events.get()
                if command == "close":
                    panel.close()
                    return
                state.apply(command, session, text, now)
            state.tick(now)
            panel.render(state)
            if smoke_dir and sys.platform == "darwin":
                panel.record_frame(now - start, state)
            next_frame = max(next_frame + 1 / 60, time.monotonic())
            panel.after(max(1, round((next_frame - time.monotonic()) * 1000)), tick)
        except BaseException as exc:
            failure.append(exc)
            panel.close()

    panel.after(16, tick)
    panel.run()
    if failure:
        raise failure[0]
