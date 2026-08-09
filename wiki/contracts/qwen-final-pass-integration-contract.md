---
title: Qwen Final-Pass Integration Contract
type: workflow
updated: 2026-08-09 00:02
---

# Qwen Final-Pass Integration Contract

## Target

把已通过 Windows 原生资格测试的 Qwen3-ASR 0.6B 接入 VoxPill 源码运行链路：保留 streaming Paraformer 的实时 partial，在应用启动后异步预加载 Qwen，并在松键后优先提交 Qwen final。

## Scope

- Qwen 在独立 Windows Python 3.11 子进程中常驻，通过本地 stdin/stdout 协议接收单轮 PCM16 音频并返回 final text。
- 主进程启动不等待 Qwen；Qwen 加载期间热键、Paraformer partial/final 与注入保持可用。
- 每轮 streaming decode 同时保留 16 kHz mono PCM16；达到最短时长后，consumer 请求 Qwen final。
- Qwen 未就绪、输出为空、超时、OOM、协议错误或子进程退出时，本轮自动回退 Paraformer final。
- Qwen 成功时，overlay 在注入前更新为 Qwen final；目标 HWND 恢复与恰好一次注入语义不变。
- 配置支持启用开关、独立 Python 路径、模型目录、请求超时、完整 PCM 保留上限与可选 context。
- cleanup 必须停止 Qwen 子进程和 reader thread，不留下后台进程。

## Non-goals

- 不接入 vLLM 或 WSL 服务，不让 Qwen 生成 streaming partial。
- 不在本轮实现完全自包含的 Torch/Qwen portable 打包；源码启动依赖已建立的独立 Windows runtime。
- 不修改热键、音频设备、overlay 视觉、注入方式或模型权重。
- 不上传音频，不把 PCM、模型、结果或日志纳入源码资产。

## Acceptance Criteria

- App 启动后 Paraformer 先进入可用状态，Qwen 在后台完成预加载并记录 ready/load 信息。
- Qwen ready 时，真实录音走 Qwen final；仅发生一次目标窗口注入。
- Qwen disabled、未就绪、空输出、超时和异常路径均选择 Paraformer final，不丢文本、不杀 consumer。
- 超时或致命 worker 故障后不会让后续请求永久排队；worker 可停止并按需后台重启。
- 清理后不存在本次 App 启动的 Qwen 子进程。
- 生产 `.venv-win` 不安装 Torch/Transformers，Qwen runtime 继续隔离。

## Required Validation

- Python compile check。
- Qwen client 协议、配置解析、成功选择、空输出与异常 fallback 单元测试。
- 现有完整 Windows 测试套件。
- Windows 原生启动/ready、真实录音 final-pass、故障 fallback 与 cleanup 集成 smoke。
- 核对生产 `.venv-win` 未新增 Torch/Transformers/Accelerate。

## Risk Class

Governed：生产识别链路、进程生命周期与 performance-sensitive GPU 集成。本阶段不新增外部下载或网络调用，音频只在本机父子进程间传递。

## Reviewer Checklist

- Qwen 加载是否完全异步，不能阻塞热键与 Paraformer。
- IPC 是否为本机、按 request ID 关联，错误/迟到响应不能污染其他 session。
- timeout、worker crash、empty output 是否可靠回退，final 是否仍只注入一次。
- PCM 生命周期是否有界，短录音是否在请求 Qwen 前被丢弃。
- cleanup 是否能停止子进程和 reader；生产依赖是否保持隔离。
- 文档是否明确 source runtime 与 portable 边界。

## See Also

- [流式语音输入运行链路](../architecture/runtime-pipeline.md)
- [Qwen3-ASR Windows Native Smoke Contract](qwen-windows-smoke-contract.md)
- [ASR 候选模型实验](../operations/asr-benchmark.md)
