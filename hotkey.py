"""Small state machine for filtering synthetic push-to-talk key pulses."""

from dataclasses import dataclass


@dataclass
class HotkeyGate:
    stable_seconds: float
    mouse_guard_seconds: float
    recording: bool = False
    candidate_since: float | None = None
    mouse_guard_until: float = 0.0
    previous_left: bool = False

    def update(self, checked_at: float, key_down: bool, left_down: bool) -> str | None:
        if left_down or left_down != self.previous_left:
            self.mouse_guard_until = checked_at + self.mouse_guard_seconds
        self.previous_left = left_down

        if self.recording:
            if not key_down:
                self.recording = False
                return "stop"
            return None

        if not key_down:
            self.candidate_since = None
            return None
        if self.candidate_since is None:
            self.candidate_since = checked_at
            return None
        if (
            checked_at - self.candidate_since >= self.stable_seconds
            and checked_at >= self.mouse_guard_until
        ):
            self.candidate_since = None
            self.recording = True
            return "start"
        return None
