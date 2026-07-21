#!/usr/bin/env python3
"""VoxPill — 全局流式语音输入：按住右 Ctrl 预览，松开提交 final。

PC 麦克风 → INT8 ONNX Paraformer + 标点恢复 → 文本注入。常驻进程，开机自启，
托盘图标可右键退出。脱胎自 Buddy 的 companion，完全不依赖硬件 / 串口 / BLE。

热键用 GetAsyncKeyState **轮询真实物理键态**（而非监听键盘事件），所以天生免疫
"按住时焦点被抢走、keyup 事件丢失导致录音卡死"的 stuck-key 问题——物理松开必停。

线程：
  - 主线程：托盘图标消息循环（pystray.Icon.run，Windows 要求跑在主线程）
  - 轮询线程：每 20ms 读热键物理状态，按下沿开录音、松开沿把成段 PCM 入队
  - 流式线程：从 chunk queue 增量 decode，把 partial 发给 no-focus overlay
  - 消费线程：等待 final → 标点恢复 → 注入 → overlay 收束退场
  - PortAudio 回调线程：只复制 PCM chunk 并入队
  缺 pystray/pillow 时退化为：主线程消费 + Ctrl+C 退出。

    uv run python -u main.py
"""
import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
import itertools
import queue
import sys
import threading
import time
from pathlib import Path

import sounddevice as sd

import inject
from hotkey import HotkeyGate
from asr import (
    SR,
    accept_streaming_pcm,
    create_streaming_session,
    finish_streaming_session,
    load_streaming_asr,
    punctuate_streaming_text,
)
from overlay import LiquidGlassOverlay

APP_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)

try:
    import tomllib
except ModuleNotFoundError:               # Python < 3.11
    tomllib = None

try:
    import pystray
    import tray
    TRAY_OK = True
except Exception:                         # 缺 pystray/pillow → 退化到 Ctrl+C 模式
    TRAY_OK = False

if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.GetForegroundWindow.argtypes = ()
user32.GetForegroundWindow.restype = wintypes.HWND
user32.IsWindow.argtypes = (wintypes.HWND,)
user32.IsWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.SetForegroundWindow.restype = wintypes.BOOL

# Prevent startup shortcut + manual launch from loading two model copies.
_instance_mutex = kernel32.CreateMutexW(None, False, "Local\\GAIVR.VoxPill")
if not _instance_mutex:
    raise ctypes.WinError(ctypes.get_last_error())
if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
    raise SystemExit(0)

# 按键名 → Windows Virtual-Key Code。按住该键录音，松开转写。
# 0xA2/0xA3 区分左右 Ctrl；0x11 是任意 Ctrl。
VK = {
    "ctrl_r": 0xA3, "ctrl_l": 0xA2, "ctrl": 0x11,
    "alt_r": 0xA5, "alt_l": 0xA4, "alt": 0x12,
    "shift_r": 0xA1, "shift_l": 0xA0, "shift": 0x10,
    "`": 0xC0, "grave": 0xC0,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}
POLL_S = 0.02   # 物理键态轮询间隔（s）；20ms 的按下→录音延迟无感
VK_LBUTTON = 0x01
HOTKEY_STABLE_S = 0.06
MOUSE_GUARD_S = 0.12

_logfile = None


@dataclass
class DecodeJob:
    session_id: int
    session: object
    target_hwnd: int
    chunks: queue.SimpleQueue = field(default_factory=queue.SimpleQueue)
    done: threading.Event = field(default_factory=threading.Event)
    byte_count: int = 0
    final: str = ""
    error: BaseException | None = None


def say(*a):
    msg = " ".join(str(x) for x in a)
    if sys.stdout is not None:
        print(msg, flush=True)
    if _logfile is not None:          # 无框(vbs)模式下日志落文件，出问题能查
        try:
            _logfile.write(time.strftime("%H:%M:%S ") + msg + "\n")
            _logfile.flush()
        except Exception:
            pass


def load_config():
    if tomllib is None:
        return {}
    path = APP_DIR / "config.toml"
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def parse_device(d):
    if d is None or d == "":
        return None
    try:
        return int(d)
    except (ValueError, TypeError):
        return d


