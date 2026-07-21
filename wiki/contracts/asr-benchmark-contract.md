---
title: ASR 候选模型实验 Contract
type: workflow
updated: 2026-07-21 12:14
---

# ASR 候选模型实验 Contract

## Target

建立可重复的 Windows CPU A/B harness，比较 voicekey 当前模型、bilingual streaming Paraformer、WeNetSpeech-Yue U2++ 与 FireRedASR2 CTC；明确排除 Qwen。

## Scope

- 提供普通话、英文、中英混说语料录制工具。
- 顺序加载单个模型，记录加载时间、RTF、峰值工作集与识别文本。
- 计算中文 CER、英文 WER 和中英混说 MER。
- 对真 streaming 模型记录首个 partial 对应的音频位置。
- 提供来自官方 sherpa-onnx release 的模型下载清单，并在下载后记录 SHA-256。

## Non-goals

- 本轮不替换 voicekey 生产模型或改变热键输入行为。
- 不把实验模型、录音或结果提交为源码资产。
- 不宣称不同硬件上的官方 RTF 可以直接横向比较。

## Acceptance Criteria

- 缺少模型或语料时给出清楚错误，不产生误导性分数。
- 每种指标有确定、经过单元测试的 normalization/tokenization。
- 每个模型在独立子进程运行，避免模型间峰值内存污染。
- downloader 防止 archive path traversal，并保存来源与 SHA-256 receipt。
- README 给出从录音、下载到运行和解读结果的完整 Windows 命令。

## Required Validation

- Python compile check。
- metrics、WAV 读取、配置校验的自动测试。
- 当前 Paraformer baseline 的最小 smoke test（有语料时）。
- 下载后检查候选模型所需文件完整性。

## Risk Class

Governed：performance-sensitive benchmark implementation。模型下载属于外部操作，约 1.1 GiB，执行前需明确授权。

## Reviewer Checklist

- 指标是否公平处理中文、英文和 code-switch。
- 时间与内存测量是否避免跨模型污染。
- streaming 指标是否没有把模拟 streaming 误称为真 streaming。
- 下载来源、校验与 archive extraction 是否安全。

## See Also

- [Project Overview](../overview.md)
- [Wiki Schema](../../SCHEMA.md)
