---
title: Streaming ASR 与自适应 Overlay Review
type: workflow
updated: 2026-07-21 16:14
---

# Streaming ASR 与自适应 Overlay Review

Contract: [Streaming Overlay Contract](../contracts/streaming-overlay-contract.md)

Verdict: PASS

## Validation Evidence

- 独立复查 `main.py`、`asr.py`、`overlay.py`、配置、测试与运行链路；Python compile check 通过，Windows `unittest discover -s bench/tests -v` 为 21/21 PASS。
- 默认热键、无效配置 fallback、README 与 Wiki 均已切换到右 Ctrl；partial 只传给 overlay，final 仍只有一条注入路径。
- `punctuate_streaming_text`、online decode 与 final punctuation 共用 pipeline `decode_lock`。真实 Windows 模型连续 30 次 partial punctuation：mean 7.43 ms、median 7.29 ms、P95 8.10 ms、max 10.93 ms，未形成明显 streaming 阻塞。
- `expanded_layout` 对 width、height、lines 分别取历史最大值；Windows lifecycle smoke 中长 partial 后的短 revision 保持 `(408, 40, 1)`，foreground 保持不变，committed 后进入 hidden，UI thread 正常关闭。
- renderer 只生成透明画布上的完整纯黑 rounded pill 与白色 meter/text；未发现 gradient、outline、shadow、screen capture 或 blur 路径，per-pixel premultiplied alpha 与 persistent DIB 提交逻辑保持不变。
- caret fallback 顺序为 GUI thread caret → MSAA `OBJID_CARET` → UI Automation focused element/TextPattern2 → focused window → cursor。当前 Windows 前台重复查询稳定返回 `focus-window`：首轮 40.70 ms，之后 5.88–7.25 ms，无崩溃或异常外泄。
- COM ABI 核对通过：IUIAutomation `GetFocusedElement` vtable index 8、IUIAutomationElement `GetCurrentPattern` index 16、TextPattern2 `GetCaretRange` index 10、TextRange `GetBoundingRectangles` index 10；`HRESULT`、pointer-sized interface arguments、`BOOL` 与 `VARIANT` 布局正确。automation、element、pattern、range 均在 `finally` 中 Release；返回 SAFEARRAY 成功读取后 Unaccess，并无条件 Destroy。
- MSAA `IAccessible::accLocation` vtable index 22、`CHILDID_SELF` 的 `VT_I4 VARIANT` 传值与最终 Release 正确；单条链失败会被捕获并继续下一级，不会阻塞 overlay 初始化或 ASR。

## Blocking Issues

None.

## Residual Risk

- 当前自动化环境中的 Electron/Codex 输入框仍未暴露可用 TextPattern2 caret，实际返回 `focus-window`；Electron、Chromium、微信等自绘输入框的精确 caret 位置必须做交互式人工验收。
- TextPattern2 成功返回 bounding-rectangle SAFEARRAY 的路径未能在当前前台应用实际触发；ABI 与释放路径静态正确，但仍需在确实暴露 TextPattern2 的应用中做动态内存/坐标验证。
- 右 Ctrl 仍由轮询而非键盘 hook 吞键；较右 Alt 更少触发菜单副作用，但目标应用仍会收到该 modifier。target 保护也仍只恢复 top-level HWND，而不是同一窗口内部的 child-control/caret。
- worker join 使用 2 秒上限；极端 runtime 卡死时依赖进程退出回收 daemon worker。

## Wiki Check

`SCHEMA.md`、`wiki/overview.md`、`wiki/architecture/runtime-pipeline.md`、`wiki/index.md` 与 `wiki/log.md` 已同步右 Ctrl、带标点 partial、单 session 最大布局、纯黑 pill 和 caret fallback 链；相对链接有效。ASR 四模型页面继续作为历史 benchmark 工作流保留。
