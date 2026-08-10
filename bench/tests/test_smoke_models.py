from __future__ import annotations

import unittest
from unittest.mock import patch

from bench import smoke_models


class SmokeOutputTest(unittest.TestCase):
    @patch("bench.smoke_models.peak_working_set_mb", return_value=123.0)
    @patch("bench.smoke_models.decode_offline")
    @patch("bench.smoke_models.load_recognizer")
    @patch("bench.smoke_models.validate_model_files")
    @patch("bench.smoke_models.resolve_model_paths")
    @patch("bench.smoke_models.load_models")
    def test_static_smoke_reports_cpu_runtime_and_memory(
        self,
        load_models,
        resolve_model_paths,
        validate_model_files,
        load_recognizer,
        decode_offline,
        peak_working_set_mb,
    ):
        del validate_model_files, peak_working_set_mb
        spec = {"kind": "offline_paraformer"}
        recognizer = object()
        load_models.return_value = {"static": spec}
        resolve_model_paths.return_value = spec
        load_recognizer.return_value = recognizer
        decode_offline.return_value = {"inference_seconds": 0.5, "text": ""}

        result = smoke_models.smoke("static")

        self.assertEqual(result["device"], "cpu")
        self.assertIsNone(result["dtype"])
        self.assertEqual(result["peak_working_set_mb"], 123.0)
        self.assertIsNone(result["peak_gpu_reserved_mb"])


if __name__ == "__main__":
    unittest.main()
