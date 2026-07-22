---
title: VoxPill 项目全景
type: overview
updated: 2026-07-22 10:17
---

# VoxPill 项目全景

## 定位

VoxPill 是一个常驻 Windows 的轻量离线语音输入工具。用户稳定按住可配置的单键说话时，应用保存当时的目标窗口，本地 INT8 ONNX 模型持续完成中英文流式识别，并在当前显示器底部中央的无焦点自动明暗 pill 预览 partial；松开后恢复目标窗口、恢复 final 标点并一次写入。核心目标是离线、低依赖、全局可用，并避免引入 PyTorch、CUDA 或云端服务。

## 用户链路

```text
按住右 Ctrl
  → 保存 foreground HWND 并录制 16 kHz 单声道 int16 PCM
  → bilingual streaming Paraformer 增量解码
  → 无焦点自动明暗 pill 显示带标点 partial
  → 松开后 flush final 并由 CT-Transformer 恢复标点
  → 恢复录音开始时的 HWND
  → 剪贴板粘贴或 Unicode SendInput 一次
  → 可选自动回车并收束浮窗
```

默认热键是右 Ctrl。短于 0.3 秒的录音会被忽略；partial 会经过 CT-Transformer 恢复标点但永不注入，只有非空 final 才通过剪贴板和 Ctrl+V 或 Unicode `SendInput` 提交。注入前必须成功恢复录音开始时保存的目标 HWND；窗口失效或无法恢复焦点时，本轮不注入。默认 paste 路径保留本次识别文本，避免目标应用延迟读取时粘贴旧内容。

## 主要组件

| 组件 | 职责 |
|------|------|
| `main.py` | 读取配置、确保单实例、保存目标 HWND、轮询物理键态、录音、调度推理与注入、跟踪 worker 和退出清理 |
| `hotkey.py` | 以 60 ms 稳定窗口和点击后 120 ms mouse guard 过滤短热键伪脉冲 |
| `asr.py` | 验证模型文件，初始化 sherpa-onnx online recognizer 和 punctuation pipeline，在共享锁内管理增量 decode、final flush 与标点恢复 |
| `overlay.py` | 运行独立 Win32 UI thread 和 60 Hz ticker，以 per-pixel alpha 在当前显示器底部中央绘制自动明暗 pill |
| `inject.py` | 封装 Win32 `SendInput`、Unicode 字符事件和剪贴板粘贴路径 |
| `tray.py` | 生成透明画布上的极简圆球与五段声纹托盘图标，并读取 Windows app theme 选择明暗配色 |
| `config.toml` | 定义热键、注入方式、剪贴板恢复、自动回车、最短录音和麦克风设备 |
| `models/` | 保存 Paraformer ASR 与 CT-Transformer 标点模型及 token 数据 |

## 运行模型

应用采用多线程常驻结构：主线程运行 Windows 托盘消息循环；轮询线程每 20 ms 读取热键物理状态；PortAudio callback 只复制音频 chunk；每轮 decode worker 完成增量识别，并与 final 标点恢复共用同一把锁；消费线程等待 punctuated final、恢复目标 HWND 并执行一次文本注入；overlay UI thread 处理 Win32 消息，独立 ticker 以 60 Hz 投递动画 frame。应用跟踪 poll、consumer 和 decode workers，cleanup 会发出停止信号、结束活跃 stream 并限时 join workers 后再关闭 overlay。若托盘依赖不可用，应用退化为主线程消费队列并通过 Ctrl+C 退出。

托盘 tooltip 和禁用菜单标题均只显示产品名 `VoxPill`，不重复热键或录音说明。图标在 8× supersampling 下绘制后缩放到 64 px，由 Windows 继续适配 16–32 px notification area；圆球直径占 64 px 画布中的 62 px，以充分利用 Windows 的小尺寸托盘槽位。图标只有圆形底面与五段声纹：浅色主题使用暖白球与深色声纹，深色主题使用黑球与暖白声纹；录音态仅切换到另一帧声纹。常驻轮询每秒检查一次 Windows app theme，无需重启即可自动更新托盘图标。

使用 `GetAsyncKeyState` 读取真实物理键态，是避免窗口焦点变化或 `keyup` 事件丢失后持续录音的关键设计。命名 mutex `Local\\GAIVR.VoxPill` 用于阻止多个进程同时加载模型。

## 平台边界

运行时直接调用 `ctypes.WinDLL`、Win32 剪贴板 API 和 `SendInput`，因此核心应用面向 Windows，而不是通用的跨平台 Python CLI。WSL 主要适合编辑、知识维护和部分静态检查；涉及麦克风、托盘、热键、剪贴板或 portable 构建的最终验证应在 Windows 环境完成。

## 模型与依赖

生产语音识别使用 bilingual streaming INT8 Paraformer encoder/decoder，标点恢复使用 INT8 CT-Transformer，均通过固定版本的 `sherpa-onnx` CPU runtime 加载。旧的 offline Paraformer 仍作为本地基线资产保留，但不在当前主链路中加载。项目使用 Python 3.11 或更高版本，以 `uv` 管理依赖。公开源码仓库不跟踪模型权重；首次运行前通过 `bench/download_models.py` 下载 streaming ASR 与标点资产。

模型二进制是大型资产，Wiki 只维护其角色、来源、许可证、尺寸和校验信息，不读取或复制模型内容。

## 配置与交付

overlay 默认在每次 show 时读取 Windows `AppsUseLightTheme`：浅色使用暖白 `#faf9f5` 与深灰内容，深色使用纯黑与暖白内容；也可通过 `overlay.theme` 强制 `light` 或 `dark`。两套主题都使用 1 DIP 极低透明度暖灰边框，不包含渐变或投影。源码入口为 `uv run python -u main.py`，`start-voicekey.bat` 提供 Windows 前台启动，`start-voicekey-hidden.vbs` 用于无窗口启动。开机自启应在 `shell:startup` 中创建指向项目内 VBS 的 `VoxPill.lnk`，不能复制 VBS 本体；项目移动后需重建快捷方式，并移除仍指向 `dist\\voicekey\\voicekey.exe` 的旧入口。PyInstaller 以 onedir、windowed 方式生成 `dist\\VoxPill\\VoxPill.exe`，同时收集配置、模型和 sherpa-onnx 运行文件。

## 当前工程状态

- 项目结构小而集中；`bench/tests/` 覆盖 benchmark 配置、streaming runtime 与 overlay 纯函数/状态行为。
- `README.md` 已覆盖主要用户操作、性能概况和配置示例。
- `.venv/`、`build/`、`dist/`、`__pycache__/` 和 `voxpill.log` 属于本地或生成状态，不应作为 Wiki ingest 来源。

## See Also

- [Wiki Index](index.md) — 全部知识页索引。
- [流式语音输入运行链路](architecture/runtime-pipeline.md) — streaming decode、final 注入与自适应 overlay 的线程和状态边界。
- [Wiki Schema](../SCHEMA.md) — Wiki 分类、约定和维护流程。
