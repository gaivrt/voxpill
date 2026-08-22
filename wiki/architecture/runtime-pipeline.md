---
title: 伪流式语音输入运行链路
type: workflow
updated: 2026-08-22 23:12
---

# 伪流式语音输入运行链路

## 用户交互语义

VoxPill 默认把右 Ctrl 作为 push-to-talk 热键。按键稳定 60 ms 后，应用保存 foreground HWND、创建 session、采集 16 kHz mono PCM，并显示不抢焦点的自动明暗 pill。按住期间，唯一的 static Paraformer 从 1.0 秒 cadence、至少 0.8 秒音频开始重识别截至当前的累积音频；结果只更新浮窗。松开后立即禁止新的 preview 调度和发布，再由同一模型识别不分段的完整录音 final。

每轮录音有递增 session ID。overlay 忽略不属于当前 session 的 partial、finalizing、committed 和 dismiss，防止旧任务覆盖新一轮浮窗。

## 数据与线程边界

```text
右 Ctrl 按下沿
  → 保存 foreground HWND
  → 创建 bounded PCM buffer 与 session ID
  → 启动麦克风并显示 overlay
  → PortAudio callback 复制 PCM chunk 到 SimpleQueue
  → capture worker 追加 PCM
  → preview worker 按 1–2 秒自适应 deadline 取得累积快照
  → static Paraformer 产生 pseudo-streaming preview
  → overlay 保留新旧 hypothesis 公共前缀，约 45ms/字展开新后缀

右 Ctrl 松开沿
  → recording_done 在线性化边界阻止新 preview/迟到发布
  → 停止并关闭麦克风 stream
  → chunk sentinel 结束 capture worker
  → consumer 检查错误、最短时长和 PCM 上限
  → final priority 识别完整 PCM
  → 更新 overlay 并恢复 target HWND
  → paste 或 Unicode SendInput 恰好一次
  → 可选 Enter 和 committed 动画
```

`RecognitionPriorityGate` 保证同一时刻只有一个 sherpa decode；等待中的 final 会越过等待中的 preview。preview 以上次 decode 耗时的两倍作为下次间隔，夹在 1–2 秒内；调度使用 monotonic deadline，超时轮次直接跳过，不会排队或并发补算。static offline decode 本身不支持中途取消，所以松键时 active preview 可以完成计算；仍在等待 gate 的 preview 则轮询 `recording_done` 并在取得 recognizer 前退出，避免连续 session 积累过期推理。`recording_done` 与 partial publication 共用 `preview_lock`，迟到结果不会再显示；final 始终不可取消并保持优先。没有第二模型、子进程 IPC、fallback 或 GPU 状态。

单轮模型或剪贴板异常不会杀死常驻 consumer。短于 `behavior.min_seconds`、超过 120 秒 PCM 上限或空 final 的录音会被丢弃。幂等 cleanup 设置 stop flag/recording_done、停止 stream、发送 capture sentinel、限时 join worker，最后关闭 overlay UI thread。

## 浮窗与注入边界

`LiquidGlassOverlay` 使用独立 Win32 UI thread、约 60 Hz 的 `WM_TIMER` 与 per-pixel-alpha layered window；Win32 timer tick 在 UI thread 忙碌时会合并，不会像独立 producer 的 `PostMessageW` 那样积累过期帧。窗口保持 topmost、click-through、no-activate，不夺取输入焦点。partial 只更新目标文本，timer 约每 45ms 显示一个新字符；ASR 修订时只回退到公共前缀，finalizing 则立即显示完整 final。auto theme 读取 Windows `AppsUseLightTheme`。文字保持单行、最大 440 DIP，溢出时保留尾部。

preview 从不编辑目标应用。consumer 取得 punctuated final 后验证并恢复录音开始时保存的 HWND，只有恢复成功才调用 `inject.paste_text` 或 `inject.type_unicode`；目标无效时 dismiss 并放弃注入。

## See Also

- [项目全景](../overview.md) — 定位、组件和交付边界。
- [ASR benchmark](../operations/asr-benchmark.md) — static baseline 指标与历史选型依据。
