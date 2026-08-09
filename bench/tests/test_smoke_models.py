from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bench import smoke_models


class SmokeOutputTest(unittest.TestCase):
    @patch("bench.smoke_models.peak_gpu_reserved_mb", return_value=456.0)
    @patch("bench.smoke_models.peak_working_set_mb", return_value=123.0)
    @patch("bench.smoke_models.decode_qwen3")
    @patch("bench.smoke_models.synchronize_recognizer")
    @patch("bench.smoke_models.load_recognizer")
    @patch("bench.smoke_models.validate_model_files")
    @patch("bench.smoke_models.resolve_model_paths")
    @patch("bench.smoke_models.load_models")
    def test_qwen_smoke_reports_runtime_and_memory(
        self,
        load_models,
        resolve_model_paths,
        validate_model_files,
        load_recognizer,
        synchronize_recognizer,
        decode_qwen3,
        peak_working_set_mb,
        peak_gpu_reserved_mb,
    ):
        del validate_model_files, peak_working_set_mb, peak_gpu_reserved_mb
        spec = {"kind": "offline_qwen3_asr"}
        recognizer = SimpleNamespace(device="cuda:0", dtype="bfloat16")
        load_models.return_value = {"qwen": spec}
        resolve_model_paths.return_value = spec
        load_recognizer.return_value = recognizer
        decode_qwen3.return_value = {"inference_seconds": 0.5, "text": ""}

        result = smoke_models.smoke("qwen")

        synchronize_recognizer.assert_called_once_with(recognizer)
        self.assertEqual(result["device"], "cuda:0")
        self.assertEqual(result["dtype"], "bfloat16")
        self.assertEqual(result["peak_working_set_mb"], 123.0)
        self.assertEqual(result["peak_gpu_reserved_mb"], 456.0)


if __name__ == "__main__":
    unittest.main()
