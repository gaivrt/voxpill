# ASR Benchmark

The benchmark measures the current static Paraformer on the fixed 12-utterance
personal corpus. Each run records Chinese CER, English WER, mixed MER, load time,
RTF, and peak process working set.

## Record the corpus

```powershell
uv run python bench\record_corpus.py --list-devices
uv run python bench\record_corpus.py --device 设备编号
```

Recordings are 16 kHz mono PCM16 WAV files under `bench/corpus/audio/`. Existing
files are skipped unless `--redo` is passed.

## Download models

```powershell
uv run python bench\download_models.py current_paraformer punctuation
uv run python bench\smoke_models.py current_paraformer
```

`models.toml` fixes the source and minimal INT8 file set. The downloader records
file sizes, source URLs, and SHA-256 receipts in ignored local runtime state.

## Run

```powershell
uv run python bench\benchmark.py --model current_paraformer
```

Each run writes an ignored `bench/results/YYYYMMDD-HHMMSS/` directory with a
summary CSV and per-utterance JSON.

## Metrics

- CER: Chinese character error rate after punctuation/space normalization.
- WER: lowercase English word error rate; non-Latin hallucinations count as insertions.
- MER: Chinese-character/English-word mixed error rate.
- RTF: inference seconds divided by audio seconds; below 1 is faster than real time.
- Peak working set: peak memory of the isolated recognizer process.

The fixed Windows baseline is CER 10.60%, WER 20.83%, MER 28.79%, corpus RTF
0.098, and about 365 MiB peak working set.
