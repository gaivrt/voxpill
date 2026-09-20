import unittest

from overlay_native import caption, tail
from overlay_unix import SubtitleState


class SubtitleTest(unittest.TestCase):
    def test_partial_revisions_reveal_unicode_characters(self):
        state = SubtitleState()
        state.apply("show", 1, "", 0)
        state.apply("partial", 1, "今天很好 Hello", 0)
        state.tick(0)
        self.assertEqual(state.text, "今")
        state.tick(0.1)
        self.assertEqual(state.text, "今天")
        state.apply("partial", 1, "今日晴天", 0.2)
        self.assertEqual(state.text, "今")
        state.tick(0.2)
        self.assertEqual(state.text, "今日")

    def test_final_ignores_late_partial_then_retires(self):
        state = SubtitleState()
        state.apply("show", 1, "", 0)
        self.assertEqual(caption(state), "正在聆听…")
        state.apply("finalizing", 1, "", 1)
        self.assertEqual(caption(state), "正在识别…")
        state.apply("finalizing", 1, "你好 world", 2)
        state.apply("partial", 1, "wrong", 2.1)
        self.assertEqual(state.text, "你好 world")
        state.apply("committed", 1, "你好 world", 3)
        state.tick(3.7)
        self.assertEqual(state.text, "你好 world")
        state.tick(3.9)
        self.assertEqual(state.status, "hidden")
        self.assertIsNone(state.session)

    def test_new_session_cancels_old_deadline_and_events(self):
        state = SubtitleState()
        state.apply("show", 1, "", 0)
        state.apply("committed", 1, "old", 1)
        state.apply("show", 2, "", 1.1)
        for command in ("partial", "finalizing", "committed", "dismiss"):
            state.apply(command, 1, "stale", 1.2)
        state.tick(2)
        self.assertEqual((state.session, state.status, state.text), (2, "listening", ""))
        state.apply("dismiss", 2, "", 2)
        state.tick(2.2)
        self.assertEqual(state.status, "hidden")

    def test_long_caption_keeps_newest_text_with_bounded_measurement(self):
        calls = []
        def measure(text):
            calls.append(text)
            return len(text) * 10
        text = "a" * 1000 + "你好世界"
        result = tail(text, measure, 100)
        self.assertTrue(result.endswith("你好世界"))
        self.assertLessEqual(len(result), 10)
        self.assertLess(len(calls), 15)
        self.assertEqual(tail("hello", len, 10), "hello")


if __name__ == "__main__":
    unittest.main()
