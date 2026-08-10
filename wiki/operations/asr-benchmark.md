---
title: ASR benchmark
type: workflow
updated: 2026-08-10 19:34
---

# ASR benchmark

## 目的与边界

`bench/` 使用固定的 12 条个人录音验证当前 static Paraformer。语料包含中文、英文和句内 code-switch 各四条；全部是 16 kHz mono PCM16 WAV。模型权重、录音和结果是 ignored local runtime artifacts。

## 当前模型

| ID | 模型 | 模式 | Provider |
|---|---|---|---|
| `current_paraformer` | INT8 Paraformer | offline / production pseudo-streaming | CPU |

`smoke_models.py` 在独立进程加载模型并解码一秒静音；`benchmark.py` 对完整语料逐条离线识别并记录 load time、RTF、peak working set、reference、hypothesis 与评分。production preview 同样使用 offline recognizer，但在 1–2 秒的自适应节奏下重识别累积音频，不把它标为 true streaming。

## 指标

- 中文按 NFKC、去标点与空白后的字符计算 CER。
- 英文按 NFKC、lowercase word 计算 WER；非 Latin hallucination 计 insertion。
- 中英混说按中文字符、英文词的 token 序列计算 MER。
- RTF 是 recognizer decode seconds / audio seconds；load time 单独记录。
- Peak working set 是隔离 benchmark 进程的峰值工作集。

## 固定 baseline

2026-08-10 Windows 同语料 run `20260810-193929` 的 static Paraformer 指标为 CER 10.60%、WER 20.83%、MER 28.79%、corpus RTF 0.035、1.16 秒加载和 363 MiB peak working set。12 条 reference/hypothesis 与历史同模型 run 逐条完全一致。

历史实验曾证明 true-streaming Paraformer 的准确率明显更差；GPU 模型改善英文和 code-switch，但需要约 1.5 GB checkpoint、独立约 3 GB runtime、1.8–2.3 GB RAM 和约 2 GB dedicated VRAM。2026-08-10 根据主要中文口述场景、核显/省电模式兼容与资源目标，生产收敛为 static Paraformer 单模型伪流式，并删除已退役模型、adapter、runtime 和本地结果。

## 工作流

```powershell
uv run python bench\download_models.py current_paraformer punctuation
uv run python bench\smoke_models.py current_paraformer
uv run python bench\benchmark.py --model current_paraformer
```

`mixed-product` 录音保留录制时的旧品牌 `Voicekey`，reference 不得随产品名修改。

## See Also

- [项目全景](../overview.md) — 当前生产模型与资源边界。
- [Static Paraformer contract](../contracts/static-paraformer-pseudo-streaming-contract.md) — 单模型迁移与验收标准。
- [ASR benchmark contract](../contracts/asr-benchmark-contract.md) — 固定语料和评分口径。
