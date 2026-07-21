from __future__ import annotations

import json
import unittest
from pathlib import Path

from bench.benchmark import (
    PROMPTS,
    load_models,
    peak_working_set_mb,
    resolve_model_paths,
    validate_model_files,
)


class ConfigurationTest(unittest.TestCase):
    @staticmethod
    def _assets_available(spec: dict) -> bool:
        required = spec.get("required", ["model", "tokens"])
        return all(Path(spec[key]).is_file() for key in required)

    def test_expected_model_matrix(self):
        models = load_models()
        self.assertEqual(
            set(models),
            {"current_paraformer", "streaming_paraformer"},
        )
        self.assertTrue(models["streaming_paraformer"]["true_streaming"])

    def test_current_model_files_exist(self):
        spec = resolve_model_paths(load_models()["current_paraformer"])
        if not self._assets_available(spec):
            self.skipTest("baseline model assets are not downloaded")
        validate_model_files("current_paraformer", spec)

    def test_all_downloaded_model_files_exist(self):
        for model_id, raw_spec in load_models().items():
            with self.subTest(model_id=model_id):
                spec = resolve_model_paths(raw_spec)
                if not self._assets_available(spec):
                    continue
                validate_model_files(model_id, spec)

    def test_prompt_balance_and_unique_ids(self):
        prompts = json.loads(PROMPTS.read_text(encoding="utf-8"))
        self.assertEqual(len(prompts), 12)
        self.assertEqual({item["category"] for item in prompts}, {"zh", "en", "mixed"})
        self.assertEqual(len({item["id"] for item in prompts}), len(prompts))
        for category in ("zh", "en", "mixed"):
            self.assertEqual(sum(item["category"] == category for item in prompts), 4)

    def test_peak_working_set_is_available(self):
        self.assertGreater(peak_working_set_mb(), 0)


if __name__ == "__main__":
    unittest.main()
