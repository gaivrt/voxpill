"""Bundle resources, writable user settings, and a process-lifetime lock."""
import os
from pathlib import Path
import shutil
import sys

RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
if sys.platform == "win32":
    DATA_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else RESOURCE_DIR
elif sys.platform == "darwin":
    DATA_DIR = Path.home() / "Library/Application Support/VoxPill"
else:
    DATA_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "voxpill"
CONFIG_PATH = DATA_DIR / "config.toml"


def initialize_config():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        shutil.copyfile(RESOURCE_DIR / "config.toml", CONFIG_PATH)


def acquire_instance():
    """The returned handle must remain alive until process exit."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        dll = ctypes.WinDLL("kernel32", use_last_error=True)
        dll.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
        dll.CreateMutexW.restype = wintypes.HANDLE
        handle = dll.CreateMutexW(None, False, "Local\\GAIVR.VoxPill")
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 183:
            raise SystemExit(0)
        return handle
    import fcntl
    handle = (DATA_DIR / "instance.lock").open("a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise SystemExit(0)
    return handle
