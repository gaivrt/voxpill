# ASR Benchmark

这套实验比较普通话、英文和句内 code-switch 的准确率与 Windows CPU 成本。每个模型在独立子进程运行，结果包括 CER、WER、MER、load time、RTF、peak working set；只有原生 online 模型才记录 first partial audio position。

## 1. 录制同一套语料

```powershell
uv run python bench\record_corpus.py --list-devices
uv run python bench\record_corpus.py --device 设备编号
```

每条录音使用 16 kHz mono PCM16 WAV，保存在 `bench/corpus/audio/`。已有文件默认跳过；需要重录时显式加 `--redo`。

## 2. 下载实验模型

```powershell
uv run python bench\download_models.py --all
```

下载范围由 `models.toml` 固定；当前只保留 baseline 和被选中用于原型的 bilingual streaming Paraformer。下载器优先从作者维护模型的 Hugging Face 镜像逐文件取得最小 INT8 集合，加 `--origin` 可绕过镜像。下载完成后，`bench/model_cache/checksums.json` 记录来源 URL、文件尺寸与 SHA-256。已放弃模型的历史实验结果仍保存在旧 results run 中。

下载后可先做不依赖录音的模型加载 smoke test：

```powershell
uv run python bench\smoke_models.py --all
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

每次结果写到独立的 `bench/results/YYYYMMDD-HHMMSS/`，其中 `summary.csv` 用于横向比较，单模型 JSON 保留每条语料的 reference、hypothesis 与指标。

## 指标解释

- CER：中文去除标点和空格后的字符错误率。
- WER：英文按 lowercase word 计算；hypothesis 中额外出现的中文或其他非 Latin 字母数字也按 insertion 计分。
- MER：中文逐字、英文逐词的混合错误率。
- RTF：推理时间除以音频时长；小于 1 表示快于实时。`corpus_rtf` 使用总推理时间除以总音频时长，`mean_rtf` 是逐句 RTF 的平均值。online decode 的推理时间包含用于 flush 的额外 500 ms 静音，但分母只计算原始语料，因此结果是偏保守的处理成本。
- first partial audio position：喂入多少毫秒音频后第一次得到非空 partial；它不是端到端 wall-clock latency。
- peak working set：整个模型子进程的峰值内存，不只是 ONNX 权重。

不同类别使用各自指标，不应把 CER、WER 和 MER 混成一个总分。选择模型时优先看个人语音上的准确率，再看是否真 streaming、RTF 与内存。
