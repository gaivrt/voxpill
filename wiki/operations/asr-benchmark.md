---
title: ASR 候选模型实验
type: workflow
updated: 2026-08-09 13:05
---

# ASR 候选模型实验

## 目的与边界

`bench/` 用同一批个人录音比较 VoxPill 当前 Paraformer 与候选模型。CPU 模型使用 sherpa-onnx，Qwen3-ASR 使用隔离的 Torch/CUDA dependency group。它不改变生产热键、文本注入或标点链路；模型权重、录音和结果均为本地 runtime artifacts，不进入源码版本控制。

## 模型矩阵

| ID | 模型 | 语言 | 模式 |
|---|---|---|---|
| `current_paraformer` | 当前 INT8 Paraformer | 中英 | offline baseline |
| `streaming_paraformer` | bilingual streaming Paraformer INT8 | 中英 | true streaming |
| `wenetspeech_yue` | WeNetSpeech-Yue U2++ CTC INT8 | 普通话、英语、粤语 | offline/simulated streaming，仅按 offline 测 |
| `fireredasr2_ctc` | FireRedASR2 CTC INT8 | 中英及 code-switch | offline/simulated streaming，仅按 offline 测 |
| `qwen3_asr_0_6b` | Qwen3-ASR 0.6B HF BF16 | 30 语言、中文方言与 code-switch | CUDA offline final-pass，不标为 true streaming |

只有 `streaming_paraformer` 记录 first partial 对应的已喂入音频毫秒数。该数值不是麦克风、调度和文本注入在内的端到端 wall-clock latency。

## 工作流

1. `record_corpus.py` 逐条录制 `prompts.json` 的 12 条 16 kHz mono PCM16 WAV；中文、英文和中英混说各四条。
2. `download_models.py --all` 按 `models.toml` 下载固定资产。Qwen 使用官方 Hugging Face repo 的固定 commit；完整快照已存在时不重复联网，receipt 仍重新计算尺寸与 SHA-256。
3. `smoke_models.py --all` 在独立进程中逐模型加载并解码一秒静音，用于发现缺文件、模型格式或 runtime 不兼容。
4. `benchmark.py --all` 逐模型启动 worker，写入单模型 JSON 和汇总 CSV，避免模型间的峰值内存污染。

`mixed-product` 录音保留了项目旧名 `Voicekey`，因此它的 reference 也必须保持录音时文本，不能随产品品牌改名；配置测试固定了这条 ground truth。

## 指标

- 中文按 NFKC、去标点与空白后的字符计算 CER。
- 英文按 NFKC、lowercase 后的 word 计算 WER，保留词内 apostrophe；hypothesis 里额外出现的非 Latin 字母数字也作为 insertion unit，避免漏罚跨语言 hallucination。
- 中英混说使用中文逐字、英文逐词的 token 序列计算 MER。
- RTF 是纯 recognizer decode 时间除以音频时长；同时输出逐句平均 `mean_rtf` 与按总时长加权的 `corpus_rtf`，load time 单独记录。online decode 包含用于 flush 的额外 500 ms 静音处理，RTF 分母只包含原始录音时长，因此口径偏保守。
- peak working set 是单个模型 worker 的进程峰值工作集。
- peak GPU reserved 是 Qwen worker 内 Torch allocator 观测到的峰值显存，不含桌面和其他进程。

不同类别的 CER、WER、MER 不合并为总分。选择生产模型时先看同一说话者语料上的准确率，再比较 true streaming、RTF、内存与加载成本。

## 当前资格测试结论

2026-08-08 在 RTX 3060 Laptop 6GB 上用同一组 12 条录音运行 Qwen3-ASR 0.6B：CER 10.60%、WER 1.39%、MER 19.70%、corpus RTF 0.126、峰值显存 1.98 GB、峰值工作集 2.40 GB。它的中文与 offline Paraformer 持平，英文和中英混说明显更好。最初的生产方案以 streaming Paraformer 生成 partial、Qwen 生成 final；实际体验显示两种模型的 preview/final 跳变明显，因此当前生产选型改为同一个 Qwen 周期性重识别累积音频并生成 final，static Paraformer 仅作 lazy failure fallback。`streaming_paraformer` 继续作为历史 benchmark 候选，不再是生产 runtime。

## Windows 原生部署资格

2026-08-08 使用独立 Windows Python 3.11 runtime 和同一本地模型 snapshot 完成 smoke 与 12 条正式录音：CUDA 13.0 可用；同步计时后的静音 smoke 加载 8.98 秒、解码 0.98 秒、峰值工作集 2.31 GB、Torch peak reserved 1.52 GB，且无幻觉文本。正式 run `20260808-234215` 的 CER 10.60%、WER 1.39%、MER 19.70%，与 WSL 结果完全一致，load 8.91 秒、corpus RTF 0.160、峰值工作集 2.31 GB、Torch peak reserved 1.98 GB。2026-08-09 已完成独立 worker、request-ID IPC、timeout/restart 与第一版 final-pass 接入，随后按真实使用体验改为 Qwen 单模型伪流式与 static Paraformer lazy fallback；完全自包含的 Qwen portable 打包仍不在本阶段范围内。

2026-08-09 尝试用能量 VAD 在自然停顿处分段、只识别松键尾段。两组参数都保持中文 CER 不变并改善 mixed MER，但英文 WER 分别比整段 Qwen 恶化 9.72 和 12.50 个百分点，因此未接入生产。替代方案保持完整录音 final：松键时旁路取消 active preview。16.588 秒英文录音的两次 smoke 中，preview cancel 在 0.574–0.837 秒内释放 gate，随后完整 final 用时 1.988–2.814 秒，hypothesis 均与固定 baseline 完全一致。

## 下载与校验

下载器只解压普通文件和目录，拒绝 path traversal、symlink、hardlink 与 special archive entry。`bench/model_cache/checksums.json` 保存实际下载 URL、canonical release URL（归档模型）、文件尺寸、SHA-256 和校验时间。该 receipt 与模型缓存一起保持为本地生成状态。

## See Also

- [Project Overview](../overview.md) — VoxPill 当前生产链路。
- [ASR 实验 Contract](../contracts/asr-benchmark-contract.md) — 本次 governed 实现的范围与验收标准。
- [Qwen3-ASR Benchmark Contract](../contracts/qwen3-asr-benchmark-contract.md) — Qwen GPU 资格测试的范围与验收标准。
- [Qwen3-ASR Windows Native Smoke Contract](../contracts/qwen-windows-smoke-contract.md) — Windows GPU runtime 的部署资格边界。
- [Wiki Schema](../../SCHEMA.md) — Wiki 结构与维护约定。
