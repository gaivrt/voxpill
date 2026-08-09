---
title: 伪流式语音输入运行链路
type: workflow
updated: 2026-08-09 13:05
---

# 伪流式语音输入运行链路

## 用户交互语义

VoxPill 默认把右 Ctrl 作为 push-to-talk 热键。右 Ctrl 连续稳定 60 ms 后，应用保存当前 foreground HWND、创建一轮独立 session、开始采集 16 kHz 单声道 PCM，并在当前显示器底部中央显示不抢焦点的自动明暗 pill。按住期间，同一个 Qwen3-ASR worker 从 1.0 秒 cadence、至少 0.8 秒音频开始重识别截至当前的累积音频，结果只更新浮窗而不写入目标应用。松开后停止安排和发布 preview，并通过旁路 IPC 取消正在生成的 preview，再提交不分段的完整录音 Qwen final；Qwen 尚在启动时最多等待 15 秒，只有缺失、真实失败、final 超时/异常或空输出才懒加载静态 Paraformer 与标点模型完成一次 fallback。preview cancellation 是正常生命周期，不触发 fallback。

每轮录音都有递增的 session ID。浮窗忽略不属于当前 session 的 partial、finalizing、committed 或 dismiss 命令，防止旧任务的迟到消息关闭或覆盖新一轮浮窗。

## 数据与线程边界

```text
右 Ctrl 按下沿
  → 保存 foreground HWND
  → 创建有界 PCM buffer 与 session ID
  → 启动麦克风并显示 overlay
  → PortAudio callback 只复制 PCM chunk 并写入 SimpleQueue
  → capture worker 把 chunk 追加到 PCM buffer
  → preview worker 按间隔取得累积快照
  → Qwen 串行重识别并产生 pseudo-streaming preview

右 Ctrl 松开沿
  → 停止并关闭麦克风 stream
  → recording_done 阻止新 preview 和迟到 overlay 更新
  → request-ID cancel 终止正在生成的 preview
  → chunk sentinel 结束 capture worker
  → consumer 检查异常与最短时长
  → active preview 释放 inference gate 后立即执行完整录音 final
  → Qwen final 成功则更新 overlay
  → 确认 Qwen 失败才 lazy-load static Paraformer fallback
  → 恢复录音开始时保存的 target HWND
  → paste 或 Unicode SendInput 恰好一次
  → 可选 Enter
  → overlay committed 动画
```

主线程承载托盘消息循环；20 ms 轮询线程读取 `GetAsyncKeyState` 的物理键态。`HotkeyGate` 要求热键稳定 60 ms；任何左键按下或松开都会把 mouse guard 延长 120 ms。PortAudio callback 不做推理，只复制 chunk 到 queue；capture worker 写入线程安全、有上限的 PCM buffer。每轮最多有一个同步 preview loop，因此不会积压同一录音的旧快照；全局 request gate 串行使用 GPU，等待中的 final 优先于等待中的 preview。松键线程不获取 inference gate，而是在 session stop 同步边界后调用 `cancel_preview()`；worker 的 stdin reader 可在 generation 进行时设置 request 专属 cancellation event，Transformers stopping criterion 在 token loop 中结束 generation。cancelled response 释放 gate、丢弃 partial，且不会重启 worker或触发 Paraformer。

Qwen client 在 App 启动后立即启动独立 `%LOCALAPPDATA%\voicekey-qwen-win` Python 子进程；Torch/Transformers 不进入生产 `.venv-win`。父子进程通过继承的 stdin/stdout 传递带 request ID 的本地 JSON；PCM16 使用 base64 承载，cancel 只匹配已知的 active/queued preview ID，错误或迟到 ID 无效，final 从不登记为可取消 preview。preview 默认 8 秒 timeout、30 秒累积音频上限；final 默认 30 秒 timeout、120 秒 PCM 上限。请求超时仍会终止并后台重启 Qwen worker。本地 `LazyOfflineAsr` 在健康路径只保存路径和锁，不 import `sherpa_onnx`、不创建 ONNX session。

单轮音频、模型或剪贴板异常不会终止常驻 consumer；短于 `behavior.min_seconds`、超过 PCM 上限或双模型均为空的录音会被丢弃。poll、consumer、capture 与 preview threads 均登记在 worker 集合中；幂等 cleanup 设置 stop flag 和 recording_done、停止 Qwen 子进程、关闭现有音频 stream、给活跃 capture job 发送 sentinel，并限时 join 其他 workers，最后关闭并 join overlay UI thread。

## 浮窗呈现与定位

`LiquidGlassOverlay` 运行在独立 Win32 UI thread，通过命令队列接收状态变化。专用 ticker 以 `perf_counter` deadline 维持 60 Hz，并向 UI thread 投递自定义 `WM_APP + 1` frame message；它不依赖精度较低的 16 ms `WM_TIMER`。窗口为 topmost、layered、click-through、no-activate 的 tool window，因此显示 partial 时不会夺走输入焦点。

浮窗使用 `UpdateLayeredWindow` 提交 premultiplied BGRA frame，圆角以 per-pixel alpha 合成，不依赖 color key。`overlay.theme=auto` 在每次 show 时读取 Windows `AppsUseLightTheme`；light 使用暖白表面和深灰内容，dark 使用纯黑表面和暖白内容。也可强制 `light` 或 `dark`，非法值回退 auto。两套均增加 1 DIP 极低透明度暖灰边框，不使用渐变、投影、截图或模糊。

几何尺寸以 DIP 定义：空状态是 36 DIP pill；有文字后宽度至少 118 DIP，并按中英文视觉宽度增长，最大宽度为 440 DIP。文字始终保持单行；超出可用像素宽度时，从左侧省略旧内容并保留最新文本。声纹与实际可见文字先组成内容组，再整体水平居中，不使用固定文字左边距。同一 session 的最大宽度只增不减。首次 partial 到达后文字立即绘制，不等待 width spring 展开阈值。每次 show 仍通过输入焦点链确定 active monitor 和 effective DPI，但 pill 的水平中心始终等于 monitor work area 中线，纵向固定为工作区底部向上 22 DIP；展开与退场都围绕同一底部中心。

## 注入边界

overlay 从不编辑或回写 partial。每轮 `DecodeJob` 在录音开始时保存 target HWND；consumer 取得 punctuated final 后，先验证该 HWND 仍有效，再用 `SetForegroundWindow` 恢复并最多等待约 100 ms 确认焦点。只有恢复成功才调用 `inject.paste_text` 或 `inject.type_unicode`；目标失效或无法恢复时会 dismiss 浮窗并放弃本轮注入。默认 paste 路径通过剪贴板和 Ctrl+V 写回录音开始时的输入窗口，而不是用户在推理期间偶然切到的其他前台窗口。

## See Also

- [项目全景](../overview.md) — 定位、组件和交付边界。
- [ASR 候选模型实验](../operations/asr-benchmark.md) — 模型的实验口径与生产选型。
