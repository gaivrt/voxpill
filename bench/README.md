# ASR Benchmark

这套实验比较普通话、英文和句内 code-switch 的准确率，以及 Windows CPU/GPU 成本。每个模型在独立子进程运行，结果包括 CER、WER、MER、load time、RTF、peak working set；CUDA 模型还记录 Torch peak reserved GPU memory，只有原生 online 模型才记录 first partial audio position。

## 1. 录制同一套语料

```powershell
uv run python bench\record_corpus.py --list-devices
uv run python bench\record_corpus.py --device 设备编号
```

每条录音使用 16 kHz mono PCM16 WAV，保存在 `bench/corpus/audio/`。已有文件默认跳过；需要重录时显式加 `--redo`。

## 2. 下载实验模型

```powershell
$QwenEnv = "$env:LOCALAPPDATA\voicekey-qwen-win"
$QwenPython = "$QwenEnv\Scripts\python.exe"
uv venv --python 3.11 $QwenEnv
uv pip install --python $QwenPython `
  --default-index https://pypi.tuna.tsinghua.edu.cn/simple `
  "https://download-r2.pytorch.org/whl/cu130/torch-2.12.0%2Bcu130-cp311-cp311-win_amd64.whl"
uv pip install --python $QwenPython `
  --default-index https://pypi.tuna.tsinghua.edu.cn/simple `
  "accelerate==1.14.0" "transformers==5.14.1"
& $QwenPython bench\download_models.py qwen3_asr_0_6b
```

Windows App 使用独立 LocalAppData runtime，避免 Torch/Transformers 改动生产 `.venv-win`；CUDA Torch 使用 PyTorch 官方 wheel，普通 PyPI 依赖使用清华 TUNA。单纯的模型准确率资格测试仍可在本机隔离 WSL CUDA 环境执行，但不能替代 Windows 部署证据。

下载范围由 `models.toml` 固定。Paraformer 继续从配置的 Hugging Face 源取得最小 INT8 集合；Qwen3-ASR 从官方 Hugging Face repo 的固定 commit snapshot 下载。下载完成后，`bench/model_cache/checksums.json` 记录来源、固定 revision、文件尺寸与 SHA-256。已放弃模型的历史实验结果仍保存在旧 results run 中。

下载后可先做不依赖录音的模型加载 smoke test：

```powershell
& $QwenPython bench\smoke_models.py qwen3_asr_0_6b
```

## 3. 运行

先跑当前 baseline：

```powershell
uv run python bench\benchmark.py --model current_paraformer
```

再跑全部模型：

```powershell
uv run python bench\benchmark.py --all
```

单独运行 Qwen3-ASR GPU final-pass：

```powershell
& $QwenPython bench\benchmark.py --model qwen3_asr_0_6b
```

每次结果写到独立的 `bench/results/YYYYMMDD-HHMMSS/`，其中 `summary.csv` 用于横向比较，单模型 JSON 保留每条语料的 reference、hypothesis 与指标。

## 指标解释

- CER：中文去除标点和空格后的字符错误率。
- WER：英文按 lowercase word 计算；hypothesis 中额外出现的中文或其他非 Latin 字母数字也按 insertion 计分。
- MER：中文逐字、英文逐词的混合错误率。
- RTF：推理时间除以音频时长；小于 1 表示快于实时。`corpus_rtf` 使用总推理时间除以总音频时长，`mean_rtf` 是逐句 RTF 的平均值。online decode 的推理时间包含用于 flush 的额外 500 ms 静音，但分母只计算原始语料，因此结果是偏保守的处理成本。
- first partial audio position：喂入多少毫秒音频后第一次得到非空 partial；它不是端到端 wall-clock latency。
- peak working set：整个模型子进程的峰值内存，不只是 ONNX 权重。
- peak GPU reserved：Qwen worker 内由 PyTorch allocator 观察到的峰值 reserved CUDA memory，不包含桌面和其他进程已占用的显存。

不同类别使用各自指标，不应把 CER、WER 和 MER 混成一个总分。选择模型时优先看个人语音上的准确率，再看是否真 streaming、RTF 与内存。
