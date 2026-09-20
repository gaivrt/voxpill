"""Text injection selected for the host desktop."""
import sys

if sys.platform == "win32":
    from inject_windows import paste_text, press_enter, type_unicode
else:
    from desktop_unix import paste_text, press_enter, type_unicode
