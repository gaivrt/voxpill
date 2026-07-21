"""Minimal adaptive VoxPill system-tray artwork."""

import os

from PIL import Image, ImageDraw


TOOLTIP = "VoxPill"

_SCALE = 8
_SIZE = 64
_LIGHT_ORB = (240, 237, 228, 255)
_LIGHT_SIGNAL = (39, 38, 36, 255)
_DARK_ORB = (5, 5, 5, 255)
_DARK_SIGNAL = (247, 246, 242, 255)


def dark_from_apps_use_light_theme(value: int) -> bool:
    """Map the Windows registry value to the corresponding dark-mode flag."""
    return not bool(value)


def system_prefers_dark() -> bool:
    """Read the current Windows app theme, defaulting to dark when unavailable."""
    if os.name != "nt":
        return True
    try:
        import winreg

        path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            light, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return dark_from_apps_use_light_theme(light)
    except (OSError, ImportError):
        return True


def _scaled_box(box):
    return tuple(round(value * _SCALE) for value in box)


def make_image(active: bool = False, *, dark: bool | None = None):
    """Return a circular 64 px icon containing one five-bar waveform frame."""
    if dark is None:
        dark = system_prefers_dark()
    orb = _DARK_ORB if dark else _LIGHT_ORB
    signal = _DARK_SIGNAL if dark else _LIGHT_SIGNAL

    canvas = Image.new(
        "RGBA", (_SIZE * _SCALE, _SIZE * _SCALE), (0, 0, 0, 0)
    )
    draw = ImageDraw.Draw(canvas)
    draw.ellipse(_scaled_box((6, 6, 58, 58)), fill=orb)

    # Two captured waveform poses make the state change feel alive without
    # adding badges, colors, borders, or a second visual language.
    heights = (12, 23, 16, 25, 12) if active else (10, 18, 26, 18, 10)
    centers = (21, 26.5, 32, 37.5, 43)
    bar_width = 3.25
    for center_x, height in zip(centers, heights):
        draw.rounded_rectangle(
            _scaled_box(
                (
                    center_x - bar_width / 2,
                    32 - height / 2,
                    center_x + bar_width / 2,
                    32 + height / 2,
                )
            ),
            radius=bar_width * _SCALE / 2,
            fill=signal,
        )

    return canvas.resize((_SIZE, _SIZE), Image.Resampling.LANCZOS)
