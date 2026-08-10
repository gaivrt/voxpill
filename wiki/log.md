---
title: Wiki Log
type: workflow
updated: 2026-07-21 22:54
---

# Wiki Log

## [2026-07-21 11:36] init | Wiki 初始化

创建 `SCHEMA.md`、`wiki/index.md`、`wiki/log.md` 和 `wiki/overview.md`，并定义 architecture、operations、assets 与 decisions 四类专题目录。

## [2026-07-21 12:50] ingest | ASR benchmark 工作流

新增 `operations/asr-benchmark.md`，记录候选模型矩阵、录音与隔离 benchmark 流程、指标语义及下载校验边界，并更新索引。

## [2026-07-21 12:58] ingest | ASR benchmark 公平性与 review

补充英文跨语言 hallucination 的 WER 规则、加权 RTF 与 online flush 口径；governed review 在两项 blocker 修复后获得 PASS。

## [2026-07-21 14:02] review | Windows benchmark 实跑

12 条真人语料完成四模型正式运行；修复并回归验证 Windows peak working set 采集，focused review PASS。结果属于 runtime artifact，不 ingest 为持久模型结论。

## [2026-07-21 15:11] ingest | 流式输入与自适应 overlay

新增 `architecture/runtime-pipeline.md`，并更新项目全景与索引，记录 bilingual streaming Paraformer、右 Alt 生命周期、partial-only 预览、final 单次注入及 per-pixel 多显示器浮窗行为。

## [2026-07-21 15:14] ingest | Schema 运行结构同步

同步 `SCHEMA.md` 的项目定义与文件角色，使入口、ASR、overlay、默认热键和模型目录说明与当前 streaming 主链路一致。

## [2026-07-21 15:30] ingest | 目标恢复与 Dynamic Island 生命周期

更新 schema、项目全景、运行链路与索引，记录 target HWND 恢复、60 Hz ticker、日夜主题、anchor monitor DPI、共享推理锁和 worker join 行为。

## [2026-07-21 15:32] ingest | 轻量主题采样

更新运行链路，记录 auto 主题改用 anchor 上方三点 Win32 像素采样，不再使用桌面截图与模糊阻塞首帧。

## [2026-07-21 16:20] ingest | 纯黑浮窗与 caret 定位

同步右 Ctrl、partial 标点、单 session 尺寸单调增长、纯黑无投影视觉，以及 Win32、MSAA、UI Automation caret 定位和 focused-window 降级链路。

## [2026-07-21 16:24] ingest | 单行居中 partial

浮窗移除双行布局；超长 partial 改为左侧省略、保留最新文字，并将声纹与可见文字作为整体水平居中，消除 revision 导致的换行跳动。

## [2026-07-21 16:38] ingest | 点击防误触与顶部居中

新增热键稳定窗口和 mouse guard，过滤连续左键点击产生的短伪脉冲；浮窗改为 active monitor 顶部整体居中，并移除首个 partial 的展开等待阈值。

## [2026-07-21 16:45] ingest | Windows 自动明暗主题

overlay 在每次 show 时读取 Windows app theme：浅色使用暖白/深灰，深色保持纯黑/暖白，同时保留 light、dark 强制配置。

## [2026-07-21 16:51] ingest | 底部居中与极浅边框

pill 移至 active monitor 工作区底部向上 22 DIP，并为浅色/深色主题增加 1 DIP 极低透明度暖灰边框，改善与相近背景的分离。

## [2026-07-21 17:21] ingest | VoxPill 公开仓库准备

项目品牌更新为 VoxPill，新增公开 README、静态 hero 与轻量交互 GIF；公开仓库排除模型权重和本地运行产物，并记录首次运行通过 downloader 获取 streaming ASR 与标点资产。

## [2026-07-21 18:53] ingest | Windows 开机自启教学

README 新增 Startup 图形操作、PowerShell 自动创建、关闭与旧版本排查教学；项目全景同步记录快捷方式必须指向项目内隐藏启动 VBS，而不是旧 portable 路径。

## [2026-07-21 22:54] ingest | VoxPill 托盘标识

托盘视觉从蓝/橙麦克风改为黑色 pill 与五段声纹，增加明暗任务栏均可辨认的暖灰边框；录音态只高亮声纹，tooltip 精简为产品名。

## [2026-07-21 23:06] ingest | 自适应圆球托盘图标

托盘标识收敛为无边框圆球与单帧五段声纹，移除胶囊、描边和彩色状态；浅色与深色配色跟随 Windows app theme，并在常驻轮询中每秒自动刷新。

