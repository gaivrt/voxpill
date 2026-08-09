---
title: Wiki Index
type: overview
updated: 2026-08-09 13:16
---

# Wiki Index

<!-- LLM 维护的内容索引。每个页面一行：链接 + 单行摘要。 -->

## Overview

- [Overview](overview.md) — VoxPill 的目标、边界、组件、运行链路与交付方式。

## Architecture

- [伪流式语音输入运行链路](architecture/runtime-pipeline.md) — hotkey mouse guard、可取消 Qwen preview、完整录音 final、static Paraformer lazy fallback、恰好一次注入与 60 Hz overlay。

## Operations

- [ASR 候选模型实验](operations/asr-benchmark.md) — Paraformer/CTC/Qwen 的同语料下载、WSL/Windows smoke、benchmark、GPU 指标与当前选型结论。

## Contracts

- [ASR benchmark](contracts/asr-benchmark-contract.md) — 统一语料和资源指标的候选模型评测约束。
- [Qwen3-ASR benchmark](contracts/qwen3-asr-benchmark-contract.md) — Qwen3-ASR 固定 revision、Windows 资格与公平对比约束。
- [Qwen Windows smoke](contracts/qwen-windows-smoke-contract.md) — 独立 Windows CUDA runtime 的接入前验证约束。
- [Qwen final-pass integration](contracts/qwen-final-pass-integration-contract.md) — Qwen final 与 Paraformer fallback 的生产接入约束。
- [Qwen pseudo-streaming](contracts/qwen-pseudo-streaming-contract.md) — 累积音频 preview、完整 final 与 lazy fallback 约束。
- [Qwen cancellable preview](contracts/qwen-cancellable-preview-contract.md) — 松键旁路取消 active preview、保护 final 与响应延迟约束。
- [Streaming overlay](contracts/streaming-overlay-contract.md) — 浮窗、目标恢复与一次注入约束。

## Reviews

- [ASR benchmark review](reviews/asr-benchmark-review.md) — 候选模型 benchmark 审查结论。
- [Qwen3-ASR benchmark review](reviews/qwen3-asr-benchmark-review.md) — Qwen3-ASR 公平 benchmark 审查结论。
- [Qwen Windows smoke review](reviews/qwen-windows-smoke-review.md) — Windows CUDA 资格测试审查结论。
- [Qwen final-pass integration review](reviews/qwen-final-pass-integration-review.md) — Qwen final 生产接入审查结论。
- [Qwen pseudo-streaming review](reviews/qwen-pseudo-streaming-review.md) — 累积 preview 与 fallback 生命周期审查结论。
- [Qwen cancellable preview review](reviews/qwen-cancellable-preview-review.md) — 松键取消 active preview、完整 final 准确率与并发生命周期审查结论。
- [Streaming overlay review](reviews/streaming-overlay-review.md) — 浮窗与注入生命周期审查结论。

## See Also

- [Wiki Schema](../SCHEMA.md) — Wiki 结构、页面类型及维护工作流。
