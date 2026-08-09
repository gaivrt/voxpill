---
title: Qwen3-ASR Windows Native Smoke Contract
type: workflow
updated: 2026-08-08 23:43
---

# Qwen3-ASR Windows Native Smoke Contract

## Target

在不修改或停止当前 VoxPill 生产进程的前提下，证明 Qwen3-ASR 0.6B 能在本机 Windows 原生 Python 与 RTX 3060 Laptop 6GB 上加载和解码，为后续开机预加载 final-pass 接入提供部署证据。

## Scope

- 使用独立于生产 `.venv-win` 的 Windows Python 3.11 runtime。
- 复用已校验的本地 Qwen 固定 revision snapshot，不重复下载模型权重。
- 安装固定版本的 Windows Torch/CUDA、Transformers 与 Accelerate 依赖；CUDA Torch 使用 PyTorch 官方 wheel，普通 PyPI 依赖按用户要求使用清华 TUNA。
- 执行一秒静音 smoke，并解码一条现有 16 kHz mono benchmark WAV。
- 记录 device、dtype、加载时间、解码时间、进程峰值内存和 Torch peak reserved GPU memory。

## Non-goals

- 本阶段不修改 `main.py`、`asr.py`、启动项或生产 `.venv-win`。
- 不实现 streaming、后台预加载、final-pass 切换或 PyInstaller 打包。
- 不停止当前正在运行的 VoiceKey/VoxPill Windows 进程。

## Acceptance Criteria

- Windows 原生 runtime 能从本地 snapshot 加载模型，且 `torch.cuda.is_available()` 为真。
- 静音和一条真实录音均成功解码；真实录音输出非空。
- smoke 输出包含加载、解码、内存和显存证据。
- 生产 `.venv-win` 与当前 VoiceKey 进程保持可用。
- 失败时保留明确的依赖、驱动、磁盘或显存 blocker，不尝试 WSL 服务替代。

## Required Validation

- 独立 Windows runtime 的 Python、Torch、Transformers 版本及 CUDA device 检查。
- Qwen Windows smoke 与一条真实 WAV decode。
- Windows `.venv-win` benchmark tests。
- 当前 VoiceKey Windows 进程健康检查。

## Risk Class

Governed：Windows GPU dependency 与 performance-sensitive 部署资格测试。外部操作从 PyTorch 官方 CUDA wheel 与清华 TUNA PyPI 镜像下载约 2–4 GB wheels；不上传录音，不重复下载模型。

## Reviewer Checklist

- 是否确实运行在 Windows 原生 Python，而不是 WSL。
- 独立环境是否避免污染生产 `.venv-win`。
- 是否复用固定 revision 与已校验模型文件。
- CUDA 计时与显存测量是否同步、口径是否明确。
- 是否在未通过 smoke 前修改生产链路。

## See Also

- [Qwen3-ASR Benchmark Contract](qwen3-asr-benchmark-contract.md)
- [ASR 候选模型实验](../operations/asr-benchmark.md)
