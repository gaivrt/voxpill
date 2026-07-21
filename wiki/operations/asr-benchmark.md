---
title: ASR 候选模型实验
type: workflow
updated: 2026-07-21 12:55
---

# ASR 候选模型实验

## 目的与边界

`bench/` 用同一批个人录音比较 VoxPill 当前离线 Paraformer 与三个不含 Qwen 的候选模型。它是 Windows CPU 实验工具，不改变生产热键、文本注入或标点链路；模型权重、录音和结果均为本地 runtime artifacts，不进入源码版本控制。

## 模型矩阵

| ID | 模型 | 语言 | 模式 |
|---|---|---|---|
| `current_paraformer` | 当前 INT8 Paraformer | 中英 | offline baseline |
| `streaming_paraformer` | bilingual streaming Paraformer INT8 | 中英 | true streaming |
| `wenetspeech_yue` | WeNetSpeech-Yue U2++ CTC INT8 | 普通话、英语、粤语 | offline/simulated streaming，仅按 offline 测 |
| `fireredasr2_ctc` | FireRedASR2 CTC INT8 | 中英及 code-switch | offline/simulated streaming，仅按 offline 测 |

只有 `streaming_paraformer` 记录 first partial 对应的已喂入音频毫秒数。该数值不是麦克风、调度和文本注入在内的端到端 wall-clock latency。

## 工作流

1. `record_corpus.py` 逐条录制 `prompts.json` 的 12 条 16 kHz mono PCM16 WAV；中文、英文和中英混说各四条。
2. `download_models.py --all` 下载 `models.toml` 固定的最小 INT8 文件集。默认使用作者维护模型的 Hugging Face / ModelScope 镜像，`--origin` 可绕过镜像；`.part` 文件支持断点续传。
3. `smoke_models.py --all` 在独立进程中逐模型加载并解码一秒静音，用于发现缺文件、模型格式或 runtime 不兼容。
4. `benchmark.py --all` 逐模型启动 worker，写入单模型 JSON 和汇总 CSV，避免模型间的峰值内存污染。

## 指标

- 中文按 NFKC、去标点与空白后的字符计算 CER。
- 英文按 NFKC、lowercase 后的 word 计算 WER，保留词内 apostrophe；hypothesis 里额外出现的非 Latin 字母数字也作为 insertion unit，避免漏罚跨语言 hallucination。
- 中英混说使用中文逐字、英文逐词的 token 序列计算 MER。
- RTF 是纯 recognizer decode 时间除以音频时长；同时输出逐句平均 `mean_rtf` 与按总时长加权的 `corpus_rtf`，load time 单独记录。online decode 包含用于 flush 的额外 500 ms 静音处理，RTF 分母只包含原始录音时长，因此口径偏保守。
- peak working set 是单个模型 worker 的进程峰值工作集。

不同类别的 CER、WER、MER 不合并为总分。选择生产模型时先看同一说话者语料上的准确率，再比较 true streaming、RTF、内存与加载成本。

## 下载与校验

下载器只解压普通文件和目录，拒绝 path traversal、symlink、hardlink 与 special archive entry。`bench/model_cache/checksums.json` 保存实际下载 URL、canonical release URL（归档模型）、文件尺寸、SHA-256 和校验时间。该 receipt 与模型缓存一起保持为本地生成状态。

## See Also

- [Project Overview](../overview.md) — VoxPill 当前生产链路。
- [ASR 实验 Contract](../contracts/asr-benchmark-contract.md) — 本次 governed 实现的范围与验收标准。
- [Wiki Schema](../../SCHEMA.md) — Wiki 结构与维护约定。
