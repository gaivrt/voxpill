---
title: Streaming Overlay Contract
type: workflow
updated: 2026-07-21 17:21
---

# Streaming Overlay Contract

## Target

VoxPill 使用 bilingual streaming Paraformer：按住右 Ctrl 时以不抢焦点、自动适配 Windows 明暗主题的自适应 pill 展示带标点 partial，松开后只向原焦点窗口提交一次 final，并在注入完成后平滑收束消失。

## Scope

- 使用 `models/asr-streaming/` 的 encoder/decoder/tokens 和现有标点模型。
- 音频 callback 只复制/排队 chunk；recognizer 在独立 worker 中增量 decode。
- overlay 使用独立 Win32 UI thread 与 60 Hz frame ticker，目标 60 FPS，保持 topmost、click-through、no-activate 与 anchor monitor DPI。
- pill 从 36 DIP 的紧凑声纹核开始，按 partial 的混合中英宽度 spring/overshoot 生长，最大 440 DIP；文字永不换行，超长时左侧省略并保留最新内容，声纹与可见文字作为整体居中。同一 session 的最大宽度只增不减。pill 固定在 active monitor 工作区底部向上 22 DIP，展开和退场始终围绕 monitor 水平中线；首个 partial 不等待展开阈值即可显示。
- show、partial、finalizing、committed、dismiss 均带 session ID，旧 session 不得关闭新 session。
- 默认热键为右 Ctrl；启动前要求 60 ms 稳定键态，左键按下/松开后设置 120 ms mouse guard，过滤点击伴随的短伪脉冲。partial 恢复标点但永不注入，只有松键后的 final 才注入一次。
- layered window 使用 premultiplied per-pixel alpha 与抗锯齿合成；auto 每次 show 读取 Windows app theme，light 为暖白/深灰，dark 为纯黑/暖白，也允许强制主题；使用 1 DIP 极低透明度暖灰边框，不得包含渐变、投影、截图或 blur。
- 录音开始时保存 foreground HWND；注入 final 前恢复并验证该 HWND，失败时不得把文本写进其他窗口。

## Non-goals

- 不实现编辑器内逐词 patch、光标追踪或 partial rollback。
- 不修改 benchmark 历史结果。
- 不承诺跨硬件稳定 60 FPS；动画不得阻塞 ASR 与音频 callback。

## Acceptance Criteria

- overlay 显示/隐藏不改变当前 foreground window。
- 初始 pill、短 partial、长 partial 的宽度在单次 session 内单调增长；任何 partial revision 都不得触发换行或纵向跳动，内容组与整个 pill 均保持 monitor 底部水平居中；连续左键点击不得创建 overlay session。
- 长语音期间 partial 可更新；松键 final 完成后才注入并触发退出动画。
- overlay 初始化失败时 ASR 仍可工作。
- 新录音覆盖旧动画时，不出现旧 session 把新浮窗隐藏的问题。
- 现有短录音过滤、剪贴板注入、托盘退出与 single-instance 行为保留。

## Required Validation

- compile check 与纯函数/状态测试。
- Windows 模型增量 decode smoke。
- Windows overlay demo：原生 DPI、透明圆角、no-activate、click-through、自适应尺寸、caret/focus fallback 与 show/update/commit 动画。
- 全部相关 Windows tests。

## Risk Class

Governed：performance-sensitive streaming pipeline 与全局焦点/输入行为变更。

## Reviewer Checklist

- PortAudio callback 是否保持非阻塞。
- recognizer 是否避免并发 decode race 与 session 交叉。
- final 是否恰好注入一次且发生在退出动画之前。
- overlay 是否不抢焦点并能安全降级。
- cleanup 是否能停止 stream、worker 与 UI thread。

## See Also

- [ASR Benchmark](../operations/asr-benchmark.md)
- [Project Overview](../overview.md)
