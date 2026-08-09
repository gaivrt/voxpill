# Qwen final-pass integration review

- Date: 2026-08-09
- Contract: [`../contracts/qwen-final-pass-integration-contract.md`](../contracts/qwen-final-pass-integration-contract.md)
- Verdict: PASS

## Validation evidence

- Windows production environment: 41/41 tests passed; `py_compile` and `uv lock --check` passed.
- Qwen loads only after Paraformer is ready, in an independent Windows Python worker. The production environment has no Torch, Transformers, or Accelerate installation.
- Local JSON-line IPC uses request IDs and serial requests. Late or unknown responses are discarded.
- Qwen success follows one final injection path. Not-ready, empty, timeout, error, and oversized-audio paths safely retain the Paraformer fallback.
- Timeout recovery restarts the worker. Cleanup validation left `NO_QWEN_WORKER`.
- The PCM buffer is bounded and permanently disables Qwen for an overflowing recording.
- Runtime logs show Paraformer ready in 1.5 seconds, Qwen ready in the background in 9.2 seconds, and consecutive real recordings completing with `[qwen] final ready` before their text was injected.
- The observed two-PID pairs are Windows virtual-environment launchers plus their interpreters: one logical VoiceKey process and one logical Qwen worker, not duplicate model instances.

## Residual risk

- Paraformer partial text and Qwen final text can differ visibly; this is a product-experience limitation of the current two-model preview, not a final-pass correctness defect.
- An 8-second timeout may fall back to Paraformer for unusually long recordings or a busy GPU.
- Portable builds still require an external Windows Qwen runtime and local model directory.
- Timeout/restart/cleanup evidence currently comes from Windows integration smoke rather than a fake-subprocess unit test.

## Wiki check

README, schema, runtime-pipeline, overview, benchmark operations, index, and log describe the current source integration and retain the portable-packaging boundary.
