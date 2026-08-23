---
title: Wiki Index
type: overview
updated: 2026-08-23 11:44
---

# Wiki Index

<!-- LLM 维护的内容索引。每个页面一行：链接 + 单行摘要。 -->

## Overview

- [Overview](overview.md) — VoxPill 的目标、边界、组件、运行链路与交付方式。

## Architecture

- [伪流式语音输入运行链路](architecture/runtime-pipeline.md) — static Paraformer 累积 preview、完整 final 优先、恰好一次注入与 60 Hz overlay。

## Operations

- [ASR benchmark](operations/asr-benchmark.md) — static Paraformer 同语料准确率、CPU 资源指标与历史选型结论。
- [Windows build and distribution](operations/build-and-distribution.md) — staging 构建、portable ZIP、per-user 安装器、快捷方式与 release 边界。

## Contracts

- [No-speech hallucination gate](contracts/no-speech-gate-contract.md) — 静音/稳态底噪 acoustic activity 判定、preview/final 抑制与 1.0.2 验证边界。
- [Windows 1.0.2 release](contracts/windows-1.0.2-release-contract.md) — HighQoS 修复的选择性提交、tag、GitHub Release 与远端资产哈希边界。
- [Windows HighQoS long-utterance latency](contracts/windows-high-qos-latency-contract.md) — 后台进程 HighQoS、识别分段耗时、长文本浮窗裁剪与本地 1.0.2 部署边界。
- [Windows 1.0.1 release](contracts/windows-1.0.1-release-contract.md) — 长时间响应性修复的版本、构建、审查与 GitHub 发布边界。
- [Long-running responsiveness](contracts/overlay-frame-scheduling-contract.md) — 合并浮窗 timer frame，并取消仍在等待 recognizer 的过期 preview。
- [ASR benchmark](contracts/asr-benchmark-contract.md) — 统一语料和资源指标的候选模型评测约束。
- [Static Paraformer pseudo-streaming](contracts/static-paraformer-pseudo-streaming-contract.md) — CPU-only 单模型 preview/final、资源与退役资产约束。
- [Streaming overlay](contracts/streaming-overlay-contract.md) — 浮窗、目标恢复与一次注入约束。
- [Windows release packaging](contracts/windows-release-contract.md) — Windows x64 portable 与安装器的目标、验收和风险约束。

## Reviews

- [No-speech hallucination gate review](reviews/no-speech-gate-review.md) — WebRTC VAD、能量动态、谐波 fallback、最终打包与安装 smoke PASS。
- [Windows 1.0.2 release review](reviews/windows-1.0.2-release-review.md) — 选择性提交、版本、产物哈希与实验排除边界 PASS。
- [Windows HighQoS long-utterance latency review](reviews/windows-high-qos-latency-review.md) — HighQoS、长句性能、1.0.2 构建安装与自启验收 PASS。
- [Windows 1.0.1 release review](reviews/windows-1.0.1-release-review.md) — 性能修复、版本、隔离提交、Windows 产物与 smoke PASS。
- [Responsiveness deployment review](reviews/responsiveness-deployment-review.md) — 新版 rebuild、安装、自启、单实例与 ASR smoke PASS。
- [Long-running responsiveness review](reviews/long-running-responsiveness-review.md) — 合并 UI frame、取消等待中 preview 与 final 优先边界 PASS。
- [ASR benchmark review](reviews/asr-benchmark-review.md) — 候选模型 benchmark 审查结论。
- [Static Paraformer pseudo-streaming review](reviews/static-paraformer-pseudo-streaming-review.md) — 单模型、自适应调度、逐字预览与资源边界 PASS。
- [Streaming overlay review](reviews/streaming-overlay-review.md) — 浮窗与注入生命周期审查结论。
- [Windows release packaging review](reviews/windows-release-review.md) — Windows 1.0.0 portable、安装器、版本一致性、快捷方式、卸载与产物完整性 PASS。

## See Also

- [Wiki Schema](../SCHEMA.md) — Wiki 结构、页面类型及维护工作流。
