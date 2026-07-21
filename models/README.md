# Models

VoxPill uses Apache-2.0 licensed INT8 ONNX models with sherpa-onnx:

- `asr/model.int8.onnx`: Paraformer Chinese/English ASR, 243,371,218 bytes,
  SHA-256 `f36a0433bcf096bd6d6f11b80a3ac8bed110bdca632fe0d731df8d1a84475945`.
- `asr-streaming/encoder.int8.onnx`: bilingual streaming Paraformer encoder,
  165,462,184 bytes, SHA-256 `81a70226a8934e6ed92aa1d4fc486b428b5398e2f2619ed4897b7294cab90e9a`.
- `asr-streaming/decoder.int8.onnx`: bilingual streaming Paraformer decoder,
  71,664,561 bytes, SHA-256 `f3cca9f77bb9d93c8fcbfb63ae617b6b1ee96818df3aa3b151c40658fe38594f`.
- `punctuation/model.int8.onnx`: Chinese/English CT-Transformer punctuation,
  75,519,198 bytes,
  SHA-256 `65a3fb9f5ad7bfb96bf69e0dc4481df97f6ee60513c1d94ce981ba6effd524b1`.

Sources:

- https://huggingface.co/csukuangfj/sherpa-onnx-paraformer-zh-2023-09-14
- https://huggingface.co/csukuangfj/sherpa-onnx-streaming-paraformer-bilingual-zh-en
- https://huggingface.co/ranger810/sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8
