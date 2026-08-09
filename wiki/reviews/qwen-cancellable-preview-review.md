# Qwen cancellable preview review

- Contract: [Qwen cancellable preview contract](../contracts/qwen-cancellable-preview-contract.md)
- Date: 2026-08-09
- Verdict: PASS

## Evidence

- Windows production suite: 54/54 tests PASS; `py_compile` and `uv lock --check` PASS.
- Production `.venv-win` still excludes Torch, Transformers, and Accelerate.
- `cancel_preview()` bypasses the inference gate through a separately locked write path; only a request registered with `priority="preview"` can become its target. Wrong/late IDs are ignored and final is never registered as cancellable.
- The worker stdin reader can set a request-scoped event during generation; the Transformers stopping criterion returns a batch BoolTensor. A cancelled preview publishes no text and does not call failure fallback or restart Qwen.
- Release marks the session stopped under the same lock used by partial publication, then cancels active preview before final is queued. No stale partial can publish after that boundary.
- Two 16.588-second WAV smokes released the preview gate in 0.574–0.837 seconds; subsequent full-recording finals completed in 1.988–2.814 seconds and exactly matched the fixed baseline.
- Three real microphone runs (2.8, 3.8, and 6.6 seconds) showed `preview ready → preview cancelled for final → Qwen final ready`; the 6.6-second run produced multiple partials and Paraformer remained unloaded throughout.
- Runtime inspection showed one logical App and one logical Qwen worker, with no duplicate model process.

## Residual risk

- Final protection is enforced by the trusted local parent rather than a `priority` field in the private pipe protocol. This is acceptable for the current single-client architecture and is covered by tests.
- The reviewer did not stop the user-visible App to repeat tray cleanup. The standalone cancellation smoke completed `client.close()` without an orphan; terminate/pending cleanup remains the previously reviewed lifecycle.

## Wiki check

Runtime architecture, overview, benchmark notes, index, and log describe the accepted cancellable-preview design and the rejected VAD experiment without presenting it as production behavior.
