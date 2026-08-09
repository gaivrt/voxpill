---
title: Qwen3-ASR Windows Native Smoke Review
type: review
updated: 2026-08-08 23:45
---

# Qwen3-ASR Windows Native Smoke Review

- Contract: [Qwen3-ASR Windows Native Smoke Contract](../contracts/qwen-windows-smoke-contract.md)
- Verdict: PASS

## Validation Evidence

- 独立 Windows CPython 3.11 runtime 使用 Torch 2.12.0+cu130、Transformers 5.14.1 与 Accelerate 1.14.0，CUDA 13.0 在 RTX 3060 Laptop GPU 上可用；生产 `.venv-win` 保持独立。
- 同步计时后的 smoke 输出 device、dtype、load/decode、RAM 与 VRAM：load 8.9836 秒、decode 0.9830 秒、peak working set 2312.117 MiB、Torch peak reserved 1522 MiB，静音无幻觉文本。
- 正式 run `20260808-234215` 的 12 条真实录音均成功解码；CER 10.60%、WER 1.39%、MER 19.70%、corpus RTF 0.1598、load 8.9124 秒、peak working set 2313.430 MiB、Torch peak reserved 1980 MiB。
- 固定模型 revision、1,564,928,088-byte 权重及 SHA-256 与下载 receipt 一致。
- Windows 生产 `.venv-win` compile check、34/34 tests 与 `uv lock --check` PASS；运行中的 VoiceKey 进程保持 `Responding=True`。

## Blocking Issues

无。首次审查要求补齐 smoke 内存/显存字段，并在模型加载计时停止前同步 CUDA；实现、回归测试和重新实跑后复审通过。

## Residual Risk

- 清华 TUNA 普通依赖来源由执行命令与 contract 记录，安装 metadata 不保存 index URL；Torch 官方 wheel 可由 `direct_url.json` 验证。
- 本阶段未实现生产双阶段链路、开机预加载、显存不足回退或 PyInstaller 打包。

## Wiki Check

`wiki/operations/asr-benchmark.md`、`wiki/index.md` 与 `wiki/log.md` 已同步 Windows 原生资格结果和后续阶段边界。
