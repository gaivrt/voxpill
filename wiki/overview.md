---
title: VoxPill 项目全景
type: overview
updated: 2026-08-10 21:31
---

# VoxPill 项目全景

## 定位

VoxPill 是常驻 Windows 的 CPU-only 离线语音输入工具。用户按住可配置单键时，应用保存目标窗口，由唯一的 static INT8 Paraformer 以 1–2 秒自适应节奏重识别累积音频，并在当前显示器底部中央的无焦点自动明暗 pill 中逐字预览；松开后同一模型识别完整录音，再恢复目标窗口并一次写入。音频不离开本机，不依赖独立 GPU、CUDA、Torch 或外部模型 runtime。

## 用户链路

```text
按住右 Ctrl
  → 保存 foreground HWND 并录制 16 kHz mono PCM16
  → static Paraformer 定时重识别累积 PCM
  → 无焦点 pill 显示 preview
  → 松开后停止 preview 调度与发布
  → 同一模型以 final 优先级识别完整录音
  → 恢复录音开始时的 HWND
  → paste 或 Unicode SendInput 一次
  → 可选自动回车并收束浮窗
```

默认热键是右 Ctrl。短于 0.3 秒的录音会被忽略；preview 永不注入，只有非空 final 才提交。注入前必须成功恢复录音开始时保存的目标 HWND；窗口失效或无法恢复焦点时放弃本轮注入。

## 主要组件

| 组件 | 职责 |
|------|------|
| `main.py` | 单实例、配置、目标 HWND、热键轮询、录音、preview/final 调度、注入和退出清理 |
| `hotkey.py` | 60 ms 稳定窗口与点击后 120 ms mouse guard |
| `asr.py` | eager static Paraformer/punctuation、bounded PCM、single-model priority gate 和伪流式 preview |
| `overlay.py` | 独立 Win32 UI thread 与 60 Hz per-pixel-alpha pill |
| `inject.py` | Win32 Unicode 输入和剪贴板粘贴 |
| `tray.py` | 托盘图标与 Windows 明暗主题 |
| `config.toml` | 热键、注入、最短录音、preview cadence、PCM 上限和音频设备 |
| `models/` | static Paraformer、CT-Transformer 标点与 token |

## 运行模型

主线程运行托盘消息循环；轮询线程每 20 ms 读取热键物理状态；PortAudio callback 只复制 chunk；capture worker 维护有界 PCM；preview worker 按上次 decode 耗时自适应取得累积快照，过期 deadline 不补算；overlay ticker 在模型计算之外逐字展开 partial；consumer 在松键后识别完整 final 并注入。唯一的 `OfflineAsr` pipeline 在 App 就绪前加载，preview 与 final 通过一个 gate 串行，等待中的 final 越过等待中的 preview。release 与 partial publication 共用 session lock，因此 release 之后不会显示迟到 preview；final 不等待字符动画。

命名 mutex `Local\\GAIVR.VoxPill` 阻止多个进程重复加载模型。运行时直接调用 Win32 API，因此最终验证必须在 Windows 完成；WSL 只用于编辑和静态检查。

## 模型与依赖

static Paraformer 与 CT-Transformer 由固定版本 `sherpa-onnx` 在 CPU 上运行。2026-08-10 固定 Windows baseline 为 CER 10.60%、WER 20.83%、MER 28.79%、corpus RTF 0.035、约 1.16 秒加载和约 363 MiB peak working set；hypothesis 与历史同模型 run 逐条完全一致。已退役的 GPU 模型、Torch runtime 与 true-streaming Paraformer 权重不属于当前项目资产。

完整 Windows App 在 14 次成功麦克风 session 后稳定在约 500.3 MiB working set，低于 512 MiB steady-state 上限；没有强制 trim working set，也没有 VoxPill GPU compute process。未按 session 逐次取样，因此不声称具体增长拐点。

## 配置与交付

preview 默认每 1.0 秒调度、至少需要 0.8 秒音频，30 秒后停止 preview；完整 PCM 最多保留 120 秒。PyInstaller onedir/windowed 构建直接包含 static Paraformer、punctuation、配置和 sherpa-onnx，无外部运行环境。

## 当前工程状态

- `bench/tests/` 覆盖 bounded PCM、单模型 eager load、preview/final 串行和优先级、release 同步、overlay 与注入边界。
- `.venv/`、`build/`、`dist/`、`__pycache__/`、录音、结果和日志是本地状态，不进入 Wiki ingest。

## See Also

- [Wiki Index](index.md) — 全部知识页索引。
- [伪流式语音输入运行链路](architecture/runtime-pipeline.md) — preview、final、注入与 overlay 的线程和状态边界。
- [Wiki Schema](../SCHEMA.md) — Wiki 分类、约定和维护流程。
