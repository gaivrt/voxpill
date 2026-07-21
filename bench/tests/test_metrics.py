from __future__ import annotations

import unittest

from bench.metrics import edit_distance, english_words, mixed_tokens, normalize_text, score


class MetricsTest(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(normalize_text("Hello，ＷＯＲＬＤ！"), "hello world")

    def test_english_words(self):
        self.assertEqual(english_words("It's a CPU-based tool."), ["it's", "a", "cpu", "based", "tool"])

    def test_english_words_penalize_non_latin_hallucinations(self):
        self.assertEqual(english_words("hello 你好"), ["hello", "你", "好"])
        self.assertEqual(score("hello", "hello 你好", "en").edits, 2)
        self.assertEqual(score("hello", "你好", "en").edits, 2)
        self.assertEqual(score("hello", "", "en").edits, 1)

    def test_mixed_tokens(self):
        self.assertEqual(mixed_tokens("运行 unit tests，然后 build。"), ["运", "行", "unit", "tests", "然", "后", "build"])

    def test_edit_distance(self):
        self.assertEqual(edit_distance(list("kitten"), list("sitting")), 3)

    def test_scores(self):
        self.assertEqual(score("你好世界", "你好世", "zh").edits, 1)
        self.assertEqual(score("one two three", "one too three", "en").edits, 1)
        self.assertEqual(score("运行 tests", "运行 test", "mixed").edits, 1)

    def test_unknown_category(self):
        with self.assertRaises(ValueError):
            score("a", "a", "unknown")


if __name__ == "__main__":
    unittest.main()
