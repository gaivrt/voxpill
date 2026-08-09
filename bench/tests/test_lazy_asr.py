from __future__ import annotations

import unittest
from unittest.mock import patch

from asr import LazyOfflineAsr


class LazyOfflineAsrTest(unittest.TestCase):
    def test_model_is_loaded_only_on_first_recognition(self):
        loads = []
        pipeline = object()

        def loader(base_dir, say):
            loads.append((base_dir, say))
            return pipeline

        lazy = LazyOfflineAsr(loader=loader)
        self.assertFalse(lazy.is_loaded)
        self.assertEqual(loads, [])

        with patch("asr.transcribe", side_effect=["first", "second"]) as recognize:
            self.assertEqual(lazy.recognize(b"one"), "first")
            self.assertEqual(lazy.recognize(b"two"), "second")

        self.assertTrue(lazy.is_loaded)
        self.assertEqual(len(loads), 1)
        self.assertEqual(recognize.call_count, 2)


if __name__ == "__main__":
    unittest.main()
