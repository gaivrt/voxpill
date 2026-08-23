"""Windows process Quality-of-Service helpers."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Callable


PROCESS_POWER_THROTTLING = 4
PROCESS_POWER_THROTTLING_CURRENT_VERSION = 1
PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1


class ProcessPowerThrottlingState(ctypes.Structure):
    _fields_ = [
        ("Version", wintypes.ULONG),
        ("ControlMask", wintypes.ULONG),
        ("StateMask", wintypes.ULONG),
    ]


def enable_high_qos(
    say: Callable[..., None] = print,
    *,
    kernel32=None,
    platform_name: str | None = None,
) -> bool:
    """Opt this process out of execution-speed throttling, failing open."""
    if (platform_name or os.name) != "nt":
        return False
    try:
        dll = kernel32 or ctypes.WinDLL("kernel32", use_last_error=True)
        if kernel32 is None:
            dll.GetCurrentProcess.argtypes = ()
            dll.GetCurrentProcess.restype = wintypes.HANDLE
            dll.SetProcessInformation.argtypes = (
                wintypes.HANDLE,
                ctypes.c_int,
                ctypes.c_void_p,
                wintypes.DWORD,
            )
            dll.SetProcessInformation.restype = wintypes.BOOL
        state = ProcessPowerThrottlingState(
            PROCESS_POWER_THROTTLING_CURRENT_VERSION,
            PROCESS_POWER_THROTTLING_EXECUTION_SPEED,
            0,
        )
        if not dll.SetProcessInformation(
            dll.GetCurrentProcess(),
            PROCESS_POWER_THROTTLING,
            ctypes.byref(state),
            ctypes.sizeof(state),
        ):
            error = ctypes.get_last_error()
            say(f"[qos] HighQoS unavailable (Win32 error {error}); continuing")
            return False
        say("[qos] HighQoS enabled for foreground recognition")
        return True
    except Exception as exc:
        say(f"[qos] HighQoS unavailable ({type(exc).__name__}: {exc}); continuing")
        return False