## [2026-07-22 10:17] ingest | 放大托盘圆球

圆球直径由 52 px 提升至 62 px，并同步放大五段声纹，充分利用 Windows 16–32 px notification area 的可见空间。

## [2026-08-08 22:25] ingest | Qwen3-ASR GPU 资格测试

新增固定 revision 的 Qwen3-ASR 0.6B HF 隔离 benchmark、CUDA/VRAM 指标与下载 receipt；12 条同语料实跑支持 streaming Paraformer partial + Qwen final-pass 的双阶段方案。

## [2026-08-08 22:35] fix | 固定录音 ground truth

恢复 `mixed-product` 录音时的旧品牌 reference，并用测试锁定；重新运行 Qwen 资格测试，确保与历史 Paraformer baseline 使用同一 ground truth。

## [2026-08-08 23:43] validate | Qwen Windows 原生资格测试

独立 Windows Python 3.11 runtime 完成 Qwen CUDA smoke 与 12 条同语料 benchmark；准确率与 WSL 一致，同步计时记录 8.91 秒加载、0.160 corpus RTF、2.31 GB RAM 和 1.98 GB Torch reserved VRAM，生产环境测试 34/34 通过。

## [2026-08-08 23:59] ingest | Qwen final-pass 生产接入

生产链路新增独立 Windows Qwen 子进程后台预加载、本地 request-ID IPC、有界 PCM、timeout/restart 与 Paraformer fallback；保留 streaming partial、目标窗口恢复和恰好一次注入语义。

## [2026-08-09 00:19] ingest | Qwen 单模型伪流式与 lazy fallback

生产预览改为同一 Qwen worker 周期重识别累积音频，final 请求优先于等待 preview；移除 streaming Paraformer 常驻链路，static Paraformer 与标点模型仅在 Qwen 确认失败后懒加载，portable 不再打包 streaming 权重。

## [2026-08-09 13:05] ingest | 可取消 Qwen preview

VAD 分句实验因英文 WER 显著退化而拒绝；生产改为 1 秒 cadence 的累积 preview，松键通过 request-ID 旁路 cancel 中止 active generation，再执行保持 baseline 准确率的完整录音 final。

## [2026-08-09 13:16] review | Qwen cancellable preview PASS

独立审查确认旁路取消只作用于 active preview，不会发布 stale partial、误取消 final、触发 Qwen restart 或加载 Paraformer；Windows tests、长音频 smoke 与真实麦克风验收均通过。

## [2026-08-10 19:34] ingest | 收敛为 static Paraformer 单模型伪流式

生产 preview/final 改为同一个 CPU static Paraformer，删除 Qwen/Torch/CUDA 与 true-streaming Paraformer 的代码、配置、权重和 runtime；保留完整录音 final、final 优先 gate、release 后禁止迟到 partial、目标恢复与一次注入。

## [2026-08-10 20:16] ingest | 自适应伪流式与逐字预览

Paraformer preview 改为 1–2 秒自适应 monotonic deadline，跳过过期轮次；overlay 将每批 partial 以约 45ms/字展开，修订时保留公共前缀，final 仍立即显示并唯一注入。

## [2026-08-10 21:31] review | Static Paraformer pseudo-streaming PASS

独立复审确认单模型自适应 preview、逐字 overlay、完整 final、一次注入与 cleanup 边界正确；14 次真实 session 后 steady-state working set 约 500.3 MiB，低于 512 MiB 上限，无 GPU 模型进程。

## See Also

- [Overview](overview.md) — 当前项目全景。
- [Wiki Schema](../SCHEMA.md) — Wiki 维护规范。
## [2026-08-10 23:46] ingest | Windows application release pipeline

新增 Windows staging build、portable ZIP、Inno per-user 安装器、开始菜单/自启/卸载语义与远程发布边界；同步更新 Wiki index。

## [2026-08-10 23:48] review | Windows release packaging PASS

独立审查确认 x64 GUI bundle、staging、portable/setup hashes、per-user 安装、开始菜单、自启、卸载与真实 ASR smoke 均通过；记录未签名等非阻塞风险。

## [2026-08-11 01:40] review | Windows 1.0.0 release packaging PASS

版本提升至 1.0.0 并新增一致性测试；独立复审确认 38 tests、完整构建、双产物 hashes、原地升级、快捷方式、卸载版本与 ASR smoke 均通过。
