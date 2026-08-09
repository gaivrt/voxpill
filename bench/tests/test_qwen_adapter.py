from __future__ import annotations

from contextlib import nullcontext
import unittest

import numpy as np

from bench.benchmark import (
    Qwen3Recognizer,
    decode_qwen3,
    peak_gpu_reserved_mb,
    synchronize_recognizer,
)


class _FakeTensor:
    shape = (1, 3)

    def __getitem__(self, key):
        del key
        return self


class _FakeInputs(dict):
    def to(self, device, dtype):
        self["to"] = (device, dtype)
        return self


class _FakeProcessor:
    class _FeatureExtractor:
        sampling_rate = 16000

    feature_extractor = _FeatureExtractor()

    def __init__(self):
        self.request = None

    def apply_transcription_request(self, **request):
        self.request = request
        return _FakeInputs(input_ids=_FakeTensor())

    def decode(self, generated_ids, return_format):
        self.decoded = (generated_ids, return_format)
        return ["  测试 Qwen final  "]


class _FakeModel:
    device = "cpu"
    dtype = "float32"

    def __init__(self):
        self.generate_kwargs = None

    def generate(self, **kwargs):
        self.generate_kwargs = kwargs
        return _FakeTensor()


class _FakeTorch:
    class cuda:
        calls = []

        @classmethod
        def synchronize(cls, device):
            cls.calls.append(device)

    @staticmethod
    def inference_mode():
        return nullcontext()


class QwenAdapterTest(unittest.TestCase):
    def test_decode_uses_shared_pcm_and_optional_context(self):
        model = _FakeModel()
        processor = _FakeProcessor()
        recognizer = Qwen3Recognizer(
            model=model,
            processor=processor,
            torch=_FakeTorch(),
            device="cpu",
            dtype="float32",
            max_new_tokens=64,
            context="Vocabulary: VoxPill, Qwen3-ASR.",
        )
        samples = np.zeros(1600, dtype=np.float32)

        result = decode_qwen3(recognizer, samples, 16000)

        self.assertEqual(result["text"], "测试 Qwen final")
        self.assertIs(processor.request["audio"], samples)
        self.assertIn("VoxPill", processor.request["prompt"])
        self.assertEqual(model.generate_kwargs["max_new_tokens"], 64)
        self.assertFalse(model.generate_kwargs["do_sample"])
        self.assertIsNone(peak_gpu_reserved_mb(recognizer))

    def test_decode_rejects_mismatched_sample_rate(self):
        recognizer = Qwen3Recognizer(
            model=_FakeModel(),
            processor=_FakeProcessor(),
            torch=_FakeTorch(),
            device="cpu",
            dtype="float32",
            max_new_tokens=64,
            context="",
        )
        with self.assertRaisesRegex(ValueError, "expects 16000 Hz"):
            decode_qwen3(recognizer, np.zeros(1600, dtype=np.float32), 8000)

    def test_cuda_recognizer_synchronizes_before_load_timing_stops(self):
        _FakeTorch.cuda.calls.clear()
        recognizer = Qwen3Recognizer(
            model=_FakeModel(),
            processor=_FakeProcessor(),
            torch=_FakeTorch(),
            device="cuda:0",
            dtype="bfloat16",
            max_new_tokens=64,
            context="",
        )

        synchronize_recognizer(recognizer)

        self.assertEqual(_FakeTorch.cuda.calls, ["cuda:0"])


if __name__ == "__main__":
    unittest.main()