def key_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def activate_target(hwnd: int) -> bool:
    """Restore the window focused when recording began before injecting final text."""
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    if user32.GetForegroundWindow() == hwnd:
        return True
    if not user32.SetForegroundWindow(hwnd):
        return False
    for _ in range(10):
        if user32.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.01)
    return False


def main():
    global _logfile
    try:    # 每次启动覆盖：日志只留本次运行，足够排查无框模式的问题
        _logfile = open(APP_DIR / "voxpill.log", "w", encoding="utf-8")
    except Exception:
        _logfile = None

    cfg = load_config()
    hk, bh, au = cfg.get("hotkey", {}), cfg.get("behavior", {}), cfg.get("audio", {})
    ov = cfg.get("overlay", {})

    key_name = str(hk.get("key", "ctrl_r")).lower()
    hotkey_vk = VK.get(key_name)
    if hotkey_vk is None:
        say(f"[config] 不认识的 key='{key_name}'，回退到 ctrl_r")
        key_name, hotkey_vk = "ctrl_r", VK["ctrl_r"]
    auto_enter = bool(bh.get("auto_enter", False))
    restore_clipboard = bool(bh.get("restore_clipboard", False))
    min_bytes = int(SR * 2 * float(bh.get("min_seconds", 0.3)))
    inject_method = str(bh.get("inject_method", "paste")).lower()
    device = parse_device(au.get("device"))

    model = load_streaming_asr(APP_DIR, say)
    glass = LiquidGlassOverlay(say, theme=str(ov.get("theme", "auto")).lower())
    say(f"\n就绪 — 按住 {key_name} 说话，松开提交。\n")

    work = queue.Queue()
    st = {"stream": None, "icon": None, "job": None}
    stop_flag = threading.Event()
    cleanup_started = threading.Event()
    session_ids = itertools.count(1)
    workers: set[threading.Thread] = set()
    workers_lock = threading.Lock()

    def launch_worker(target, *, name, args=()):
        def run():
            try:
                target(*args)
            finally:
                with workers_lock:
                    workers.discard(threading.current_thread())

        thread = threading.Thread(target=run, name=name, daemon=True)
        with workers_lock:
            workers.add(thread)
        thread.start()
        return thread

    def set_icon(active):
        ic = st["icon"]
        if ic is not None:
            try:
                ic.icon = tray.make_image(active)   # idle 蓝 / 录音橙
            except Exception:
                pass

    def audio_cb(indata, n, t, status):
        del n, t
        if status:
            say(f"[audio] {status}")
        job = st["job"]
        if job is not None:
            pcm = indata.copy().tobytes()
            job.byte_count += len(pcm)
            job.chunks.put(pcm)

    def decode_job(job):
        last_partial = ""
        try:
            while True:
                pcm = job.chunks.get()
                if pcm is None:
                    break
                partial = accept_streaming_pcm(job.session, pcm)
                if partial and partial != last_partial:
                    last_partial = partial
                    glass.partial(
                        job.session_id,
                        punctuate_streaming_text(job.session, partial),
                    )
            job.final = finish_streaming_session(job.session)
            glass.finalizing(job.session_id, job.final)
        except BaseException as exc:
            job.error = exc
        finally:
            job.done.set()

    def start_rec():
        session_id = next(session_ids)
        job = DecodeJob(
            session_id,
            create_streaming_session(model),
            int(user32.GetForegroundWindow() or 0),
        )
        st["job"] = job
        glass.show(session_id)
        try:
            stream = sd.InputStream(
                samplerate=SR, channels=1, dtype="int16",
                device=device, callback=audio_cb
            )
            stream.start()
            st["stream"] = stream
            launch_worker(
                decode_job,
                args=(job,),
                name=f"voxpill-decode-{session_id}",
            )
            set_icon(True)
            say("● REC")
        except Exception:
            st["job"] = None
            glass.dismiss(session_id)
            raise

    def stop_rec():
        stream = st["stream"]
        job = st["job"]
        st["stream"] = None
        st["job"] = None
        set_icon(False)
        if stream is not None:
            try:
                stream.stop()      # 阻塞到回调结束，之后读 frames 无竞争
                stream.close()
            except Exception as e:  # USB 麦克风中途拔出等：别让轮询线程崩
                say(f"[audio] 关闭录音异常：{e}")
        if job is not None:
            job.chunks.put(None)
        return job

    def poll_loop():
        # 直接读物理键态：松开就一定停，免疫丢失的 keyup（stuck-key）。
        gate = HotkeyGate(HOTKEY_STABLE_S, MOUSE_GUARD_S)
        while not stop_flag.is_set():
            checked_at = time.perf_counter()
            left = key_down(VK_LBUTTON)
            now = key_down(hotkey_vk)
            action = gate.update(checked_at, now, left)
            if action == "start":
                try:
                    start_rec()
                except Exception as e:   # 麦克风被占用/无权限：别让轮询线程崩
                    gate.recording = False
                    say(f"[audio] 打不开麦克风：{e}")
            elif action == "stop":
                job = stop_rec()
                if job is not None:
                    work.put(job)
            time.sleep(POLL_S)

    def consume_loop():
        while not stop_flag.is_set():
            try:
                # 带 timeout：无 timeout 的 get 在 Windows 下吞掉 Ctrl+C，杀不掉进程
                job = work.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                job.done.wait()
                dur = job.byte_count / (SR * 2)
                if job.error is not None:
                    glass.dismiss(job.session_id)
                    raise job.error
                if job.byte_count < min_bytes:
                    say(f"■ ({dur:.1f}s) 太短，忽略")
                    glass.dismiss(job.session_id)
                    continue
                text = job.final
                say(f'  → "{text}"')
                if text:
                    # 推理较慢时，用户可能已经按住热键开始下一句。等这次录音
                    # 松开后再注入，避免上一句在讲话过程中突然插入当前窗口。
                    while key_down(hotkey_vk) and not stop_flag.wait(POLL_S):
                        pass
                    if stop_flag.is_set():
                        glass.dismiss(job.session_id)
                        continue
                    if not activate_target(job.target_hwnd):
                        glass.dismiss(job.session_id)
                        raise RuntimeError("录音开始时的目标窗口已失效或无法恢复焦点")
                    if inject_method == "unicode":
                        inject.type_unicode(text)
                    else:
                        inject.paste_text(text, restore_clipboard=restore_clipboard)
                    if auto_enter:
                        inject.press_enter()
                    glass.committed(job.session_id, text)
                else:
                    glass.dismiss(job.session_id)
            except Exception as e:
                # 单次音频、模型或剪贴板异常不能杀掉常驻消费线程；否则后续
                # 录音只会不断排队，表面上就像 VoxPill 永久“卡住”。
                say(f"[worker] 本次转写/注入失败：{type(e).__name__}: {e}")
            finally:
                work.task_done()

    def cleanup():
        if cleanup_started.is_set():
            return
        cleanup_started.set()
        stop_flag.set()
        stream = st["stream"]             # 原子取，避免与 poll 线程 double-stop
        st["stream"] = None
        if stream is not None:            # 退出时还在录音 → 兜底停流
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        job = st["job"]
        st["job"] = None
        if job is not None:
            job.chunks.put(None)
            glass.dismiss(job.session_id)
        current = threading.current_thread()
        with workers_lock:
            pending = list(workers)
        for worker in pending:
            if worker is not current:
                worker.join(timeout=2.0)
        glass.close()

    launch_worker(poll_loop, name="voxpill-hotkey-poll")

    if TRAY_OK:
        # 托盘图标占用主线程消息循环，消费循环挪到后台线程。
        launch_worker(consume_loop, name="voxpill-final-consumer")

        def on_quit(icon, item):
            say("退出。")
            cleanup()
            icon.stop()

        title = f"VoxPill · 按住 {key_name} 流式听写"
        menu = pystray.Menu(
            pystray.MenuItem(title, None, enabled=False),
            pystray.MenuItem("退出", on_quit),
        )
        icon = pystray.Icon("voxpill", tray.make_image(False), title, menu)
        st["icon"] = icon
        try:
            icon.run()          # 阻塞主线程直到 on_quit
        finally:
            cleanup()
    else:
        say("[tray] 托盘不可用（缺 pystray/pillow），Ctrl+C 退出。")
        try:
            consume_loop()      # 主线程跑，可被 Ctrl+C 打断
        except KeyboardInterrupt:
            say("\nstopped.")
        finally:
            cleanup()


if __name__ == "__main__":
    main()
