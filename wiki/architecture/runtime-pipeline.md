---
title: 流式语音输入运行链路
type: workflow
updated: 2026-07-21 17:21
---

# 流式语音输入运行链路

## 用户交互语义

VoxPill 默认把右 Ctrl 作为 push-to-talk 热键。右 Ctrl 连续稳定 60 ms 后，应用保存当前 foreground HWND、创建一轮独立 session、开始采集 16 kHz 单声道 PCM，并在当前显示器底部中央显示不抢焦点的自动明暗 pill；按住期间，bilingual streaming Paraformer 持续解码，partial 经 CT-Transformer 恢复标点后只用于更新浮窗，不写入目标应用。松开右 Ctrl 后停止采集并 flush recognizer；满足最短录音时长且 final 非空时，应用先恢复录音开始时的目标 HWND，再把 final 只注入一次，注入完成后浮窗才收束消失。

每轮录音都有递增的 session ID。浮窗忽略不属于当前 session 的 partial、finalizing、committed 或 dismiss 命令，防止旧任务的迟到消息关闭或覆盖新一轮浮窗。

## 数据与线程边界

```text
右 Ctrl 按下沿
  → 保存 foreground HWND
  → 创建 streaming recognizer stream 与 session ID
  → 启动麦克风并显示 overlay
  → PortAudio callback 只复制 PCM chunk 并写入 SimpleQueue
  → decode worker 串行 accept/decode，产生 partial preview

右 Ctrl 松开沿
  → 停止并关闭麦克风 stream
  → chunk sentinel 触发 recognizer flush
  → 追加 0.5 秒静音、input_finished、decode 至不可继续
  → final 文本恢复标点
  → consumer 检查异常、时长和非空文本
  → 恢复录音开始时保存的 target HWND
  → paste 或 Unicode SendInput 恰好一次
  → 可选 Enter
  → overlay committed 动画
```

主线程承载托盘消息循环；20 ms 轮询线程读取 `GetAsyncKeyState` 的物理键态。`HotkeyGate` 要求热键稳定 60 ms；任何左键按下或松开都会把 mouse guard 延长 120 ms，因此连续点击、拖选或鼠标驱动伴随的短 modifier 脉冲不会创建录音 session。PortAudio callback 不做推理；每轮 decode worker 处理增量识别和 partial 标点；consumer 串行负责 final 注入。online decode、partial/final 标点恢复共用 pipeline 的 `decode_lock`。若上一句尚在等待注入时用户已开始下一句，consumer 会等右 Ctrl 再次松开后才提交上一句。

单轮音频、模型或剪贴板异常不会终止常驻 consumer；短于 `behavior.min_seconds` 的录音和空 final 会被丢弃。poll、consumer 与 decode threads 均登记在 worker 集合中；幂等 cleanup 设置 stop flag、关闭现有音频 stream、给活跃 decode job 发送 sentinel，并限时 join 其他 workers，最后关闭并 join overlay UI thread。overlay 自己也会停止并 join ticker。

## 浮窗呈现与定位

`LiquidGlassOverlay` 运行在独立 Win32 UI thread，通过命令队列接收状态变化。专用 ticker 以 `perf_counter` deadline 维持 60 Hz，并向 UI thread 投递自定义 `WM_APP + 1` frame message；它不依赖精度较低的 16 ms `WM_TIMER`。窗口为 topmost、layered、click-through、no-activate 的 tool window，因此显示 partial 时不会夺走输入焦点。

浮窗使用 `UpdateLayeredWindow` 提交 premultiplied BGRA frame，圆角以 per-pixel alpha 合成，不依赖 color key。`overlay.theme=auto` 在每次 show 时读取 Windows `AppsUseLightTheme`；light 使用暖白表面和深灰内容，dark 使用纯黑表面和暖白内容。也可强制 `light` 或 `dark`，非法值回退 auto。两套均增加 1 DIP 极低透明度暖灰边框，不使用渐变、投影、截图或模糊。

几何尺寸以 DIP 定义：空状态是 36 DIP pill；有文字后宽度至少 118 DIP，并按中英文视觉宽度增长，最大宽度为 440 DIP。文字始终保持单行；超出可用像素宽度时，从左侧省略旧内容并保留最新文本。声纹与实际可见文字先组成内容组，再整体水平居中，不使用固定文字左边距。同一 session 的最大宽度只增不减。首次 partial 到达后文字立即绘制，不等待 width spring 展开阈值。每次 show 仍通过输入焦点链确定 active monitor 和 effective DPI，但 pill 的水平中心始终等于 monitor work area 中线，纵向固定为工作区底部向上 22 DIP；展开与退场都围绕同一底部中心。

## 注入边界

overlay 从不编辑或回写 partial。每轮 `DecodeJob` 在录音开始时保存 target HWND；consumer 取得 punctuated final 后，先验证该 HWND 仍有效，再用 `SetForegroundWindow` 恢复并最多等待约 100 ms 确认焦点。只有恢复成功才调用 `inject.paste_text` 或 `inject.type_unicode`；目标失效或无法恢复时会 dismiss 浮窗并放弃本轮注入。默认 paste 路径通过剪贴板和 Ctrl+V 写回录音开始时的输入窗口，而不是用户在推理期间偶然切到的其他前台窗口。

## See Also

- [项目全景](../overview.md) — 定位、组件和交付边界。
- [ASR 候选模型实验](../operations/asr-benchmark.md) — streaming 模型的实验口径。
