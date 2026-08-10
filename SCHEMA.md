# SCHEMA — VoxPill LLM Wiki

## Project

VoxPill 是一个面向 Windows 的 CPU-only 离线全局语音输入工具：按住右 Ctrl 时保存目标窗口，由单个 static INT8 Paraformer 以 1–2 秒自适应节奏重识别累积音频，并在无焦点、自动适配 Windows 明暗主题的 pill 中逐字伪流式预览；松开后停止 preview 发布，以 final 优先级识别完整录音，随后恢复目标窗口并一次注入。

## Project Structure

| 路径 | 角色 |
|------|------|
| `main.py` | 应用入口；管理单实例、配置、热键轮询、录音、目标 HWND、static Paraformer preview/final、注入、worker 与进程生命周期 |
| `hotkey.py` | 对 push-to-talk 物理键态做稳定窗口与 mouse guard，过滤连续点击产生的短伪脉冲 |
| `asr.py` | 启动时加载唯一的 static Paraformer + CT-Transformer pipeline，提供有界 PCM、final 优先 gate 与累积音频伪流式调度 |
| `overlay.py` | 以独立 Win32 UI thread 和 60 Hz ticker 在当前显示器底部中央显示 no-activate、per-pixel alpha 的自动明暗 pill |
| `inject.py` | 通过剪贴板或 Win32 `SendInput` 向焦点窗口注入文本 |
| `tray.py` | 生成空闲与录音状态的托盘图标 |
| `config.toml` | 用户可编辑的 push-to-talk 热键、overlay 主题、注入行为、preview cadence/PCM 上限和音频设备配置；默认使用右 Ctrl 与 auto 主题 |
| `models/` | 生产 static Paraformer、标点模型和 token 文件；`models/README.md` 记录来源、许可证和校验值 |
| `pyproject.toml` / `uv.lock` | Python 项目元数据、运行依赖与锁定版本 |
| `voicekey.spec` / `build-portable.bat` | PyInstaller portable 构建配置与 Windows 构建入口 |
| `start-voicekey.bat` / `start-voicekey-hidden.vbs` | 前台启动及隐藏自启动入口 |
| `README.md` | 面向用户的功能、运行、配置和打包说明 |
| `.venv/`, `build/`, `dist/`, `__pycache__/` | 依赖、缓存和构建产物；不是知识吸收来源 |
| `voxpill.log` | 单次运行诊断日志；属于 runtime state，不进入 Wiki |

所有项目文件均可编辑。修改模型二进制前必须明确确认目标、来源与校验信息。

## Wiki Structure

```text
wiki/
├── index.md                       # 内容索引
├── log.md                         # Wiki 操作日志
├── overview.md                    # 项目全景
├── architecture/
│   ├── runtime-pipeline.md        # 热键到文本注入的运行链路
│   └── windows-integration.md     # Win32、剪贴板、托盘和单实例边界
├── operations/
│   ├── configuration.md           # 配置语义和默认行为
│   ├── build-and-distribution.md  # 依赖、portable 构建与交付
│   └── troubleshooting.md         # 常见故障与诊断入口
├── assets/
│   └── speech-models.md           # 模型元数据、来源和许可证
└── decisions/                     # 重要、长期有效的技术决策
```

结构图中的专题页面按 ingest 或实际需要创建；不得为了填满目录而生成空泛页面。

## Page Types

- **overview** — 项目目标、边界、能力和整体结构。
- **subsystem** — 一个稳定子系统的职责、接口、状态与失败边界。
- **workflow** — 跨文件的运行、构建、发布或维护流程。
- **configuration** — 配置字段、默认值、容错和相互影响。
- **asset** — 模型等大型资产的用途、来源、许可证、尺寸和校验信息。
- **decision** — 有长期影响的技术选择、理由、替代方案和后果。
- **troubleshooting** — 可观察症状、诊断路径、原因和恢复方法。

## Conventions

- 文件名使用 kebab-case，如 `runtime-pipeline.md`。
- 内链使用相对 Markdown 链接，如 `[运行链路](wiki/architecture/runtime-pipeline.md)`。
- 每个 Wiki 页面带 YAML frontmatter：

  ```yaml
  ---
  title: 页面标题
  type: overview | subsystem | workflow | configuration | asset | decision | troubleshooting
  updated: YYYY-MM-DD HH:MM
  ---
  ```

- `updated` 使用 Asia/Macau 当前时间，精确到分钟。
- 页面只记录当前、可验证的项目知识；任务讨论和 review 历史不复制进正文。
- 页面底部使用 `## See Also` 放置相关页面链接；没有相关页面时可省略。
- `wiki/index.md` 必须覆盖所有知识页，`wiki/log.md` 只追加不改写历史。
- 源文件是事实依据；Wiki 与源码冲突时，以当前源码为准并修正 Wiki。

## Ingest Workflow

1. 判断 source 变化是否产生长期知识；trivial、生成物或 runtime-only 变化不 ingest。
2. 默认 ingest 源码、说明文档、配置和构建脚本；排除 `.venv/`、`build/`、`dist/`、`__pycache__/` 和日志。
3. 模型二进制不读取、不摘要；只从 `models/README.md` 和明确的构建配置吸收其元数据。
4. 小而集中的 ingest 由 main agent 直接完成；大型、跨模块或已委托的实现可使用 focused wiki-ingest subagent。
5. 完整读取目标 source，更新相关页面，并检查被其影响的交叉引用。
6. 更新 `wiki/index.md`，在 `wiki/log.md` 追加一条简洁记录。
7. 验收覆盖范围、事实准确性和链接完整性后结束 ingest。

## Query Workflow

1. 每个 session/worktree 的首次非 trivial 代码任务读取 `SCHEMA.md` 与 `wiki/index.md`；未变化时不重复读取。
2. 针对问题先读取最多一个最相关的 Wiki 页面。
3. Wiki 不足时再读取其他相关页面或回溯源文件。
4. 以当前源码验证易变或实现级细节。
5. 只有长期有用的新分析才写入 Wiki，并同步索引与日志。

## Lint Checklist

- [ ] 页面与当前源码之间没有矛盾或过时声明
- [ ] 所有知识页均被 `wiki/index.md` 收录
- [ ] 没有孤立页面、失效链接或缺失的交叉引用
- [ ] 模型信息包含来源、许可证和校验依据，不复制二进制内容
- [ ] 生成物、日志和临时状态未被误写成持久知识
- [ ] 新增的长期行为已记入相关页面和 `wiki/log.md`

## Log Format

每条记录使用二级标题，时间精确到分钟：

```markdown
## [YYYY-MM-DD HH:MM] operation | description

简要说明做了什么、影响了哪些页面。
```
