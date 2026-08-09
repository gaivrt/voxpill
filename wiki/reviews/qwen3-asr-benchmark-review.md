---
title: Qwen3-ASR 0.6B Benchmark Review
type: review
updated: 2026-08-08 22:38
---

# Qwen3-ASR 0.6B Benchmark Review

- Contract: [Qwen3-ASR 0.6B Benchmark Contract](../contracts/qwen3-asr-benchmark-contract.md)
- Verdict: PASS

## Validation Evidence

- 新 Qwen run `20260808-223402` 与历史 Paraformer baseline 的 12 个 `(id, category, reference)`、音频时长完全一致；WAV 均为 mono、PCM16、16 kHz。
- 独立重算逐句 edit counts、CER/WER/MER 与 corpus RTF，结果与 JSON 一致：CER 10.60%、WER 1.39%、MER 19.70%、corpus RTF 0.126。
- CUDA worker 记录 peak reserved 1980 MiB、peak working set 2396.9 MiB，并明确标记 `true_streaming=false`。
- 固定 Hugging Face revision、模型尺寸及 SHA-256 与本地 receipt 一致；完整 snapshot 缓存复用有回归测试。
- WSL 与 Windows `.venv-win` 各 32 项测试 PASS；Python compile check 与 `uv lock --check` PASS；Qwen CUDA smoke PASS。

## Blocking Issues

无。首次审查发现 `mixed-product` reference 曾随品牌名变更；现已恢复录音时的 `Voicekey`，增加回归断言并重新生成正式结果。

## Residual Risk

- 语料仅 12 条且为单说话者，结论不应外推为通用模型排名。
- peak reserved 是 Torch allocator 指标，不代表整机显存占用。
- Windows 原生 Qwen smoke 与打包验证属于后续生产接入阶段；本轮未修改生产识别链路。

## Wiki Check

`wiki/operations/asr-benchmark.md` 与 `wiki/index.md` 已同步当前模型矩阵、指标口径、资格测试结论和 Windows 部署边界。
