---
title: Wiki Index
type: overview
updated: 2026-08-10 21:31
---

# Wiki Index

<!-- LLM 维护的内容索引。每个页面一行：链接 + 单行摘要。 -->

## Overview

- [Overview](overview.md) — VoxPill 的目标、边界、组件、运行链路与交付方式。

## Architecture

- [伪流式语音输入运行链路](architecture/runtime-pipeline.md) — static Paraformer 累积 preview、完整 final 优先、恰好一次注入与 60 Hz overlay。

## Operations

- [ASR benchmark](operations/asr-benchmark.md) — static Paraformer 同语料准确率、CPU 资源指标与历史选型结论。

## Contracts

- [ASR benchmark](contracts/asr-benchmark-contract.md) — 统一语料和资源指标的候选模型评测约束。
- [Static Paraformer pseudo-streaming](contracts/static-paraformer-pseudo-streaming-contract.md) — CPU-only 单模型 preview/final、资源与退役资产约束。
- [Streaming overlay](contracts/streaming-overlay-contract.md) — 浮窗、目标恢复与一次注入约束。

## Reviews

- [ASR benchmark review](reviews/asr-benchmark-review.md) — 候选模型 benchmark 审查结论。
- [Static Paraformer pseudo-streaming review](reviews/static-paraformer-pseudo-streaming-review.md) — 单模型、自适应调度、逐字预览与资源边界 PASS。
- [Streaming overlay review](reviews/streaming-overlay-review.md) — 浮窗与注入生命周期审查结论。

## See Also

- [Wiki Schema](../SCHEMA.md) — Wiki 结构、页面类型及维护工作流。
