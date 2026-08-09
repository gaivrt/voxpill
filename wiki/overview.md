---
title: VoxPill 项目全景
type: overview
updated: 2026-08-09 13:05
---

# VoxPill 项目全景

## 定位

VoxPill 是一个常驻 Windows 的离线语音输入工具。用户稳定按住可配置的单键说话时，应用保存当时的目标窗口，由独立 Windows GPU runtime 中的 Qwen3-ASR 周期性重识别累积音频，并在当前显示器底部中央的无焦点自动明暗 pill 伪流式预览；松开后同一 Qwen worker 生成高准确率 final，再恢复目标窗口并一次写入。静态 INT8 Paraformer 与标点模型只在 Qwen 确认失败后懒加载。Torch/CUDA 不进入生产 `.venv-win`，音频不离开本机。

## 用户链路

```text
按住右 Ctrl
  → 保存 foreground HWND 并录制 16 kHz 单声道 int16 PCM
  → 同一个 Qwen worker 定时重识别累积 PCM
  → 无焦点自动明暗 pill 显示 Qwen preview
  → 松开后取消 active preview，并优先请求完整录音 Qwen final
  → Qwen 确认不可用、失败、超时或为空时才加载 static Paraformer
  → 恢复录音开始时的 HWND
  → 剪贴板粘贴或 Unicode SendInput 一次
  → 可选自动回车并收束浮窗
```

默认热键是右 Ctrl。短于 0.3 秒的录音会被忽略；preview 永不注入，只有非空 final 才通过剪贴板和 Ctrl+V 或 Unicode `SendInput` 提交。注入前必须成功恢复录音开始时保存的目标 HWND；窗口失效或无法恢复焦点时，本轮不注入。默认 paste 路径保留本次识别文本，避免目标应用延迟读取时粘贴旧内容。

## 主要组件

| 组件 | 职责 |
|------|------|
| `main.py` | 读取配置、确保单实例、保存目标 HWND、轮询物理键态、录音、调度推理与注入、跟踪 worker 和退出清理 |
| `hotkey.py` | 以 60 ms 稳定窗口和点击后 120 ms mouse guard 过滤短热键伪脉冲 |
| `asr.py` | 在首次 fallback 时才初始化 sherpa-onnx static Paraformer 和 punctuation pipeline，并串行完成离线识别 |
| `qwen_final.py` | 管理隔离 Qwen 子进程、本地 request-ID/cancel IPC、后台预加载、伪流式 preview、final 优先、timeout/restart 与 fallback 选择 |
| `overlay.py` | 运行独立 Win32 UI thread 和 60 Hz ticker，以 per-pixel alpha 在当前显示器底部中央绘制自动明暗 pill |
| `inject.py` | 封装 Win32 `SendInput`、Unicode 字符事件和剪贴板粘贴路径 |
| `tray.py` | 生成透明画布上的极简圆球与五段声纹托盘图标，并读取 Windows app theme 选择明暗配色 |
| `config.toml` | 定义热键、注入方式、剪贴板恢复、自动回车、最短录音、Qwen runtime/timeout/PCM 上限和麦克风设备 |
| `models/` | 保存 Paraformer ASR 与 CT-Transformer 标点模型及 token 数据 |

## 运行模型

应用采用多线程加隔离子进程的常驻结构：主线程运行 Windows 托盘消息循环；轮询线程每 20 ms 读取热键物理状态；PortAudio callback 只复制音频 chunk；每轮 capture worker 维护有界 PCM，preview worker 周期请求 Qwen；松键通过旁路 cancel 终止 active preview，消费线程随后以更高优先级请求完整录音 Qwen final、必要时触发 lazy fallback、恢复目标 HWND 并执行一次文本注入；父进程 reader 按 request ID 分发响应，子进程 stdin reader 并发接收 cancel；overlay UI thread 处理 Win32 消息。

托盘 tooltip 和禁用菜单标题均只显示产品名 `VoxPill`，不重复热键或录音说明。图标在 8× supersampling 下绘制后缩放到 64 px，由 Windows 继续适配 16–32 px notification area；圆球直径占 64 px 画布中的 62 px，以充分利用 Windows 的小尺寸托盘槽位。图标只有圆形底面与五段声纹：浅色主题使用暖白球与深色声纹，深色主题使用黑球与暖白声纹；录音态仅切换到另一帧声纹。常驻轮询每秒检查一次 Windows app theme，无需重启即可自动更新托盘图标。

使用 `GetAsyncKeyState` 读取真实物理键态，是避免窗口焦点变化或 `keyup` 事件丢失后持续录音的关键设计。命名 mutex `Local\\GAIVR.VoxPill` 用于阻止多个进程同时加载模型。

## 平台边界

运行时直接调用 `ctypes.WinDLL`、Win32 剪贴板 API 和 `SendInput`，因此核心应用面向 Windows，而不是通用的跨平台 Python CLI。WSL 主要适合编辑、知识维护和部分静态检查；涉及麦克风、托盘、热键、剪贴板或 portable 构建的最终验证应在 Windows 环境完成。

## 模型与依赖

Qwen3-ASR 0.6B BF16 在独立 Windows Python 3.11 runtime 中常驻 GPU，同时负责默认 1.0 秒 cadence、至少 0.8 秒音频的累积 preview 和松键后的完整录音 final。两次松键 cancel smoke 实测让 16.6 秒 active preview 在 0.574–0.837 秒内释放 gate，随后完整 final 在 1.988–2.814 秒完成且与固定 baseline 完全一致。static bilingual INT8 Paraformer 与 INT8 CT-Transformer 通过固定版本 `sherpa-onnx` 作为 CPU fallback，但健康路径不加载 ONNX session。

模型二进制是大型资产，Wiki 只维护其角色、来源、许可证、尺寸和校验信息，不读取或复制模型内容。

## 配置与交付

overlay 默认在每次 show 时读取 Windows `AppsUseLightTheme`：浅色使用暖白 `#faf9f5` 与深灰内容，深色使用纯黑与暖白内容；也可通过 `overlay.theme` 强制 `light` 或 `dark`。两套主题都使用 1 DIP 极低透明度暖灰边框，不包含渐变或投影。源码入口为 `uv run python -u main.py`，`start-voicekey.bat` 提供 Windows 前台启动，`start-voicekey-hidden.vbs` 用于无窗口启动。开机自启应在 `shell:startup` 中创建指向项目内 VBS 的 `VoxPill.lnk`，不能复制 VBS 本体；项目移动后需重建快捷方式，并移除仍指向 `dist\\voicekey\\voicekey.exe` 的旧入口。PyInstaller 以 onedir、windowed 方式生成 `dist\\VoxPill\\VoxPill.exe`，同时收集配置、模型和 sherpa-onnx 运行文件。

## 当前工程状态

- `bench/tests/` 覆盖 benchmark、伪流式 preview、旁路 cancel、final 保护/优先、request ID 隔离、bounded PCM、lazy fallback 与 overlay 状态行为。
- `README.md` 已覆盖主要用户操作、性能概况和配置示例。
- `.venv/`、`build/`、`dist/`、`__pycache__/` 和 `voxpill.log` 属于本地或生成状态，不应作为 Wiki ingest 来源。

## See Also

- [Wiki Index](index.md) — 全部知识页索引。
- [伪流式语音输入运行链路](architecture/runtime-pipeline.md) — Qwen preview/final、lazy fallback、注入与 overlay 的线程和状态边界。
- [Wiki Schema](../SCHEMA.md) — Wiki 分类、约定和维护流程。
