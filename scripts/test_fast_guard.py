#!/usr/bin/env python3

"""Guard unit tests: python3 scripts/test_fast_guard.py"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fast_guard  # noqa: E402


class RiskyStepTests(unittest.TestCase):
    def test_a_destructive_tap_later_in_a_batch_is_risky(self) -> None:
        actions = [{"type": "tap_label", "label": "Edit"}, {"type": "tap_label", "label": "Delete Account"}]
        self.assertEqual(fast_guard.risky_step(actions), (2, "Delete Account"))

    def test_selectors_of_every_gesture_kind_are_checked(self) -> None:
        for action in ({"type": "tap_first", "label_contains": "Remove"}, {"type": "long_press", "id": "sign-out-button"},
                       {"type": "double_tap", "label": "Buy Now"},
                       {"type": "tap_nearest", "target": {"label": "Send"}, "anchor": {"label": "Ann"}}):
            with self.subTest(action=action["type"]):
                self.assertIsNotNone(fast_guard.risky_step([{"type": "wait", "label": "Home"}, action]))

    def test_confirmed_single_and_harmless_steps_pass(self) -> None:
        self.assertIsNone(fast_guard.risky_step([{"type": "tap_label", "label": "Delete"}]))
        self.assertIsNone(fast_guard.risky_step([{"type": "wait", "label": "Delete"}, {"type": "tap_label", "label": "Delete", "confirm": True}]))
        self.assertIsNone(fast_guard.risky_step([{"type": "tap_label", "label": "General"}, {"type": "tap_label", "label": "Sender Name"},
                                                 {"type": "wait", "label": "Payment History"}]))

    def test_ids_in_camel_or_snake_case_and_vietnamese_labels_are_caught(self) -> None:
        for text in ("deleteAccountButton", "signOutButton", "btn_delete", "delete_account", "Xóa tài khoản",
                     "Đăng xuất", "Thanh toán", "Gửi"):
            with self.subTest(text=text):
                self.assertIsNotNone(fast_guard.risky_step([{"type": "wait", "label": "x"}, {"type": "tap_label", "id": text}]))
        for text in ("Sender Name", "Payment History", "Hủy", "Cancel"):
            with self.subTest(text=text):
                self.assertIsNone(fast_guard.risky_step([{"type": "wait", "label": "x"}, {"type": "tap_label", "label": text}]))

    def test_extra_words_come_from_the_environment(self) -> None:
        import os
        from unittest import mock
        actions = [{"type": "wait", "label": "x"}, {"type": "tap_label", "label": "Archive Chat"}]
        self.assertIsNone(fast_guard.risky_step(actions))
        with mock.patch.dict(os.environ, {"FAST_GUARD_WORDS": "archive, block"}):
            self.assertEqual(fast_guard.risky_step(actions), (2, "Archive Chat"))

    def test_requests_are_checked_for_shape(self) -> None:
        with self.assertRaisesRegex(ValueError, "step 2: each action must be a JSON object"):
            fast_guard.check_actions([{"type": "wait", "label": "a"}, "b"])
        with self.assertRaisesRegex(ValueError, "step 1: expect must be a selector object"):
            fast_guard.check_actions([{"type": "tap_label", "label": "Go", "expect": "About"}])
        fast_guard.check_actions([{"type": "tap_label", "label": "Go", "expect": {"label": "About"}}])

    def test_prompt_labels_parse_from_text_or_rules(self) -> None:
        self.assertEqual(fast_guard.parse_prompt_labels("Allow, Don’t Allow"), ["Allow", "Don’t Allow"])
        self.assertEqual(fast_guard.parse_prompt_labels('[{"title_contains": "track", "tap": "Ask App Not to Track"}]'),
                         [{"title_contains": "track", "tap": "Ask App Not to Track"}])
        with self.assertRaisesRegex(ValueError, "tap"):
            fast_guard.parse_prompt_labels('[{"title_contains": "track"}]')


if __name__ == "__main__":
    unittest.main(verbosity=1)
