---
title: ASR Benchmark Review
type: workflow
updated: 2026-07-21 14:02
---

# ASR Benchmark Review

Contract: [ASR 候选模型实验 Contract](../contracts/asr-benchmark-contract.md)

Verdict: PASS

## Validation Evidence

- `python3 -m py_compile bench/*.py bench/tests/*.py` passed。
- Windows Python unit suite passed：16 tests，覆盖 metrics、WAV、配置、模型文件、安全解压和 cached provenance。
- Windows isolated-process smoke passed：current Paraformer、streaming Paraformer、WeNetSpeech-Yue、FireRedASR2 均成功加载并解码一秒静音。
- Windows PortAudio 成功枚举输入设备，默认输入为 BEHRINGER UMC 202HD。
- 三套候选模型已下载并写入本地 size/SHA-256 receipt；缓存迁移后保留实际 hf-mirror / ModelScope URL。
- 12 条真人录音格式与时长校验通过；四模型正式 benchmark 完成并生成 `bench/results/20260721-135750/summary.csv`。
- 首次正式运行暴露 Windows peak memory fallback bug；新增失败回归测试后修复 WinAPI 签名与错误边界。Windows suite 17/17 PASS，同一 reviewer focused re-check PASS。

## Reviewer Findings

初审发现英文 WER 漏罚非 Latin hallucination，以及 cache hit 可能误写下载来源。修复后由同一 reviewer focused re-check：非 Latin hypothesis 现作为 insertion unit；cached URL 保留旧 provenance，未知预存文件显式标记；`corpus_rtf` 与 online flush 口径也已补充。所有 blocker 已关闭。

正式运行后的二次 focused review 确认 `PROCESS_MEMORY_COUNTERS_EX` 字段、`GetCurrentProcess` / `GetProcessMemoryInfo` 签名和 Windows-only failure path 正确；四模型峰值约 365、330、344、913 MB，与模型规模一致。

## Residual Risk

- HTTP resume 尚未用 ETag / `Content-Range` 校验远端对象版本变化。
- 静音 smoke 只证明 runtime/API 兼容；模型准确率必须等同一说话者录完 12 条 corpus 后才能判断。

## Wiki Check

`wiki/operations/asr-benchmark.md` 已记录当前模型矩阵、指标、公平性规则、隔离流程、RTF 口径与下载安全边界；`wiki/index.md` 已收录，无新增 orphan knowledge page。
