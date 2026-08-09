# Qwen pseudo-streaming and lazy fallback review

- Date: 2026-08-09
- Contract: [`../contracts/qwen-pseudo-streaming-contract.md`](../contracts/qwen-pseudo-streaming-contract.md)
- Verdict: PASS

## Validation evidence

- Windows production environment: 49/49 tests passed; focused runtime tests: 21/21 passed.
- `py_compile` and `uv lock --check` passed. The production environment contains no Torch, Transformers, or Accelerate installation.
- Healthy Windows WAV smoke produced a Qwen preview and Qwen final while `paraformer_loaded=false`.
- Forced missing-Qwen smoke changed the client to `failed`, then loaded static Paraformer once and returned a fallback transcript in about 1.9 seconds.
- Real microphone evidence: Qwen published a preview at 6.7 seconds captured, returned the final for 8.7 seconds of audio, and logged that Paraformer remained unloaded.
- The actual app interpreter used about 60 MiB working set on the healthy path; the Qwen interpreter held the model separately.
- Request serialization gives waiting final requests priority over waiting previews. A final waits behind at most the active request.
- `preview_lock` makes session stop and partial publication mutually exclusive, preventing a stopped session from publishing a stale preview.
- Cleanup now marks the session stopped and ends capture before closing Qwen. Shutdown cancellation prevents Qwen close/errors from triggering a new Paraformer load.
- Static Paraformer is absent from normal startup and loads only through the failure fallback. Portable build inputs exclude the legacy streaming Paraformer weights.
- A Windows virtual-environment launcher experiment confirmed that terminating the launcher also terminates its actual child; tray cleanup therefore releases the Qwen/Torch process, RAM, and VRAM.

## Residual risk

- Pseudo-streaming re-decodes all accumulated audio. Near the 30-second preview limit, a preview can take noticeably longer.
- A static fallback that began synchronously before the user clicked Exit cannot be interrupted mid-load, but it exits and releases memory with the VoxPill process.
- Qwen portable packaging still depends on the external Windows runtime and checkpoint.

## Wiki check

README, schema, overview, runtime pipeline, benchmark operations, model metadata, index, and log describe Qwen pseudo-streaming, final priority, and static Paraformer lazy fallback consistently.
