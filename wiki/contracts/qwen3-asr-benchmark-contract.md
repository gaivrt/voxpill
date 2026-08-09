---
title: Qwen3-ASR 0.6B Benchmark Contract
type: workflow
updated: 2026-08-08 22:35
---

# Qwen3-ASR 0.6B Benchmark Contract

## Target

在不改变 VoxPill 生产识别链路的前提下，把官方 Qwen3-ASR-0.6B-HF 接入现有个人语料 benchmark，并在本机 RTX 3060 Laptop 6GB 上与现有 Paraformer 结果公平比较。

## Scope

- 为 benchmark 增加隔离的 Qwen3-ASR dependency group、固定模型 revision 和本地下载 receipt。
- 准确率资格测试可使用本机隔离的 WSL CUDA runtime；该结果不代表 Windows App 部署验证，生产接入前仍需 Windows 原生 smoke。
- 使用同一组 16 kHz mono 录音、同一 CER/WER/MER normalization 和独立 worker 进程。
- 记录模型加载时间、逐句 decode 时间、RTF、进程峰值内存，以及 CUDA 可用时的峰值显存。
- 支持为 Qwen3-ASR 配置固定的中英技术词 context，但首轮无提示结果必须单独可运行，避免与旧模型不公平比较。

## Non-goals

- 不替换 `main.py` / `asr.py` 的生产模型，不改变热键、overlay 或注入行为。
- 不把模型权重、真人录音、结果或 Hugging Face cache 纳入源码资产。
- 不把官方 benchmark 数字当作本机个人语料结论。
- 本轮不接入 vLLM streaming；只验证 native Transformers offline final-pass。

## Acceptance Criteria

- 未安装可选依赖、CUDA 不可用、模型不完整或显存不足时给出明确错误。
- Qwen worker 输出与现有 JSON/CSV 结果兼容，并额外记录 device、dtype 与 peak GPU memory。
- downloader 固定官方 repo revision，receipt 保存 repo、revision、文件尺寸和 SHA-256。
- 现有 Paraformer 配置、下载和 benchmark 测试不回归。
- 在本机 RTX 3060 上完成 12 条语料的 Qwen3-ASR-0.6B 准确率运行，或留下可复现的客观硬件/依赖 blocker 证据。

## Required Validation

- Python compile check。
- benchmark configuration、download receipt 和 Qwen adapter 单元测试。
- 现有 benchmark 相关测试套件。
- Qwen 模型下载后用本机隔离 CUDA runtime 执行 smoke decode。
- RTX 3060 上正式准确率 benchmark，核对 12 条结果、CER/WER/MER、RTF 和峰值显存。

## Risk Class

Governed：performance-sensitive benchmark implementation。外部操作限于从官方 Hugging Face repo 下载约 1.6 GiB 模型；录音不离开本机。

## Reviewer Checklist

- 是否复用同一语料和评分逻辑，未为 Qwen 特殊放宽 normalization。
- 是否把 offline final-pass 误标为 true streaming。
- 可选 GPU 依赖是否与生产 runtime 隔离。
- revision、来源与校验 receipt 是否足以复现下载。
- CUDA 计时是否同步，显存指标是否在单模型 worker 内采集。

## See Also

- [ASR 候选模型实验](../operations/asr-benchmark.md)
- [Project Overview](../overview.md)
- [Wiki Schema](../../SCHEMA.md)
